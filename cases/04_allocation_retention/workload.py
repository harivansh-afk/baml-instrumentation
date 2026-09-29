import json
class Cell:
    __slots__ = ('value', 'payload')
    def __init__(self, value, payload): self.value, self.payload = value, payload

def prepare(raw): return json.loads(raw)
async def run(s):
    retained, checksum = [], 0
    for batch in range(s['batches']):
        cells = []
        for i in range(s['width']):
            cell = Cell(batch + i, [i, i+1, i+2, i+3])
            alias = cell
            alias.value += 1
            alias.payload[0] += 1
            cells.append(cell)
        for cell in cells: checksum += cell.value + cell.payload[0]
        if s['retain']:
            if len(retained) < s['retain']: retained.append(cells)
            else: retained[batch % s['retain']] = cells
    live_sum = 0
    for cells in retained:
        for cell in cells: live_sum += cell.value + cell.payload[0]
    return json.dumps([checksum, live_sum], separators=(',', ':'))
