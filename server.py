from starlette.applications import Starlette
from starlette.routing import Route, Mount
from starlette.responses import JSONResponse
import uvicorn
import threading
from fastmcp import FastMCP
import httpx
import os
import json
from typing import Optional, List

mcp = FastMCP("rest980")

BASE_URL = os.environ.get("REST980_BASE_URL", "http://localhost:3000")
BASIC_AUTH_USER = os.environ.get("BASIC_AUTH_USER", "")
BASIC_AUTH_PASS = os.environ.get("BASIC_AUTH_PASS", "")


def get_auth():
    if BASIC_AUTH_USER and BASIC_AUTH_PASS:
        return (BASIC_AUTH_USER, BASIC_AUTH_PASS)
    return None


async def make_request(method: str, path: str, json_body=None, params=None):
    auth = get_auth()
    url = f"{BASE_URL}{path}"
    async with httpx.AsyncClient(timeout=30.0) as client:
        kwargs = {"url": url}
        if auth:
            kwargs["auth"] = auth
        if params:
            kwargs["params"] = params
        if json_body is not None:
            kwargs["json"] = json_body
        response = await getattr(client, method.lower())(**kwargs)
        response.raise_for_status()
        try:
            return response.json()
        except Exception:
            return {"raw": response.text, "status_code": response.status_code}


@mcp.tool()
async def get_roomba_status(api_type: str = "local") -> dict:
    """
    Get the current status and state of the Roomba robot, including battery level,
    cleaning state, mission status, and position. Use this to check if the robot
    is cleaning, docked, or idle before issuing commands.
    """
    path = f"/api/{api_type}/info/state"
    try:
        result = await make_request("GET", path)
        return {"success": True, "api_type": api_type, "status": result}
    except httpx.HTTPStatusError as e:
        # Try mission endpoint as fallback
        try:
            mission_path = f"/api/{api_type}/info/mission"
            mission_result = await make_request("GET", mission_path)
            return {"success": True, "api_type": api_type, "status": mission_result}
        except Exception as e2:
            return {"success": False, "error": str(e), "fallback_error": str(e2)}
    except Exception as e:
        return {"success": False, "error": str(e)}


@mcp.tool()
async def start_cleaning(
    api_type: str = "local",
    pmap_id: Optional[str] = None,
    regions: Optional[List[dict]] = None
) -> dict:
    """
    Start a cleaning mission on the Roomba. Use this to begin vacuuming.
    Can optionally specify a room or zone for i7/i7+ models that support smart mapping.
    """
    try:
        if pmap_id and regions:
            # Use cleanRoom endpoint for targeted cleaning (POST)
            path = f"/api/{api_type}/action/cleanRoom"
            body = {"pmap_id": pmap_id, "regions": regions}
            result = await make_request("POST", path, json_body=body)
        else:
            # Use standard start endpoint (GET)
            path = f"/api/{api_type}/action/start"
            result = await make_request("GET", path)
        return {"success": True, "api_type": api_type, "result": result}
    except Exception as e:
        return {"success": False, "error": str(e)}


@mcp.tool()
async def stop_cleaning(api_type: str = "local") -> dict:
    """
    Stop the current cleaning mission and have the Roomba return to its dock/home base.
    Use this to end an active cleaning session.
    """
    try:
        # First stop, then dock
        stop_path = f"/api/{api_type}/action/stop"
        stop_result = await make_request("GET", stop_path)
        dock_path = f"/api/{api_type}/action/dock"
        dock_result = await make_request("GET", dock_path)
        return {
            "success": True,
            "api_type": api_type,
            "stop_result": stop_result,
            "dock_result": dock_result
        }
    except Exception as e:
        # Try dock only if stop failed
        try:
            dock_path = f"/api/{api_type}/action/dock"
            dock_result = await make_request("GET", dock_path)
            return {"success": True, "api_type": api_type, "dock_result": dock_result, "note": "stop failed, sent dock command"}
        except Exception as e2:
            return {"success": False, "error": str(e), "dock_error": str(e2)}


@mcp.tool()
async def pause_resume_cleaning(action: str, api_type: str = "local") -> dict:
    """
    Pause an active cleaning mission or resume a paused one.
    Use pause when you need to temporarily halt cleaning without ending the mission,
    and resume to continue from where it left off.
    """
    if action not in ("pause", "resume"):
        return {"success": False, "error": f"Invalid action '{action}'. Must be 'pause' or 'resume'."}
    try:
        path = f"/api/{api_type}/action/{action}"
        result = await make_request("GET", path)
        return {"success": True, "api_type": api_type, "action": action, "result": result}
    except Exception as e:
        return {"success": False, "error": str(e)}


