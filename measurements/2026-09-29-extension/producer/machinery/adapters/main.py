import asyncio
import inspect
import gc
import importlib.util
import json
import sys
import time

source, fixture, jobs, warmup = sys.argv[1:]
jobs, warmup = int(jobs), int(warmup)
spec = importlib.util.spec_from_file_location("workload", source)
workload = importlib.util.module_from_spec(spec)
spec.loader.exec_module(workload)
state = workload.prepare(open(fixture).read())


def collections():
    return sum(x["collections"] for x in gc.get_stats())


def emit(value):
    print(json.dumps(value), flush=True)


# Async workloads use one loop for the whole process, including warmup.


async def main():
    emit({"event": "ready"})

    async def call():
        value = workload.run(state)
        return await value if inspect.isawaitable(value) else value

    before = collections()
    for _ in range(warmup):
        await call()
    start_gc = collections()
    wall, cpu = time.perf_counter_ns(), time.process_time_ns()
    for _ in range(jobs):
        result = await call()
    cpu, wall = time.process_time_ns() - cpu, time.perf_counter_ns() - wall
    emit(
        {
            "event": "result",
            "jobs": jobs,
            "execution_wall_ns": wall,
            "execution_cpu_ns": cpu,
            "result": result,
            "gc_execution": collections() - start_gc,
            "gc_warmup": start_gc - before,
            "gc_counter": "cyclic_collections; reference-count reclamation excluded",
        }
    )


asyncio.run(main())
