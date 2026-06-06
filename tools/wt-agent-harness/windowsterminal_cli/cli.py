"""
wt-api: CLI-Anything compatible CLI for Windows Terminal external control.

Connects to the ApiServer embedded in a forked WindowsTerminal.exe
(127.0.0.1:9551, line-based JSON-RPC).

Subcommands:
  send-text TEXT           Inject text as if typed (window may be inactive).
  get-buffer [-n N]        Return latest N lines from active TermControl buffer.
  set-font-size SIZE       Set font size (float) of active TermControl.
"""
import json
import socket
import sys
import click

# Force UTF-8 output so block-drawing / CJK chars from get-buffer never crash
# on cp932 / cp1252 default consoles. errors='replace' substitutes U+FFFD
# for any chars the active code page actually can't render.
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        try:
            _stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 9551
DEFAULT_TIMEOUT = 5.0


def rpc(method: str, params: dict, host: str = DEFAULT_HOST,
        port: int = DEFAULT_PORT, timeout: float = DEFAULT_TIMEOUT) -> dict:
    """Send one JSON-RPC line, read one JSON-RPC line back, close."""
    s = socket.create_connection((host, port), timeout=timeout)
    try:
        req = (json.dumps({"id": 1, "method": method, "params": params},
                          ensure_ascii=False) + "\n").encode("utf-8")
        s.sendall(req)
        s.shutdown(socket.SHUT_WR)
        buf = b""
        while True:
            chunk = s.recv(65536)
            if not chunk:
                break
            buf += chunk
            if b"\n" in buf:
                break
    finally:
        s.close()
    line = buf.decode("utf-8", errors="replace").strip()
    return json.loads(line)


def _emit(obj, json_out: bool):
    if json_out:
        click.echo(json.dumps(obj, ensure_ascii=False, indent=2))
    else:
        if isinstance(obj, dict) and "error" in obj:
            click.echo(f"error: {obj['error']}", err=True)
            sys.exit(1)
        if isinstance(obj, dict) and "result" in obj:
            r = obj["result"]
            if isinstance(r, dict) and "lines" in r:
                for line in r["lines"]:
                    click.echo(line)
            else:
                click.echo(str(r))
        else:
            click.echo(json.dumps(obj, ensure_ascii=False))


@click.group()
@click.option("--host", default=DEFAULT_HOST, show_default=True,
              help="ApiServer host (default 127.0.0.1).")
@click.option("--port", default=DEFAULT_PORT, show_default=True, type=int,
              help="ApiServer port (default 9551).")
@click.option("--json", "json_out", is_flag=True,
              help="Emit raw JSON instead of human-readable.")
@click.option("--tab", default=-1, type=int,
              help="Target tab index (default: -1 = active tab).")
@click.option("--tab-name", default="", type=str,
              help="Target tab by title (overrides --tab if non-empty).")
@click.pass_context
def main(ctx, host, port, json_out, tab, tab_name):
    """CLI-Anything harness for Windows Terminal external API."""
    ctx.ensure_object(dict)
    ctx.obj["host"] = host
    ctx.obj["port"] = port
    ctx.obj["json"] = json_out
    ctx.obj["tab"] = tab
    ctx.obj["tab_name"] = tab_name


def _rpc(ctx, method, params=None):
    """Wrapper that auto-injects target tab index AND optional tab_name."""
    p = dict(params or {})
    if "tab" not in p:
        p["tab"] = ctx.obj.get("tab", -1)
    name = ctx.obj.get("tab_name", "")
    if name and "tab_name" not in p:
        p["tab_name"] = name
    return rpc(method, p, ctx.obj["host"], ctx.obj["port"])


@main.command("send-text")
@click.argument("text")
@click.option("--newline/--no-newline", default=False,
              help="Append \\r at end (submit current line).")
@click.pass_context
def cmd_send_text(ctx, text, newline):
    """Inject TEXT as keyboard input (works when window is inactive)."""
    if newline:
        text = text + "\r"
    resp = _rpc(ctx, "send_text", {"text": text})
    _emit(resp, ctx.obj["json"])


@main.command("get-buffer")
@click.option("--lines", "-n", default=50, show_default=True, type=int,
              help="Number of latest lines to return.")
@click.pass_context
def cmd_get_buffer(ctx, lines):
    """Return latest N lines from active TermControl buffer."""
    resp = _rpc(ctx, "get_buffer", {"lines": lines})
    _emit(resp, ctx.obj["json"])


