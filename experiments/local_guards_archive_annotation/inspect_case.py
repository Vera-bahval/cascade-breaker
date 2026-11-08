#!/usr/bin/env python3
"""Page a single assigned JSON case without interpreting its contents."""
import argparse
import json
from pathlib import Path


def pointer(path):
    return ''.join('/' + str(p).replace('~', '~0').replace('/', '~1') for p in path)


def strings(value, path=()):
    if isinstance(value, str):
        yield pointer(path), value
    elif isinstance(value, dict):
        for key, child in value.items():
            yield from strings(child, path + (key,))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            yield from strings(child, path + (index,))


def page(items, index, char_offset, limit):
    if index < 0 or index > len(items) or char_offset < 0 or limit < 1:
        raise ValueError('invalid index, character offset, or limit')
    if index == len(items):
        if char_offset:
            raise ValueError('character offset beyond end')
        return {'total': len(items), 'index': index, 'fragment': '', 'next_cursor': None}
    # Fragments concatenate into one JSON object, including its paths and complete text.
    encoded = json.dumps(items[index], ensure_ascii=False, separators=(',', ':'))
    if char_offset >= len(encoded) and char_offset != 0:
        raise ValueError('character offset beyond item')
    end = min(len(encoded), char_offset + limit)
    next_cursor = ({'index': index, 'char_offset': end} if end < len(encoded)
                   else {'index': index + 1, 'char_offset': 0} if index + 1 < len(items)
                   else None)
    return {'total': len(items), 'index': index, 'char_offset': char_offset,
            'item_characters': len(encoded), 'fragment': encoded[char_offset:end],
            'next_cursor': next_cursor}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('case', type=Path, help='one assigned case JSON file')
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--overview', action='store_true')
    mode.add_argument('--events', action='store_true')
    mode.add_argument('--texts', action='store_true')
    parser.add_argument('--offset', type=int, default=0, help='first event index (events only)')
    parser.add_argument('--count', type=int, default=20, help='maximum events in selection')
    parser.add_argument('--index', type=int, default=0, help='item index within selection')
    parser.add_argument('--char-offset', type=int, default=0)
    parser.add_argument('--char-limit', type=int, default=4000, help='maximum characters of JSON fragment')
    args = parser.parse_args()
    case = json.loads(args.case.read_text(encoding='utf-8'))
    if not isinstance(case, dict):
        parser.error('case must be a JSON object')
    if args.overview:
        observation = case.get('observation') or {}
        result = {k: observation.get(k) for k in ('facts', 'context', 'proposal')}
        result['evidence_status'] = case.get('evidence_status')
    elif args.events:
        events = (case.get('raw_context') or {}).get('events', [])
        if not isinstance(events, list) or args.offset < 0 or args.count < 1 or args.offset > len(events):
            parser.error('invalid events, offset, or count')
        selected = [{'source_pointer': pointer(('raw_context', 'events', i)), 'event': event}
                    for i, event in enumerate(events[args.offset:args.offset + args.count], args.offset)]
        result = page(selected, args.index, args.char_offset, args.char_limit)
        result.update(total_events=len(events), selection_offset=args.offset,
                      selection_count=len(selected), next_offset=(args.offset + len(selected)
                      if args.offset + len(selected) < len(events) else None))
    else:
        grouped = {}
        for ref, value in strings(case):
            grouped.setdefault(value, []).append(ref)
        items = [{'text': value, 'pointers': refs} for value, refs in grouped.items()]
        result = page(items, args.index, args.char_offset, args.char_limit)
    print(json.dumps(result, ensure_ascii=False))


if __name__ == '__main__':
    main()
