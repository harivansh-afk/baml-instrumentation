use serde::Deserialize;
#[derive(Deserialize)]
pub struct State { values: Vec<i64> }
pub fn prepare(raw: &str) -> State { serde_json::from_str(raw).unwrap() }
pub async fn run(state: &mut State) -> String {
    let (mut a, mut b) = (Vec::new(), Vec::new());
    for &value in &state.values { a.push(value); b.push(0_i64); }
    let n = a.len();
    let mut width = 1;
    while width < n {
        let mut lo = 0;
        while lo < n {
            let mid = (lo + width).min(n);
            let hi = (lo + 2 * width).min(n);
            let (mut i, mut j) = (lo, mid);
            for k in lo..hi {
                if i < mid && (j >= hi || a[i] <= a[j]) { b[k] = a[i]; i += 1; }
                else { b[k] = a[j]; j += 1; }
            }
            lo += 2 * width;
        }
        std::mem::swap(&mut a, &mut b);
        width *= 2;
    }
    serde_json::to_string(&a).unwrap()
}
