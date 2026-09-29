//! The second trust domain: the capability broker. It runs outside the
//! sandbox; the worker reaches it only through one Unix socket bound into the
//! sandbox. One JSON request per connection, one JSON response:
//!     {"id", "category", "params"}  ->  {"id", "approved", "result" | "reason"}
//! Authorize against the session's fixed ceiling, perform the effect here with
//! host privilege (the worker has no code path to it), and write a receipt
//! for every request, approved or not.

use crate::sandbox::{self, RunWorker};
use crate::util;
use serde_json::{json, Map, Value};
use std::collections::BTreeMap;
use std::fs::{self, OpenOptions};
use std::io::{BufRead, BufReader, Read, Write};
use std::os::unix::fs::PermissionsExt;
use std::os::unix::net::{UnixListener, UnixStream};
use std::path::{Path, PathBuf};
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::{Arc, Mutex};
use std::time::Duration;

/// What the agent host does for a `host_request`: (type, payload) -> reply
/// ({"status": "ok", "result"} or {"status": "error", "error"}). Set by the
/// process that owns the session, never by a request.
pub type HostBridge = Arc<dyn Fn(&str, &Value) -> Value + Send + Sync>;

enum Fail {
    /// A policy decision.
    Denied(String),
    /// A bug or an effect that failed; receipted as such, not as policy.
    Internal(String),
}
use Fail::{Denied, Internal};

fn obj(v: &Value) -> Map<String, Value> {
    v.as_object().cloned().unwrap_or_default()
}

fn str_list(v: Option<&Value>) -> Option<Vec<String>> {
    v?.as_array().map(|a| a.iter().filter_map(|x| x.as_str().map(str::to_string)).collect())
}

/// C_child ⊆ C_caller. Fails closed: a category the parent lacks, or one this
/// broker does not know, is denied -- never ignored.
pub fn ceiling_is_subset(requested: &Value, parent: &Value) -> (bool, String) {
    let (req, par) = (obj(requested), obj(parent));
    for (category, rc) in &req {
        // Key presence, not truthiness: an empty `{}` grant is still a grant.
        let Some(pc) = par.get(category) else {
            return (false, format!("category {} is not present in the parent's ceiling at all", q(category)));
        };
        let (rc, pc) = (obj(rc), obj(pc));
        match category.as_str() {
            "external_fs_write" => {
                let rd: Vec<PathBuf> = str_list(rc.get("allowed_dirs")).unwrap_or_default().iter().map(|d| util::resolve(Path::new(d))).collect();
                let pd: Vec<PathBuf> = str_list(pc.get("allowed_dirs")).unwrap_or_default().iter().map(|d| util::resolve(Path::new(d))).collect();
                for d in &rd {
                    if !pd.iter().any(|p| util::within(d, p)) {
                        return (false, format!("requested external_fs_write dir {} is not within any parent allowed_dir {}", d.display(), qpaths(&pd)));
                    }
                }
            }
            "network_access" => {
                let r_allowed = rc.get("allowed").and_then(Value::as_bool).unwrap_or(false);
                if r_allowed && !pc.get("allowed").and_then(Value::as_bool).unwrap_or(false) {
                    return (false, "requested network_access=true but parent's ceiling has network_access=false".into());
                }
                let rh = str_list(rc.get("allowed_hosts"));
                let ph = str_list(pc.get("allowed_hosts"));
                // Omitting allowed_hosts means unrestricted, which is wider
                // than a host-restricted parent.
                if r_allowed && ph.is_some() && rh.is_none() {
                    return (false, "parent's network_access is restricted to allowed_hosts; a child request must name its own allowed_hosts subset explicitly, not omit it (omitting it means unrestricted)".into());
                }
                if let (Some(rh), Some(ph)) = (&rh, &ph) {
                    if !rh.iter().all(|h| ph.contains(h)) {
                        return (false, format!("requested allowed_hosts {} is not a subset of parent's {}", ql(rh), ql(ph)));
                    }
                }
            }
            "package_management" => {
                let Some(rp) = str_list(rc.get("allowed_packages")) else {
                    return (false, "requested package_management must name allowed_packages explicitly (no unrestricted child grant)".into());
                };
                if let Some(pp) = str_list(pc.get("allowed_packages")) {
                    if !rp.iter().all(|p| pp.contains(p)) {
                        return (false, format!("requested allowed_packages {} is not a subset of parent's {}", ql(&rp), ql(&pp)));
                    }
                }
            }
            // A grandchild's own ceiling is checked against this child's when it is spawned.
            "spawn_child_worker" => {}
            "host_request" => {
                let Some(rt) = str_list(rc.get("allowed_types")).filter(|_| rc.get("allowed_types").is_some_and(Value::is_array)) else {
                    return (false, "requested host_request must name allowed_types explicitly (no unrestricted child grant)".into());
                };
                let pt = str_list(pc.get("allowed_types")).unwrap_or_default();
                if !rt.iter().all(|t| pt.contains(t)) {
                    return (false, format!("requested host_request types {} are not a subset of parent's {}", ql(&rt), ql(&pt)));
                }
            }
            _ => return (false, format!("unrecognized category {} cannot be validated as a subset -- denied, not ignored", q(category))),
        }
    }
    (true, String::new())
}

