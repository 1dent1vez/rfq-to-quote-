"""Bounded, offline literal grammar. No catalog, labels, inference or I/O."""
import re
from .extraction import validate_extraction

PARSER_VERSION = 'explicit-reference-numeric-v1'
RULE_VERSION = '1'
REFERENCE = re.compile(r'(?<![\w./+\-])[A-Za-z]{2,4}-?[0-9]{2,5}(?![\w/+\-]|\.[\w])')


def span(message, start, end):
    return {'start': start, 'end': end, 'text': message[start:end]}


def parse_message(message):
    if not isinstance(message, str) or not message.strip() or len(message) > 20000 or len(message.splitlines()) > 100:
        raise ValueError('Message required: maximum 20000 Unicode characters and 100 lines')
    shaped = list(REFERENCE.finditer(message))
    # Lexical exclusions are syntax safety rules, never a catalog-prefix allowlist.
    reserved = {'tel', 'fax', 'ene', 'jan', 'feb', 'mar', 'abr', 'apr', 'may', 'jun', 'jul', 'ago', 'aug', 'sep', 'sept', 'oct', 'nov', 'dic', 'dec'}
    uncertain, matches = [], []
    for candidate in shaped:
        prefix = re.match(r'[A-Za-z]+', candidate.group()).group().casefold()
        number = int(re.search(r'[0-9]+$', candidate.group()).group())
        if prefix in reserved or 1900 <= number <= 2099:
            uncertain.append(span(message, *candidate.span()))
        else:
            matches.append(candidate)
    if len(shaped) > 100:
        raise ValueError('Maximum 100 reference occurrences')
    items, rules, quantity_gaps = [], [], []
    covered = [False] * len(message)
    numeric = r'[+\-]?[0-9]+(?:[.,][0-9]+)?'
    prefixes, suffixes = [], []
    for index, match in enumerate(matches):
        left = max(message.rfind('\n', 0, match.start()) + 1, matches[index-1].end() if index else 0)
        right = min(message.find('\n', match.end()) if '\n' in message[match.end():] else len(message),
                    matches[index+1].start() if index+1 < len(matches) else len(message))
        pre = re.search(r'(?<![\w.,+\-])(' + numeric + r')(?:[ \t]+(?:piezas?|pzas?))?[ \t]+$', message[left:match.start()], re.I)
        post = re.match(r'[ \t]*[xX][ \t]*(' + numeric + r')(?![\w,+\-]|\.[0-9])', message[match.end():right])
        prefixes.append(None if pre is None else (left+pre.start(1), left+pre.end(1)))
        suffixes.append(None if post is None else (match.end()+post.start(1), match.end()+post.end(1)))
    for index, match in enumerate(matches):
        evidence = span(message, *match.span())
        item = {'reference': {'value': match.group(), 'evidence': [evidence]}}
        candidates = [s for s in (prefixes[index], suffixes[index]) if s is not None]
        # A suffix attached to the previous reference cannot be borrowed as a prefix.
        if index and prefixes[index] == suffixes[index-1] and prefixes[index] is not None:
            candidates.remove(prefixes[index])
        ambiguous_run = prefixes[index] is not None and re.search(r'[0-9](?:[ \t]+(?:[yoó][ \t]+)?)$', message[:prefixes[index][0]], re.I)
        if len(candidates) == 1 and not ambiguous_run:
            start, end = candidates[0]
            literal = message[start:end]
            if len(literal) <= 7 and literal.isascii() and literal.isdigit() and 1 <= int(literal) <= 1000000 and not 1900 <= int(literal) <= 2099:
                q = span(message, start, end)
                item['quantity'] = {'value': int(literal), 'evidence': [q]}
                rules.append({'item': index, 'rule_id': 'numeric-local-quantity', 'rule_version': RULE_VERSION, 'evidence': [q]})
                covered[start:end] = [True] * (end-start)
                syntax_start, syntax_end = ((start, match.start()) if candidates[0] == prefixes[index]
                                            else (match.end(), end))
                covered[syntax_start:syntax_end] = [True] * (syntax_end-syntax_start)
        if candidates and 'quantity' not in item:
            quantity_gaps.append({'item': index, 'reason': 'ambiguous_or_out_of_grammar_quantity', 'evidence': [span(message, *s) for s in candidates]})
        items.append(item)
        rules.append({'item': index, 'rule_id': 'reference-shape', 'rule_version': RULE_VERSION, 'evidence': [evidence]})
        covered[match.start():match.end()] = [True] * len(match.group())
    unresolved = []
    for match in re.finditer(r'[^\n]+', message):
        start = match.start()
        for index in range(match.start(), match.end()+1):
            if index == match.end() or covered[index]:
                if start < index and message[start:index].strip(' \t\r,;.!?'):
                    unresolved.append(span(message, start, index))
                start = index+1
    result = validate_extraction({'items': items}, message).model_dump(mode='json') if items else None
    years = [{'value': m.group(), 'evidence': [span(message, *m.span())], 'assignment': 'unassigned',
              'rule_id': 'standalone-year-candidate', 'rule_version': RULE_VERSION}
             for m in re.finditer(r'(?<![\w./+\-])(?:19[0-9]{2}|20[0-9]{2})(?![\w/+\-]|\.[0-9])', message)]
    handoff = ['free_text_and_relationships_deferred'] if unresolved else []
    if any(item.get('quantity') is None for item in items):
        handoff.append('numeric_quantity_missing_or_ambiguous')
    if years:
        handoff.append('vehicle_relationships_deferred')
    if uncertain:
        handoff.append('uncertain_reference_candidates')
    return {'parser_version': PARSER_VERSION, 'state': 'extracted' if items else 'pending_no_explicit_items',
            'result': result, 'rules': rules, 'year_candidates': years, 'uncertain_reference_candidates': uncertain,
            'quantity_gaps': quantity_gaps, 'unresolved_fragments': unresolved,
            'handoff_gaps': handoff}
