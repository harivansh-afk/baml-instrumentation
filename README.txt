Goal: Reduce CPU per correct BAML job/request while preserving behavior and
      telemetry, within declared latency, memory and deployment limits.

Cases: 00 startup                 04 allocation and retention
       01 array traversal         05 async fan-out
       02 merge sort              06 HTTP aggregation
       03 JSON aggregation

Languages: BAML, Rust, Go, Python, TypeScript on Node/V8 and Bun/JavaScriptCore.

Results: Each case has baseline.csv and baseline.samples.csv.
         BASELINE.txt defines units, boundaries and limitations.
         baseline.environment.json records versions, hashes and run settings.

Build: uv run --no-project runner.py build --baml /absolute/path/to/baml-cli
       uv run --no-project runner.py build --languages bun
       Requires Linux, uv, cc, Cargo, Go, Node >=24 and Bun.

Check: uv run --no-project -m unittest test_runner -v
       uv run --no-project runner.py verify --cases 01_array_traversal 02_merge_sort
       /absolute/path/to/baml-cli run main --file correctness.baml

Measure: uv run --no-project baseline.py calibrate --case 03_json_aggregate --scenario 1000_records
         uv run --no-project baseline.py round --case 03_json_aggregate --scenario 1000_records --round 0
         Repeat rounds 0 through 4 for each scenario in baseline.py, then run:
         uv run --no-project baseline.py publish
         Use --run-dir results/<new-name> consistently for a new measurement set.

Protocol: Same fixture and CPU allowance; calibrated job counts; five shuffled
          process trials. Runtimes use normal GC. Compilation is outside timers.
          Correctness failures invalidate a job; HTTP failures stay in the data.

References: MEASUREMENT.txt for timer details; GC.txt for collector attribution;
            SOURCES.txt for code/call references; VALIDATION.txt for smoke checks.
