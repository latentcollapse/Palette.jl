# Authority boundaries

Palette workers run ordinary Julia with reflection, subprocesses, and native
calls. The Linux supervisor places them in bubblewrap namespaces with a bounded
filesystem view. Julia source checks are convenience checks, not an isolation
boundary. The plain in-process package API does not establish this OS boundary.

Workspace effects happen within configured mounts. Effects outside that envelope
must be requested from the host broker, whose capability ceiling is configured
before the session starts. A worker cannot grant itself a capability. Child
ceilings must be subsets of the caller's ceiling. Requests outside the ceiling
are denied, and broker receipts record decisions and outcomes.

A network capability grants broker-mediated access, not unrestricted raw worker
networking. Read-only runtime mounts remain read-only even when Julia can run
arbitrary code. Credentials belong to host services rather than worker bindings.

Writable workspace and saved-state mounts must be disjoint from protected
runtime, project, toolchain, shared depot, OS and broker-socket paths. Canonical
path checks reject parent, child, equal and symlink overlaps before launch.
The routed workspace must also exclude the host registry, grants, ownership
metadata and scratch area. Keep generated client configuration outside it.

The routed MCP adapter can apply exact reviewed patches to trusted configured
source roots. Approval binds a digest and world to one expiring attempt. It
requires client confirmation or separately authorized administrator approval;
model-supplied arguments cannot mint a grant. See [patch contracts](workspaces.md).

Routing context keys prevent accidental conversation collisions. They are not
an authenticated identity system. Project-scoped worlds can share files, and
multiple worlds do not imply filesystem isolation from those shared project files.

The host trusts the operating system's namespace, filesystem, and Landlock
mechanisms. Unmanaged host writers do not participate in Palette's patch lock.
Multi-file patches can complete partially; receipts identify the committed files.
Sandbox-local success alone does not establish that an effect reached the host.
