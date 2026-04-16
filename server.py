from starlette.applications import Starlette
from starlette.routing import Route, Mount
from starlette.responses import JSONResponse
import uvicorn
import threading
from fastmcp import FastMCP
import httpx
import os
import base64
from typing import Optional, List, Any

mcp = FastMCP("rest980")

BASE_URL = os.environ.get("REST980_BASE_URL", "http://localhost:3000")
BASIC_AUTH_USER = os.environ.get("BASIC_AUTH_USER", "")
BASIC_AUTH_PASS = os.environ.get("BASIC_AUTH_PASS", "")


def get_auth_headers() -> dict:
    """Build basic auth headers if credentials are configured."""
    if BASIC_AUTH_USER and BASIC_AUTH_PASS:
        credentials = base64.b64encode(
            f"{BASIC_AUTH_USER}:{BASIC_AUTH_PASS}".encode()
        ).decode()
        return {"Authorization": f"Basic {credentials}"}
    return {}


async def make_request(
    method: str,
    path: str,
    params: Optional[dict] = None,
    json_body: Optional[dict] = None,
) -> dict:
    """Make an HTTP request to the rest980 server."""
    url = f"{BASE_URL}{path}"
    headers = get_auth_headers()
    async with httpx.AsyncClient(timeout=30.0) as client:
        if method.upper() == "GET":
            response = await client.get(url, headers=headers, params=params)
        elif method.upper() == "POST":
            response = await client.post(url, headers=headers, json=json_body, params=params)
        else:
            response = await client.request(method, url, headers=headers, params=params, json=json_body)
        
        response.raise_for_status()
        
        content_type = response.headers.get("content-type", "")
        if "application/json" in content_type:
            return response.json()
        elif "image/" in content_type or "png" in content_type:
            return {
                "content_type": content_type,
                "data_base64": base64.b64encode(response.content).decode(),
                "size_bytes": len(response.content),
                "message": "Map image retrieved successfully. Data is base64 encoded."
            }
        else:
            try:
                return response.json()
            except Exception:
                return {"response": response.text, "status_code": response.status_code}


@mcp.tool()
async def get_roomba_status(api_type: str = "local") -> dict:
    """
    Get the current status and state of the Roomba robot, including battery level,
    cleaning phase, position, mission info, and connectivity. Use this to check if
    the robot is cleaning, docking, idle, or in an error state before issuing commands.
    """
    try:
        # Get mission/state info
        mission_path = f"/api/{api_type}/info/mission"
        mission_data = await make_request("GET", mission_path)

        # Also try to get general state
        try:
            state_path = f"/api/{api_type}/info/state"
            state_data = await make_request("GET", state_path)
        except Exception:
            state_data = None

        # Try battery info
        try:
            battery_path = f"/api/{api_type}/info/batInfo"
            battery_data = await make_request("GET", battery_path)
        except Exception:
            battery_data = None

        result = {
            "mission": mission_data,
            "api_type": api_type,
        }
        if state_data:
            result["state"] = state_data
        if battery_data:
            result["battery_info"] = battery_data

        return result
    except httpx.HTTPStatusError as e:
        return {"error": f"HTTP error {e.response.status_code}: {e.response.text}", "api_type": api_type}
    except httpx.ConnectError:
        return {"error": f"Could not connect to rest980 at {BASE_URL}. Is the server running?", "api_type": api_type}
    except Exception as e:
        return {"error": str(e), "api_type": api_type}


@mcp.tool()
async def start_cleaning(api_type: str = "local") -> dict:
    """
    Start a cleaning mission on the Roomba. Use this when the user wants the robot
    to begin vacuuming. The robot must be docked or idle for this to work.
    """
    try:
        path = f"/api/{api_type}/action/start"
        result = await make_request("GET", path)
        return {"success": True, "response": result, "action": "start", "api_type": api_type}
    except httpx.HTTPStatusError as e:
        return {"error": f"HTTP error {e.response.status_code}: {e.response.text}", "action": "start", "api_type": api_type}
    except httpx.ConnectError:
        return {"error": f"Could not connect to rest980 at {BASE_URL}. Is the server running?", "action": "start"}
    except Exception as e:
        return {"error": str(e), "action": "start", "api_type": api_type}


