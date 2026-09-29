use serde::Deserialize;
#[derive(Deserialize)]
pub struct State {
    count: usize,
    seed: i64,
}
pub fn prepare(raw: &str) -> State {
    serde_json::from_str(raw).unwrap()
}
pub async fn run(s: &mut State) -> String {
    let mut a = Vec::new();
    let mut v = s.seed;
    for _ in 0..s.count {
        v = v * 48271 % 1000000007;
        a.push(v)
    }
    a.sort();
    serde_json::to_string(&a).unwrap()
}
