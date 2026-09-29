Why: this is the first application baseline from the JSON/server discussion.
Work: parse an array; validate account:string (ASCII), amount_cents:integer-valued
number in [0,1000000], active:bool; group active amounts; sort accounts; encode
[{account,total_cents}]. Accept <=1000000 rows, ignore extra fields, reject invalid
input with {"error":"invalid"}. The complete result is checked independently.
Measure: parse/validate/aggregate/sort/encode plus protocol, CPU/job and memory.
Input text is supplied before the batch; parsing stays INSIDE every job.
BAML behavior: native JSON parser, conversion to heap classes, iteration, maps,
strings, native key sort, serialization and telemetry. AOT changes only some costs.
Use: the main CPU-per-correct-job goal; HTTP adds queueing and service latency.
Compare parsed JSON, not object-key order. No duplicate-key/invalid-Unicode claims.
