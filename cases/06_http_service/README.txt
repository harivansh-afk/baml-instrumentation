HTTP services

Question
  What does a persistent JSON HTTP service deliver at a fixed offered load?
Work
  GET /hello returns {"message":"Hello, world!"}. POST /aggregate runs case 03
  on 64 records. Each POST in a trial uses the same seeded document.
  Every measured response is checked against the independent
  oracle. Separate correctness runs include malformed JSON and schema errors.
Boundary
  HTTP/1.1 over loopback, a new connection per request, no TLS or compression.
  Servers use CPUs 15 and 16; the Python load client uses CPUs 17 and 18.
  Five fresh processes per configuration and load, ten sequential warmup
  requests, then three seconds of independently scheduled arrivals. Arrival
  rates are 100/500 requests/s for hello and 50/200 for aggregation.
BAML path
  Native HTTP I/O, one VM root per callback, JSON parsing and serialization,
  VM aggregation, allocation and scheduling. Each process also has a main root.
Evidence
  Each request records scheduled arrival, actual dispatch and body completion.
  Scheduled-to-body latency includes driver lag; dispatch-to-body latency is
  also retained. Nearest-rank p50/p95/p99 use successful responses within each
  process; unsuccessful requests are counted separately. Trials with request
  failures remain in throughput, CPU and memory comparisons. Invalid driver
  schedules are excluded from performance bars and counted in the tables.
  The report shows medians/ranges of those percentiles, never a pooled percentile.
  A trial violates the schedule check if p99 client dispatch lag exceeds 10 ms.
  The 10-second per-request deadline and 4096 in-flight cap retain failures;
  they do not silently lower the arrival rate. Valid BTEL recordings require
  one successful root per request plus main, exact handler counts in medium/high,
  exact handler completion spans in high, and zero delivery loss at every level.
Claim
  Achieved throughput at these loads, latency, whole-server CPU and peak RSS.
  Throughput divides correct responses by the longer of the planned load window
  and time to the last response or request deadline. It is not a maximum-capacity measurement.
  CPU/RSS include startup, warmup and shutdown; the load client is excluded.
  BAML GC counts cover the service lifetime, not an isolated load phase. The
  HTTP suite makes no cross-runtime GC claim and does not measure GC pauses.
  The stacks differ: BAML native HTTP, Rust axum/Tokio, Go net/http, Python
  aiohttp, Node/Bun node:http. A difference cannot be attributed only to a compiler.
  Rust/Python/Node/Bun use one event loop; two permitted CPUs do not mean two
  parallel application workers. BAML and Go are configured for two workers.
References
  https://github.com/BoundaryML/baml/blob/340b9085d9427e6d458f1c700409ffc88c58b050/baml_language/crates/baml_builtins2/baml_std/baml/ns_http/server.baml
  https://github.com/BoundaryML/baml/blob/340b9085d9427e6d458f1c700409ffc88c58b050/baml_language/crates/bex_engine/src/lib.rs
  https://docs.rs/axum/0.8.9/axum/serve/index.html
  https://docs.aiohttp.org/en/v3.14.3/web.html
  https://pkg.go.dev/net/http
  https://nodejs.org/api/http.html
