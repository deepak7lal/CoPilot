# Validation and measured results

Recorded on 16 October 2026 on the local Windows machine. These results distinguish software tests from real model behavior.

## Automated software validation

| Check | Observed result |
| --- | --- |
| Python 3.12.14: `python -m unittest discover -s tests -v` | 43 tests: 42 passed, 1 skipped |
| Python 3.11.5: `py -3 -m unittest discover -s tests -v` | 43 tests: 42 passed, 1 skipped |
| Deterministic replay: `python -m evals.replay` | Completed: initial regression failure, applied fix, passing retest, independent assertions passed |
| CLI help | Passed with both Python environments |
| Wheel build and installation into a temporary local target | Passed without application dependencies |
| Remote GitHub Actions | Configured; not run on GitHub during this session |

The skipped test creates a directory symlink. This Windows environment does not permit creating it. Symlink escape protection is implemented, but its real-symlink test was not exercised locally. The CI matrix includes Linux, where this test can run.

The tests cover actual subprocess failures, execution timeouts, output limits, path validation, dry-run preservation, a real failing-test/fix/retest cycle, verification invalidation, tool errors, repeated-call limits, budgets, reports, the HTTP request contract, and CLI exit codes. The model double in those tests is scripted; these passes are not evidence of model coding accuracy.

## Initial Qwen real-model smoke evaluation

Command: `python -m evals.run` using `qwen3:4b`, Ollama 0.40.2, default inference placement, and a 120-second socket timeout per model request.

| Task | Buggy baseline fails independent checks | Final independent checks pass | Original tests preserved | Agent tool calls |
| --- | --- | --- | --- | --- |
| Sum accumulation | Yes | No | Yes | 0 |
| Slug normalization | Yes | No | Yes | 0 |
| Percentage discount and validation | Yes | No | Yes | 0 |

**Observed task result: 0/3.** Each run ended with a model-request timeout before the first tool call. This is a failure of the configured live path, not a successful repair benchmark. The raw summary is retained in [the initial smoke results](results/initial-qwen-smoke.json).

A follow-up CPU-only Qwen run with a 180-second request timeout also timed out before tool use. A short CPU probe did produce output, showing the server was reachable and capable of generation. Inspection of the installed Qwen template showed it opened a thinking block unconditionally. The adapter now also requests Qwen's `/no_think` soft switch; a further CPU sum retry with a 90-second timeout still did not return a tool call in time. These observations do not establish a specific GPU fault or prove the soft switch is effective for this installed model.

The request timeout is a socket timeout rather than a strict total task deadline; elapsed time can exceed it. A run can also contain multiple requests. Keep the measured durations in the JSON traces when comparing performance.

## Llama comparison and recovery behavior

Command: `py -3 -m evals.run --case sum --cpu --model llama3.2:latest --model-timeout 90`.

| Implementation state | Independent task result | Agent status | Observation |
| --- | --- | --- | --- |
| Initial loop | Failed | unverified | One invalid Python tool call; then printed a proposed repair rather than applying it |
| With bounded completion recovery | Passed 1/1 | unverified | Model read and edited the source; independent assertions passed and original tests were preserved; model failed to run the correct test command |
| With runner-owned final verification | Failed 0/1 | error | Request timed out before tool use on this retry; this run did not exercise the new final-verification path |
| Runner-owned final verification, 240-second request timeout, no concurrent validation | Passed 1/1 | completed | Runner test discovery passed, independent assertions passed, original tests preserved |

The independently successful repair took 146.172 seconds and six tool calls. Its [recorded summary](results/llama-recovery-sum.json) preserves the `unverified` status. This is one successful behavior check on one small task; it is not a verified agent completion or a general accuracy score. The [later timeout summary](results/llama-final-retry.json) is retained alongside it.

The final verified live run used `py -3 -m evals.run --case sum --cpu --model llama3.2:latest --model-timeout 240` with no concurrent validation. It took **190.625 seconds**. The model again used invalid intermediate execution/test calls; after it applied a correct repair, the runner executed test discovery itself and obtained a passing nonempty suite. Independent assertions passed and the original test file was unchanged. See the [summary](results/verified-llama-sum.json) and [full sanitized trace](results/verified-llama-trace.json). This is one recorded verified completion, not evidence of a generally reliable coding model.

The final runner-owned test-discovery path is also covered by automated tests using real subprocesses, including a model that forgets tests and a run with no remaining tool budget. Concurrent local validation produced a timed-out scripted test process once; its automatic final retest passed. Keep the project labeled experimental and record timing conditions when comparing results.

## Interpreting the evidence

The agent's file tools, orchestration, execution controls, reporting, and evaluation harness have automated evidence. A CPU Llama run completed an end-to-end verified repair with independent checks. Qwen inference and repeatability across tasks remain unresolved on this machine. Use the recorded configuration and trace for the live demonstration, and the separately labeled deterministic replay to explain orchestration without model inference.

Even a future 3/3 result would only cover three small fixtures. A broader claim would require a larger, held-out dataset, repeated trials, recorded model digests and inference settings, resource measurements, and explicit task-level success criteria.

A defensible numeric resume bullet is: "Validated a local coding-agent tool loop with 42 passing automated tests covering execution failures, timeouts, path controls, verification state, and CLI behavior; configured a Windows/Linux CI matrix." Avoid presenting the current live evaluation as a general success rate.
