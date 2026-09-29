use serde::{Deserialize, Serialize};
#[derive(Deserialize, Serialize)]
pub struct State {
    message: String,
}
pub fn prepare(raw: &str) -> State {
    serde_json::from_str(raw).unwrap()
}
pub async fn run(s: &mut State) -> String {
    serde_json::to_string(s).unwrap()
}
