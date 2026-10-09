"""Synthetic annotations only; no model inference or customer evidence."""
import asyncio
import copy
import pytest
from backend import extraction as ex
from backend.app import CATALOG, identify


def field(message, text, value=None):
    start = message.index(text)
    return {'value': text if value is None else value,
            'evidence': [{'start': start, 'end': start + len(text), 'text': text}]}


def normalize(result):
    from backend import normalization
    return normalization.normalize_extraction(result)


@pytest.mark.parametrize('name,raw,expected,rule', [
    ('make', ' nISSAN ', 'Nissan', 'make-allowlist'),
    ('model', ' VERSA ', 'Versa', 'model-allowlist'),
    ('manufacturer', ' gonHER ', 'GONHER', 'manufacturer-allowlist'),
    ('engine', '1.6L', '1.6', 'engine-allowlist'),
    ('engine', 'L4-1.6L', '1.6', 'engine-allowlist'),
    ('engine', '1.6', '1.6', 'engine-allowlist'),
])
def test_known_domain_values_use_only_explicit_rules(name, raw, expected, rule):
    item = {'manufacturer': field(raw, raw)} if name == 'manufacturer' else {'vehicle': {name: field(raw, raw)}}
    result = ex.validate_extraction({'items': [item]}, raw)
    projection = normalize(result).items[0]
    value = projection.manufacturer if name == 'manufacturer' else getattr(projection.vehicle, name)
    assert value.normalized_value == expected
    assert value.raw_value == raw and value.evidence[0].text == raw
    assert value.rule_id == rule and value.rule_version == '1'


def vehicle_payload(alias='aceite', engine='L4-1.6L', *, quantity=True):
    message = f'{alias}; nISSAN; VERSA; 2018; {engine}; gonHER; dos'
    item = {'description': field(message, alias), 'manufacturer': field(message, 'gonHER'),
            'vehicle': {'make': field(message, 'nISSAN'), 'model': field(message, 'VERSA'),
                        'year': field(message, '2018'), 'engine': field(message, engine)}}
    if quantity:
        item['quantity'] = field(message, 'dos', 2)
    return message, {'items': [item]}


@pytest.mark.parametrize('alias,refs,status', [
    ('aceite', ['GP-149'], 'matched'),
    ('aire', ['GA-306'], 'matched'),
    ('cabina', ['GAC-2271', 'GAF-2271'], 'pending'),
])
def test_alias_projection_matches_only_correct_catalog_family(alias, refs, status):
    message, output = vehicle_payload(alias)
    result = ex.validate_extraction(output, message)
    before = result.model_dump(mode='json')
    line = ex.identify_validated(result, CATALOG, identify)[0]
    assert [c['reference'] for c in line['candidates']] == refs
    assert line['status'] == status
    assert line['evidence']['fields'] == before['items'][0]
    assert line['normalization']['description']['normalized_value'] == f'filtro de {alias}'
    assert line['normalization']['description']['raw_value'] == alias
    assert result.model_dump(mode='json') == before
    if alias == 'cabina':
        assert 'seleccion' in line['missing_fields']
    else:
        assert line['compatibility'] == 'source_catalog_claim_only'


@pytest.mark.parametrize('name,raw', [
    ('description', 'clima'), ('description', 'gasolina'), ('description', 'kit'),
    ('description', 'balatas'), ('description', 'filtro'),
    ('description', 'aceite de motor'), ('make', 'Datsun'), ('model', 'V-Drive'),
    ('manufacturer', 'otra marca'), ('engine', '1600cc'), ('engine', 'L4 1.6 L'),
])
def test_unallowlisted_terms_do_not_broaden_candidates(name, raw):
    message, output = vehicle_payload()
    message += '; ' + raw
    item = output['items'][0]
    target = item['vehicle'] if name in ('make', 'model', 'engine') else item
    target[name] = field(message, raw)
    result = ex.validate_extraction(output, message)
    item_projection = normalize(result).items[0]
    value = getattr(item_projection.vehicle if name in ('make', 'model', 'engine') else item_projection, name)
    assert value.raw_value == raw and value.normalized_value is None
    assert value.outcome == 'unsupported'
    line = ex.identify_validated(result, CATALOG, identify)[0]
    assert line['status'] == 'pending'
    assert line['candidates'] == []
    assert line['compatibility'] == 'not_evaluated'
    assert 'normalization_unsupported' in line['missing_fields']


