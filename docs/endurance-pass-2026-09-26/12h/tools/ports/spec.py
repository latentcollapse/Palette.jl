"""Python-stdlib port batches for the 12h NeuraJL run.

Each port is a Julia module the agent writes under ports/. The hidden goldens are the
outputs of the adapters below, run on CPython; `oracle` mode serves the same adapters
over stdin so a Julia shim can prove the grader's marshaling end to end.
"""
import ast, base64, bisect, calendar, colorsys, collections, configparser, csv, datetime, difflib, email.utils
import fnmatch, fractions, graphlib, hashlib, heapq, html, io, ipaddress, itertools, json, math, posixpath
import pathlib, pprint, random, shlex, statistics, string, struct, sys, textwrap, urllib.parse, zlib
from xml.sax import saxutils

R = random.Random(20260927)
PORTS = {}


def port(name, module, blurb, funcs):
    def deco(gen):
        PORTS[name] = dict(module=module, blurb=blurb, funcs=funcs, gen=gen)
        return gen
    return deco


def words(n, alphabet="abcdefg"):
    return ["".join(R.choice(alphabet) for _ in range(R.randint(0, 6))) for _ in range(n)]


# ---------------------------------------------------------------- adapters
A = {}
def adapter(port_name):
    def deco(f):
        A.setdefault(port_name, {})[f.__name__] = f
        return f
    return deco

# fnmatch
@adapter("fnmatch")
def fnmatchcase(name, pat): return fnmatch.fnmatchcase(name, pat)
@adapter("fnmatch")
def filter(names, pat): return [n for n in names if fnmatch.fnmatchcase(n, pat)]

@port("fnmatch", "PyFnmatch", "Unix shell-style wildcard matching, as Python's fnmatch module does it on POSIX: `*`, `?`, `[seq]`, `[!seq]`, ranges, and every edge case of bracket parsing (an unclosed `[` is a literal, `]` first in a set is a member, and so on). Matching is case-sensitive.",
      ["fnmatchcase(name::AbstractString, pat::AbstractString) -> Bool", "filter(names::AbstractVector, pat::AbstractString) -> Vector of the names that match, in order (case-sensitive)"])
def _():
    pats = ["*", "?", "a*", "*.py", "[abc]*", "[!abc]*", "[a-c]?", "[]]", "[!]]x", "[", "a[", "[a-", "*[!a-c]", "a*b*c", "??*", "[!]", "\\*", "[*]", "[a-]", "[z-a]", "*.[ch]", "x[!-]y", "[[]", "**a"]
    names = ["", "a", "b", "abc", "a.py", "x.c", "x.h", "]", "[", "a[", "*", "zzz", "a-", "x-y", "xay", "acb", "aXbYc", "[a-", "-", "\\x"] + words(12, "abc.[]-*")
    cases = [("fnmatchcase", [n, p]) for p in pats for n in R.sample(names, 7)]
    cases += [("filter", [R.sample(names, 8), p]) for p in pats[:10]]
    return cases

# shlex
@adapter("shlex")
def split(s): return shlex.split(s)
@adapter("shlex")
def shell_quote(s): return shlex.quote(s)
@adapter("shlex")
def join(parts): return shlex.join(parts)

@port("shlex", "PyShlex", "Python's shlex in POSIX mode: split(s) (comments=False), shell_quote(s) (shlex.quote; quote is a Julia keyword), join(parts). An unclosed quote or a trailing escape is an error (throw).",
      ["split(s::AbstractString) -> Vector{String}", "shell_quote(s::AbstractString) -> String (shlex.quote)", "join(parts::AbstractVector) -> String"])
def _():
    ss = ["a b c", "  a   b  ", "'a b' c", '"a \\"b\\" c"', "a\\ b", "a'b'c", "'a\\b'", '"a\\b"', '"$x \\$y"', "a#b c", "''", '""', "a ''", "'unclosed", '"unclosed', "trail\\",
          "x=1 y='2 3'", "a\tb\nc", 'mixed"quo"\'tes\'', "\\'", '"\\\\"', "é ü", "a;b|c&d", "--flag='a b'"]
    qs = ["", "abc", "a b", "it's", "$HOME", "a\"b", "@%+=:,./-_", "é", "a\nb", "*", "~user", "!"]
    cases = [("split", [s]) for s in ss] + [("shell_quote", [q]) for q in qs]
    cases += [("join", [p]) for p in (["a", "b c"], ["", "x"], ["it's", "$x"], [], ["a\"b", "c'd"])]
    return cases

# textwrap
@adapter("textwrap")
def wrap(text, width): return textwrap.wrap(text, width)
@adapter("textwrap")
def fill(text, width): return textwrap.fill(text, width)
@adapter("textwrap")
def dedent(text): return textwrap.dedent(text)
@adapter("textwrap")
def indent(text, prefix): return textwrap.indent(text, prefix)
@adapter("textwrap")
def shorten(text, width): return textwrap.shorten(text, width)

LOREM = "The quick brown fox jumps over the lazy dog. Well-known long-winded twenty-first-century e-mail addresses like someone@example.com break oddly; supercalifragilisticexpialidocious words too.\tTabs\tand  double  spaces.\nNew lines."
@port("textwrap", "PyTextwrap", "Python's textwrap with default options (expand_tabs, replace_whitespace, drop_whitespace, break_long_words and break_on_hyphens all on, fix_sentence_endings off). shorten uses the default placeholder \" [...]\".",
      ["wrap(text, width::Integer) -> Vector{String}", "fill(text, width::Integer) -> String", "dedent(text) -> String", "indent(text, prefix) -> String (default predicate: lines that are not whitespace-only)", "shorten(text, width::Integer) -> String"])
def _():
    texts = [LOREM, "", "   ", "a", "hyphen-ated-word-chain-here", "x" * 40, "one two  three\tfour\n\nfive", "e.g. Mr. Smith"]
    cases = [("wrap", [t, w]) for t in texts for w in (1, 5, 12, 30, 70)]
    cases += [("fill", [LOREM, w]) for w in (10, 25, 50)]
    cases += [("dedent", [t]) for t in ["  a\n  b", "  a\n\tb", "    a\n  b\n", "\n  a\n\n  b\n", "  a\n   \n  b", "\t a\n\t b", "no\n  indent"]]
    cases += [("indent", [t, p]) for t in ["a\nb\n", "a\n\n  \nb", "", "x\r\ny"] for p in ("> ", "  ")]
    cases += [("shorten", [t, w]) for t in [LOREM, "Hello  world!", "abcdefghijkl mnop"] for w in (8, 12, 30, 200)]
    return cases

# difflib, part one: SequenceMatcher
def _seq(x): return x if isinstance(x, str) else list(x)
@adapter("difflib")
def ratio(a, b): return difflib.SequenceMatcher(None, _seq(a), _seq(b)).ratio()
@adapter("difflib")
def matching_blocks(a, b): return [list(m) for m in difflib.SequenceMatcher(None, _seq(a), _seq(b)).get_matching_blocks()]
@adapter("difflib")
def opcodes(a, b): return [list(o) for o in difflib.SequenceMatcher(None, _seq(a), _seq(b)).get_opcodes()]
@adapter("difflib")
def close_matches(word, possibilities, n, cutoff): return difflib.get_close_matches(word, possibilities, n, cutoff)
@adapter("difflib")
def unified_diff(a, b, fromfile, tofile, n): return list(difflib.unified_diff(a, b, fromfile, tofile, n=n, lineterm=""))
@adapter("difflib")
def context_diff(a, b, fromfile, tofile, n): return list(difflib.context_diff(a, b, fromfile, tofile, n=n, lineterm=""))
@adapter("difflib")
def ndiff(a, b): return [l.rstrip("\n") for l in difflib.ndiff([x + "\n" for x in a], [x + "\n" for x in b])]

