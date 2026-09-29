export function prepare(raw: string): {value: number} { return JSON.parse(raw); }
export async function run(state: {value: number}): Promise<string> { return String(state.value); }
