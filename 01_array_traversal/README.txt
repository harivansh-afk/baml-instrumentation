Why: this isolates the loop path proposed for the first VM optimization.
Work: sum a prepared integer array. --variant iterator uses each language's
iterator; indexed rereads length; build also copies via repeated append.
Measure: repeated traversal plus result encoding/protocol. Input decoding is
outside the batch. Sweep 0, 1, 64, 4096 and 262144 elements; tiny cases expose
the harness floor. These are proposed sizes, not performance targets.
BAML behavior: ArrayIterator.next(), calls/dispatch, array reads and safepoints.
Use: explain a change, then rerun JSON/HTTP to establish application benefit.
Go range and Rust iterators do not promise BAML's mutation semantics. The timed
inputs are immutable; correctness.baml separately gates append/alias behavior.
