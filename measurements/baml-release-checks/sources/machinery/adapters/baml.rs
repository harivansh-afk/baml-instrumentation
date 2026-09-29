// Built as an example against the selected BAML revision; no engine changes.
use anyhow::{Result, bail, ensure};
use bex_engine::{BexEngine, BexExternalValue, FunctionCallContextBuilder, TelemetryRecording};
use serde_json::json;
use std::{collections::HashMap, io::Write, path::Path, sync::Arc, time::Instant};
use sys_native::SysOpsExt;

fn cpu_ns() -> u128 {
    let mut ts = libc::timespec {
        tv_sec: 0,
        tv_nsec: 0,
    };
    assert_eq!(
        unsafe { libc::clock_gettime(libc::CLOCK_PROCESS_CPUTIME_ID, &mut ts) },
        0
    );
    ts.tv_sec as u128 * 1_000_000_000 + ts.tv_nsec as u128
}
fn output(v: serde_json::Value) {
    println!("{v}");
    std::io::stdout().flush().unwrap();
}
fn inspect(path: &Path, expected: u64, level: &str) -> Result<()> {
    let mut counts: HashMap<String, u64> = HashMap::new();
    let mut recordings = 0;
    let mut issues = Vec::new();
    let mut ended = true;
    if path.exists() {
        for entry in std::fs::read_dir(path)? {
            let p = entry?.path();
            if !p.is_dir()
                || p.file_name()
                    .unwrap()
                    .to_str()
                    .is_none_or(|n| n.len() != 32 || !n.bytes().all(|c| c.is_ascii_hexdigit()))
            {
                continue;
            }
            let r = btel_file::read_directory(&p)?;
            recordings += 1;
            ended &= r.has_recording_end;
            issues.extend(r.issues.iter().map(|x| format!("{x:?}")));
            let mut functions = HashMap::new();
            let mut paths = HashMap::new();
            for f in &r.files {
                if let Some(d) = &f.definitions {
                    for x in &d.functions {
                        if let Some(
                            btel_recorder::proto::function_definition::Resolution::Metadata(m),
                        ) = &x.resolution
                        {
                            functions.insert(x.function_id, m.fqn.clone());
                        }
                    }
                    for x in &d.call_paths {
                        paths.insert(x.call_path_id, x.callee_function_id);
                    }
                }
            }
            for f in &r.files {
                if let Some(a) = &f.aggregates {
                    for x in &a.entries {
                        if let Some(name) = paths
                            .get(&((x.node >> 1) as u32))
                            .and_then(|id| functions.get(id))
                        {
                            *counts.entry(name.clone()).or_default() += x.count;
                        }
                    }
                }
            }
        }
    }
    let observed: u64 = counts
        .iter()
        .filter(|(n, _)| n.as_str() == "run" || n.ends_with(".run"))
        .map(|(_, n)| *n)
        .sum();
    let count_ok = if level == "low" {
        observed == 0
    } else {
        observed == expected
    };
    let valid = recordings == 1 && ended && issues.is_empty() && count_ok;
    output(
        json!({"valid":valid,"recordings":recordings,"recording_end":ended,"issues":issues,"run_count":observed,"expected_run_count":if level=="low" {0} else {expected},"function_counts":counts,"scope":"structural validation and exact run completions; value capture is not exercised"}),
    );
    ensure!(valid, "telemetry coverage failed");
    Ok(())
}
fn main() -> Result<()> {
    let a: Vec<String> = std::env::args().collect();
    match a.get(1).map(String::as_str) {
        Some("compile") => {
            ensure!(a.len() == 4, "compile SOURCE ARTIFACT");
            let program = baml_db::testing::compile_source(&std::fs::read_to_string(&a[2])?);
            std::fs::write(&a[3], borsh::to_vec(&program)?)?;
            Ok(())
        }
        Some("inspect") => inspect(Path::new(&a[2]), a[3].parse()?, &a[4]),
        Some("run") => {
            ensure!(a.len() == 8, "run ARTIFACT INPUT JOBS WARMUP SINK OUTPUT");
            let origin = Instant::now();
            let program = borsh::from_slice::<bex_vm_types::Program>(&std::fs::read(&a[2])?)?;
            let load_ns = origin.elapsed().as_nanos();
            let workers: usize = std::env::var("BENCH_WORKERS")?.parse()?;
            let rt = tokio::runtime::Builder::new_multi_thread()
                .worker_threads(workers)
                .enable_all()
                .build()?;
            let engine = {
                let _g = rt.enter();
                Arc::new(if a[6] == "local" {
                    BexEngine::new_with_telemetry_recording(
                        program,
                        Arc::new(sys_native::SysOps::native()),
                        vec![],
                        None,
                        btel_settings::clock::DEFAULT_MODE,
                        TelemetryRecording::local_files_in(
                            Path::new(&a[7]).to_path_buf(),
                            btel_recorder::RecordingConfig::default(),
                        ),
                    )?
                } else {
                    BexEngine::new(program, Arc::new(sys_native::SysOps::native()), vec![])?
                })
            };
            let call = |name: &str, args: Vec<BexExternalValue>, copy| {
                rt.block_on(engine.call_function(
                    name,
                    args,
                    FunctionCallContextBuilder::new(sys_native::CallId::next()).build(),
                    copy,
                ))
            };
            let state = call(
                "prepare",
                vec![BexExternalValue::String(
                    std::fs::read_to_string(&a[3])?.into(),
                )],
                false,
            )?;
            output(
                json!({"event":"ready","load_ns":load_ns,"setup_ns":origin.elapsed().as_nanos()-load_ns}),
            );
            let jobs: u64 = a[4].parse()?;
            let warmup: u64 = a[5].parse()?;
            ensure!(jobs > 0, "jobs must be positive");
            let gc0 = engine.heap().gc_budget().full_collections;
            for _ in 0..warmup {
                std::hint::black_box(call("run", vec![state.clone()], true)?);
            }
            let gc1 = engine.heap().gc_budget().full_collections;
            let start = Instant::now();
            let cpu = cpu_ns();
            let mut last = BexExternalValue::Null;
            for _ in 0..jobs {
                last = std::hint::black_box(call("run", vec![state.clone()], true)?);
            }
            let execution_cpu_ns = cpu_ns() - cpu;
            let execution_wall_ns = start.elapsed().as_nanos();
            let gc2 = engine.heap().gc_budget().full_collections;
            let result = match last {
                BexExternalValue::String(s) => s.to_string(),
                _ => bail!("run must return a JSON string"),
            };
            output(
                json!({"event":"result","jobs":jobs,"execution_wall_ns":execution_wall_ns,"execution_cpu_ns":execution_cpu_ns,"result":result,"gc_execution":gc2-gc1,"gc_warmup":gc1-gc0,"gc_counter":"full_collections","workers":workers}),
            );
            drop(state);
            let start = Instant::now();
            rt.block_on(engine.shutdown());
            let drain_ns = start.elapsed().as_nanos();
            let gc3 = engine.heap().gc_budget().full_collections;
            let telemetry_ok = engine.telemetry_result().is_none_or(|r| r.is_ok());
            output(
                json!({"event":"drained","drain_ns":drain_ns,"gc_drain":gc3-gc2,"telemetry_ok":telemetry_ok,"delivery_loss":engine.telemetry_delivery_loss_count()}),
            );
            ensure!(telemetry_ok, "telemetry delivery failed");
            Ok(())
        }
        _ => bail!("expected compile, run, or inspect"),
    }
}
