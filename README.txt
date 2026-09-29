Compare the cost of the same correct work across BAML implementations and
reference languages. Keep compilation, execution, memory and deployment separate.

cases/          Programs and the claim each experiment can support.
measurements/   Immutable runs: configuration, artifacts, raw trials and summaries.
machinery/      Pinned tools, adapters, resource observer and validation.

Start with machinery/README.txt. Results are data first: samples.csv and
summary.csv support a later single-file HTML report without copying numbers.

The previous suite is preserved at Git commit 10fe4d7. Its measurements are not
part of this baseline. No absolute latency, memory or compile-time budget has
been agreed; collecting a result does not establish that it meets a product goal.
