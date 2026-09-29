export function prepare(raw: string): string { return raw; }
export function aggregate(raw: string): string {
  try {
    const rows = JSON.parse(raw);
    if (!Array.isArray(rows) || rows.length > 1000000) throw new Error();
    const totals = new Map<string, number>();
    for (const row of rows) {
      if (row === null || typeof row !== 'object' || Array.isArray(row)) throw new Error();
      const {account, amount_cents: amount, active} = row;
      if (typeof account !== 'string' || /[^\x00-\x7F]/.test(account)) throw new Error();
      if (typeof active !== 'boolean' || !Number.isInteger(amount) || amount < 0 || amount > 1000000) throw new Error();
      if (active) totals.set(account, (totals.get(account) ?? 0) + amount);
    }
    return JSON.stringify([...totals.keys()].sort().map(account => ({account, total_cents: totals.get(account)})));
  } catch { return '{"error":"invalid"}'; }
}
export async function run(state: string): Promise<string> { return aggregate(state); }
