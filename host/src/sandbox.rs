//! The first trust domain: a bubblewrap sandbox around an unrestricted
//! `julia`. Full language power inside, bounded by the OS outside it. Paths
//! are bound at the same guest path as on the host, because Julia's manifests
//! and precompile caches embed absolute paths. Each worker gets its own
//! reflink clone of the depot as its single writable depot entry: a split
//! JULIA_DEPOT_PATH makes Julia recompute stdlib build ids and invalidate
//! every precompiled cache on each launch.

use crate::util;
use std::collections::BTreeMap;
use std::fs;
use std::io::Read;
use std::path::{Path, PathBuf};
use std::process::{Command, Stdio};
use std::time::{Duration, Instant};

pub const SANDBOX_USER: &str = "neura";
/// The sandbox sets these itself; a task environment cannot move them.
const SANDBOX_OWNED_ENV: &[&str] = &[
    "PATH", "HOME", "USER", "LOGNAME", "LANG", "JULIA_DEPOT_PATH", "JULIA_PROJECT", "JULIA_LOAD_PATH",
    "JULIA_PKG_OFFLINE", "PALETTE_REPO_DIR", "PALETTE_STATE_DIR", "PALETTE_BROKER_SOCKET",
];

/// The real julia binary, past the juliaup shim. An explicit PALETTE_JULIA_BIN
/// wins: asked under a fresh HOME, the shim installs its current default
/// release, and an endurance run got a Julia the depot was not built for.
/// stdin is never inherited: `julia -e` with the caller's stdin breaks the
/// caller's later reads from it, and the session reads its requests there.
pub fn resolve_julia() -> Result<String, String> {
    if let Ok(pinned) = std::env::var("PALETTE_JULIA_BIN") {
        if !pinned.is_empty() {
            if !Path::new(&pinned).is_file() {
                return Err(format!("PALETTE_JULIA_BIN is not a file: {pinned}"));
            }
            return Ok(pinned);
        }
    }
    let out = Command::new("julia")
        .args(["-e", "print(Sys.BINDIR)"])
        .stdin(Stdio::null())
        .output()
        .map_err(|e| format!("could not run julia to find its binary: {e}"))?;
    if !out.status.success() {
        return Err("julia -e print(Sys.BINDIR) failed".into());
    }
    Ok(format!("{}/julia", String::from_utf8_lossy(&out.stdout).trim()))
}

pub fn default_depot() -> String {
    std::env::var("JULIA_DEPOT_PATH")
        .ok()
        .and_then(|v| v.split(':').next_back().map(str::to_string))
        .filter(|s| !s.is_empty())
        .unwrap_or_else(|| util::home().join(".julia").to_string_lossy().into_owned())
}

/// One private, writable depot clone, shared by a whole session: the broker's
/// package installs go into the same directory a running worker has bound.
pub fn create_session_depot(real_depot: Option<&str>) -> Result<PathBuf, String> {
    let depot = real_depot.map(str::to_string).unwrap_or_else(default_depot);
    let root = Path::new(&depot).parent().unwrap_or(Path::new("/")).join(".palette-depot-clones");
    fs::create_dir_all(&root).map_err(|e| format!("creating {}: {e}", root.display()))?;
    let dest = util::mkdtemp_in(&root, "depot-").map_err(|e| e.to_string())?;
    let _ = fs::remove_dir(&dest); // cp wants a destination that does not exist yet
    let status = Command::new("cp")
        .args(["-a", "--reflink=auto"])
        .arg(&depot)
        .arg(&dest)
        .stdin(Stdio::null())
        .status()
        .map_err(|e| format!("cp: {e}"))?;
    if !status.success() {
        let _ = fs::remove_dir_all(&dest);
        return Err(format!("cloning the depot {depot} failed"));
    }
    Ok(dest)
}

/// A benchmark's toolchain activation (KEY=VALUE lines), given to the kernel
/// as the other contestants get it.
pub fn read_task_env(path: Option<&str>) -> Result<BTreeMap<String, String>, String> {
    let mut env = BTreeMap::new();
    let Some(path) = path.filter(|p| !p.is_empty()) else { return Ok(env) };
    let text = fs::read_to_string(path).map_err(|e| format!("NIRA_TASK_ENV {path}: {e}"))?;
    for line in text.lines() {
        if line.trim().is_empty() || line.trim_start().starts_with('#') {
            continue;
        }
        let Some((key, value)) = line.split_once('=') else {
            return Err(format!("NIRA_TASK_ENV: not a KEY=VALUE line: {line:?}"));
        };
        let key = key.trim();
        let ident = !key.is_empty()
            && !key.starts_with(|c: char| c.is_ascii_digit())
            && key.chars().all(|c| c.is_alphanumeric() || c == '_');
        if !ident {
            return Err(format!("NIRA_TASK_ENV: not a KEY=VALUE line: {line:?}"));
        }
        if !SANDBOX_OWNED_ENV.contains(&key) {
            env.insert(key.to_string(), value.to_string());
        }
    }
    Ok(env)
}

