
# Open issues, batch 6

28. **`filter_keys`.** Add and export `filter_keys(pred, d::OrderedDict)`: a new `OrderedDict` with the entries whose key satisfies `pred`, in order.
29. **`invert`.** Add and export `invert(d::OrderedDict)`: a new `OrderedDict` mapping each value to its key, in order. Throws `ArgumentError` if two keys share a value.
30. **`group_by_value`.** Add and export `group_by_value(d::OrderedDict)`: an `OrderedDict` from each distinct value (in first-seen order) to the `Vector` of its keys, in order.
31. **`rotate!` for `OrderedSet`.** Support `rotate!(s::OrderedSet, k::Integer)` with the same semantics as for `OrderedDict`.
32. **`nth_key`.** Add `OrderedCollections.nth_key(d::OrderedDict, i::Integer)` (not exported): the key at position `i`; `BoundsError` if out of range.
33. **Changelog.** Add entries for 28–32 to `CHANGELOG.md`.
