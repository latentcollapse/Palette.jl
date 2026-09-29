test: test-core test-load test-api test-planner test-db test-ctl
test-core:
	cd core && cargo test --offline --color never
test-load:
	bash tools/load_check.sh
test-api:
	cd api && tsc -p . && node --test test/
test-planner:
	cd planner && dune test --display short
test-db:
	bash db/test/check.sh && bash db/test/check_next.sh
test-ctl:
	cd relayctl && go test ./...
.PHONY: test test-core test-load test-api test-planner test-db test-ctl
