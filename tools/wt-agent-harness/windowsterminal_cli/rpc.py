"""
Shared JSON-RPC transport for the Windows Terminal external ApiServer.

Used by both the wt-api CLI (cli.py) and the gj-terminal-plus MCP server
(mcp_server.py). One line-based JSON-RPC request -> one response -> close.
"""
import json
import socket

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
