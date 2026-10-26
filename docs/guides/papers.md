# Papers

Papers are self-contained HTML write-ups served by the dashboard at `/papers/<name>`. People comment on any
paragraph; an agent answers in the thread.

| Kind | One per | Audience | Created with |
|---|---|---|---|
| Goal paper | goal | public: the result, or the negative result | `arx paper new --goal <goal>` |
| Hill paper | hill | internal debugging notes, kept current while the hill is open | `arx paper new <hill>` |

## Write and publish

```bash
arx paper new count-list                         # copies the worked example to paper-count-list.html
arx paper check --file paper-count-list.html     # lint against PROTOCOL.md § Papers; goal papers add --goal <goal>
arx paper add count-list --hill count-list --file paper-count-list.html
arx paper edit count-list --file paper-count-list.html   # republish; open pages swap the new version in place
arx paper ls
```

`arx paper new` copies a worked example. It is one possible shape, not a template: structure, length, section
names and widgets are the author's choice. Only the non-negotiables in PROTOCOL.md § Papers are fixed.

`arx paper check` must report 0 errors before every publish. It checks those non-negotiables: a `data-block` id on
every `section`, `p` and `figure` (comments anchor to them), numbers that name their slice and n and sit next to a
visual, the prose budget, at least one explorable, a quiz and a Remember section, dark mode and no serif fonts; for
goal papers, the final value, the paired delta vs the starting champion and links to the hill papers.

## Comments and the agent

- In the reader, select text or click the margin to comment. A new comment, or a reply from a person, is sent to the
  agent automatically and the card shows **Sent to the agent**.
- Once the agent has answered (or the thread is resolved) the card shows **Send to agent**: it posts `@agent`,
  which hands the whole thread back, even on a resolved thread. Typing `@agent` in any message does the same.
- While the agent works on a thread the card shows **Agent is thinking**.

The agent side is a loop in the project directory:

```bash
arx paper poll [name] [--timeout S]   # blocks until someone waits on the agent; one JSON line per thread
arx paper reply <name> <thread> "text" [--link "label=#block"] [--file answer.html]
arx paper resolve <name> <thread> ["closing note"]
arx paper attach <name> --file widget.html   # serve a page next to the paper and print its URL
```

Nothing answers comments unless an agent is running `arx paper poll`; keep one running while people review.

## Safety

Papers, replies and threads live in `.research/papers/<name>/` (`paper.html`, `meta.json`, `thread.jsonl`,
`files/`). The server binds to loopback and refuses cross-origin writes. People cannot post as the agent
(`agent`, `claude`, `arx` are reserved author names) and can edit or delete only their own messages. Do not put
client text, answers or traces in a paper; paraphrase.

A paper's own scripts run on the dashboard's origin (the reader needs that to anchor comments), so publish only
papers you or your agent wrote. Attached files (`arx paper attach`, `--file` on replies) are served with
`Content-Security-Policy: sandbox`, so a widget cannot read other projects or post comments. Reviewer names are
not authenticated: anyone at the keyboard can pick any name.
