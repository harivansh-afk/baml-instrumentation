import json
def prepare(raw): return json.loads(raw)
async def run(state):
    a, b = [], []
    for value in state['values']:
        a.append(value)
        b.append(0)
    n, width = len(a), 1
    while width < n:
        lo = 0
        while lo < n:
            mid, hi = min(lo + width, n), min(lo + 2 * width, n)
            i, j, k = lo, mid, lo
            while k < hi:
                if i < mid and (j >= hi or a[i] <= a[j]):
                    b[k] = a[i]
                    i += 1
                else:
                    b[k] = a[j]
                    j += 1
                k += 1
            lo += 2 * width
        a, b = b, a
        width *= 2
    return json.dumps(a, separators=(',', ':'))
