use relay_core::{score_record, Record};

#[test]
fn bulk_score_000() { assert_eq!(score_record(&Record { id: 0, weight: 0.5, hits: 0 }), (0.5_f64 * 0 as f64).min(100.0)); }
#[test]
fn bulk_score_001() { assert_eq!(score_record(&Record { id: 1, weight: 1.5, hits: 1 }), (1.5_f64 * 1 as f64).min(100.0)); }
#[test]
fn bulk_score_002() { assert_eq!(score_record(&Record { id: 2, weight: 2.5, hits: 2 }), (2.5_f64 * 2 as f64).min(100.0)); }
#[test]
fn bulk_score_003() { assert_eq!(score_record(&Record { id: 3, weight: 3.5, hits: 3 }), (3.5_f64 * 3 as f64).min(100.0)); }
#[test]
fn bulk_score_004() { assert_eq!(score_record(&Record { id: 4, weight: 4.5, hits: 4 }), (4.5_f64 * 4 as f64).min(100.0)); }
#[test]
fn bulk_score_005() { assert_eq!(score_record(&Record { id: 5, weight: 5.5, hits: 5 }), (5.5_f64 * 5 as f64).min(100.0)); }
#[test]
fn bulk_score_006() { assert_eq!(score_record(&Record { id: 6, weight: 6.5, hits: 6 }), (6.5_f64 * 6 as f64).min(100.0)); }
#[test]
fn bulk_score_007() { assert_eq!(score_record(&Record { id: 7, weight: 7.5, hits: 7 }), (7.5_f64 * 7 as f64).min(100.0)); }
#[test]
fn bulk_score_008() { assert_eq!(score_record(&Record { id: 8, weight: 8.5, hits: 8 }), (8.5_f64 * 8 as f64).min(100.0)); }
#[test]
fn bulk_score_009() { assert_eq!(score_record(&Record { id: 9, weight: 9.5, hits: 0 }), (9.5_f64 * 0 as f64).min(100.0)); }
#[test]
fn bulk_score_010() { assert_eq!(score_record(&Record { id: 10, weight: 10.5, hits: 1 }), (10.5_f64 * 1 as f64).min(100.0)); }
#[test]
fn bulk_score_011() { assert_eq!(score_record(&Record { id: 11, weight: 11.5, hits: 2 }), (11.5_f64 * 2 as f64).min(100.0)); }
#[test]
fn bulk_score_012() { assert_eq!(score_record(&Record { id: 12, weight: 12.5, hits: 3 }), (12.5_f64 * 3 as f64).min(100.0)); }
#[test]
fn bulk_score_013() { assert_eq!(score_record(&Record { id: 13, weight: 13.5, hits: 4 }), (13.5_f64 * 4 as f64).min(100.0)); }
#[test]
fn bulk_score_014() { assert_eq!(score_record(&Record { id: 14, weight: 14.5, hits: 5 }), (14.5_f64 * 5 as f64).min(100.0)); }
#[test]
fn bulk_score_015() { assert_eq!(score_record(&Record { id: 15, weight: 15.5, hits: 6 }), (15.5_f64 * 6 as f64).min(100.0)); }
#[test]
fn bulk_score_016() { assert_eq!(score_record(&Record { id: 16, weight: 16.5, hits: 7 }), (16.5_f64 * 7 as f64).min(100.0)); }
#[test]
fn bulk_score_017() { assert_eq!(score_record(&Record { id: 17, weight: 0.5, hits: 8 }), (0.5_f64 * 8 as f64).min(100.0)); }
#[test]
fn bulk_score_018() { assert_eq!(score_record(&Record { id: 18, weight: 1.5, hits: 0 }), (1.5_f64 * 0 as f64).min(100.0)); }
#[test]
fn bulk_score_019() { assert_eq!(score_record(&Record { id: 19, weight: 2.5, hits: 1 }), (2.5_f64 * 1 as f64).min(100.0)); }
#[test]
fn bulk_score_020() { assert_eq!(score_record(&Record { id: 20, weight: 3.5, hits: 2 }), (3.5_f64 * 2 as f64).min(100.0)); }
#[test]
fn bulk_score_021() { assert_eq!(score_record(&Record { id: 21, weight: 4.5, hits: 3 }), (4.5_f64 * 3 as f64).min(100.0)); }
#[test]
fn bulk_score_022() { assert_eq!(score_record(&Record { id: 22, weight: 5.5, hits: 4 }), (5.5_f64 * 4 as f64).min(100.0)); }
#[test]
fn bulk_score_023() { assert_eq!(score_record(&Record { id: 23, weight: 6.5, hits: 5 }), (6.5_f64 * 5 as f64).min(100.0)); }
#[test]
fn bulk_score_024() { assert_eq!(score_record(&Record { id: 24, weight: 7.5, hits: 6 }), (7.5_f64 * 6 as f64).min(100.0)); }
#[test]
fn bulk_score_025() { assert_eq!(score_record(&Record { id: 25, weight: 8.5, hits: 7 }), (8.5_f64 * 7 as f64).min(100.0)); }
#[test]
fn bulk_score_026() { assert_eq!(score_record(&Record { id: 26, weight: 9.5, hits: 8 }), (9.5_f64 * 8 as f64).min(100.0)); }
#[test]
fn bulk_score_027() { assert_eq!(score_record(&Record { id: 27, weight: 10.5, hits: 0 }), (10.5_f64 * 0 as f64).min(100.0)); }
#[test]
fn bulk_score_028() { assert_eq!(score_record(&Record { id: 28, weight: 11.5, hits: 1 }), (11.5_f64 * 1 as f64).min(100.0)); }
#[test]
fn bulk_score_029() { assert_eq!(score_record(&Record { id: 29, weight: 12.5, hits: 2 }), (12.5_f64 * 2 as f64).min(100.0)); }
#[test]
fn bulk_score_030() { assert_eq!(score_record(&Record { id: 30, weight: 13.5, hits: 3 }), (13.5_f64 * 3 as f64).min(100.0)); }
#[test]
fn bulk_score_031() { assert_eq!(score_record(&Record { id: 31, weight: 14.5, hits: 4 }), (14.5_f64 * 4 as f64).min(100.0)); }
#[test]
fn bulk_score_032() { assert_eq!(score_record(&Record { id: 32, weight: 15.5, hits: 5 }), (15.5_f64 * 5 as f64).min(100.0)); }
#[test]
fn bulk_score_033() { assert_eq!(score_record(&Record { id: 33, weight: 16.5, hits: 6 }), (16.5_f64 * 6 as f64).min(100.0)); }
#[test]
fn bulk_score_034() { assert_eq!(score_record(&Record { id: 34, weight: 0.5, hits: 7 }), (0.5_f64 * 7 as f64).min(100.0)); }
#[test]
fn bulk_score_035() { assert_eq!(score_record(&Record { id: 35, weight: 1.5, hits: 8 }), (1.5_f64 * 8 as f64).min(100.0)); }
#[test]
fn bulk_score_036() { assert_eq!(score_record(&Record { id: 36, weight: 2.5, hits: 0 }), (2.5_f64 * 0 as f64).min(100.0)); }
#[test]
fn bulk_score_037() { assert_eq!(score_record(&Record { id: 37, weight: 3.5, hits: 1 }), (3.5_f64 * 1 as f64).min(100.0)); }
#[test]
fn bulk_score_038() { assert_eq!(score_record(&Record { id: 38, weight: 4.5, hits: 2 }), (4.5_f64 * 2 as f64).min(100.0)); }
#[test]
fn bulk_score_039() { assert_eq!(score_record(&Record { id: 39, weight: 5.5, hits: 3 }), (5.5_f64 * 3 as f64).min(100.0)); }
#[test]
fn bulk_score_040() { assert_eq!(score_record(&Record { id: 40, weight: 6.5, hits: 4 }), (6.5_f64 * 4 as f64).min(100.0)); }
#[test]
fn bulk_score_041() { assert_eq!(score_record(&Record { id: 41, weight: 7.5, hits: 5 }), (7.5_f64 * 5 as f64).min(100.0)); }
#[test]
fn bulk_score_042() { assert_eq!(score_record(&Record { id: 42, weight: 8.5, hits: 6 }), (8.5_f64 * 6 as f64).min(100.0)); }
#[test]
fn bulk_score_043() { assert_eq!(score_record(&Record { id: 43, weight: 9.5, hits: 7 }), (9.5_f64 * 7 as f64).min(100.0)); }
#[test]
fn bulk_score_044() { assert_eq!(score_record(&Record { id: 44, weight: 10.5, hits: 8 }), (10.5_f64 * 8 as f64).min(100.0)); }
#[test]
fn bulk_score_045() { assert_eq!(score_record(&Record { id: 45, weight: 11.5, hits: 0 }), (11.5_f64 * 0 as f64).min(100.0)); }
#[test]
fn bulk_score_046() { assert_eq!(score_record(&Record { id: 46, weight: 12.5, hits: 1 }), (12.5_f64 * 1 as f64).min(100.0)); }
#[test]
fn bulk_score_047() { assert_eq!(score_record(&Record { id: 47, weight: 13.5, hits: 2 }), (13.5_f64 * 2 as f64).min(100.0)); }
#[test]
fn bulk_score_048() { assert_eq!(score_record(&Record { id: 48, weight: 14.5, hits: 3 }), (14.5_f64 * 3 as f64).min(100.0)); }
#[test]
fn bulk_score_049() { assert_eq!(score_record(&Record { id: 49, weight: 15.5, hits: 4 }), (15.5_f64 * 4 as f64).min(100.0)); }
#[test]
fn bulk_score_050() { assert_eq!(score_record(&Record { id: 50, weight: 16.5, hits: 5 }), (16.5_f64 * 5 as f64).min(100.0)); }
#[test]
fn bulk_score_051() { assert_eq!(score_record(&Record { id: 51, weight: 0.5, hits: 6 }), (0.5_f64 * 6 as f64).min(100.0)); }
#[test]
fn bulk_score_052() { assert_eq!(score_record(&Record { id: 52, weight: 1.5, hits: 7 }), (1.5_f64 * 7 as f64).min(100.0)); }
#[test]
fn bulk_score_053() { assert_eq!(score_record(&Record { id: 53, weight: 2.5, hits: 8 }), (2.5_f64 * 8 as f64).min(100.0)); }
#[test]
fn bulk_score_054() { assert_eq!(score_record(&Record { id: 54, weight: 3.5, hits: 0 }), (3.5_f64 * 0 as f64).min(100.0)); }
#[test]
fn bulk_score_055() { assert_eq!(score_record(&Record { id: 55, weight: 4.5, hits: 1 }), (4.5_f64 * 1 as f64).min(100.0)); }
#[test]
fn bulk_score_056() { assert_eq!(score_record(&Record { id: 56, weight: 5.5, hits: 2 }), (5.5_f64 * 2 as f64).min(100.0)); }
#[test]
fn bulk_score_057() { assert_eq!(score_record(&Record { id: 57, weight: 6.5, hits: 3 }), (6.5_f64 * 3 as f64).min(100.0)); }
#[test]
fn bulk_score_058() { assert_eq!(score_record(&Record { id: 58, weight: 7.5, hits: 4 }), (7.5_f64 * 4 as f64).min(100.0)); }
#[test]
fn bulk_score_059() { assert_eq!(score_record(&Record { id: 59, weight: 8.5, hits: 5 }), (8.5_f64 * 5 as f64).min(100.0)); }
#[test]
fn bulk_score_060() { assert_eq!(score_record(&Record { id: 60, weight: 9.5, hits: 6 }), (9.5_f64 * 6 as f64).min(100.0)); }
#[test]
fn bulk_score_061() { assert_eq!(score_record(&Record { id: 61, weight: 10.5, hits: 7 }), (10.5_f64 * 7 as f64).min(100.0)); }
#[test]
fn bulk_score_062() { assert_eq!(score_record(&Record { id: 62, weight: 11.5, hits: 8 }), (11.5_f64 * 8 as f64).min(100.0)); }
#[test]
fn bulk_score_063() { assert_eq!(score_record(&Record { id: 63, weight: 12.5, hits: 0 }), (12.5_f64 * 0 as f64).min(100.0)); }
#[test]
fn bulk_score_064() { assert_eq!(score_record(&Record { id: 64, weight: 13.5, hits: 1 }), (13.5_f64 * 1 as f64).min(100.0)); }
#[test]
fn bulk_score_065() { assert_eq!(score_record(&Record { id: 65, weight: 14.5, hits: 2 }), (14.5_f64 * 2 as f64).min(100.0)); }
#[test]
fn bulk_score_066() { assert_eq!(score_record(&Record { id: 66, weight: 15.5, hits: 3 }), (15.5_f64 * 3 as f64).min(100.0)); }
#[test]
fn bulk_score_067() { assert_eq!(score_record(&Record { id: 67, weight: 16.5, hits: 4 }), (16.5_f64 * 4 as f64).min(100.0)); }
#[test]
fn bulk_score_068() { assert_eq!(score_record(&Record { id: 68, weight: 0.5, hits: 5 }), (0.5_f64 * 5 as f64).min(100.0)); }
#[test]
fn bulk_score_069() { assert_eq!(score_record(&Record { id: 69, weight: 1.5, hits: 6 }), (1.5_f64 * 6 as f64).min(100.0)); }
#[test]
fn bulk_score_070() { assert_eq!(score_record(&Record { id: 70, weight: 2.5, hits: 7 }), (2.5_f64 * 7 as f64).min(100.0)); }
#[test]
fn bulk_score_071() { assert_eq!(score_record(&Record { id: 71, weight: 3.5, hits: 8 }), (3.5_f64 * 8 as f64).min(100.0)); }
#[test]
fn bulk_score_072() { assert_eq!(score_record(&Record { id: 72, weight: 4.5, hits: 0 }), (4.5_f64 * 0 as f64).min(100.0)); }
#[test]
fn bulk_score_073() { assert_eq!(score_record(&Record { id: 73, weight: 5.5, hits: 1 }), (5.5_f64 * 1 as f64).min(100.0)); }
#[test]
fn bulk_score_074() { assert_eq!(score_record(&Record { id: 74, weight: 6.5, hits: 2 }), (6.5_f64 * 2 as f64).min(100.0)); }
#[test]
fn bulk_score_075() { assert_eq!(score_record(&Record { id: 75, weight: 7.5, hits: 3 }), (7.5_f64 * 3 as f64).min(100.0)); }
#[test]
fn bulk_score_076() { assert_eq!(score_record(&Record { id: 76, weight: 8.5, hits: 4 }), (8.5_f64 * 4 as f64).min(100.0)); }
#[test]
fn bulk_score_077() { assert_eq!(score_record(&Record { id: 77, weight: 9.5, hits: 5 }), (9.5_f64 * 5 as f64).min(100.0)); }
#[test]
fn bulk_score_078() { assert_eq!(score_record(&Record { id: 78, weight: 10.5, hits: 6 }), (10.5_f64 * 6 as f64).min(100.0)); }
#[test]
fn bulk_score_079() { assert_eq!(score_record(&Record { id: 79, weight: 11.5, hits: 7 }), (11.5_f64 * 7 as f64).min(100.0)); }
#[test]
fn bulk_score_080() { assert_eq!(score_record(&Record { id: 80, weight: 12.5, hits: 8 }), (12.5_f64 * 8 as f64).min(100.0)); }
#[test]
fn bulk_score_081() { assert_eq!(score_record(&Record { id: 81, weight: 13.5, hits: 0 }), (13.5_f64 * 0 as f64).min(100.0)); }
#[test]
fn bulk_score_082() { assert_eq!(score_record(&Record { id: 82, weight: 14.5, hits: 1 }), (14.5_f64 * 1 as f64).min(100.0)); }
#[test]
fn bulk_score_083() { assert_eq!(score_record(&Record { id: 83, weight: 15.5, hits: 2 }), (15.5_f64 * 2 as f64).min(100.0)); }
#[test]
fn bulk_score_084() { assert_eq!(score_record(&Record { id: 84, weight: 16.5, hits: 3 }), (16.5_f64 * 3 as f64).min(100.0)); }
#[test]
fn bulk_score_085() { assert_eq!(score_record(&Record { id: 85, weight: 0.5, hits: 4 }), (0.5_f64 * 4 as f64).min(100.0)); }
#[test]
fn bulk_score_086() { assert_eq!(score_record(&Record { id: 86, weight: 1.5, hits: 5 }), (1.5_f64 * 5 as f64).min(100.0)); }
#[test]
fn bulk_score_087() { assert_eq!(score_record(&Record { id: 87, weight: 2.5, hits: 6 }), (2.5_f64 * 6 as f64).min(100.0)); }
#[test]
fn bulk_score_088() { assert_eq!(score_record(&Record { id: 88, weight: 3.5, hits: 7 }), (3.5_f64 * 7 as f64).min(100.0)); }
#[test]
fn bulk_score_089() { assert_eq!(score_record(&Record { id: 89, weight: 4.5, hits: 8 }), (4.5_f64 * 8 as f64).min(100.0)); }
#[test]
fn bulk_score_090() { assert_eq!(score_record(&Record { id: 90, weight: 5.5, hits: 0 }), (5.5_f64 * 0 as f64).min(100.0)); }
#[test]
fn bulk_score_091() { assert_eq!(score_record(&Record { id: 91, weight: 6.5, hits: 1 }), (6.5_f64 * 1 as f64).min(100.0)); }
#[test]
fn bulk_score_092() { assert_eq!(score_record(&Record { id: 92, weight: 7.5, hits: 2 }), (7.5_f64 * 2 as f64).min(100.0)); }
#[test]
fn bulk_score_093() { assert_eq!(score_record(&Record { id: 93, weight: 8.5, hits: 3 }), (8.5_f64 * 3 as f64).min(100.0)); }
#[test]
fn bulk_score_094() { assert_eq!(score_record(&Record { id: 94, weight: 9.5, hits: 4 }), (9.5_f64 * 4 as f64).min(100.0)); }
#[test]
fn bulk_score_095() { assert_eq!(score_record(&Record { id: 95, weight: 10.5, hits: 5 }), (10.5_f64 * 5 as f64).min(100.0)); }
#[test]
fn bulk_score_096() { assert_eq!(score_record(&Record { id: 96, weight: 11.5, hits: 6 }), (11.5_f64 * 6 as f64).min(100.0)); }
#[test]
fn bulk_score_097() { assert_eq!(score_record(&Record { id: 97, weight: 12.5, hits: 7 }), (12.5_f64 * 7 as f64).min(100.0)); }
#[test]
fn bulk_score_098() { assert_eq!(score_record(&Record { id: 98, weight: 13.5, hits: 8 }), (13.5_f64 * 8 as f64).min(100.0)); }
#[test]
fn bulk_score_099() { assert_eq!(score_record(&Record { id: 99, weight: 14.5, hits: 0 }), (14.5_f64 * 0 as f64).min(100.0)); }
#[test]
fn bulk_score_100() { assert_eq!(score_record(&Record { id: 100, weight: 15.5, hits: 1 }), (15.5_f64 * 1 as f64).min(100.0)); }
#[test]
fn bulk_score_101() { assert_eq!(score_record(&Record { id: 101, weight: 16.5, hits: 2 }), (16.5_f64 * 2 as f64).min(100.0)); }
#[test]
fn bulk_score_102() { assert_eq!(score_record(&Record { id: 102, weight: 0.5, hits: 3 }), (0.5_f64 * 3 as f64).min(100.0)); }
#[test]
fn bulk_score_103() { assert_eq!(score_record(&Record { id: 103, weight: 1.5, hits: 4 }), (1.5_f64 * 4 as f64).min(100.0)); }
#[test]
fn bulk_score_104() { assert_eq!(score_record(&Record { id: 104, weight: 2.5, hits: 5 }), (2.5_f64 * 5 as f64).min(100.0)); }
#[test]
fn bulk_score_105() { assert_eq!(score_record(&Record { id: 105, weight: 3.5, hits: 6 }), (3.5_f64 * 6 as f64).min(100.0)); }
#[test]
fn bulk_score_106() { assert_eq!(score_record(&Record { id: 106, weight: 4.5, hits: 7 }), (4.5_f64 * 7 as f64).min(100.0)); }
#[test]
fn bulk_score_107() { assert_eq!(score_record(&Record { id: 107, weight: 5.5, hits: 8 }), (5.5_f64 * 8 as f64).min(100.0)); }
#[test]
fn bulk_score_108() { assert_eq!(score_record(&Record { id: 108, weight: 6.5, hits: 0 }), (6.5_f64 * 0 as f64).min(100.0)); }
#[test]
fn bulk_score_109() { assert_eq!(score_record(&Record { id: 109, weight: 7.5, hits: 1 }), (7.5_f64 * 1 as f64).min(100.0)); }
#[test]
fn bulk_score_110() { assert_eq!(score_record(&Record { id: 110, weight: 8.5, hits: 2 }), (8.5_f64 * 2 as f64).min(100.0)); }
#[test]
fn bulk_score_111() { assert_eq!(score_record(&Record { id: 111, weight: 9.5, hits: 3 }), (9.5_f64 * 3 as f64).min(100.0)); }
#[test]
fn bulk_score_112() { assert_eq!(score_record(&Record { id: 112, weight: 10.5, hits: 4 }), (10.5_f64 * 4 as f64).min(100.0)); }
#[test]
fn bulk_score_113() { assert_eq!(score_record(&Record { id: 113, weight: 11.5, hits: 5 }), (11.5_f64 * 5 as f64).min(100.0)); }
#[test]
fn bulk_score_114() { assert_eq!(score_record(&Record { id: 114, weight: 12.5, hits: 6 }), (12.5_f64 * 6 as f64).min(100.0)); }
#[test]
fn bulk_score_115() { assert_eq!(score_record(&Record { id: 115, weight: 13.5, hits: 7 }), (13.5_f64 * 7 as f64).min(100.0)); }
#[test]
fn bulk_score_116() { assert_eq!(score_record(&Record { id: 116, weight: 14.5, hits: 8 }), (14.5_f64 * 8 as f64).min(100.0)); }
#[test]
fn bulk_score_117() { assert_eq!(score_record(&Record { id: 117, weight: 15.5, hits: 0 }), (15.5_f64 * 0 as f64).min(100.0)); }
#[test]
fn bulk_score_118() { assert_eq!(score_record(&Record { id: 118, weight: 16.5, hits: 1 }), (16.5_f64 * 1 as f64).min(100.0)); }
#[test]
fn bulk_score_119() { assert_eq!(score_record(&Record { id: 119, weight: 0.5, hits: 2 }), (0.5_f64 * 2 as f64).min(100.0)); }
#[test]
fn bulk_score_120() { assert_eq!(score_record(&Record { id: 120, weight: 1.5, hits: 3 }), (1.5_f64 * 3 as f64).min(100.0)); }
#[test]
fn bulk_score_121() { assert_eq!(score_record(&Record { id: 121, weight: 2.5, hits: 4 }), (2.5_f64 * 4 as f64).min(100.0)); }
#[test]
fn bulk_score_122() { assert_eq!(score_record(&Record { id: 122, weight: 3.5, hits: 5 }), (3.5_f64 * 5 as f64).min(100.0)); }
#[test]
fn bulk_score_123() { assert_eq!(score_record(&Record { id: 123, weight: 4.5, hits: 6 }), (4.5_f64 * 6 as f64).min(100.0)); }
#[test]
fn bulk_score_124() { assert_eq!(score_record(&Record { id: 124, weight: 5.5, hits: 7 }), (5.5_f64 * 7 as f64).min(100.0)); }
#[test]
fn bulk_score_125() { assert_eq!(score_record(&Record { id: 125, weight: 6.5, hits: 8 }), (6.5_f64 * 8 as f64).min(100.0)); }
#[test]
fn bulk_score_126() { assert_eq!(score_record(&Record { id: 126, weight: 7.5, hits: 0 }), (7.5_f64 * 0 as f64).min(100.0)); }
#[test]
fn bulk_score_127() { assert_eq!(score_record(&Record { id: 127, weight: 8.5, hits: 1 }), (8.5_f64 * 1 as f64).min(100.0)); }
#[test]
fn bulk_score_128() { assert_eq!(score_record(&Record { id: 128, weight: 9.5, hits: 2 }), (9.5_f64 * 2 as f64).min(100.0)); }
#[test]
fn bulk_score_129() { assert_eq!(score_record(&Record { id: 129, weight: 10.5, hits: 3 }), (10.5_f64 * 3 as f64).min(100.0)); }
#[test]
fn bulk_score_130() { assert_eq!(score_record(&Record { id: 130, weight: 11.5, hits: 4 }), (11.5_f64 * 4 as f64).min(100.0)); }
#[test]
fn bulk_score_131() { assert_eq!(score_record(&Record { id: 131, weight: 12.5, hits: 5 }), (12.5_f64 * 5 as f64).min(100.0)); }
#[test]
fn bulk_score_132() { assert_eq!(score_record(&Record { id: 132, weight: 13.5, hits: 6 }), (13.5_f64 * 6 as f64).min(100.0)); }
#[test]
fn bulk_score_133() { assert_eq!(score_record(&Record { id: 133, weight: 14.5, hits: 7 }), (14.5_f64 * 7 as f64).min(100.0)); }
#[test]
fn bulk_score_134() { assert_eq!(score_record(&Record { id: 134, weight: 15.5, hits: 8 }), (15.5_f64 * 8 as f64).min(100.0)); }
#[test]
fn bulk_score_135() { assert_eq!(score_record(&Record { id: 135, weight: 16.5, hits: 0 }), (16.5_f64 * 0 as f64).min(100.0)); }
#[test]
fn bulk_score_136() { assert_eq!(score_record(&Record { id: 136, weight: 0.5, hits: 1 }), (0.5_f64 * 1 as f64).min(100.0)); }
#[test]
fn bulk_score_137() { assert_eq!(score_record(&Record { id: 137, weight: 1.5, hits: 2 }), (1.5_f64 * 2 as f64).min(100.0)); }
#[test]
fn bulk_score_138() { assert_eq!(score_record(&Record { id: 138, weight: 2.5, hits: 3 }), (2.5_f64 * 3 as f64).min(100.0)); }
#[test]
fn bulk_score_139() { assert_eq!(score_record(&Record { id: 139, weight: 3.5, hits: 4 }), (3.5_f64 * 4 as f64).min(100.0)); }
#[test]
fn bulk_score_140() { assert_eq!(score_record(&Record { id: 140, weight: 4.5, hits: 5 }), (4.5_f64 * 5 as f64).min(100.0)); }
#[test]
fn bulk_score_141() { assert_eq!(score_record(&Record { id: 141, weight: 5.5, hits: 6 }), (5.5_f64 * 6 as f64).min(100.0)); }
#[test]
fn bulk_score_142() { assert_eq!(score_record(&Record { id: 142, weight: 6.5, hits: 7 }), (6.5_f64 * 7 as f64).min(100.0)); }
#[test]
fn bulk_score_143() { assert_eq!(score_record(&Record { id: 143, weight: 7.5, hits: 8 }), (7.5_f64 * 8 as f64).min(100.0)); }
#[test]
fn bulk_score_144() { assert_eq!(score_record(&Record { id: 144, weight: 8.5, hits: 0 }), (8.5_f64 * 0 as f64).min(100.0)); }
#[test]
fn bulk_score_145() { assert_eq!(score_record(&Record { id: 145, weight: 9.5, hits: 1 }), (9.5_f64 * 1 as f64).min(100.0)); }
#[test]
fn bulk_score_146() { assert_eq!(score_record(&Record { id: 146, weight: 10.5, hits: 2 }), (10.5_f64 * 2 as f64).min(100.0)); }
#[test]
fn bulk_score_147() { assert_eq!(score_record(&Record { id: 147, weight: 11.5, hits: 3 }), (11.5_f64 * 3 as f64).min(100.0)); }
#[test]
fn bulk_score_148() { assert_eq!(score_record(&Record { id: 148, weight: 12.5, hits: 4 }), (12.5_f64 * 4 as f64).min(100.0)); }
#[test]
fn bulk_score_149() { assert_eq!(score_record(&Record { id: 149, weight: 13.5, hits: 5 }), (13.5_f64 * 5 as f64).min(100.0)); }
#[test]
fn bulk_score_150() { assert_eq!(score_record(&Record { id: 150, weight: 14.5, hits: 6 }), (14.5_f64 * 6 as f64).min(100.0)); }
#[test]
fn bulk_score_151() { assert_eq!(score_record(&Record { id: 151, weight: 15.5, hits: 7 }), (15.5_f64 * 7 as f64).min(100.0)); }
#[test]
fn bulk_score_152() { assert_eq!(score_record(&Record { id: 152, weight: 16.5, hits: 8 }), (16.5_f64 * 8 as f64).min(100.0)); }
#[test]
fn bulk_score_153() { assert_eq!(score_record(&Record { id: 153, weight: 0.5, hits: 0 }), (0.5_f64 * 0 as f64).min(100.0)); }
#[test]
fn bulk_score_154() { assert_eq!(score_record(&Record { id: 154, weight: 1.5, hits: 1 }), (1.5_f64 * 1 as f64).min(100.0)); }
#[test]
fn bulk_score_155() { assert_eq!(score_record(&Record { id: 155, weight: 2.5, hits: 2 }), (2.5_f64 * 2 as f64).min(100.0)); }
#[test]
fn bulk_score_156() { assert_eq!(score_record(&Record { id: 156, weight: 3.5, hits: 3 }), (3.5_f64 * 3 as f64).min(100.0)); }
#[test]
fn bulk_score_157() { assert_eq!(score_record(&Record { id: 157, weight: 4.5, hits: 4 }), (4.5_f64 * 4 as f64).min(100.0)); }
#[test]
fn bulk_score_158() { assert_eq!(score_record(&Record { id: 158, weight: 5.5, hits: 5 }), (5.5_f64 * 5 as f64).min(100.0)); }
#[test]
fn bulk_score_159() { assert_eq!(score_record(&Record { id: 159, weight: 6.5, hits: 6 }), (6.5_f64 * 6 as f64).min(100.0)); }
#[test]
fn bulk_score_160() { assert_eq!(score_record(&Record { id: 160, weight: 7.5, hits: 7 }), (7.5_f64 * 7 as f64).min(100.0)); }
#[test]
fn bulk_score_161() { assert_eq!(score_record(&Record { id: 161, weight: 8.5, hits: 8 }), (8.5_f64 * 8 as f64).min(100.0)); }
#[test]
fn bulk_score_162() { assert_eq!(score_record(&Record { id: 162, weight: 9.5, hits: 0 }), (9.5_f64 * 0 as f64).min(100.0)); }
#[test]
fn bulk_score_163() { assert_eq!(score_record(&Record { id: 163, weight: 10.5, hits: 1 }), (10.5_f64 * 1 as f64).min(100.0)); }
#[test]
fn bulk_score_164() { assert_eq!(score_record(&Record { id: 164, weight: 11.5, hits: 2 }), (11.5_f64 * 2 as f64).min(100.0)); }
#[test]
fn bulk_score_165() { assert_eq!(score_record(&Record { id: 165, weight: 12.5, hits: 3 }), (12.5_f64 * 3 as f64).min(100.0)); }
#[test]
fn bulk_score_166() { assert_eq!(score_record(&Record { id: 166, weight: 13.5, hits: 4 }), (13.5_f64 * 4 as f64).min(100.0)); }
#[test]
fn bulk_score_167() { assert_eq!(score_record(&Record { id: 167, weight: 14.5, hits: 5 }), (14.5_f64 * 5 as f64).min(100.0)); }
#[test]
fn bulk_score_168() { assert_eq!(score_record(&Record { id: 168, weight: 15.5, hits: 6 }), (15.5_f64 * 6 as f64).min(100.0)); }
#[test]
fn bulk_score_169() { assert_eq!(score_record(&Record { id: 169, weight: 16.5, hits: 7 }), (16.5_f64 * 7 as f64).min(100.0)); }
#[test]
fn bulk_score_170() { assert_eq!(score_record(&Record { id: 170, weight: 0.5, hits: 8 }), (0.5_f64 * 8 as f64).min(100.0)); }
#[test]
fn bulk_score_171() { assert_eq!(score_record(&Record { id: 171, weight: 1.5, hits: 0 }), (1.5_f64 * 0 as f64).min(100.0)); }
#[test]
fn bulk_score_172() { assert_eq!(score_record(&Record { id: 172, weight: 2.5, hits: 1 }), (2.5_f64 * 1 as f64).min(100.0)); }
#[test]
fn bulk_score_173() { assert_eq!(score_record(&Record { id: 173, weight: 3.5, hits: 2 }), (3.5_f64 * 2 as f64).min(100.0)); }
#[test]
fn bulk_score_174() { assert_eq!(score_record(&Record { id: 174, weight: 4.5, hits: 3 }), (4.5_f64 * 3 as f64).min(100.0)); }
#[test]
fn bulk_score_175() { assert_eq!(score_record(&Record { id: 175, weight: 5.5, hits: 4 }), (5.5_f64 * 4 as f64).min(100.0)); }
#[test]
fn bulk_score_176() { assert_eq!(score_record(&Record { id: 176, weight: 6.5, hits: 5 }), (6.5_f64 * 5 as f64).min(100.0)); }
#[test]
fn bulk_score_177() { assert_eq!(score_record(&Record { id: 177, weight: 7.5, hits: 6 }), (7.5_f64 * 6 as f64).min(100.0)); }
#[test]
fn bulk_score_178() { assert_eq!(score_record(&Record { id: 178, weight: 8.5, hits: 7 }), (8.5_f64 * 7 as f64).min(100.0)); }
#[test]
fn bulk_score_179() { assert_eq!(score_record(&Record { id: 179, weight: 9.5, hits: 8 }), (9.5_f64 * 8 as f64).min(100.0)); }
#[test]
fn bulk_score_180() { assert_eq!(score_record(&Record { id: 180, weight: 10.5, hits: 0 }), (10.5_f64 * 0 as f64).min(100.0)); }
#[test]
fn bulk_score_181() { assert_eq!(score_record(&Record { id: 181, weight: 11.5, hits: 1 }), (11.5_f64 * 1 as f64).min(100.0)); }
#[test]
fn bulk_score_182() { assert_eq!(score_record(&Record { id: 182, weight: 12.5, hits: 2 }), (12.5_f64 * 2 as f64).min(100.0)); }
#[test]
fn bulk_score_183() { assert_eq!(score_record(&Record { id: 183, weight: 13.5, hits: 3 }), (13.5_f64 * 3 as f64).min(100.0)); }
#[test]
fn bulk_score_184() { assert_eq!(score_record(&Record { id: 184, weight: 14.5, hits: 4 }), (14.5_f64 * 4 as f64).min(100.0)); }
#[test]
fn bulk_score_185() { assert_eq!(score_record(&Record { id: 185, weight: 15.5, hits: 5 }), (15.5_f64 * 5 as f64).min(100.0)); }
#[test]
fn bulk_score_186() { assert_eq!(score_record(&Record { id: 186, weight: 16.5, hits: 6 }), (16.5_f64 * 6 as f64).min(100.0)); }
#[test]
fn bulk_score_187() { assert_eq!(score_record(&Record { id: 187, weight: 0.5, hits: 7 }), (0.5_f64 * 7 as f64).min(100.0)); }
#[test]
fn bulk_score_188() { assert_eq!(score_record(&Record { id: 188, weight: 1.5, hits: 8 }), (1.5_f64 * 8 as f64).min(100.0)); }
#[test]
fn bulk_score_189() { assert_eq!(score_record(&Record { id: 189, weight: 2.5, hits: 0 }), (2.5_f64 * 0 as f64).min(100.0)); }
#[test]
fn bulk_score_190() { assert_eq!(score_record(&Record { id: 190, weight: 3.5, hits: 1 }), (3.5_f64 * 1 as f64).min(100.0)); }
#[test]
fn bulk_score_191() { assert_eq!(score_record(&Record { id: 191, weight: 4.5, hits: 2 }), (4.5_f64 * 2 as f64).min(100.0)); }
#[test]
fn bulk_score_192() { assert_eq!(score_record(&Record { id: 192, weight: 5.5, hits: 3 }), (5.5_f64 * 3 as f64).min(100.0)); }
#[test]
fn bulk_score_193() { assert_eq!(score_record(&Record { id: 193, weight: 6.5, hits: 4 }), (6.5_f64 * 4 as f64).min(100.0)); }
#[test]
fn bulk_score_194() { assert_eq!(score_record(&Record { id: 194, weight: 7.5, hits: 5 }), (7.5_f64 * 5 as f64).min(100.0)); }
#[test]
fn bulk_score_195() { assert_eq!(score_record(&Record { id: 195, weight: 8.5, hits: 6 }), (8.5_f64 * 6 as f64).min(100.0)); }
#[test]
fn bulk_score_196() { assert_eq!(score_record(&Record { id: 196, weight: 9.5, hits: 7 }), (9.5_f64 * 7 as f64).min(100.0)); }
#[test]
fn bulk_score_197() { assert_eq!(score_record(&Record { id: 197, weight: 10.5, hits: 8 }), (10.5_f64 * 8 as f64).min(100.0)); }
#[test]
fn bulk_score_198() { assert_eq!(score_record(&Record { id: 198, weight: 11.5, hits: 0 }), (11.5_f64 * 0 as f64).min(100.0)); }
#[test]
fn bulk_score_199() { assert_eq!(score_record(&Record { id: 199, weight: 12.5, hits: 1 }), (12.5_f64 * 1 as f64).min(100.0)); }
#[test]
fn bulk_score_200() { assert_eq!(score_record(&Record { id: 200, weight: 13.5, hits: 2 }), (13.5_f64 * 2 as f64).min(100.0)); }
#[test]
fn bulk_score_201() { assert_eq!(score_record(&Record { id: 201, weight: 14.5, hits: 3 }), (14.5_f64 * 3 as f64).min(100.0)); }
#[test]
fn bulk_score_202() { assert_eq!(score_record(&Record { id: 202, weight: 15.5, hits: 4 }), (15.5_f64 * 4 as f64).min(100.0)); }
#[test]
fn bulk_score_203() { assert_eq!(score_record(&Record { id: 203, weight: 16.5, hits: 5 }), (16.5_f64 * 5 as f64).min(100.0)); }
#[test]
fn bulk_score_204() { assert_eq!(score_record(&Record { id: 204, weight: 0.5, hits: 6 }), (0.5_f64 * 6 as f64).min(100.0)); }
#[test]
fn bulk_score_205() { assert_eq!(score_record(&Record { id: 205, weight: 1.5, hits: 7 }), (1.5_f64 * 7 as f64).min(100.0)); }
#[test]
fn bulk_score_206() { assert_eq!(score_record(&Record { id: 206, weight: 2.5, hits: 8 }), (2.5_f64 * 8 as f64).min(100.0)); }
#[test]
fn bulk_score_207() { assert_eq!(score_record(&Record { id: 207, weight: 3.5, hits: 0 }), (3.5_f64 * 0 as f64).min(100.0)); }
#[test]
fn bulk_score_208() { assert_eq!(score_record(&Record { id: 208, weight: 4.5, hits: 1 }), (4.5_f64 * 1 as f64).min(100.0)); }
#[test]
fn bulk_score_209() { assert_eq!(score_record(&Record { id: 209, weight: 5.5, hits: 2 }), (5.5_f64 * 2 as f64).min(100.0)); }
#[test]
fn bulk_score_210() { assert_eq!(score_record(&Record { id: 210, weight: 6.5, hits: 3 }), (6.5_f64 * 3 as f64).min(100.0)); }
#[test]
fn bulk_score_211() { assert_eq!(score_record(&Record { id: 211, weight: 7.5, hits: 4 }), (7.5_f64 * 4 as f64).min(100.0)); }
#[test]
fn bulk_score_212() { assert_eq!(score_record(&Record { id: 212, weight: 8.5, hits: 5 }), (8.5_f64 * 5 as f64).min(100.0)); }
#[test]
fn bulk_score_213() { assert_eq!(score_record(&Record { id: 213, weight: 9.5, hits: 6 }), (9.5_f64 * 6 as f64).min(100.0)); }
#[test]
fn bulk_score_214() { assert_eq!(score_record(&Record { id: 214, weight: 10.5, hits: 7 }), (10.5_f64 * 7 as f64).min(100.0)); }
#[test]
fn bulk_score_215() { assert_eq!(score_record(&Record { id: 215, weight: 11.5, hits: 8 }), (11.5_f64 * 8 as f64).min(100.0)); }
#[test]
fn bulk_score_216() { assert_eq!(score_record(&Record { id: 216, weight: 12.5, hits: 0 }), (12.5_f64 * 0 as f64).min(100.0)); }
#[test]
fn bulk_score_217() { assert_eq!(score_record(&Record { id: 217, weight: 13.5, hits: 1 }), (13.5_f64 * 1 as f64).min(100.0)); }
#[test]
fn bulk_score_218() { assert_eq!(score_record(&Record { id: 218, weight: 14.5, hits: 2 }), (14.5_f64 * 2 as f64).min(100.0)); }
#[test]
fn bulk_score_219() { assert_eq!(score_record(&Record { id: 219, weight: 15.5, hits: 3 }), (15.5_f64 * 3 as f64).min(100.0)); }
#[test]
fn bulk_score_220() { assert_eq!(score_record(&Record { id: 220, weight: 16.5, hits: 4 }), (16.5_f64 * 4 as f64).min(100.0)); }
#[test]
fn bulk_score_221() { assert_eq!(score_record(&Record { id: 221, weight: 0.5, hits: 5 }), (0.5_f64 * 5 as f64).min(100.0)); }
#[test]
fn bulk_score_222() { assert_eq!(score_record(&Record { id: 222, weight: 1.5, hits: 6 }), (1.5_f64 * 6 as f64).min(100.0)); }
#[test]
fn bulk_score_223() { assert_eq!(score_record(&Record { id: 223, weight: 2.5, hits: 7 }), (2.5_f64 * 7 as f64).min(100.0)); }
#[test]
fn bulk_score_224() { assert_eq!(score_record(&Record { id: 224, weight: 3.5, hits: 8 }), (3.5_f64 * 8 as f64).min(100.0)); }
#[test]
fn bulk_score_225() { assert_eq!(score_record(&Record { id: 225, weight: 4.5, hits: 0 }), (4.5_f64 * 0 as f64).min(100.0)); }
#[test]
fn bulk_score_226() { assert_eq!(score_record(&Record { id: 226, weight: 5.5, hits: 1 }), (5.5_f64 * 1 as f64).min(100.0)); }
#[test]
fn bulk_score_227() { assert_eq!(score_record(&Record { id: 227, weight: 6.5, hits: 2 }), (6.5_f64 * 2 as f64).min(100.0)); }
#[test]
fn bulk_score_228() { assert_eq!(score_record(&Record { id: 228, weight: 7.5, hits: 3 }), (7.5_f64 * 3 as f64).min(100.0)); }
#[test]
fn bulk_score_229() { assert_eq!(score_record(&Record { id: 229, weight: 8.5, hits: 4 }), (8.5_f64 * 4 as f64).min(100.0)); }
#[test]
fn bulk_score_230() { assert_eq!(score_record(&Record { id: 230, weight: 9.5, hits: 5 }), (9.5_f64 * 5 as f64).min(100.0)); }
#[test]
fn bulk_score_231() { assert_eq!(score_record(&Record { id: 231, weight: 10.5, hits: 6 }), (10.5_f64 * 6 as f64).min(100.0)); }
#[test]
fn bulk_score_232() { assert_eq!(score_record(&Record { id: 232, weight: 11.5, hits: 7 }), (11.5_f64 * 7 as f64).min(100.0)); }
#[test]
fn bulk_score_233() { assert_eq!(score_record(&Record { id: 233, weight: 12.5, hits: 8 }), (12.5_f64 * 8 as f64).min(100.0)); }
#[test]
fn bulk_score_234() { assert_eq!(score_record(&Record { id: 234, weight: 13.5, hits: 0 }), (13.5_f64 * 0 as f64).min(100.0)); }
#[test]
fn bulk_score_235() { assert_eq!(score_record(&Record { id: 235, weight: 14.5, hits: 1 }), (14.5_f64 * 1 as f64).min(100.0)); }
#[test]
fn bulk_score_236() { assert_eq!(score_record(&Record { id: 236, weight: 15.5, hits: 2 }), (15.5_f64 * 2 as f64).min(100.0)); }
#[test]
fn bulk_score_237() { assert_eq!(score_record(&Record { id: 237, weight: 16.5, hits: 3 }), (16.5_f64 * 3 as f64).min(100.0)); }
#[test]
fn bulk_score_238() { assert_eq!(score_record(&Record { id: 238, weight: 0.5, hits: 4 }), (0.5_f64 * 4 as f64).min(100.0)); }
#[test]
fn bulk_score_239() { assert_eq!(score_record(&Record { id: 239, weight: 1.5, hits: 5 }), (1.5_f64 * 5 as f64).min(100.0)); }
#[test]
fn bulk_score_240() { assert_eq!(score_record(&Record { id: 240, weight: 2.5, hits: 6 }), (2.5_f64 * 6 as f64).min(100.0)); }
#[test]
fn bulk_score_241() { assert_eq!(score_record(&Record { id: 241, weight: 3.5, hits: 7 }), (3.5_f64 * 7 as f64).min(100.0)); }
#[test]
fn bulk_score_242() { assert_eq!(score_record(&Record { id: 242, weight: 4.5, hits: 8 }), (4.5_f64 * 8 as f64).min(100.0)); }
#[test]
fn bulk_score_243() { assert_eq!(score_record(&Record { id: 243, weight: 5.5, hits: 0 }), (5.5_f64 * 0 as f64).min(100.0)); }
#[test]
fn bulk_score_244() { assert_eq!(score_record(&Record { id: 244, weight: 6.5, hits: 1 }), (6.5_f64 * 1 as f64).min(100.0)); }
#[test]
fn bulk_score_245() { assert_eq!(score_record(&Record { id: 245, weight: 7.5, hits: 2 }), (7.5_f64 * 2 as f64).min(100.0)); }
#[test]
fn bulk_score_246() { assert_eq!(score_record(&Record { id: 246, weight: 8.5, hits: 3 }), (8.5_f64 * 3 as f64).min(100.0)); }
#[test]
fn bulk_score_247() { assert_eq!(score_record(&Record { id: 247, weight: 9.5, hits: 4 }), (9.5_f64 * 4 as f64).min(100.0)); }
#[test]
fn bulk_score_248() { assert_eq!(score_record(&Record { id: 248, weight: 10.5, hits: 5 }), (10.5_f64 * 5 as f64).min(100.0)); }
#[test]
fn bulk_score_249() { assert_eq!(score_record(&Record { id: 249, weight: 11.5, hits: 6 }), (11.5_f64 * 6 as f64).min(100.0)); }
#[test]
fn bulk_score_250() { assert_eq!(score_record(&Record { id: 250, weight: 12.5, hits: 7 }), (12.5_f64 * 7 as f64).min(100.0)); }
#[test]
fn bulk_score_251() { assert_eq!(score_record(&Record { id: 251, weight: 13.5, hits: 8 }), (13.5_f64 * 8 as f64).min(100.0)); }
#[test]
fn bulk_score_252() { assert_eq!(score_record(&Record { id: 252, weight: 14.5, hits: 0 }), (14.5_f64 * 0 as f64).min(100.0)); }
#[test]
fn bulk_score_253() { assert_eq!(score_record(&Record { id: 253, weight: 15.5, hits: 1 }), (15.5_f64 * 1 as f64).min(100.0)); }
#[test]
fn bulk_score_254() { assert_eq!(score_record(&Record { id: 254, weight: 16.5, hits: 2 }), (16.5_f64 * 2 as f64).min(100.0)); }
#[test]
fn bulk_score_255() { assert_eq!(score_record(&Record { id: 255, weight: 0.5, hits: 3 }), (0.5_f64 * 3 as f64).min(100.0)); }
#[test]
fn bulk_score_256() { assert_eq!(score_record(&Record { id: 256, weight: 1.5, hits: 4 }), (1.5_f64 * 4 as f64).min(100.0)); }
#[test]
fn bulk_score_257() { assert_eq!(score_record(&Record { id: 257, weight: 2.5, hits: 5 }), (2.5_f64 * 5 as f64).min(100.0)); }
#[test]
fn bulk_score_258() { assert_eq!(score_record(&Record { id: 258, weight: 3.5, hits: 6 }), (3.5_f64 * 6 as f64).min(100.0)); }
#[test]
fn bulk_score_259() { assert_eq!(score_record(&Record { id: 259, weight: 4.5, hits: 7 }), (4.5_f64 * 7 as f64).min(100.0)); }
#[test]
fn bulk_score_260() { assert_eq!(score_record(&Record { id: 260, weight: 5.5, hits: 8 }), (5.5_f64 * 8 as f64).min(100.0)); }
#[test]
fn bulk_score_261() { assert_eq!(score_record(&Record { id: 261, weight: 6.5, hits: 0 }), (6.5_f64 * 0 as f64).min(100.0)); }
#[test]
fn bulk_score_262() { assert_eq!(score_record(&Record { id: 262, weight: 7.5, hits: 1 }), (7.5_f64 * 1 as f64).min(100.0)); }
#[test]
fn bulk_score_263() { assert_eq!(score_record(&Record { id: 263, weight: 8.5, hits: 2 }), (8.5_f64 * 2 as f64).min(100.0)); }
#[test]
fn bulk_score_264() { assert_eq!(score_record(&Record { id: 264, weight: 9.5, hits: 3 }), (9.5_f64 * 3 as f64).min(100.0)); }
#[test]
fn bulk_score_265() { assert_eq!(score_record(&Record { id: 265, weight: 10.5, hits: 4 }), (10.5_f64 * 4 as f64).min(100.0)); }
#[test]
fn bulk_score_266() { assert_eq!(score_record(&Record { id: 266, weight: 11.5, hits: 5 }), (11.5_f64 * 5 as f64).min(100.0)); }
#[test]
fn bulk_score_267() { assert_eq!(score_record(&Record { id: 267, weight: 12.5, hits: 6 }), (12.5_f64 * 6 as f64).min(100.0)); }
#[test]
fn bulk_score_268() { assert_eq!(score_record(&Record { id: 268, weight: 13.5, hits: 7 }), (13.5_f64 * 7 as f64).min(100.0)); }
#[test]
fn bulk_score_269() { assert_eq!(score_record(&Record { id: 269, weight: 14.5, hits: 8 }), (14.5_f64 * 8 as f64).min(100.0)); }
#[test]
fn bulk_score_270() { assert_eq!(score_record(&Record { id: 270, weight: 15.5, hits: 0 }), (15.5_f64 * 0 as f64).min(100.0)); }
#[test]
fn bulk_score_271() { assert_eq!(score_record(&Record { id: 271, weight: 16.5, hits: 1 }), (16.5_f64 * 1 as f64).min(100.0)); }
#[test]
fn bulk_score_272() { assert_eq!(score_record(&Record { id: 272, weight: 0.5, hits: 2 }), (0.5_f64 * 2 as f64).min(100.0)); }
#[test]
fn bulk_score_273() { assert_eq!(score_record(&Record { id: 273, weight: 1.5, hits: 3 }), (1.5_f64 * 3 as f64).min(100.0)); }
#[test]
fn bulk_score_274() { assert_eq!(score_record(&Record { id: 274, weight: 2.5, hits: 4 }), (2.5_f64 * 4 as f64).min(100.0)); }
#[test]
fn bulk_score_275() { assert_eq!(score_record(&Record { id: 275, weight: 3.5, hits: 5 }), (3.5_f64 * 5 as f64).min(100.0)); }
#[test]
fn bulk_score_276() { assert_eq!(score_record(&Record { id: 276, weight: 4.5, hits: 6 }), (4.5_f64 * 6 as f64).min(100.0)); }
#[test]
fn bulk_score_277() { assert_eq!(score_record(&Record { id: 277, weight: 5.5, hits: 7 }), (5.5_f64 * 7 as f64).min(100.0)); }
#[test]
fn bulk_score_278() { assert_eq!(score_record(&Record { id: 278, weight: 6.5, hits: 8 }), (6.5_f64 * 8 as f64).min(100.0)); }
#[test]
fn bulk_score_279() { assert_eq!(score_record(&Record { id: 279, weight: 7.5, hits: 0 }), (7.5_f64 * 0 as f64).min(100.0)); }
#[test]
fn bulk_score_280() { assert_eq!(score_record(&Record { id: 280, weight: 8.5, hits: 1 }), (8.5_f64 * 1 as f64).min(100.0)); }
#[test]
fn bulk_score_281() { assert_eq!(score_record(&Record { id: 281, weight: 9.5, hits: 2 }), (9.5_f64 * 2 as f64).min(100.0)); }
#[test]
fn bulk_score_282() { assert_eq!(score_record(&Record { id: 282, weight: 10.5, hits: 3 }), (10.5_f64 * 3 as f64).min(100.0)); }
#[test]
fn bulk_score_283() { assert_eq!(score_record(&Record { id: 283, weight: 11.5, hits: 4 }), (11.5_f64 * 4 as f64).min(100.0)); }
#[test]
fn bulk_score_284() { assert_eq!(score_record(&Record { id: 284, weight: 12.5, hits: 5 }), (12.5_f64 * 5 as f64).min(100.0)); }
#[test]
fn bulk_score_285() { assert_eq!(score_record(&Record { id: 285, weight: 13.5, hits: 6 }), (13.5_f64 * 6 as f64).min(100.0)); }
#[test]
fn bulk_score_286() { assert_eq!(score_record(&Record { id: 286, weight: 14.5, hits: 7 }), (14.5_f64 * 7 as f64).min(100.0)); }
#[test]
fn bulk_score_287() { assert_eq!(score_record(&Record { id: 287, weight: 15.5, hits: 8 }), (15.5_f64 * 8 as f64).min(100.0)); }
#[test]
fn bulk_score_288() { assert_eq!(score_record(&Record { id: 288, weight: 16.5, hits: 0 }), (16.5_f64 * 0 as f64).min(100.0)); }
#[test]
fn bulk_score_289() { assert_eq!(score_record(&Record { id: 289, weight: 0.5, hits: 1 }), (0.5_f64 * 1 as f64).min(100.0)); }
#[test]
fn bulk_score_290() { assert_eq!(score_record(&Record { id: 290, weight: 1.5, hits: 2 }), (1.5_f64 * 2 as f64).min(100.0)); }
#[test]
fn bulk_score_291() { assert_eq!(score_record(&Record { id: 291, weight: 2.5, hits: 3 }), (2.5_f64 * 3 as f64).min(100.0)); }
#[test]
fn bulk_score_292() { assert_eq!(score_record(&Record { id: 292, weight: 3.5, hits: 4 }), (3.5_f64 * 4 as f64).min(100.0)); }
#[test]
fn bulk_score_293() { assert_eq!(score_record(&Record { id: 293, weight: 4.5, hits: 5 }), (4.5_f64 * 5 as f64).min(100.0)); }
#[test]
fn bulk_score_294() { assert_eq!(score_record(&Record { id: 294, weight: 5.5, hits: 6 }), (5.5_f64 * 6 as f64).min(100.0)); }
#[test]
fn bulk_score_295() { assert_eq!(score_record(&Record { id: 295, weight: 6.5, hits: 7 }), (6.5_f64 * 7 as f64).min(100.0)); }
#[test]
fn bulk_score_296() { assert_eq!(score_record(&Record { id: 296, weight: 7.5, hits: 8 }), (7.5_f64 * 8 as f64).min(100.0)); }
#[test]
fn bulk_score_297() { assert_eq!(score_record(&Record { id: 297, weight: 8.5, hits: 0 }), (8.5_f64 * 0 as f64).min(100.0)); }
#[test]
fn bulk_score_298() { assert_eq!(score_record(&Record { id: 298, weight: 9.5, hits: 1 }), (9.5_f64 * 1 as f64).min(100.0)); }
#[test]
fn bulk_score_299() { assert_eq!(score_record(&Record { id: 299, weight: 10.5, hits: 2 }), (10.5_f64 * 2 as f64).min(100.0)); }
