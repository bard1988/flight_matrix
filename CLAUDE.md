# CLAUDE.md

## Repo knowledge graph (use this first)

This repo ships a prebuilt graphify knowledge graph of its documentation in `graphify-out/`.
Before answering architecture / "how does X work" / "what connects Y to Z" questions:

- Read `graphify-out/GRAPH_REPORT.md` for orientation — god nodes, communities, and
  cross-cutting connections.
- For a specific question, run `/graphify query "<question>"` (or `graphify query "<question>"`).
  It traverses `graphify-out/graph.json` instead of re-reading the whole corpus.
- `graphify-out/graph.html` is the interactive view for a human.

Rebuild after substantial `README.md` edits: `/graphify . --update`, then commit the
refreshed `graphify-out/`. The `cache/` and `manifest.json` make an unchanged rebuild free.

## Project

flight_matrix / **FlightMatrix** — a multi-destination fare board that renders a
departure × return date grid. Full design, data sources (Kiwi.com board, Travelpayouts /
Aviasales fill, per-cell Google Flights verification), rate-limit mitigations, and
deployment constraints are documented in `README.md`.

## Every bug fix ships with a test

When a reported bug is fixed, add a test that reproduces it and fails without the fix
(check this by applying the test against the pre-fix code, e.g. `git stash`/checkout the
prior revision, before trusting it). This applies to backend (`pytest`) and frontend
(Playwright, skipped gracefully without the dev extras) fixes alike. A fix without a
regression test is not done.
