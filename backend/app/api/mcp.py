"""
MCP API endpoints for managing external Model Context Protocol tool servers and executing tools.
"""
from typing import Dict, Any, List
from fastapi import APIRouter, Depends, HTTPException, Body
from app.api.auth import get_current_user
from app.mcp_client import mcp_client_manager

router = APIRouter(prefix="/api/mcp", tags=["mcp"])


@router.get("/servers")
async def list_servers(user: dict = Depends(get_current_user)):
    """List all registered MCP tool servers."""
    return mcp_client_manager.list_servers()


@router.post("/servers")
async def add_server(
    server_config: Dict[str, Any] = Body(...),
    user: dict = Depends(get_current_user)
):
    """Register a new external MCP server (stdio command or SSE URL)."""
    return mcp_client_manager.add_server(server_config)


@router.patch("/servers/{server_id}/toggle")
async def toggle_server(
    server_id: str,
    enabled: bool = Body(..., embed=True),
    user: dict = Depends(get_current_user)
):
    """Enable or disable an MCP server."""
    updated = mcp_client_manager.toggle_server(server_id, enabled)
    if not updated:
        raise HTTPException(status_code=404, detail=f"MCP Server '{server_id}' not found")
    return updated


@router.delete("/servers/{server_id}")
async def delete_server(
    server_id: str,
    user: dict = Depends(get_current_user)
):
    """Delete an MCP server configuration."""
    success = mcp_client_manager.delete_server(server_id)
    if not success:
        raise HTTPException(status_code=404, detail=f"MCP Server '{server_id}' not found")
    return {"status": "success", "message": f"Server '{server_id}' removed."}


@router.get("/tools")
async def list_tools(user: dict = Depends(get_current_user)):
    """List all active MCP tools provided by enabled servers."""
    return mcp_client_manager.list_available_tools()


@router.post("/tools/execute")
async def execute_tool(
    payload: Dict[str, Any] = Body(...),
    user: dict = Depends(get_current_user)
):
    """Execute an MCP tool call."""
    tool_name = payload.get("tool_name")
    arguments = payload.get("arguments", {})
    if not tool_name:
        raise HTTPException(status_code=400, detail="tool_name is required")
    
    result = await mcp_client_manager.execute_tool(tool_name, arguments)
    return result
