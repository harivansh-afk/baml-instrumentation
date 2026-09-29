// Built as an example against the selected BAML revision; no engine changes.
use anyhow::{Result, bail, ensure};
use bex_engine::{BexEngine, FunctionCallContextBuilder, TelemetryRecording};
use serde_json::json;
use std::{collections::HashMap, io::Write, path::Path, sync::Arc, time::Instant};
use sys_native::SysOpsExt;

fn output(v: serde_json::Value) {
    println!("{v}");
    std::io::stdout().flush().unwrap();
}
fn inspect(path: &Path, expected: u64, level: &str, names: HashMap<u64, String>) -> Result<()> {
    let mut counts: HashMap<String, u64> = HashMap::new();
    let mut span_counts: HashMap<String, u64> = HashMap::new();
    let mut root_completions = 0;
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
            let mut functions = names.clone();
            let mut paths = HashMap::new();
            let mut roots = std::collections::HashSet::new();
            let mut completed = std::collections::HashSet::new();
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
                    for x in &d.threads {
                        if x.parent_id.is_none() {
                            roots.insert(x.thread_id);
                        }
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
                if let Some(spans) = &f.spans {
                    for section in &spans.sections {
                        for event in &section.events {
                            use btel_recorder::proto::span_event::Event;
                            match &event.event {
                                Some(Event::ThreadCompletion(done))
                                    if roots.contains(&section.thread_id) =>
                                {
                                    if !completed.insert(section.thread_id) || done.outcome != 1 {
                                        issues.push(
                                            "duplicate or unsuccessful root completion".to_string(),
                                        );
                                    }
                                }
                                Some(
                                    Event::FunctionCompletion(done)
                                    | Event::LateFunctionCompletion(done),
                                ) => {
                                    if let Some(name) = paths
                                        .get(&((done.node >> 1) as u32))
                                        .and_then(|id| functions.get(id))
                                    {
                                        *span_counts.entry(name.clone()).or_default() += 1;
                                    }
                                }
                                _ => {}
                            }
                        }
                    }
                }
            }
            root_completions += completed.len() as u64;
        }
    }
    let observed: u64 = counts
        .iter()
        .filter(|(n, _)| n.as_str() == "handle" || n.ends_with(".handle"))
        .map(|(_, n)| *n)
        .sum();
    let count_ok = if level == "low" {
        observed == 0
    } else {
        observed == expected
    };
    let prepare_count: u64 = counts
        .iter()
        .filter(|(n, _)| n.rsplit('.').next() == Some("prepare"))
        .map(|(_, n)| *n)
        .sum();
    let span_run_count: u64 = span_counts
        .iter()
        .filter(|(n, _)| n.rsplit('.').next() == Some("handle"))
        .map(|(_, n)| *n)
        .sum();
    // This release does not emit RecordingEnd or resolved function names.
    // The host supplies runtime IDs after execution; expected calls establish coverage.
    let valid = recordings == 1
        && issues.is_empty()
        && count_ok
        && root_completions == 1
        && span_run_count == if level == "high" { expected } else { 0 };
    output(
        json!({"valid":valid,"recordings":recordings,"recording_end":ended,"issues":issues,"run_count":observed,"prepare_count":prepare_count,"root_completions":root_completions,"span_run_count":span_run_count,"expected_run_count":if level=="low" {0} else {expected},"function_counts":counts,"scope":"structural validation, runtime metadata, root completions and exact handler counts; value capture is not exercised"}),
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
        Some("inspect") => {
            ensure!(
                a.len() == 6,
                "inspect OUTPUT EXPECTED_CALLS LEVEL FUNCTION_NAMES_JSON"
            );
            inspect(
                Path::new(&a[2]),
                a[3].parse()?,
                &a[4],
                serde_json::from_str(&a[5])?,
            )
        }
        Some("handle") => {
            ensure!(a.len() == 4, "run ARTIFACT OUTPUT");
            let program = borsh::from_slice::<bex_vm_types::Program>(&std::fs::read(&a[2])?)?;
            let workers: usize = std::env::var("BENCH_WORKERS")?.parse()?;
            let rt = tokio::runtime::Builder::new_multi_thread()
                .worker_threads(workers)
                .enable_all()
                .build()?;
            let engine = {
                let _g = rt.enter();
                Arc::new(BexEngine::new_with_telemetry_recording(
                    program,
                    Arc::new(sys_native::SysOps::native()),
                    vec![],
                    None,
                    btel_settings::clock::DEFAULT_MODE,
                    TelemetryRecording::local_files_in(
                        Path::new(&a[3]).to_path_buf(),
                        btel_recorder::RecordingConfig::default(),
                    ),
                )?)
            };
            let gc0 = engine.heap().gc_budget().full_collections;
            rt.block_on(engine.call_function(
                "main",
                vec![],
                FunctionCallContextBuilder::new(sys_native::CallId::next()).build(),
                true,
            ))?;
            let gc2 = engine.heap().gc_budget().full_collections;
            let metadata_start = Instant::now();
            let function_names: HashMap<u64, String> = rt
                .block_on(engine.program_metadata())
                .function_table
                .functions
                .into_iter()
                .filter(|f| {
                    matches!(
                        f.fqn.rsplit('.').next(),
                        Some("prepare" | "run" | "handle" | "main")
                    )
                })
                .map(|f| (f.function_id.get(), f.fqn))
                .collect();
            let metadata_ns = metadata_start.elapsed().as_nanos();
            let start = Instant::now();
            rt.block_on(engine.shutdown());
            let drain_ns = start.elapsed().as_nanos();
            let gc3 = engine.heap().gc_budget().full_collections;
            let telemetry_ok = if std::env::var("BAML_TELEMETRY").as_deref() == Ok("off") {
                engine.telemetry_result().is_none()
            } else {
                engine.telemetry_result().is_some_and(|r| r.is_ok())
            };
            output(
                json!({"event":"drained","drain_ns":drain_ns,"gc_drain":gc3-gc2,"gc_service_lifetime":gc2-gc0,"telemetry_ok":telemetry_ok,"delivery_loss":engine.telemetry_delivery_loss_count(),"function_names":function_names,"metadata_ns":metadata_ns}),
            );
            ensure!(telemetry_ok, "telemetry delivery failed");
            Ok(())
        }
        _ => bail!("expected compile, run, or inspect"),
    }
}
