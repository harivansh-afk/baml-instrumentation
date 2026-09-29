Why: short-lived workers pay for loading and starting the language runtime.

Work: read a runtime-supplied integer and return it through the common protocol.

Measure: launch to ready, first correct output, whole-process wall/CPU time,
         peak RSS, and shutdown. Run with --warmup 0 --jobs 1 --trials 10.

BAML behavior: packed bytecode loading, engine/Tokio setup, input conversion,
               return serialization and telemetry drain. baml pack is NOT Rust AOT.

Use: a deployment constraint and harness floor, not a representative application.
     The JSON-capable harness is part of this feature bundle, not minimal hello-world.
     Manifest executable_bytes is one file's size, NOT complete deployment size.
