import json
import math

def prepare(raw): return raw

def aggregate(raw):
    try:
        rows = json.loads(raw)
        if not isinstance(rows, list) or len(rows) > 1000000: raise ValueError()
        totals = {}
        for row in rows:
            if not isinstance(row, dict): raise ValueError()
            account, amount, active = row['account'], row['amount_cents'], row['active']
            if not isinstance(account, str) or not account.isascii(): raise ValueError()
            if type(active) is not bool or type(amount) not in (int, float): raise ValueError()
            if not math.isfinite(amount) or amount != int(amount) or not 0 <= amount <= 1000000:
                raise ValueError()
            if active: totals[account] = totals.get(account, 0) + int(amount)
        return json.dumps([{'account': k, 'total_cents': totals[k]} for k in sorted(totals)], separators=(',', ':'))
    except (ValueError, KeyError, TypeError, OverflowError):
        return '{"error":"invalid"}'

async def run(state): return aggregate(state)