@main.command("get-font-size")
@click.pass_context
def cmd_get_font_size(ctx):
    """Return current font size (float) of active TermControl."""
    resp = _rpc(ctx, "get_font_size", {})
    _emit(resp, ctx.obj["json"])


@main.command("set-font-size")
@click.argument("size", type=float)
@click.pass_context
def cmd_set_font_size(ctx, size):
    """Set font size (float, e.g. 14.0) of active TermControl."""
    resp = _rpc(ctx, "set_font_size", {"size": size})
    _emit(resp, ctx.obj["json"])


@main.command("get-selection")
@click.option("--no-trim", is_flag=True,
              help="Do NOT trim trailing whitespace (default: trim).")
@click.pass_context
def cmd_get_selection(ctx, no_trim):
    """Return currently-selected (highlighted) text from the active TermControl.

    Selection is read-only; no copy operation is performed.
    Exits with status 0 even if nothing is selected (text=='').
    """
    resp = _rpc(ctx, "get_selection", {"trim": not no_trim})
    if ctx.obj["json"]:
        click.echo(json.dumps(resp, ensure_ascii=False, indent=2))
        return
    if "error" in resp:
        click.echo(f"error: {resp['error']}", err=True)
        sys.exit(1)
    r = resp["result"]
    if not r["has_selection"]:
        click.echo("(no selection)", err=True)
        return
    click.echo(r["text"], nl=False)


@main.command("scroll-state")
@click.pass_context
def cmd_scroll_state(ctx):
    """Show current scroll position (atBottom / scrolledBackRows / etc.)."""
    resp = _rpc(ctx, "get_scroll_state", {})
    if ctx.obj["json"]:
        click.echo(json.dumps(resp, ensure_ascii=False, indent=2))
        return
    if "error" in resp:
        click.echo(f"error: {resp['error']}", err=True)
        sys.exit(1)
    r = resp["result"]
    click.echo(f"scroll_offset      = {r['scroll_offset']}")
    click.echo(f"view_height        = {r['view_height']}")
    click.echo(f"buffer_height      = {r['buffer_height']}")
    click.echo(f"at_bottom          = {r['at_bottom']}")
    click.echo(f"scrolled_back_rows = {r['scrolled_back_rows']}")


@main.command("get-viewport")
@click.pass_context
def cmd_get_viewport(ctx):
    """Return currently visible viewport lines (= what user sees on screen now)."""
    resp = _rpc(ctx, "get_viewport", {})
    if ctx.obj["json"]:
        click.echo(json.dumps(resp, ensure_ascii=False, indent=2))
        return
    if "error" in resp:
        click.echo(f"error: {resp['error']}", err=True)
        sys.exit(1)
    for line in resp["result"]["lines"]:
        click.echo(line)


@main.command("set-bar-color")
@click.argument("color")
@click.pass_context
def cmd_set_bar_color(ctx, color):
    """Set tab/title-bar background color. Accepts #RRGGBB, #AARRGGBB, RRGGBB."""
    resp = _rpc(ctx, "set_bar_color", {"color": color})
    _emit(resp, ctx.obj["json"])


@main.command("list-tabs")
@click.pass_context
def cmd_list_tabs(ctx):
    """List all open tabs (index + title)."""
    resp = _rpc(ctx, "list_tabs", {})
    if ctx.obj["json"]:
        click.echo(json.dumps(resp, ensure_ascii=False, indent=2))
        return
    if "error" in resp:
        click.echo(f"error: {resp['error']}", err=True)
        sys.exit(1)
    r = resp["result"]
    click.echo(f"count = {r['count']}")
    for t in r["tabs"]:
        click.echo(f"  [{t['index']}] {t['title']}")


@main.command("new-tab")
@click.pass_context
def cmd_new_tab(ctx):
    """Open a new tab with the default profile."""
    resp = _rpc(ctx, "new_tab", {})
    _emit(resp, ctx.obj["json"])


@main.command("close-tab")
@click.argument("index", type=int)
@click.pass_context
def cmd_close_tab(ctx, index):
    """Close tab at INDEX (0-based)."""
    resp = rpc("close_tab", {"tab": index}, ctx.obj["host"], ctx.obj["port"])
    _emit(resp, ctx.obj["json"])


@main.command("window-action")
@click.argument("action",
                type=click.Choice(["maximize", "minimize", "restore", "normal"]))
@click.pass_context
def cmd_window_action(ctx, action):
    """Maximize / minimize / restore / normal the hosting window."""
    resp = rpc("window_action", {"action": action},
               ctx.obj["host"], ctx.obj["port"])
    _emit(resp, ctx.obj["json"])


