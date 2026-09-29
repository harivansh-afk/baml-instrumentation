type State = {batches: number, width: number, retain: number};
type Cell = {value: number, payload: number[]};
export function prepare(raw: string): State { return JSON.parse(raw); }
export async function run(s: State): Promise<string> {
  const retained: Cell[][] = [];
  let checksum = 0;
  for (let batch = 0; batch < s.batches; batch++) {
    const cells: Cell[] = [];
    for (let i = 0; i < s.width; i++) {
      const cell = {value: batch + i, payload: [i, i+1, i+2, i+3]};
      const alias = cell; alias.value++; alias.payload[0]++;
      cells.push(cell);
    }
    for (const cell of cells) checksum += cell.value + cell.payload[0];
    if (s.retain > 0) {
      if (retained.length < s.retain) retained.push(cells);
      else retained[batch % s.retain] = cells;
    }
  }
  let liveSum = 0;
  for (const cells of retained) for (const cell of cells) liveSum += cell.value + cell.payload[0];
  return JSON.stringify([checksum, liveSum]);
}
