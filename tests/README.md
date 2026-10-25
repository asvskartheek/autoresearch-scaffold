# Tests

Standard library only (`unittest`, `subprocess`) plus `node` for the view tests.

    python3 -m unittest discover -s tests -v          # everything, about a minute
    python3 -m unittest discover -s tests -p 'test_core.py'

| File | Covers |
|---|---|
| `fixture.py` | Builds a synthetic mature ledger (invented names, seeded RNG): champion with duplicate seeding, 22 rejected, 65 historical models, 150 imported runs over a week, real evals, stalled tasks, 7 hills. |
| `test_core.py` | `champions()`, gate, promote, paired stats, frozen slices. |
| `test_server.py` | `state()`, runs and track frontiers, detail endpoints, static serving and path traversal, over a real server process. |
| `test_cli.py` | `up` / `down` / `ps`, stale records, SIGTERM, idle shutdown (takes about 30 s), `init`, `sweep`, `task`. |
| `test_views.py` | Renders every route with `render.js` against the fixture, an empty project and the demo seed. |

Tests point `HOME` at a temp directory, so `~/.arx/servers.json` is never touched, and every spawned dashboard is killed
on exit. Import `helpers` before `autoresearch` in any new test module.
