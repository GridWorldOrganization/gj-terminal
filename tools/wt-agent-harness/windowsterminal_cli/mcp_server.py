"""
gj-terminal-plus — MCP server for the Windows Terminal external control API.

Exposes the embedded ApiServer (TCP line-based JSON-RPC on 127.0.0.1:9551) as
MCP tools so an MCP client (Claude Code, etc.) can drive a forked Windows
Terminal directly — no shell, no CLI subprocess. Driving via MCP avoids the
shell-escaping pitfalls of going through Bash/PowerShell (e.g. MSYS2 path
mangling that turns "/goal ..." into "C:/Program Files/Git/goal ..."), because
arguments go straight to the socket as JSON.

Transport: stdio. Run as:  python -m windowsterminal_cli.mcp_server
(or the `wt-mcp` console entry point).

Every tool accepts optional `tab` (index, -1 = active), `tab_name` (target by
title; overrides tab when non-empty) and `port` (default 9551; one window per
port — use list_windows to discover them). Tools return the raw JSON-RPC
result object (or {"error": ...} on failure).
"""
from typing import Any, Optional

from mcp.server.fastmcp import FastMCP

from .rpc import rpc, resolve_port_for_tab, DEFAULT_HOST, DEFAULT_PORT

mcp = FastMCP("gj-terminal-plus")


def _call(method: str, params: dict, tab: int, tab_name: str, port: int) -> Any:
    """Inject tab targeting + dispatch one RPC, returning result or error dict."""
    if tab_name and port == DEFAULT_PORT:
        port = resolve_port_for_tab(tab_name)
    p = dict(params)
    if "tab" not in p:
        p["tab"] = tab
    if tab_name and "tab_name" not in p:
        p["tab_name"] = tab_name
    try:
        resp = rpc(method, p, port=port)
    except Exception as e:  # socket / decode errors -> structured error
        return {"error": f"rpc failed ({method}): {e}"}
    if "error" in resp:
        return {"error": resp["error"]}
    return resp.get("result")


# ---------------------------------------------------------------- input / read

@mcp.tool()
def send_text(text: str, newline: bool = False, tab: int = -1,
              tab_name: str = "", port: int = DEFAULT_PORT) -> Any:
    """Inject TEXT as keystrokes into a Windows Terminal window.

    Works even when the window is inactive / unfocused / in the background.
    Set newline=True to append a carriage return (submit the current line).
    """
    # text と \r を別 RPC で送る。同一バッチ末尾の \r は readline が Enter と
    # 認識しないため、必ず分離して送信する (Windows Terminal SendInput の制約)。
    if text:
        _call("send_text", {"text": text}, tab, tab_name, port)
    return _call("send_text", {"text": "\r"}, tab, tab_name, port)


@mcp.tool()
def get_buffer(lines: int = 50, tab: int = -1, tab_name: str = "",
               port: int = DEFAULT_PORT) -> Any:
    """Return the latest N lines from the terminal scrollback buffer (latest last)."""
    return _call("get_buffer", {"lines": lines}, tab, tab_name, port)


@mcp.tool()
def get_viewport(tab: int = -1, tab_name: str = "",
                 port: int = DEFAULT_PORT) -> Any:
    """Return the currently visible viewport lines (what the user sees on screen now)."""
    return _call("get_viewport", {}, tab, tab_name, port)


@mcp.tool()
def get_selection(trim: bool = True, tab: int = -1, tab_name: str = "",
                  port: int = DEFAULT_PORT) -> Any:
    """Return the currently highlighted/selected text (read-only). trim strips trailing whitespace."""
    return _call("get_selection", {"trim": trim}, tab, tab_name, port)


@mcp.tool()
def get_scroll_state(tab: int = -1, tab_name: str = "",
                     port: int = DEFAULT_PORT) -> Any:
    """Return scroll position: scroll_offset, view_height, buffer_height, at_bottom, scrolled_back_rows."""
    return _call("get_scroll_state", {}, tab, tab_name, port)


# ----------------------------------------------------------------------- font

@mcp.tool()
def get_font_size(tab: int = -1, tab_name: str = "",
                  port: int = DEFAULT_PORT) -> Any:
    """Return the current font size (float) of the target terminal control."""
    return _call("get_font_size", {}, tab, tab_name, port)


@mcp.tool()
def set_font_size(size: float, tab: int = -1, tab_name: str = "",
                  port: int = DEFAULT_PORT) -> Any:
    """Set the font size (float, e.g. 14.0) of the target terminal control."""
    return _call("set_font_size", {"size": size}, tab, tab_name, port)


# ------------------------------------------------------------------------ tabs

_SCAN_ALL = 0  # sentinel: port=0 → scan all running ApiServers


@mcp.tool()
def list_tabs(port: int = _SCAN_ALL) -> Any:
    """List tabs across ALL windows (port=0, default) or a single window (port=N).

    Multi-window (port=0): scans [DEFAULT_PORT, DEFAULT_PORT+16), returns
      {"tabs": [{"port": int, "index": int, "title": str}, ...]}
    Each entry carries its port so callers know which window to target.

    Single-window (port=N): original single-window query, returns
      {"count": int, "tabs": [{"index": int, "title": str}]}
    """
    if port == _SCAN_ALL:
        result = list_windows()
        flat = []
        for w in result.get("windows", []):
            for i, title in enumerate(w.get("tab_titles", [])):
                flat.append({"port": w["port"], "index": i, "title": title})
        return {"tabs": flat}
    return _call("list_tabs", {}, -1, "", port)


