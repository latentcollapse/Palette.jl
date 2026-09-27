using Serialization
make_adder(n) = x -> x + n
add3 = make_adder(3)
counter = let c = Ref(0); () -> (c[] += 1) end
counter(); counter()
anon = x -> 2x
compose = add3 ∘ anon
nested = Dict(:f => add3, :g => [anon, counter])
struct Wrap; f::Function; end
w = Wrap(add3)
open("clos.bin", "w") do io; serialize(io, (add3, counter, anon, compose, nested, w)); end
println("saved: ", add3(1), " ", counter(), " ", anon(5), " ", compose(5))
