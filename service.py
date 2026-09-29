"""Fixed-arrival HTTP/1.1 load; every response is checked, including failures."""
import asyncio
import json
import math
import resource
import socket
import time

from runner import Child
from fixtures import matches


def percentile(values, p):
    return sorted(values)[max(0, math.ceil(p * len(values))-1)] if values else None


async def request(port, raw):
    reader, writer = await asyncio.open_connection('127.0.0.1', port)
    try:
        body = raw.encode()
        writer.write((f'POST /aggregate HTTP/1.1\r\nHost: 127.0.0.1\r\n'
                      f'Content-Type: application/json\r\nContent-Length: {len(body)}\r\n'
                      'Connection: close\r\n\r\n').encode()+body)
        await writer.drain()
        status = int((await reader.readline()).split()[1])
        headers = {}
        while True:
            line = await reader.readline()
            if line == b'\r\n': break
            if not line: raise RuntimeError('incomplete HTTP header')
            key, value = line.decode().split(':',1)
            headers[key.lower()] = value.strip()
        if headers.get('transfer-encoding') == 'chunked':
            chunks = []
            while True:
                size = int((await reader.readline()).split(b';')[0],16)
                if size == 0: break
                chunks.append(await reader.readexactly(size))
                if await reader.readexactly(2) != b'\r\n': raise RuntimeError('invalid chunk')
            payload = b''.join(chunks)
        elif 'content-length' in headers:
            payload = await reader.readexactly(int(headers['content-length']))
        else: payload = await reader.read()
        return status,payload
    finally:
        writer.close()
        await writer.wait_closed()


async def load(child, port, raw, expected, args):
    expected_status = 400 if expected == {'error':'invalid'} else 200
    # Same ready-to-correct-response warmup for every implementation.
    for _ in range(args.warmup):
        status,payload = await asyncio.wait_for(request(port,raw),10)
        if status != expected_status or not matches(json.loads(payload), expected): raise AssertionError('HTTP warmup mismatch')
    client_before = resource.getrusage(resource.RUSAGE_SELF)
    cpu_before = child.sample()
    start = time.perf_counter()
    stop_sampling = asyncio.Event()

    async def sample():
        while not stop_sampling.is_set():
            child.sample()
            await asyncio.sleep(0.005)

    async def arrival(index):
        scheduled = start+index/args.rate
        await asyncio.sleep(max(0,scheduled-time.perf_counter()))
        dispatched = time.perf_counter()
        entry = {'index':index,'scheduled_s':scheduled-start,'dispatch_lag_s':dispatched-scheduled}
        try:
            status,payload = await asyncio.wait_for(request(port,raw),10)
            completed = time.perf_counter()
            correct = status == expected_status and matches(json.loads(payload), expected)
            entry.update(status=status,correct=correct,latency_s=completed-scheduled,
                         service_observed_s=completed-dispatched,
                         within_deadline=completed-scheduled <= args.deadline_ms/1000)
        except Exception as error:
            entry.update(correct=False,within_deadline=False,error=str(error),latency_s=time.perf_counter()-scheduled)
        return entry

    sampler = asyncio.create_task(sample())
    entries = await asyncio.gather(*(arrival(i) for i in range(args.requests)))
    await asyncio.sleep(max(0,start+args.requests/args.rate-time.perf_counter()))
    elapsed = time.perf_counter()-start
    stop_sampling.set()
    await sampler
    cpu_after = child.sample()
    client_after = resource.getrusage(resource.RUSAGE_SELF)
    good = [e for e in entries if e['correct'] and e['within_deadline']]
    correct = [e for e in entries if e['correct']]
    latency = [e['latency_s']*1000 for e in correct]
    return {'offered':args.requests,'offered_rate_rps':args.rate,'observed_window_s':elapsed,
            'correct':len(correct),'failed_or_incorrect':len(entries)-len(correct),
            'late_correct':len(correct)-len(good),'deadline_ms':args.deadline_ms,
            'goodput_rps':len(good)/elapsed,'correct_rps':len(correct)/elapsed,
            'p50_ms':percentile(latency,0.50),'p95_ms':percentile(latency,0.95),
            'p99_ms':percentile(latency,0.99) if len(latency) >= 1000 else None,
            'cpu_s_ticks':cpu_after['cpu_s']-cpu_before['cpu_s'],
            'client_cpu_s':client_after.ru_utime+client_after.ru_stime-client_before.ru_utime-client_before.ru_stime,
            'max_dispatch_lag_ms':max(e['dispatch_lag_s'] for e in entries)*1000,
            'requests':entries}


def measure(record,raw,expected,mode,directory,args):
    # Reserve an uncommon loopback port; fail on a bind race rather than reuse a service.
    with socket.socket() as reservation:
        reservation.bind(('127.0.0.1',0))
        port = reservation.getsockname()[1]
    child = Child(record,f'127.0.0.1:{port}',mode,directory)
    try:
        ready = child.ready()
        data = asyncio.run(load(child,port,raw,expected,args))
        invocation = child.finish()
        if args.action == 'verify' and data['failed_or_incorrect']:
            raise AssertionError(f"{data['failed_or_incorrect']} incorrect HTTP responses")
        return {'ready_s':ready,'http':data,'invocation':invocation}
    except BaseException:
        child.abort()
        raise
