// Appended to each workload by runner.py; stdout is a checked line protocol.
function main() -> void {
    let state = prepare(baml.io.input(null));
    baml.io.println("@ready");
    let count = int.parse(baml.io.input(null));
    while (count > 0) {
        let i = 0;
        while (i < count) {
            baml.io.println("@result " + run(state));
            i += 1;
        }
        baml.io.println("@done");
        count = int.parse(baml.io.input(null));
    }
}