pub struct Broker {
    ceiling: Value,
    receipt_log_path: PathBuf,
    session_id: String,
    // Trusted paths fixed when the session starts; never taken from a request.
    depot_dir: Option<String>,
    project_dir: Option<String>,
    repo_dir: Option<String>,
    child_timeout: Duration,
    host_bridge: Mutex<Option<HostBridge>>,
    log_lock: Mutex<()>,
    depot_lock: Mutex<()>,
}

pub struct BrokerConfig {
    pub ceiling: Value,
    pub receipt_log_path: PathBuf,
    pub session_id: String,
    pub depot_dir: Option<String>,
    pub project_dir: Option<String>,
    pub repo_dir: Option<String>,
    pub child_timeout: Duration,
}

impl Broker {
    pub fn new(c: BrokerConfig) -> Result<Broker, String> {
        if let Some(parent) = c.receipt_log_path.parent() {
            fs::create_dir_all(parent).map_err(|e| e.to_string())?;
        }
        Ok(Broker {
            ceiling: c.ceiling,
            receipt_log_path: c.receipt_log_path,
            session_id: c.session_id,
            depot_dir: c.depot_dir,
            project_dir: c.project_dir,
            repo_dir: c.repo_dir,
            child_timeout: c.child_timeout,
            host_bridge: Mutex::new(None),
            log_lock: Mutex::new(()),
            depot_lock: Mutex::new(()),
        })
    }

    pub fn set_host_bridge(&self, bridge: HostBridge) {
        *self.host_bridge.lock().unwrap() = Some(bridge);
    }

    fn cap(&self, category: &str) -> Option<Map<String, Value>> {
        self.ceiling.get(category).map(obj)
    }

    fn external_fs_write(&self, p: &Map<String, Value>) -> Result<Value, Fail> {
        let cap = self.cap("external_fs_write").unwrap_or_default();
        let dirs = str_list(cap.get("allowed_dirs")).unwrap_or_default();
        if dirs.is_empty() {
            return Err(Denied("external_fs_write is not in this session's capability ceiling".into()));
        }
        let (Some(path), Some(content)) = (p.get("path").and_then(Value::as_str), p.get("content").and_then(Value::as_str)) else {
            return Err(Denied("external_fs_write requires string 'path' and 'content'".into()));
        };
        if path.contains('\0') {
            return Err(Internal("internal error handling request (not a policy denial): embedded null byte".into()));
        }
        let target = util::resolve(Path::new(path));
        let allowed: Vec<PathBuf> = dirs.iter().map(|d| util::resolve(Path::new(d))).collect();
        if !allowed.iter().any(|a| util::within(&target, a)) {
            return Err(Denied(format!("path {} is outside the ceiling's allowed_dirs {}", target.display(), qpaths(&allowed))));
        }
        if let Some(parent) = target.parent() {
            fs::create_dir_all(parent).map_err(|e| Internal(e.to_string()))?;
        }
        fs::write(&target, content).map_err(|e| Internal(e.to_string()))?;
        Ok(json!({"path": target.to_string_lossy(), "bytes_written": content.len()}))
    }

