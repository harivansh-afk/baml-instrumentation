Why: short-lived allocation and a large live set stress different GC work.

Work: create cells with four-int payload arrays; mutate through aliases; traverse all
      cells. Keep a ring of --retain batches, replacing old slots. --batches controls
      churn; --size controls width. Check both total and surviving-cell sums by formula.

Measure: CPU/job, process peak RSS and sampled RSS through repeated jobs. Vary
         retain=0/1/4/32 at fixed width/batches, then churn at fixed retained capacity.

BAML behavior: object/TLAB allocation, pointer stores, roots, promotion and copying.
               Rust uses Rc<RefCell<Cell>> to preserve shared identity; Go uses
               pointers; Python and JS use reference objects. Object layouts, barriers
               and reclamation differ.

Use: reject apparent speedups that only postpone memory work. Retention lasts within one
     job. RSS is not live heap; see GC.txt before attributing pauses or leaks.

Baseline: baseline.csv; individual trials in baseline.samples.csv.
          Units, size accounting and run settings: ../BASELINE.txt.
