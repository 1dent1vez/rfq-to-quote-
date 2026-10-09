"""Opt-in extraction boundary. No default provider and no demo integration."""
from pydantic import BaseModel, ConfigDict, Field, StrictInt, StrictStr
import asyncio
import json
import sqlite3
import uuid
import math
from pathlib import Path
from datetime import datetime, timezone
from typing import Protocol, Any, Callable


class ExtractionProvider(Protocol):
    """Adapter must be async/cancellation-cooperative. No concrete provider shipped."""
    version: str

    async def extract(self, original_message: str, schema: dict) -> Any: ...

CONTRACT_VERSION = 'requested-parts-v1'


class ContractModel(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True)


class SourceSpan(ContractModel):
    start: StrictInt = Field(ge=0)
    end: StrictInt = Field(gt=0)
    text: StrictStr = Field(min_length=1)


class TextField(ContractModel):
    value: StrictStr = Field(min_length=1, max_length=500)
    evidence: tuple[SourceSpan, ...] = Field(min_length=1)


class QuantityField(ContractModel):
    value: StrictInt = Field(ge=1, le=1000000)
    evidence: tuple[SourceSpan, ...] = Field(min_length=1)


class Vehicle(ContractModel):
    make: TextField | None = None
    model: TextField | None = None
    year: TextField | None = None
    engine: TextField | None = None


class RequestedItem(ContractModel):
    reference: TextField | None = None
    description: TextField | None = None
    manufacturer: TextField | None = None
    quantity: QuantityField | None = None
    vehicle: Vehicle | None = None
    unsupported_concepts: tuple[TextField, ...] = ()


class ExtractionResult(ContractModel):
    items: tuple[RequestedItem, ...] = Field(min_length=1, max_length=100)


def validate_extraction(output, original_message: str) -> ExtractionResult:
    result = ExtractionResult.model_validate(output)
    for item in result.items:
        fields = [item.reference, item.description, item.manufacturer, item.quantity, *item.unsupported_concepts]
        if item.vehicle:
            fields.extend([item.vehicle.make, item.vehicle.model, item.vehicle.year, item.vehicle.engine])
        for field in filter(None, fields):
            for span in field.evidence:
                if not (span.start < span.end <= len(original_message)) or original_message[span.start:span.end] != span.text:
                    raise ValueError('Evidence must exactly match original-message character offsets')
            if isinstance(field, TextField) and any(c in field.value for c in '|=\n\r'):
                raise ValueError('Structured lookup delimiters are not supported in field values')
            if isinstance(field, TextField) and field.value not in [s.text for s in field.evidence]:
                raise ValueError('Text values must be literal evidence, not repaired or inferred')
    return result


def identify_validated(result: ExtractionResult, catalog, identify):
    """Normalize a separate projection, then use existing deterministic grammar."""
    from .normalization import normalize_extraction
    return _identify_normalized(normalize_extraction(result), catalog, identify)


def _identify_normalized(projection, catalog, identify):
    lines = []
    for original, item in zip(projection.extraction.items, projection.items):
        mode = 'vehiculo' if item.vehicle or original.description else 'pieza'
        fields = {'referencia': item.reference, 'descripcion': item.description, 'fabricante': item.manufacturer, 'cantidad': item.quantity}
        if item.vehicle:
            fields.update(dict(zip(('marca', 'modelo', 'anio', 'motor'), (item.vehicle.make, item.vehicle.model, item.vehicle.year, item.vehicle.engine))))
        text = mode + ''.join(' | ' + key + '=' + str(field.normalized_value) for key, field in fields.items() if field.normalized_value is not None)
        line = identify(text, catalog)[0]
        line['evidence'] = {'source': 'validated_extraction', 'fields': original.model_dump(mode='json')}
        line['normalization'] = item.model_dump(mode='json')
        if any(field.outcome == 'unsupported' for field in fields.values()):
            # Never treat a rejected supplied constraint as an absent constraint.
            line['status'] = 'pending'
            line['candidates'] = []
            line['compatibility'] = 'not_evaluated'
            line['missing_fields'].append('normalization_unsupported')
            line['clarifications'].append('Valor fuera de reglas explícitas de normalización; revisión humana requerida.')
        if item.unsupported_concepts:
            line['status'] = 'pending'
            line['missing_fields'].append('unsupported_concepts')
            line['clarifications'].append('Conceptos no soportados: revisión humana requerida; sin inferencias.')
        lines.append(line)
    return lines


