import asyncio
import importlib.util
import sys

spec = importlib.util.spec_from_file_location("workload", sys.argv[1])
workload = importlib.util.module_from_spec(spec)
spec.loader.exec_module(workload)


async def main():
    state = workload.prepare(sys.stdin.readline().removesuffix('\n'))
    print("@ready", flush=True)
    while count := int(sys.stdin.readline()):
        for _ in range(count):
            print("@result " + await workload.run(state), flush=True)
        print("@done", flush=True)


asyncio.run(main())
