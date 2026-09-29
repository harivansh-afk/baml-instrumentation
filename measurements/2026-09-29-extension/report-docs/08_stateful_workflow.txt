Question
  What does a persistent workflow cost while requests allocate short-lived
  objects and a bounded application cache survives between requests?

Work
  Cycle through 128 fixed JSON request strings. Parse nested typed records,
  validate credit/debit/skip tags and integer payloads, run four deterministic
  tool operations, merge their results, update a FIFO cache, then serialize a
  response. Existing keys keep their eviction position. Invalid requests
  return an error response without changing the cache.
  Each tool handles indices congruent to its index modulo four, allocates
  transformed payloads, optionally waits, and returns them for aggregation.
  Fanout 1 runs the same four tools sequentially; fanout 4 runs them together.
  Retention changes the maximum cached keys, not the request stream or tools.
  One invocation processes the declared request batch. State, cursor and digest
  survive subsequent invocations in the same process, including warmup.

BAML path
  Typed JSON decoding, branches, function calls, maps, arrays and serialization;
  allocation, surviving roots and collection; optional futures and timer waits.
  Map deletion preserves insertion order in this release and can cost O(n).

Boundary
  Preparing fixture strings and the empty cache is outside execution. Parsing
  every request, validation, all tools, response serialization, eviction, digest
  updates and the final cache traversal are inside. The host enters the workflow
  once per batch; requests do not individually cross the host API boundary.
  Timer variants include their requested waits. They measure orchestration under
  suspension, not external I/O or CPU parallel scaling. No network or LLM is used.

Evidence
  Correctness runs return every response in full for structural comparison with
  an independent sequential oracle using ordered-dictionary eviction and closed
  payload-sum formulas. Repeated-invocation checks include warmup in that oracle.
  Timing runs consume each response in a cumulative modular digest and count its
  encoded bytes; the final sorted cache summary recomputes surviving payloads.
  A digest is not a proof against collisions. Full transcripts are checked in
  correctness runs, not retained during timing, where they would grow the heap.
  Natural collections must occur inside execution for sustained-GC claims.

Claim
  Cost per fixed request stream with bounded persistent state and these idiomatic
  implementations. Rust owns cached cells and shares immutable request input
  through Arc for spawned tasks; Go, BAML, Python and JavaScript use their native
  object models. Object layouts and allocator policies differ.
  The cache changes hit rates and final traversal work as well as surviving heap.
  This case cannot isolate collector cost. Collections do not establish pauses
  or prove that collection overlapped a suspended tool. Batch/request averages
  are not individual request latencies, p95 or p99. The stream starts empty and
  includes cache filling; no JIT convergence or steady-state claim is made.
  Validation equivalence is checked for the retained corpus; duplicate JSON keys,
  coercion differences, adversarial numeric encodings and Unicode are outside it.

References
  https://github.com/BoundaryML/baml/blob/340b9085d9427e6d458f1c700409ffc88c58b050/baml_language/crates/bex_vm/src/package_baml/json.rs
  https://github.com/BoundaryML/baml/blob/340b9085d9427e6d458f1c700409ffc88c58b050/baml_language/crates/baml_builtins2/baml_std/baml/containers.baml
  https://github.com/BoundaryML/baml/blob/340b9085d9427e6d458f1c700409ffc88c58b050/baml_language/crates/bex_engine/src/bex_work.rs
  https://github.com/BoundaryML/baml/blob/340b9085d9427e6d458f1c700409ffc88c58b050/baml_language/crates/bex_heap/src/gc.rs
  https://go.dev/doc/gc-guide
