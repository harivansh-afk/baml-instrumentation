import { createInterface } from 'node:readline';
import { once } from 'node:events';
import { pathToFileURL } from 'node:url';

const workload = await import(pathToFileURL(process.argv[2]).href);
const lines = createInterface({input: process.stdin, crlfDelay: Infinity})[Symbol.asyncIterator]();
async function line(): Promise<string> {
  const next = await lines.next();
  if (next.done) throw new Error('unexpected EOF');
  return next.value;
}
async function emit(s: string) {
  if (!process.stdout.write(s + '\n')) await once(process.stdout, 'drain');
}
const state = workload.prepare(await line());
await emit('@ready');
for (let count = Number(await line()); count > 0; count = Number(await line())) {
  for (let i = 0; i < count; i++) await emit('@result ' + await workload.run(state));
  await emit('@done');
}
