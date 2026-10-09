"""Pure deterministic projection of validated extraction; no providers or I/O."""
from typing import Literal
from pydantic import StrictInt, StrictStr
from .extraction import ContractModel, ExtractionResult, SourceSpan

NORMALIZATION_VERSION = 'automotive-normalization-v1'
RULE_VERSION = '1'
FILTER_DESCRIPTIONS = {
    'aceite': 'filtro de aceite', 'aire': 'filtro de aire', 'cabina': 'filtro de cabina',
    'filtro de aceite': 'filtro de aceite', 'filtro de aire': 'filtro de aire',
    'filtro de cabina': 'filtro de cabina',
}


ALLOWLISTS = {
    'description': ('filter-description-allowlist', FILTER_DESCRIPTIONS),
    'make': ('make-allowlist', {'nissan': 'Nissan'}),
    'model': ('model-allowlist', {'versa': 'Versa'}),
    'manufacturer': ('manufacturer-allowlist', {'gonher': 'GONHER'}),
    'engine': ('engine-allowlist', {'1.6': '1.6', '1.6l': '1.6', 'l4-1.6l': '1.6'}),
}


class NormalizedField(ContractModel):
    raw_value: StrictStr | StrictInt | None
    evidence: tuple[SourceSpan, ...]
    normalized_value: StrictStr | StrictInt | None
    rule_id: StrictStr
    rule_version: StrictStr = RULE_VERSION
    outcome: Literal['normalized', 'unchanged', 'unknown', 'unsupported']


class NormalizedVehicle(ContractModel):
    make: NormalizedField
    model: NormalizedField
    year: NormalizedField
    engine: NormalizedField


class NormalizedItem(ContractModel):
    reference: NormalizedField
    description: NormalizedField
    manufacturer: NormalizedField
    quantity: NormalizedField
    vehicle: NormalizedVehicle | None
    unsupported_concepts: tuple[NormalizedField, ...]


class NormalizationResult(ContractModel):
    normalization_version: StrictStr = NORMALIZATION_VERSION
    extraction: ExtractionResult
    items: tuple[NormalizedItem, ...]


def normalize_field(field, name):
    raw = field.value if field is not None else None
    evidence = field.evidence if field is not None else ()
    rule_id = 'literal-identity'
    value = raw
    outcome = 'unknown' if raw is None else 'unchanged'
    if name == 'unsupported_concepts':
        rule_id = 'unsupported-concept-review'
        value = None
        outcome = 'unsupported'
    elif name in ALLOWLISTS:
        rule_id, allowlist = ALLOWLISTS[name]
        if raw is not None:
            value = allowlist.get(raw.strip().casefold())
            outcome = 'unsupported' if value is None else ('unchanged' if value == raw else 'normalized')
    return NormalizedField(raw_value=raw, evidence=evidence, normalized_value=value,
                           rule_id=rule_id, outcome=outcome)


def normalize_extraction(result: ExtractionResult) -> NormalizationResult:
    """Accept only a validated typed extraction; preserve its immutable snapshot."""
    items = []
    for item in result.items:
        fields = {name: normalize_field(getattr(item, name), name)
                  for name in ('reference', 'description', 'manufacturer', 'quantity')}
        vehicle = None
        if item.vehicle is not None:
            vehicle = NormalizedVehicle(**{name: normalize_field(getattr(item.vehicle, name), name)
                                           for name in ('make', 'model', 'year', 'engine')})
        items.append(NormalizedItem(**fields, vehicle=vehicle,
                                   unsupported_concepts=tuple(normalize_field(f, 'unsupported_concepts')
                                                              for f in item.unsupported_concepts)))
    return NormalizationResult(extraction=result, items=tuple(items))
