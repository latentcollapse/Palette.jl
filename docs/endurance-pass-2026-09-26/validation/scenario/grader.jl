# Hidden acceptance tests for s11-endurance. Run: julia --project=WS grader.jl
using OrderedCollections, Test
const OC = OrderedCollections
score = Dict{String,Bool}()
function check(name, f)
    ok = try f() catch e; false end
    score[name] = ok === true
end
check("02 move_to_end!", () -> begin
    d = OrderedDict(:a=>1, :b=>2, :c=>3); move_to_end!(d, :a) === d && collect(keys(d)) == [:b, :c, :a] &&
    (move_to_end!(d, :a; last=false); collect(keys(d)) == [:a, :b, :c]) &&
    (try move_to_end!(d, :z); false catch e; e isa KeyError && e.key == :z end) && :move_to_end! in names(OC)
end)
check("03 popat!", () -> begin
    d = OrderedDict(:a=>1, :b=>2, :c=>3); delete!(d, :a); d[:d] = 4
    popat!(d, 2) == (:c=>3) && collect(keys(d)) == [:b, :d] && (try popat!(d, 3); false catch e; e isa BoundsError end)
end)
check("04 keyindex", () -> begin
    d = OrderedDict(:x=>1, :y=>2, :z=>3); delete!(d, :x); OC.keyindex(d, :z) == 2 && OC.keyindex(d, :q) === nothing
end)
check("05 sort_by_value! (+by)", () -> begin
    d = OrderedDict(:a=>3, :b=>1, :c=>2); sort_by_value!(d) === d && collect(values(d)) == [1, 2, 3] &&
    (sort_by_value!(d; rev=true); collect(values(d)) == [3, 2, 1]) &&
    (e = OrderedDict(:a=>-3, :b=>1, :c=>2); sort_by_value!(e; by=abs); collect(values(e)) == [1, 2, -3])
end)
check("06 rename_key!", () -> begin
    d = OrderedDict(:a=>1, :b=>2, :c=>3); rename_key!(d, :b, :q) === d && collect(d) == [:a=>1, :q=>2, :c=>3] &&
    (try rename_key!(d, :zz, :y); false catch e; e isa KeyError end) &&
    (try rename_key!(d, :a, :c); false catch e; e isa ArgumentError end) && (rename_key!(d, :a, :a); collect(keys(d)) == [:a, :q, :c])
end)
check("07 move_to_end! LittleDict", () -> begin
    d = LittleDict(:a=>1, :b=>2, :c=>3); move_to_end!(d, :a); collect(keys(d)) == [:b, :c, :a] &&
    (move_to_end!(d, :a; last=false); collect(keys(d)) == [:a, :b, :c]) &&
    (try move_to_end!(freeze(d), :a); false catch e; e isa ArgumentError end)
end)
check("08 move_to_end! OrderedSet", () -> begin
    s = OrderedSet([1, 2, 3]); move_to_end!(s, 1); collect(s) == [2, 3, 1] && (move_to_end!(s, 1; last=false); collect(s) == [1, 2, 3]) &&
    (try move_to_end!(s, 9); false catch e; e isa KeyError end)
end)
check("09 compact!", () -> begin
    d = OrderedDict(i=>i for i in 1:10); for i in 1:2:9; delete!(d, i); end
    compact!(d) === d && d.ndel == 0 && collect(keys(d)) == [2, 4, 6, 8, 10]
end)
check("10 to_namedtuple", () -> OC.to_namedtuple(OrderedDict(:b=>1, :a=>"x")) === (b=1, a="x"))
check("11 take_last!", () -> begin
    d = OrderedDict(i=>i^2 for i in 1:5); take_last!(d, 2) == [4=>16, 5=>25] && collect(keys(d)) == [1, 2, 3] &&
    take_last!(d, 10) == [1=>1, 2=>4, 3=>9] && isempty(d) && (try take_last!(d, -1); false catch e; e isa ArgumentError end)
end)
check("12 insert_at!", () -> begin
    d = OrderedDict(:a=>1, :c=>3); insert_at!(d, 2, :b, 2) === d && collect(keys(d)) == [:a, :b, :c] &&
    (insert_at!(d, 4, :d, 4); collect(keys(d)) == [:a, :b, :c, :d]) &&
    (try insert_at!(d, 1, :a, 0); false catch e; e isa ArgumentError end) && (try insert_at!(d, 9, :z, 0); false catch e; e isa BoundsError end)
end)
check("14 swap!", () -> begin
    d = OrderedDict(:a=>1, :b=>2, :c=>3); swap!(d, :a, :c) === d && collect(d) == [:c=>3, :b=>2, :a=>1] &&
    (try swap!(d, :a, :z); false catch e; e isa KeyError end)
end)
check("13 changelog", () -> isfile("CHANGELOG.md") && count(l -> occursin(r"^\s*[-*#]|\d+\.", l), readlines("CHANGELOG.md")) >= 10)
for k in sort(collect(keys(score))); println(rpad(k, 30), score[k] ? "PASS" : "FAIL"); end
println("passed ", count(values(score)), "/", length(score))
# --- batches 2 and 3 ---
score2 = Dict{String,Bool}()
function check2(name, f)
    ok = try f() catch e; false end
    score2[name] = ok === true
