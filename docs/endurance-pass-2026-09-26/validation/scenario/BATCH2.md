
# Open issues, batch 2

15. **`popat!` for `OrderedSet`.** Add a method `Base.popat!(s::OrderedSet, i::Integer)`: removes and returns the element at position `i` in iteration order. Throws `BoundsError` if `i` is out of range.
16. **`reverse!`.** Add a method `Base.reverse!(d::OrderedDict)`: reverses the iteration order in place and returns `d`.
17. **`rotate!`.** Add and export `rotate!(d::OrderedDict, k::Integer)`: rotates the order left by `k` positions (the first `k` entries move to the end). Negative `k` rotates right; `k` may exceed `length(d)`. Returns `d`.
18. **`find_key`.** Add `OrderedCollections.find_key(pred, d::OrderedDict)` (not exported): the first key, in order, whose value satisfies `pred`, or `nothing`.
19. **`dedupe_values!`.** Add and export `dedupe_values!(d::OrderedDict)`: removes every entry whose value equals (`isequal`) the value of an earlier entry, keeping the first. Returns `d`.
20. **Benchmark.** Add `bench/bench_move.jl`: builds an `OrderedDict` of 10,000 `Int` keys, calls `move_to_end!` on 100,000 random existing keys, and prints the elapsed seconds. It must finish in under 60 seconds with `julia --project=. bench/bench_move.jl`. If it is too slow, make `move_to_end!` faster.
21. **Changelog.** Add entries for 15–20 to `CHANGELOG.md`.
