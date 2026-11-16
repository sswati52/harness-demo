import difflib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import urllib.request


ROOT = Path(__file__).resolve().parent
BUGGY = (ROOT / "cart.py").read_text(encoding="utf-8")
FIXED = BUGGY.replace("subtotal > 1000", "subtotal >= 1000")
FAULTY = FIXED.replace("    if not prices:\n        return 0\n", "")
TASK = (
    "Fix shipping: orders below INR 1000 pay INR 50; orders at or above "
    "INR 1000 ship free. Empty carts total zero. Negative prices are invalid. "
    "Preserve existing behavior."
)
TOOLS = (
    'Return one JSON action only. Actions: '
    '{"tool":"read_file","path":"cart.py"}, '
    '{"tool":"apply_patch","path":"cart.py","old":"exact existing text",'
    '"new":"replacement text"}, or {"tool":"finish"}. '
    "Only change the shipping comparison from > to >=. "
    "Do not use markdown or propose shell commands."
)


def run_checks(workspace):
    source = (workspace / "cart.py").read_text(encoding="utf-8")
    # The demo executes only these known templates, never arbitrary model code.
    if source not in (BUGGY, FIXED, FAULTY):
        raise ValueError("Execution blocked: source is outside known demo templates")
    completed = subprocess.run(
        [sys.executable, "-I", "-B", "-c",
         "import sys, unittest; sys.path.insert(0, '.'); "
         "suite = unittest.defaultTestLoader.loadTestsFromName('test_cart'); "
         "result = unittest.TextTestRunner(verbosity=2).run(suite); "
         "sys.exit(not result.wasSuccessful())"],
        cwd=workspace,
        capture_output=True,
        text=True,
        timeout=10,
    )
    return {
        "passed": completed.returncode == 0,
        "output": completed.stdout + completed.stderr,
        "exit_code": completed.returncode,
    }


class ReplayModel:
    def next_action(self, messages):
        results = [m["content"] for m in messages if m["role"] == "user"]
        if len(results) == 1:
            return {"tool": "read_file", "path": "cart.py"}
        latest = results[-1]
        if "FAILED" in latest:
            return {
                "tool": "apply_patch", "path": "cart.py",
                "old": "    subtotal = sum(prices)",
                "new": "    if not prices:\n        return 0\n    subtotal = sum(prices)",
            }
        if "subtotal > 1000" in latest:
            return {
                "tool": "apply_patch", "path": "cart.py",
                "old": "subtotal > 1000", "new": "subtotal >= 1000",
            }
        return {"tool": "finish"}


