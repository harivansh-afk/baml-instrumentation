use serde::Deserialize;
use std::{rc::Rc, cell::RefCell};
struct Cell { value: i64, payload: Vec<i64> }
#[derive(Deserialize)]
pub struct State { batches: usize, width: usize, retain: usize }
pub fn prepare(raw: &str) -> State { serde_json::from_str(raw).unwrap() }
pub async fn run(s: &mut State) -> String {
    let mut retained: Vec<Vec<Rc<RefCell<Cell>>>> = Vec::new();
    let mut checksum = 0_i64;
    for batch in 0..s.batches {
        let mut cells = Vec::new();
        for i in 0..s.width as i64 {
            let cell = Rc::new(RefCell::new(Cell { value: batch as i64+i, payload: vec![i,i+1,i+2,i+3] }));
            let alias = Rc::clone(&cell);
            { let mut a = alias.borrow_mut(); a.value += 1; a.payload[0] += 1; }
            cells.push(cell);
        }
        for cell in &cells { let c = cell.borrow(); checksum += c.value + c.payload[0]; }
        if s.retain > 0 {
            if retained.len() < s.retain { retained.push(cells); }
            else { retained[batch % s.retain] = cells; }
        }
    }
    let mut live = 0_i64;
    for cells in &retained { for cell in cells { let c = cell.borrow(); live += c.value + c.payload[0]; } }
    serde_json::to_string(&[checksum,live]).unwrap()
}
