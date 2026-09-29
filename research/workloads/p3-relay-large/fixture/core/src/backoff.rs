//! Retry delays. See SPEC.md, "core: backoff".

pub fn schedule(base_ms: u64, factor: u32, cap_ms: u64, attempts: usize) -> Vec<u64> {
    let _ = (base_ms, factor, cap_ms, attempts);
    todo!("schedule")
}
