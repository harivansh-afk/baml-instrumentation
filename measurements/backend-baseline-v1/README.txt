Backend comparison scorecard, version 1

Status
  Frozen measurements. KPI selection mapped to the supplied MIR-to-Rust mind map
  and design notes on September 30. Static charts: board/index.html.
  Drawing snapshot: https://draw.harivan.sh/local#json=2931700bc6a55c2fe6a0,7023hZBs6po8dm2v3qpy_A
  Reference: BAML 0.20.2-nightly.20260927.a, source 340b9085d9427e6d458f1c700409ffc88c58b050.
  Linux aarch64, shared host; measured September 29, 2026. CPU affinity does not
  establish isolation. This is a historical reference, not an accepted idle-host
  baseline. The saved observations and their failures remain unchanged.

Six comparisons to keep on each backend's card
  Build: workflow source -> runnable executable, 659.680 ms median, five builds.
    Range 559.702-1578.407 ms. Published runtime already built; downloads and
    runtime bootstrap excluded. Bytecode/diagnostics caches disabled; filesystem
    caches uncontrolled. Require the same declared cache/runtime-build scope.
  Execution: workflow wall 3.422 ms/request; CPU 3.420 ms/request, twenty trials.
    768 requests, 128 items/request, retain four keys, no timers, BTEL off.
    Averages include invalid-request handling and collection; not p95 or p99.
  Memory: allocation peak RSS 100.148 MiB / 203.359 MiB, retain 4 / 64 batches.
    Fixed allocation workload, twenty trials per condition; includes the entire
    measurement process. Neither live-heap size nor isolated collector cost.
  Startup: packed hello invocation 35.033 ms, five fresh processes, BTEL off.
    Includes argument decoding, execution, output and shutdown. This is a
    different artifact and boundary from the 20.494 ms measurement-probe result.
  Artifact: packed workflow 32.687 MiB, five identical artifact observations.
    Published musl host plus bytecode in one executable, no external BAML runtime.
    A backend requiring an external runtime must list that dependency separately;
    a smaller payload alone does not establish a smaller deployment.
  BTEL: same workflow and work counts, measured independently at all four levels.
    Medium: wall 3.640 ms/request (+6.37%); CPU 3.715 ms/request (+8.61%).
    High: wall 4.051 ms/request (+18.39%); CPU 4.501 ms/request (+31.59%).
    High recording: 607.382 KiB/request, whole recording divided by request count.
    Low: wall 3.419 ms/request; CPU 3.418 ms/request. Its small negative overhead
    estimate is not evidence that enabling telemetry accelerates execution.
    Ratios use medians of separate trials, not paired-trial differences. Keep
    absolute costs beside percentages; slowing off-mode must not look like a win.

Correctness gates
  Pass the same required input/output and persistent-state corpus. Include the
  language semantics a backend claims to implement: aliasing, mutation, errors,
  cleanup and async behavior. Existing case checks do not prove full conformance.
  Unsupported required behavior is unsupported, not a successful zero-cost run.
  Require complete expected telemetry and zero delivery loss at supported levels.
  The current reference passes its retained batch corpus but has one invalid
  HTTP BTEL recording. Its telemetry reliability gate is not fully passed.
  Require valid artifact/source identity and the declared measurement protocol.
  Retain failures and predeclared exclusions; never replace an inconvenient trial.

How to judge a candidate
  Preserve each workload's inputs, work counts, lifecycle boundary and output.
  Record backend revision, optimization flags, architecture, CPU placement,
  worker policy, collector policy, dependencies and feature support.
  For each positive cost, index = 100 * candidate median / reference median.
  Lower is cheaper. Keep separate indices; no weighted overall winner score.
  The reference is 100. Also rerun the frozen BAML backend alongside candidates,
  alternating or randomizing trials, to distinguish code changes from host drift.
  Historical and contemporaneous controls remain separate collections.
  Require reproducible improvement beyond observed noise before claiming a gain.
  There is no agreed 5% regression gate or product latency budget in these data.
  A collector-free backend need not collect. If an optimizing collector-backed
  implementation stops triggering GC in the fixed workload, preserve that result
  and add a separately labelled stress run to establish sustained-GC coverage.
  GC count is coverage, not a target to minimize or hold artificially constant.

Current charts to promote
  Workflow: ../charts/2026-09-29-extension-workflow-retain-4-per-request.svg
  Memory: ../charts/2026-09-29-shared-host-allocation-low-retention-peak_rss_bytes-btel.svg
          ../charts/2026-09-29-shared-host-allocation-high-retention-peak_rss_bytes-btel.svg
  BTEL: ../charts/2026-09-29-extension-workflow-retain-4-execution_wall_ns-btel.svg
        ../charts/2026-09-29-extension-workflow-retain-4-recording_bytes-btel.svg
  HTTP: ../charts/2026-09-29-http-http-aggregate-200-latency_p99_ns.svg
  Existing compiler and startup charts use the source-built probe. The main build,
  startup and artifact values above deliberately use the published packed path;
  those observations currently appear in report tables and packed/*/pack.csv.

Engineering diagnostics
  Iterator/indexed traversal: 1.705 / 0.284 ms per 8192-element job, BTEL off.
  Sequential/concurrent tools: 23.113 / 16.055 ms/request; waits plus CPU work.
  HTTP aggregation at 200 requests/s: 5.952 ms median of five process-level p99s,
  successful responses only; zero failures in these BAML-off process trials.
  These HTTP runs last three seconds and do not measure sustainable capacity.
  Probe bytecode compilation: 697.541 ms, distinct from source-to-runnable cost.
  Native integer library sorting and handwritten sorting exercise different paths.

Unmeasured; do not put zero on a backend's card
  BAML GC pause distributions and phase attribution; payload-inclusive live heap;
  long-duration memory plateau; incremental compilation and project-size scaling;
  sustained HTTP capacity; complete backend language conformance.
  The pinned BAML source already has compile-time GC profiling. Keep profiling
  builds separate from release timing; park wait is not a uniform application pause.

Artifacts and evidence
  card.txt is the compact text to copy under a backend in the mind map.
  baseline.json retains all selected observations, units, formulas, source CSV
  selections, artifact identities and SHA-256 hashes of twenty source files.
  It is a frozen reference record, not a runner for a backend that does not exist.
  Existing commands and adapter contract: ../../machinery/README.txt.
  Failure details: ../2026-09-29-http/FINDINGS.txt.
  Raw collections: ../2026-09-29-shared-host/ and ../2026-09-29-extension/.
  https://github.com/BoundaryML/baml/blob/340b9085d9427e6d458f1c700409ffc88c58b050/baml_language/crates/bex_heap/src/gc_policy.rs
  https://github.com/BoundaryML/baml/blob/340b9085d9427e6d458f1c700409ffc88c58b050/baml_language/crates/bex_heap/src/gc_profile.rs