def test_attempt_and_correction_persist_same_versioned_projection(tmp_path):
    message, output = vehicle_payload()

    class MockAnnotations:
        """Synthetic test annotation, not a model."""
        version = 'mock-normalization-annotations-v1'

        async def extract(self, original_message, schema):
            return copy.deepcopy(output)

    path = tmp_path / 'normalization.db'
    store = ex.AttemptStore(path)
    engine = ex.ExtractionOrchestrator(MockAnnotations(), store, identify, timeout_seconds=1)
    initial = asyncio.run(engine.run('normalize', message, CATALOG))
    assert initial['normalization_version'] == 'automotive-normalization-v1'
    assert initial['normalization'] == normalize(ex.validate_extraction(output, message)).model_dump(mode='json')
    assert initial['result'] == ex.validate_extraction(output, message).model_dump(mode='json')
    assert initial['status'] == 'identified'
    revised_output = copy.deepcopy(output)
    del revised_output['items'][0]['quantity']
    corrected = engine.correct('normalize', initial['attempt_id'], revised_output,
                               actor='local-reviewer', reason='Revisar cantidad', catalog=CATALOG)
    assert corrected['normalization_version'] == initial['normalization_version']
    assert corrected['normalization'] == normalize(ex.validate_extraction(revised_output, message)).model_dump(mode='json')
    assert corrected['normalization']['items'][0]['description']['rule_version'] == '1'
    assert corrected['normalization']['items'][0]['vehicle']['engine']['rule_version'] == '1'
    assert corrected['normalization']['items'][0]['quantity']['outcome'] == 'unknown'
    assert corrected['status'] == 'pending'
    history = ex.AttemptStore(path).history('normalize')
    assert history[-2:] == [initial, corrected]
    assert history[0]['normalization'] is None
    assert history[0]['normalization_version'] == initial['normalization_version']
    assert corrected['lines'][0]['normalization'] == corrected['normalization']['items'][0]


@pytest.mark.parametrize('reference,expected_refs', [
    ('GP149', []), ('gp-149', ['GP-149']), ('GP-149', ['GP-149']),
    ('GP--149', []), ('GP-0149', []),
])
def test_reference_projection_is_exact_identity_not_equivalence(reference, expected_refs):
    message = f'dos {reference}'
    result = ex.validate_extraction({'items': [{'reference': field(message, reference),
                                               'quantity': field(message, 'dos', 2)}]}, message)
    value = normalize(result).items[0].reference
    assert value.raw_value == value.normalized_value == reference
    assert value.outcome == 'unchanged' and value.rule_id == 'literal-identity'
    assert value.evidence[0].text == reference
    line = ex.identify_validated(result, CATALOG, identify)[0]
    assert [c['reference'] for c in line['candidates']] == expected_refs
    assert line['evidence']['fields']['reference']['value'] == reference
    assert line['compatibility'] == 'not_evaluated'


def test_unknown_fields_and_quantity_are_not_filled_by_matching_catalog():
    message, output = vehicle_payload(quantity=False)
    del output['items'][0]['manufacturer']
    result = ex.validate_extraction(output, message)
    projection = normalize(result)
    for name in ('quantity', 'manufacturer', 'reference'):
        value = getattr(projection.items[0], name)
        assert value.raw_value is None and value.normalized_value is None
        assert value.evidence == () and value.outcome == 'unknown'
    line = ex.identify_validated(result, CATALOG, identify)[0]
    assert line['status'] == 'pending' and 'cantidad' in line['missing_fields']
    assert line['normalization']['manufacturer']['normalized_value'] is None
    unknown = normalize(ex.validate_extraction({'items': [{}]}, 'desconocido'))
    assert unknown.items[0].vehicle is None
    assert ex.identify_validated(unknown.extraction, CATALOG, identify)[0]['status'] == 'pending'


