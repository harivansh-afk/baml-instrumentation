type State = {count: number, seed: number};
export function prepare(raw: string): State { return JSON.parse(raw); }
function leaf(value: number): number { return value + 1; }
export async function run(state: State): Promise<string> {
    let value = state.seed;
    for (let i = 0; i < state.count; i++) value = leaf(value);
    return String(value);
}