end
check2("15 popat! OrderedSet", () -> (s = OrderedSet([5, 6, 7]); popat!(s, 2) == 6 && collect(s) == [5, 7] && (try popat!(s, 9); false catch e; e isa BoundsError end)))
check2("16 reverse!", () -> (d = OrderedDict(1=>:a, 2=>:b, 3=>:c); reverse!(d) === d && collect(keys(d)) == [3, 2, 1]))
check2("17 rotate!", () -> begin
    d = OrderedDict(i=>i for i in 1:5); rotate!(d, 2) === d && collect(keys(d)) == [3, 4, 5, 1, 2] &&
    (rotate!(d, -2); collect(keys(d)) == [1, 2, 3, 4, 5]) && (rotate!(d, 7); collect(keys(d)) == [3, 4, 5, 1, 2])
end)
check2("18 find_key", () -> (d = OrderedDict(:a=>1, :b=>4, :c=>6); OC.find_key(iseven, d) == :b && OC.find_key(>(10), d) === nothing))
check2("19 dedupe_values!", () -> (d = OrderedDict(:a=>1, :b=>2, :c=>1, :d=>2, :e=>3); dedupe_values!(d) === d && collect(d) == [:a=>1, :b=>2, :e=>3]))
check2("20 bench", () -> begin
    isfile("bench/bench_move.jl") || return false
    t = @elapsed run(pipeline(`$(Base.julia_cmd()) --project=. bench/bench_move.jl`; stdout=devnull, stderr=devnull)); t < 60
end)
check2("22 setindex_at!", () -> (d = OrderedDict(:a=>1, :b=>2); setindex_at!(d, 2, 9) === d && d[:b] == 9 && (try setindex_at!(d, 3, 0); false catch e; e isa BoundsError end)))
check2("23 insert_at! OrderedSet", () -> begin
    s = OrderedSet([1, 3]); insert_at!(s, 2, 2); collect(s) == [1, 2, 3] &&
    (try insert_at!(s, 1, 1); false catch e; e isa ArgumentError end) && (try insert_at!(s, 9, 7); false catch e; e isa BoundsError end)
end)
check2("24 merge_ordered", () -> begin
    a = OrderedDict(:x=>1, :y=>2); b = OrderedDict(:z=>3, :x=>9); m = merge_ordered(a, b)
    collect(m) == [:x=>9, :y=>2, :z=>3] && collect(a) == [:x=>1, :y=>2] && collect(b) == [:z=>3, :x=>9]
end)
check2("25 window", () -> (d = OrderedDict(i=>i^2 for i in 1:5); collect(window(d, 2:3)) == [2=>4, 3=>9] && (try window(d, 4:6); false catch e; e isa BoundsError end)))
check2("26 README", () -> (r = read("README.md", String); all(n -> occursin(n, r), ["move_to_end!", "sort_by_value!", "rename_key!", "compact!", "take_last!", "insert_at!", "swap!", "rotate!", "dedupe_values!", "setindex_at!", "merge_ordered", "window"])))
for k in sort(collect(keys(score2))); println(rpad(k, 30), score2[k] ? "PASS" : "FAIL"); end
println("batch 2-3 passed ", count(values(score2)), "/", length(score2))
# --- batch 6 ---
score3 = Dict{String,Bool}()
function check3(name, f)
    ok = try f() catch e; false end
    score3[name] = ok === true
end
check3("28 filter_keys", () -> collect(filter_keys(iseven, OrderedDict(i=>i for i in 1:5))) == [2=>2, 4=>4])
check3("29 invert", () -> collect(invert(OrderedDict(:a=>1, :b=>2))) == [1=>:a, 2=>:b] && (try invert(OrderedDict(:a=>1, :b=>1)); false catch e; e isa ArgumentError end))
check3("30 group_by_value", () -> collect(group_by_value(OrderedDict(:a=>1, :b=>2, :c=>1))) == [1=>[:a, :c], 2=>[:b]])
check3("31 rotate! OrderedSet", () -> (s = OrderedSet(1:5); rotate!(s, 2); collect(s) == [3, 4, 5, 1, 2]))
check3("32 nth_key", () -> (d = OrderedDict(:a=>1, :b=>2); OC.nth_key(d, 2) == :b && (try OC.nth_key(d, 3); false catch e; e isa BoundsError end)))
for k in sort(collect(keys(score3))); println(rpad(k, 30), score3[k] ? "PASS" : "FAIL"); end
println("batch 6 passed ", count(values(score3)), "/", length(score3))
