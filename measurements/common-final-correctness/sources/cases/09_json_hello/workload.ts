type State = {message: string};
export function prepare(raw: string): State { return JSON.parse(raw); }
export async function run(state: State): Promise<string> { return JSON.stringify(state); }
