Open index.html for the combined, static visual report.
backend-baseline-v1/ freezes a proposed backend scorecard, exact values and sources.

2026-09-29-shared-host/   Original batch suite; raw observations unchanged.
2026-09-29-extension/     Stateful workflow, JSON hello, sorting distributions,
                          quicksort, and generated-number library sorting.
2026-09-29-http/          Persistent HTTP request observations and process totals.
2026-09-29-http-builds/   Five clean HTTP builds per compiled language.

Each collection retains its own protocol and artifact identities. They are
shared-host observations, not a pooled distribution or idle-machine baseline.
Correctness and sizing directories are validation evidence, not performance
samples for these collections. Rejected runs remain distinguishable by status.
BTEL recording binaries remain local under each trial's recordings/ directory;
Git includes their byte counts and structural/coverage validation summaries.

Rebuild the combined document from saved observations:
  uv run machinery/html_report.py \
    measurements/2026-09-29-shared-host measurements/2026-09-29-extension \
    --http measurements/2026-09-29-http \
    --http-build measurements/2026-09-29-http-builds \
    --output measurements/index.html

This command reads saved results; it never reruns a workload. The HTML embeds
its SVGs, data and downloads. charts/ also holds the individual static SVGs.

See machinery/VALIDATION.txt for correctness controls and retained setup failures.
2026-09-29-http/FINDINGS.txt explains the recording failure, request timeouts and
scheduling exclusions. baseline_accepted remains false for every collection.
