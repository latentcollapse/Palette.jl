#!/usr/bin/env bash
# GitHub Ubuntu runners only; leave global AppArmor/userns policy intact.
set -euo pipefail
sudo apt-get update
sudo apt-get install -y bubblewrap apparmor
profile=$(mktemp)
trap 'rm -f "$profile"' EXIT
# Ubuntu recommends this upstream profile. Pin both revision and content.
# It permits bwrap setup, then stacks a child profile denying capabilities.
curl --fail --silent --show-error --location \
  https://gitlab.com/apparmor/apparmor/-/raw/72229df83059480f4e9fb1488624201bdbd61755/profiles/apparmor/profiles/extras/bwrap-userns-restrict \
  --output "$profile"
printf '%s  %s\n' a964037f6cf0df1099f14226b037eaedde6237c86e715188e93eb460b30be859 "$profile" | sha256sum --check
sudo install -m 0644 "$profile" /etc/apparmor.d/bwrap-userns-restrict
sudo apparmor_parser --replace /etc/apparmor.d/bwrap-userns-restrict
# Exercise the namespace setup that previously failed before Julia startup.
bwrap --unshare-user --unshare-net --unshare-pid --unshare-ipc \
  --disable-userns --assert-userns-disabled --cap-drop ALL \
  --ro-bind / / --proc /proc --dev /dev --die-with-parent \
  /usr/bin/python3 -c 'from pathlib import Path; caps = next(line.split()[1] for line in Path("/proc/self/status").read_text().splitlines() if line.startswith("CapEff:")); assert int(caps, 16) == 0, caps'