    fn network_access(&self, p: &Map<String, Value>) -> Result<Value, Fail> {
        let cap = self.cap("network_access").unwrap_or_default();
        if !cap.get("allowed").and_then(Value::as_bool).unwrap_or(false) {
            return Err(Denied("network_access is not in this session's capability ceiling".into()));
        }
        let Some(url) = p.get("url").and_then(Value::as_str) else {
            return Err(Denied("network_access requires a string 'url'".into()));
        };
        // A scheme allowlist: a network grant must not double as a host file read (file://).
        let (scheme, rest) = url.split_once("://").unwrap_or(("", ""));
        let scheme = scheme.to_ascii_lowercase();
        if scheme != "http" && scheme != "https" {
            return Err(Denied(format!("network_access only permits http/https URLs, got scheme {}", q(&scheme))));
        }
        if let Some(hosts) = str_list(cap.get("allowed_hosts")) {
            let authority = rest.split(['/', '?', '#']).next().unwrap_or("");
            let hostport = authority.rsplit('@').next().unwrap_or("");
            let host = if let Some(h) = hostport.strip_prefix('[') {
                h.split(']').next().unwrap_or("").to_ascii_lowercase()
            } else {
                hostport.split(':').next().unwrap_or("").to_ascii_lowercase()
            };
            if !hosts.contains(&host) {
                return Err(Denied(format!("host {host} is not in this session's allowed_hosts {}", ql(&hosts))));
            }
        }
        // No redirect-following: a redirect target is a URL the allowlist was
        // never asked about. A 3xx comes back as data.
        let agent = ureq::AgentBuilder::new().redirects(0).timeout(Duration::from_secs(5)).build();
        let resp = match agent.get(url).call() {
            Ok(r) => r,
            Err(ureq::Error::Status(_, r)) => r,
            Err(e) => return Err(Internal(format!("internal error handling request (not a policy denial): {e}"))),
        };
        let status = resp.status();
        let mut body = Vec::new();
        let _ = resp.into_reader().take(2048).read_to_end(&mut body);
        body.truncate(200);
        Ok(json!({"url": url, "status": status, "body_prefix": String::from_utf8_lossy(&body)}))
    }

