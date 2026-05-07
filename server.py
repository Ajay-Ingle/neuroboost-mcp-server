import os
import uvicorn
from starlette.applications import Starlette
from starlette.routing import Route, Mount
from starlette.responses import JSONResponse
from mcp.server import Server
from mcp.server.sse import SseServerTransport
from supabase import create_client, Client
from dotenv import load_dotenv
import mcp.types as types

# Load env variables (for local testing)
load_dotenv(".env.local")

SUPABASE_URL = os.environ.get("NEXT_PUBLIC_SUPABASE_URL")
SUPABASE_KEY = os.environ.get("NEXT_PUBLIC_SUPABASE_ANON_KEY")

# Standard Official MCP Server
server = Server("NeuroBoost_Clinical_Server")

def get_secure_client(jwt_token: str = None) -> Client:
    client = create_client(SUPABASE_URL, SUPABASE_KEY)
    if jwt_token:
        client.postgrest.auth(jwt_token)
    return client

@server.list_tools()
async def handle_list_tools() -> list[types.Tool]:
    """Defines the Clinical Tools for the AI"""
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
    """Executes the tool with strict RLS enforcement"""
    supabase = get_secure_client(arguments.get("jwt_token"))
    user_id = arguments.get("user_id")
    
    if name == "get_patient_baseline":
        try:
            profile_res = supabase.table('profiles').select('*').eq('id', user_id).execute()
            return [types.TextContent(type="text", text=str(profile_res.data))]
        except Exception as e:
            return [types.TextContent(type="text", text=f"Error: {str(e)}")]
            
    elif name == "analyze_cognitive_fatigue":
        try:
            limit = arguments.get("limit", 10)
            logs = supabase.table('session_logs').select('session_date, attention_stability_score').eq('user_id', user_id).limit(limit).execute()
            return [types.TextContent(type="text", text=str(logs.data))]
        except Exception as e:
            return [types.TextContent(type="text", text=f"Error: {str(e)}")]
            
    return [types.TextContent(type="text", text="Unknown tool")]

# ---- ASGI WEB SERVER FIX (The Magic) ----

sse = SseServerTransport("/messages")

async def health_check(request):
    """Render pings this to make sure the server didn't crash"""
    return JSONResponse({"status": "alive", "service": "NeuroBoost Clinical MCP"})

async def sse_app(scope, receive, send):
    """Raw ASGI app for the SSE endpoint"""
    async with sse.connect_sse(scope, receive, send) as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())

async def messages_app(scope, receive, send):
    """Raw ASGI app for the POST endpoint"""
    await sse.handle_post_message(scope, receive, send)

# We use 'Mount' instead of 'Route' so Starlette correctly passes the raw connection streams!
app = Starlette(routes=[
    Route("/", endpoint=health_check),
    Mount("/sse", app=sse_app),
    Mount("/messages", app=messages_app)
])

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    print(f"Starting Production MCP Server on port {port}...")
    uvicorn.run(app, host="0.0.0.0", port=port)
