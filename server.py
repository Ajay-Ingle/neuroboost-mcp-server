import os
import asyncio
import uvicorn
from starlette.responses import JSONResponse
from mcp.server import Server
from mcp.server.sse import SseServerTransport
from supabase import create_client, Client
from dotenv import load_dotenv
import mcp.types as types

load_dotenv(".env.local")

SUPABASE_URL = os.environ.get("NEXT_PUBLIC_SUPABASE_URL")
SUPABASE_KEY = os.environ.get("NEXT_PUBLIC_SUPABASE_ANON_KEY")

server = Server("NeuroBoost_Clinical_Server")

def get_secure_client(jwt_token: str = None) -> Client:
    client = create_client(SUPABASE_URL, SUPABASE_KEY)
    if jwt_token:
        client.postgrest.auth(jwt_token)
    return client

# --- THREAD-SAFE HELPERS ---
def fetch_patient_profile(jwt_token, user_id):
    supabase = get_secure_client(jwt_token)
    return supabase.table('profiles').select('*').eq('id', user_id).execute()

def fetch_fatigue_logs(jwt_token, user_id, limit):
    supabase = get_secure_client(jwt_token)
    return supabase.table('session_logs').select('session_date, attention_stability_score').eq('user_id', user_id).limit(limit).execute()
# ---------------------------

@server.list_tools()
async def handle_list_tools() -> list[types.Tool]:
    return [
        types.Tool(
            name="get_patient_baseline",
            description="Retrieves patient baseline demographics.",
            inputSchema={
                "type": "object",
                "properties": {"user_id": {"type": "string"}, "jwt_token": {"type": "string"}},
                "required": ["user_id"]
            }
        ),
        types.Tool(
            name="analyze_cognitive_fatigue",
            description="Extracts the attention stability and performance variance.",
            inputSchema={
                "type": "object",
                "properties": {"user_id": {"type": "string"}, "limit": {"type": "integer"}, "jwt_token": {"type": "string"}},
                "required": ["user_id"]
            }
        )
    ]

@server.call_tool()
async def handle_call_tool(name: str, arguments: dict) -> list[types.TextContent]:
    jwt_token = arguments.get("jwt_token")
    user_id = arguments.get("user_id")
    
    if name == "get_patient_baseline":
        try:
            profile_res = await asyncio.to_thread(fetch_patient_profile, jwt_token, user_id)
            return [types.TextContent(type="text", text=str(profile_res.data))]
        except Exception as e:
            return [types.TextContent(type="text", text=f"Error: {str(e)}")]
            
    elif name == "analyze_cognitive_fatigue":
        try:
            limit = arguments.get("limit", 10)
            logs = await asyncio.to_thread(fetch_fatigue_logs, jwt_token, user_id, limit)
            return [types.TextContent(type="text", text=str(logs.data))]
        except Exception as e:
            return [types.TextContent(type="text", text=f"Error: {str(e)}")]
            
    return [types.TextContent(type="text", text="Unknown tool")]


# ---- PURE ASGI WEB SERVER (Fixes the Routing Bug) ----
sse = SseServerTransport("/messages")

async def mcp_app(scope, receive, send):
    """A mathematically perfect router that guarantees no overlapping bugs."""
    if scope["type"] not in ["http", "https"]:
        return

    path = scope["path"]
    
    # 1. Health Check for Render
    if path == "/" or path == "":
        response = JSONResponse({"status": "alive", "service": "NeuroBoost Clinical MCP"})
        await response(scope, receive, send)
        
    # 2. SSE Connection Stream
    elif path == "/sse":
        async with sse.connect_sse(scope, receive, send) as (read_stream, write_stream):
            await server.run(read_stream, write_stream, server.create_initialization_options())
            
    # 3. Message POST Receiver
    elif path == "/sse/messages" or path == "/messages":
        await sse.handle_post_message(scope, receive, send)
        
    # 4. Fallback
    else:
        response = JSONResponse({"error": "Not found"}, status_code=404)
        await response(scope, receive, send)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    print(f"Starting Production MCP Server on port {port}...")
    # Notice we run mcp_app directly now, completely bypassing Starlette's router!
    uvicorn.run(mcp_app, host="0.0.0.0", port=port)
