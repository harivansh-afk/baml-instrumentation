use serde::Deserialize;
#[derive(Deserialize)]
pub struct State { values: Vec<i64>, variant: String }
pub fn prepare(raw: &str) -> State { serde_json::from_str(raw).unwrap() }
pub async fn run(state: &mut State) -> String {
    let copy;
    let values = if state.variant == "build" {
        let mut v = Vec::new();
        for i in 0..state.values.len() { v.push(state.values[i]); }
        copy = v;
        &copy
    } else { &state.values };
    let mut total = 0_i64;
    if state.variant == "indexed" {
        let mut i = 0;
        while i < values.len() { total += values[i]; i += 1; }
    } else {
        for value in values { total += value; }
    }
    total.to_string()
}
