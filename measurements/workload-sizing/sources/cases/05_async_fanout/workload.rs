use serde::Deserialize;
#[derive(Deserialize)]
pub struct State { fanout: usize, delay_ms: u64, payload_size: usize }
pub fn prepare(raw: &str) -> State { serde_json::from_str(raw).unwrap() }
pub async fn run(s: &mut State) -> String {
    let mut tasks = Vec::new();
    for i in 0..s.fanout {
        let (delay, size) = (s.delay_ms, s.payload_size);
        tasks.push(tokio::spawn(async move {
            let mut payload = Vec::new();
            for j in 0..size { payload.push((i+j) as i64); }
            tokio::time::sleep(std::time::Duration::from_millis(delay)).await;
            let mut sum = 0_i64;
            for value in payload { sum += value; }
            sum
        }));
    }
    let mut results = Vec::new();
    for task in tasks { results.push(task.await.unwrap()); }
    serde_json::to_string(&results).unwrap()
}
