const { test } = require("node:test");
const assert = require("node:assert");
const { describe, stamp } = require("../dist/src/client.js");

test("stamp is the UTC calendar date", () => {
  assert.strictEqual(stamp(new Date(Date.UTC(2026, 8, 28, 23, 0))), "2026-09-28");
});
test("describe names the job", () => {
  assert.strictEqual(describe({ jobId: "j7", startedAt: new Date(Date.UTC(2026, 0, 2)), rows: 3 }), "j7: 3 rows since 2026-01-02");
});
