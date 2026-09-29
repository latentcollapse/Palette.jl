// Query strings for the job API. See SPEC.md, "api: query strings".

export type Query = Record<string, string | string[]>;

export function parseQuery(s: string): Query {
  throw new Error("parseQuery: not implemented");
}

export function stringifyQuery(q: Query): string {
  throw new Error("stringifyQuery: not implemented");
}
