# stdin is a pipe fed by the shell: one line now, one line 1 s later.
l1 = readline(stdin)
t = time(); seen = nothing
while time() - t < 3
    Base.process_events()
    if bytesavailable(stdin) > 0; global seen = round(time() - t, digits=2); break; end
    x = sum(rand(10^5))   # busy, never yields
end
println("first: ", l1, "  bytesavailable after process_events saw the 2nd line at: ", seen)
t = time(); seen2 = nothing
while time() - t < 3
    yield()
    if bytesavailable(stdin) > 0; global seen2 = round(time() - t, digits=2); break; end
    x = sum(rand(10^5))
end
println("with yield(): ", seen2)
