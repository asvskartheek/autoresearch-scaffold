# The dashboard lifecycle

One dashboard server per project. It reads `.research/` and nothing else, so it can be stopped and started at will;
no work is lost.

## Commands

```bash
arx up              # start this project's dashboard if it is not running; print the URL
arx up --restart    # stop it and start it again on the same port
arx ps              # every running dashboard, with its pid and project folder
arx down            # stop this project's dashboard
arx down --all      # stop every project's
```

`arx up` is idempotent. It looks for a running server whose project folder is this one and whose `/api/ping`
answers with that folder; if it finds one it prints the URL and exits (`--port` is ignored). Otherwise it starts
`arx serve` detached (own session, log in `.research/server.log`) on the first free port from `--port` (default
8890) upward.

## Where a server is recorded

| File | Holds |
|---|---|
| `.research/server.json` | `{root, port, pid, started}` of this project's server |
| `~/.arx/servers.json` | the same record for every project on the machine; `arx ps` and `arx down --all` read it |

A server writes both when it starts and removes them when it stops. Records whose process is gone are dropped the
next time anything reads the index.

## Identity

`GET /api/ping` returns `{root, name, pid}`. `arx up` trusts a port only if `root` is this project's folder. The
browser tab is titled `<project name> · Observatory`.

## Idle shutdown

A server that nobody has requested a page from for `dashboard_idle_minutes` (default 30, in `research.json`) stops
itself, unless a task is `running` or `stalled`. An open dashboard tab polls every few seconds, so a tab left open
keeps it alive. `0` disables the shutdown. The server checks every 15 seconds.

The ledger is unaffected; `arx up` brings the dashboard back, usually on the same port.

## Session hooks

`arx init` writes `.claude/settings.json` so the dashboard follows the agent session:

```json
{
  "hooks": {
    "SessionStart": [{ "hooks": [{ "type": "command", "command": "arx up" }] }],
    "SessionEnd": [{ "hooks": [{ "type": "command", "command": "arx down" }] }]
  }
}
```

- The file is written only if it does not exist. In a project that already has a `.claude/settings.json`, add the
  two hooks by hand.
- The hooks run `arx`, so it must be on `PATH` for the session.
- `SessionEnd` stops the dashboard even if another session is using it; that session's next `arx up` restarts it.

## A port shows another project

Ports are handed out upward from 8890, so a port that served project A yesterday can serve project B today (A
idled out, B started and took the number). An old bookmark then shows the wrong project.

1. Check the tab title, or `curl http://127.0.0.1:PORT/api/ping`, for the project name and folder.
2. `arx ps` lists each project with its port. Run `arx up` inside the project to get its URL.
3. Never give a user a port you have not checked against `arx up` or `arx ps`.

## Pointing a project at a newer ARX

`arx init` copies the `autoresearch/` package into the project ("vendors" it) so `import autoresearch` works in the
project's own Python. That copy shadows an installed `autoresearch` for any script run from the project folder, so
upgrading ARX does not change what those scripts import.

`arx up` does not have this problem: it launches the dashboard from the package of the `arx` that ran it, never
the vendored copy. After an upgrade the dashboard shows the new UI while Python in the project still runs the old
core, until:

```bash
arx sync     # replace ./autoresearch/ with the installed one and restart the dashboard
```

- Run it with the installed `arx`. `python -m autoresearch sync` from inside the project fails with "this is the
  vendored copy itself".
- `sync` updates only `autoresearch/`. `AGENTS.md`, `PROTOCOL.md`, `research.json` and `.claude/settings.json` are
  never overwritten; diff them against the templates in the installed package (`autoresearch/templates/`) and merge
  by hand.
- It restarts the dashboard on its previous port, or starts it if it was not running.
