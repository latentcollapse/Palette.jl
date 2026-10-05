#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Prepare bundled Palette on Linux, then generate client launch configurations."""
import argparse
import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import sys


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo-dir', type=Path, default=Path(__file__).resolve().parent / 'sdk')
    parser.add_argument('--output-dir', type=Path, required=True)
    parser.add_argument('--data-dir', type=Path, required=True)
    parser.add_argument('--depot-dir', type=Path, required=True)
    parser.add_argument('--connect-only', action='store_true', help='Use a runtime already built and prewarmed; do not prepare again')
    parser.add_argument('--wsl-distribution', help='Generate Windows Claude configuration targeting this WSL distribution')
    args = parser.parse_args()
    if sys.platform != 'linux':
        parser.error('Run setup in Linux or WSL2; the supervised host requires bubblewrap')
    repo, output, data, depot = (p.resolve() for p in (args.repo_dir, args.output_dir, args.data_dir, args.depot_dir))
    for command in ('julia', 'bwrap') + (() if args.connect_only else ('cargo',)):
        if not shutil.which(command):
            parser.error(f'missing prerequisite on PATH: {command}')
    if not (repo / 'Project.toml').is_file():
        parser.error(f'not a Palette SDK: {repo}')
    for private in (data, depot, output):
        if private == repo or repo in private.parents:
            parser.error('Keep data, depot, and generated configuration outside the SDK tree')
    workspace = (data/'workspace').resolve()
    for protected in (repo, depot, output, (data/'state').resolve(), (data/'worlds').resolve()):
        if workspace == protected or workspace.is_relative_to(protected) or protected.is_relative_to(workspace):
            parser.error('Workspace must not overlap source, depot, configuration, or host state')
    env = dict(os.environ, JULIA_DEPOT_PATH=str(depot))
    host = repo / 'runtime/host/target/release/palette-host'
    if not args.connect_only:
        subprocess.run(['julia', '--project='+str(repo), '-e', 'using Pkg; Pkg.instantiate()'], env=env, check=True)
        subprocess.run(['cargo','build','--manifest-path',str(repo/'runtime/host/Cargo.toml'),'--release','--locked'],env=env,check=True)
        subprocess.run([sys.executable,str(repo/'runtime/security/prewarm_depot.py'),'--project-dir',str(repo),'--host-bin',str(host)],env=env,check=True)
    for path in (repo/'Manifest.toml', host):
        if not path.is_file():
            parser.error(f'missing prepared runtime file: {path}')
    if not os.access(host, os.X_OK):
        parser.error(f'host is not executable: {host}')
    (data/'workspace').mkdir(parents=True, exist_ok=True)
    output.mkdir(parents=True, exist_ok=True)
    plugin = output/'palette-local-plugin'
    subprocess.run([sys.executable,str(repo/'runtime/security/install_operator_plugin.py'),'--format','portable','--plugin-dir',str(plugin),'--workspace-dir',str(data/'workspace'),'--repo-dir',str(repo)],check=True)
    package = Path(__file__).resolve().parent
    shutil.copyfile(package/'LICENSE', plugin/'LICENSE')
    (plugin/'NOTICE').write_text('Palette client integration\nCopyright (c) 2026 Matt C\nApache-2.0. Core runtime is separately licensed AGPL-3.0-only.\n')
    inherited = next(p for p in (package/'licenses/MIT-INHERITED.txt', package.parent/'licenses/MIT-INHERITED.txt') if p.is_file())
    shutil.copyfile(inherited, plugin/'MIT-INHERITED.txt')
    manifest_path = plugin/'plugin.json'
    manifest = json.loads(manifest_path.read_text()); manifest['license'] = 'Apache-2.0'
    manifest_path.write_text(json.dumps(manifest, indent=2)+'\n')
    launch_env = {'PALETTE_REPO':str(repo),'PALETTE_HOST':str(host),'PALETTE_DATA_HOME':str(data),
                  'PALETTE_STATE_DIR':str(data/'state'),'PALETTE_WORKSPACE_STATE_ROOT':str(data/'worlds'),
                  'OPERATOR_WORKSPACE':str(data/'workspace'),'JULIA_DEPOT_PATH':str(depot),'JULIA_PKG_OFFLINE':'true'}
    entry={'command':sys.executable,'args':[str(repo/'runtime/security/serve_palette.py')],'env':launch_env}
    config_path=plugin/'mcp.json'
    config=json.loads(config_path.read_text());config['mcpServers']['palette']={'type':'stdio',**entry}
    config_path.write_text(json.dumps(config,indent=2)+'\n')
    # Claude Desktop launches WSL explicitly; paths and environment stay Linux-native.
    desktop=entry
    if args.wsl_distribution:
        desktop={'command':'wsl.exe','args':['--distribution',args.wsl_distribution,'--exec','env',
                  *[key+'='+value for key,value in launch_env.items()],sys.executable,*entry['args']]}
    (output/'palette-launch.json').write_text(json.dumps(desktop,indent=2)+'\n')
    (output/'generic-mcp.json').write_text(json.dumps({'mcpServers':{'palette':desktop}},indent=2)+'\n')
    launcher=output/'palette-mcp'
    launcher.write_text('#!/bin/sh\nexec env '+ ' '.join(shlex.quote(k+'='+v) for k,v in launch_env.items())+' '+shlex.quote(sys.executable)+' '+shlex.quote(entry['args'][0])+' "$@"\n')
    launcher.chmod(0o755)
    print(json.dumps({'local_plugin':str(plugin),'claude_launch_config':str(output/'palette-launch.json'),'tunnel_stdio_command':str(launcher)}))

if __name__ == '__main__':
    main()
