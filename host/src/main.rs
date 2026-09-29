//! palette-host: the host side of Palette -- the sandbox launcher, the
//! persistent session bridge and the capability broker -- as one binary.
//!
//!   palette-host session    --project-dir P [--ceiling C] [--workspace-dir W] [--state-dir S] ...
//!   palette-host run-worker --workspace W --project P --repo R --script CODE [--broker-socket-dir D] [--timeout S]
//!   palette-host broker     --socket PATH --ceiling C --receipts FILE [--session-id ID] [--project P --repo R --depot D]
//!   palette-host subset     REQUESTED_JSON PARENT_JSON
//!   palette-host prewarm    --project-dir P [--repo-dir R]

mod broker;
mod cli;
mod sandbox;
mod session;
mod util;

use serde_json::{json, Value};
use std::collections::HashMap;
use std::path::PathBuf;
use std::sync::Arc;
use std::time::Duration;

fn flags(argv: &[String], booleans: &[&str]) -> Result<HashMap<String, String>, String> {
    let mut m = HashMap::new();
    let mut i = 0;
    while i < argv.len() {
        let k = argv[i].strip_prefix("--").ok_or_else(|| format!("unexpected argument: {}", argv[i]))?;
        if booleans.contains(&k) {
            m.insert(k.to_string(), "true".into());
        } else {
            i += 1;
            m.insert(k.to_string(), argv.get(i).cloned().ok_or_else(|| format!("--{k} needs a value"))?);
        }
        i += 1;
    }
    Ok(m)
}

fn ceiling_arg(s: &str) -> Result<Value, String> {
    let text = if std::path::Path::new(s).is_file() { std::fs::read_to_string(s).map_err(|e| e.to_string())? } else { s.to_string() };
    serde_json::from_str(&text).map_err(|e| format!("ceiling: {e}"))
}

fn run_worker(argv: &[String]) -> Result<i32, String> {
    let f = flags(argv, &["network"])?;
    let get = |k: &str| f.get(k).cloned().ok_or_else(|| format!("--{k} is required"));
    let r = sandbox::run_worker(&sandbox::RunWorker {
        workspace_dir: &get("workspace")?,
        project_dir: &get("project")?,
        repo_dir: &get("repo")?,
        script: &get("script")?,
        broker_socket_dir: f.get("broker-socket-dir").map(String::as_str),
        network_enabled: f.contains_key("network"),
        depot_clone_dir: f.get("depot-clone-dir").map(String::as_str),
        timeout: Duration::from_secs_f64(f.get("timeout").map_or(Ok(60.0), |t| t.parse::<f64>()).map_err(|e| e.to_string())?),
    })?;
    println!("{}", json!({"returncode": r.returncode, "stdout": r.stdout, "stderr": r.stderr, "timed_out": r.timed_out}));
    Ok(0)
}

/// A standalone broker, serving until its stdin closes; prints one READY line.
fn run_broker(argv: &[String]) -> Result<i32, String> {
    let f = flags(argv, &[])?;
    let get = |k: &str| f.get(k).cloned().ok_or_else(|| format!("--{k} is required"));
    let b = Arc::new(broker::Broker::new(broker::BrokerConfig {
        ceiling: ceiling_arg(&get("ceiling")?)?,
        receipt_log_path: PathBuf::from(get("receipts")?),
        session_id: f.get("session-id").cloned().unwrap_or_else(util::uuid4),
        depot_dir: f.get("depot").cloned(),
        project_dir: f.get("project").cloned(),
        repo_dir: f.get("repo").cloned(),
        child_timeout: Duration::from_secs_f64(f.get("child-timeout").map_or(Ok(90.0), |t| t.parse::<f64>()).map_err(|e| e.to_string())?),
    })?);
    let server = broker::serve(std::path::Path::new(&get("socket")?), b)?;
    println!("{}", json!({"kind": "READY"}));
    let mut sink = String::new();
    while std::io::stdin().read_line(&mut sink).map(|n| n > 0).unwrap_or(false) {
        sink.clear();
    }
    server.shutdown();
    Ok(0)
}

fn subset(argv: &[String]) -> Result<i32, String> {
    let [req, parent] = argv else { return Err("subset takes REQUESTED_JSON PARENT_JSON".into()) };
    let parse = |s: &str| serde_json::from_str::<Value>(s).map_err(|e| e.to_string());
    let (ok, reason) = broker::ceiling_is_subset(&parse(req)?, &parse(parent)?);
    println!("{}", json!({"ok": ok, "reason": reason}));
    Ok(0)
}

/// Precompile every stdlib and project dependency into the real depot, in the
/// worker's own sandbox so the caches record the paths a worker sees. Run once
/// per depot, and again after Neura or the project changes.
const PREWARM: &str = r#"
using Neura
failed = String[]
stdlibs = filter(n -> isfile(joinpath(Sys.STDLIB, n, "Project.toml")), readdir(Sys.STDLIB))
project_deps = collect(keys(get(Base.parsed_toml(Base.active_project()), "deps", Dict())))
for name in sort(unique([stdlibs; project_deps]))
    try
        Core.eval(Main, :(import $(Symbol(name))))
    catch e
        push!(failed, name * ": " * first(sprint(showerror, e), 200))
    end
end
println("prewarmed ", length(Base.loaded_modules), " modules")
foreach(f -> println("could not load ", f), failed)
"#;

fn prewarm(argv: &[String]) -> Result<i32, String> {
    let f = flags(argv, &[])?;
    let project = std::fs::canonicalize(f.get("project-dir").ok_or("--project-dir is required")?).map_err(|e| e.to_string())?;
    let repo = std::fs::canonicalize(f.get("repo-dir").cloned().unwrap_or_else(cli::default_repo_dir)).map_err(|e| e.to_string())?;
    let julia = sandbox::resolve_julia()?;
    let workspace = util::mkdtemp("palette-prewarm-").map_err(|e| e.to_string())?;
    let depot = sandbox::default_depot();
    // No depot clone: the real depot is bound writable at its own path.
    let mut argv = sandbox::build_bwrap_argv(&sandbox::SandboxSpec {
        workspace_dir: &workspace.to_string_lossy(),
        broker_socket_dir: None,
        project_dir: &project.to_string_lossy(),
        repo_dir: &repo.to_string_lossy(),
        julia_bin: &julia,
        julia_depot: &depot,
        network_enabled: false,
        depot_clone_dir: None,
        state_dir: None,
    })?;
    argv.extend(["--".into(), julia, "--startup-file=no".into(), "-e".into(), PREWARM.into()]);
    let status = std::process::Command::new(&argv[0]).args(&argv[1..]).stdin(std::process::Stdio::null()).status();
    let _ = std::fs::remove_dir_all(&workspace);
    Ok(status.map_err(|e| e.to_string())?.code().unwrap_or(1))
}

fn main() {
    let argv: Vec<String> = std::env::args().collect();
    let rest = argv.get(2..).unwrap_or(&[]);
    let code = match argv.get(1).map(String::as_str) {
        Some("session") => Ok(cli::main(rest)),
        Some("run-worker") => run_worker(rest),
        Some("broker") => run_broker(rest),
        Some("subset") => subset(rest),
        Some("prewarm") => prewarm(rest),
        _ => Err("usage: palette-host session|run-worker|broker|subset|prewarm ...".into()),
    };
    std::process::exit(match code {
        Ok(c) => c,
        Err(e) => {
            eprintln!("palette-host: {e}");
            2
        }
    });
}
