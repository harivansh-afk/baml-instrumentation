use serde_json::{Value, json};
use std::collections::HashMap;
pub struct State { raw: String }
pub fn prepare(raw: &str) -> State { State { raw: raw.to_owned() } }
fn checked(raw: &str) -> Option<String> {
    let value: Value = serde_json::from_str(raw).ok()?;
    let rows = value.as_array()?;
    if rows.len() > 1_000_000 { return None; }
    let mut totals: HashMap<String,i64> = HashMap::new();
    for row in rows {
        let account = row.get("account")?.as_str()?;
        let amount = row.get("amount_cents")?.as_f64()?;
        let active = row.get("active")?.as_bool()?;
        if !account.is_ascii() || !amount.is_finite() || amount != amount.trunc() || !(0.0..=1_000_000.0).contains(&amount) { return None; }
        if active { *totals.entry(account.to_owned()).or_default() += amount as i64; }
    }
    let mut keys: Vec<_> = totals.keys().collect();
    keys.sort();
    Some(serde_json::to_string(&keys.into_iter().map(|k| json!({"account":k,"total_cents":totals[k]})).collect::<Vec<_>>()).unwrap())
}
pub fn aggregate(raw: &str) -> String { checked(raw).unwrap_or_else(|| r#"{"error":"invalid"}"#.to_owned()) }
pub async fn run(s: &mut State) -> String { aggregate(&s.raw) }
