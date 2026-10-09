# Seller realism research — block 1 revision proposal

## Human correction
Synthetic transactions/customers should use existing vehicle makes, models and real referenced part numbers. Invented automotive applications are not sufficient for acceptance. Human requested internet research and assessment of usefulness to a seller. Human approved the scoped revision: real GONHER references and source-backed Nissan Versa 2012–2025 filter applications; fictitious customers/transactions, simpler intake forms, source/edition evidence and clear separation of simulated operational data. Free-text LLM extraction remains a separate, unapproved expansion. Build this revision and stop for human acceptance.

## Verified primary source
GONHER 2026 filter catalog: https://gonher.com.mx/wp-content/uploads/2026/04/CATALOGO26_FILTROS.pdf
Downloaded successfully and extracted PDF physical page 71 / printed page 69 with pdftotext -layout. Source data below are catalog claims, not independent fitment certification.

| Vehicle | Years | Engine | Oil filter | Air filter | Cabin filter |
|---|---|---|---|---|---|
| Nissan Versa | 2012–2019 | L4-1.6L | GP-149 | GA-306 | GAC-2271 / GAF-2271 |
| Nissan Versa | 2020–2025 | L4-1.6L | GP-91 | GAD-6554 | GAC-2330 / GAF-2330 |

Do not infer cross-equivalence or other vehicle applications beyond these source rows. Keep catalog edition, printed page, URL and original claim for each application. Online availability does not grant bulk redistribution rights; review terms/license before publishing datasets or integrating at scale.

Retail corroboration for first row: https://encuentraautopartes.com/products/kit-de-filtros-para-nissan-versa-l4-1-6l-2012-2019 (GP-149, GA-306, GAC-2271).

## Operational sources
https://refacciones.com/pages/refacciones-por-vehiculo explicitly describes make/model/year lookup with engine, version, position or part number depending on component. This argues against asking engine unconditionally for every part and against accepting make/model/year as universally sufficient.
https://www.rigs.com.mx/api-refacciones advertises number and vehicle lookup and ACES/PIES/VCDB data for Mexican market. Its examples are explicitly illustrative; access is negotiated, no API call or independent coverage verification performed.
https://buscarefacciones.com/ search indexing describes multi-catalog reference/vehicle search; direct extraction was blocked. Not treated as a fully verified product.

## Assessment
Existing block proves persistence and controlled matching but is not a realistic seller tool: invented domain labels, exact-case structured grammar, no free-text interpretation, no real inventory/pricing, and no measured seller usability. Existing public catalogs mean lookup alone is not differentiated. Value hypothesis: turn messy customer requests into complete lines, ask only relevant clarifications, show source-backed candidates and later join local stock/pricing in an approval workflow.

## Proposed revision for human approval
1. Focus filters and Nissan Versa 2012–2025 first, using source-backed references above.
2. Keep fictitious customer (e.g. Taller Rivera, fictitious) and transactions; real vehicle/part references; synthetic stock and later prices visibly separate.
3. Add part-number and vehicle forms, no operator-facing key=value requirement; label parser baseline honestly.
4. Sample requests inspired by realistic customer wording, not claims of actual customer messages. Free-text AI extraction requires separate implementation/evaluation scope.
5. Cases: GP-149 direct request; Versa 2018 kit; Versa 2021 oil filter; missing year; unsupported component; no known application. Unknown coverage is not proof of incompatibility.
6. Seller validation: replay same curated requests in current/manual catalog lookup and revised app; measure identification time, corrections and wrong selections. No ROI or usability claim until tested with a seller.
