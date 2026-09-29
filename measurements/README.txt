No accepted performance baseline exists yet.

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

See machinery/VALIDATION.txt for verified scope and remaining gaps. A later static
HTML report must retain run identity, failures, unavailable metrics and coverage.
