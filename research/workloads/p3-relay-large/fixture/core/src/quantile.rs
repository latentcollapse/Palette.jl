//! Quantiles of a latency sample. See SPEC.md, "core: quantiles".

#[derive(Debug, PartialEq)]
pub enum QuantileError {
    Empty,
    BadQuantile(f64),
}

pub fn quantiles(xs: &[f64], qs: &[f64]) -> Result<Vec<f64>, QuantileError> {
    let _ = (xs, qs);
    todo!("quantiles")
}
