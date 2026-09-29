use serde::Deserialize;
#[derive(Deserialize)]
pub struct State {
    count: usize,
    seed: i64,
}
pub fn prepare(raw: &str) -> State {
    serde_json::from_str(raw).unwrap()
}
fn leaf(value: i64) -> i64 {
    value + 1
}
pub async fn run(state: &mut State) -> String {
    let mut value = state.seed;
    for _ in 0..state.count {
        value = leaf(value);
    }
    value.to_string()
}
