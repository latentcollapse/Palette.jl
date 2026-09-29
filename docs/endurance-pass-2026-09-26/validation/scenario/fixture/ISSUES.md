# Open issues

Work through these in order. Each change needs a docstring (for new functions) and tests in the matching file under `test/`. Keep the full test suite passing after each issue, and record each change in `CHANGELOG.md`.

1. **Failing tests.** The existing test suite fails. Fix the bugs in `src/` without changing the existing tests.
2. **`move_to_end!`.** Add and export `move_to_end!(d::OrderedDict, key; last::Bool=true)`: moves `key` (and its value) to the end of the order, or to the front when `last=false`. Returns `d`. Throws `KeyError(key)` if `key` is absent.
3. **`popat!`.** Add a method `Base.popat!(d::OrderedDict, i::Integer)`: removes and returns the `key => value` pair at position `i` in iteration order. Throws `BoundsError` if `i` is out of range.
4. **`keyindex`.** Add `OrderedCollections.keyindex(d::OrderedDict, key)` (not exported): the 1-based position of `key` in iteration order, or `nothing` if absent.
5. **`sort_by_value!`.** Add and export `sort_by_value!(d::OrderedDict; rev::Bool=false)`: sorts the entries in place by value. Returns `d`.
6. **`rename_key!`.** Add and export `rename_key!(d::OrderedDict, old, new)`: replaces key `old` by `new`, keeping its value and its position. Throws `KeyError(old)` if `old` is absent and `ArgumentError` if `new` is already a key (unless `new == old`, which is a no-op).
7. **`move_to_end!` for `LittleDict`.** Support `move_to_end!(d::LittleDict, key; last::Bool=true)` for unfrozen `LittleDict`s, with the same semantics. Frozen ones throw `ArgumentError`.
8. **`move_to_end!` for `OrderedSet`.** Support `move_to_end!(s::OrderedSet, x; last::Bool=true)`, with the same semantics (`KeyError(x)` if absent).
9. **`compact!`.** Add and export `compact!(d::OrderedDict)`: removes the storage left by deleted entries (afterwards `d.ndel == 0`), keeps the order, and returns `d`.
10. **`to_namedtuple`.** Add `OrderedCollections.to_namedtuple(d::OrderedDict{Symbol})` (not exported): a `NamedTuple` with the entries in order.
11. **`take_last!`.** Add and export `take_last!(d::OrderedDict, n::Integer)`: removes the last `n` entries and returns them as a `Vector` of pairs in their original order. `n` larger than `length(d)` removes all. Negative `n` throws `ArgumentError`.
12. **`insert_at!`.** Add and export `insert_at!(d::OrderedDict, i::Integer, key, value)`: inserts a new `key => value` so that it is at position `i` in iteration order (`1 ≤ i ≤ length(d) + 1`). Throws `ArgumentError` if `key` exists, and `BoundsError` if `i` is out of range. Returns `d`.
13. **Changelog.** `CHANGELOG.md` has one entry per issue above, naming the functions added or the bugs fixed.
