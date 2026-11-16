# Agent Says Done. But Is It Really Done?

A small VS Code-ready demo of harness engineering. Python 3.10+,
standard library only. No pip install, API key or internet is needed for replay.

## Run in VS Code (Windows)

1. Open this folder in VS Code: `C:\Users\swatisingh\Downloads\harness-demo`.
2. Choose **Terminal > New Terminal**.
3. Run:

   ```powershell
   python app.py
   ```

4. Open `http://127.0.0.1:8765` in your browser.
5. Leave the terminal running. Stop with **Ctrl+C**.

If `python` is not recognized, try `py app.py`. If port 8765 is busy:

```powershell
python app.py --port 8766
```

Then open `http://127.0.0.1:8766`.
Do not open `index.html` directly or use Live Server: the Python backend runs
the actual tools and tests. Use the exact `127.0.0.1` address above.

On this machine, the existing demo's Python runtime can also start this project:

```powershell
Set-Location 'C:\Users\swatisingh\Downloads\harness-demo'
& 'C:\Users\swatisingh\harness-engineering-demo\demo-code\.python\python.exe' -B -c "import sys; sys.path.insert(0, '.'); import app; app.main()"
```

This fallback requires the original demo's `.python` folder to remain in place.
The explicit import path selects this downloaded project's code.

Optional F5 debugging requires Microsoft's Python and Python Debugger VS Code
extensions. Select your Python interpreter, then **Run Harness Demo**.
The terminal command does not require those extensions.

## What is real, and what is replay?

Default **Replay** uses explicitly scripted model actions. It is NOT a live AI
agent or a reliability benchmark. The file reads, edits, test subprocesses,
failure feedback, edit restrictions and completion gate are real Python code.
This makes the first presentation repeatable without an LLM setup.

**Live local Ollama** uses a real locally installed LLM. It is optional, requires
separate model setup, and can fail or produce an invalid action. No remote model
API is configured. Live inference quality depends on the installed model.

## Core demo flow (15-minute hands-on)

Keep **Replay** selected for your first practice.

| Time | Click / show | What to say (Hinglish) |
|---|---|---|
| 0-3 min | **1. Show original bug** | "Rule hai INR 1000 par free shipping. Actual total 1050 hai. Tests bhi yeh bug pakad rahe hain." |
| 3-6 min | **2. Minimal harness** | "Model action se patch apply hua. Status Unverified hai: is run mein tests nahi chale. Patch correct ho sakta hai, lekin evidence nahi mila." |
| 6-11 min | **3. Engineered harness** | "Same starting code, task aur model provider. Harness context deta hai, tool request execute karta hai, phir independently tests chalata hai." |
| 11-13 min | Scroll to trace | "Model proposes action. Harness tool chalata hai. Test output actual subprocess se aata hai. Completion system ke checks par depend karti hai." |
| 13-15 min | Diff and test evidence | "In 6 cases ke checks pass hue. Iska matlab universal correctness nahi. Agent ki completion request aur verified outcome alag hain." |

The minimal patch is intentionally correct too. Do not claim that a minimal
harness necessarily produces bad code. The comparison is **unverified vs checked**.
Both setups retain the same safe edit restrictions; the engineered setup adds
tests, failure feedback and a test-based completion gate.

### Optional controlled scenarios

Expand **Extra: controlled harness failure scenarios**:

- **Inject faulty patch + repair**: a labelled fixture removes the empty-cart
  guard. Real tests fail; that failure goes back to the replay model; the next
  action restores the guard and tests pass.
- **Try editing protected tests**: a prepared request is rejected before writing.
- **Exhaust 3-attempt budget**: the fixture repeatedly breaks the empty-cart
  rule. The harness stops after three patches and reports **Incomplete**.

These injections test harness behavior. They are not natural model mistakes.
Every run starts from a fresh temporary copy. **Clear screen** only clears the
display; the project source always remains buggy for the next presentation.

## Optional: real local LLM

Install Ollama separately from its official distribution and download a suitable
instruction-following model. Downloading a model needs internet and disk space.
Do not download anything during the live presentation.

1. Start your local Ollama service.
2. In the VS Code terminal, inspect your installed models:

   ```powershell
   ollama list
   ```

3. Stop the demo server if it is running, then set the exact model name from that
   list in the **same terminal**:

   ```powershell
   $env:OLLAMA_MODEL = "your-installed-model-name"
   python app.py
   ```

4. On the page, select **Live local Ollama**.
5. Run **Minimal harness** or **Engineered harness**.

The adapter calls `http://127.0.0.1:11434/api/chat` with JSON output requested.
It sends the demo task, tool contract and observations. A model response is only
a proposal; the harness validates it and executes the tool.

No installed local model was required to validate replay. A mocked protocol test
covers the adapter; it does not establish live model success. An unavailable
Ollama service, invalid response, rejected edit or exhausted turn budget yields
**Incomplete**, not "verified". Controlled scenarios are replay-only.

## Code walkthrough

| File | Responsibility |
|---|---|
| `cart.py` | Original buggy shopping-cart code (`>` instead of `>=`). |
| `test_cart.py` | Six protected regression cases; boundary, below/above threshold, empty, negative and multiple items. |
| `harness.py` | Context, model adapters, read/edit tool dispatch, permissions, tests, feedback, budgets and completion. |
| `app.py` | Local Python HTTP server; binds only to 127.0.0.1. |
| `index.html` | UI displaying source, diff, actual test evidence and completed trace. |
| `test_harness.py` | Harness behavior and local HTTP integration tests. |

The trace is shown after the run completes. It is not animated or streamed
model reasoning. It records observable actions and tool results only.

## Validate the harness

```powershell
python -B -m unittest test_harness -v
```

To reproduce the original cart bug independently:

```powershell
python -B -m unittest test_cart -v
```

That second command **intentionally fails two boundary tests**. Do not run bare
test discovery as a "green" project test; the original app stays buggy by design.

## Safety and scope

This is a narrow educational harness, not a production sandbox. It only accepts
`cart.py`, exact-match replacements and three known source templates. Arbitrary
model-generated Python is never executed. Test subprocesses have a 10-second
timeout. Model requests have a 60-second network timeout and a bounded response.
Each run permits at most 8 model turns and 3 patches. Temporary run copies are
cleaned automatically. No tools for shell execution or remote model calls are
offered to the model.

Do not remove the template allowlist without first designing real isolation.
Use it only locally; do not expose the HTTP server on a network.
