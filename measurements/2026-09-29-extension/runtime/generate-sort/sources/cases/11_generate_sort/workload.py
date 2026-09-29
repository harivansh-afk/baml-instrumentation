import json


def prepare(raw):
    return json.loads(raw)


async def run(s):
    a = []
    v = s["seed"]
    for _ in range(s["count"]):
        v = v * 48271 % 1000000007
        a.append(v)
    a.sort()
    return json.dumps(a, separators=(",", ":"))