    fn package_management(&self, p: &Map<String, Value>) -> Result<Value, Fail> {
        let cap = self.cap("package_management").unwrap_or_default();
        let Some(allowed) = str_list(cap.get("allowed_packages")) else {
            return Err(Denied("package_management is not in this session's capability ceiling".into()));
        };
        let Some(depot) = &self.depot_dir else {
            return Err(Denied("no session depot is configured for this broker -- package_management requires one".into()));
        };
        let name = p.get("name").and_then(Value::as_str).unwrap_or("");
        let ident = !name.is_empty()
            && name.starts_with(|c: char| c.is_ascii_alphabetic() || c == '_')
            && name.chars().all(|c| c.is_ascii_alphanumeric() || c == '_');
        if !ident {
            return Err(Denied("package_management requires a string 'name' that is a valid Julia identifier".into()));
        }
        let version = match p.get("version") {
            None | Some(Value::Null) => None,
            Some(Value::String(v)) if valid_version(v) => Some(v.clone()),
            _ => return Err(Denied("package_management's 'version', if given, must look like '1', '1.2', or '1.2.3'".into())),
        };
        if !allowed.iter().any(|a| a == name) {
            return Err(Denied(format!("package {} is not in this session's allowed_packages {}", q(name), ql(&allowed))));
        }
        let spec = match &version {
            Some(v) => format!("name=\"{name}\", version=\"{v}\""),
            None => format!("name=\"{name}\""),
        };
        let mut env = BTreeMap::new();
        env.insert("JULIA_DEPOT_PATH".to_string(), Some(depot.clone()));
        env.insert("JULIA_PROJECT".to_string(), None);
        let argv: Vec<String> = vec!["julia".into(), "--startup-file=no".into(), "-e".into(),
                                     format!("using Pkg; Pkg.add(Pkg.PackageSpec({spec}))")];
        let r = {
            let _g = self.depot_lock.lock().unwrap();
            sandbox::run_captured(&argv, Some(&env), Duration::from_secs(300)).map_err(Internal)?
        };
        if r.returncode != 0 || r.timed_out {
            return Err(Denied(format!("Pkg.add({}) failed: {}", q(name), util::tail(&r.stderr, 800))));
        }
        Ok(json!({"name": name, "version": version, "installed": true, "stdout_tail": util::tail(&r.stdout, 500)}))
    }

    /// C_child ⊆ C_caller, enforced here. A request chooses which capabilities
    /// the child gets, never where its filesystem view points. A child's
    /// network namespace is always unshared: network_access for a child means
    /// asking its own broker, which enforces its already-validated ceiling.
    fn spawn_child_worker(&self, p: &Map<String, Value>) -> Result<Value, Fail> {
        let requested = p.get("ceiling").cloned().unwrap_or_else(|| json!({}));
        if !requested.is_object() {
            return Err(Denied("spawn_child_worker requires a 'ceiling' object".into()));
        }
        let (ok, reason) = ceiling_is_subset(&requested, &self.ceiling);
        if !ok {
            return Err(Denied(format!("requested child ceiling is not a subset of this session's ceiling: {reason}")));
        }
        let (Some(project), Some(repo)) = (&self.project_dir, &self.repo_dir) else {
            return Err(Denied("no session project/repo is configured for this broker -- spawn_child_worker requires one".into()));
        };
        let Some(script) = p.get("script").and_then(Value::as_str) else {
            return Err(Denied("spawn_child_worker requires a string 'script'".into()));
        };
        let ws = util::mkdtemp("neurajl-child-ws-").map_err(|e| Internal(e.to_string()))?;
        let child_depot = if requested.get("package_management").is_some() {
            Some(sandbox::create_session_depot(None).map_err(Internal)?)
        } else {
            None
        };
        let sock_dir = util::mkdtemp("neurajl-child-broker-").map_err(|e| Internal(e.to_string()))?;
        let result = (|| {
            let child = Arc::new(Broker::new(BrokerConfig {
                ceiling: requested.clone(),
                receipt_log_path: sock_dir.join("receipts.jsonl"),
                session_id: format!("{}/child", self.session_id),
                depot_dir: child_depot.as_ref().map(|d| d.to_string_lossy().into_owned()),
                project_dir: Some(project.clone()),
                repo_dir: Some(repo.clone()),
                child_timeout: Duration::from_secs(90),
            }).map_err(Internal)?);
            let server = serve(&sock_dir.join("broker.sock"), child).map_err(Internal)?;
            let r = sandbox::run_worker(&RunWorker {
                workspace_dir: &ws.to_string_lossy(),
                project_dir: project,
                repo_dir: repo,
                script,
                broker_socket_dir: Some(&sock_dir.to_string_lossy()),
                network_enabled: false,
                depot_clone_dir: child_depot.as_ref().map(|d| d.to_str().unwrap_or_default()),
                timeout: self.child_timeout,
            });
            server.shutdown();
            let r = r.map_err(Internal)?;
            if r.timed_out {
                return Err(Denied(format!("child worker exceeded its {}s time limit and was killed",
                                          util::fmt_g(self.child_timeout.as_secs_f64()))));
            }
            Ok(json!({"returncode": r.returncode, "stdout": util::tail(&r.stdout, 4000), "stderr": util::tail(&r.stderr, 2000)}))
        })();
        let _ = fs::remove_dir_all(&sock_dir);
        let _ = fs::remove_dir_all(&ws);
        if let Some(d) = child_depot {
            let _ = fs::remove_dir_all(d);
        }
        result
    }

