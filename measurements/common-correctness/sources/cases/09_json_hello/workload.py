import json
def prepare(raw): return json.loads(raw)
async def run(state): return json.dumps(state, separators=(',', ':'), ensure_ascii=False)
