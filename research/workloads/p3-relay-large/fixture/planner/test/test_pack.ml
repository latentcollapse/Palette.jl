let check name got want =
  if got <> want then (Printf.printf "FAIL %s\n" name; exit 1)
let raises name f =
  match f () with
  | _ -> Printf.printf "FAIL %s (no exception)\n" name; exit 1
  | exception Invalid_argument _ -> ()
let () =
  check "empty" (Planner.pack ~capacity:10 []) [];
  check "one bin" (Planner.pack ~capacity:10 [("a", 3); ("b", 4)]) [["b"; "a"]];
  check "decreasing first fit"
    (Planner.pack ~capacity:10 [("a", 5); ("b", 7); ("c", 5); ("d", 3)])
    [["b"; "d"]; ["a"; "c"]];
  check "ties by name"
    (Planner.pack ~capacity:6 [("z", 3); ("y", 3); ("x", 3)])
    [["x"; "y"]; ["z"]];
  check "exact fill" (Planner.pack ~capacity:4 [("a", 4); ("b", 4)]) [["a"]; ["b"]];
  check "first bin that fits, not best"
    (Planner.pack ~capacity:10 [("a", 6); ("b", 5); ("c", 4); ("d", 4)])
    [["a"; "c"]; ["b"; "d"]];
  check "zero-size items" (Planner.pack ~capacity:1 [("b", 0); ("a", 1)]) [["a"; "b"]];
  raises "too big" (fun () -> Planner.pack ~capacity:5 [("a", 6)]);
  raises "negative" (fun () -> Planner.pack ~capacity:5 [("a", -1)]);
  raises "capacity" (fun () -> Planner.pack ~capacity:0 [("a", 0)]);
  print_endline "pack ok"
