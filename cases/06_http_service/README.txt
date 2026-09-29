Question
  Do data-transformation savings improve a persistent service?

Work
  POST /aggregate performs case 03. GET /health returns 42. HTTP/1.1 over
  loopback, connection close, no TLS or compression.

BAML path
  HTTP-to-VM entry, native I/O, concurrent roots, allocation and scheduling.

Boundary
  The service experiment is retained as a planned case. Its old driver
  is not used by the rebuilt harness and no new service baseline is published.

Evidence
  The replacement driver must schedule arrivals independently of completions,
  record client dispatch lag, validate responses and retain failures/timeouts.

Claim
  Throughput, CPU per correct response, RSS and latency versus offered load
  under a stated concurrency/resource budget. No product deadline is assumed.

References
  https://github.com/BoundaryML/baml/blob/340b9085d9427e6d458f1c700409ffc88c58b050/baml_language/crates/baml_builtins2/baml_std/baml/ns_http/server.baml
  https://github.com/BoundaryML/baml/blob/340b9085d9427e6d458f1c700409ffc88c58b050/baml_language/crates/bex_engine/src/lib.rs
