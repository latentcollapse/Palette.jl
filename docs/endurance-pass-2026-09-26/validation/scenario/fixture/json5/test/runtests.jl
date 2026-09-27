using JSON5Lite, Test

@testset "JSON5Lite" begin
    @test JSON5Lite.parse("{a: 1}") == Dict("a" => 1)
    @test JSON5Lite.parse("[1, 2,]") == Any[1, 2]
end