@pytest.mark.parametrize('name,raw,repaired', [
    ('description', 'aceite', 'filtro de aceite'), ('reference', 'GP149', 'GP-149'),
    ('manufacturer', 'gonher', 'GONHER'),
])
def test_normalization_never_relaxes_exact_extraction_contract(name, raw, repaired):
    with pytest.raises(ValueError, match='literal evidence'):
        ex.validate_extraction({'items': [{name: field(raw, raw, repaired)}]}, raw)
    invalid = {'items': [{name: field(raw, raw)}]}
    invalid['items'][0][name]['evidence'][0]['text'] = repaired
    with pytest.raises(ValueError, match='exactly match'):
        ex.validate_extraction(invalid, raw)


def test_old_history_remains_exact_and_can_parent_new_normalized_correction(tmp_path):
    message, output = vehicle_payload()
    store = ex.AttemptStore(tmp_path / 'legacy.db')
    legacy = {'attempt_id': 'old-attempt', 'request_id': 'old', 'original_message': message,
              'contract_version': ex.CONTRACT_VERSION, 'extractor_version': 'old-extractor-v1',
              'state': 'validated', 'status': 'pending', 'result': output, 'lines': []}
    store.append(legacy)
    before = copy.deepcopy(store.history('old'))
    engine = ex.ExtractionOrchestrator(None, store, identify, timeout_seconds=1)
    corrected = engine.correct('old', 'old-attempt', output, actor='reviewer',
                               reason='Aplicar reglas aprobadas', catalog=CATALOG)
    reopened = ex.AttemptStore(tmp_path / 'legacy.db').history('old')
    assert reopened[0] == before[0]
    assert 'normalization' not in reopened[0] and 'normalization_version' not in reopened[0]
    assert reopened[1] == corrected and corrected['status'] == 'identified'
    assert corrected['normalization']['extraction'] == corrected['result']


@pytest.mark.parametrize('raw,expected', [(' AIRE ', 'filtro de aire'),
    ('filtro de aceite', 'filtro de aceite'), ('FILTRO DE CABINA', 'filtro de cabina')])
def test_allowlist_uses_casing_and_outer_whitespace_only(raw, expected):
    result = ex.validate_extraction({'items': [{'description': field(raw, raw)}]}, raw)
    value = normalize(result).items[0].description
    assert value.raw_value == raw and value.evidence[0].text == raw
    assert value.normalized_value == expected


def test_unsupported_concept_is_a_review_constraint_never_a_filter_alias():
    message = 'dos GP-149 aceite'
    output = {'items': [{'reference': field(message, 'GP-149'), 'quantity': field(message, 'dos', 2),
                         'unsupported_concepts': [field(message, 'aceite')]}]}
    result = ex.validate_extraction(output, message)
    value = normalize(result).items[0].unsupported_concepts[0]
    assert value.raw_value == 'aceite' and value.evidence[0].text == 'aceite'
    assert value.normalized_value is None and value.outcome == 'unsupported'
    assert value.rule_id == 'unsupported-concept-review'
    line = ex.identify_validated(result, CATALOG, identify)[0]
    assert line['status'] == 'pending' and 'unsupported_concepts' in line['missing_fields']


def test_literal_alias_projection_is_separate_and_immutable():
    message = 'aceite'
    result = ex.validate_extraction({'items': [{'description': field(message, message)}]}, message)
    before = result.model_dump(mode='json')
    projection = normalize(result)
    value = projection.items[0].description
    assert value.raw_value == 'aceite'
    assert value.normalized_value == 'filtro de aceite'
    assert value.evidence == result.items[0].description.evidence
    assert value.rule_id == 'filter-description-allowlist'
    assert value.rule_version == '1'
    assert value.outcome == 'normalized'
    assert projection.extraction == result
    assert result.model_dump(mode='json') == before
    with pytest.raises(ValueError):
        value.normalized_value = 'filtro de aire'
    with pytest.raises(ValueError):
        result.items[0].description.value = 'filtro de aceite'
