BAML baseline board

Drawing with the original mind map and the new baseline section:
  https://draw.harivan.sh/local#json=83414f7779a548723c30,PtRNOaT8QZ0CPclFzYZvzA
This is a new immutable snapshot; the input share link is unchanged.

Open index.html for 16 static panels. Import baseline-section.excalidraw to use
the same panels in a drawing. Each chart also has PNG and SVG copies.

Regenerate from the instrumentation root:
  uv run machinery/board_report.py

The generator verifies every source hash in ../baseline.json and requires all
expected trials for each displayed configuration to be valid. It reads existing
observations; it neither runs workloads nor changes the historical collections.
chart-data.json contains exact observations, selections, units and source hashes.

Reference identity
  Measured 2026-09-29 on shared Linux aarch64; CPUs 15 and 16, two workers where
  supported. This is not an accepted isolated-host baseline.
  BAML 0.20.2-nightly.20260927.a, source 340b9085d9427e6d458f1c700409ffc88c58b050.
  Rust 1.98.1; Go 1.27.1; CPython 3.14.7; Node 26.10.0; Bun 1.4.2.
  Version manifest: ../../2026-09-29-shared-host/producer/machinery/tools.json
  BAML release: https://github.com/BoundaryML/baml/releases/tag/baml-language-0.20.2-nightly.20260927.a

Panel order
  01: absolute BAML scorecard.
  02-03: five-workload execution ratio versus Node, for every BTEL level.
  04-08: absolute workload times, BAML off/high and five language references.
  09-11: CPU, peak RSS with retention, and telemetry time/bytes/drain.
  12-13: native executable footprint, build wall/CPU/RSS, invocation time.
  14-15: fixed-load HTTP and concurrency with waiting.
  16: comparison rules for MIR-to-Rust and later backends.

Runtime comparison
  The fixed suite is array-indexed, merge-random, json-aggregate,
  workflow-retain-4 and generate-sort. It uses one declared input size each.
  Each trial is a process batch average. Divide workflow batches by 768 requests;
  other cases by jobs. Medians describe these averages, not individual latencies.
  The single runtime summary is the equal-weight geometric mean of five ratios
  to Node. Do not average milliseconds across unlike amounts of work or combine
  execution, compilation, memory and size into one score. Keep per-case results.
  Timing includes the adapter and result serialization. Fixed finite warmups
  are not evidence of V8 steady state; Node GC coverage remains unknown.
  BAML GC occurred in workflow and allocation cases, not the other four suite
  cases. Whole-process peak RSS includes the measurement probe and diagnostics.
  Rust is a handwritten comparator, not generated BAML-to-Rust code.

Artifact and build comparison
  Pack rows use the published musl host, already built, with bytecode appended.
  Source-built BEX probe timing and published packed-executable timing are
  different boundaries. A candidate needs both execution and deployable-artifact
  measurements, with compiler/linker flags, cache policy and dependency scope.
  MIR-to-Rust builds must include Rust compilation and linking. Track runtime
  bootstrap separately. Packed workflow invocation uses 8 requests of 64 items,
  retain 2 and sequential 10 ms tools; its input differs from the runtime suite.
  Candidate executable size must list required external
  runtime files; language source bytes are not equivalent deployment footprints.
  Current WASM size and removal of dynamic-compilation support are unmeasured.

HTTP and reliability
  All 45 displayed aggregate-200 trials pass status, scheduling and telemetry
  validation, with zero failed requests. Other scenarios retain their failures:
  see ../../2026-09-29-http/FINDINGS.txt. The BAML HTTP telemetry gate is not fully
  passed across the collection. A three-second fixed-rate test is not sustained
  capacity. Tool concurrency includes timer waits, not CPU-parallel scaling.

Why these KPIs
  The supplied sibling notes bamlrust.md, call_notes.md and hari_notes.md ask for
  execution against V8 with telemetry on, wall and CPU time, peak RSS, binary
  size, realistic workloads and HTTP req/s with time-window context. bamlrust.md
  also calls out LTO, WASM footprint and reflect.Package.compile dependencies.
  Their 20+ MB WASM and roughly 500 KB Mac prototype statements are not measured
  results from this Linux collection and are not plotted as baseline values.
  Notes are design motivation; charts derive only from the frozen observations.

Measurement contracts and case rationale
  ../README.txt
  ../../2026-09-29-shared-host/protocol.json
  ../../2026-09-29-extension/protocol.json
  ../../2026-09-29-http/protocol.json
  ../../../cases/01_array_traversal/README.txt
  ../../../cases/02_merge_sort/README.txt
  ../../../cases/03_json_aggregate/README.txt
  ../../../cases/04_allocation_retention/README.txt
  ../../../cases/08_stateful_workflow/README.txt
  ../../../cases/11_generate_sort/README.txt

Use a contemporaneous VM control alongside each backend candidate. Display
absolute values and 100 * candidate median / control median for each cost.
Keep the historical reference separate. Do not award a whole-suite score to a
backend that supports only part of the required semantics.