@main.command("window-rect")
@click.pass_context
def cmd_window_rect(ctx):
    """Get current window position + size (and maximized/minimized state)."""
    resp = rpc("get_window_rect", {}, ctx.obj["host"], ctx.obj["port"])
    if ctx.obj["json"]:
        click.echo(json.dumps(resp, ensure_ascii=False, indent=2))
        return
    if "error" in resp:
        click.echo(f"error: {resp['error']}", err=True)
        sys.exit(1)
    r = resp["result"]
    click.echo(f"x         = {r['x']}")
    click.echo(f"y         = {r['y']}")
    click.echo(f"width     = {r['width']}")
    click.echo(f"height    = {r['height']}")
    click.echo(f"maximized = {r['maximized']}")
    click.echo(f"minimized = {r['minimized']}")


@main.command("window-set")
@click.option("--x", type=int, default=None, help="New X (px). Omit to keep.")
@click.option("--y", type=int, default=None, help="New Y (px). Omit to keep.")
@click.option("--width", type=int, default=None, help="New width (px). Omit to keep.")
@click.option("--height", type=int, default=None, help="New height (px). Omit to keep.")
@click.pass_context
def cmd_window_set(ctx, x, y, width, height):
    """Move/resize the hosting window. Any omitted field keeps its current value."""
    params = {}
    if x is not None: params["x"] = x
    if y is not None: params["y"] = y
    if width is not None: params["width"] = width
    if height is not None: params["height"] = height
    resp = rpc("set_window_rect", params, ctx.obj["host"], ctx.obj["port"])
    _emit(resp, ctx.obj["json"])


@main.command("get-bar-color")
@click.pass_context
def cmd_get_bar_color(ctx):
    """Get tint color of target tab (use --tab N or --tab-name X). Returns hex or empty."""
    resp = _rpc(ctx, "get_tab_color", {})
    if ctx.obj["json"]:
        click.echo(json.dumps(resp, ensure_ascii=False, indent=2))
        return
    if "error" in resp:
        click.echo(f"error: {resp['error']}", err=True)
        sys.exit(1)
    r = resp["result"]
    if not r.get("has_color"):
        click.echo("(no color set)", err=True)
        return
    click.echo(r["color"])


@main.command("rename-tab")
@click.argument("title")
@click.pass_context
def cmd_rename_tab(ctx, title):
    """Rename target tab (--tab N or --tab-name X) to TITLE."""
    resp = _rpc(ctx, "rename_tab", {"title": title})
    _emit(resp, ctx.obj["json"])


@main.command("list-windows")
@click.option("--start", default=9551, type=int, show_default=True,
              help="Starting port for scan.")
@click.option("--count", default=16, type=int, show_default=True,
              help="Number of ports to scan.")
@click.pass_context
def cmd_list_windows(ctx, start, count):
    """Scan ports for running WindowsTerminalDev ApiServers (each window = 1 port)."""
    found = []
    for p in range(start, start + count):
        try:
            s = socket.create_connection((ctx.obj["host"], p), timeout=0.3)
            s.sendall(b'{"id":1,"method":"list_tabs","params":{}}\n')
            s.shutdown(socket.SHUT_WR)
            buf = b''
            while True:
                c = s.recv(65536)
                if not c:
                    break
                buf += c
            s.close()
            d = json.loads(buf.decode('utf-8', 'replace').strip())
            r = d.get('result', {})
            tabs = r.get('tabs', [])
            found.append({
                'port': p,
                'tab_count': len(tabs),
                'tab_titles': [t['title'] for t in tabs],
            })
        except Exception:
            pass
    if ctx.obj["json"]:
        click.echo(json.dumps({'windows': found}, ensure_ascii=False, indent=2))
        return
    if not found:
        click.echo(f"(no WindowsTerminalDev ApiServer found on ports {start}-{start+count-1})",
                   err=True)
        sys.exit(1)
    click.echo(f"found {len(found)} window(s):")
    for w in found:
        titles = ", ".join(w['tab_titles']) or '(none)'
        click.echo(f"  port={w['port']:>5}  tabs={w['tab_count']}  [{titles}]")


@main.command("ping")
@click.pass_context
def cmd_ping(ctx):
    """Probe ApiServer reachability."""
    try:
        resp = rpc("__ping__", {}, ctx.obj["host"], ctx.obj["port"])
        _emit(resp, ctx.obj["json"])
    except Exception as e:
        click.echo(f"unreachable: {e}", err=True)
        sys.exit(2)


if __name__ == "__main__":
    main(obj={})
