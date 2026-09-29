import json


def prepare(raw):
    return json.loads(raw)


async def run(s):
    a = []
    for v in s["values"]:
        a.append(v)
    lows, highs, top = [0], [len(a) - 1], 1
    while top:
        top -= 1
        lo, hi = lows[top], highs[top]
        if lo >= hi:
            continue
        pivot = a[lo + (hi - lo) // 2]
        lt, i, gt = lo, lo, hi
        while i <= gt:
            if a[i] < pivot:
                a[lt], a[i] = a[i], a[lt]
                lt += 1
                i += 1
            elif a[i] > pivot:
                a[gt], a[i] = a[i], a[gt]
                gt -= 1
            else:
                i += 1
        if top == len(lows):
            lows.append(lo)
            highs.append(lt - 1)
        else:
            lows[top] = lo
            highs[top] = lt - 1
        top += 1
        if top == len(lows):
            lows.append(gt + 1)
            highs.append(hi)
        else:
            lows[top] = gt + 1
            highs[top] = hi
        top += 1
    return json.dumps(a, separators=(",", ":"))
