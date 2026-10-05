# Install Palette in your chatbot

These bundles contain the clean Palette SDK source and client integration. They
do not contain preinstalled Julia, Rust, Python, extra kernels, credentials, or
a hosted service. Initial preparation takes several minutes; do it once before
connecting. This is a source-based installation, not a thirty-second binary installer.

## 1. Prepare your runtime

Use Linux with Julia 1.12, Python 3, Rust/Cargo, and bubblewrap installed.
On Windows, use a WSL2 Linux distribution with those prerequisites; execute this
step in that distribution. Native macOS and native Windows supervised runtimes
are not currently supported. Cloud-only clients can connect to a Linux host.

Extract the ZIP to a permanent location. From the extracted directory run:

```sh
python3 setup.py \
  --output-dir "$HOME/.local/share/palette-client" \
  --data-dir "$HOME/.local/share/palette-data" \
  --depot-dir "$HOME/.local/share/palette-depot"
```

For Windows Claude Desktop add `--wsl-distribution YOUR_DISTRO_NAME` (the name
shown by `wsl.exe --list --quiet`). Keep output, data and depot outside `sdk/`.
The helper instantiates the Julia project, builds the locked Rust host, prewarms
the real sandbox, and generates `palette-launch.json`, `generic-mcp.json`, a
local portable plugin, and a `palette-mcp` stdio command. It never requests model
API calls or automatically configures a tunnel. Linux must permit bubblewrap's
user namespaces; an AppArmor denial is an administrator setup issue, not a
reason to disable isolation. See `sdk/runtime/docs/install.md`.

For an existing, already built and prewarmed installation, use
`--repo-dir /absolute/path/to/Palette --connect-only` with its existing depot.
This option checks required files but intentionally does not rebuild or prewarm.

## 2a. Claude Desktop

Extract `Palette-Claude.zip`, prepare the runtime above, then install the
included **Palette-Claude.mcpb** through Claude Desktop's extension installation
UI. This is a ZIP-format MCP bundle with the extension-specific suffix.
When asked for **Palette launch configuration**, select the generated
`palette-launch.json`. On Windows it must be accessible to the Windows app
(for example through `\\wsl.localhost\YOUR_DISTRO\home\YOUR_USER\...`).
Its command targets the explicitly selected WSL distribution.

The extension uses Claude's Node runtime and forwards MCP stdio to the prepared
Linux service. It does not run Julia inside Node or make the SDK cross-platform.
For another local MCP client, merge the Palette entry from `generic-mcp.json`
into that client's configuration. Do not replace unrelated server entries.

Cloud Claude conversations require a separately reachable supported MCP
connector; this local Desktop extension does not deploy an HTTPS endpoint.

Official extension format: https://github.com/modelcontextprotocol/mcpb

## 2b. ChatGPT Chat

Extract `Palette-ChatGPT.zip` and prepare the runtime above. ChatGPT's cloud Chat
mode cannot execute a local `palette-mcp` command merely because you upload a ZIP.

1. Connect the generated `palette-mcp` executable to **your own** Secure MCP Tunnel
   using OpenAI's tunnel client instructions. Keep the client running on the
   prepared Linux machine. Use the exact absolute path printed by setup.py.
   Alternatively deploy a supported authenticated HTTPS MCP endpoint.
2. In ChatGPT, enable developer mode when available under your account policy.
3. Open Plugins, add a connection named Palette, choose Tunnel, and select your
   tunnel ID; or enter your hosted MCP URL. Review the discovered tools.
4. Start a new Chat conversation and select that connection.

No tunnel ID or API credential is included. Tunnel registration/authentication
is separate from your ChatGPT subscription and from Palette runtime setup.
Follow the current official instructions rather than guessing account permissions:

- https://developers.openai.com/api/docs/guides/secure-mcp-tunnels
- https://developers.openai.com/plugins/deploy/connect-chatgpt

The ZIP also has a root `plugin.json` and `mcp.json` for Agent Plugins-compatible
local clients. That template expects `palette-mcp` on PATH. Prefer importing the
**generated** `palette-local-plugin` directory, whose configuration has absolute
paths. Directory submission for public ChatGPT distribution requires the remote
endpoint/registration/review workflow; this archive is not an approved directory
listing and contains no fabricated app ID. Do not create duplicate registrations
when only the installed runtime changes.

## 3. Verify persistence and isolation

Ask the model to create a new thread-scoped workspace and use its returned
workspace ID explicitly. Evaluate `probe = 41`, then evaluate `probe + 1` in a
second call: expect 42. Start a separate workspace and check that `probe` is not
defined there. Caller-chosen context keys are routing hints, not authentication.

Provide `BRAIN_BLAST.md` as optional model context, or withhold it for unprimed
exploration. Use public supported API contracts; extra lab toolchains are absent.
Host write roots stay closed until the administrator configures them and the
broker receives exact-operation approval. A client without confirmation support
cannot grant that approval simply by evaluating Julia.

## Updates and license

Keep the SDK at a stable path and retain the external data/depot directories.
Stop the adapter, replace the SDK with the new source bundle, rebuild/prewarm,
restart, and refresh client tool discovery if schemas changed. Do not copy an
old Manifest blindly into a new source release. Keep a prior source bundle for
rollback; do not overwrite live runtime files during an active call.

Core is AGPL-3.0-only; these client packages/installers and identified public
docs are Apache-2.0. Inherited MIT grants/notices remain intact. The included
`sdk/runtime/licenses/README.md` gives the exact source boundaries. SHA256SUMS.txt
accompanies the artifacts; SOURCE.json records the precise source revision.
