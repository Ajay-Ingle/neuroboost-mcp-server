from mcp.server.fastmcp import FastMCP
from supabase import create_client, Client
import os
from dotenv import load_dotenv

# Load local env if present (Render will automatically use its own Dashboard Variables)
load_dotenv(".env.local")

# Supabase Credentials
SUPABASE_URL = os.environ.get("NEXT_PUBLIC_SUPABASE_URL")
SUPABASE_KEY = os.environ.get("NEXT_PUBLIC_SUPABASE_ANON_KEY")

if not SUPABASE_URL or not SUPABASE_KEY:
    print("WARNING: Missing Supabase credentials. Ensure environment variables are set in Render.")

# Initialize the official FastMCP Server
mcp = FastMCP("NeuroBoost_Clinical_Server")

def get_secure_client(jwt_token: str = None) -> Client:
    """
    Helper function to get a Supabase client.
    Binds the JWT token to strictly enforce our Row Level Security (RLS) policies.
    """
    client = create_client(SUPABASE_URL, SUPABASE_KEY)
    if jwt_token:
        client.postgrest.auth(jwt_token)
    return client

@mcp.tool()
def get_patient_baseline(user_id: str, jwt_token: str = None) -> str:
    """
    Retrieves the patient's baseline demographics, medical conditions, and lifetime training stats.
    Requires user_id to query.
    """
    supabase = get_secure_client(jwt_token)
        
    try:
        profile_res = supabase.table('profiles').select('*').eq('id', user_id).execute()
        stats_res = supabase.table('user_stats').select('*').eq('user_id', user_id).execute()
        
        if not profile_res.data:
            return f"No profile found for user_id: {user_id}. Either they do not exist, or you lack permission."
            
        return str({
            "demographics": profile_res.data[0],
            "lifetime_stats": stats_res.data[0] if stats_res.data else "No lifetime stats found."
        })
    except Exception as e:
        return f"Error fetching baseline: {str(e)}"

@mcp.tool()
def analyze_cognitive_fatigue(user_id: str, limit: int = 10, jwt_token: str = None) -> str:
    """
    Extracts the attention_stability_score and performance_stability_variance over the last N sessions.
    Used to map cognitive exhaustion thresholds.
    """
    supabase = get_secure_client(jwt_token)
        
    try:
        logs = supabase.table('session_logs').select(
            'session_date, attention_stability_score, performance_stability_variance'
        ).eq('user_id', user_id).order('session_date', desc=True).limit(limit).execute()
        
        if not logs.data:
            return f"No session logs found for user_id: {user_id}."
            
        return str(logs.data)
    except Exception as e:
        return f"Error analyzing fatigue: {str(e)}"

@mcp.tool()
def evaluate_panic_resistance(user_id: str, limit: int = 5, jwt_token: str = None) -> str:
    """
    Analyzes the adaptation_accuracy_score and error_rate during high-difficulty spikes.
    Measures how the patient handles sudden cognitive load.
    """
    supabase = get_secure_client(jwt_token)
        
    try:
        logs = supabase.table('session_logs').select(
            'session_date, adaptation_accuracy_score, error_rate, difficulty_progression_level'
        ).eq('user_id', user_id).order('session_date', desc=True).limit(limit).execute()
        
        return str(logs.data)
    except Exception as e:
        return f"Error evaluating panic resistance: {str(e)}"

@mcp.tool()
def query_cohort_averages(primary_cohort: str, jwt_token: str = None) -> str:
    """
    Fetches the average performance metrics for a specific medical cohort (e.g., 'Post-Stroke', 'ADHD').
    Only Doctors (with the correct JWT) will have the RLS permissions to run this globally!
    """
    supabase = get_secure_client(jwt_token)
        
    try:
        profiles = supabase.table('profiles').select('id').eq('primary_cohort', primary_cohort).execute()
        user_ids = [p['id'] for p in profiles.data]
        
        if not user_ids:
            return f"No users found in the {primary_cohort} cohort."
            
        logs = supabase.table('session_logs').select(
            'reaction_time_ms_avg, accuracy_rate, effectiveness_score'
        ).in_('user_id', user_ids).limit(100).execute()
        
        if not logs.data:
            return f"No session logs found for cohort {primary_cohort}."
            
        total_rt = sum(log['reaction_time_ms_avg'] for log in logs.data if log['reaction_time_ms_avg'] is not None)
        total_acc = sum(log['accuracy_rate'] for log in logs.data if log['accuracy_rate'] is not None)
        count = len(logs.data)
        
        return str({
            "cohort": primary_cohort,
            "sample_size_sessions": count,
            "average_reaction_time_ms": round(total_rt / count, 2) if count else 0,
            "average_accuracy_rate": round(total_acc / count, 2) if count else 0
        })
    except Exception as e:
        return f"Error querying cohort averages: {str(e)}"

if __name__ == "__main__":
    # Render.com injects a dynamic PORT environment variable. We MUST bind to it.
    port = int(os.environ.get("PORT", 8000))
    
    # We use the SSE (Server-Sent Events) transport layer for Cloud HTTP hosting.
    print(f"Starting Clinical MCP Server on port {port}...")
    mcp.run(transport="sse", port=port)
