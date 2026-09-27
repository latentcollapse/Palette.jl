
# Open issues, batch 3

22. **`setindex_at!`.** Add and export `setindex_at!(d::OrderedDict, i::Integer, value)`: sets the value of the entry at position `i`. Throws `BoundsError` if `i` is out of range. Returns `d`.
23. **`insert_at!` for `OrderedSet`.** Support `insert_at!(s::OrderedSet, i::Integer, x)` with the same rules as for `OrderedDict` (`ArgumentError` if `x` is present, `BoundsError` if `i` is out of `1:length(s)+1`).
24. **`merge_ordered`.** Add and export `merge_ordered(a::OrderedDict, b::OrderedDict)`: a new `OrderedDict` with the keys of `a` in order, then the keys of `b` not in `a`. A key in both takes `b`'s value and keeps its position from `a`. `a` and `b` are not modified.
25. **`window`.** Add and export `window(d::OrderedDict, r::AbstractUnitRange)`: a new `OrderedDict` with the entries at positions `r`. Throws `BoundsError` if `r` is not within `1:length(d)`.
26. **README.** Add a section "Additions in this fork" to `README.md` that names every function added in issues 2–25.
27. **Changelog.** Add entries for 22–26 to `CHANGELOG.md`.
