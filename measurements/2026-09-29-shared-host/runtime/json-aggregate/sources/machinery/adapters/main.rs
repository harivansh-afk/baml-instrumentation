use std::{io::Write, time::Instant};
mod workload;
fn cpu_ns() -> u128 {
    let mut t = libc::timespec {
        tv_sec: 0,
        tv_nsec: 0,
    };
    assert_eq!(
        unsafe { libc::clock_gettime(libc::CLOCK_PROCESS_CPUTIME_ID, &mut t) },
        0
    );
    t.tv_sec as u128 * 1_000_000_000 + t.tv_nsec as u128
}
fn emit(v: serde_json::Value) {
    println!("{v}");
    std::io::stdout().flush().unwrap();
}
#[tokio::main(flavor = "current_thread")]
async fn main() {
    let a: Vec<_> = std::env::args().collect();
    let raw = std::fs::read_to_string(&a[1]).unwrap();
    let jobs: u64 = a[2].parse().unwrap();
    let warmup: u64 = a[3].parse().unwrap();
    assert!(jobs > 0);
    let mut s = workload::prepare(&raw);
    emit(serde_json::json!({"event":"ready"}));
    for _ in 0..warmup {
        std::hint::black_box(workload::run(std::hint::black_box(&mut s)).await);
    }
    let start = Instant::now();
    let cpu = cpu_ns();
    let mut result = String::new();
    for _ in 0..jobs {
        result = std::hint::black_box(workload::run(std::hint::black_box(&mut s)).await);
    }
    let cpu = cpu_ns() - cpu;
    let wall = start.elapsed().as_nanos();
    emit(
        serde_json::json!({"event":"result","jobs":jobs,"execution_wall_ns":wall,"execution_cpu_ns":cpu,"result":result,"gc_execution":null,"gc_counter":"not_applicable; ownership and reference counting"}),
    );
}
