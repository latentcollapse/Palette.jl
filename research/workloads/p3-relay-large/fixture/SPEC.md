# relay 0.5

Each section is a stub in the tree with tests next to it. The tests are the contract; this file says what they check.

## core: quantiles (`core/src/quantile.rs`)

`quantiles(xs, qs)` returns one value per requested quantile, in the order asked.

- NaN values in `xs` are ignored. If no values remain, the result is `Err(Empty)`.
- `Empty` is checked before the quantiles. A quantile outside `[0, 1]` is `Err(BadQuantile(q))` for the first such `q`.
- Values are sorted ascending. For quantile `q`, let `h = (n - 1) * q`. The result is `x[floor(h)] + (h - floor(h)) * (x[floor(h) + 1] - x[floor(h)])`, which is linear interpolation, as numpy's default. At `h = n - 1` the result is `x[n - 1]`.

## core: backoff (`core/src/backoff.rs`)

`schedule(base_ms, factor, cap_ms, attempts)` returns `attempts` delays.

- Delay `i`, counting from 0, is `min(cap_ms, base_ms * factor^i)`.
- It never overflows: arithmetic saturates at `u64::MAX`.
- A factor of 0 means no growth, the same as 1.

## api: query strings (`api/src/query.ts`)

**`parseQuery(s)`:**

- A leading `?` is ignored. Pieces are split on `&`, and empty pieces are skipped.
- A piece splits at its first `=`. A piece with no `=` is a key with the value `""`.
- `+` decodes to a space. `%XX` escapes decode as UTF-8, in keys and values alike.
- A `%` not followed by two hex digits is kept literally.
- A key that appears more than once maps to an array of its values, in order. A key seen once maps to a string.

**`stringifyQuery(q)`:**

- Keys are written in ascending order. An array writes one `key=value` per element, in order, and an empty array writes nothing.
- Encoding keeps `A-Z a-z 0-9 - _ . ~` as they are. A space is written as `+`. Everything else is written as `%XX` with uppercase hex, over its UTF-8 bytes.
- An empty value is written as `key=`.

## planner: packing (`planner/src/planner.ml`)

`pack ~capacity items` packs `(name, size)` items into batches with first-fit decreasing:

- Sort by size descending, and ties by name ascending.
- Place each item in the first batch, in creation order, whose total stays `<= capacity`. If none fits, open a new batch.
- Batches are returned in creation order. The names within a batch are in the order they were placed.
- `Invalid_argument` is raised for `capacity <= 0`, a negative size, or a size greater than `capacity`.

## db: priority (`db/migrations/003_priority.sql`, `db/queries/next_jobs.sql`)

- Migration 003 adds two columns to `jobs`:
  - `priority INTEGER NOT NULL DEFAULT 0`;
  - `queue TEXT NOT NULL DEFAULT 'default'`.
- `next_jobs.sql` returns the next jobs to run:
  - for each queue, at most 2 jobs with status `'queued'`, by priority descending, then id ascending;
  - queues are listed in ascending order;
  - the columns are `queue, id`.

## relayctl: config (`relayctl/config.go`)

`Parse(text)` reads an INI-style config into section → key → value. Keys that come before any section header go in section `""`.

- Lines may end in `\n` or `\r\n`.
- **Comments and blank lines:** a line whose first non-blank character is `;` or `#` is a comment. Comments and blank lines are ignored. A `;` or `#` later in a line is part of the value.
- **Section headers:** `[name]` starts a section. The name is trimmed and lowercased, and must not be empty. A section with no keys still appears, as an empty map. A section that appears twice is merged.
- **Key lines:** `key = value` splits at the first `=`. The key is trimmed and lowercased, and must not be empty. The value is trimmed. For a repeated key, the last value wins.
- **Continuation lines:** a line that starts with a space or tab, and is not blank or a comment, continues the previous key's value when a key precedes it in the current section. It is appended as `"\n" + trimmed line`. With no preceding key, the line is read like any other line.
- **Errors:** any other line is an error. The result is a `*ParseError` whose `Line` is the 1-based number of the first bad line.
