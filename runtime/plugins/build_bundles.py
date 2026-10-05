#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Build reproducible client bundles from an explicit committed Palette revision."""
import argparse
import hashlib
import io
import json
from pathlib import Path
import subprocess
import tarfile
import zipfile

ROOT = Path(__file__).resolve().parents[2]


def zip_bytes(files):
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for name, data in sorted(files.items()):
            info = zipfile.ZipInfo(name, (2026, 10, 4, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            archive.writestr(info, data)
    return stream.getvalue()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--revision', default='HEAD')
    parser.add_argument('--output-dir', type=Path, required=True)
    args = parser.parse_args()
    revision = subprocess.check_output(['git','rev-parse',args.revision+'^{commit}'],cwd=ROOT,text=True).strip()
    raw = subprocess.check_output(['git','archive','--format=tar',revision],cwd=ROOT)
    with tarfile.open(fileobj=io.BytesIO(raw)) as archive:
        source = {m.name: archive.extractfile(m).read() for m in archive if m.isfile()}
    assert not any('.archive' in Path(n).parts or '.git' in Path(n).parts for n in source)
    version=json.loads(source['runtime/plugins/palette/plugin.json'])['version']
    inherited=source['runtime/licenses/MIT-INHERITED.txt']
    license_text=source['runtime/licenses/Apache-2.0.txt']
    shared={
        **{'sdk/'+n:d for n,d in source.items()},
        'setup.py':source['runtime/plugins/setup.py'],
        'INSTALL.md':source['runtime/plugins/DISTRIBUTION.md'],
        'BRAIN_BLAST.md':source['BRAIN_BLAST.md'].replace(b'(runtime/docs/', b'(sdk/runtime/docs/'),
        'LICENSE':license_text,
        'NOTICE':source['NOTICE'],
        'licenses/AGPL-3.0-only.txt':source['LICENSE'],
        'licenses/MIT-INHERITED.txt':inherited,
        'licenses/BOUNDARIES.md':source['runtime/licenses/README.md'],
        'SOURCE.json':json.dumps({'repository':'https://github.com/latentcollapse/Palette.jl','revision':revision,'plugin_version':version,'runtime':'source; prepare on Linux or WSL2','extra_language_toolchains':False},indent=2).encode()+b'\n'
    }
    claude={n.removeprefix('runtime/plugins/claude/'):d for n,d in source.items() if n.startswith('runtime/plugins/claude/')}
    claude.update({'LICENSE':license_text,'NOTICE':source['NOTICE'],'MIT-INHERITED.txt':inherited})
    mcpb=zip_bytes(claude)
    outputs={'Palette-Claude.mcpb':mcpb,'Palette-Claude.zip':zip_bytes({**shared,'Palette-Claude.mcpb':mcpb}),
             'Palette-ChatGPT.zip':zip_bytes({**shared,**{n.removeprefix('runtime/plugins/palette/'):d for n,d in source.items() if n.startswith('runtime/plugins/palette/')}})}
    args.output_dir.mkdir(parents=True,exist_ok=True)
    checks=[]
    for name,data in outputs.items():
        (args.output_dir/name).write_bytes(data)
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            assert archive.testzip() is None
        checks.append(hashlib.sha256(data).hexdigest()+'  '+name)
    (args.output_dir/'SHA256SUMS.txt').write_text('\n'.join(checks)+'\n')
    print(json.dumps({'revision':revision,'artifacts':list(outputs),'output_dir':str(args.output_dir.resolve())},indent=2))

if __name__ == '__main__':
    main()
