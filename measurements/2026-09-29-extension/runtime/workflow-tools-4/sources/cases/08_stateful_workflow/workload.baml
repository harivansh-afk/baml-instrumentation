class Item { kind: string, amount: int, payload: int[] }
class Request { key: string, mode: string, items: Item[] }
class Cell { id: int, value: int, payload: int[] }
class Entry { total: int, cells: Cell[] }
class Config { requests: string[], batch: int, retain: int, fanout: int, delay_ms: int, capture: bool }
class State { config: Config, cache: map<string, Entry>, order: string[], slot: int, cursor: int, digest: int, response_bytes: int }
class Response { seq: int, ok: bool, key: string, total: int, check: int, evicted: string }
class Snapshot { key: string, total: int, check: int, count: int }
class Result { processed: int, digest: int, response_bytes: int, cache: Snapshot[], responses: Response[] }
class Invalid { message: string }
function prepare(raw: string) -> State {
    State { config: baml.json.deserialize<Config>(raw), cache: {}, order: [], slot: 0, cursor: 0, digest: 0, response_bytes: 0 }
}
function tool(req: Request, worker: int, delay: int) -> Cell[] {
    let cells: Cell[] = [];
    let i = worker;
    while (i < req.items.length()) {
        let item = req.items[i];
        let value = 0;
        if (item.kind == "credit") { value = item.amount; }
        else if (item.kind == "debit") { value = -item.amount; }
        let payload: int[] = [];
        for (let v in item.payload) { payload.push(v + worker + 1); }
        cells.push(Cell { id: i, value: value, payload: payload });
        i += 4;
    }
    if (delay > 0) { baml.sys.sleep(baml.time.Duration.from_milliseconds(delay)); }
    cells
}
function cell_sum(cell: Cell) -> int {
    let value = cell.value;
    for (let v in cell.payload) { value += v; }
    value
}
function live_check(cells: Cell[]) -> int {
    let total = 0;
    for (let c in cells) { total += (c.id + 1) * cell_sum(c); }
    total
}
function process(s: State, raw: string) -> Response {
    let req = baml.json.deserialize<Request>(raw);
    if (req.key.length() == 0 || !req.key.is_ascii() || (req.mode != "replace" && req.mode != "accumulate")) { throw Invalid { message: "request" }; }
    for (let item in req.items) {
        if ((item.kind != "credit" && item.kind != "debit" && item.kind != "skip") || item.amount < 0 || item.amount > 1000000) { throw Invalid { message: "item" }; }
        for (let v in item.payload) { if (v < 0 || v > 1000000) { throw Invalid { message: "payload" }; } }
    }
    let parts: Cell[][] = [];
    if (s.config.fanout == 4) {
        let tasks: baml.future.Future<Cell[], baml.errors.Io>[] = [];
        let worker = 0;
        while (worker < 4) {
            let id = worker;
            tasks.push(spawn { tool(req, id, s.config.delay_ms) });
            worker += 1;
        }
        for (let task in tasks) { parts.push(await task); }
    } else {
        let worker = 0;
        while (worker < 4) { parts.push(tool(req, worker, s.config.delay_ms)); worker += 1; }
    }
    let cells: Cell[] = [];
    let total = 0;
    for (let part in parts) { for (let c in part) { cells.push(c); total += cell_sum(c); } }
    let previous = s.cache.get(req.key);
    if (req.mode == "accumulate" && previous != null) { total += previous.total; }
    let evicted = "";
    if (s.config.retain > 0) {
        if (previous == null) {
            if (s.order.length() < s.config.retain) { s.order.push(req.key); }
            else {
                evicted = s.order[s.slot];
                s.cache.delete(evicted);
                s.order[s.slot] = req.key;
                s.slot = (s.slot + 1) % s.config.retain;
            }
        }
        s.cache[req.key] = Entry { total: total, cells: cells };
    }
    Response { seq: s.cursor, ok: true, key: req.key, total: total, check: live_check(cells), evicted: evicted }
}
function run(s: State) -> string {
    let responses: Response[] = [];
    let i = 0;
    while (i < s.config.batch) {
        let response = process(s, s.config.requests[s.cursor % s.config.requests.length()]) catch (_) {
            let _ => Response { seq: s.cursor, ok: false, key: "", total: 0, check: 0, evicted: "" }
        };
        s.response_bytes += baml.json.to_string(response).length();
        let ok = 0;
        if (response.ok) { ok = 1; }
        for (let v in [s.cursor, ok, response.total, response.check, s.cache.length()]) {
            s.digest = ((s.digest * 257 + v) % 1000000007 + 1000000007) % 1000000007;
        }
        if (s.config.capture) { responses.push(response); }
        s.cursor += 1;
        i += 1;
    }
    let keys = s.cache.keys();
    keys.sort();
    let snapshot: Snapshot[] = [];
    for (let key in keys) {
        let entry = s.cache[key];
        snapshot.push(Snapshot { key: key, total: entry.total, check: live_check(entry.cells), count: entry.cells.length() });
    }
    baml.json.to_string(Result { processed: s.cursor, digest: s.digest, response_bytes: s.response_bytes, cache: snapshot, responses: responses })
}
