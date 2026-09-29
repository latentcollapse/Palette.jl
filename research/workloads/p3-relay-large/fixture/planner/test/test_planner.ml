let check name got want =
  if got <> want then (Printf.printf "FAIL %s\n" name; exit 1)
let () =
  check "even" (Planner.batch_sizes ~total:9 ~shards:3) [3; 3; 3];
  check "remainder" (Planner.batch_sizes ~total:10 ~shards:3) [4; 3; 3];
  check "sum" (List.fold_left (+) 0 (Planner.batch_sizes ~total:17 ~shards:5)) 17;
  print_endline "planner ok"
