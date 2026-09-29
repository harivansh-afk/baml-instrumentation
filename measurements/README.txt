No accepted performance baseline exists yet.

2026-09-29-shared-host/ contains the first frozen comparison protocol, repeated
builds and runtime trials. Its generated BASELINE.txt carries the host-load limits;
these observations do not establish an idle-machine or per-call tail-latency baseline.

Each directory is a separate run. Case directories contain raw trials and CSVs;
environment.json and artifacts.json identify the experiment and measured code.
summary.csv is derived from samples.csv with machinery/report.py.

foundation-reference-checks/ and corpus-reference-checks/ test input/output
correctness on the pinned Rust, Go, Python, Node and Bun runtimes.
published-release-validation/ and published-release-corpus-checks/ check the
published BAML executable path. published-release-final-checks/ repeats all seven
with recorded cache policy and source snapshots. reference-protocol-checks/ checks
warmup and repeated jobs. reference-validation/ preserves a rejected setup.
These checks are not latency comparisons, sustained-GC evidence or a frozen baseline.

baml-release-verified/ checks all four telemetry levels. baml-recording-guardrails/
checks rejection paths. gc-sizing/, retention-sizing/ and workload-sizing/ are
pilots used to choose the frozen protocol. baml-release-checks/ retains the failed
validator assumptions that were corrected before collecting the comparison.

See machinery/VALIDATION.txt for verified scope and remaining gaps. A later static
HTML report must retain run identity, failures, unavailable metrics and coverage.
