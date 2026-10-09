# Contributing

This is a local, synthetic portfolio demo, not a production quoting service.

1. Install with `./run-demo.sh --verify`; use only fictional customer requests.
2. Add a meaningful failing test before changing behavior. Observe RED, implement the smallest vertical slice, then run GREEN and the full regression suite.
3. Preserve original evidence, source provenance, strict unknowns, Decimal money and exact-version approvals. Do not repair part identifiers or infer fitment.
4. Run `./run-demo.sh --verify`, `.venv/bin/python scripts/http_smoke.py`, and the documented Chromium smoke before a UI/workflow change is considered complete.
5. Run `.venv/bin/python scripts/public_check.py --list` and independently inspect intended changes, synthetic screenshots and dependency updates before publication.

Historical modules, tests and study artifacts are retained, not deleted to improve pass counts. Public tests use a sanitized technical snapshot only when private archival manifests are absent. Never redistribute manufacturer PDFs or raw model/account logs.

Keep model inference, external account access, paid usage, email sending, deployment and publication out of routine development. Do not reset old request/cost ledgers to enable another experiment. Real model evaluation requires a separately authorized scope and an honest report of failures, null-aware versus populated-field scoring and dataset provenance.

Issues and pull requests should state behavior, reproduction steps, real verification and remaining limitations. Do not claim adoption, ROI or production readiness from synthetic tests.
