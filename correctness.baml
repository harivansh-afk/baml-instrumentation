// BAML semantic gates, deliberately outside all performance measurements.
// This supplements the upstream suite; it is not full language conformance.
class Live { values: int[], started: bool }

function fail_with_cleanup(log: string[]) -> void {
    defer { log.push("first") }
    defer { log.push("second") }
    log.push("body");
    throw "expected";
}

function main() -> bool {
    let values = [1, 2];
    let alias = values;
    let sum = 0;
    for (let value in values) {
        if (value == 1) { alias.push(3); }
        sum += value;
    }
    assert.equal(sum, 6);
    assert.equal(values.length(), 3);

    let nullable: int?[] = [null, 7, null];
    let seen = 0;
    for (let value in nullable) { seen += 1; }
    assert.equal(seen, 3);

    let nested = 0;
    for (let x in [1, 2, 3]) {
        for (let y in [1, 2, 3]) {
            if (y == 2) { continue; }
            if (x == 3) { break; }
            nested += x * y;
        }
    }
    assert.equal(nested, 12);

    let log: string[] = [];
    fail_with_cleanup(log) catch (_) { "expected" => { log.push("caught"); } };
    assert.equal(log, ["body", "second", "first", "caught"]);

    let maximum = int.max_value();
    let overflow_caught = false;
    (maximum + 1) catch (_) { baml.panics.IntegerOverflow => { overflow_caught = true; 0 } };
    assert.equal(overflow_caught, true);

    let live = Live { values: [3, 5, 7], started: false };
    let task = spawn {
        let held = live.values;
        live.started = true;
        baml.sys.sleep(baml.time.Duration.from_milliseconds(50));
        held[0] + held[1] + held[2]
    };
    while (!live.started) { baml.sys.sleep(baml.time.Duration.from_milliseconds(1)); }
    // Leave the old array reachable only through the suspended child's local.
    live.values = [];
    baml.sys.collect_garbage();
    assert.equal(await task, 15);

    let cancellable = spawn { baml.sys.sleep(baml.time.Duration.from_milliseconds(1000)); 1 };
    cancellable.cancel();
    let cancelled = (await cancellable) catch (_) { baml.panics.Cancelled => -1 };
    assert.equal(cancelled, -1);
    true
}
