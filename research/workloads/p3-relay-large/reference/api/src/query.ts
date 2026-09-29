// Query strings for the job API. See SPEC.md, "api: query strings".

export type Query = Record<string, string | string[]>;

function decode(s: string): string {
  const bytes: number[] = [];
  const enc = new TextEncoder();
  for (let i = 0; i < s.length; ) {
    const c = s[i];
    if (c === "%" && /^[0-9A-Fa-f]{2}$/.test(s.slice(i + 1, i + 3))) {
      bytes.push(parseInt(s.slice(i + 1, i + 3), 16)); i += 3;
    } else {
      const cp = s.codePointAt(i)!;
      const ch = String.fromCodePoint(cp);
      bytes.push(...enc.encode(ch === "+" ? " " : ch)); i += ch.length;
    }
  }
  return new TextDecoder().decode(new Uint8Array(bytes));
}

function encode(s: string): string {
  let out = "";
  for (const b of new TextEncoder().encode(s)) {
    const ch = String.fromCharCode(b);
    if (/[A-Za-z0-9\-_.~]/.test(ch)) out += ch;
    else if (ch === " ") out += "+";
    else out += "%" + b.toString(16).toUpperCase().padStart(2, "0");
  }
  return out;
}

export function parseQuery(s: string): Query {
  const q: Query = {};
  for (const piece of s.replace(/^\?/, "").split("&")) {
    if (piece === "") continue;
    const i = piece.indexOf("=");
    const k = decode(i < 0 ? piece : piece.slice(0, i));
    const v = i < 0 ? "" : decode(piece.slice(i + 1));
    const prev = q[k];
    q[k] = prev === undefined ? v : Array.isArray(prev) ? [...prev, v] : [prev, v];
  }
  return q;
}

export function stringifyQuery(q: Query): string {
  const parts: string[] = [];
  for (const k of Object.keys(q).sort()) {
    const v = q[k];
    for (const x of Array.isArray(v) ? v : [v]) parts.push(`${encode(k)}=${encode(x)}`);
  }
  return parts.join("&");
}