class OllamaModel:
    def next_action(self, messages):
        model = os.environ.get("OLLAMA_MODEL", "").strip()
        if not model:
            raise ValueError("Set OLLAMA_MODEL to an installed local model first")
        request = urllib.request.Request(
            "http://127.0.0.1:11434/api/chat",
            data=json.dumps({
                "model": model, "messages": messages, "stream": False,
                "format": "json", "options": {"temperature": 0},
            }).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
        # Ignore proxy variables: this adapter only sends demo context to localhost.
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with opener.open(request, timeout=60) as response:
            payload = response.read(65537)
        if len(payload) > 65536:
            raise ValueError("Model response exceeds the demo size limit")
        action = json.loads(json.loads(payload)["message"]["content"])
        if not isinstance(action, dict):
            raise ValueError("Model response must be a JSON object")
        return action


def run_demo(mode="engineered", provider="replay", scenario="happy"):
    if mode not in ("basic", "engineered"):
        raise ValueError("Unknown harness mode")
    if provider not in ("replay", "ollama"):
        raise ValueError("Unknown model provider")
    if scenario not in ("happy", "repair", "blocked", "budget"):
        raise ValueError("Unknown scenario")
    if scenario != "happy" and (mode != "engineered" or provider != "replay"):
        raise ValueError("Controlled scenarios require engineered + replay mode")

    events = []

    def log(kind, title, detail):
        events.append({"kind": kind, "title": title, "detail": detail})

    result = {
        "mode": mode, "provider": provider, "scenario": scenario,
        "status": "Incomplete", "events": events, "before": BUGGY,
        "after": BUGGY, "checks": None, "patch_attempts": 0,
        "model_summary": None,
    }
    model = ReplayModel() if provider == "replay" else OllamaModel()
    log("context", "Harness prepares context", TASK + "\n\n" + TOOLS)
    log("model", "Model provider", (
        "REPLAY: scripted model actions, not a live LLM. Real edits and tests."
        if provider == "replay" else
        "LIVE: requests to the local Ollama model. No remote API."
    ))
    messages = [
        {"role": "system", "content": TOOLS},
        {"role": "user", "content": TASK},
    ]

    with tempfile.TemporaryDirectory(prefix="harness-demo-") as directory:
        workspace = Path(directory)
        (workspace / "cart.py").write_text(BUGGY, encoding="utf-8")
        (workspace / "test_cart.py").write_text(
            (ROOT / "test_cart.py").read_text(encoding="utf-8"), encoding="utf-8"
        )
        try:
            if scenario == "blocked":
                log("model", "Prepared tool request (not a model failure)",
                    '{"tool":"apply_patch","path":"test_cart.py"}')
                log("blocked", "Harness rejects protected-file edit",
                    "Only cart.py is writable. Tests remain unchanged.")
                result["status"] = "Blocked"
                return result

            injected = False
            for _ in range(8):
                action = model.next_action(messages)
                log("model", "Model proposes action", json.dumps(action, indent=2))
                messages.append({"role": "assistant", "content": json.dumps(action)})
                tool = action.get("tool")
                if tool in ("read_file", "apply_patch"):
                    if action.get("path") != "cart.py":
                        log("blocked", "Harness denies path", "Only cart.py is allowed.")
                        result["status"] = "Blocked"
                        break
                if tool == "read_file":
                    observation = (workspace / "cart.py").read_text(encoding="utf-8")
                    log("tool", "Harness executes read_file", observation)
                elif tool == "apply_patch":
                    if result["patch_attempts"] >= 3:
                        log("blocked", "Patch budget exhausted", "Maximum 3 patch attempts.")
                        break
                    old, new = action.get("old"), action.get("new")
                    source = (workspace / "cart.py").read_text(encoding="utf-8")
                    if (not isinstance(old, str) or not old or
                            not isinstance(new, str) or source.count(old) != 1):
                        raise ValueError("Patch requires one exact non-empty match")
                    candidate = source.replace(old, new, 1)
                    if candidate not in (BUGGY, FIXED, FAULTY):
                        raise ValueError("Patch blocked: only known demo templates are allowed")
                    result["patch_attempts"] += 1
                    if scenario in ("repair", "budget") and (not injected or scenario == "budget"):
                        candidate = FAULTY
                        injected = True
                        log("warning", "Controlled fault injection",
                            "Demo fixture removes the empty-cart guard. "
                            "This is NOT a natural model mistake.")
                    (workspace / "cart.py").write_text(candidate, encoding="utf-8")
                    result["after"] = candidate
                    log("tool", "Harness executes apply_patch", candidate)
                    if mode == "basic":
                        observation = "Patch applied. No verification was run."
                    else:
                        checks = run_checks(workspace)
                        result["checks"] = checks
                        log("pass" if checks["passed"] else "fail",
                            "Harness independently runs 6 regression tests", checks["output"])
                        if checks["passed"]:
                            result["status"] = "Checks passed"
                            log("pass", "Harness completion gate accepts result",
                                "All 6 specified tests passed. Not proof of universal correctness.")
                            break
                        observation = checks["output"]
                        log("feedback", "Harness feeds test failure back to model", observation)
                elif tool == "finish":
                    result["model_summary"] = "Model requested completion."
                    if mode == "basic":
                        result["status"] = "Unverified"
                        log("warning", "Model finished; no verification gate",
                            "A patch and completion request are not test evidence.")
                    else:
                        checks = run_checks(workspace)
                        result["checks"] = checks
                        result["status"] = "Checks passed" if checks["passed"] else "Incomplete"
                        log("pass" if checks["passed"] else "fail",
                            "Harness verifies completion request", checks["output"])
                    break
                else:
                    raise ValueError("Unknown tool; only read_file, apply_patch, finish allowed")
                messages.append({"role": "user", "content": observation})
            else:
                log("blocked", "Tool-call budget exhausted", "Maximum 8 model turns.")
        except (ValueError, KeyError, TypeError, OSError, subprocess.TimeoutExpired) as error:
            log("fail", "Run incomplete", str(error))
            result["status"] = "Incomplete"
        result["after"] = (workspace / "cart.py").read_text(encoding="utf-8")

    result["diff"] = "".join(difflib.unified_diff(
        BUGGY.splitlines(True), result["after"].splitlines(True),
        fromfile="original/cart.py", tofile="patched/cart.py",
    ))
    return result


def show_bug():
    with tempfile.TemporaryDirectory(prefix="harness-demo-") as directory:
        workspace = Path(directory)
        (workspace / "cart.py").write_text(BUGGY, encoding="utf-8")
        (workspace / "test_cart.py").write_text(
            (ROOT / "test_cart.py").read_text(encoding="utf-8"), encoding="utf-8"
        )
        checks = run_checks(workspace)
    return {
        "status": "Bug reproduced", "before": BUGGY, "after": BUGGY, "diff": "",
        "checks": checks, "patch_attempts": 0,
        "events": [
            {"kind": "fail", "title": "INR 1000 order: expected 1000, actual 1050",
             "detail": "The > comparison excludes the exact threshold."},
            {"kind": "fail", "title": "Initial regression tests", "detail": checks["output"]},
        ],
    }
