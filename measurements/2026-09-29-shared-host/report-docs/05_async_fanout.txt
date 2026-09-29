Question
  What does concurrent suspension with retained state cost?

Work
  Spawn children, build one array per child, suspend for a timer, resume
  and sum each array. Join and verify all children in launch order.

BAML path
  Spawn/future dispatch, retained roots, suspension and resumption.

Boundary
  Child creation, allocation, wait, join and result serialization are inside
  each job. Positive timer delays measure concurrent waiting, not CPU scaling.

Evidence
  Every child returns its expected sum. GC across suspension requires
  an observed overlapping collection; a timer alone does not establish it.

Claim
  Orchestration cost at the declared fanout/payload/delay. This version
  does not assert that it exercises root relocation or cancellation.

References
  https://github.com/BoundaryML/baml/blob/340b9085d9427e6d458f1c700409ffc88c58b050/baml_language/crates/bex_engine/src/lib.rs
  https://github.com/BoundaryML/baml/blob/340b9085d9427e6d458f1c700409ffc88c58b050/baml_language/crates/bex_heap/src/heap_guard.rs
