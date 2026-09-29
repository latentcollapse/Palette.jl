use relay_core::count_events;

#[test]
fn events_are_all_counted() {
    // 4 workers x 2000 events, plus one end-of-batch marker each.
    assert_eq!(count_events(4, 2000), 8004);
}
