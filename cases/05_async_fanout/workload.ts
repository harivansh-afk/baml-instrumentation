import { setTimeout } from 'node:timers/promises';
type State = {fanout: number, delay_ms: number, payload_size: number};
export function prepare(raw: string): State { return JSON.parse(raw); }
async function child(i: number, s: State): Promise<number> {
  const payload: number[] = [];
  for (let j = 0; j < s.payload_size; j++) payload.push(i+j);
  await setTimeout(s.delay_ms);
  let sum = 0;
  for (const value of payload) sum += value;
  return sum;
}
export async function run(s: State): Promise<string> {
  const tasks: Promise<number>[] = [];
  for (let i = 0; i < s.fanout; i++) tasks.push(child(i,s));
  const results: number[] = [];
  for (const task of tasks) results.push(await task);
  return JSON.stringify(results);
}
