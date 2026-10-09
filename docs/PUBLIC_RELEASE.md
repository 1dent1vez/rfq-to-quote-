# Public release checklist

Publication, Git initialization, commits and remote pushes were not performed by the implementation task. The project owner should independently review before publishing.

## Proposed public scope

`python scripts/public_check.py --list` prints an explicit allowlist of source, tests, synthetic fixtures, dependency locks, license, CI, release docs, sanitized benchmark summary and six newly generated synthetic screenshots. This is a proposed list, not a claim that all workspace files are safe to commit. `.gitignore` excludes local stores, account/model responses, historic logs and screenshots, dependencies/caches, `.env`, private keys and manufacturer PDFs.

1. Independently inspect the list, source changes, documentation and screenshot pixels. The heuristic scanner can miss secrets.
2. Check `.gitignore` before staging; do not use force-add to include excluded studies, databases or raw responses.
3. Preserve private archival ledgers locally. Do not delete/reset them to obtain new inference. Public artifacts include technical summary/projection only, never account metadata or quota responses.
4. Re-run `./run-demo.sh --verify`, `scripts/http_smoke.py`, the Chromium smoke and `scripts/public_check.py` from the final proposed public source tree.
5. Confirm README and case-study claims match executed outputs. CI YAML is included, but a hosted run is only verified after it actually executes on the published repository.
6. Confirm manufacturer PDF is linked, not redistributed; the license applies to project code, not third-party catalog material.
7. Publish only after owner review. No OAuth, account or token changes are necessary for the local demo.

## Fresh-checkout regression detail

The historic partial-evaluation test originally needed private preservation manifests and prior study output. When those private manifests are absent, an additive test fixture builds an isolated mirror from public synthetic labels and a sanitized technical projection of the recorded offline parser results. It hashes those copied fixtures and validates preservation within that mirror. Existing tests and historical evaluator source remain intact; this does not pretend that a missing private ledger was checked.

The original local private manifest is still honored when present. Separate hash verification established that its protected historical bytes remained unchanged while the new portfolio app, frontend entrypoint and database were introduced.

## Release limitations

This is a trusted-local-operator demonstration, not a publicly deployable service. Identity labels are unverified, reset is locally accessible, in-progress UI edits are not autosaved, and local administrators can alter the audit DB. No real customer validation, broad NLP capability, server PDF/OCR, ERP/email integration, tax certification or ROI claim is included. No Docker or hosted CI execution is claimed without actual evidence.
