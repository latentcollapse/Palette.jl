use relay_core::{moving_average, score_record, Record};

#[test]
fn score_is_capped() {
    assert_eq!(score_record(&Record { id: 1, weight: 30.0, hits: 5 }), 100.0);
    assert_eq!(score_record(&Record { id: 2, weight: 2.5, hits: 4 }), 10.0);
}

#[test]
fn moving_average_covers_every_window() {
    assert_eq!(moving_average(&[1.0, 2.0, 3.0, 4.0], 2), vec![1.5, 2.5, 3.5]);
    assert_eq!(moving_average(&[5.0], 1), vec![5.0]);
    assert_eq!(moving_average(&[1.0], 2), Vec::<f64>::new());
}
