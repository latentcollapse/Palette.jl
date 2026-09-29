use relay_core::{quantiles, QuantileError};

fn close(a: &[f64], b: &[f64]) -> bool {
    a.len() == b.len() && a.iter().zip(b).all(|(x, y)| (x - y).abs() < 1e-9)
}

#[test]
fn median_of_odd_and_even_samples() {
    assert!(close(&quantiles(&[3.0, 1.0, 2.0], &[0.5]).unwrap(), &[2.0]));
    assert!(close(&quantiles(&[4.0, 1.0, 3.0, 2.0], &[0.5]).unwrap(), &[2.5]));
}

#[test]
fn linear_interpolation_between_ranks() {
    let xs = [10.0, 20.0, 30.0, 40.0, 50.0];
    assert!(close(&quantiles(&xs, &[0.0, 0.25, 0.9, 1.0]).unwrap(), &[10.0, 20.0, 46.0, 50.0]));
    assert!(close(&quantiles(&[1.0, 2.0], &[0.95, 0.99]).unwrap(), &[1.95, 1.99]));
}

#[test]
fn nan_is_ignored() {
    assert!(close(&quantiles(&[f64::NAN, 5.0, 1.0, f64::NAN], &[0.5]).unwrap(), &[3.0]));
}

#[test]
fn single_value() {
    assert!(close(&quantiles(&[7.0], &[0.0, 0.5, 1.0]).unwrap(), &[7.0, 7.0, 7.0]));
}

#[test]
fn errors() {
    assert_eq!(quantiles(&[], &[0.5]), Err(QuantileError::Empty));
    assert_eq!(quantiles(&[f64::NAN], &[0.5]), Err(QuantileError::Empty));
    assert_eq!(quantiles(&[1.0], &[1.5]), Err(QuantileError::BadQuantile(1.5)));
    assert_eq!(quantiles(&[1.0], &[-0.1]), Err(QuantileError::BadQuantile(-0.1)));
}

#[test]
fn quantiles_keep_the_order_asked() {
    assert!(close(&quantiles(&[1.0, 2.0, 3.0], &[1.0, 0.0]).unwrap(), &[3.0, 1.0]));
}
