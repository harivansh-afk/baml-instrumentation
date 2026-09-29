use serde::Deserialize;
#[derive(Deserialize)]
pub struct State { value: i64 }
pub fn prepare(raw: &str) -> State { serde_json::from_str(raw).unwrap() }
pub async fn run(s: &mut State) -> String { s.value.to_string() }
