# Global search

Search is a **provider contract**, not an index. `apps/web/search/` holds the
aggregator; each domain owns its own searchable queryset.

## The rule that shapes everything

**The aggregator never queries a domain.** It asks a provider, and every
provider starts from the domain's already-scoped queryset:

| Provider | Starts from |
| --- | --- |
| People | `directory_queryset(actor)` |
| Announcements | `visible_announcements(actor)` |
| Office resources | `effective_resources_queryset(actor)` |
| Offices | Active offices — brokerage-public name and city only |

Search is therefore exactly as permissive as the pages those functions already
serve, and a scope fix in a domain reaches search without anybody remembering
to mirror it.

The alternative — a central index the aggregator filters itself — is how search
becomes the one surface that leaks. It would need its own copy of every
domain's rules, and that copy would drift.

## What a provider promises

* **Authorization is the domain's**, applied before anything is projected.
* **Titles and snippets are plain text.** No HTML crosses the boundary, so
  there is nothing to sanitize and no highlight to escape — the client
  highlights by matching the same query against the plain string.
* **Only fields the actor may read.** Email is matched *and* shown only with
  the administration grant: matching on a field you cannot see turns search
  into an oracle — type an address, watch a result appear.
* **A cap**, so one busy domain cannot crowd out the rest.

## Isolation, caps, budget

* A source whose permission the actor lacks is **never called and never
  named**. "No results in Transactions" would still disclose a Transactions.
* A provider that raises is caught, marked `failed`, and reported. One domain
  being down must not empty the response, and a shorter list that looks
  complete is worse than an honest gap.
* `TIME_BUDGET_SECONDS` bounds the whole run. Past it the remaining providers
  are skipped and reported rather than the request hanging on the slowest one.
* `RATE_LIMIT_REQUESTS` per `RATE_LIMIT_WINDOW_SECONDS`, keyed by user. The
  full results page is deliberately **not** limited: it is one navigation, and
  somebody following "see all" must never meet a 429.

## Ranking

`apps/web/search/ranking.py` has one implementation per database that has one,
chosen from `connection.vendor` rather than a setting — a setting can disagree
with the database it points at, and the cost of being wrong is a 500 on every
search.

**PostgreSQL.** A weighted `tsvector` (title A, summary B, body C, so a title
hit outranks a body hit), matched with `websearch_to_tsquery` so quoted phrases
and `-exclusions` work and a stray operator is text rather than an error.
Trigram similarity widens it, so `Fairfx` still finds Fairfax.

**Everything else.** Substring matching. Not dead code — the test suite runs on
SQLite, so this is the path CI exercises, and it has to return the same rows in
the same order.

### Filter with operators, rank with functions

The only two filters an index can answer:

```
vector @@ query   → the GIN full-text index
field % 'text'    → the GIN trigram index
```

`ts_rank(...) > 0` and `similarity(...) > 0.3` express the same intent and are
**not** index-usable: PostgreSQL computes them per row, so an index built for
them is never chosen. This shipped wrong once — the first version filtered on
`ts_rank`, and `EXPLAIN` with `enable_seqscan = off` still showed a sequential
scan, meaning the indexes were dead weight. Ranking functions now appear only
in `ORDER BY`, over rows the operators already narrowed.

`django.contrib.postgres` is in `INSTALLED_APPS` for exactly one reason: it
registers `__trigram_similar`, which compiles to `%`.

### Indexes

Created by `announcements/0008` and `user/0025` through the conditional
operations in `apps/web/search/operations.py`, which no-op away from
PostgreSQL — the test database is SQLite and would fail on `CREATE EXTENSION`.
They stay **out of migration state** (`state_forwards` is a no-op), so models
need not declare PostgreSQL index classes and `makemigrations --check` is clean
on both backends.

| Index | Kind |
| --- | --- |
| `announcement_search_fts`, `office_resource_search_fts` | GIN over the weighted vector |
| `announcement_search_trgm`, `office_resource_search_trgm` | GIN trigram on title |
| `user_search_name_trgm` | GIN trigram on first/last name |
| `office_search_name_trgm` | GIN trigram on name |

The GIN expression must match what `search_ranked` builds, weights included, or
the planner ignores it. To check after a change:

```python
qs = search_ranked(Model.objects.all(), "term", fields=(...), trigram_field="title")
sql, params = qs.query.sql_with_params()
cursor.execute("SET enable_seqscan = off")
cursor.execute("EXPLAIN " + sql, params)  # look for the index name
```

Turning `enable_seqscan` off is what makes this meaningful at small row counts:
Postgres would sequential-scan a handful of rows whatever indexes exist, so a
plan that *still* refuses the index is telling you the expression does not
match.

## Why not Elasticsearch

The specification says to use PostgreSQL at current scale and avoid external
search infrastructure without measured need, and that is the standing
decision. Two reasons beyond the corpus size:

1. **Authorization would have to move into the index.** Every provider today
   inherits its domain's scope function. An external index means either
   filtering post-hoc (slow, and wrong for counts) or copying each domain's
   rules into index-time ACLs — the drift this design exists to prevent.
2. **It is another moving part to keep in sync**, with its own backfill,
   reindex, and failure modes, for a corpus that currently fits comfortably in
   the primary database.

The provider contract is what makes this reversible. When measurements justify
it, a domain swaps *its own* `search` callable for one backed by an external
index and nothing else changes — the aggregator, the caps, the isolation, and
the payload stay as they are. Revisit when a provider's own query is the
measured bottleneck.

## Sources not yet registered

Documents, training, transactions, CRM contacts, and policies have no model
behind them. A provider over a table that does not exist would be a group
heading that never returns anything, so they register with their domains.
`test_search.py` asserts every registered provider's permission is catalogued
and its "see all" route reverses.

## The palette

The header control opens a Spotlight-style command palette
(`components/design-system/command-palette.tsx`), distinct from `Dialog`: a
dialog interrupts and is centred, titled, and closable; a palette is a place
you go, anchored near the top with no visible chrome.

* **⌘K / Ctrl-K** opens it from anywhere.
* **Selection roves, focus does not.** Arrow keys move the highlight while the
  caret stays in the input, exposed with `aria-activedescendant`, so typing
  never breaks. That is the behaviour Spotlight has trained everyone to expect.
* **Source tabs** filter to one group; ← and → move between them. The strip
  only appears with more than one source — a single tab is a label pretending
  to be a control. Filtering is client-side over what the server already
  returned, so it can only ever narrow.
* **States**: loading skeleton, below-minimum hint, no-results, rate-limited,
  and per-source failure — a response of only failed groups says so rather
  than reporting an outage as "no results".

## Related docs

- `docs/permissions.md` — the catalog every provider permission comes from
- `docs/user-directory.md` — the field groups the people provider honours
- `docs/announcements.md` — the audience predicate the news provider inherits
