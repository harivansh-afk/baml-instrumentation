Compare the cost of the same correct work across BAML implementations and
reference languages. Keep compilation, execution, memory and deployment separate.

cases/          Programs and the claim each experiment can support.
measurements/   Immutable runs: configuration, artifacts, raw trials and summaries.
machinery/      Pinned tools, adapters, resource observer and validation.

Open measurements/2026-09-29-shared-host/index.html for the visual report.
It works offline and includes per-case charts, BTEL comparisons and CSV downloads.
Start with machinery/README.txt to reproduce a collection or rebuild the report.

Collected results: measurements/2026-09-29-shared-host/BASELINE.txt.
The 2420 runtime trials passed; background workloads prevent treating these
observations as an idle-machine baseline.

The previous suite is preserved at Git commit 10fe4d7. Its measurements are not
part of this baseline. No absolute latency, memory or compile-time budget has
been agreed; collecting a result does not establish that it meets a product goal.
