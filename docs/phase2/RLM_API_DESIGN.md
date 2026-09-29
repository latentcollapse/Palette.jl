# RLM API in Julia: design (phase 2, item 1)

## What it replaces

The Python RLM shim, `prime-agent-runtime/src/rlm/` in NP2 (6.1k lines), gives code running in the IPython kernel seven calls:

| Call | Wire type | Returns |
|---|---|---|
| `rlm.spawn(prompt; name, model, thinking)` | `rlm.run` | a handle: child id, name, session dir, model |
| `rlm.create_session(prompt; …)` | `rlm.create_session` | a session handle |
| `rlm.find_models(query, limit)` | `rlm.find_models` | models (provider, id, name, selector) |
| `rlm.list_subagents()` | `rlm.list_subagents` | children and their activity |
| `rlm.collect(targets; timeout_ms)` | `rlm.collect` | each child's result |
| `rlm.progress_note(message)` | `rlm.progress_note` | an acknowledgement |
| `rlm.delete_subagent(target)` | `rlm.delete_subagent` | the deleted child |

All seven go through one primitive, `host_request(type, payload)`. The kernel sends `{"event": "host_request", "id", "data"}` to the TypeScript host **in the middle of a call** and waits for `{"status": "ok" | "error", …}`. The TypeScript host dispatches on `type`. Those handlers already exist, and the IPython tool uses them.

Today a NeuraJL model reaches RLM only through the separate TypeScript `rlm` tool. With this API, Julia code can do what IPython code can: spawn children in a loop, collect their results into Julia values, and work on them without a round trip through the model.

## Route

```
Julia code (Neura.rlm.spawn)
  → broker socket, which already exists: NEURAJL_BROKER_SOCKET, one JSON request per connection
  → broker (host side, outside the sandbox): checks the session's capability ceiling
  → session_cli writes {"event": "host_request", …} to stdout mid-call      [new]
  → NP2 neurajl.ts dispatches it to the existing TypeScript host handlers   [new]
  → the reply goes to session_cli's stdin                                    [new]
  → broker → Julia
```

**Why the broker, and not a new channel.** The broker is already the one way out of the sandbox, and it already enforces the rule that the worker cannot give itself authority. An RLM spawn is an effect with a cost: a new model session. So it belongs behind the same check, as a new capability category, `host_request`, with its own allowlist of wire types. A session without it cannot spawn children.

## The work

1. **Protocol.** session_cli sends mid-call `host_request` events and accepts matching replies while a call runs. Tests: an event goes out mid-call, the reply is routed to the right waiter, a late reply is dropped, a host disconnect fails every waiter (as `_fail_pending_host_requests` does in Python), and a call never deadlocks on a reply that never comes.
2. **Broker category `host_request`.** It is off by default, allows only listed wire types, and writes a receipt for every request. Tests: allowed, denied by ceiling, unknown type, and a receipt written in each case.
3. **The Julia API.** `Neura.rlm` has the seven calls with typed handles. Errors carry the host's message and are thrown as Julia exceptions. `spawn` and `collect` yield, so `@async` works. Tests are unit tests against a fake host, plus the precompile workload.
4. **The NP2 side.** `neurajl.ts` listens for mid-call events and dispatches them to the same handlers the IPython tool uses, with the same wire types, so there is no second implementation. The tool description gets one line naming `Neura.rlm.spawn`/`collect`, as the only way the model learns about it.
5. **Live test.** A real session spawns two children from Julia, collects both, and works on their results in the same call.
6. **Adoption.** Whether Luna uses it at all gets measured, not assumed.

## Parity target

Same wire types, same payload validation and the same error messages as the Python shim, so both kernels behave identically against one host. Where Python checks a payload's structure (`_spawn_handle_from_payload` and the others), Julia does the same and fails the same way.

## Open questions

- **Does collect keep a NeuraJL call open past the 60 s call limit?** Children run for minutes. The likely answer is to launch them with `spawn`, return, and `collect` in a later call. `@async` also works, since background jobs already cross calls.
- **Revival.** Handles are plain data (ids and paths) and survive a snapshot. An RLM child outlives a kernel death, because it is hosted by TypeScript, so after revival `list_subagents` finds it again.
