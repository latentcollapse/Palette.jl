//! Retry delays. See SPEC.md, "core: backoff".

pub fn schedule(base_ms: u64, factor: u32, cap_ms: u64, attempts: usize) -> Vec<u64> {
    let f = u64::from(factor.max(1));
    let mut d = base_ms;
    (0..attempts)
        .map(|_| {
            let out = d.min(cap_ms);
            d = d.saturating_mul(f);
            out
        })
        .collect()
}
