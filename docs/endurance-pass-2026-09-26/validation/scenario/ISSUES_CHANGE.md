
## Update from a teammate

- Issue 5 changed: `sort_by_value!` also takes a keyword `by=identity`, applied to each value before comparing, like `sort`'s `by`.
- New issue 14: add and export `swap!(d::OrderedDict, a, b)`, which swaps the positions of keys `a` and `b` (values stay with their keys). Throws `KeyError` for an absent key. Returns `d`.
