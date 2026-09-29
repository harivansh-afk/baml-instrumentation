import asyncio
import json
def prepare(raw): return json.loads(raw)
async def child(i, s):
    payload = []
    for j in range(s['payload_size']): payload.append(i+j)
    await asyncio.sleep(s['delay_ms']/1000)
    total = 0
    for value in payload: total += value
    return total
async def run(s):
    tasks = [asyncio.create_task(child(i,s)) for i in range(s['fanout'])]
    results = [await task for task in tasks]
    return json.dumps(results, separators=(',', ':'))
