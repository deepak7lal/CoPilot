# Demo and interview guide

## A three-minute demo

1. Introduce the problem: a model that only prints code cannot verify that its edits work. CodePilot connects local model tool calls to project inspection, edits, and actual execution.
2. Show `examples/repair/calculator.py` and its four tests. Point out the addition bug and the division behavior that must be preserved.
3. Copy the example into a fresh directory using the README command. Run the task with `--allow-exec` and show the tool output and diff. Do not edit the example fixture itself.
4. Open the generated JSON report. Show the write diff, test subprocess exit code, and status. Explain that an unverified model claim cannot produce a `completed` status.
5. Show `python -m unittest discover -s tests -v` and the real-model evaluation summary. Explain exactly which evidence uses a scripted model and which uses real Qwen inference.

If the live model fails or times out, show the recorded result, explain the failure, and use a previous trace to demonstrate the intended path. A recorded demonstration is useful; passing it off as a live run is not.

`python -m evals.replay` runs a clearly labeled scripted demonstration without Ollama. It uses real file tools and test processes, including the initial failure and successful retest. This is a reliable way to explain the architecture while keeping claims about model inference separate.

The recorded real-model success on this machine uses `py -3 -m evals.run --case sum --cpu --model llama3.2:latest --model-timeout 240`. Allow roughly three minutes, and avoid concurrent validation while recording it. It demonstrates an actual model repair, a runner-owned passing test check, preserved original tests, and independent final assertions. The successful trace is linked from `docs/evaluation.md`; earlier failed attempts are retained there as well. One completed fixture does not establish general coding accuracy.

## Questions to prepare for

**Why an agent instead of a chatbot?** The model selects tools across turns, receives actual execution feedback, and can revise its edits. Explain one complete read, edit, test, repair cycle from a report.

**How did you prevent infinite loops?** Independent step and tool-call caps, repeated-call detection between writes, and a per-execution timeout. Explain the remaining absence of a global deadline and process-tree isolation.

**How did you measure success?** Separate orchestration tests from model behavior. The evaluator checks known-bug baselines, independent final assertions, and original test preservation. Three small cases are useful smoke tests, not a general coding benchmark.

**Is it secure?** File tools restrict paths; Python execution is opt-in and runs separately from the agent process. Generated Python still has user permissions. Container or OS sandboxing is needed for untrusted code.

**What would you improve next?** Use results to choose: stronger isolation, patch/rollback support, repository search and context management, and a larger held-out task set. Discuss tradeoffs rather than claiming these already exist.

## Resume wording

**CodePilot — Local AI Coding Agent | Python, Ollama, Qwen, unittest, GitHub Actions**

- Built a local tool-calling coding agent that inspects Python projects, applies edits, executes tests, and saves diffs and structured run reports.
- Implemented workspace file checks, opt-in subprocess execution, timeouts, loop budgets, dry-run previews, and verification-aware run statuses.
- Added automated orchestration and execution tests, a Windows/Linux CI workflow, and a reproducible task evaluator with independent assertions and test-preservation checks.

Use the measured results in `docs/evaluation.md` if you want a numeric bullet. State the task set size and model. Avoid claims such as production-ready, secure sandbox, arbitrary-repository repair, or an accuracy percentage without a representative benchmark.

Before publishing, review the source and run traces, understand the tests, record a short demo, and add your actual repository URL. Do not claim deployed CI passed until it has run on the hosting service.
