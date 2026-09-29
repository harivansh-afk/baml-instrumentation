use std::io::{self, BufRead, Write};
mod workload;

#[tokio::main(flavor = "current_thread")]
async fn main() {
    let stdin = io::stdin();
    let mut lines = stdin.lock().lines();
    let mut state = workload::prepare(&lines.next().unwrap().unwrap());
    println!("@ready");
    io::stdout().flush().unwrap();
    loop {
        let count: usize = lines.next().unwrap().unwrap().parse().unwrap();
        if count == 0 { break; }
        for _ in 0..count {
            println!("@result {}", workload::run(&mut state).await);
            io::stdout().flush().unwrap();
        }
        println!("@done");
        io::stdout().flush().unwrap();
    }
}
