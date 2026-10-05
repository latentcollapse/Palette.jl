# Palette chatbot bundle verification

Artifact source: `b61b08f9adf2492339e59ce146dcfd2dba249858`. PR: https://github.com/latentcollapse/Palette.jl/pull/19.

Created Palette-ChatGPT.zip, Palette-Claude.zip, and Palette-Claude.mcpb with SHA256SUMS.txt in Downloads/Palette-Chatbot-Bundles. Two independent builds have identical hashes. Each ZIP passes integrity checks; source comes only from the committed Git tree, with no ignored archive, build cache, personal state, or credentials.

Official Agent Plugins JSON schemas and the official MCPB 2.1.2 manifest validator pass. The packaged MCPB was extracted before validation (the validator accepts a directory/manifest, not an archive filename).

The ChatGPT ZIP was extracted and its actual default setup command instantiated Julia, built the locked Rust host, prewarmed the real sandbox, and generated client configuration successfully, using installed toolchains and an existing provisioned depot. This is not a clean-machine or empty-depot installation claim. The packaged Claude bridge connected to that prepared extracted SDK, initialized MCP, discovered all four tools, created a routed workspace, evaluated Julia, returned 42 from a binding created in the previous call, and closed the world. The final executable payloads exactly match those tested; a final follow-up changed only briefing links.

Negative checks reject malformed args and missing executables with nonzero status, and preserve literal shell metacharacters without interpretation. Eight Rust unit tests pass after the Cargo license metadata change. Python syntax, Node syntax, diff whitespace, and public-base test policy pass.

Generated Windows/WSL2 config shape is checked, but native Windows execution and installation through Claude Desktop UI were not tested. ChatGPT account registration was not performed for third parties. Cloud Chat needs each user's own supported tunnel/remote endpoint. Native macOS/Windows supervised runtimes are not provided.

Core's outgoing license is AGPL-3.0-only, with explicit Apache-2.0 client/plugin/documentation exceptions. Original MIT licenses and copyright notices are retained; earlier grants remain in force. SECURITY.md and contribution scope are included. No community repository, donation endpoint, visibility change, or public-release tag was created.

Retained failed attempts: the first launcher probe exposed a missing workspace directory, fixed in setup.py; a connect-only check initially looked for new license assets in an old runtime checkout, corrected to use the package's own license assets; system and lab Python lacked jsonschema, so validation used an isolated pinned validation environment; passing the MCPB archive directly to `mcpb validate` failed because that command reads a manifest/directory, followed by successful validation of the extracted archive. No assertion or execution deadline was weakened.

PR CI is running; the source/licensing change has not yet been merged into GitHub main. The local artifacts include the full licensing change now.