/// passwd and group files naming the sandbox's uid 1000, written once per host.
fn identity_files() -> Result<PathBuf, String> {
    let uid = unsafe { libc::getuid() };
    let etc = util::temp_dir().join(format!("palette-etc-{uid}"));
    let passwd = format!("{SANDBOX_USER}:x:1000:1000:Palette sandbox:/run/palette/home:/bin/bash\n");
    let group = format!("{SANDBOX_USER}:x:1000:\n");
    if fs::read_to_string(etc.join("passwd")).ok().as_deref() != Some(passwd.as_str()) {
        use std::os::unix::fs::{DirBuilderExt, PermissionsExt};
        let _ = fs::DirBuilder::new().mode(0o755).create(&etc);
        for (name, text) in [("passwd", &passwd), ("group", &group)] {
            let tmp = etc.join(format!(".{name}.{}", std::process::id()));
            fs::write(&tmp, text).map_err(|e| e.to_string())?;
            fs::set_permissions(&tmp, fs::Permissions::from_mode(0o644)).map_err(|e| e.to_string())?;
            fs::rename(&tmp, etc.join(name)).map_err(|e| e.to_string())?;
        }
    }
    Ok(etc)
}

pub struct SandboxSpec<'a> {
    pub workspace_dir: &'a str,
    pub broker_socket_dir: Option<&'a str>,
    pub project_dir: &'a str,
    pub repo_dir: &'a str,
    pub julia_bin: &'a str,
    pub julia_depot: &'a str,
    pub network_enabled: bool,
    pub depot_clone_dir: Option<&'a str>,
    pub state_dir: Option<&'a str>,
}

pub fn build_bwrap_argv(s: &SandboxSpec) -> Result<Vec<String>, String> {
    let toolchain = Path::new(s.julia_bin).parent().and_then(Path::parent).unwrap_or(Path::new("/"));
    let toolchain = toolchain.to_string_lossy().into_owned();
    let task_tools = std::env::var("NIRA_TASK_TOOLS").ok().filter(|t| !t.is_empty());
    if let Some(t) = &task_tools {
        if !Path::new(t).join("bin").is_dir() {
            return Err(format!("NIRA_TASK_TOOLS has no bin directory: {t}"));
        }
    }
    let task_env = read_task_env(std::env::var("NIRA_TASK_ENV").ok().as_deref())?;

    let mut a: Vec<String> = Vec::new();
    let mut push = |xs: &[&str]| a.extend(xs.iter().map(|x| x.to_string()));
    // A new PID namespace whose PID 1 is bwrap's reaper, with julia as its
    // child: when julia exits, everything left in the namespace is killed --
    // background runs, double forks, daemons that ignore TERM and HUP.
    // --die-with-parent ends it if this process dies first.
    push(&["bwrap", "--unshare-user", "--uid", "1000", "--gid", "1000", "--disable-userns", "--assert-userns-disabled",
           "--unshare-pid", "--unshare-ipc"]);
    if !s.network_enabled {
        push(&["--unshare-net"]);
    }
    push(&["--proc", "/proc", "--dev", "/dev", "--tmpfs", "/tmp", "--dir", "/run/palette", "--tmpfs", "/run/palette",
           "--dir", "/run/palette/home", "--clearenv", "--die-with-parent", "--new-session", "--cap-drop", "ALL",
           // Preserve the host ELF loader layout (Ubuntu differs from Arch).
           "--ro-bind", "/usr", "/usr", "--symlink", "usr/lib", "/lib", "--ro-bind", "/lib64", "/lib64",
           "--symlink", "usr/bin", "/bin", "--ro-bind", "/etc/ld.so.cache", "/etc/ld.so.cache",
           "--ro-bind", &toolchain, &toolchain,
           // The depot, writable at its own real path; the source is this
           // worker's private clone, never the shared depot.
           "--bind", s.depot_clone_dir.unwrap_or(s.julia_depot), s.julia_depot,
           "--ro-bind", s.repo_dir, s.repo_dir,
           "--ro-bind", s.project_dir, s.project_dir,
           "--bind", s.workspace_dir, s.workspace_dir]);
    if let Some(t) = &task_tools {
        push(&["--ro-bind", t, t]);
    }
    if let Some(d) = s.broker_socket_dir {
        push(&["--ro-bind", d, d]);
    }
    let etc = identity_files()?;
    let (pw, gr) = (etc.join("passwd"), etc.join("group"));
    push(&["--ro-bind", &pw.to_string_lossy(), "/etc/passwd", "--ro-bind", &gr.to_string_lossy(), "/etc/group"]);
    // The persistent kernel's saved state, outside the task workspace.
    if let Some(st) = s.state_dir {
        push(&["--bind", st, st, "--setenv", "PALETTE_STATE_DIR", st]);
    }
    let path = match &task_tools {
        Some(t) => format!("{t}/bin:{toolchain}/bin:/usr/bin:/bin"),
        None => format!("{toolchain}/bin:/usr/bin:/bin"),
    };
    let load_path = format!("@:{}:@v#.#:@stdlib", s.project_dir);
    push(&["--setenv", "HOME", "/run/palette/home", "--setenv", "JULIA_DEPOT_PATH", s.julia_depot,
           "--setenv", "JULIA_PROJECT", s.project_dir,
           // The session project stays loadable after turn code activates another.
           "--setenv", "JULIA_LOAD_PATH", &load_path,
           "--setenv", "PALETTE_REPO_DIR", s.repo_dir, "--setenv", "PATH", &path,
           "--setenv", "LANG", "en_US.UTF-8", "--setenv", "USER", SANDBOX_USER, "--setenv", "LOGNAME", SANDBOX_USER,
           "--chdir", s.workspace_dir]);
    for (k, v) in &task_env {
        push(&["--setenv", k, v]);
    }
    if let Some(d) = s.broker_socket_dir {
        let sock = format!("{d}/broker.sock");
        push(&["--setenv", "PALETTE_BROKER_SOCKET", &sock]);
    }
    if !s.network_enabled {
        // Without it Pkg.add spends ~18 s per package on DNS retries.
        push(&["--setenv", "JULIA_PKG_OFFLINE", "true"]);
    }
    Ok(a)
}

