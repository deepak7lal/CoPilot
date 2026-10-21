# Architecture and engineering decisions

## Agent loop

`Agent` depends on two small interfaces: a client exposing `chat(messages, tools)` and a tool executor exposing `execute(name, arguments)`. This makes the loop testable without a model or network connection. Production uses `OllamaClient`; tests use scripted responses while still executing real file tools and subprocess tests.

Each turn appends the assistant's tool calls, executes them sequentially, and appends JSON tool results with their `tool_name`. The next model request receives those results. Model calls stop at the step budget; tool calls have an independent cap. Identical calls are counted between applied writes, catching alternating repetitions as well as immediate duplicates. The fourth identical call stops the run. An applied write clears those counts because project state has changed.

The adapter uses the standard library's HTTP and JSON support rather than requiring an SDK. It requests deterministic temperature settings, although local inference is not guaranteed to be reproducible across hardware and model versions. It suppresses thinking output for the default Qwen model and returns tool calls and user-facing content to the loop.

For Qwen3, it also appends the model's documented [`/no_think` soft switch](https://github.com/QwenLM/Qwen3) to a copied system message. This supports older installed model templates that open a thinking block even when the HTTP request sets `think=false`. The original conversation history is unchanged. `--cpu` sets Ollama's `num_gpu=0` option for systems where GPU inference stalls. Each response is capped at 2,048 generated tokens.

## Verification state

Every run begins unverified. An applied file write invalidates earlier evidence. `run_python` and `run_file` also invalidate it because Python can mutate files. A successful `run_tests` sets the verification flag, provided unittest discovered at least one test. A later failed execution clears it. A model's final response cannot change the flag.

When the model finishes, the status is `completed` if current test evidence exists, otherwise `unverified`. Dry runs end as `preview`. Provider failures, malformed responses, exhausted budgets, and repeated calls get distinct statuses and a report. A passing test suite is evidence of what was executed, not proof of task correctness. The separate evaluator tests final requirements independently.

If the model ends with prose while the run is still unverified, the loop gives it one corrective prompt to inspect files, apply edits through tools, and run tests. This retry consumes the existing step budget and is counted in the report. If it stops again without evidence, the status remains `unverified`. This addresses a failure observed with the installed Llama model, which printed proposed code and JSON rather than applying its repair; it does not reinterpret printed JSON as executable instructions.

When the model stops after tracked edits without current verification, the runner first executes workspace test discovery itself if execution is enabled and tool-call budget remains. This final check is recorded with `origin: final_verification` and consumes a tool call. A model selecting `run_file` or supplying an invalid test-directory argument cannot substitute for a passing test suite. The automatic check is skipped for previews and when no tracked write occurred. Failed checks remain visible and can feed the single corrective turn.

## Execution boundary

File tools resolve paths against an explicit workspace and reject absolute paths, traversal, symlink escapes, Windows alternate data streams, and common metadata/secret paths. Reads and writes are limited to 128,000 bytes. Directory listing skips common generated directories and stops at 500 files. These checks reduce accidental access; they are not a complete secret scanner and do not prevent filesystem race conditions.

Python execution is disabled by default. When enabled, it uses a subprocess with an explicit workspace working directory and closed stdin. `run_file` executes a script normally, so `__name__ == '__main__'` and local imports work. stdout and stderr are captured independently, with at most 12,000 bytes of each returned to the model. Temporary output files avoid buffering unlimited output in application memory; they do not impose a disk quota.

Each subprocess has a timeout and the direct process is killed when it expires. Descendant processes are not reliably terminated as a tree. There is no OS sandbox: Python can access the network, other files, or spawn children with the user's permissions. Use disposable workspaces and trusted tasks; container/OS isolation is a future improvement, not an implemented guarantee.

## Reports and observability

Every completed loop returns a report with a UTC start time, monotonic elapsed time, model name, workspace, step and call counts, tracked changed files, and tool events. Writes include unified diffs and whether they were applied. Execution events include exit codes, timeout state, stdout, stderr, and truncation state. The CLI saves a uniquely named JSON report. Reports can expose source code or credentials printed by a program; keep `.codepilot/` out of Git and review exports manually.

## Testing strategy

- Unit and integration tests cover path rules, execution opt-in, actual process failures and timeouts, output limits, dry-run preservation, empty test suites, malformed calls, error recovery, budgets, verification invalidation, reports, CLI exit codes, and the HTTP payload contract.
- One end-to-end orchestration test inspects a real file, observes a failing test, applies a patch, and observes the passing test using a scripted model.
- The real-model evaluator uses three fresh projects and independent assertions, checks every baseline fails, and checks the visible tests were preserved.
- The CI workflow is configured for Python 3.10/3.12 on Linux and Windows. Local evidence is recorded separately from remote CI status.

## Tradeoffs and next steps

The deliberately small implementation makes the entire tool loop reviewable. Subprocess isolation improves failure handling over in-process `exec`, while leaving a clear security boundary. Full-file writes keep the model interface simple, but can overwrite unrelated changes; diffs are shown and recorded, and dry-run offers a preview. Larger repositories would benefit from targeted patch tools, search, context budgets, rollback, container isolation, and a broader evaluation set. Those are future scope.
