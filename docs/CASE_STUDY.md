# Case study: reliable quotation boundaries before model automation

## Problem and scope

An automotive-parts request can mix literal references, vehicle descriptions, quantities and restrictions. A plausible extracted line is not a commercial authorization. Missing context, alternative cabin references, changed prices and racing stock reservations must remain visible and must prevent accidental approval.

This portfolio delivery is a working, single-user local engineering MVP. Customers, transactions, commercial rules and operating data are agent-authored synthetic examples. They have not been validated by a salesperson or customer. No adoption, saved-time or ROI claim is made.

## Delivered path

A Spanish React/TypeScript interface receives pasted text or strict UTF-8 TXT/CSV. Manual capture is the default; a bounded offline parser is opt-in. Original source text and literal spans remain immutable. Humans select source-backed catalog entries, supply missing quantity/vehicle facts as supplemental evidence, classify unresolved context with reasons and record their demo actor label.

Only a fully reviewed request can become a Decimal-priced draft. Approval binds its version, customer/request/evidence, rules, catalog and inventory snapshot. SQLite `BEGIN IMMEDIATE` serializes revalidation, aggregate stock checks, reservation, case update and audit writes. Repeated exact approval is idempotent; stale or changed input is rejected. Approved cases are read-only and export printable HTML and spreadsheet-protected CSV locally.

## Real source versus synthetic operation

The eight GONHER references and Versa 2012–2025 L4-1.6L applications are a manually curated projection of the official 2026 catalog, printed page 69 / PDF page 71. GP oil references only; GPS is excluded, not denied. No manufacturer PDF is redistributed. Catalog declaration is not a fitment guarantee, and absence from the subset is not incompatibility.

Prices, costs, stock, IVA 16%, margin floor 20%, customers and reservations are separate DEMO data. No live supplier pricing, warehouse connection, production identity, tax-compliance engine or email channel is implemented.

## Recorded extraction evidence — failures retained

The following are projections of prior real synthetic studies, not fresh calls or a new performance claim. The original model experiment and citation experiment are retained locally unchanged; raw responses, account/catalog metadata and ledgers are intentionally excluded from the proposed public file list. [Sanitized technical summary](benchmark-summary.json).

| Study | Evaluated / planned | Strict contract passes | Exact full annotations | Populated gold fields correct |
|---|---:|---:|---:|---:|
| Original Solar Mini 4 experiment, initial | 8 / 8 | 7 / 8 | 0 / 8 | Not reported in original initial summary |
| Original experiment, latest selected after bounded retries | 8 / 8 | 8 / 8 | 1 / 8 | 17 / 37 |
| Citation contract, Solar Mini 4 | 8 / 8 | 3 / 8 | 0 / 8 | 20 / 37 |
| Citation contract, Step 3.7 Flash | 2 / 8 | 0 / 2 | 0 / 2 | 0 / 9 |
| Offline literal parser, broad existing contract fixtures | 8 / 8 | 3 / 8 | 0 / 8 | 3 / 37 |
| Offline literal parser, grammar-specific numeric fixtures | 17 / 17 | 16 / 17 | 16 / 17 | 29 / 29 |

The numeric fixture set includes one expected no-explicit-item pending envelope; contract counts refer to non-null extracted item results. The grammar-specific set is deliberately narrow and is **not** broad extraction accuracy. The broad fixture results show why manual confirmation remains necessary.

The original model's latest null-aware slots were 68/90 versus only 17/37 populated fields. Correctly absent fields can inflate the null-aware score. Evidence validation passing does not establish semantic completeness. The second citation model did not complete its planned evaluation; its two cases must not be presented as a full comparable benchmark.

The provider's schema-advertisement versus observed behavior discrepancy was investigated, but an upstream schema/transformation root cause was not proven. The experimental adapter used locally validated JSON-object output; this is not a provider-enforced schema guarantee. Failed attempts and exhausted/halted request/cost ledgers were not reset. **No model inference, paid fallback or account operation was performed for this delivery.**

## Engineering decisions and tradeoffs

- **Deterministic commercial core, human semantic review:** safe unknowns and observable decisions matter more than an impressive-looking autonomous quote. This leaves real operator work and does not claim unrestricted natural-language coverage.
- **No LangGraph for a short workflow:** explicit domain transitions and tests are easier to inspect here. Agent orchestration would add complexity without solving catalog provenance or atomic inventory.
- **SQLite instead of an ERP:** immediate transactions and conditional stock updates provide real local concurrency guarantees, but there is no distributed warehouse consistency or external reservation authority.
- **Whole-request review before draft:** incomplete requests cannot be commercially acted on. UI edits must be saved with new evidence before draft/approval. In-progress unsaved edits do not survive a page reload.
- **Snapshot-based optimistic approval:** any touched inventory version invalidates the draft, including a stock increase or unrelated reservation on the same product. Conservative regeneration is intentional; approved quote snapshots remain stable after future repricing.
- **Printable HTML plus CSV instead of server PDF:** no PDF renderer dependency or OCR claim. Browser print-to-PDF is available to the operator, while server exports remain inspectable and escaped.
- **Demo identity labels, not pretend authentication:** approval is a domain action for a trusted local operator. Production would need verified identities, roles, tenant isolation, authorization, durable audit protection, monitoring and integration design.
- **Historical isolation:** new app, entrypoint and database preserve old modules, UI studies and ledgers. Public regression checks use a sanitized technical projection when private archival manifests are unavailable; they do not pretend to validate a missing private ledger.

## Verification and what would come next

[QA_REPORT](QA_REPORT.md) records executed backend/component tests, fresh-environment build, real HTTP concurrency/restart smoke and Chromium UI/download verification. These demonstrate engineering behavior with synthetic inputs, not salesperson usability or business outcomes.

A responsible next phase would gather consented, labeled real-world requests, measure semantic coverage and operator error rates, evaluate a separately authorized model without leaking customer data, then design production identities and ERP/email integration. Those phases are not implemented or claimed here.