@mcp.tool()
async def stop_cleaning(api_type: str = "local") -> dict:
    """
    Stop the current cleaning mission and pause the Roomba in place. Use this when
    the user wants to halt cleaning without sending the robot back to the dock.
    """
    try:
        path = f"/api/{api_type}/action/stop"
        result = await make_request("GET", path)
        return {"success": True, "response": result, "action": "stop", "api_type": api_type}
    except httpx.HTTPStatusError as e:
        return {"error": f"HTTP error {e.response.status_code}: {e.response.text}", "action": "stop", "api_type": api_type}
    except httpx.ConnectError:
        return {"error": f"Could not connect to rest980 at {BASE_URL}. Is the server running?", "action": "stop"}
    except Exception as e:
        return {"error": str(e), "action": "stop", "api_type": api_type}


@mcp.tool()
async def dock_roomba(api_type: str = "local") -> dict:
    """
    Send the Roomba back to its Home Base dock to charge. Use this after cleaning
    is complete or when the user wants to end a session and have the robot return home.
    """
    try:
        path = f"/api/{api_type}/action/dock"
        result = await make_request("GET", path)
        return {"success": True, "response": result, "action": "dock", "api_type": api_type}
    except httpx.HTTPStatusError as e:
        return {"error": f"HTTP error {e.response.status_code}: {e.response.text}", "action": "dock", "api_type": api_type}
    except httpx.ConnectError:
        return {"error": f"Could not connect to rest980 at {BASE_URL}. Is the server running?", "action": "dock"}
    except Exception as e:
        return {"error": str(e), "action": "dock", "api_type": api_type}


@mcp.tool()
async def pause_cleaning(api_type: str = "local") -> dict:
    """
    Pause the Roomba mid-mission without ending the cleaning session. The robot will
    stop in place and the mission can be resumed later. Use this for a temporary halt.
    """
    try:
        path = f"/api/{api_type}/action/pause"
        result = await make_request("GET", path)
        return {"success": True, "response": result, "action": "pause", "api_type": api_type}
    except httpx.HTTPStatusError as e:
        return {"error": f"HTTP error {e.response.status_code}: {e.response.text}", "action": "pause", "api_type": api_type}
    except httpx.ConnectError:
        return {"error": f"Could not connect to rest980 at {BASE_URL}. Is the server running?", "action": "pause"}
    except Exception as e:
        return {"error": str(e), "action": "pause", "api_type": api_type}


@mcp.tool()
async def resume_cleaning(api_type: str = "local") -> dict:
    """
    Resume a previously paused cleaning mission. Use this to continue cleaning after
    the Roomba has been paused, without starting an entirely new mission.
    """
    try:
        path = f"/api/{api_type}/action/resume"
        result = await make_request("GET", path)
        return {"success": True, "response": result, "action": "resume", "api_type": api_type}
    except httpx.HTTPStatusError as e:
        return {"error": f"HTTP error {e.response.status_code}: {e.response.text}", "action": "resume", "api_type": api_type}
    except httpx.ConnectError:
        return {"error": f"Could not connect to rest980 at {BASE_URL}. Is the server running?", "action": "resume"}
    except Exception as e:
        return {"error": str(e), "action": "resume", "api_type": api_type}


