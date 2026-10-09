# RFQ-to-Quote — Product brief

## Approved scope
A local portfolio MVP that turns a synthetic RFQ and text/CSV attachment into a catalog-backed quote requiring explicit human approval. No external account access, real email sending, cloud publishing, paid model API, or customer data.

## Human–agent contract
The human developer now authorizes autonomous completion of the local portfolio project without further stage approvals; ask only for critical blockers involving missing access, real expenditure, external publication or irreversible effects. The agent owns domain research, implementation, tests and independent review, and distinguishes hypotheses from validated usability/ROI. Resolve ordinary architecture, UX and synthetic commercial rules with explicit documented defaults. Deliver a working integrated demo and sanitized Git-ready artifact, not isolated modules. Do not publish to GitHub, send real email, access customer data, spend on paid inference or claim production readiness. Existing AI quality limitations and provider budget halts remain visible. Notify the human when final verification and independent review are complete.

## Approved business domain
Automotive spare-parts distributor (distribuidor de refacciones de autos). Human confirmed both intake modes: requests by part number and requests by vehicle plus part description. Detailed intake behavior, vehicle compatibility rules, commercial policy and interface design still require proposals and human decisions. Never invent part compatibility.

## Approved block 1 — intake and matching
Human approved: both part-number and vehicle/description intake, including mixed requests. Exact part lookup uses manufacturer when needed and never implies vehicle fitment. Vehicle lookup uses synthetic catalog applications by make/model/year/engine, requests missing discriminating fields, and never picks ambiguous matches automatically. Interface: original message → identified lines → evidence-backed candidates → pending clarifications. Clearly label synthetic catalog; no real fitment claims and no autonomous substitutes. Implement and demonstrate this block before advancing to pricing or quote approval. Extraction is deterministic offline baseline with supported format disclosed, not an implemented LLM.

## Approved next block — AI extraction boundary
Human developer approved provider-independent structured extraction: message → model extraction → Pydantic validation → deterministic catalog lookup → exception review. Model interprets requested parts, quantity, vehicle and missing information with original-message evidence; never invents fitment, prices or inventory. Persist original text, extraction result, extractor version and human corrections. Invalid output/timeout leaves explicit pending status. Contract tests and evaluation on labeled requests required. Do not add LangGraph for this short sequence by default. Provider/account access remains unapproved and must be agreed separately. Mock/fixture tests are not evidence of real model performance.

## Approved normalization boundary
Human developer approved separate representations: immutable raw_value with exact source evidence; normalized_value with deterministic rule ID/version for catalog lookup. Normalize only explicit domain aliases/units; never repair part numbers, infer missing quantities/vehicle data or invent fitment. Keep raw extraction and normalization records separate and auditable. Later customer facts require new supplementary messages, not overwriting original evidence. Model integration remains deferred.

## Approved citation experiment
Human developer approved simpler model wire contract: literal values and exact citations, deterministic code resolves Unicode offsets and rejects absent/ambiguous citations without weakening internal evidence validation. Compare the revised contract with a second currently free model on the same existing synthetic fixtures. No paid fallback or automatic default UI activation. Preserve original benchmark and exhausted budget ledger; new bounded experiment has separate authorization/accounting. Real customer data, pricing and stock remain out of scope.

## Approved hybrid baseline checkpoint
Human developer approved deterministic baseline first, with no further inference calls: code extracts explicit part-reference tokens, numeric quantities and years with exact evidence; model remains deferred for descriptions, spelled-out quantities and part–vehicle relationships. Preserve strict evidence, normalization and catalog boundaries. Do not guess missing facts, repair part identifiers, use gold labels/catalog matches as extraction answers, reset inference ledgers or activate a default AI UI. Measure baseline against existing fixtures and document gaps before another model experiment.

## Approved partial-result state boundary
Human developer approved separate line and request states: retain independently identified lines/candidates with exact evidence; unresolved substantive text remains explicitly pending at request level, never discarded or marked processed. Trivial greetings may be identified by a small explicit versioned rule, not a broad ignore/fuzzy heuristic. A partially resolved request is not commercially actionable; no quote/stock/send authorization. Implement and measure offline without further model calls or default UI expansion.

## Provisional demo policy — awaiting human business approval
- Currency: MXN.
- VAT: 16% demo assumption; not a tax compliance engine.
- Minimum gross margin: 20%, defined as (sale price − cost) / sale price.
- No autonomous discounts or substitute items.
- Never infer unknown SKUs, price, inventory or cost.
- Unknown/ambiguous items, insufficient stock and policy violations block approval.
- Approval applies to the exact displayed quote version; inventory is checked again at approval.
- Inventory reservation is local simulation, not an ERP write or customer commitment.

## Demonstration acceptance criteria
1. Operator can submit an RFQ with a supported attachment and see extracted items and source evidence.
2. Catalog-backed lines and deterministic monetary totals are visible.
3. Exceptions prevent approval server-side, not only in the UI.
4. A valid draft can be explicitly approved and downloaded as a local quote.
5. Duplicate input cannot accidentally reserve inventory twice.
6. Changed inventory and stale approvals are rejected safely.
7. Case state and audit events survive application restart.
8. Tests and production frontend build execute successfully.
9. README states what is implemented, simulated and not yet implemented.

## Honest portfolio positioning
This first delivery is an offline workflow-engineering demonstrator, not yet a deployed AI system. A deterministic extractor is a baseline, not an LLM. Text/CSV support is not PDF/OCR support. Synthetic evaluation is not proof of customer savings. Follow-up scope: evaluate a real structured-output model against labeled RFQs, add document parsing, then integrate approved channels and systems.

## Non-goals
Multi-tenant production security, SSO, ERP integration, unrestricted natural-language extraction, PDF/OCR, email delivery, tax compliance certification, and claims of production ROI.
