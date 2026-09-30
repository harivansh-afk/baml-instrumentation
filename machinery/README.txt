Run on Linux aarch64. Python commands use uv; benchmark Python is separately pinned.

Visual report
  Open measurements/index.html directly in a browser. It combines separately
  identified collections without pooling samples, and includes HTTP results.
  Rebuild with the command in measurements/README.txt.
  html_report.py pins matplotlib 3.10.6 and embeds static SVG charts and downloads.
  charts/ contains standalone SVGs for reuse. No JavaScript, server or network
  is needed to view the HTML; each chart has a labelled, zero-based linear axis.
  Bars show medians; whiskers show observed min-max, not confidence intervals.
  Tables retain sample counts and failures. Metric units and deployment scopes
  stay separate; unavailable counters are never replaced with zero.
  Per-workload charts compare languages with BAML off and compare BAML's four
  telemetry modes separately. Sorting has additional algorithm-pair charts.
  The overview is a table of individual workloads, not an aggregate winner score.

Stateful and service cases
  08_stateful_workflow keeps cache, request cursor and digest across invocations.
  Its oracle applies both warmup and measured calls; preparation resets a fresh
  process only. Trace fixtures check each response and surviving cached payloads.
  extension-protocol.json freezes the added batch cases, including JSON hello,
  quicksort, generated-number sorting and four distributions for merge sort.
  HTTP uses separate lifecycle machinery and protocol under machinery/http/;
  read http/README.txt for commands and cases/06_http_service/README.txt for scope.

Setup
  uv run --no-project machinery/setup.py
  Install Rust 1.98.1 with rustup if it is absent. Setup verifies download hashes.
  tools.json pins releases checked on 2026-09-29; setup never resolves "latest".
  Update pins deliberately, then create a new measurement run.
  BAML 0.20.2-nightly.20260927.a; Rust 1.98.1; Go 1.27.1;
  CPython 3.14.7; Node 26.10.0; Bun 1.4.2. URLs and archive hashes are in tools.json.

BAML host
  uv run --no-project machinery/build_baml.py --checkout /absolute/path/to/baml
  Build adapters/baml.rs as examples/instrumentation.rs in bex_engine at the
  selected BAML revision. build_baml.py prepares an isolated source worktree.
  The host uses existing compiler/engine/heap/recording APIs; it does not change
  collector policy. Its binary hash and build profile belong to every artifact.
  The published CLI and the source-built measurement host are distinct artifacts.
  Build timeout is disabled by default; --timeout sets seconds. A timeout is not a
  successful build. Completed hosts are retained separately by revision/profile.

Build
  uv run --no-project machinery/run.py build --baml-host /absolute/path/to/instrumentation
  Build all selected languages before measuring them. Compiler downloads and
  dependency fetching happen outside the timer. Rust and Go use empty build
  caches, including dependency compilation; BAML compiles source to Program
  bytecode. These targets have different semantics and remain labelled.
  Python/Node/Bun have no separate artifact build here: compile time is unavailable,
  not zero. Parsing and JIT work occur during startup/warmup/execution as applicable.

Check
  uv run --no-project -m unittest discover -s machinery -p 'test_*.py' -v
  uv run --no-project machinery/run.py verify --output measurements/<new-run>
  Until the BAML host is built, add --languages rust go python node bun to build
  and verify. machinery/VALIDATION.txt states the checks actually completed.
  Independent input/output checks precede performance runs. A checksum or last
  result alone cannot establish algorithm correctness for all inputs.

Pilot
  uv run --no-project machinery/run.py run --cases 04_allocation_retention \
    --size 4096 --batches 128 --retain 4 --jobs 8 --warmup 1 --trials 5 \
    --cpus 15,16 --workers 2 --output measurements/<new-run>
  These are exploratory settings, not an accepted statistical protocol. Use pilot
  evidence to freeze sizes, warmup, work counts and trial counts before comparison.
  Run one trial at a time on the same host. CPU affinity permits placement; it
  does not reserve cores or prevent other services from competing for resources.
  Every process observation saves host.json with CPU ticks, scheduler pressure,
  load and selected-core frequency settings before/after the child. These readings
  document interference; they neither eliminate it nor prove exclusive execution.

