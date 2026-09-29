"""Diagnostic only: trace the socket-read phase and count server callbacks."""
import asyncio
import contextvars
import importlib.util
import json
from pathlib import Path
import subprocess
import sys

root=Path('/home/rathi/Documents/Git/boundary/instrumentation/.worktrees/stateful-baseline')
out=root/'measurements/http-timeout-diagnostic'
spec=importlib.util.spec_from_file_location('client',root/'machinery/http/client.py');client=importlib.util.module_from_spec(spec);spec.loader.exec_module(client)
context=contextvars.ContextVar('phase')
real_connect=asyncio.open_connection
class Reader:
    def __init__(self, wrapped):self.wrapped=wrapped
    async def readuntil(self,*a,**k):context.get()['phase']='response_headers';return await self.wrapped.readuntil(*a,**k)
    async def readexactly(self,*a,**k):context.get()['phase']='response_body';return await self.wrapped.readexactly(*a,**k)
    async def readline(self,*a,**k):context.get()['phase']='chunk_header_or_trailer';return await self.wrapped.readline(*a,**k)
    async def read(self,*a,**k):context.get()['phase']='body_until_close';return await self.wrapped.read(*a,**k)
async def connect(*a,**k):
    context.get()['phase']='connect'
    r,w=await real_connect(*a,**k)
    return Reader(r),w
original=client.request
async def request(*a,**k):
    state={'phase':'start'};context.set(state)
    result=await original(*a,**k)
    result['last_phase']=state['phase']
    return result
asyncio.open_connection=connect
client.request=request
async def main():
    import os,socket
    os.sched_setaffinity(0,{17,18})
    out.mkdir(exist_ok=False)
    source=(root/'cases/06_http_service/workload.ts').read_text()
    source=source.replace('const server = http.createServer', 'let seen = 0, finished = 0, connections = 0;\nconst server = http.createServer')
    source=source.replace("  if (req.method", "  seen++; res.on('finish', () => { finished++; });\n  if (req.method",1)
    source=source.replace('server.listen(Number(port),host);', "server.on('connection', () => { connections++; });\nserver.listen(Number(port),host);")
    source += '\nconsole.error(JSON.stringify({seen,finished,connections}));\n'
    server_source=out/'server.ts';server_source.write_text(source)
    tools=json.loads((root/'.cache/tools.local.json').read_text())
    for repeat in range(10):
        with socket.socket() as s:s.bind(('127.0.0.1',0));port=s.getsockname()[1]
        server=subprocess.Popen(['taskset','-c','15,16',tools['bun'],str(server_source),str(root/'cases/03_json_aggregate/workload.ts')],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
        try:
            server.stdin.write(f'127.0.0.1:{port}\n');server.stdin.flush()
            if server.stdout.readline().strip()!='@ready':raise RuntimeError('not ready')
            config=dict(port=port,method='GET',path='/hello',body='',expected={'message':'Hello, world!'},rate=500,requests=1500,deadline_s=10,max_inflight=4096)
            for _ in range(10):await request(('127.0.0.1',port),'GET','/hello','',{'message':'Hello, world!'})
            result=await client.run(config)
            server.stdin.write('\n');server.stdin.flush();server.stdin.close();server.wait()
            result['server_counters']=json.loads(server.stderr.read())
            (out/f'{repeat}.json').write_text(json.dumps(result,indent=2)+'\n')
            print(repeat,result['failed'],result['server_counters'],[r for r in result['requests'] if r['status']!='ok'],flush=True)
        finally:
            if server.poll() is None:server.kill();server.wait()
    (out/'README.txt').write_text('Diagnostic only; excluded from baseline charts. Ten fresh Bun node:http processes, 1500 requests at 500/s, ten warmup requests. Client records the last socket-read phase; server counts connection events, handler entries and response finish events. These added diagnostics change the implementation and timing. Source and full client observations are retained.\n')
asyncio.run(main())
