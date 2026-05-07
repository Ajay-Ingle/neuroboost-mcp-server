import os
import uvicorn
from starlette.applications import Starlette
from starlette.routing import Route
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
sse_transport = None

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

# ---- WEB SERVER SETUP (This is what fixes the Render Error) ----
async def sse_endpoint(request):
    """Initial connection endpoint for Server-Sent Events"""
    global sse_transport
    sse_transport = SseServerTransport("/messages")
    await server.connect(sse_transport)
    return await sse_transport.handle_sse(request)

async def messages_endpoint(request):
    """Endpoint where the Next.js app sends the tool arguments"""
    if sse_transport:
        return await sse_transport.handle_post_message(request)

app = Starlette(routes=[
    Route("/sse", endpoint=sse_endpoint),
    Route("/messages", endpoint=messages_endpoint, methods=["POST"])
])

if __name__ == "__main__":
    # Dynamically grab the port from Render and explicitly bind to 0.0.0.0
    port = int(os.environ.get("PORT", 8000))
    print(f"Starting Production MCP Server on port {port}...")
    uvicorn.run(app, host="0.0.0.0", port=port)
