"""Open-loop HTTP/1.1 requests; each observation retains its scheduled arrival."""
import argparse
import asyncio
import json
import math
import os
from pathlib import Path
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from fixtures import matches


def percentile(values, fraction):
    return sorted(values)[max(0, math.ceil(len(values) * fraction) - 1)] if values else None


async def request(address, method, path, body, expected, expected_status=200, deadline=10):
    writer = None
    started = time.monotonic_ns()
    result = {"dispatch_ns": started, "status": "error"}
    try:
        async with asyncio.timeout(deadline):
            reader, writer = await asyncio.open_connection(*address)
            encoded = body.encode()
            writer.write((f"{method} {path} HTTP/1.1\r\nHost: {address[0]}:{address[1]}\r\nConnection: close\r\nContent-Type: application/json\r\nContent-Length: {len(encoded)}\r\n\r\n").encode() + encoded)
            await writer.drain()
            header = (await reader.readuntil(b"\r\n\r\n")).decode('latin1').split('\r\n')
            status = int(header[0].split()[1])
            fields = dict(line.lower().split(':', 1) for line in header[1:] if ':' in line)
            if 'chunked' in fields.get('transfer-encoding', ''):
                chunks = []
                while True:
                    size = int((await reader.readline()).split(b';')[0], 16)
                    if not size:
                        while await reader.readline() != b'\r\n': pass
                        break
                    chunks.append(await reader.readexactly(size))
                    if await reader.readexactly(2) != b'\r\n': raise ValueError('invalid chunk')
                response = b''.join(chunks)
            elif 'content-length' in fields:
                response = await reader.readexactly(int(fields['content-length']))
            else:
                response = await reader.read()
            # Stop timing before JSON validation and client-side cleanup.
            result['completed_ns'] = time.monotonic_ns()
            result.update(http_status=status, response_bytes=len(response))
            result['status'] = 'ok' if status == expected_status and matches(json.loads(response), expected) and 'application/json' in fields.get('content-type', '') else 'wrong_response'
    except Exception as error:
        result.update(error=f'{type(error).__name__}: {error}')
    finally:
        result.setdefault('completed_ns', time.monotonic_ns())
        if writer:
            writer.close()
            try: await writer.wait_closed()
            except (OSError, RuntimeError): pass
    return result


async def run(config):
    address = ('127.0.0.1', config['port'])
    if 'checks' in config:
        return [await request(address, **check) for check in config['checks']]
    start = time.monotonic_ns() + 50_000_000
    records = []
    pending = set()
    async def issue(index, scheduled):
        row = await request(address, config['method'], config['path'], config['body'], config['expected'], deadline=config['deadline_s'])
        row.update(index=index, scheduled_ns=scheduled, lag_ns=max(0, row['dispatch_ns']-scheduled), latency_ns=max(0, row['completed_ns']-scheduled), service_ns=row['completed_ns']-row['dispatch_ns'])
        records.append(row)
    for i in range(config['requests']):
        scheduled = start + round(i * 1e9 / config['rate'])
        await asyncio.sleep(max(0, (scheduled-time.monotonic_ns())/1e9))
        if len(pending) >= config['max_inflight']:
            # Never silently drop a scheduled request or delay future arrivals.
            records.append(dict(index=i, scheduled_ns=scheduled, status='client_capacity_rejected'))
            continue
        task = asyncio.create_task(issue(i, scheduled))
        pending.add(task)
        task.add_done_callback(pending.discard)
    if pending: await asyncio.gather(*pending)
    end = max(start + round(config['requests']*1e9/config['rate']), max((r.get('completed_ns',start) for r in records), default=start))
    good = [r for r in records if r['status']=='ok']
    latency = [r['latency_ns'] for r in good]
    lag = [r['lag_ns'] for r in records if 'lag_ns' in r]
    service = [r['service_ns'] for r in good]
    return dict(requests=sorted(records,key=lambda r:r['index']), started_ns=start, ended_ns=end, completed=len(good), failed=len(records)-len(good), duration_ns=end-start, throughput=len(good)*1e9/(end-start), latency_p50_ns=percentile(latency,.50), latency_p95_ns=percentile(latency,.95), latency_p99_ns=percentile(latency,.99), service_p95_ns=percentile(service,.95), client_lag_p99_ns=percentile(lag,.99))


def main():
    p=argparse.ArgumentParser();p.add_argument('config',type=Path);p.add_argument('output',type=Path);p.add_argument('--cpus',default='17,18');a=p.parse_args()
    os.sched_setaffinity(0,{int(c) for c in a.cpus.split(',')})
    result=asyncio.run(run(json.loads(a.config.read_text())))
    a.output.write_text(json.dumps(result,indent=2)+'\n')

if __name__=='__main__':main()
