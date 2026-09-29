# NeuraJL operator surface: what the model sees

This file describes what a model driving NeuraJL through NIRA-Prime's `neurajl` tool can rely on. The tool description (`NIRA-Prime-NeuraJL/packages/coding-agent/src/core/tools/neurajl.ts`) is the compact form. `kernelinfo()` is the executable form. Every line below is covered by `security/test_session_cli.py` or `test/runtests.jl`.

## The tool call

| Field | Meaning |
|---|---|
| `code` | Julia evaluated in the session's persistent kernel. The working directory is the task workspace. |
| `payload` | Optional text, bound as `PAYLOAD` for this call only. It is never parsed as Julia, so it carries the complete text of a file (Python, JSON, a Julia file with triple quotes) without escaping: `write("f.py", PAYLOAD)`. It is `nothing` in calls that send none. |
| `ephemeral` | Optional. Run in a disposable child process that sees no bindings and no workspace (about 10s to start). |

The result is everything printed during the call, then `=> ` and the rendered value of the last expression. NIRA-Prime shows the model at most 12,000 characters of it. When a result is longer, the middle is elided, and the elision notice names the call: `Neura.output(n)` returns everything that call printed, up to 256 KiB, for the last 64 calls.

## What persists

- Bindings, functions, types and loaded packages persist until the kernel stops. Julia 1.12 also allows a `struct` to be redefined.
- `ans` holds the last successful call's value.
- Files written to the workspace outlive the kernel.
- When the workspace is itself a package (its `Project.toml` has a `name` and `uuid`), the workspace comes first in `LOAD_PATH`, so `using` that package loads the workspace's code. The kernel's environment has packages of its own, such as OrderedCollections for DataFrames. Before this change, a model that appended the workspace to `LOAD_PATH` tested the kernel's copy of the package instead of its own.
- A package loaded from the workspace (its `pathof` lies under the workspace) is reloaded when any `.jl` file under its source directory changes. The reload happens before the next call runs, and before an `include` in the same call, so edited code and tests run in the kernel see the edits. The call's output then begins with `[reloaded Pkg from the workspace: files changed]`. If the edited source does not parse or load, the output says so and the package keeps its previous code. A reload re-evaluates the package's module body in place: methods deleted from the source stay defined, and `__init__` does not run again.
- The kernel keeps no value that nothing refers to. Only `ans` and your own bindings hold memory.

## Helpers bound in the session

| Name | What it does |
|---|---|
| `sh"cmd"` | Runs `cmd` with bash. `$` belongs to the shell; there is no Julia interpolation. It prints stdout, then stderr, and returns a `ShellResult`. A quote inside is written `\"`. A bare `"` ends the command early, and the error says so. |
| `bash("cmd")` | The same, but in an ordinary Julia string, so `$x` interpolates Julia values and a literal shell `$` must be written `\$`. `bash(PAYLOAD)` runs a script passed as the call's payload, with no quoting at all. |
| `ShellResult` | Fields `exitcode` (a process killed by a signal reports 128 + signal), `stdout` and `stderr`. `success(r)` is true for status 0. It displays as one line, because the output was already printed. |
| `run(`prog args`)`, `read(`...`, String)` | Standard Julia: one program, no shell, and they throw on a nonzero exit. |
| `include("file.jl")` | Loads a workspace file into the session; relative paths resolve against the workspace. Edited workspace packages are reloaded first. |
| `varinfo()` | Your bindings, with their size and a summary. |
| `Neura.output(n)` | Everything call `n` printed, in full, for the last 64 calls. The call number appears in each elision notice. |
| `kernelinfo()` | The kernel card: Julia version, workspace, what persists, the time limit, the network, loadable and loaded packages, and these helpers. |
| `Neura.request_capability(category, params)` | The only way to reach broker-mediated authority (see `CAPABILITY_MODEL.md`). The session's ceiling decides. |
| `@doc f` | Rendered documentation. |

## Time limit

Each call has a limit (60s in NIRA-Prime).

- **Waiting work** (`sleep`, `run`, `read` of a process or file, I/O, `wait`) is interrupted at the limit. The kernel and every binding survive. Processes started by the interrupted call are stopped, while processes started by earlier calls keep running. The result says `Interrupted: ...` and still includes the output printed before the interrupt.
- **Compute that never yields** cannot be interrupted in Julia 1.12. An external SIGINT segfaults the runtime in 3 of 3 attempts, and a watchdog thread's SIGINT is never delivered. The host kills the worker 12s after the limit. The next call starts a new kernel and says so first.
- **A call that catches the interrupt and keeps going** gets it again every second for 5 seconds. Then the kernel stops, and the result says why.

The workaround for long compute: put `yield()` (or any I/O) inside long loops, or split the work across calls.

## Errors

- Stack frames are listed most recent first. The model's own code is labelled `this call` or `an earlier call`, and long runs of library frames are collapsed to the frames that matter.
- Hints are appended for:
  - shell syntax inside backticks;
  - `$` in a Julia string;
  - reserved words used as names (`quote`, `end`, `function`, ...);
  - offline package installs.

## What is not there

- **Network:** none. `Pkg.add` fails and says so. The loadable packages are listed in the tool description and in `kernelinfo()`.
- **Threads:** one Julia thread. BLAS uses its own threads.
