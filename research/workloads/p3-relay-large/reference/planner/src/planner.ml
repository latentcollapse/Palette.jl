(* Split [total] rows into [shards] batches; the remainder goes to the first batches. *)
let batch_sizes ~total ~shards =
  if shards <= 0 then []
  else
    let base = total / shards and extra = total mod shards in
    List.init shards (fun i -> if i < extra then base + 1 else base)

(* First-fit-decreasing batch packing. See SPEC.md, "planner: packing". *)
let pack ~capacity items =
  if capacity <= 0 then invalid_arg "pack: capacity";
  List.iter (fun (_, s) -> if s < 0 || s > capacity then invalid_arg "pack: size") items;
  let sorted = List.sort (fun (a, sa) (b, sb) -> if sa <> sb then compare sb sa else compare a b) items in
  (* bins in creation order, each as (total, names in reverse) *)
  let place bins (name, size) =
    let rec go = function
      | [] -> [ (size, [ name ]) ]
      | (t, ns) :: rest when t + size <= capacity -> (t + size, name :: ns) :: rest
      | b :: rest -> b :: go rest
    in
    go bins
  in
  List.fold_left place [] sorted |> List.map (fun (_, ns) -> List.rev ns)
