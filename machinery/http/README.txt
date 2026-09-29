Persistent-service measurement

Use the language pins in ../tools.json. Cargo.lock pins the HTTP dependency
closure; requirements.txt pins Python dependencies with download hashes.
Dependencies are fetched before compilation timing. Go builds an explicit module
with go 1.27.1 so net/http uses that toolchain's routing compatibility defaults.

Build the separate BAML HTTP host:
  uv run machinery/build_baml.py --checkout /absolute/path/to/baml --probe http

Build five clean service artifacts per compiled language:
  uv run machinery/http/run.py build --output measurements/<build-run> \
    --baml-host /absolute/path/to/instrumentation_http --repeats 5

Check responses and recording coverage, then run the frozen offered-load protocol:
  uv run machinery/http/run.py verify --output measurements/<correctness-run> \
    --artifacts measurements/<build-run>/artifacts.json
  uv run machinery/http/run.py run --output measurements/<service-run> \
    --artifacts measurements/<build-run>/artifacts.json

Each server announces @ready after binding and receives a newline to shut down.
The native observer owns wait4 accounting; stdout and RSS sampling occur in the
controller. The load client is a separate process on separate permitted CPUs.
Its request timestamps use one monotonic clock. Response timing ends before
client JSON validation; validation still consumes client time and can contribute
to later dispatch lag, which is explicitly recorded. Only one trial runs at once.

Each trial retains commands/artifact identity through artifacts.json, exact
request configuration, one observation per request, warmup checks, stdout/stderr,
RSS samples, host snapshots, wait4 usage and BTEL validation. Source hashes and
producer/ snapshots identify the machinery. Recordings stay local and ignored
by Git; validation summaries are committed. Failed trials remain visible.

There is no packed-executable HTTP observation. BAML service artifact size is
bytecode plus a separately listed shared measurement host. Rust/Go sizes include
the selected HTTP stack; script sizes exclude their interpreters and dependencies.
These are labelled artifact inventories, not equivalent full deployment sizes.
