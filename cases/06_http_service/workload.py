import asyncio
import importlib.util
import sys
from aiohttp import web
spec = importlib.util.spec_from_file_location('aggregate', sys.argv[1])
aggregate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(aggregate)
async def health(request): return web.Response(text='42', content_type='application/json')
async def handle(request):
    body = aggregate.aggregate(await request.text())
    return web.Response(text=body, status=400 if body == '{"error":"invalid"}' else 200, content_type='application/json')
async def main():
    host, port = sys.stdin.readline().strip().split(':')
    app = web.Application(client_max_size=64*1024*1024)
    app.router.add_get('/health',health)
    app.router.add_post('/aggregate',handle)
    runner = web.AppRunner(app, access_log=None)
    await runner.setup()
    await web.TCPSite(runner,host,int(port)).start()
    print('@ready',flush=True)
    await asyncio.to_thread(sys.stdin.readline)
    await runner.cleanup()
asyncio.run(main())
