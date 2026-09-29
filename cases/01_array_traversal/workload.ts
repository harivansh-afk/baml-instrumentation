type State = { values: number[], variant: string };
export function prepare(raw: string): State { return JSON.parse(raw); }
export async function run(state: State): Promise<string> {
  let values = state.values;
  if (state.variant === 'build') {
    values = [];
    for (let i = 0; i < state.values.length; i++) values.push(state.values[i]);
  }
  let total = 0;
  if (state.variant === 'indexed') {
    for (let i = 0; i < values.length; i++) total += values[i];
  } else {
    for (const value of values) total += value;
  }
  return String(total);
}