Boundaries
  Execution wall/CPU: inside the child, around repeated run(state) calls.
  Includes function entry, runtime work, allocation/reclamation and the case's
  result-string serialization. Excludes stdout, controller checks and sampling.
  Adapters keep warmup and work in one process. BAML reuses one engine. Rust uses
  one current-thread Tokio runtime; BAML uses the declared Tokio worker count.
  Python/JS adapters await each call; their entry overhead remains in the result.
  Small jobs need a workload-size sweep to establish the measurement floor.
  BAML takes a function-ID metadata snapshot after execution for recording checks.
  metadata_ns reports its wall time. Whole-process CPU/RSS includes this diagnostic;
  execution timing and the published packed-executable path exclude it.

  Process wall: native observer fork -> child reaped, including actual shutdown.
  Process CPU: wait4 user + system time, including threads and waited descendants.
  Peak RSS: Linux wait4 high-water value; for process trees this is not summed
  simultaneous tree memory. Runtime adapters here execute in one process.
  RSS samples: best-effort /proc reads every 10 ms; samples can miss short peaks.
  Launch-to-ready: controller launch -> received marker, including observer/pipe
  overhead. Do not call it exact runtime initialization time.

  Compile wall/CPU includes the compiler process tree. Dependency fetching is
  excluded. Clean build means empty compilation caches, not cold filesystem caches.
  Build metrics are one observation per artifact; runtime repeats do not create
  additional compile samples. Incremental compile measurements are not implemented.

Coverage
  Read runtime counters outside each timed batch in the same measured build.
  BAML reports full collections in warmup, execution and drain separately.
  Go reports completed GC cycles, cumulative allocation bytes and pause totals.
  Python reports cyclic collections; reference-count reclamation is not counted.
  Rust has no tracing collector. Node/Bun GC coverage is currently unknown.
  Unknown, not observed and not applicable remain distinct values.
  Counter deltas bracket the batch. A concurrent collection can cross a clock
  boundary; these counts establish observed activity, not precise pause duration.

  Sustained-GC claims require repeated natural collections during execution;
  shutdown-only collections do not qualify. Retain each insufficient-coverage run.
  A short process may legitimately finish without collecting. Do not extrapolate
  that result to a persistent service. Never force GC in the default comparison.

  For detailed BAML pause attribution, separately build with gc_profiling and
  configure a bex_gc tracing subscriber. Those diagnostics are not baseline timing.
  park_wait is waiting for exclusive access; pause is exclusive heap access;
  post_gc happens after release. Total includes these intervals; do not sum twice.

BTEL
  Each trial is a fresh process: BAML_TELEMETRY is read when the engine is created.
  off disables globally; low/medium/high select automatic policies. Destination
  is independently none/local. Cloud delivery is outside this first harness.
  Local files use the release defaults and no fsync durability guarantee.
  After measured shutdown, a separate reader validates files/references, root
  completions and exact run() totals (zero at low; warmup + jobs at medium/high).
  High additionally requires one run() span per call. This release does not emit
  RecordingEnd or function names; resolve IDs using the measured engine's metadata.
  This checks these ordinary functions, not LLM value capture or every event type.
  A failed output, delivery, decode or completion check remains a failed trial.

Size
  artifact_bytes means bytecode, native benchmark executable or script + adapter,
  as labelled in artifacts.json. Shared BAML host/interpreter bytes are separate.
  The measurement adapter is not a minimal deployment. Complete deployment size
  and published-pack startup need separate artifacts; this harness does not
  present benchmark-host size as application deployment size.

