"""Conservative public-file allowlist and heuristic hygiene scan; no git writes."""
import argparse
import json
import re
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
ROOT_FILES={'README.md','LICENSE','CONTRIBUTING.md','SECURITY.md','.gitignore','.env.example','requirements.txt','requirements.lock','requirements-dev.txt','run-demo.sh'}
PUBLIC_DOCS={'CASE_STUDY.md','ARCHITECTURE.md','GUIA_ES.md','QA_REPORT.md','PUBLIC_RELEASE.md','PRODUCT_BRIEF.md','SELLER_REALISM_RESEARCH.md','benchmark-summary.json'}
SCREENSHOTS={'01-intake.png','02-review.png','03-approved.png','04-printable.png','05-stale-draft.png','06-mobile.png'}


def selected_files(root):
    root=Path(root)
    found=[]
    for path in root.rglob('*'):
        if not path.is_file() or path.is_symlink():continue
        rel=path.relative_to(root)
        parts=rel.parts
        if any(p in {'node_modules','dist','.venv','.cache','__pycache__','.pytest_cache','.git'} for p in parts):continue
        allowed=(len(parts)==1 and parts[0] in ROOT_FILES)
        allowed|=parts[0] in {'backend','tests','scripts'} and path.suffix in {'.py','.json'}
        allowed|=parts[0]=='frontend' and (path.suffix in {'.tsx','.ts','.css','.json','.html'})
        allowed|=parts[0]=='.github' and path.suffix in {'.yml','.yaml'}
        allowed|=len(parts)==2 and parts[0]=='docs' and parts[1] in PUBLIC_DOCS
        allowed|=len(parts)==3 and parts[:2]==('docs','screenshots') and parts[2] in SCREENSHOTS
        if allowed:found.append(path)
    return sorted(found,key=lambda p:str(p.relative_to(root)))


def scan(root):
    root=Path(root)
    findings=[]
    for path in selected_files(root):
        if path.suffix=='.png':continue
        text=path.read_text(encoding='utf-8')
        for number,line in enumerate(text.splitlines(),1):
            kinds=[]
            # Pattern literals in scanner/tests are test code, not private artifacts.
            if path.name not in {'public_check.py','test_public_release.py'} and re.search(r'/(?:home|Users)/[A-Za-z0-9_.-]+/',line):kinds.append('personal-path')
            for match in re.finditer(r'[A-Za-z0-9._%+-]+@([A-Za-z0-9.-]+\.[A-Za-z]{2,})',line):
                domain=match.group(1).lower()
                if domain not in {'example.com','example.org','example.net'} and not domain.endswith(('.invalid','.test','.example')) and path.name!='test_public_release.py':
                    kinds.append('non-example-email')
            if re.search(r'\bsk-[A-Za-z0-9_-]{20,}|\bgh[pousr]_[A-Za-z0-9]{20,}|-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----',line):kinds.append('possible-secret')
            for kind in sorted(set(kinds)):
                findings.append({'path':str(path.relative_to(root)),'line':number,'kind':kind})
    return findings


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--list',action='store_true',help='Print exact proposed public file list, not source contents')
    args=parser.parse_args()
    files=selected_files(ROOT)
    findings=scan(ROOT)
    result={'selected_files':len(files),'findings':findings,'note':'Heuristic checks do not replace independent source/image/secret review; no git operation performed.'}
    if args.list:result['files']=[str(p.relative_to(ROOT)) for p in files]
    print(json.dumps(result,ensure_ascii=False,indent=2))
    return 1 if findings else 0


if __name__=='__main__':raise SystemExit(main())