@mcp.tool()
async def get_robot_info(
    info_type: str = "sys",
    api_type: str = "local"
) -> dict:
    """
    Retrieve detailed information about the Roomba robot including firmware version,
    model, SKU, capabilities, preferences, and schedule settings.
    info_type options: 'sys' for system info, 'prefs' for preferences,
    'schedule' for cleaning schedule, 'cloud' for cloud connection info, 'week' for weekly schedule.
    """
    # Map info_type to actual API path segments
    info_type_map = {
        "sys": "sys",
        "prefs": "prefs",
        "schedule": "schedule",
        "cloud": "cloud",
        "week": "week",
        "mission": "mission",
        "state": "state",
        "version": "version"
    }
    endpoint = info_type_map.get(info_type, info_type)
    path = f"/api/{api_type}/info/{endpoint}"
    try:
        result = await make_request("GET", path)
        return {"success": True, "api_type": api_type, "info_type": info_type, "data": result}
    except Exception as e:
        return {"success": False, "error": str(e)}


@mcp.tool()
async def set_robot_preferences(
    preferences: str,
    api_type: str = "local"
) -> dict:
    """
    Update Roomba preferences and settings such as cleaning passes, carpet boost,
    edge clean, and scheduled cleaning times. preferences should be a JSON string
    of key-value pairs. Examples: noAutoPasses, twoPass, carpetBoost, openOnly, schedHold, binPause.
    """
    try:
        prefs_dict = json.loads(preferences)
    except json.JSONDecodeError as e:
        return {"success": False, "error": f"Invalid JSON in preferences: {str(e)}"}

    try:
        path = f"/api/{api_type}/action/setPrefs"
        result = await make_request("POST", path, json_body=prefs_dict)
        return {"success": True, "api_type": api_type, "updated_preferences": prefs_dict, "result": result}
    except Exception as e:
        return {"success": False, "error": str(e)}


@mcp.tool()
async def get_maps(map_action: str = "list") -> dict:
    """
    Retrieve the floor plan maps generated by the Roomba during cleaning missions.
    Use this for i7/i7+ models with smart mapping to get map IDs needed for
    room-specific cleaning, or to view the latest cleaning map/path visualization.
    map_action: 'list' to get all saved maps with their IDs and regions,
    'latest' to get the most recent cleaning mission map image.
    """
    try:
        if map_action == "latest":
            path = "/map/latest"
            result = await make_request("GET", path)
            return {"success": True, "map_action": map_action, "data": result}
        else:
            # Default: list all maps
            path = "/api/local/info/maps"
            result = await make_request("GET", path)
            return {"success": True, "map_action": map_action, "data": result}
    except Exception as e:
        return {"success": False, "error": str(e)}


@mcp.tool()
async def find_robot(api_type: str = "local") -> dict:
    """
    Make the Roomba play a sound to help locate it in the home.
    Use this when you cannot find where the robot is physically located.
    """
    try:
        path = f"/api/{api_type}/action/find"
        result = await make_request("GET", path)
        return {"success": True, "api_type": api_type, "result": result, "message": "Roomba should now be playing a sound to help you locate it."}
    except Exception as e:
        return {"success": False, "error": str(e)}




_SERVER_SLUG = "koalazak-rest980"

def _track(tool_name: str, ua: str = ""):
    try:
        import urllib.request, json as _json
        data = _json.dumps({"slug": _SERVER_SLUG, "event": "tool_call", "tool": tool_name, "user_agent": ua}).encode()
        req = urllib.request.Request("https://www.volspan.dev/api/analytics/event", data=data, headers={"Content-Type": "application/json"})
        urllib.request.urlopen(req, timeout=1)
    except Exception:
        pass

async def health(request):
    return JSONResponse({"status": "ok", "server": mcp.name})

async def tools(request):
    registered = await mcp.list_tools()
    tool_list = [{"name": t.name, "description": t.description or ""} for t in registered]
    return JSONResponse({"tools": tool_list, "count": len(tool_list)})

sse_app = mcp.http_app(transport="sse")

app = Starlette(
    routes=[
        Route("/health", health),
        Route("/tools", tools),
        Mount("/", sse_app),
    ],
    lifespan=sse_app.lifespan,
)

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", 8000)))
