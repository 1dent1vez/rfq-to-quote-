"""Small frozen citation wire; exact Unicode resolution into unchanged contract."""
from pydantic import Field, StrictInt, StrictStr
from .extraction import ContractModel, validate_extraction

RESOLUTION_VERSION = 'exact-citations-v1'


class CitationText(ContractModel):
    value: StrictStr = Field(min_length=1, max_length=500)
    citations: tuple[StrictStr, ...] = Field(min_length=1, max_length=20)


class CitationQuantity(ContractModel):
    value: StrictInt = Field(ge=1, le=1000000)
    citations: tuple[StrictStr, ...] = Field(min_length=1, max_length=20)


class CitationVehicle(ContractModel):
    make: CitationText | None
    model: CitationText | None
    year: CitationText | None
    engine: CitationText | None


class CitationItem(ContractModel):
    reference: CitationText | None
    description: CitationText | None
    manufacturer: CitationText | None
    quantity: CitationQuantity | None
    vehicle: CitationVehicle | None
    unsupported_concepts: tuple[CitationText, ...]


class CitationResult(ContractModel):
    items: tuple[CitationItem, ...] = Field(min_length=1, max_length=100)


def unique_location(original, literal):
    """Count overlapping matches; never choose a first match from ambiguity."""
    if not literal:
        raise ValueError('Empty citation')
    start = original.find(literal)
    if start < 0 or original.find(literal, start + 1) >= 0:
        raise ValueError('Citation/value must have exactly one occurrence in its anchor')
    return start


def resolve_citations(output, original):
    wire = CitationResult.model_validate(output)
    def field(obj):
        if obj is None:
            return None
        evidence = []
        if len(set(obj.citations)) != len(obj.citations):
            raise ValueError('Duplicate citations are not evidence')
        for citation in obj.citations:
            start = unique_location(original, citation)
            text = citation
            if isinstance(obj, CitationText):
                start += unique_location(citation, obj.value)
                text = obj.value
            evidence.append({'start': start, 'end': start + len(text), 'text': text})
        return {'value': obj.value, 'evidence': evidence}
    items = []
    for item in wire.items:
        row = {name: field(getattr(item, name)) for name in ('reference', 'description', 'manufacturer', 'quantity')}
        row['vehicle'] = None if item.vehicle is None else {name: field(getattr(item.vehicle, name)) for name in ('make', 'model', 'year', 'engine')}
        row['unsupported_concepts'] = [field(obj) for obj in item.unsupported_concepts]
        items.append(row)
    return validate_extraction({'items': items}, original)
