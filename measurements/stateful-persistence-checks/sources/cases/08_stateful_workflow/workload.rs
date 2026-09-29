use serde::{Deserialize, Serialize};
use std::{collections::HashMap, sync::Arc};

#[derive(Deserialize)]
pub struct Config { requests: Vec<String>, batch: usize, retain: usize, fanout: usize, delay_ms: u64, capture: bool }
#[derive(Deserialize)]
struct Item { kind: String, amount: i64, payload: Vec<i64> }
#[derive(Deserialize)]
struct Request { key: String, mode: String, items: Vec<Item> }
struct Cell { id: usize, value: i64, payload: Vec<i64> }
struct Entry { total: i64, cells: Vec<Cell> }
pub struct State { config: Config, cache: HashMap<String, Entry>, order: Vec<String>, slot: usize, cursor: usize, digest: i64, response_bytes: usize }
#[derive(Serialize)]
struct Response { seq: usize, ok: bool, key: String, total: i64, check: i64, evicted: String }
#[derive(Serialize)]
struct Snapshot { key: String, total: i64, check: i64, count: usize }
#[derive(Serialize)]
struct Result { processed: usize, digest: i64, response_bytes: usize, cache: Vec<Snapshot>, responses: Vec<Response> }
pub fn prepare(raw: &str) -> State {
    State { config: serde_json::from_str(raw).unwrap(), cache: HashMap::new(), order: Vec::new(), slot: 0, cursor: 0, digest: 0, response_bytes: 0 }
}
async fn tool(req: &Request, worker: usize, delay: u64) -> Vec<Cell> {
    let mut cells = Vec::new();
    for i in (worker..req.items.len()).step_by(4) {
        let item = &req.items[i];
        let value = match item.kind.as_str() { "credit" => item.amount, "debit" => -item.amount, _ => 0 };
        let mut payload = Vec::new();
        for v in &item.payload { payload.push(v + worker as i64 + 1); }
        cells.push(Cell { id: i, value, payload });
    }
    if delay > 0 { tokio::time::sleep(std::time::Duration::from_millis(delay)).await; }
    cells
}
fn cell_sum(c: &Cell) -> i64 { c.value + c.payload.iter().sum::<i64>() }
fn live_check(cells: &[Cell]) -> i64 { cells.iter().map(|c| (c.id as i64 + 1) * cell_sum(c)).sum() }
async fn process(s: &mut State, raw: &str) -> Option<Response> {
    let req: Request = serde_json::from_str(raw).ok()?;
    if req.key.is_empty() || !req.key.is_ascii() || !matches!(req.mode.as_str(), "replace" | "accumulate") { return None; }
    for item in &req.items {
        if !matches!(item.kind.as_str(), "credit" | "debit" | "skip") || !(0..=1000000).contains(&item.amount) || item.payload.iter().any(|v| !(0..=1000000).contains(v)) { return None; }
    }
    let req = Arc::new(req);
    let mut parts = Vec::new();
    if s.config.fanout == 4 {
        let mut tasks = Vec::new();
        for worker in 0..4 { let r=Arc::clone(&req); let delay=s.config.delay_ms; tasks.push(tokio::spawn(async move { tool(&r,worker,delay).await })); }
        for task in tasks { parts.push(task.await.unwrap()); }
    } else { for worker in 0..4 { parts.push(tool(&req,worker,s.config.delay_ms).await); } }
    let mut cells=Vec::new(); let mut total=0;
    for part in parts { for cell in part { total+=cell_sum(&cell); cells.push(cell); } }
    if req.mode == "accumulate" { total+=s.cache.get(&req.key).map_or(0,|e|e.total); }
    let check=live_check(&cells);
    let mut evicted=String::new();
    if s.config.retain > 0 {
        if !s.cache.contains_key(&req.key) {
            if s.order.len()<s.config.retain { s.order.push(req.key.clone()); }
            else { evicted=s.order[s.slot].clone(); s.cache.remove(&evicted); s.order[s.slot]=req.key.clone(); s.slot=(s.slot+1)%s.config.retain; }
        }
        s.cache.insert(req.key.clone(),Entry {total,cells});
    }
    Some(Response {seq:s.cursor,ok:true,key:req.key.clone(),total,check,evicted})
}
pub async fn run(s: &mut State) -> String {
    let mut responses=Vec::new();
    for _ in 0..s.config.batch {
        // Move this immutable fixture string temporarily; parsing remains timed.
        let index=s.cursor%s.config.requests.len();
        let raw=std::mem::take(&mut s.config.requests[index]);
        let response=process(s,&raw).await.unwrap_or(Response {seq:s.cursor,ok:false,key:String::new(),total:0,check:0,evicted:String::new()});
        s.config.requests[index]=raw;
        s.response_bytes+=serde_json::to_string(&response).unwrap().len();
        for v in [s.cursor as i64,i64::from(response.ok),response.total,response.check,s.cache.len() as i64] {s.digest=(s.digest*257+v).rem_euclid(1000000007);}
        if s.config.capture {responses.push(response);}
        s.cursor+=1;
    }
    let mut keys:Vec<_>=s.cache.keys().collect();keys.sort();
    let cache=keys.into_iter().map(|key|{let e=&s.cache[key];Snapshot {key:key.clone(),total:e.total,check:live_check(&e.cells),count:e.cells.len()}}).collect();
    serde_json::to_string(&Result {processed:s.cursor,digest:s.digest,response_bytes:s.response_bytes,cache,responses}).unwrap()
}
