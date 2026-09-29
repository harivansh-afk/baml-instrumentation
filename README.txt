BAML baseline programs

Goal: reduce CPU per correct JSON job/request with required telemetry, while
keeping latency and memory inside an explicitly chosen budget. Compare current
BAML with candidate BAML first; Python, TypeScript on Node/V8, Go and Rust provide
context. Matching Node/V8 with telemetry is the meeting's aspiration, not a result.
No single average score across these cases. Correctness is a gate.

00 startup                deployment/harness floor
01 array traversal        first iteration optimization probe
02 merge sort             substantial user-written control flow
03 JSON aggregation       main application baseline
04 allocation/retention   allocation rate versus surviving data
05 async fan-out          scheduling and roots across suspension
06 HTTP aggregation       service efficiency and responsiveness

Each folder has workload.baml/.rs/.go/.py/.ts and a short README.txt. Shared
drivers only implement the protocol; the workload remains in its case folder.
Bun can run the same TS, but is labelled separately from Node/V8.

From this directory, on Linux with uv, Cargo, Go, Node >=24 and a BAML CLI:

  uv run --no-project runner.py build --baml /absolute/path/to/baml-cli
  uv run --no-project runner.py verify --cases 00_startup 01_array_traversal 02_merge_sort
  uv run --no-project runner.py verify --cases 03_json_aggregate 04_allocation_retention 05_async_fanout
  uv run --no-project runner.py verify --cases 06_http_service --requests 2 --rate 100
  /absolute/path/to/baml-cli run main --file correctness.baml
  uv run --no-project runner.py run --cases 03_json_aggregate --size 10000 --jobs 100 --warmup 20 --trials 5
  uv run --no-project runner.py run --cases 06_http_service --size 100 --requests 1000 --rate 100 --trials 5

Run a long matrix in separate commands: each child/build command is limited to
110 seconds. Tune workload/jobs so individual trials fit. Warmup is a parameter,
not proof that the JIT stabilized. Run only one measurement job on the host at a
time. For controlled CPU allocation, prefix with taskset -c <chosen CPUs>;
children inherit affinity, which is recorded. Nix pinning is a separate next step.

Build first; source or executable changes invalidate the recorded build. Outputs
go to .build/ and results/, with exact fixture text, expected output, source and
executable hashes, versions, stderr, raw samples, process RSS samples and commands.
Trials are shuffled reproducibly. --input loads a saved single-line JSON fixture. Missing runners,
output mismatches and build failures fail explicitly; no language is silently skipped.
Rust dependencies are pinned by Cargo.lock; Python HTTP records its installed packages.

Read MEASUREMENT.txt for timer boundaries and GC.txt before interpreting results.
SOURCES.txt points to the meeting notes and existing implementation/benchmarks.
VALIDATION.txt records what was actually exercised, including the binary mismatch.

Initial win rule (proposed, not a team-agreed SLA): lower CPU/correct application
job beyond repeated-run variation, with no reproducible regression in latency or
memory at the same load/resources. Otherwise report the tradeoff. Require the
BAML correctness gate and upstream semantic tests before changing the VM/backend.
Rust's different representation and absence of tracing GC do not make it an
automatic lower bound or evidence that BAML's collector is the bottleneck.
