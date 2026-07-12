"""Thin MCP client: short-lived sessions per call over stdio or streamable HTTP.

Failures are returned as strings so a broken server never crashes a chat turn.
"""
import asyncio
import json


async def _with_session(server: dict, fn):
    from mcp import ClientSession

    transport = server.get("transport", "stdio")
    if transport == "stdio":
        from mcp import StdioServerParameters
        from mcp.client.stdio import stdio_client

        args = json.loads(server.get("args_json") or "[]")
        params = StdioServerParameters(command=server["command"], args=args)
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                return await fn(session)
    else:
        from mcp.client.streamable_http import streamablehttp_client

        async with streamablehttp_client(server["url"]) as (read, write, _):
            async with ClientSession(read, write) as session:
                await session.initialize()
                return await fn(session)


def list_tools_sync(server: dict) -> list[dict]:
    async def go(session):
        result = await session.list_tools()
        return [{"name": t.name, "description": t.description or "",
                 "inputSchema": t.inputSchema or {"type": "object"}}
                for t in result.tools]

    return asyncio.run(_with_session(server, go))


def call_tool_sync(server: dict, name: str, args: dict) -> str:
    async def go(session):
        result = await session.call_tool(name, args)
        parts = []
        for block in result.content:
            if getattr(block, "type", "") == "text":
                parts.append(block.text)
            else:
                parts.append(str(block))
        return "\n".join(parts)

    try:
        return asyncio.run(_with_session(server, go))
    except Exception as e:  # noqa: BLE001
        return f"MCP tool error: {e}"