def _lines(k):
    base = [f"line {i} " + R.choice(["alpha", "beta", "gamma", "delta"]) for i in range(k)]
    b = list(base)
    for _ in range(max(1, k // 4)):
        op = R.random(); i = R.randrange(len(b) + 1)
        if op < .33 and b: b.pop(min(i, len(b) - 1))
        elif op < .66: b.insert(i, "inserted " + R.choice("xyz"))
        elif b: b[min(i, len(b) - 1)] += " changed"
    return base, b

@port("difflib", "PyDifflib", "Python's difflib.SequenceMatcher with isjunk=None and autojunk on (so the popular-element heuristic applies to sequences of 200 or more). a and b are both strings (compare characters) or both vectors of strings (compare elements). ratio, matching blocks (including the final dummy block) and opcodes must match exactly, and so must get_close_matches.",
      ["ratio(a, b) -> Float64", "matching_blocks(a, b) -> vector of [i, j, n]", "opcodes(a, b) -> vector of [tag, i1, i2, j1, j2] with tag a String", "close_matches(word, possibilities::AbstractVector, n::Integer, cutoff::Real) -> Vector{String}"])
def _():
    pairs = [("", ""), ("abc", ""), ("", "abc"), ("abcd", "bcde"), ("private Thread currentThread;", "private volatile Thread currentThread;"),
             ("qabxcd", "abycdf"), ("aaaa", "aa"), ("abxcd", "abcd"), ("the cat sat", "the hat sat on")]
    s = "".join(R.choice("ab ") for _ in range(260)); t = "".join(R.choice("ab c") for _ in range(240))
    pairs += [(s, t), ("x" * 250 + "y", "y" + "x" * 250), (["a", "b", "c", "d"], ["a", "x", "c", "d", "e"])]
    pairs += [tuple(_lines(k)) for k in (5, 12, 30)]
    cases = [(f, [a, b]) for a, b in pairs for f in ("ratio", "matching_blocks", "opcodes")]
    vocab = ["ape", "apple", "peach", "puppy", "apply", "appel", "happy", "pineapple", "applesauce", "ppl"]
    cases += [("close_matches", [w, vocab, n, c]) for w in ("appel", "pupy", "zzz", "ple") for n, c in ((3, 0.6), (1, 0.0), (5, 0.8))]
    return cases

@port("difflib2", "PyDifflib", "In the same PyDifflib module (ports/difflib.jl): the line-diff generators of Python's difflib, returned as vectors of lines with lineterm=\"\" (no trailing newlines). For ndiff the input lines are given without newlines; behave as Python's ndiff does when every line ends in \"\\n\", with the newline stripped from each output line, including the \"? \" hint lines (default charjunk=IS_CHARACTER_JUNK, linejunk=None).",
      ["unified_diff(a::AbstractVector, b::AbstractVector, fromfile, tofile, n::Integer) -> Vector{String}", "context_diff(a, b, fromfile, tofile, n::Integer) -> Vector{String}", "ndiff(a::AbstractVector, b::AbstractVector) -> Vector{String}"])
def _():
    pairs = [_lines(k) for k in (0, 3, 8, 20, 40)] + [(["one", "two", "three"], ["ore", "tree", "emu"]), (["abcDefghiJkl"], ["abcdefGhijkl"]),
             (["a\tb", "same"], ["a b", "same"]), (["x"], []), ([], ["y"])]
    cases = []
    for a, b in pairs:
        cases += [("unified_diff", [a, b, "a.txt", "b.txt", n]) for n in (0, 1, 3)]
        cases += [("context_diff", [a, b, "a.txt", "b.txt", 3]), ("ndiff", [a, b])]
    return cases

# string
@adapter("string")
def template_substitute(template, mapping): return string.Template(template).substitute(mapping)
@adapter("string")
def template_safe_substitute(template, mapping): return string.Template(template).safe_substitute(mapping)
@adapter("string")
def capwords(s, sep): return string.capwords(s, sep)

@port("string", "PyString", "string.Template substitute and safe_substitute (default delimiter $, default idpattern, $$ escape, ${name} braces; substitute throws on a missing key or an invalid placeholder, safe_substitute leaves them), and string.capwords. mapping values are strings or numbers, rendered as Python's str() would. sep === nothing means the default whitespace splitting.",
      ["template_substitute(template, mapping::AbstractDict) -> String", "template_safe_substitute(template, mapping::AbstractDict) -> String", "capwords(s, sep) -> String"])
def _():
    m = {"who": "tim", "what": "kung pao", "n": 3, "x": 1.5, "_u": "under", "a1": "A"}
    ts = ["$who likes $what", "${who}s", "$$who", "$n items at $x", "$missing", "${missing}", "$", "$1", "cost: $$5", "${who", "$_u$a1", "$who$", "é$who", "${ who}", "$whoever"]
    cases = [(f, [t, m]) for t in ts for f in ("template_substitute", "template_safe_substitute")]
    cases += [("capwords", [s, sep]) for s in ["hello world", "  hello   WORLD  ", "o'neil mcdonald", "a-b c-d", "", "ßtraße ǆ", "x\ty\nz"] for sep in (None, "-", " ")]
    return cases

# heapq
@adapter("heapq")
def heapify(xs): h = list(xs); heapq.heapify(h); return h
@adapter("heapq")
def push_all(xs):
    h = []
    for x in xs: heapq.heappush(h, x)
    return h
@adapter("heapq")
def pop_all(xs): h = list(xs); heapq.heapify(h); return [heapq.heappop(h) for _ in range(len(h))]
@adapter("heapq")
def pushpop_seq(heap, items): h = list(heap); heapq.heapify(h); out = [heapq.heappushpop(h, x) for x in items]; return [out, h]
@adapter("heapq")
def replace_seq(heap, items): h = list(heap); heapq.heapify(h); out = [heapq.heapreplace(h, x) for x in items]; return [out, h]
@adapter("heapq")
def nsmallest(n, xs): return heapq.nsmallest(n, xs)
@adapter("heapq")
def nlargest(n, xs): return heapq.nlargest(n, xs)
@adapter("heapq")
def merge(lists): return list(heapq.merge(*lists))

@port("heapq", "PyHeapq", "Python's heapq, including the exact array layout its sift algorithms produce (heapify, heappush, heappop, heappushpop, heapreplace are compared element by element, not just as valid heaps). replace_seq on an empty heap throws, as heapreplace does.",
      ["heapify(xs) -> Vector (a new heapified copy)", "push_all(xs) -> heap after heappush of each x onto an empty heap", "pop_all(xs) -> heapify a copy, then heappop until empty", "pushpop_seq(heap, items) -> [results, final_heap] (heap is heapified first)", "replace_seq(heap, items) -> [results, final_heap]", "nsmallest(n, xs)", "nlargest(n, xs)", "merge(lists) -> merged Vector"])
def _():
    cases = []
    for k in (0, 1, 2, 7, 16, 33, 100):
        xs = [R.randint(-50, 50) for _ in range(k)]
        cases += [("heapify", [xs]), ("push_all", [xs]), ("pop_all", [xs]), ("nsmallest", [3, xs]), ("nlargest", [5, xs]), ("nsmallest", [k + 2, xs])]
        items = [R.randint(-60, 60) for _ in range(6)]
        cases += [("pushpop_seq", [xs, items]), ("replace_seq", [xs, items])]
    cases += [("merge", [[sorted(R.randint(0, 30) for _ in range(R.randint(0, 6))) for _ in range(m)]]) for m in (0, 1, 3, 5)]
    cases += [("heapify", [[R.random() for _ in range(9)]]), ("nlargest", [0, [1, 2]]), ("nsmallest", [-1, [1, 2]])]
    return cases

# statistics
def _stat(name):
    def f(*a): return getattr(statistics, name)(*a)
    f.__name__ = name; return adapter("statistics")(f)
for _n in ("mean", "fmean", "median", "median_low", "median_high", "mode", "multimode", "pvariance", "variance", "pstdev", "stdev", "harmonic_mean", "geometric_mean"):
    _stat(_n)
@adapter("statistics")
def median_grouped(data, interval): return statistics.median_grouped(data, interval)
@adapter("statistics")
def quantiles(data, n, method): return statistics.quantiles(data, n=n, method=method)

@port("statistics", "PyStatistics", "Python's statistics module. Results are compared numerically (relative tolerance 1e-9), so exact-fraction arithmetic is not required, but every edge case is: empty or too-short data throws, mode/multimode on strings, median_grouped with an interval, quantiles with method \"exclusive\" or \"inclusive\", harmonic_mean with zeros, geometric_mean of non-positive data throws.",
      [f"{n}(data)" for n in ("mean", "fmean", "median", "median_low", "median_high", "mode", "multimode", "pvariance", "variance", "pstdev", "stdev", "harmonic_mean", "geometric_mean")] + ["median_grouped(data, interval)", "quantiles(data, n::Integer, method::AbstractString) -> Vector"])
def _():
    ds = [[1, 2, 3, 4, 4], [2.5, 3.25, 5.5, 11.25, 11.75], [7], [], [1, 1, 2, 2, 3], ["red", "blue", "blue", "red", "green"], [0, 1, 4], [-1, 2, 3],
          [R.gauss(10, 3) for _ in range(40)], [R.randint(1, 9) for _ in range(25)], [1e10, 1, -1e10, 1], [3, 3]]
    fs = ("mean", "fmean", "median", "median_low", "median_high", "mode", "multimode", "pvariance", "variance", "pstdev", "stdev", "harmonic_mean", "geometric_mean")
    cases = [(f, [d]) for d in ds for f in fs]
    cases += [("median_grouped", [d, i]) for d in ([52, 52, 53, 54], [1, 3, 3, 5, 7], [2, 2, 3, 3, 3, 4]) for i in (1, 2)]
    cases += [("quantiles", [d, n, m]) for d in ds[8:10] + [[1, 2]] for n in (2, 4, 10) for m in ("exclusive", "inclusive")]
    return cases

# csv
@adapter("csv")
def reader(text, delimiter, quotechar): return list(csv.reader(io.StringIO(text, newline=""), delimiter=delimiter, quotechar=quotechar))
@adapter("csv")
def write_rows(rows, delimiter):
    buf = io.StringIO(newline=""); csv.writer(buf, delimiter=delimiter).writerows(rows); return buf.getvalue()

@port("csv", "PyCsv", "Python's csv module, default excel dialect apart from the delimiter/quotechar given: doublequote on, skipinitialspace off, strict off, QUOTE_MINIMAL, lineterminator \"\\r\\n\" for writing. Reading accepts \\n, \\r and \\r\\n line endings and quoted fields spanning lines. Writing renders values as Python's str() would (None as an empty field, floats in Python repr form).",
      ["reader(text, delimiter::AbstractString, quotechar::AbstractString) -> Vector of rows (Vector{String})", "write_rows(rows::AbstractVector, delimiter::AbstractString) -> String"])
def _():
    texts = ["a,b,c\n1,2,3\n", "a,b\r\nc,d\r\n", 'a,"b,c",d\n', '"multi\nline",x\n', '"say ""hi""",y\n', 'a, "b" ,c\n', '"unterminated\n', "\n\na\n", 'x"y,z\n', "a,b,\n,,\n", "é,ü\n", "a\rb\r", 'q"",r\n', '"",""\n']
    cases = [("reader", [t, ",", '"']) for t in texts]
    cases += [("reader", ["a;b;'c;d'\n", ";", "'"]), ("reader", ["a\tb\t\"c\td\"\n", "\t", '"'])]
    rows = [[["a", "b"], ["1", "2"]], [["x,y", 'q"z', "line\nbreak", ""]], [[1, 2.5, None, True, 1e16, 0.1]], [[" lead", "trail ", "\r"]], [[]], [["", ""]], [["a;b", "c"]]]
    cases += [("write_rows", [r, d]) for r in rows for d in (",", ";")]
    return cases

# colorsys
for _n in ("rgb_to_hsv", "hsv_to_rgb", "rgb_to_hls", "hls_to_rgb", "rgb_to_yiq", "yiq_to_rgb"):
    def _mk(n):
        def f(a, b, c): return list(getattr(colorsys, n)(a, b, c))
        f.__name__ = n; adapter("colorsys")(f)
    _mk(_n)

@port("colorsys", "PyColorsys", "Python's colorsys conversions, each returning a 3-element vector. Compared with relative tolerance 1e-9.",
      [f"{n}(a, b, c) -> Vector{{Float64}}" for n in ("rgb_to_hsv", "hsv_to_rgb", "rgb_to_hls", "hls_to_rgb", "rgb_to_yiq", "yiq_to_rgb")])
def _():
    pts = [(0, 0, 0), (1, 1, 1), (1, 0, 0), (0.2, 0.4, 0.4), (0.5, 0.5, 0.5), (1.0, 0.5, 0.0)] + [(R.random(), R.random(), R.random()) for _ in range(8)]
    return [(f, list(p)) for p in pts for f in ("rgb_to_hsv", "hsv_to_rgb", "rgb_to_hls", "hls_to_rgb", "rgb_to_yiq", "yiq_to_rgb")]

# bisect + Counter
@adapter("bisect")
def bisect_left(a, x, lo, hi): return bisect.bisect_left(a, x, lo, len(a) if hi is None else hi)
@adapter("bisect")
def bisect_right(a, x, lo, hi): return bisect.bisect_right(a, x, lo, len(a) if hi is None else hi)
@adapter("bisect")
def insort_left(a, x): a = list(a); bisect.insort_left(a, x); return a
@adapter("bisect")
def most_common(items, n): return [list(p) for p in collections.Counter(items).most_common(n)]
@adapter("bisect")
def counter_total_ops(a, b):
    ca, cb = collections.Counter(a), collections.Counter(b)
    return [sorted(map(list, (ca + cb).items())), sorted(map(list, (ca - cb).items())), sorted(map(list, (ca & cb).items())), sorted(map(list, (ca | cb).items()))]

@port("bisect", "PyBisect", "Python's bisect functions (lo, hi as Python indices, 0-based; hi === nothing means len(a); a negative lo throws) and collections.Counter.most_common (ties keep first-insertion order; n === nothing means all) and the Counter +, -, &, | operators (return each result as the sorted vector of [element, count] pairs).",
      ["bisect_left(a, x, lo, hi) -> Int (0-based)", "bisect_right(a, x, lo, hi) -> Int (0-based)", "insort_left(a, x) -> new Vector", "most_common(items, n) -> vector of [item, count]", "counter_total_ops(a, b) -> [sum, difference, intersection, union]"])
def _():
    cases = []
    for a in ([], [1], [1, 2, 2, 2, 3], [0, 10, 20, 30], [1.5, 2.5]):
        for x in (0, 2, 3, 25, 40):
            cases += [("bisect_left", [a, x, 0, None]), ("bisect_right", [a, x, 0, None]), ("insort_left", [a, x])]
        cases += [("bisect_left", [a, 2, 1, len(a)]), ("bisect_right", [a, 2, -1, None])]
    for items in (list("abracadabra"), [3, 1, 3, 2, 1, 3], [], list("zyxzyx")):
        cases += [("most_common", [items, n]) for n in (None, 0, 1, 2, 10)]
    cases += [("counter_total_ops", [list("aabbbc"), list("abbd")]), ("counter_total_ops", [[], list("xx")])]
    return cases

# base64
def _b(s): return s.encode("utf-8")
@adapter("base64")
def b64encode(s): return base64.b64encode(_b(s)).decode()
@adapter("base64")
def b64decode(s): return base64.b64decode(s, validate=True).decode("utf-8")
@adapter("base64")
def urlsafe_b64encode(s): return base64.urlsafe_b64encode(_b(s)).decode()
@adapter("base64")
def b32encode(s): return base64.b32encode(_b(s)).decode()
@adapter("base64")
def b32decode(s): return base64.b32decode(s).decode("utf-8")
@adapter("base64")
def b16encode(s): return base64.b16encode(_b(s)).decode()
@adapter("base64")
def b85encode(s): return base64.b85encode(_b(s)).decode()
@adapter("base64")
def a85encode(s): return base64.a85encode(_b(s)).decode()
@adapter("base64")
def a85decode(s): return base64.a85decode(s).decode("utf-8")

@port("base64", "PyBase64", "Python's base64 encodings of the UTF-8 bytes of a string (decoders return the decoded bytes as a UTF-8 string). b64decode is strict (validate=True): bad characters or bad padding throw. b32decode and a85decode throw on malformed input as Python does. Defaults everywhere else (a85encode: no foldspaces, no wrapcol, no pad).",
      [f"{n}(s::AbstractString) -> String" for n in ("b64encode", "b64decode", "urlsafe_b64encode", "b32encode", "b32decode", "b16encode", "b85encode", "a85encode", "a85decode")])
def _():
    ss = ["", "f", "fo", "foo", "foob", "fooba", "foobar", "\x00\x00\x00\x00", "    ", "héllo wörld ✓", "~~~???>>>", "a" * 57]
    cases = [(f, [s]) for s in ss for f in ("b64encode", "urlsafe_b64encode", "b32encode", "b16encode", "b85encode", "a85encode")]
    cases += [("b64decode", [base64.b64encode(_b(s)).decode()]) for s in ss] + [("b64decode", [bad]) for bad in ("Zm9v=", "Zm9", "Zm9v!", "Zg==Zg==")]
    cases += [("b32decode", [base64.b32encode(_b(s)).decode()]) for s in ss] + [("b32decode", ["MZXW6==="]), ("b32decode", ["mzxw6==="])]
    cases += [("a85decode", [base64.a85encode(_b(s)).decode()]) for s in ss] + [("a85decode", ["z"]), ("a85decode", ["<~9jqo^~>"])]
    return cases

# urllib.parse
@adapter("urlparse")
def urlsplit(url): return list(urllib.parse.urlsplit(url))
@adapter("urlparse")
def urlunsplit(parts): return urllib.parse.urlunsplit(parts)
@adapter("urlparse")
def url_quote(s, safe): return urllib.parse.quote(s, safe=safe)
@adapter("urlparse")
def quote_plus(s): return urllib.parse.quote_plus(s)
@adapter("urlparse")
def unquote(s): return urllib.parse.unquote(s)
@adapter("urlparse")
def unquote_plus(s): return urllib.parse.unquote_plus(s)
@adapter("urlparse")
def urlencode(pairs): return urllib.parse.urlencode([tuple(p) for p in pairs])
@adapter("urlparse")
def parse_qsl(qs, keep_blank_values): return [list(p) for p in urllib.parse.parse_qsl(qs, keep_blank_values=keep_blank_values)]
@adapter("urlparse")
def urljoin(base, url): return urllib.parse.urljoin(base, url)

@port("urlparse", "PyUrlparse", "Python's urllib.parse: urlsplit/urlunsplit (5-part, allow_fragments on), quote/quote_plus/unquote/unquote_plus (UTF-8, errors=\"replace\" on decode), urlencode of [key, value] pairs, parse_qsl (& separator only), and urljoin including every RFC 3986 relative-reference example. urlsplit raises on an invalid IPv6 netloc; throw there.",
      ["urlsplit(url) -> [scheme, netloc, path, query, fragment]", "urlunsplit(parts::AbstractVector) -> String", "url_quote(s, safe) -> String (urllib.parse.quote; quote is a Julia keyword)", "quote_plus(s)", "unquote(s)", "unquote_plus(s)", "urlencode(pairs) -> String", "parse_qsl(qs, keep_blank_values::Bool) -> vector of [k, v]", "urljoin(base, url) -> String"])
def _():
    urls = ["http://www.example.com:80/path;p?q=1&r=2#frag", "HTTPS://User:Pw@Host.COM/a/b/", "mailto:someone@example.com", "file:///etc/passwd", "//netloc/only", "/just/path?x", "?q", "#f", "", "http://[::1]:8080/x", "http://[::1/x", "a:b", "scheme-only:", "http://h/p?a=1#", "  http://leading.space/  ", "http://h/%7Euser"]
    cases = [("urlsplit", [u]) for u in urls if u != "http://[::1/x"] + [("urlsplit", ["http://[::1/x"])]
    cases += [("urlunsplit", [list(urllib.parse.urlsplit(u))]) for u in urls if u != "http://[::1/x"]
    cases += [("urlunsplit", [["http", "h", "p", "", ""]]), ("urlunsplit", [["", "", "//x", "", ""]])]
    qs = ["a b&c=d/é", "/~user", "", "%", "safe-_.~", "100%", "✓/?#[]@!$&'()*+,;="]
    cases += [("url_quote", [s, safe]) for s in qs for safe in ("/", "", "@:")] + [("quote_plus", [s]) for s in qs]
    cases += [("unquote", [s]) for s in ["%41%42", "%e2%9c%93", "%zz", "%", "a+b", "%C3%28", "%E2%9C"]] + [("unquote_plus", [s]) for s in ["a+b%20c", "++", "%2B"]]
    cases += [("urlencode", [p]) for p in ([["a", "1"], ["b", "x y"]], [["é", "✓"], ["k", ""]], [])]
    cases += [("parse_qsl", [q, k]) for q in ["a=1&b=2", "a=1&&b=", "a", "a=1;b=2", "x=%20+y", "=v", "a=1&a=2"] for k in (False, True)]
    base = "http://a/b/c/d;p?q"
    refs = ["g:h", "g", "./g", "g/", "/g", "//g", "?y", "g?y", "#s", "g#s", "g?y#s", ";x", "g;x", "g;x?y#s", "", ".", "./", "..", "../", "../g", "../..", "../../", "../../g", "../../../g", "../../../../g", "/./g", "/../g", "g.", ".g", "g..", "..g", "./../g", "./g/.", "g/./h", "g/../h", "g;x=1/./y", "g;x=1/../y", "g?y/./x", "g?y/../x", "g#s/./x", "g#s/../x", "http:g"]
    cases += [("urljoin", [base, r]) for r in refs] + [("urljoin", ["http://a/b/", "../../x"]), ("urljoin", ["", "x"]), ("urljoin", ["mailto:x@y", "z"])]
    return cases

# posixpath
@adapter("posixpath")
def normpath(p): return posixpath.normpath(p)
@adapter("posixpath")
def join(parts): return posixpath.join(*parts)
@adapter("posixpath")
def split(p): return list(posixpath.split(p))
@adapter("posixpath")
def splitext(p): return list(posixpath.splitext(p))
@adapter("posixpath")
def basename(p): return posixpath.basename(p)
@adapter("posixpath")
def dirname(p): return posixpath.dirname(p)
@adapter("posixpath")
def commonpath(ps): return posixpath.commonpath(ps)
@adapter("posixpath")
def commonprefix(ps): return posixpath.commonprefix(ps)
@adapter("posixpath")
def relpath(p, start): return posixpath.relpath(p, start)

@port("posixpath", "PyPosixpath", "Python's posixpath functions (pure string manipulation; no filesystem access). relpath is only called with absolute paths. commonpath throws on an empty list or on a mix of absolute and relative paths.",
      ["normpath(p)", "join(parts::AbstractVector)", "split(p) -> [head, tail]", "splitext(p) -> [root, ext]", "basename(p)", "dirname(p)", "commonpath(paths)", "commonprefix(paths)", "relpath(p, start)"])
def _():
    ps = ["", "/", "//", "///", "a", "/a/b/", "a//b/./c/..", "/../x", "../../y", "./", "a/b/../../..", "//a//b", ".bashrc", "a.tar.gz", "/x/.hidden", "dir.d/file", "a/b.", "..."]
    cases = [(f, [p]) for p in ps for f in ("normpath", "split", "splitext", "basename", "dirname")]
    cases += [("join", [j]) for j in (["a", "b"], ["a/", "b"], ["a", "/b", "c"], ["", "x"], ["a", ""], ["/"])]
    cases += [("commonpath", [c]) for c in (["/usr/lib", "/usr/local/lib"], ["a/b", "a/c"], ["/a"], [], ["/a", "b"], ["/a//b/", "/a/b/c"])]
    cases += [("commonprefix", [c]) for c in (["/usr/lib", "/usr/local/lib"], [], ["abc", "abd", "ab"])]
    cases += [("relpath", [p, s]) for p, s in (("/a/b/c", "/a"), ("/a", "/a/b/c"), ("/x/y", "/a/b"), ("/a", "/a"), ("/", "/a/b"), ("/a/./b/../c", "/a"))]
    return cases

# calendar
@adapter("calendar")
def isleap(y): return calendar.isleap(y)
@adapter("calendar")
def leapdays(y1, y2): return calendar.leapdays(y1, y2)
@adapter("calendar")
def weekday(y, m, d): return calendar.weekday(y, m, d)
@adapter("calendar")
def monthrange(y, m): return list(calendar.monthrange(y, m))
@adapter("calendar")
def monthcalendar(y, m): return calendar.monthcalendar(y, m)
@adapter("calendar")
def month(y, m, w, l): return calendar.month(y, m, w, l)
@adapter("calendar")
def month_firstweekday(y, m, firstweekday): return calendar.TextCalendar(firstweekday).formatmonth(y, m)
@adapter("calendar")
def timegm(t): return calendar.timegm(tuple(t) + (0, 0, 0))

@port("calendar", "PyCalendar", "Python's calendar module in the C locale: English month and day names, TextCalendar layout exactly (month(y, m, w, l) is calendar.month; month_firstweekday uses TextCalendar(firstweekday).formatmonth with default w and l). timegm takes [year, month, day, hour, minute, second]. Out-of-range months throw.",
      ["isleap(y)", "leapdays(y1, y2)", "weekday(y, m, d) (Monday == 0)", "monthrange(y, m) -> [first_weekday, days]", "monthcalendar(y, m) -> vector of weeks", "month(y, m, w, l) -> String", "month_firstweekday(y, m, firstweekday) -> String", "timegm(t::AbstractVector) -> Int"])
def _():
    cases = [("isleap", [y]) for y in (1900, 2000, 2024, 2023, 1600, 1)]
    cases += [("leapdays", [a, b]) for a, b in ((1900, 2000), (2000, 2001), (2024, 1990), (1, 9999))]
    cases += [("weekday", list(d)) for d in ((2026, 9, 27), (1970, 1, 1), (2000, 2, 29), (1, 1, 1), (9999, 12, 31))]
    cases += [(f, [y, m]) for y, m in ((2026, 9), (2024, 2), (2023, 2), (1999, 12), (2026, 13)) for f in ("monthrange", "monthcalendar")]
    cases += [("month", [y, m, w, l]) for y, m in ((2026, 9), (2024, 2)) for w, l in ((0, 0), (2, 1), (3, 2), (5, 1))]
    cases += [("month_firstweekday", [2026, m, f]) for m in (2, 3) for f in (0, 6, 3)]
    cases += [("timegm", [t]) for t in ([1970, 1, 1, 0, 0, 0], [2026, 9, 27, 12, 30, 5], [1969, 12, 31, 23, 59, 59], [2000, 2, 30, 0, 0, 0])]
    return cases

# fractions
def _F(s): return fractions.Fraction(s)
@adapter("fractions")
def fraction(s): return str(_F(s))
@adapter("fractions")
def add(a, b): return str(_F(a) + _F(b))
@adapter("fractions")
def mul(a, b): return str(_F(a) * _F(b))
@adapter("fractions")
def div(a, b): return str(_F(a) / _F(b))
@adapter("fractions")
def limit_denominator(s, max_den): return str(_F(s).limit_denominator(max_den))
@adapter("fractions")
def from_float(x): return str(fractions.Fraction(x))
@adapter("fractions")
def fraction_round(s, ndigits): return str(round(_F(s), ndigits)) if ndigits is not None else str(round(_F(s)))

@port("fractions", "PyFractions", "Python's fractions.Fraction, with fractions written as Python's str() writes them (\"n/d\" in lowest terms with the sign on the numerator, or just \"n\" when the denominator is 1). Parsing accepts everything Fraction(str) accepts (\"3/4\", \" -1.25 \", \"1e-3\", \"1_000/3\") and throws on the rest. Numerators can exceed Int64. round uses round-half-even; ndigits === nothing returns an integer.",
      ["fraction(s) -> String", "add(a, b)", "mul(a, b)", "div(a, b) (division by zero throws)", "limit_denominator(s, max_den::Integer)", "from_float(x::Float64) (exact binary value)", "fraction_round(s, ndigits)"])
def _():
    fs = ["3/4", "-6/8", " 7 ", "1.25", "-0.5e2", "1e-3", "1_000/3", "0/5", "3/0", "abc", "1/-3", "+2/4", "123456789012345678901234567890/7"]
    cases = [("fraction", [f]) for f in fs]
    pairs = [("1/3", "1/6"), ("-2/3", "3/4"), ("5", "1/5"), ("99999999999/7", "1/99999999999"), ("1/2", "0")]
    cases += [(op, list(p)) for p in pairs for op in ("add", "mul", "div")]
    cases += [("limit_denominator", [s, m]) for s in ("3.141592653589793", "-0.3333333", "1/7", "1234567/100000") for m in (1, 10, 1000, 1000000)]
    cases += [("from_float", [x]) for x in (0.1, 0.5, -2.75, 1e-10, 3.0, 1e22)]
    cases += [("fraction_round", [s, n]) for s in ("5/2", "7/2", "-5/2", "2675/1000", "1/3") for n in (None, 0, 1, 2)]
    return cases

# json
@adapter("json")
def dumps(obj, indent, sort_keys, ensure_ascii): return json.dumps(obj, indent=indent, sort_keys=sort_keys, ensure_ascii=ensure_ascii)

@port("json", "PyJson", "Python's json.dumps output, byte for byte: separators (\", \" and \": \" without indent; \",\" and newline with it; indent 0 still inserts newlines), float formatting as Python's float repr (1e+16, 1e-05, 0.1, 2.0), ensure_ascii \\uXXXX escapes with surrogate pairs above U+FFFF, the short escapes (\\n, \\\", \\\\ and so on), sort_keys, and nested empty containers ([] and {}). obj arrives as parsed JSON: an insertion-ordered AbstractDict{String,Any}, Vector{Any}, String, Int64, Float64, Bool or nothing.",
      ["dumps(obj, indent, sort_keys::Bool, ensure_ascii::Bool) -> String (indent === nothing means compact)"])
def _():
    objs = [{"b": 1, "a": [1, 2.0, None, True, False], "c": {"z": {}, "y": []}}, [0.1, 1e16, 1e-5, 123456789.0, -0.0, 1.5e300, 1e-7, 100.0, 9007199254740993],
            "é ✓ 😀 \n\t\"\\ \x01 \x7f /", {"é": "ü", "": ""}, [], {}, [[[]]], {"k": [{"a": 1}, []]}, 42, None]
    return [("dumps", [o, i, s, e]) for o in objs for i, s, e in ((None, False, True), (2, True, True), (0, False, False), (4, False, True))]

# numeric
@adapter("numeric")
def fsum(xs): return math.fsum(xs)
@adapter("numeric")
def float_repr(x): return repr(x)
@adapter("numeric")
def float_hex(x): return x.hex()
@adapter("numeric")
def float_fromhex(s): return float.fromhex(s)
@adapter("numeric")
def py_round(x, ndigits): return round(x, ndigits)
@adapter("numeric")
def comb(n, k): return str(math.comb(n, k))
@adapter("numeric")
def isqrt(n): return math.isqrt(n)

@port("numeric", "PyNumeric", "Numeric behaviours of Python: math.fsum (exact, Shewchuk-style), repr() of a float (shortest round-tripping digits, Python's exponent thresholds and formatting), float.hex and float.fromhex, round(x, ndigits) on floats (correctly rounded, half-even on the exact decimal value, so round(2.675, 2) == 2.67), math.comb returned as a decimal string (it can exceed Int64), and math.isqrt.",
      ["fsum(xs) -> Float64", "float_repr(x::Float64) -> String", "float_hex(x::Float64) -> String", "float_fromhex(s) -> Float64", "py_round(x::Float64, ndigits::Integer) -> Float64", "comb(n, k) -> String", "isqrt(n) -> Int"])
def _():
    xs = [0.1, 1.0, 1e16, 1e-5, 1e-4, 123456789012345678.0, 5e-324, 1.7976931348623157e308, -0.0, 0.3, 2.675, 1 / 3, 100.0, 1e22, 1e15, 9007199254740993.0, 0.000123]
    cases = [("float_repr", [x]) for x in xs] + [("float_hex", [x]) for x in xs]
    cases += [("float_fromhex", [s]) for s in ("0x1.8p1", "-0x1p-1074", "0x.8", "inf", "0x1p1024", "  0X1.FFFFFFFFFFFFFP+1023 ", "0x1.fffffffffffff8p1023", "nope")]
    cases += [("py_round", [x, n]) for x in (2.675, 0.125, 0.375, 1.005, -2.5, 1234.5678, 1e-10) for n in (0, 1, 2, -2)]
    cases += [("fsum", [l]) for l in ([0.1] * 10, [1e100, 1.0, -1e100], [1, 1e-16, 1e-16], [], [R.uniform(-1e6, 1e6) for _ in range(50)], [1e308, 1e308, -1e308])]
    cases += [("comb", [n, k]) for n, k in ((5, 2), (100, 50), (10, 11), (0, 0), (-1, 1))]
    cases += [("isqrt", [n]) for n in (0, 1, 15, 16, 10**18, 2**62 - 1, -1)]
    return cases

# struct
@adapter("struct")
def pack(fmt, values):
    vals = [v.encode("latin-1") if isinstance(v, str) else v for v in values]
    return struct.pack(fmt, *vals).hex()
@adapter("struct")
def unpack(fmt, hexstr):
    return [v.decode("latin-1") if isinstance(v, bytes) else v for v in struct.unpack(fmt, bytes.fromhex(hexstr))]
@adapter("struct")
def calcsize(fmt): return struct.calcsize(fmt)

@port("struct", "PyStruct", "Python's struct.pack / unpack / calcsize on x86-64 Linux for the codes x c b B ? h H i I l L q Q n N e f d s p and byte-order prefixes @ = < > ! (native @ uses native sizes and alignment; the others standard sizes and no alignment), with repeat counts. Bytes values (for c, s and p) are passed and returned as Latin-1 strings; packed data is a lowercase hex string. Range errors, wrong argument counts, and wrong buffer lengths throw.",
      ["pack(fmt, values::AbstractVector) -> hex String", "unpack(fmt, hex) -> Vector", "calcsize(fmt) -> Int"])
def _():
    fmts = [("<h", [1]), (">h", [-2]), ("!I", [4294967295]), ("<q", [-(2**62)]), ("@bi", [1, 2]), ("@ci", ["x", 7]), ("<3s", ["abcd"]), ("<5s", ["ab"]), ("<5p", ["abc"]),
            (">?x?", [True, False]), ("<e", [1.5]), ("<f", [0.1]), (">d", [-2.5]), ("@hq", [1, 2]), ("=hq", [1, 2]), ("<2h2x", [1, 2]), ("<B", [256]), ("<b", [-129]),
            ("<h", [1, 2]), ("@n", [-5]), ("@N", [5]), ("<0s", []), ("!3B", [1, 2, 3]), ("<e", [65520.0])]
    cases = [("pack", [f, v]) for f, v in fmts] + [("calcsize", [f]) for f, _ in fmts] + [("calcsize", ["@bq"]), ("calcsize", ["@qb"]), ("calcsize", ["@i0q"])]
    for f, v in fmts:
        try: cases.append(("unpack", [f, struct.pack(f, *[x.encode("latin-1") if isinstance(x, str) else x for x in v]).hex()]))
        except (struct.error, OverflowError): pass
    cases += [("unpack", ["<h", "01"]), ("unpack", ["<?", "02"]), ("unpack", ["<e", "007c"])]
    return cases

# graphlib
@adapter("graphlib")
def static_order(graph):
    ts = graphlib.TopologicalSorter()
    for node, preds in graph: ts.add(node, *preds)
    return list(ts.static_order())
@adapter("graphlib")
def ready_batches(graph):
    ts = graphlib.TopologicalSorter()
    for node, preds in graph: ts.add(node, *preds)
    ts.prepare(); out = []
    while ts.is_active():
        batch = list(ts.get_ready()); out.append(batch); ts.done(*batch)
    return out

@port("graphlib", "PyGraphlib", "Python's graphlib.TopologicalSorter, with its exact output order. graph is a vector of [node, [predecessors...]] pairs, applied as successive ts.add(node, *predecessors) calls in order (a node may appear more than once). static_order is the order static_order() yields; ready_batches is what successive get_ready() calls return when each whole batch is marked done before the next call. A cycle throws.",
      ["static_order(graph) -> Vector{String}", "ready_batches(graph) -> vector of Vector{String}"])
def _():
    gs = [[["d", ["b", "c"]], ["b", ["a"]], ["c", ["a"]]], [["a", []]], [], [["x", ["y"]], ["y", ["x"]]], [["a", ["a"]]],
          [["b", ["a"]], ["b", ["c"]], ["a", []], ["c", []]]]
    for _ in range(6):
        nodes = [f"n{i}" for i in range(R.randint(4, 12))]
        g = [[n, R.sample(nodes[:i], min(i, R.randint(0, 3)))] for i, n in enumerate(nodes)]
        R.shuffle(g); gs.append(g)
    return [(f, [g]) for g in gs for f in ("static_order", "ready_batches")]

# format spec
@adapter("format")
def format_value(value, spec): return format(value, spec)

@port("format", "PyFormat", "Python's format(value, spec) for int, float, str and bool values: the whole format-spec mini-language (fill, align < > ^ =, sign + - space, z, #, 0, width, grouping , and _, precision, and types b c d o x X n e E f F g G % s, plus the empty type). Locale-dependent n behaves as in the C locale. Invalid specs for the value's type throw. value arrives as Int64, Float64, String or Bool.",
      ["format_value(value, spec::AbstractString) -> String"])
def _():
    ints = [0, 42, -42, 255, 1234567, -9876543210]
    floats = [0.0, -0.0, 3.14159, -2.5, 1234567.891, 1e-7, 1e16, 0.5, 1.5, 2.5, 123456789.0, 0.1, float("inf"), float("nan"), -1e-300]
    ispecs = ["", "d", "5d", "<5", ">8", "^9", "*^9", "=+8", "+d", " d", "08d", ",d", "_d", "_x", "b", "#b", "o", "#o", "x", "#X", "c", ",.2f", "e", "%", "n", "010,d", "s", ".3"]
    fspecs = ["", "f", ".2f", ".0f", "#.0f", "e", ".3E", "g", ".3g", "#.3g", "G", "%", ".1%", ",.2f", "_.3f", "010.3f", "+.1f", " .1e", "z.1f", "=^12.4f", "n", ".17g", ".0e", "x", "r"]
    sspecs = ["", "s", "10", "<10", ">10", "^10", ".2", "*^7.3", "d", "=5"]
    cases = [("format_value", [v, s]) for v in ints for s in ispecs]
    cases += [("format_value", [v, s]) for v in floats for s in fspecs]
    cases += [("format_value", [v, s]) for v in ("", "héllo", "abc") for s in sspecs]
    cases += [("format_value", [b, s]) for b in (True, False) for s in ("", "d", ">6", "s", "x")]
    return cases

# str methods
def _strm(name, f):
    f.__name__ = name; adapter("pystr")(f)
_strm("title", lambda s: s.title()); _strm("capitalize", lambda s: s.capitalize()); _strm("swapcase", lambda s: s.swapcase())
_strm("casefold", lambda s: s.casefold()); _strm("splitlines", lambda s, keepends: s.splitlines(keepends)); _strm("expandtabs", lambda s, n: s.expandtabs(n))
_strm("center", lambda s, w, fill: s.center(w, fill)); _strm("zfill", lambda s, w: s.zfill(w)); _strm("partition", lambda s, sep: list(s.partition(sep)))
_strm("rpartition", lambda s, sep: list(s.rpartition(sep))); _strm("split", lambda s, sep, maxsplit: s.split(sep, maxsplit)); _strm("rsplit", lambda s, sep, maxsplit: s.rsplit(sep, maxsplit))
_strm("strip", lambda s, chars: s.strip(chars)); _strm("isidentifier", lambda s: s.isidentifier()); _strm("str_repr", lambda s: repr(s))

@port("pystr", "PyStr", "Python str methods with Python's exact Unicode semantics: title (word boundaries are any non-cased character, so \"they're\" -> \"They'Re\"), capitalize, swapcase, casefold (full case folding, ß -> ss), splitlines (every Python line boundary, including \\x1c-\\x1e, \\x85, \\u2028, \\u2029, \\v, \\f), expandtabs, center (Python's placement of the odd padding character), zfill, partition/rpartition, split/rsplit with sep === nothing meaning whitespace runs and maxsplit -1 meaning no limit, strip with chars === nothing meaning whitespace, isidentifier, and repr() of a string (quote choice, escapes, printable non-ASCII kept).",
      ["title(s)", "capitalize(s)", "swapcase(s)", "casefold(s)", "splitlines(s, keepends::Bool)", "expandtabs(s, tabsize)", "center(s, width, fill)", "zfill(s, width)", "partition(s, sep)", "rpartition(s, sep)", "split(s, sep, maxsplit)", "rsplit(s, sep, maxsplit)", "strip(s, chars)", "isidentifier(s)", "str_repr(s)"])
def _():
    ss = ["hello world", "they're bill's friends", "ǆemal ǳ", "ßtraße İstanbul ﬁne", "MiXeD 123abc", "", "a\tb\t\tc", "  pad  ", "x\r\ny\rz\n\x0b\x0c\x1c\x1d\x1e\x85\u2028\u2029end", "-42", "+7", "αβγ ΣΑΣ", "l'été", "don't", "'q\"", "tab\there\\ \x00 \x7f é 😀 \u200b"]
    cases = [(f, [s]) for s in ss for f in ("title", "capitalize", "swapcase", "casefold", "str_repr")]
    cases += [("splitlines", [s, k]) for s in ss[7:9] + ["a\n\nb\n", "\n"] for k in (False, True)]
    cases += [("expandtabs", [s, n]) for s in ("a\tb\t\tc", "\t", "ab\ncd\te", "12345678\tx") for n in (8, 4, 1, 0)]
    cases += [("center", [s, w, f]) for s in ("abc", "ab", "", "é") for w, f in ((2, " "), (6, "*"), (7, "-"), (8, " "))]
    cases += [("zfill", [s, w]) for s in ("42", "-42", "+x", "", "abc") for w in (1, 5)]
    cases += [(f, [s, sep]) for s in ("a,b,c", "abc", ",", "") for sep in (",", "b", "bc") for f in ("partition", "rpartition")] + [("partition", ["abc", ""])]
    cases += [(f, [s, sep, m]) for s in ("  a  b\tc\n", "a,,b,", "", "x") for sep, m in ((None, -1), (None, 1), (",", -1), (",", 1), (",", 0)) for f in ("split", "rsplit")]
    cases += [("strip", [s, c]) for s in ("  x  ", "xxhixx", "\u2003y\u3000", "") for c in (None, "x", "")]
    cases += [("isidentifier", [s]) for s in ("abc", "_", "1a", "é", "a-b", "", "ǆ", "℘x", "x·")]
    return cases

# random
def _rnd(seed): return random.Random(seed)
@adapter("random")
def random_floats(seed, n): r = _rnd(seed); return [r.random() for _ in range(n)]
@adapter("random")
def getrandbits_seq(seed, k, n): r = _rnd(seed); return [r.getrandbits(k) for _ in range(n)]
@adapter("random")
def randrange_seq(seed, start, stop, step, n): r = _rnd(seed); return [r.randrange(start, stop, step) for _ in range(n)]
@adapter("random")
def shuffle(seed, xs): r = _rnd(seed); xs = list(xs); r.shuffle(xs); return xs
@adapter("random")
def choice_seq(seed, xs, n): r = _rnd(seed); return [r.choice(xs) for _ in range(n)]
@adapter("random")
def sample(seed, xs, k): return _rnd(seed).sample(xs, k)
@adapter("random")
def gauss_seq(seed, mu, sigma, n): r = _rnd(seed); return [r.gauss(mu, sigma) for _ in range(n)]
@adapter("random")
def uniform_seq(seed, a, b, n): r = _rnd(seed); return [r.uniform(a, b) for _ in range(n)]

@port("random", "PyRandom", "Bit-exact reproduction of CPython's random.Random for integer seeds: the MT19937 generator, CPython's seeding (init_by_array over the 32-bit words of abs(seed)), random() from two 32-bit outputs, getrandbits, randrange via _randbelow's rejection sampling, shuffle, choice, sample (both of its internal algorithms, selected by population size), gauss (with its cached second value) and uniform. Each function starts from a fresh generator seeded with seed.",
      ["random_floats(seed, n)", "getrandbits_seq(seed, k, n) (k <= 62)", "randrange_seq(seed, start, stop, step, n)", "shuffle(seed, xs)", "choice_seq(seed, xs, n)", "sample(seed, xs, k)", "gauss_seq(seed, mu, sigma, n)", "uniform_seq(seed, a, b, n)"])
def _():
    seeds = [0, 1, 42, 12345678901, -7, 2**40 + 3]
    cases = []
    for s in seeds:
        cases += [("random_floats", [s, 5]), ("getrandbits_seq", [s, 1, 8]), ("getrandbits_seq", [s, 33, 3]), ("getrandbits_seq", [s, 62, 2]),
                  ("randrange_seq", [s, 0, 10, 1, 8]), ("randrange_seq", [s, -5, 100, 7, 5]), ("randrange_seq", [s, 0, 2**40, 1, 3]),
                  ("shuffle", [s, list(range(10))]), ("choice_seq", [s, list("abcde"), 6]), ("sample", [s, list(range(30)), 5]),
                  ("sample", [s, list(range(3000)), 4]), ("gauss_seq", [s, 0.0, 1.0, 3]), ("uniform_seq", [s, -1.0, 1.0, 3])]
    cases += [("randrange_seq", [1, 5, 5, 1, 1]), ("sample", [1, [1, 2], 3]), ("choice_seq", [1, [], 1])]
    return cases

# configparser
@adapter("configparser")
def read_string(text):
    cp = configparser.ConfigParser(); cp.read_string(text)
    return {s: dict(cp.items(s)) for s in cp.sections()}
@adapter("configparser")
def read_raw(text):
    cp = configparser.ConfigParser(interpolation=None); cp.read_string(text)
    return {s: dict(cp.items(s)) for s in cp.sections()}

@port("configparser", "PyConfig", "Python's configparser.ConfigParser reading from a string with default settings: = and : delimiters, # and ; full-line comments only, keys lowercased, values stripped, indented continuation lines (empty lines inside values kept per Python's rules), the DEFAULT section merged into every section's items, BasicInterpolation (%(name)s, %% escape, max depth 10) for read_string and none for read_raw. Duplicate sections or options, missing section headers, lines without a delimiter, and bad interpolation throw. Return an insertion-ordered dict: section -> (key -> value), with sections in file order and keys in Python's items() order.",
      ["read_string(text) -> AbstractDict", "read_raw(text) -> AbstractDict"])
def _():
    texts = ["[a]\nx = 1\ny: two\n", "[DEFAULT]\nbase = /srv\n[paths]\nlogs = %(base)s/logs\nlit = 100%%\n", "[s]\nKey = Value\n  continued\n\n  after blank\nnext=1\n",
             "# c\n; c2\n[s]\na = 1 # not a comment\n", "[s]\na=1\n[s]\nb=2\n", "[s]\na=1\na=2\n", "x=1\n", "[s]\nnodelim\n", "[s]\na = %(missing)s\n",
             "[s]\na = %(b)s\nb = %(a)s\n", "[s]\nempty =\n", "[DEFAULT]\nk = d\n[one]\nk = o\n[two]\n", "[ spaced ]\n k = v \n", "[s]\nA=1\nb = x=y:z\n"]
    return [(f, [t]) for t in texts for f in ("read_string", "read_raw")]

# ipaddress
@adapter("ipaddress")
def network_info(s, strict):
    n = ipaddress.ip_network(s, strict=strict)
    return [str(n.network_address), str(n.broadcast_address), str(n.netmask), str(n.hostmask), n.prefixlen, n.num_addresses]
@adapter("ipaddress")
def subnets(s, new_prefix): return [str(x) for x in ipaddress.ip_network(s).subnets(new_prefix=new_prefix)]
@adapter("ipaddress")
def supernet(s, new_prefix): return str(ipaddress.ip_network(s).supernet(new_prefix=new_prefix))
@adapter("ipaddress")
def collapse(nets): return [str(x) for x in ipaddress.collapse_addresses([ipaddress.ip_network(n) for n in nets])]
@adapter("ipaddress")
def exclude(net, other): return sorted(str(x) for x in ipaddress.ip_network(net).address_exclude(ipaddress.ip_network(other)))
@adapter("ipaddress")
def classify(addr):
    a = ipaddress.ip_address(addr)
    return [a.is_private, a.is_global, a.is_loopback, a.is_multicast, a.is_link_local, a.is_reserved, a.is_unspecified]
@adapter("ipaddress")
def summarize(first, last): return [str(x) for x in ipaddress.summarize_address_range(ipaddress.ip_address(first), ipaddress.ip_address(last))]

@port("ipaddress", "PyIpaddress", "Python 3.14's ipaddress module for IPv4 only: network parsing (strict and non-strict, prefix or netmask or hostmask forms), subnets, supernet, collapse_addresses, address_exclude (sorted), summarize_address_range, and address classification flags exactly as Python 3.14 defines them (its is_private/is_global tables changed in 3.13). Invalid input throws.",
      ["network_info(s, strict::Bool) -> [network, broadcast, netmask, hostmask, prefixlen, num_addresses]", "subnets(s, new_prefix)", "supernet(s, new_prefix)", "collapse(nets)", "exclude(net, other)", "classify(addr) -> [is_private, is_global, is_loopback, is_multicast, is_link_local, is_reserved, is_unspecified]", "summarize(first, last)"])
def _():
    nets = ["192.168.1.0/24", "10.0.0.0/8", "192.168.1.5/24", "0.0.0.0/0", "1.2.3.4/32", "172.16.0.0/255.240.0.0", "10.0.0.0/0.0.0.255", "300.1.1.1/8", "1.2.3.0/33"]
    cases = [("network_info", [n, s]) for n in nets for s in (True, False)]
    cases += [("subnets", [n, p]) for n, p in (("192.168.0.0/24", 26), ("10.0.0.0/30", 32), ("10.0.0.0/24", 23))]
    cases += [("supernet", [n, p]) for n, p in (("192.168.1.0/24", 16), ("0.0.0.0/0", 0), ("10.0.0.0/8", 9))]
    cases += [("collapse", [l]) for l in (["192.0.2.0/25", "192.0.2.128/25"], ["10.0.0.0/24", "10.0.0.0/16", "10.1.0.0/16"], [], ["1.0.0.0/32", "1.0.0.1/32", "1.0.0.2/32"])]
    cases += [("exclude", list(p)) for p in (("192.0.2.0/28", "192.0.2.1/32"), ("10.0.0.0/8", "10.128.0.0/9"), ("10.0.0.0/8", "11.0.0.0/8"))]
    cases += [("classify", [a]) for a in ("10.1.2.3", "8.8.8.8", "127.0.0.1", "224.0.0.1", "169.254.1.1", "240.0.0.1", "0.0.0.0", "100.64.0.1", "192.0.0.9", "192.88.99.1", "255.255.255.255", "198.18.0.1")]
    cases += [("summarize", list(p)) for p in (("192.0.2.0", "192.0.2.130"), ("0.0.0.0", "255.255.255.255"), ("10.0.0.5", "10.0.0.5"), ("10.0.0.9", "10.0.0.1"))]
    return cases

# datetime / strftime
@adapter("strftime")
def strftime(t, fmt): return datetime.datetime(*t).strftime(fmt)
@adapter("strftime")
def isocalendar(y, m, d): return list(datetime.date(y, m, d).isocalendar())
@adapter("strftime")
def add_days(iso, n): return (datetime.date.fromisoformat(iso) + datetime.timedelta(days=n)).isoformat()
@adapter("strftime")
def toordinal(y, m, d): return datetime.date(y, m, d).toordinal()
@adapter("strftime")
def fromordinal(n): return datetime.date.fromordinal(n).isoformat()
@adapter("strftime")
def fromisoformat(s): return datetime.datetime.fromisoformat(s).isoformat()

@port("strftime", "PyStrftime", "Python datetime behaviour in the C locale: strftime for %a %A %b %B %d %H %I %j %m %M %p %S %U %w %W %y %Y %G %V %u %% on naive datetimes (t = [year, month, day, hour, minute, second]); isocalendar; date arithmetic; toordinal/fromordinal; datetime.fromisoformat (Python 3.11+ rules: accepts basic and extended ISO 8601 forms, fractional seconds, the T or space separator, and UTC offsets) re-rendered with isoformat(). Invalid dates throw.",
      ["strftime(t::AbstractVector, fmt) -> String", "isocalendar(y, m, d) -> [year, week, weekday]", "add_days(iso_date, n) -> iso date", "toordinal(y, m, d)", "fromordinal(n) -> iso date", "fromisoformat(s) -> isoformat() string"])
def _():
    ts = [[2026, 9, 27, 13, 5, 9], [2024, 12, 30, 0, 0, 0], [2021, 1, 3, 12, 0, 0], [1999, 12, 31, 23, 59, 59], [1, 1, 1, 0, 0, 0], [2026, 1, 1, 7, 30, 0]]
    fmts = ["%Y-%m-%d %H:%M:%S", "%a %A %b %B", "%j %U %W %w", "%I %p", "%y %G-W%V-%u", "100%% %d/%m"]
    cases = [("strftime", [t, f]) for t in ts for f in fmts] + [("strftime", [[2026, 2, 30, 0, 0, 0], "%Y"])]
    cases += [("isocalendar", t[:3]) for t in ts] + [("isocalendar", [2020, 12, 31]), ("isocalendar", [2027, 1, 1])]
    cases += [("add_days", [d, n]) for d in ("2024-02-28", "2023-12-31", "0001-01-01") for n in (1, 365, -1)]
    cases += [("toordinal", t[:3]) for t in ts] + [("fromordinal", [n]) for n in (1, 730120, 739886, 3652059, 0)]
    cases += [("fromisoformat", [s]) for s in ("2026-09-27", "2026-09-27T13:05", "2026-09-27 13:05:09.5", "20260927T130509", "2026-09-27T13:05:09+02:00", "2026-09-27T13:05:09Z", "2026-W39-7", "2026-13-01", "2026-09-27T25:00")]
    return cases

# checksums
@adapter("checksum")
def crc32(s): return zlib.crc32(s.encode())
@adapter("checksum")
def adler32(s): return zlib.adler32(s.encode())
@adapter("checksum")
def md5_hex(s): return hashlib.md5(s.encode()).hexdigest()
@adapter("checksum")
def sha1_hex(s): return hashlib.sha1(s.encode()).hexdigest()
@adapter("checksum")
def crc32_chain(parts): v = 0; [v := zlib.crc32(p.encode(), v) for p in parts]; return v

@port("checksum", "PyChecksum", "zlib.crc32, zlib.adler32 (both unsigned, over the UTF-8 bytes of s), hashlib.md5 and hashlib.sha1 hex digests, and crc32 chaining (crc32(b, previous)). Write MD5 yourself; other Julia standard libraries are allowed.",
      ["crc32(s) -> Int", "adler32(s) -> Int", "md5_hex(s) -> String", "sha1_hex(s) -> String", "crc32_chain(parts) -> Int"])
def _():
    ss = ["", "a", "abc", "message digest", "The quick brown fox jumps over the lazy dog", "é✓😀", "x" * 55, "y" * 56, "z" * 64, "w" * 5553]
    cases = [(f, [s]) for s in ss for f in ("crc32", "adler32", "md5_hex", "sha1_hex")]
    cases += [("crc32_chain", [p]) for p in (["ab", "c"], [], ["", "x"], ["hello ", "world", "!"])]
    return cases

# pprint
@adapter("pprint")
def pformat(obj, width): return pprint.pformat(obj, width=width)

@port("pprint", "PyPprint", "Python's pprint.pformat(obj, width=width) with the other defaults (indent 1, sort_dicts on, compact off): Python reprs of str/int/float/bool/None, dict and list layout, and the splitting of long strings into parenthesised adjacent literals. obj arrives as parsed JSON: an insertion-ordered AbstractDict{String,Any}, Vector{Any}, String, Int64, Float64, Bool or nothing.",
      ["pformat(obj, width::Integer) -> String"])
def _():
    big = {"name": "endurance", "numbers": list(range(30)), "nested": {"b": [1.5, None, True], "a": {"deep": ["x" * 30, "y" * 30]}}, "text": "the quick brown fox jumps over the lazy dog " * 3, "e": {}, "l": []}
    objs = [big, list(range(40)), ["short", "list"], {"k": "v"}, "a long string that will need splitting across several lines when narrow " * 2, 1e16, [[1, 2], [3, [4, [5, [6]]]]], {"é": "ü✓", "'q'": "\"dq\""}, [], {}]
    return [("pformat", [o, w]) for o in objs for w in (80, 40, 20, 5)]

# itertools
@adapter("itertools")
def combinations(xs, r): return [list(c) for c in itertools.combinations(xs, r)]
@adapter("itertools")
def permutations(xs, r): return [list(c) for c in itertools.permutations(xs, r)]
@adapter("itertools")
def product(lists, repeat): return [list(c) for c in itertools.product(*lists, repeat=repeat)]
@adapter("itertools")
def combinations_with_replacement(xs, r): return [list(c) for c in itertools.combinations_with_replacement(xs, r)]
@adapter("itertools")
def accumulate(xs, initial): return list(itertools.accumulate(xs, initial=initial))
@adapter("itertools")
def groupby(xs): return [[k, list(g)] for k, g in itertools.groupby(xs)]
@adapter("itertools")
def batched(xs, n): return [list(b) for b in itertools.batched(xs, n)]
@adapter("itertools")
def pairwise(xs): return [list(p) for p in itertools.pairwise(xs)]
@adapter("itertools")
def islice(xs, start, stop, step): return list(itertools.islice(xs, start, stop, step))
@adapter("itertools")
def zip_longest(lists, fillvalue): return [list(z) for z in itertools.zip_longest(*lists, fillvalue=fillvalue)]

@port("itertools", "PyItertools", "Python's itertools results, materialised as vectors in Python's exact output order. r === nothing in permutations means len(xs); islice's start/stop/step follow Python (stop === nothing means no limit, negatives throw); batched with n < 1 throws; accumulate sums with an optional initial value (initial === nothing means none).",
      ["combinations(xs, r)", "permutations(xs, r)", "product(lists, repeat)", "combinations_with_replacement(xs, r)", "accumulate(xs, initial)", "groupby(xs) -> vector of [key, items]", "batched(xs, n)", "pairwise(xs)", "islice(xs, start, stop, step)", "zip_longest(lists, fillvalue)"])
def _():
    cases = [("combinations", [list("ABCD"), r]) for r in (0, 2, 4, 5)] + [("permutations", [list("abc"), r]) for r in (None, 2, 0, 4)]
    cases += [("product", [l, rep]) for l, rep in (([["a", "b"], [1, 2, 3]], 1), ([["x", "y"]], 2), ([], 1), ([["a"], []], 1))]
    cases += [("combinations_with_replacement", [list("abc"), r]) for r in (0, 2, 3)]
    cases += [("accumulate", [xs, i]) for xs, i in (([1, 2, 3, 4], None), ([1, 2, 3], 100), ([], None), ([], 5), ([0.5, 0.25], None))]
    cases += [("groupby", [xs]) for xs in (list("AAAABBBCCDAABBB"), [], [1, 1, 2, 1])]
    cases += [("batched", [list(range(7)), n]) for n in (1, 3, 7, 10, 0)] + [("pairwise", [xs]) for xs in (list("ABCD"), [1], [])]
    cases += [("islice", [list(range(10)), a, b, c]) for a, b, c in ((0, 5, 1), (2, None, 3), (5, 2, 1), (0, None, 1), (-1, 3, 1), (1, 20, 4))]
    cases += [("zip_longest", [l, f]) for l, f in (([[1, 2, 3], ["a"]], None), ([[1], [2, 3], []], "-"), ([], 0))]
    return cases

# escaping
@adapter("escape")
def html_escape(s, quote): return html.escape(s, quote)
@adapter("escape")
def html_unescape(s): return html.unescape(s)
@adapter("escape")
def sax_escape(s): return saxutils.escape(s)
@adapter("escape")
def sax_unescape(s): return saxutils.unescape(s)
@adapter("escape")
def quoteattr(s): return saxutils.quoteattr(s)

@port("escape", "PyEscape", "Python's html.escape and html.unescape (all HTML5 named character references, including the ones matched without a trailing semicolon, numeric references with invalid and Windows-1252-remapped code points, exactly as Python 3.14 does it), and xml.sax.saxutils escape/unescape/quoteattr with no extra entities.",
      ["html_escape(s, quote::Bool)", "html_unescape(s)", "sax_escape(s)", "sax_unescape(s)", "quoteattr(s)"])
def _():
    ss = ["<a href=\"x\">'&'</a>", "plain", "", "&amp;&lt;&gt;&quot;&#39;", "&copy &copy; &COPY; &notit; &notin;", "&#65;&#x42;&#X43;", "&#0; &#x80; &#x9f; &#xD800; &#x110000; &#1114111;",
          "&amp &ampx &AMP;", "&nosuch; &#; &#x; &", "&lang;&rang;&NotNestedGreaterGreater;&fjlig;", "&#128512;&#x1F600;", "\"quoted\" and 'single' \n\t"]
    cases = [(f, [s]) for s in ss for f in ("html_unescape", "sax_escape", "sax_unescape", "quoteattr")]
    cases += [("html_escape", [s, q]) for s in ss for q in (True, False)]
    return cases

# email.utils
@adapter("emailutils")
def parseaddr(s): return list(email.utils.parseaddr(s))
@adapter("emailutils")
def formataddr(pair): return email.utils.formataddr(tuple(pair))
@adapter("emailutils")
def parsedate(s):
    t = email.utils.parsedate_tz(s)
    return None if t is None else list(t)
@adapter("emailutils")
def getaddresses(fields): return [list(p) for p in email.utils.getaddresses(fields)]

@port("emailutils", "PyEmailUtils", "Python 3.14's email.utils address and date helpers: parseaddr (strict mode, the default, which returns [\"\", \"\"] for anything it rejects), formataddr of [realname, address] (quoting as Python does; only ASCII names are tested), parsedate_tz (returns nothing on failure, otherwise a 10-element vector as Python's tuple, with the offset in seconds or nothing), and getaddresses over a vector of header values (strict mode).",
      ["parseaddr(s) -> [realname, address]", "formataddr(pair) -> String", "parsedate(s) -> Vector or nothing", "getaddresses(fields) -> vector of [realname, address]"])
def _():
    addrs = ["John Doe <jdoe@example.com>", "jdoe@example.com", "\"Doe, John\" <jdoe@example.com>", "<bare@example.com>", "jdoe@example.com (John Doe)", "", "not an address", "a@b, c@d", "\"quoted \\\" name\" <q@x.org>", "Name <a@b> trailing"]
    cases = [("parseaddr", [a]) for a in addrs]
    cases += [("formataddr", [p]) for p in (["John Doe", "jdoe@example.com"], ["", "a@b"], ["Doe, John", "j@x"], ["A \"B\" C", "q@x"], ["x.y", "z@w"])]
    cases += [("parsedate", [d]) for d in ("Sun, 27 Sep 2026 13:05:09 +0200", "27 Sep 2026 13:05 GMT", "Sun, 27 Sep 26 13:05:09 -0000", "Tue, 1 Jan 2019 00:00:00 EST", "garbage", "Sun, 27 Sep 2026 13:05:09", "27-Sep-2026 13:05:09 +0000")]
    cases += [("getaddresses", [f]) for f in (["a@b, C D <c@d>"], ["x@y", "\"q, r\" <s@t>"], [""], ["a@b@c"])]
    return cases

# literal_eval
def _plain(v):
    if isinstance(v, tuple): return [_plain(x) for x in v]
    if isinstance(v, list): return [_plain(x) for x in v]
    if isinstance(v, dict): return {str(k): _plain(x) for k, x in v.items()}
    return v
@adapter("literal")
def literal_eval(s):
    v = ast.literal_eval(s)
    if isinstance(v, (set, frozenset, bytes, complex)) or (isinstance(v, int) and not isinstance(v, bool) and abs(v) >= 2**63): raise ValueError("outside the port's value set")
    if isinstance(v, dict) and not all(isinstance(k, str) for k in v): raise ValueError("outside the port's value set")
    return _plain(v)

@port("literal", "PyLiteral", "A port of ast.literal_eval restricted to this value set: ints (all literal forms: 0x, 0o, 0b, underscores; results within Int64), floats (all literal forms, including 1., .5, 1e3, 1_0.5), strings (single, double and triple quotes, r and u prefixes, every escape except \\N{...}, adjacent-literal concatenation), True/False/None, lists, tuples (returned as vectors), dicts with string keys (insertion-ordered), and unary +/- on numbers. Anything else, including names, calls, sets, bytes, complex numbers, f-strings, binary operators, and malformed syntax, throws.",
      ["literal_eval(s) -> value"])
def _():
    ss = ["1", "-0x1F", "0o17", "0b1010", "1_000_000", "1.", ".5", "1e3", "-1_0.5e-1", "'a'", "\"b\"", "'''tri\nple'''", "r'\\n'", "'\\n\\t\\x41\\u00e9\\U0001F600\\101'", "'a' 'b' \"c\"",
          "True", "None", "[1, (2, 3), {'k': [None]}]", "()", "(1,)", "{}", "{'a': 1, 'b': {'c': 2}}", "  [1, 2 ,3 ,]  ", "+5", "--5", "1+2", "x", "f(1)", "{1, 2}", "b'x'", "1j",
          "f'x'", "[1, 2", "'unterminated", "0777", "1__0", "{1: 2}", "'\\N{DASH}'", "9223372036854775807", "9223372036854775808", "u'x'", "(1, 2) + (3,)", "-True"]
    return [("literal_eval", [s]) for s in ss]


# ---------------------------------------------------------------- output
def enc(v):
    if isinstance(v, float) and (v != v or v in (float("inf"), float("-inf"))):
        return {"__float__": repr(v)}
    if isinstance(v, dict): return {k: enc(x) for k, x in v.items()}
    if isinstance(v, (list, tuple)): return [enc(x) for x in v]
    return v


def run_case(name, fn, args):
    try:
        return enc(A[name][fn](*args))
    except Exception as e:  # the port must throw here
        return {"__error__": type(e).__name__}


def build(out_dir):
    out = pathlib.Path(out_dir); out.mkdir(parents=True, exist_ok=True)
    goldens = {}
    for name, p in PORTS.items():
        adapters_name = "difflib" if name == "difflib2" else name
        cases = [[fn, enc(args), run_case(adapters_name, fn, args)] for fn, args in p["gen"]()]
        goldens[name] = {"module": p["module"], "file": "ports/" + ("difflib" if name == "difflib2" else name) + ".jl", "cases": cases}
    (out / "goldens.json").write_text(json.dumps(goldens, ensure_ascii=False))
    return goldens


if __name__ == "__main__":
    if sys.argv[1] == "oracle":  # stdin: [port, fn, args] -> stdout: result
        name, fn, args = json.loads(sys.stdin.read())
        def dec(v):
            if isinstance(v, dict): return float(v["__float__"]) if "__float__" in v and len(v) == 1 else {k: dec(x) for k, x in v.items()}
            if isinstance(v, list): return [dec(x) for x in v]
            return v
        print(json.dumps(run_case(name, fn, dec(args)), ensure_ascii=False))
    else:
        g = build(sys.argv[2])
        for k, v in g.items():
            errs = sum(1 for c in v["cases"] if isinstance(c[2], dict) and "__error__" in c[2])
            print(f"{k:14s} {v['module']:14s} {len(v['cases']):4d} cases, {errs} expect an error")
