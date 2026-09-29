using TOMLLite, Test

@testset "TOMLLite" begin
    @test TOMLLite.parse("a = 1") == Dict("a" => 1)
end