pub struct WorkerResult {
    pub returncode: i32,
    pub stdout: String,
    pub stderr: String,
    pub timed_out: bool,
}

/// Run a child process to completion or `timeout`, capturing its output
/// (invalid UTF-8 replaced). A timed-out child is killed.
pub fn run_captured(argv: &[String], env: Option<&BTreeMap<String, Option<String>>>, timeout: Duration)
    -> Result<WorkerResult, String> {
    let mut cmd = Command::new(&argv[0]);
    cmd.args(&argv[1..]).stdin(Stdio::null()).stdout(Stdio::piped()).stderr(Stdio::piped());
    if let Some(env) = env {
        for (k, v) in env {
            match v {
                Some(v) => cmd.env(k, v),
                None => cmd.env_remove(k),
            };
        }
    }
    let mut child = cmd.spawn().map_err(|e| format!("starting {}: {e}", argv[0]))?;
    let mut out = child.stdout.take().unwrap();
    let mut err = child.stderr.take().unwrap();
    let t_out = std::thread::spawn(move || {
        let mut b = Vec::new();
        let _ = out.read_to_end(&mut b);
        b
    });
    let t_err = std::thread::spawn(move || {
        let mut b = Vec::new();
        let _ = err.read_to_end(&mut b);
        b
    });
    let deadline = Instant::now() + timeout;
    let mut timed_out = false;
    let status = loop {
        if let Some(st) = child.try_wait().map_err(|e| e.to_string())? {
            break st;
        }
        if Instant::now() >= deadline {
            timed_out = true;
            let _ = child.kill();
            break child.wait().map_err(|e| e.to_string())?;
        }
        std::thread::sleep(Duration::from_millis(20));
    };
    let stdout = String::from_utf8_lossy(&t_out.join().unwrap_or_default()).into_owned();
    let stderr = String::from_utf8_lossy(&t_err.join().unwrap_or_default()).into_owned();
    use std::os::unix::process::ExitStatusExt;
    let returncode = status.code().unwrap_or_else(|| -status.signal().unwrap_or(0));
    Ok(WorkerResult { returncode, stdout, stderr, timed_out })
}

pub struct RunWorker<'a> {
    pub workspace_dir: &'a str,
    pub project_dir: &'a str,
    pub repo_dir: &'a str,
    pub script: &'a str,
    pub broker_socket_dir: Option<&'a str>,
    pub network_enabled: bool,
    pub depot_clone_dir: Option<&'a str>,
    pub timeout: Duration,
}

/// One sandboxed `julia -e script`. A caller that owns a session-lifetime
/// depot clone passes it in; otherwise a fresh clone is made and removed.
pub fn run_worker(r: &RunWorker) -> Result<WorkerResult, String> {
    let julia = resolve_julia()?;
    let depot = default_depot();
    fs::create_dir_all(r.workspace_dir).map_err(|e| e.to_string())?;
    let owned = match r.depot_clone_dir {
        Some(_) => None,
        None => Some(create_session_depot(Some(&depot))?),
    };
    let clone = owned.as_ref().map(|p| p.to_string_lossy().into_owned());
    let result = (|| {
        let mut argv = build_bwrap_argv(&SandboxSpec {
            workspace_dir: r.workspace_dir,
            broker_socket_dir: r.broker_socket_dir,
            project_dir: r.project_dir,
            repo_dir: r.repo_dir,
            julia_bin: &julia,
            julia_depot: &depot,
            network_enabled: r.network_enabled,
            depot_clone_dir: r.depot_clone_dir.or(clone.as_deref()),
            state_dir: None,
        })?;
        argv.extend(["--".into(), julia.clone(), "--startup-file=no".into(), "-e".into(), r.script.into()]);
        run_captured(&argv, None, r.timeout)
    })();
    if let Some(p) = owned {
        let _ = fs::remove_dir_all(p);
    }
    result
}
