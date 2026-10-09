"""Pure, conservative partial-state policy. No parsing expansion or fitment inference."""
import re
from typing import Literal, TypedDict

STATE_VERSION = 'offline-partial-intake-v1'
LineStatus = Literal['matched', 'pending']
RequestStatus = Literal['identified', 'partially_identified', 'pending']


class ContextFlag(TypedDict):
    rule_id: str
    rule_version: str
    items: list[int]
    evidence: list[dict]
    blocks_line: bool


# Literal lexical flags, not a semantic classifier. Isolated restrictions have
# ambiguous scope and block all occurrences; attached text blocks only its clause.
RESTRICTION = re.compile(r'\b(?:solo|sólo|sin|no|excepto|total|ambos|ambas|cada|todos|todas|sustitutos?|sustituir|alternativa|originales)\b|\ben lugar de\b', re.I)
# This recognizes only deferred context syntax, NEVER a vehicle fact/assignment.
VEHICLE_CONTEXT = re.compile(r'para\s+[A-Za-zÁÉÍÓÚÜÑáéíóúüñ]+\s*(?:19[0-9]{2}|20[0-9]{2})', re.I)


def context_flags(message: str, parsed: dict) -> list[ContextFlag]:
    items = parsed['result']['items'] if parsed['result'] else []
    flags = []
    clauses = list(re.finditer(r'[^;\n]+', message))
    for fragment in parsed['unresolved_fragments']:
        # Original spans can include separators; intersect without rewriting them.
        for clause in clauses:
            start, end = max(clause.start(), fragment['start']), min(clause.end(), fragment['end'])
            if start >= end:
                continue
            text = message[start:end]
            trimmed = text.strip(' \t\r,;.!?')
            if not trimmed:
                continue
            local = [i for i, item in enumerate(items) if clause.start() <= item['reference']['evidence'][0]['start'] < clause.end()]
            vehicle = bool(VEHICLE_CONTEXT.fullmatch(trimmed))
            blocking = bool(local) and not vehicle
            affected = local
            rule = 'unassigned_vehicle_context' if vehicle else 'unprocessed_attached_context' if local else 'unprocessed_request_fragment'
            if RESTRICTION.search(text):
                blocking = True
                affected = local or list(range(len(items)))
                rule = 'literal_restriction_or_ambiguous_scope'
            flags.append({'rule_id': rule, 'rule_version': '1', 'items': affected,
                          'evidence': [{'start': start, 'end': end, 'text': text}], 'blocks_line': blocking})
    return flags


def request_status(lines: list[dict], unresolved: bool) -> RequestStatus:
    if any(line['status'] not in ('matched', 'pending') for line in lines):
        raise ValueError('Invalid partial line status')
    matched = sum(line['status'] == 'matched' for line in lines)
    if not matched:
        return 'pending'
    if matched == len(lines) and not unresolved:
        return 'identified'
    return 'partially_identified'