Reuse
  --backend names the BAML implementation; --baml-host and --baml-revision select it.
  Build each candidate into a separate cache. Adapter compile/run/inspect commands
  form the boundary: later backends can implement the same JSONL protocol while
  preserving workload semantics and reporting unsupported counters as unavailable.
  Never compare unlike build profiles or claim source-built results are measurements
  of a published binary. Record those distinctions in the report.

Output
  schema.txt defines units and keys. Failed trials stay in samples.csv. report.py
  produces derived summary.csv only; raw observations and provenance are retained.
  environment.json marks pilot/verification runs baseline_accepted=false. A baseline
  report must carry that status until a frozen protocol and coverage are reviewed.
  Each new run has its own directory under measurements/, then one directory per
  case. This preserves earlier baselines when an implementation or setting changes.

Frozen collection
  uv run --no-project machinery/collect.py --protocol machinery/baseline.json \
    --baml-host /absolute/path/to/instrumentation --output measurements/<new-run>
  uv run --no-project machinery/results.py measurements/<new-run>
  This first protocol uses five fresh builds and twenty randomized runtime trials
  per configuration. Pilot runs selected sizes; measurements/gc-sizing/ and
  retention-sizing/ demonstrate natural collections in the allocation workloads.
  The resulting BASELINE.txt is a shared-host comparison, not an idle-machine
  or JIT-converged baseline. Keep its scope attached to every exported figure.

References (pinned BAML release source)
  https://github.com/BoundaryML/baml/tree/340b9085d9427e6d458f1c700409ffc88c58b050/baml_language/crates/bex_engine/examples/resource_workloads
  https://github.com/BoundaryML/baml/blob/340b9085d9427e6d458f1c700409ffc88c58b050/baml_language/crates/bex_heap/src/gc_profile.rs
  https://github.com/BoundaryML/baml/blob/340b9085d9427e6d458f1c700409ffc88c58b050/baml_language/crates/btel_settings/src/mode.rs
  https://github.com/BoundaryML/baml/blob/340b9085d9427e6d458f1c700409ffc88c58b050/baml_language/crates/bex_engine/tests/telemetry_recording.rs
  https://go.dev/doc/gc-guide
  https://docs.python.org/3.14/library/gc.html
  https://man7.org/linux/man-pages/man2/getrusage.2.html
  https://man7.org/linux/man-pages/man2/clock_gettime.2.html
  https://man7.org/linux/man-pages/man2/wait4.2.html

Published executable
  uv run --no-project machinery/pack.py --output measurements/<new-run>
  This separately measures baml pack and one complete off-mode invocation of the
  published musl runtime. pack.csv reports the standalone executable size and
  whole-invocation cost; GC coverage is unknown. Its clock is not the probe's
  execution clock. The source-built probe must not stand in for this artifact.

Pinned build environment
  nix develop path:./machinery
  flake.lock pins support tools. tools.json pins benchmark language distributions;
  changing either requires new provenance. The validation record states which
  environment actually ran the checks; merely evaluating a flake is not using it.

Audit saved numbers
  uv run machinery/audit.py --batch measurements/2026-09-29-shared-host \
    measurements/2026-09-29-extension --http measurements/2026-09-29-http \
    --http-build measurements/2026-09-29-http-builds
  Verify producer snapshots, input hashes, trial counts, raw-versus-exported
  fields, wait4 accounting, required GC counts and exact recording coverage.
  For HTTP, also reconstruct every scheduled arrival, duration, percentile and
  throughput denominator from request records. HTTP request failures are valid
  recorded outcomes; incomplete measurements and invalid schedules are not.
  Missing local recording binaries are explicitly counted. Their saved validation
  summaries can be audited after a clone, but the binaries cannot be re-decoded.
  The first HTML render also freezes case explanations under each collection's
  report-docs/, with content hashes. Later report rebuilds use those snapshots so
  changed case documentation cannot silently reinterpret older measurements.

Board charts: uv run machinery/board_report.py (from the instrumentation root).
Writes measurements/backend-baseline-v1/board/ as PNG, SVG, HTML and Excalidraw;
verifies frozen source hashes and trial validity before rendering.
