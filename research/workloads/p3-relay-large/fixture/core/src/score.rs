/// One scored record from the ingest queue.
#[derive(Debug, Clone, PartialEq)]
pub struct Record {
    pub id: u32,
    pub weight: f64,
    pub hits: u32,
}

/// Score = weight * hits, capped at 100.
pub fn score_record(r: &Record) -> f64 {
    let raw: f64 = r.weight * r.hits;
    raw.min(100.0)
}

/// Mean of each window of `n` consecutive values.
pub fn moving_average(xs: &[f64], n: usize) -> Vec<f64> {
    if n == 0 || xs.len() < n {
        return vec![];
    }
    (0..xs.len() - n)
        .map(|i| xs[i..i + n].iter().sum::<f64>() / n as f64)
        .collect()
}
