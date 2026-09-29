import asyncio
import json


def encode(value):
    return json.dumps(value, separators=(",", ":"))


def prepare(raw):
    return dict(
        config=json.loads(raw),
        cache={},
        order=[],
        slot=0,
        cursor=0,
        digest=0,
        response_bytes=0,
    )


async def tool(req, worker, delay):
    cells = []
    for i in range(worker, len(req["items"]), 4):
        item = req["items"][i]
        amount = item["amount"] * {"credit": 1, "debit": -1, "skip": 0}[item["kind"]]
        cells.append(
            {
                "id": i,
                "value": amount,
                "payload": [v + worker + 1 for v in item["payload"]],
            }
        )
    if delay:
        await asyncio.sleep(delay / 1000)
    return cells


def live_check(cells):
    return sum((c["id"] + 1) * (c["value"] + sum(c["payload"])) for c in cells)


async def process(state, raw):
    req = json.loads(raw)
    if (
        not isinstance(req, dict)
        or not isinstance(req.get("key"), str)
        or not req["key"]
        or not req["key"].isascii()
    ):
        raise ValueError()
    if req.get("mode") not in ("replace", "accumulate") or not isinstance(
        req.get("items"), list
    ):
        raise ValueError()
    for item in req["items"]:
        if not isinstance(item, dict) or item.get("kind") not in (
            "credit",
            "debit",
            "skip",
        ):
            raise ValueError()
        if type(item.get("amount")) is not int or not 0 <= item["amount"] <= 1000000:
            raise ValueError()
        if not isinstance(item.get("payload"), list) or any(
            type(v) is not int or not 0 <= v <= 1000000 for v in item["payload"]
        ):
            raise ValueError()
    conf, cache = state["config"], state["cache"]
    if conf["fanout"] == 4:
        parts = await asyncio.gather(
            *(tool(req, i, conf["delay_ms"]) for i in range(4))
        )
    else:
        parts = [await tool(req, i, conf["delay_ms"]) for i in range(4)]
    cells = [cell for part in parts for cell in part]
    total = sum(c["value"] + sum(c["payload"]) for c in cells)
    if req["mode"] == "accumulate" and req["key"] in cache:
        total += cache[req["key"]]["total"]
    evicted = ""
    if conf["retain"]:
        if req["key"] not in cache:
            if len(state["order"]) < conf["retain"]:
                state["order"].append(req["key"])
            else:
                evicted = state["order"][state["slot"]]
                del cache[evicted]
                state["order"][state["slot"]] = req["key"]
                state["slot"] = (state["slot"] + 1) % conf["retain"]
        cache[req["key"]] = dict(total=total, cells=cells)
    return dict(
        seq=state["cursor"],
        ok=True,
        key=req["key"],
        total=total,
        check=live_check(cells),
        evicted=evicted,
    )


async def run(state):
    conf, responses = state["config"], []
    for _ in range(conf["batch"]):
        raw = conf["requests"][state["cursor"] % len(conf["requests"])]
        try:
            response = await process(state, raw)
        except (ValueError, TypeError, KeyError):
            response = dict(
                seq=state["cursor"], ok=False, key="", total=0, check=0, evicted=""
            )
        state["response_bytes"] += len(encode(response))
        for value in (
            state["cursor"],
            int(response["ok"]),
            response["total"],
            response["check"],
            len(state["cache"]),
        ):
            state["digest"] = (state["digest"] * 257 + value) % 1000000007
        if conf["capture"]:
            responses.append(response)
        state["cursor"] += 1
    snapshot = [
        dict(
            key=k, total=e["total"], check=live_check(e["cells"]), count=len(e["cells"])
        )
        for k, e in sorted(state["cache"].items())
    ]
    return encode(
        dict(
            processed=state["cursor"],
            digest=state["digest"],
            response_bytes=state["response_bytes"],
            cache=snapshot,
            responses=responses,
        )
    )
