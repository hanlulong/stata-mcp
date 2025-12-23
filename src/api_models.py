#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
API Models for Stata MCP Server

This module contains Pydantic models and dataclasses used for API
request/response handling in the Stata MCP Server.
"""

from typing import Dict, Any, Optional, List
from pydantic import BaseModel, Field


# =============================================================================
# MCP Tool Parameter Models
# =============================================================================

class RunSelectionParams(BaseModel):
    """Parameters for running Stata code selection."""
    selection: str = Field(..., description="The Stata code to execute")
    session_id: Optional[str] = Field(None, description="Optional session ID for multi-session mode")


class RunFileParams(BaseModel):
    """Parameters for running a Stata .do file."""
    file_path: str = Field(..., description="The full path to the .do file")
    timeout: int = Field(600, description="Timeout in seconds (default: 600 seconds / 10 minutes)")
    session_id: Optional[str] = Field(None, description="Optional session ID for multi-session mode")
    working_dir: Optional[str] = Field(None, description="Optional working directory")


# =============================================================================
# Legacy VS Code Extension Support Models
# =============================================================================

class ToolRequest(BaseModel):
    """Request format for legacy /v1/tools endpoint."""
    tool: str
    parameters: Dict[str, Any]


class ToolResponse(BaseModel):
    """Response format for legacy /v1/tools endpoint."""
    status: str
    result: Optional[str] = None
    message: Optional[str] = None


# =============================================================================
# Session Management Models
# =============================================================================

class SessionInfo(BaseModel):
    """Information about a Stata session."""
    session_id: str = Field(..., description="Unique session identifier")
    state: str = Field(..., description="Current session state (idle, busy, error)")
    created_at: Optional[str] = Field(None, description="Session creation timestamp")
    last_used: Optional[str] = Field(None, description="Last activity timestamp")


class SessionListResponse(BaseModel):
    """Response for listing all sessions."""
    sessions: List[SessionInfo] = Field(default_factory=list)
    total: int = Field(0, description="Total number of active sessions")
    max_sessions: int = Field(0, description="Maximum allowed sessions")


class SessionCreateRequest(BaseModel):
    """Request to create a new session."""
    session_id: Optional[str] = Field(None, description="Optional custom session ID")


class SessionActionRequest(BaseModel):
    """Request for session actions (stop, destroy)."""
    action: str = Field(..., description="Action: 'stop' or 'destroy'")


# =============================================================================
# Execution Status Models
# =============================================================================

class ExecutionStatus(BaseModel):
    """Current execution status."""
    is_executing: bool = Field(False, description="Whether code is currently executing")
    session_id: Optional[str] = Field(None, description="Session ID if executing")
    command_id: Optional[str] = Field(None, description="Current command ID")


class StopExecutionResponse(BaseModel):
    """Response from stop execution request."""
    status: str = Field(..., description="Result status")
    message: Optional[str] = Field(None, description="Status message")


# =============================================================================
# Health and Status Models
# =============================================================================

class HealthResponse(BaseModel):
    """Server health check response."""
    status: str = Field("ok", description="Server status")
    stata_available: bool = Field(False, description="Whether Stata is available")
    multi_session_enabled: bool = Field(False, description="Whether multi-session mode is enabled")
    active_sessions: int = Field(0, description="Number of active sessions")
    version: str = Field("0.4.1", description="Server version")


# =============================================================================
# Error Response Models
# =============================================================================

class ErrorResponse(BaseModel):
    """Standard error response."""
    error: str = Field(..., description="Error message")
    details: Optional[str] = Field(None, description="Additional error details")
    code: Optional[str] = Field(None, description="Error code for programmatic handling")
