Compare the cost of the same correct work across BAML implementations and
reference languages. Keep compilation, execution, memory and deployment separate.

cases/          Programs and the claim each experiment can support.
measurements/   Immutable runs: configuration, artifacts, raw trials and summaries.
machinery/      Pinned tools, adapters, resource observer and validation.

Open measurements/index.html for the combined visual report.
It works offline: static bar charts, per-case and BTEL comparisons, CSV downloads.
Start with machinery/README.txt to reproduce a collection or rebuild the report.

4940 batch trials passed, including stateful workflows, JSON and sorting.
180 HTTP trials completed; five request timeouts, one incomplete BTEL recording
and two scheduling exclusions are documented in:
  measurements/2026-09-29-http/FINDINGS.txt
Background services remained active: this is a shared-host record.

The previous suite is preserved at Git commit 10fe4d7. Its measurements are not
part of this baseline. No absolute latency, memory or compile-time budget has
been agreed; collecting a result does not establish that it meets a product goal.
