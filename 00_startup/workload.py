import json
def prepare(raw): return json.loads(raw)
async def run(state): return str(state['value'])
