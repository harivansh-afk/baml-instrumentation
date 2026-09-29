import json

def prepare(raw):
    return json.loads(raw)

async def run(state):
    values = state['values']
    if state['variant'] == 'build':
        values = []
        i = 0
        while i < len(state['values']):
            values.append(state['values'][i])
            i += 1
    total = 0
    if state['variant'] == 'indexed':
        i = 0
        while i < len(values):
            total += values[i]
            i += 1
    else:
        for value in values:
            total += value
    return str(total)
