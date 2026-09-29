//! Quantiles of a latency sample. See SPEC.md, "core: quantiles".

#[derive(Debug, PartialEq)]
pub enum QuantileError {
    Empty,
    BadQuantile(f64),
}

pub fn quantiles(xs: &[f64], qs: &[f64]) -> Result<Vec<f64>, QuantileError> {
    let mut v: Vec<f64> = xs.iter().copied().filter(|x| !x.is_nan()).collect();
    if v.is_empty() {
        return Err(QuantileError::Empty);
    }
    if let Some(&q) = qs.iter().find(|q| !(0.0..=1.0).contains(*q)) {
        return Err(QuantileError::BadQuantile(q));
    }
    v.sort_by(|a, b| a.partial_cmp(b).unwrap());
    let n = v.len();
    Ok(qs
        .iter()
        .map(|q| {
            let h = (n - 1) as f64 * q;
            let lo = h.floor() as usize;
            if lo + 1 >= n { v[n - 1] } else { v[lo] + (h - lo as f64) * (v[lo + 1] - v[lo]) }
        })
        .collect())
}
