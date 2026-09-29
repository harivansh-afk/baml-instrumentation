use serde::Deserialize;
#[derive(Deserialize)]
pub struct State {
    values: Vec<i64>,
}
pub fn prepare(raw: &str) -> State {
    serde_json::from_str(raw).unwrap()
}
pub async fn run(s: &mut State) -> String {
    let mut a = Vec::new();
    for &v in &s.values {
        a.push(v)
    }
    let (mut lows, mut highs, mut top) = (vec![0_isize], vec![a.len() as isize - 1], 1_usize);
    while top > 0 {
        top -= 1;
        let (lo, hi) = (lows[top], highs[top]);
        if lo >= hi {
            continue;
        }
        let pivot = a[(lo + (hi - lo) / 2) as usize];
        let (mut lt, mut i, mut gt) = (lo, lo, hi);
        while i <= gt {
            if a[i as usize] < pivot {
                a.swap(lt as usize, i as usize);
                lt += 1;
                i += 1
            } else if a[i as usize] > pivot {
                a.swap(gt as usize, i as usize);
                gt -= 1
            } else {
                i += 1
            }
        }
        if top == lows.len() {
            lows.push(lo);
            highs.push(lt - 1)
        } else {
            lows[top] = lo;
            highs[top] = lt - 1
        }
        top += 1;
        if top == lows.len() {
            lows.push(gt + 1);
            highs.push(hi)
        } else {
            lows[top] = gt + 1;
            highs[top] = hi
        }
        top += 1;
    }
    serde_json::to_string(&a).unwrap()
}
