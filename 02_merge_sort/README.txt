Why: substantial user-written code should improve, not only native helpers.

Work: bottom-up integer merge sort, with the same tie rule in all languages. Input is
      unchanged. Every job copies it, allocates scratch, merges, then encodes the FULL
      output. The oracle uses an independent library sort.

Measure: whole sort job, CPU, elapsed time and memory over sizes/distributions. Try
         --variant random, sorted, reverse and duplicates; include non-powers of two.

BAML behavior: nested control flow, indexing, shared array references, writes,
               allocation and dispatch. This does not call BAML's native primitive sort.

Use: judge generated user-code quality. Output encoding/IPC is included, so this is not
     a pure sort-kernel timer. Stability of equal-key records is not tested.

Baseline: baseline.csv; individual trials in baseline.samples.csv.
          Units, size accounting and run settings: ../BASELINE.txt.
