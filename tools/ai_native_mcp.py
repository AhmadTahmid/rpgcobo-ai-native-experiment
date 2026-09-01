#!/usr/bin/env python3
"""Small stdio client for RPG-Cobo's native MCP bridge.

The editor must already be running.  Mutations are rejected unless --confirm is
passed; with it, the client answers RPG-Cobo's elicitation request explicitly.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]


class MCPError(RuntimeError):
    def __init__(self, error: dict[str, Any]):
        super().__init__(error.get("message", "MCP call failed"))
        self.error = error


class RPGCoboClient:
    def __init__(self, confirm_changes: bool = False):
        self.confirm_changes = confirm_changes
        self._next_id = 0
        self._process = subprocess.Popen(
            [str(ROOT / "rpgcobo.exe"), "-mcp-stdio"],
            cwd=ROOT,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            bufsize=1,
        )
        self.request(
            "initialize",
            {
                "protocolVersion": "2025-06-18",
                "capabilities": {"elicitation": {}},
                "clientInfo": {"name": "rpgcobo-ai-native-client", "version": "0.1"},
            },
        )
        self.notify("notifications/initialized", {})

    def close(self) -> None:
        if self._process.poll() is None:
            self._process.terminate()
            try:
                self._process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                self._process.kill()

    def __enter__(self) -> "RPGCoboClient":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def _send(self, value: dict[str, Any]) -> None:
        assert self._process.stdin is not None
        self._process.stdin.write(json.dumps(value, separators=(",", ":")) + "\n")
        self._process.stdin.flush()

    def _read(self) -> dict[str, Any]:
        assert self._process.stdout is not None
        line = self._process.stdout.readline()
        if not line:
            stderr = self._process.stderr.read() if self._process.stderr else ""
            raise RuntimeError(f"RPG-Cobo MCP bridge closed unexpectedly: {stderr}")
        return json.loads(line)

    def notify(self, method: str, params: dict[str, Any]) -> None:
        self._send({"jsonrpc": "2.0", "method": method, "params": params})

    def request(self, method: str, params: dict[str, Any]) -> Any:
        self._next_id += 1
        request_id = self._next_id
        self._send({"jsonrpc": "2.0", "id": request_id, "method": method, "params": params})
        while True:
            message = self._read()
            if message.get("method") == "elicitation/create":
                accepted = self.confirm_changes
                self._send(
                    {
                        "jsonrpc": "2.0",
                        "id": message["id"],
                        "result": {
                            "action": "accept" if accepted else "decline",
                            "content": {"confirmed": accepted},
                        },
                    }
                )
                continue
            if message.get("id") != request_id:
                continue
            if "error" in message:
                raise MCPError(message["error"])
            return message.get("result")

    def tools(self) -> list[dict[str, Any]]:
        return self.request("tools/list", {})["tools"]

    def call_raw(self, name: str, arguments: dict[str, Any] | None = None) -> dict[str, Any]:
        return self.request(
            "tools/call", {"name": name, "arguments": arguments or {}}
        )

    def call(self, name: str, arguments: dict[str, Any] | None = None) -> Any:
        result = self.call_raw(name, arguments)
        content = result.get("content", [])
        if result.get("isError"):
            text = content[0].get("text", "MCP tool returned an error") if content else "MCP tool returned an error"
            raise RuntimeError(text)
        if len(content) == 1 and content[0].get("type") == "text":
            text = content[0].get("text", "")
            try:
                return json.loads(text)
            except json.JSONDecodeError:
                return text
        return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--confirm", action="store_true", help="explicitly accept mutating-tool elicitations")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("list")
    call_parser = sub.add_parser("call")
    call_parser.add_argument("tool")
    call_parser.add_argument("arguments", nargs="?", default="{}", help="JSON object")
    args = parser.parse_args()

    with RPGCoboClient(confirm_changes=args.confirm) as client:
        if args.command == "list":
            value = client.tools()
        else:
            value = client.call(args.tool, json.loads(args.arguments))
    print(json.dumps(value, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