class AttemptStore:
    """Local append-only snapshots, isolated from current seller tables."""
    def __init__(self, path):
        self.path = str(path)
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.path) as conn:
            conn.executescript('''
                CREATE TABLE IF NOT EXISTS extraction_v1_messages (
                    request_id TEXT PRIMARY KEY, original_message TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS extraction_v1_events (
                    sequence INTEGER PRIMARY KEY AUTOINCREMENT, data TEXT NOT NULL,
                    request_id TEXT NOT NULL);
            ''')

    def append(self, record):
        with sqlite3.connect(self.path, timeout=10) as conn:
            conn.execute('BEGIN IMMEDIATE')
            conn.execute('INSERT OR IGNORE INTO extraction_v1_messages VALUES (?, ?)',
                         (record['request_id'], record['original_message']))
            original = conn.execute('SELECT original_message FROM extraction_v1_messages WHERE request_id=?',
                                    (record['request_id'],)).fetchone()[0]
            if original != record['original_message']:
                raise ValueError('Original message is immutable for this request')
            if record.get('parent_attempt_id'):
                latest = conn.execute('SELECT data FROM extraction_v1_events WHERE request_id=? ORDER BY sequence DESC LIMIT 1',
                                      (record['request_id'],)).fetchone()
                if not latest or json.loads(latest[0])['attempt_id'] != record['parent_attempt_id'] or json.loads(latest[0])['state'] == 'started':
                    raise ValueError('Correction parent is stale or incomplete')
            record['recorded_at'] = datetime.now(timezone.utc).isoformat()
            conn.execute('INSERT INTO extraction_v1_events(data, request_id) VALUES (?, ?)',
                         (json.dumps(record, ensure_ascii=False, allow_nan=False), record['request_id']))

    def history(self, request_id):
        with sqlite3.connect(self.path) as conn:
            return [json.loads(row[0]) for row in conn.execute(
                'SELECT data FROM extraction_v1_events WHERE request_id=? ORDER BY sequence', (request_id,))]


class ExtractionOrchestrator:
    def __init__(self, provider: ExtractionProvider, store: AttemptStore, identify: Callable, *, timeout_seconds: float):
        if not math.isfinite(timeout_seconds) or timeout_seconds <= 0:
            raise ValueError('Timeout must be positive and finite')
        self.provider, self.store, self.identify = provider, store, identify
        self.timeout_seconds = timeout_seconds

    def correct(self, request_id: str, parent_attempt_id: str, output, *, actor: str, reason: str, catalog):
        """Append a human interpretation revision; cannot add facts absent from original."""
        if not actor.strip() or not reason.strip() or len(actor) > 200 or len(reason) > 2000:
            raise ValueError('Correction actor and reason required within limits')
        history = self.store.history(request_id)
        if not history or history[-1]['attempt_id'] != parent_attempt_id or history[-1]['state'] == 'started':
            raise ValueError('Correction parent is stale or incomplete')
        parent = history[-1]
        from .normalization import normalize_extraction
        result = validate_extraction(output, parent['original_message'])
        projection = normalize_extraction(result)
        lines = _identify_normalized(projection, catalog, self.identify)
        record = {'attempt_id': str(uuid.uuid4()), 'parent_attempt_id': parent_attempt_id,
                  'request_id': request_id, 'original_message': parent['original_message'],
                  'contract_version': CONTRACT_VERSION, 'extractor_version': 'human-correction-v1',
                  'parent_extractor_version': parent['extractor_version'], 'state': 'corrected',
                  'actor': actor, 'reason': reason, 'result': result.model_dump(mode='json'),
                  'normalization_version': projection.normalization_version,
                  'normalization': projection.model_dump(mode='json'),
                  'lines': lines, 'status': 'pending' if any(line['status'] == 'pending' for line in lines) else 'identified'}
        self.store.append(record)
        return record

    async def run(self, request_id: str, original_message: str, catalog):
        from .normalization import NORMALIZATION_VERSION, normalize_extraction
        if not isinstance(original_message, str) or not original_message.strip() or len(original_message) > 20000 or len(original_message.splitlines()) > 100:
            raise ValueError('Original message required: maximum 20000 characters and 100 lines')
        if not isinstance(request_id, str) or not request_id.strip() or len(request_id) > 128:
            raise ValueError('Request identifier required: maximum 128 characters')
        record = {'attempt_id': str(uuid.uuid4()), 'request_id': request_id,
                  'original_message': original_message, 'contract_version': CONTRACT_VERSION,
                  'extractor_version': self.provider.version, 'state': 'started',
                  'status': 'pending', 'result': None, 'raw_output': None, 'lines': [],
                  'normalization_version': NORMALIZATION_VERSION, 'normalization': None}
        self.store.append(record)
        try:
            output = await asyncio.wait_for(self.provider.extract(original_message, ExtractionResult.model_json_schema()),
                                            timeout=self.timeout_seconds)
        except TimeoutError:
            record['state'] = 'timeout'
        except Exception:
            record['state'] = 'provider_error'
        else:
            try:
                encoded_output = json.dumps(output, ensure_ascii=False, allow_nan=False)
                if len(encoded_output) > 200000:
                    raise ValueError('Output exceeds retention limit')
            except (TypeError, ValueError, OverflowError):
                record['state'] = 'invalid_output'
                record['output_retention'] = 'omitted_unsafe_or_oversize'
                self.store.append(record)
                return record
            record['raw_output'] = json.loads(encoded_output)
            record['output_retention'] = 'retained'
            try:
                result = validate_extraction(output, original_message)
            except ValueError:
                record['state'] = 'invalid_output'
            else:
                projection = normalize_extraction(result)
                record['result'] = result.model_dump(mode='json')
                record['normalization'] = projection.model_dump(mode='json')
                record['lines'] = _identify_normalized(projection, catalog, self.identify)
                record['state'] = 'validated'
                record['status'] = 'pending' if any(line['status'] == 'pending' for line in record['lines']) else 'identified'
        if callable(getattr(self.provider, 'audit_snapshot', None)):
            record['provider_audit'] = self.provider.audit_snapshot()
        self.store.append(record)
        return record
