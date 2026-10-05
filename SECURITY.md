# Security reporting

Report a suspected vulnerability through this repository's **Security → Report
a vulnerability** form when private vulnerability reporting is enabled. If it
is unavailable, request a private reporting channel in a GitHub issue without
including exploit details, credentials, personal files, or deployment state.
There is no published response-time commitment or bug-bounty program.

Include the source revision, Julia/Python/Rust versions, operating system, client
transport, minimal reproduction, expected authority boundary, actual behavior,
and relevant redacted receipts. Keep ordinary correctness bugs in Issues.

Use the supervised Linux host for OS-isolated execution; the plain Julia API
is not a sandbox. Keep snapshot state and transport credentials outside worker
workspaces. Grant host write capabilities explicitly. Caller-chosen workspace
routing keys are not authenticated identities. See
[runtime authority](runtime/docs/authority.md) and
[workspace contracts](runtime/docs/workspaces.md).
