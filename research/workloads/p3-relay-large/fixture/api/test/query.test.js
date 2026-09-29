const { test } = require("node:test");
const assert = require("node:assert");
const { parseQuery, stringifyQuery } = require("../dist/src/query.js");

test("plain pairs", () => {
  assert.deepStrictEqual(parseQuery("a=1&b=two"), { a: "1", b: "two" });
});
test("a leading question mark is ignored", () => {
  assert.deepStrictEqual(parseQuery("?a=1"), { a: "1" });
});
test("empty input and empty pieces", () => {
  assert.deepStrictEqual(parseQuery(""), {});
  assert.deepStrictEqual(parseQuery("?"), {});
  assert.deepStrictEqual(parseQuery("a=1&&b=2&"), { a: "1", b: "2" });
});
test("a key with no equals sign has an empty value", () => {
  assert.deepStrictEqual(parseQuery("flag&x=1"), { flag: "", x: "1" });
});
test("only the first equals sign splits", () => {
  assert.deepStrictEqual(parseQuery("expr=a=b"), { expr: "a=b" });
});
test("repeated keys become an array, in order", () => {
  assert.deepStrictEqual(parseQuery("t=x&u=1&t=y&t=z"), { t: ["x", "y", "z"], u: "1" });
});
test("plus is a space, and percent escapes decode as UTF-8", () => {
  assert.deepStrictEqual(parseQuery("q=hello+world&n=%C3%A9t%C3%A9&p=%2B1"), { q: "hello world", n: "été", p: "+1" });
});
test("a malformed percent escape is kept literally", () => {
  assert.deepStrictEqual(parseQuery("a=100%&b=%zz&c=%4"), { a: "100%", b: "%zz", c: "%4" });
});
test("keys are decoded too", () => {
  assert.deepStrictEqual(parseQuery("a%20b=1"), { "a b": "1" });
});
test("stringify sorts keys and keeps array order", () => {
  assert.strictEqual(stringifyQuery({ b: "2", a: ["y", "x"] }), "a=y&a=x&b=2");
});
test("stringify encodes spaces as plus and reserved characters as escapes", () => {
  assert.strictEqual(stringifyQuery({ q: "a b&c=d", e: "été", s: "~-_.!" }), "e=%C3%A9t%C3%A9&q=a+b%26c%3Dd&s=~-_.%21");
});
test("stringify writes an empty value as key=", () => {
  assert.strictEqual(stringifyQuery({ flag: "" }), "flag=");
});
test("an empty array writes nothing", () => {
  assert.strictEqual(stringifyQuery({ a: [], b: "1" }), "b=1");
});
test("round trip", () => {
  const q = { job: ["j 1", "j+2"], since: "2026-09-28", note: "100% done" };
  assert.deepStrictEqual(parseQuery(stringifyQuery(q)), q);
});
