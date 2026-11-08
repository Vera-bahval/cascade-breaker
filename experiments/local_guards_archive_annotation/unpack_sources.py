"""Restore byte-identical source evidence from the committed, hashed bundles."""
import argparse
import hashlib
import json
import tarfile
from pathlib import Path

E = Path(__file__).resolve().parent


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--destination',type=Path,default=E)
    args=parser.parse_args(); destination=args.destination.resolve()
    manifest=json.loads((E/'source-bundles/manifest.json').read_text())
    total=0
    for name,record in manifest.items():
        archive=E/'source-bundles'/record['archive']
        if hashlib.sha256(archive.read_bytes()).hexdigest()!=record['sha256']:
            raise ValueError(f'{name}: archive checksum')
        with tarfile.open(archive,'r:gz') as tar:
            members=tar.getmembers()
            if len(members)!=len(record['members']) or {m.name for m in members}!=set(record['members']):
                raise ValueError(f'{name}: member set')
            for member in members:
                target=(destination/member.name).resolve()
                if not member.isfile() or not target.is_relative_to(destination) or Path(member.name).parts[0]!=name:
                    raise ValueError('invalid archive member')
                data=tar.extractfile(member).read()
                if hashlib.sha256(data).hexdigest()!=record['members'][member.name]:
                    raise ValueError('member checksum')
                if target.exists():
                    if target.read_bytes()!=data:raise ValueError(f'refuse overwrite {target}')
                else:
                    target.parent.mkdir(parents=True,exist_ok=True)
                    target.write_bytes(data)
                total+=1
    print(f'Verified and restored {total} source evidence files.')


if __name__=='__main__':main()
