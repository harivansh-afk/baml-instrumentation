package main

import (
	"encoding/json"
	"fmt"
	"os"
	"runtime"
	"strconv"
	"syscall"
	"time"
)

func cpuNS() int64 {
	var r syscall.Rusage
	if e := syscall.Getrusage(syscall.RUSAGE_SELF, &r); e != nil {
		panic(e)
	}
	return (r.Utime.Sec+r.Stime.Sec)*1e9 + (r.Utime.Usec+r.Stime.Usec)*1000
}
func emit(v any) {
	b, e := json.Marshal(v)
	if e != nil {
		panic(e)
	}
	fmt.Println(string(b))
}
func main() {
	raw, e := os.ReadFile(os.Args[1])
	if e != nil {
		panic(e)
	}
	jobs, e := strconv.Atoi(os.Args[2])
	if e != nil || jobs < 1 {
		panic("invalid jobs")
	}
	warm, e := strconv.Atoi(os.Args[3])
	if e != nil {
		panic(e)
	}
	state := prepare(string(raw))
	emit(map[string]any{"event": "ready"})
	var a, b, c runtime.MemStats
	runtime.ReadMemStats(&a)
	for i := 0; i < warm; i++ {
		run(state)
	}
	runtime.ReadMemStats(&b)
	start := time.Now()
	cpu := cpuNS()
	var result string
	for i := 0; i < jobs; i++ {
		result = run(state)
	}
	cpu = cpuNS() - cpu
	wall := time.Since(start).Nanoseconds()
	runtime.ReadMemStats(&c)
	emit(map[string]any{"event": "result", "jobs": jobs, "result": result, "execution_wall_ns": wall, "execution_cpu_ns": cpu, "gc_execution": c.NumGC - b.NumGC, "gc_warmup": b.NumGC - a.NumGC, "gc_counter": "completed_gc_cycles", "allocated_bytes": c.TotalAlloc - b.TotalAlloc, "heap_alloc_bytes": c.HeapAlloc, "gc_pause_ns": c.PauseTotalNs - b.PauseTotalNs})
}
