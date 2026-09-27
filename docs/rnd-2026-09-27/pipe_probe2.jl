fd = ccall(:dup, Cint, (Cint,), 0); io = open(Base.RawFD(fd))
function waiting()
    bytesavailable(io) > 0 && return true
    pfd = Ref((fd, Cshort(0x001), Cshort(0)))
    ccall(:poll, Cint, (Ptr{Cvoid}, Culong, Cint), pfd, 1, 0) > 0 && (pfd[][3] & 0x011) != 0
end
l1 = readline(io)
println("right after the first line: ", waiting())
t = time(); seen = nothing
while time() - t < 3
    if waiting(); global seen = round(time() - t, digits=2); break; end
    x = sum(rand(10^5))
end
println("second line seen at ", seen, " s; it still reads: ", repr(readline(io)))
