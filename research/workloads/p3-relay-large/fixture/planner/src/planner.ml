(* Split [total] rows into [shards] batches; the remainder goes to the first batches. *)
let batch_sizes ~total ~shards =
  if shards <= 0 then []
  else
    let base = total / shards and extra = total mod shards in
    List.init shards (fun i -> if i <= extra then base + 1 else base)

(* First-fit-decreasing batch packing. See SPEC.md, "planner: packing". *)
let pack ~capacity items =
  ignore capacity; ignore items;
  failwith "pack: not implemented"
