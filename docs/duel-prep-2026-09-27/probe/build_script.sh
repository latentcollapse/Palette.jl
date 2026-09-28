set -e
echo "PATH=$PATH"; echo "whoami=$(whoami 2>&1)"; echo "USER=${USER:-unset}"
cargo new -q --vcs none rs && (cd rs && cargo build -q --offline && ./target/debug/rs)
mkdir ts && cd ts && printf 'const x: number = 41; console.log("ts", x + 1);\n' > a.ts && tsc a.ts && node a.js && cd ..
mkdir -p ml/bin && cd ml && printf '(lang dune 3.0)\n' > dune-project && printf '(executable (name m))\n' > bin/dune && printf 'let () = print_endline "ocaml ok"\n' > bin/m.ml && dune build 2>&1 && ./_build/default/bin/m.exe && cd ..
printf 'create table t(x); insert into t values (1),(2); select sum(x) from t;\n' | sqlite3 :memory:
mkdir go1 && cd go1 && printf 'package main\nimport "fmt"\nfunc main(){ fmt.Println("go ok") }\n' > m.go && GOFLAGS=-mod=mod GOCACHE=/tmp/gocache go run m.go && cd ..
initdb -D /tmp/pg -U pg >/dev/null && pg_ctl -D /tmp/pg -o "-k /tmp -c listen_addresses=''" -l /tmp/pg.log start >/dev/null && sleep 2 && psql -h /tmp -U pg -d postgres -Atc "select 40+2" && pg_ctl -D /tmp/pg stop >/dev/null
echo ALL-BUILT
