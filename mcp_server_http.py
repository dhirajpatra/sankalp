"""
mcp_server_http.py – HTTP/SSE wrapper for SANKALP MCP Server
Allows connecting via URL (e.g., from claude.ai MCP connector).

Run:
    pip install mcp uvicorn
    uvicorn mcp_server_http:app --host 0.0.0.0 --port 8080

Then connect Claude to: http://localhost:8080/sse
or expose via ngrok: ngrok http 8080
"""

import os
import sys

try:
    from mcp.server.sse import SseServerTransport
    from starlette.applications import Starlette
    from starlette.routing import Mount, Route
    from starlette.requests import Request
except ImportError:
    print("Install: pip install mcp uvicorn starlette", file=sys.stderr)
    sys.exit(1)

# Import the same app and handlers from mcp_server.py
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from mcp_server import app  # reuse the Server instance

# ── SSE transport ─────────────────────────────────────────────────────────────
sse = SseServerTransport("/messages")


async def handle_sse(request: Request):
    async with sse.connect_sse(
        request.scope, request.receive, request._send
    ) as streams:
        await app.run(
            streams[0], streams[1],
            app.create_initialization_options()
        )


async def handle_messages(request: Request):
    await sse.handle_post_message(request.scope, request.receive, request._send)


# ── Starlette app ─────────────────────────────────────────────────────────────
starlette_app = Starlette(
    routes=[
        Route("/sse",      endpoint=handle_sse),
        Mount("/messages", app=handle_messages),
    ]
)

# Alias for uvicorn
app_http = starlette_app

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("MCP_PORT", 8080))
    print(f"\n🛡️  SANKALP MCP Server (HTTP/SSE)")
    print(f"   Endpoint: http://localhost:{port}/sse")
    print(f"   Connect Claude to this URL as an MCP server\n")
    uvicorn.run(starlette_app, host="0.0.0.0", port=port)