    /// Ask the agent host to act for the kernel (an RLM child, for instance),
    /// for the request types the ceiling names. The host's reply -- its
    /// success or its own error -- is the result.
    fn host_request(&self, p: &Map<String, Value>) -> Result<Value, Fail> {
        let Some(cap) = self.cap("host_request") else {
            return Err(Denied("host_request not in this session's ceiling".into()));
        };
        let rtype = p.get("type").and_then(Value::as_str).unwrap_or("");
        if rtype.is_empty() {
            return Err(Denied("host_request requires a non-empty string 'type'".into()));
        }
        if !str_list(cap.get("allowed_types")).unwrap_or_default().iter().any(|t| t == rtype) {
            return Err(Denied(format!("host_request type {} is not in this session's allowed_types", q(rtype))));
        }
        let payload = p.get("payload").cloned().unwrap_or_else(|| json!({}));
        if !payload.is_object() {
            return Err(Denied("host_request 'payload' must be an object".into()));
        }
        let bridge = self.host_bridge.lock().unwrap().clone();
        let Some(bridge) = bridge else {
            return Err(Denied("no agent host is attached to this session".into()));
        };
        let reply = bridge(rtype, &payload);
        match reply.get("status").and_then(Value::as_str) {
            Some("ok") | Some("error") => Ok(reply),
            _ => Err(Internal(format!("internal error handling request (not a policy denial): host returned a malformed reply to {}", q(rtype)))),
        }
    }

    pub fn handle_request(&self, req: &Value) -> Value {
        let req_id = req.get("id").cloned().unwrap_or_else(|| json!(util::uuid4()));
        let category = req.get("category").cloned().unwrap_or(Value::Null);
        let params = req.get("params").cloned().unwrap_or_else(|| json!({}));
        let p = obj(&params);
        let outcome = match category.as_str() {
            Some("external_fs_write") => self.external_fs_write(&p),
            Some("network_access") => self.network_access(&p),
            Some("package_management") => self.package_management(&p),
            Some("spawn_child_worker") => self.spawn_child_worker(&p),
            Some("host_request") => self.host_request(&p),
            _ => Err(Denied(format!("unknown capability category: {}", py_repr(&category)))),
        };
        let (approved, result, reason) = match outcome {
            Ok(r) => (true, r, Value::Null),
            Err(Denied(r)) => (false, Value::Null, json!(r)),
            Err(Internal(r)) => {
                let r = if r.starts_with("internal error handling request") { r } else { format!("internal error handling request (not a policy denial): {r}") };
                (false, Value::Null, json!(r))
            }
        };
        self.write_receipt(&req_id, &category, &params, approved, &result, &reason);
        let mut resp = json!({"id": req_id, "approved": approved});
        if approved {
            resp["result"] = result;
        } else {
            resp["reason"] = reason;
        }
        resp
    }

    fn write_receipt(&self, req_id: &Value, category: &Value, params: &Value, approved: bool, result: &Value, reason: &Value) {
        let receipt = json!({
            "receipt_id": util::uuid4(), "request_id": req_id, "session_id": self.session_id,
            "timestamp": util::now_secs(), "category": category, "params": params,
            "approved": approved, "result": result, "reason": reason,
        });
        let _g = self.log_lock.lock().unwrap();
        if let Ok(mut f) = OpenOptions::new().create(true).append(true).open(&self.receipt_log_path) {
            let _ = writeln!(f, "{receipt}");
        }
    }
}

