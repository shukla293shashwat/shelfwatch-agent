"""Create a clean source ZIP; runtime mode omits reports and documentation."""
import argparse
import hashlib
import json
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKIP = {'.git','.venv','venv','__pycache__','.data','reports'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--runtime-only',action='store_true')
    args=parser.parse_args()
    target=args.output.resolve()
    if target.exists():
        raise SystemExit(f'Refusing to replace an existing archive: {target}')
    manifest={}
    with zipfile.ZipFile(target,'w',zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(ROOT.rglob('*')):
            if not path.is_file() or path.resolve()==target:
                continue
            relative=path.relative_to(ROOT)
            if set(relative.parts)&SKIP or path.suffix in {'.pyc','.log','.zip'}:
                continue
            if path.name.startswith('.env') and path.name!='.env.example':
                continue
            if path.name.startswith('deployment-state'):
                continue
            if args.runtime_only and (relative.parts[0] in {'docs','tests','deploy'} or path.name.startswith('test_')):
                continue
            data=path.read_bytes()
            name=relative.as_posix() if args.runtime_only else 'ShelfWatch-Ready/'+relative.as_posix()
            archive.writestr(name,data)
            manifest[name]=hashlib.sha256(data).hexdigest()
        manifest_name='PACKAGE_MANIFEST.json' if args.runtime_only else 'ShelfWatch-Ready/PACKAGE_MANIFEST.json'
        archive.writestr(manifest_name,json.dumps({'files':manifest},indent=2))
    print(f'Saved {target} ({len(manifest)} files)')


if __name__=='__main__':
    main()
