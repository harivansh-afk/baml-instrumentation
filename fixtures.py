"""Deterministic inputs and independent oracles; never timed as workload code."""
import itertools
import json
import math
import random

CASES = ('00_startup', '01_array_traversal', '02_merge_sort', '03_json_aggregate',
         '04_allocation_retention', '05_async_fanout', '06_http_service')


def encode(value):
    return json.dumps(value, separators=(',', ':'), ensure_ascii=True)


def matches(actual, expected):
    """JSON structural equality without Python's True == 1 coercion."""
    if type(actual) is bool or type(expected) is bool:
        return type(actual) is type(expected) and actual == expected
    if isinstance(expected, dict):
        return (isinstance(actual, dict) and actual.keys() == expected.keys()
                and all(matches(actual[k], value) for k, value in expected.items()))
    if isinstance(expected, list):
        return (isinstance(actual, list) and len(actual) == len(expected)
                and all(matches(a, b) for a, b in zip(actual, expected)))
    return actual == expected


def fixture(case, size=1024, variant='iterator', batches=64, retain=4,
            fanout=8, delay_ms=10, seed=1729):
    rng = random.Random(seed)
    if case == '00_startup':
        return encode({'value': 42})
    if case in ('01_array_traversal', '02_merge_sort'):
        values = [rng.randrange(0, 1000000) for _ in range(size)]
        if variant == 'sorted': values.sort()
        if variant == 'reverse': values.sort(reverse=True)
        if variant == 'duplicates': values = [n % 8 for n in values]
        return encode({'values': values, 'variant': variant})
    if case in ('03_json_aggregate', '06_http_service'):
        return encode([{'account': f'account_{rng.randrange(64):04d}',
                        'amount_cents': rng.randrange(1000001),
                        'active': i % 3 != 0} for i in range(size)])
    if case == '04_allocation_retention':
        return encode({'width': size, 'batches': batches, 'retain': retain})
    if case == '05_async_fanout':
        return encode({'payload_size': size, 'fanout': fanout, 'delay_ms': delay_ms})
    raise ValueError(case)


def oracle(case, raw):
    try:
        data = json.loads(raw)
    except ValueError:
        if case in ('03_json_aggregate', '06_http_service'): return {'error': 'invalid'}
        raise
    if case == '00_startup': return data['value']
    if case == '01_array_traversal': return sum(data['values'])
    if case == '02_merge_sort': return sorted(data['values'])
    if case in ('03_json_aggregate', '06_http_service'):
        # Sort/group, rather than copying the implementations' hash aggregation.
        if not isinstance(data, list) or len(data) > 1000000: return {'error': 'invalid'}
        for row in data:
            if not isinstance(row, dict): return {'error': 'invalid'}
            a, n, active = (row.get(k) for k in ('account', 'amount_cents', 'active'))
            if (not isinstance(a, str) or not a.isascii() or type(active) is not bool
                    or type(n) not in (int, float) or not math.isfinite(n)
                    or n != int(n) or not 0 <= n <= 1000000):
                return {'error': 'invalid'}
        active = sorted((r for r in data if r['active']), key=lambda r: r['account'])
        return [{'account': key, 'total_cents': sum(int(r['amount_cents']) for r in rows)}
                for key, rows in itertools.groupby(active, key=lambda r: r['account'])]
    if case == '04_allocation_retention':
        w, b = data['width'], data['batches']
        kept = min(b, data['retain'])
        # Every cell contributes batch + 2*i + 2 after the two alias writes.
        checksum = w * b * (b - 1) // 2 + b * w * (w + 1)
        live = w * kept * (2 * b - kept - 1) // 2 + kept * w * (w + 1)
        return [checksum, live]
    if case == '05_async_fanout':
        n = data['payload_size']
        return [n * i + n * (n - 1) // 2 for i in range(data['fanout'])]
    raise ValueError(case)


def checks(case):
    yield 'default', fixture(case, size=16, batches=8, retain=2, delay_ms=2)
    if case in ('01_array_traversal', '02_merge_sort'):
        variants = ('iterator', 'indexed', 'build') if case == '01_array_traversal' else ('random', 'sorted', 'reverse', 'duplicates')
        for size in (0, 1, 2, 17, 257):
            for variant in variants: yield f'{size}-{variant}', fixture(case, size=size, variant=variant)
    if case in ('03_json_aggregate', '06_http_service'):
        examples = [[], [{'account': 'a', 'amount_cents': 1.0, 'active': True}],
                    [{'account': 'a', 'amount_cents': 1000000, 'active': True, 'ignored': 5}],
                    [{'account': '', 'amount_cents': 0, 'active': True}],
                    [{'account': '__proto__', 'amount_cents': 8, 'active': True}],
                    None, {}, [None], [False]]
        for field, values in {'account': [None, 4, 'é'], 'amount_cents': [True, '1', -1, 1.5, 1000001, None], 'active': [None, 1, 'true']}.items():
            for value in values:
                row = {'account': 'a', 'amount_cents': 1, 'active': True}
                row[field] = value
                examples.append([row])
            row = {'account': 'a', 'amount_cents': 1, 'active': True}
            del row[field]
            examples.append([row])
        for i, example in enumerate(examples): yield f'validation-{i}', encode(example)
        yield 'syntax-error', '[{"account":'
        yield 'trailing-document', '[] []'
        yield 'exponent-integer', '[{"account":"a","amount_cents":1e2,"active":true}]'
    if case == '04_allocation_retention':
        for width, batches, retain in ((0, 0, 0), (0, 4, 2), (5, 9, 0), (5, 9, 1), (5, 9, 9), (5, 9, 20)):
            yield f'{width}-{batches}-{retain}', fixture(case, size=width, batches=batches, retain=retain)
    if case == '05_async_fanout':
        for fanout, size in ((0, 4), (1, 0), (1, 7), (32, 8)):
            yield f'{fanout}-{size}', fixture(case, fanout=fanout, size=size, delay_ms=2)
