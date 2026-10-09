# Security policy

## Supported boundary

Only a single-user, loopback-only demonstration with synthetic data is supported. Actor labels are not authentication, roles are not access controls, and the inventory editor/reset endpoint is intentionally available to the local demo operator. Do not bind it to a public interface, tunnel it, run it with real customer data or connect it to an ERP.

Implemented defenses: bounded JSON/multipart bodies, strict schemas and UTF-8 attachment validation, safe filenames without disk persistence, parameterized SQL, non-portfolio DB refusal, optimistic versions, atomic SQLite approval/reservation/audit, same-origin writes, local host allowlisting, CSP, escaped HTML and CSV formula protection. These do not provide tenant isolation, SSO, protected secrets or a tamper-proof audit. Local filesystem administrators can modify the database. FastAPI validation responses can contain the submitted local values; do not submit confidential data.

## Reporting

Before disclosing a vulnerability publicly, contact the repository maintainer through a private channel or the hosting platform's private vulnerability-reporting feature if enabled. No reporting inbox or hosted security program is claimed for this unpublished local project. Include a minimal synthetic reproduction, affected version and impact; never include passwords, API tokens, private model logs, personal contact information or real customer records.

## Release hygiene

Run `scripts/public_check.py`, inspect the explicit public file list and independently review source/images before committing. The scanner is heuristic, not proof that secrets cannot exist. Exclude `.env`, local databases, audit/history/model-response logs, caches, dependency directories and manufacturer PDFs. If sensitive material is ever exposed, stop distribution, revoke affected credentials through their owner and follow the host's incident process.
