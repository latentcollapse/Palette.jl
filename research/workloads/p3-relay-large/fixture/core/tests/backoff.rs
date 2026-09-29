use relay_core::schedule;

#[test]
fn doubles_until_the_cap() {
    assert_eq!(schedule(100, 2, 1000, 6), vec![100, 200, 400, 800, 1000, 1000]);
}

#[test]
fn factor_one_is_constant() {
    assert_eq!(schedule(250, 1, 1000, 3), vec![250, 250, 250]);
}

#[test]
fn base_above_cap_is_capped() {
    assert_eq!(schedule(5000, 3, 1200, 2), vec![1200, 1200]);
}

#[test]
fn zero_attempts() {
    assert_eq!(schedule(100, 2, 1000, 0), Vec::<u64>::new());
}

#[test]
fn never_overflows() {
    let s = schedule(u64::MAX / 2, 10, u64::MAX, 5);
    assert_eq!(s, vec![u64::MAX / 2, u64::MAX, u64::MAX, u64::MAX, u64::MAX]);
    assert_eq!(schedule(3, 1_000_000, u64::MAX, 8).last(), Some(&u64::MAX));
}

#[test]
fn factor_zero_means_no_growth() {
    assert_eq!(schedule(100, 0, 1000, 3), vec![100, 100, 100]);
}