fn valid_version(v: &str) -> bool {
    let parts: Vec<&str> = v.split('.').collect();
    (1..=3).contains(&parts.len()) && parts.iter().all(|p| !p.is_empty() && p.chars().all(|c| c.is_ascii_digit()))
}

/// Python's repr of a string, as the messages have always read.
fn q(s: &str) -> String {
    format!("'{s}'")
}

fn ql<S: AsRef<str>>(xs: &[S]) -> String {
    format!("[{}]", xs.iter().map(|x| q(x.as_ref())).collect::<Vec<_>>().join(", "))
}

fn qpaths(ps: &[PathBuf]) -> String {
    format!("[{}]", ps.iter().map(|p| format!("PosixPath('{}')", p.display())).collect::<Vec<_>>().join(", "))
}

fn py_repr(v: &Value) -> String {
    match v {
        Value::Null => "None".into(),
        Value::String(s) => format!("'{s}'"),
        other => other.to_string(),
    }
}

/// A worker holding unbounded power inside its sandbox is still an untrusted
/// client of this host process: an unterminated stream must not buffer forever.
const MAX_REQUEST_BYTES: usize = 1 << 20;

pub struct BrokerServer {
    path: PathBuf,
    stop: Arc<AtomicBool>,
    thread: Option<std::thread::JoinHandle<()>>,
}

impl BrokerServer {
    pub fn shutdown(mut self) {
        self.stop_now();
    }

    fn stop_now(&mut self) {
        self.stop.store(true, Ordering::SeqCst);
        let _ = UnixStream::connect(&self.path); // wake the accept loop
        if let Some(t) = self.thread.take() {
            let _ = t.join();
        }
        let _ = fs::remove_file(&self.path);
    }
}

impl Drop for BrokerServer {
    fn drop(&mut self) {
        if self.thread.is_some() {
            self.stop_now();
        }
    }
}

pub fn serve(sock_path: &Path, broker: Arc<Broker>) -> Result<BrokerServer, String> {
    let _ = fs::remove_file(sock_path);
    let listener = UnixListener::bind(sock_path).map_err(|e| format!("binding {}: {e}", sock_path.display()))?;
    // The sandboxed worker connects under a different uid view.
    fs::set_permissions(sock_path, fs::Permissions::from_mode(0o666)).map_err(|e| e.to_string())?;
    let stop = Arc::new(AtomicBool::new(false));
    let stop2 = stop.clone();
    let thread = std::thread::spawn(move || {
        for conn in listener.incoming() {
            if stop2.load(Ordering::SeqCst) {
                break;
            }
            let Ok(conn) = conn else { continue };
            let b = broker.clone();
            std::thread::spawn(move || handle_conn(conn, &b));
        }
    });
    Ok(BrokerServer { path: sock_path.to_path_buf(), stop, thread: Some(thread) })
}

fn handle_conn(conn: UnixStream, broker: &Broker) {
    let mut writer = match conn.try_clone() {
        Ok(w) => w,
        Err(_) => return,
    };
    let mut reader = BufReader::new(conn.take(MAX_REQUEST_BYTES as u64));
    let mut line = Vec::new();
    if reader.read_until(b'\n', &mut line).unwrap_or(0) == 0 {
        return;
    }
    let reply = if line.len() >= MAX_REQUEST_BYTES && !line.ends_with(b"\n") {
        json!({"approved": false, "reason": "request exceeds maximum size"})
    } else {
        match serde_json::from_slice::<Value>(&line) {
            Ok(req) => broker.handle_request(&req),
            Err(e) => json!({"approved": false, "reason": format!("broker error: {e}")}),
        }
    };
    let _ = writeln!(writer, "{reply}");
    let _ = writer.flush();
}