@mcp.tool()
def new_tab(port: int = DEFAULT_PORT) -> Any:
    """Open a new tab with the default profile."""
    return _call("new_tab", {}, -1, "", port)


@mcp.tool()
def close_tab(index: int, port: int = DEFAULT_PORT) -> Any:
    """Close the tab at INDEX (0-based)."""
    return _call("close_tab", {"tab": index}, index, "", port)


@mcp.tool()
def rename_tab(title: str, tab: int = -1, tab_name: str = "",
               port: int = DEFAULT_PORT) -> Any:
    """Rename the target tab (by tab index or tab_name) to TITLE."""
    return _call("rename_tab", {"title": title}, tab, tab_name, port)


@mcp.tool()
def get_tab_color(tab: int = -1, tab_name: str = "",
                  port: int = DEFAULT_PORT) -> Any:
    """Return the tint color of the target tab: {has_color, color} (color is #rrggbb)."""
    return _call("get_tab_color", {}, tab, tab_name, port)


@mcp.tool()
def set_bar_color(color: str, tab: int = -1, tab_name: str = "",
                  port: int = DEFAULT_PORT) -> Any:
    """Set the tab/title-bar background color. Accepts #RRGGBB, #AARRGGBB, or RRGGBB."""
    return _call("set_bar_color", {"color": color}, tab, tab_name, port)


# ---------------------------------------------------------------------- window

@mcp.tool()
def focus_tab(tab: int = -1, tab_name: str = "", port: int = DEFAULT_PORT) -> Any:
    """Switch the active tab to TAB (index) or TAB_NAME.

    Only switches tab selection — does not raise the window to foreground.
    Call focus_window() after this if you need the window visible.
    """
    return _call("focus_tab", {}, tab, tab_name, port)


@mcp.tool()
def focus_window(port: int = DEFAULT_PORT) -> Any:
    """Bring the gj-terminal window to the foreground (raise + activate).

    Uses the internal SummonWindow path (AttachThreadInput, virtual-desktop aware).
    Combine with focus_tab() to switch tab AND raise the window in one sequence.
    """
    return _call("focus_window", {}, -1, "", port)


@mcp.tool()
def window_action(action: str, port: int = DEFAULT_PORT) -> Any:
    """Apply a window action: one of "maximize", "minimize", "restore", "normal"."""
    return _call("window_action", {"action": action}, -1, "", port)


@mcp.tool()
def get_window_rect(port: int = DEFAULT_PORT) -> Any:
    """Return window geometry: {x, y, width, height, maximized, minimized}."""
    return _call("get_window_rect", {}, -1, "", port)


@mcp.tool()
def set_window_rect(x: Optional[int] = None, y: Optional[int] = None,
                    width: Optional[int] = None, height: Optional[int] = None,
                    port: int = DEFAULT_PORT) -> Any:
    """Move/resize the window. Any omitted field keeps its current value."""
    params: dict = {}
    if x is not None:
        params["x"] = x
    if y is not None:
        params["y"] = y
    if width is not None:
        params["width"] = width
    if height is not None:
        params["height"] = height
    return _call("set_window_rect", params, -1, "", port)


# ------------------------------------------------------------ discovery / probe

@mcp.tool()
def list_windows(start: int = DEFAULT_PORT, count: int = 16,
                 host: str = DEFAULT_HOST) -> Any:
    """Scan ports [start, start+count) for running ApiServers (one window per port).

    Returns {windows: [{port, tab_count, tab_titles}]}.
    """
    import json as _json
    import socket as _socket
    found = []
    for p in range(start, start + count):
        try:
            s = _socket.create_connection((host, p), timeout=0.3)
            s.sendall(b'{"id":1,"method":"list_tabs","params":{}}\n')
            s.shutdown(_socket.SHUT_WR)
            buf = b""
            while True:
                c = s.recv(65536)
                if not c:
                    break
                buf += c
            s.close()
            d = _json.loads(buf.decode("utf-8", "replace").strip())
            r = d.get("result", {})
            tabs = r.get("tabs", [])
            found.append({
                "port": p,
                "tab_count": len(tabs),
                "tab_titles": [t["title"] for t in tabs],
            })
        except Exception:
            pass
    return {"windows": found}


@mcp.tool()
def ping(port: int = DEFAULT_PORT, host: str = DEFAULT_HOST) -> Any:
    """Probe ApiServer reachability on host:port. Returns {ok: bool, detail: ...}."""
    try:
        resp = rpc("__ping__", {}, host=host, port=port)
        return {"ok": True, "detail": resp.get("result", resp)}
    except Exception as e:
        return {"ok": False, "detail": f"unreachable: {e}"}


def main() -> None:
    """Console entry point: run the MCP server over stdio."""
    mcp.run()


if __name__ == "__main__":
    main()
