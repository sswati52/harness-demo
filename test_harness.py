import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch
import urllib.error
import urllib.request

from app import Handler, ThreadingHTTPServer
from harness import BUGGY, FIXED, ROOT, OllamaModel, run_checks, run_demo, show_bug


class HarnessTests(unittest.TestCase):
    def test_initial_bug_has_failing_boundary_checks(self):
        result = show_bug()
        self.assertFalse(result["checks"]["passed"])
        self.assertIn("test_boundary_free_shipping", result["checks"]["output"])

    def test_basic_patch_is_correct_but_unverified(self):
        result = run_demo("basic")
        self.assertEqual(result["status"], "Unverified")
        self.assertEqual(result["after"], FIXED)
        self.assertIsNone(result["checks"])

    def test_engineered_mode_really_checks_patch(self):
        result = run_demo()
        self.assertEqual(result["status"], "Checks passed")
        self.assertTrue(result["checks"]["passed"])
        self.assertIn("Ran 6 tests", result["checks"]["output"])

    def test_injected_regression_is_detected_and_repaired(self):
        result = run_demo(scenario="repair")
        self.assertEqual(result["status"], "Checks passed")
        self.assertEqual(result["patch_attempts"], 2)
        failures = [e for e in result["events"] if e["kind"] == "feedback"]
        self.assertIn("test_empty_cart", failures[0]["detail"])

    def test_protected_file_is_blocked(self):
        result = run_demo(scenario="blocked")
        self.assertEqual(result["status"], "Blocked")
        self.assertEqual(result["after"], BUGGY)

    def test_repeated_fault_stops_at_budget(self):
        result = run_demo(scenario="budget")
        self.assertEqual(result["status"], "Incomplete")
        self.assertEqual(result["patch_attempts"], 3)
        self.assertFalse(result["checks"]["passed"])
        self.assertIn("Patch budget exhausted", result["events"][-1]["title"])

    def test_runs_do_not_modify_project_source(self):
        original = (ROOT / "cart.py").read_bytes()
        run_demo()
        self.assertEqual((ROOT / "cart.py").read_bytes(), original)

    def test_arbitrary_source_is_never_executed(self):
        with tempfile.TemporaryDirectory(prefix="harness-demo-test-") as directory:
            workspace = Path(directory)
            (workspace / "cart.py").write_text("raise RuntimeError('unsafe')", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "Execution blocked"):
                run_checks(workspace)

    def test_arbitrary_model_patch_is_rejected(self):
        with patch("harness.ReplayModel.next_action", return_value={
            "tool": "apply_patch", "path": "cart.py",
            "old": "return subtotal + shipping", "new": "raise RuntimeError('unsafe')",
        }):
            result = run_demo()
        self.assertEqual(result["status"], "Incomplete")
        self.assertEqual(result["after"], BUGGY)
        self.assertIsNone(result["checks"])

    def test_model_cannot_claim_success_without_passing_tests(self):
        with patch("harness.ReplayModel.next_action", return_value={"tool": "finish"}):
            result = run_demo()
        self.assertEqual(result["status"], "Incomplete")
        self.assertFalse(result["checks"]["passed"])

    def test_invalid_provider_and_controlled_live_scenario_rejected(self):
        with self.assertRaises(ValueError):
            run_demo(provider="unknown")
        with self.assertRaises(ValueError):
            run_demo(provider="ollama", scenario="repair")

    def test_ollama_json_contract(self):
        class Response:
            def __enter__(self):
                return self

            def __exit__(self, *args):
                pass

            def read(self, size):
                return json.dumps({"message": {"content": '{"tool":"finish"}'}}).encode()

        with patch.dict("os.environ", {"OLLAMA_MODEL": "demo-local"}):
            with patch("urllib.request.OpenerDirector.open", return_value=Response()) as request:
                self.assertEqual(OllamaModel().next_action([]), {"tool": "finish"})
                self.assertEqual(request.call_args.args[0].full_url,
                                 "http://127.0.0.1:11434/api/chat")


class ServerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.url = f"http://127.0.0.1:{cls.server.server_port}"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join()

    def test_ui_and_real_run_endpoint(self):
        with urllib.request.urlopen(self.url) as response:
            self.assertIn(b"Agent says done", response.read())
        request = urllib.request.Request(
            self.url + "/api/run", data=b'{"mode":"engineered"}',
            headers={"Content-Type": "application/json", "Origin": self.url},
        )
        with urllib.request.urlopen(request) as response:
            result = json.load(response)
        self.assertEqual(result["status"], "Checks passed")
        self.assertTrue(result["checks"]["passed"])

    def test_cross_origin_post_is_rejected(self):
        request = urllib.request.Request(
            self.url + "/api/run", data=b"{}",
            headers={"Content-Type": "application/json", "Origin": "https://example.com"},
        )
        with self.assertRaises(urllib.error.HTTPError) as error:
            urllib.request.urlopen(request)
        self.assertEqual(error.exception.code, 403)


if __name__ == "__main__":
    unittest.main(verbosity=2)
