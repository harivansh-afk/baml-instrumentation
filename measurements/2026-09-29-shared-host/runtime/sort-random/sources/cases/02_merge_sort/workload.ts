type State = {values: number[]};
export function prepare(raw: string): State { return JSON.parse(raw); }
export async function run(state: State): Promise<string> {
  let a: number[] = [], b: number[] = [];
  for (const value of state.values) { a.push(value); b.push(0); }
  const n = a.length;
  for (let width = 1; width < n; width *= 2) {
    for (let lo = 0; lo < n; lo += 2 * width) {
      const mid = Math.min(lo + width, n), hi = Math.min(lo + 2 * width, n);
      let i = lo, j = mid;
      for (let k = lo; k < hi; k++) {
        if (i < mid && (j >= hi || a[i] <= a[j])) b[k] = a[i++];
        else b[k] = a[j++];
      }
    }
    [a, b] = [b, a];
  }
  return JSON.stringify(a);
}
