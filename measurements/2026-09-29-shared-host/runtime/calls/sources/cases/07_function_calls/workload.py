import json


def prepare(raw):
    return json.loads(raw)


def leaf(value):
    return value + 1


async def run(state):
    value = state["seed"]
    for _ in range(state["count"]):
        value = leaf(value)
    return str(value)
