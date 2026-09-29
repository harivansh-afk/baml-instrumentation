Why: agent programs suspend with live state and resume many small tasks.
Work: start --fanout children, each builds --size integers, suspends for --delay-ms,
then sums the retained array; join in launch order and check every child's result.
Measure: CPU/workflow, elapsed time and memory while varying fanout and payload.
BAML behavior: spawn/future dispatch, suspension roots, resumption, scheduling
and natural GC with arrays live across await. No real provider/network is involved.
Rust uses Tokio tasks, Go goroutines, Python asyncio, TS promises on Node/V8.
Use: prevent CPU-loop improvements from regressing orchestration. This measures
concurrent waiting, not parallel CPU throughput. Timer granularity differs;
use 10/50 ms delays, and treat delay=0 as a distinct scheduler experiment.
Cancellation and forced-GC correctness live in correctness.baml, outside timing.
