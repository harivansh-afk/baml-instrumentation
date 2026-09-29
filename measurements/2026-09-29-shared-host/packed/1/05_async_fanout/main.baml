class State { fanout: int, delay_ms: int, payload_size: int }
function prepare(raw: string) -> State { baml.json.deserialize<State>(raw) }
function child(i: int, s: State) -> int {
    let payload: int[] = [];
    let j = 0;
    while (j < s.payload_size) { payload.push(i + j); j += 1; }
    baml.sys.sleep(baml.time.Duration.from_milliseconds(s.delay_ms));
    let sum = 0;
    for (let value in payload) { sum += value; }
    sum
}
function run(s: State) -> string {
    let tasks: baml.future.Future<int, baml.errors.Io>[] = [];
    let i = 0;
    while (i < s.fanout) {
        let id = i;
        tasks.push(spawn { child(id, s) });
        i += 1;
    }
    let results: int[] = [];
    for (let task in tasks) { results.push(await task); }
    baml.json.to_string(results)
}

function main(raw: string) -> string { run(prepare(raw)) }
