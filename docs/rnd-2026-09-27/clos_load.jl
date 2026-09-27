using Serialization
# A fresh process. Only the named definitions are rebuilt from source, as revival does.
make_adder(n) = x -> x + n
struct Wrap; f::Function; end
add3, counter, anon, compose, nested, w = open(deserialize, "clos.bin")
println("loaded: add3(1)=", add3(1), " counter()=", counter(), " anon(5)=", anon(5), " compose(5)=", compose(5), " nested=", nested[:f](10), " ", nested[:g][2](), " w=", w.f(0))
println("aliasing kept: ", nested[:g][2] === counter, " ", nested[:f] === add3)
