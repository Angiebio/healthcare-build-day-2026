# Lantern docs

| Doc | What it is |
|---|---|
| [ARCHITECTURE.md](ARCHITECTURE.md) | The system: the data finding that shaped it, the trust-boundary diagram, privacy tiers, scope cutline, and the clock we built against |
| [API-CONTRACT.md](API-CONTRACT.md) | The frozen API contract. Frozen early so every lane could build in parallel without waiting on each other |
| [process/design-decisions.md](process/design-decisions.md) | What we cut and why — the ideas that didn't survive contact with the actual corpus, with the measurements that killed them |
| [process/ticket-algorithms.md](process/ticket-algorithms.md) | The algorithm-core spec (measurement extraction, query AST, rank fusion, disclosure guard) |
| [process/ticket-lanes.md](process/ticket-lanes.md) | How six agents and two humans built in parallel without collisions |

## How this was built

Lantern was built in a five-hour window by a cooperative of humans and AI agents working parallel
lanes against a contract frozen in the first thirty minutes. The `process/` docs are the actual
working tickets, published as-is.

Two habits did most of the work, and both are visible in the code:

**Profile the data before designing anything.** The first thing we did was measure the corpus rather
than assume its shape. That is where the 78.4%-of-reports-carry-measurements finding came from, and it
overturned our own pre-event architecture — which had assumed pixel data that does not exist in this
dataset. `process/design-decisions.md` is the record of that reversal.

**Deterministic where it must be correct.** Everything that decides what gets released is a plain,
tested function in `scripts/`. Natural-language input is *validated*, not interpreted, and no model
participates in deciding what is disclosed.
