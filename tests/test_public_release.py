from pathlib import Path
from scripts.public_check import selected_files, scan


def test_public_allowlist_excludes_private_stores_responses_and_old_screenshots(tmp_path):
    for name in ['backend/portfolio.py','tests/fixtures/synthetic.json','docs/CASE_STUDY.md','docs/screenshots/01-intake.png','docs/nous-free-evaluation.json','data/ledger.sqlite3','.env','docs/seller-desktop.png','manufacturer.pdf']:
        target=tmp_path/name;target.parent.mkdir(parents=True,exist_ok=True);target.write_text('synthetic')
    assert [str(p.relative_to(tmp_path)) for p in selected_files(tmp_path)]==['backend/portfolio.py','docs/CASE_STUDY.md','docs/screenshots/01-intake.png','tests/fixtures/synthetic.json']


def test_public_scan_flags_personal_paths_and_nonfictional_emails_without_echoing_values(tmp_path):
    target=tmp_path/'README.md'
    target.write_text('Local path /home/someone/project\nprivate@real-company.net\nfiction@example.com\n')
    findings=scan(tmp_path)
    assert [(f['path'],f['line'],f['kind']) for f in findings]==[('README.md',1,'personal-path'),('README.md',2,'non-example-email')]
    assert 'someone' not in str(findings) and 'real-company.net' not in str(findings)
