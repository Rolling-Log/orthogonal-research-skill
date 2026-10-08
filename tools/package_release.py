"""Create one installable latest-version folder, never repository history."""
import argparse
import hashlib
import zipfile
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir',type=Path,default=ROOT/'dist')
    args=parser.parse_args()
    skill=ROOT/'orthogonal-research-skill'
    assert (skill/'SKILL.md').is_file() and (skill/'VERSION.txt').is_file()
    output=args.output_dir.resolve()
    output.mkdir(parents=True,exist_ok=True)
    archive=output/'orthogonal-research-skill.zip'
    with zipfile.ZipFile(archive,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=9) as package:
        for path in sorted(skill.rglob('*')):
            if path.is_file() and '__pycache__' not in path.parts and path.suffix not in ('.pyc','.pyd','.exe'):
                package.write(path,Path('orthogonal-research-skill')/path.relative_to(skill))
    with zipfile.ZipFile(archive) as package:
        names=package.namelist()
        assert all(name.startswith('orthogonal-research-skill/') for name in names)
        assert not any('/.git/' in name or '__pycache__' in name for name in names)
        assert package.read('orthogonal-research-skill/VERSION.txt') == (skill/'VERSION.txt').read_bytes()
    digest=hashlib.sha256(archive.read_bytes()).hexdigest()
    (output/'SHA256SUMS.txt').write_text(digest+'  '+archive.name+'\n',encoding='ascii')
    print(str(archive))
    print('{} files; {} bytes; sha256 {}'.format(len(names),archive.stat().st_size,digest))

if __name__=='__main__':
    main()
