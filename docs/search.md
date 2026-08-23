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