@mcp.tool()
async def get_cleaning_map(mode: str = "latest", format: str = "png") -> dict:
    """
    Retrieve the latest cleaning map image generated from the Roomba's VSLAM navigation
    data. Use this to show the user a visual map of what areas have been cleaned during
    the current or last mission.
    """
    try:
        # rest980 serves maps at /map endpoint
        if mode == "latest":
            path = "/map"
        else:
            path = f"/map/{mode}"

        url = f"{BASE_URL}{path}"
        headers = get_auth_headers()

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(url, headers=headers)
            response.raise_for_status()

            content_type = response.headers.get("content-type", "")
            if "image" in content_type or len(response.content) > 100:
                return {
                    "success": True,
                    "content_type": content_type,
                    "data_base64": base64.b64encode(response.content).decode(),
                    "size_bytes": len(response.content),
                    "mode": mode,
                    "format": format,
                    "message": "Map image retrieved. The 'data_base64' field contains the base64-encoded image."
                }
            else:
                try:
                    return {"success": True, "response": response.json(), "mode": mode}
                except Exception:
                    return {"success": True, "response": response.text, "mode": mode}
    except httpx.HTTPStatusError as e:
        return {"error": f"HTTP error {e.response.status_code}: {e.response.text}", "mode": mode}
    except httpx.ConnectError:
        return {"error": f"Could not connect to rest980 at {BASE_URL}. Is the server running?", "mode": mode}
    except Exception as e:
        return {"error": str(e), "mode": mode}


@mcp.tool()
async def send_roomba_command(
    command: str,
    params: Optional[List[Any]] = None,
    api_type: str = "local"
) -> dict:
    """
    Send a raw or advanced command to the Roomba that is not covered by the standard
    start/stop/dock tools, such as setting preferences, configuring cleaning passes,
    adjusting edge-clean settings, or invoking any dorita980 method directly.
    Use this for advanced control or configuration tasks.

    Common commands:
    - 'find': Make the robot play a sound to locate it
    - 'evac': Empty the bin (i7+ only)
    - 'setCarpetBoost': Set carpet boost mode
    - 'setEdgeClean': Enable/disable edge cleaning
    - 'setCleaningPasses': Set number of cleaning passes
    - 'getCarpetBoost': Get current carpet boost setting
    - 'getCleaningPasses': Get current cleaning passes setting
    - 'getEdgeClean': Get edge clean setting
    - 'getPreferences': Get all preferences
    """
    try:
        # Determine if this is a GET (info/query) or POST (action/set) command
        # Commands starting with 'get' or 'info' are typically GET requests
        command_lower = command.lower()
        
        # Map commands to appropriate REST endpoints
        # Try action endpoint first for most commands
        if command_lower.startswith("get") or command_lower in ["find"]:
            # For find and get-type commands, use GET
            # Try info path for get commands
            if command_lower.startswith("get"):
                path = f"/api/{api_type}/info/{command}"
            else:
                path = f"/api/{api_type}/action/{command}"
            
            result = await make_request("GET", path)
        elif params is not None:
            # POST with params for set-type commands
            path = f"/api/{api_type}/action/{command}"
            body = {"params": params} if params else {}
            try:
                result = await make_request("POST", path, json_body=body)
            except httpx.HTTPStatusError:
                # Fallback to GET
                result = await make_request("GET", path)
        else:
            # Default to GET action
            path = f"/api/{api_type}/action/{command}"
            try:
                result = await make_request("GET", path)
            except httpx.HTTPStatusError as e:
                if e.response.status_code == 404:
                    # Try info path
                    path = f"/api/{api_type}/info/{command}"
                    result = await make_request("GET", path)
                else:
                    raise

        return {
            "success": True,
            "command": command,
            "params": params,
            "api_type": api_type,
            "response": result
        }
    except httpx.HTTPStatusError as e:
        return {
            "error": f"HTTP error {e.response.status_code}: {e.response.text}",
            "command": command,
            "api_type": api_type
        }
    except httpx.ConnectError:
        return {
            "error": f"Could not connect to rest980 at {BASE_URL}. Is the server running?",
            "command": command
        }
    except Exception as e:
        return {"error": str(e), "command": command, "api_type": api_type}




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
