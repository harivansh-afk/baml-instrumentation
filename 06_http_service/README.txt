Why: resource savings must translate into a responsive persistent service.
Work: POST /aggregate runs the exact 03_json_aggregate implementation; GET /health
returns 42. Five servers use BAML HTTP, Rust Axum/Tokio, Go net/http, Python aiohttp,
and Node http. No TLS/compression, HTTP/1.1, connection close, loopback only.
Measure: scheduled arrivals, correct/late/failed requests, goodput, p50/p95/p99,
server CPU and memory. Latency begins at scheduled arrival, including client lag.
BAML behavior: request-to-VM dispatch, shared heap, native I/O, allocation, GC,
concurrent request roots and telemetry. Library/runtime choices remain in the gap.
Use: primary service goal: less CPU/correct request within latency/memory bounds.
Client CPU and dispatch lag expose load-generator limits. Only >=1000 correct
requests get p99; that threshold alone does not establish statistical confidence.
The supplied 1000ms deadline is experimental, not a product SLA. Sweep load;
match CPU affinity and report actual runtime concurrency before scaling claims.
