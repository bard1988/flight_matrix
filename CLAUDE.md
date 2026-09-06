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

flight_matrix / **SkyMatrix** — a multi-destination fare board that renders a
departure × return date grid. Full design, data sources (Kiwi.com board, Travelpayouts /
Aviasales fill, per-cell Google Flights verification), rate-limit mitigations, and
deployment constraints are documented in `README.md`.
