# windowsterminal-cli — CLI-Anything harness

External control CLI for **a forked Windows Terminal** with an embedded `ApiServer`
(`src/cascadia/TerminalApp/ApiServer.{h,cpp}`).

Stock Microsoft Store / GitHub Releases Windows Terminal has **no** external
control API; this harness only works against the in-tree build of
`microsoft/terminal` patched with `ApiServer`.

## Protocol

- TCP, line-based JSON-RPC (one `{...}\n` request -> one `{...}\n` response, then close)
- Default endpoint: `127.0.0.1:9551`
- Methods:
  - `send_text { text: str }` -> `{ result: "ok" }`
  - `get_buffer { lines: int }` -> `{ result: { lines: [str, ...], total_rows: int } }`
  - `set_font_size { size: float }` -> `{ result: "ok" }`

## Install

```bash
pip install -e tools/wt-agent-harness
```

## Subcommands

| Command | Purpose |
|---|---|
| `wt-api send-text TEXT [--newline]` | Inject text as keystrokes (works on inactive window). |
| `wt-api get-buffer [-n N]`          | Latest N lines from active TermControl buffer. |
| `wt-api set-font-size SIZE`         | Set font size (float). |
| `wt-api ping`                       | Probe ApiServer reachability. |

`--json` on any subcommand emits raw JSON-RPC response.
