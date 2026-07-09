"""MCP (Model Context Protocol) external tool integrations.

Wrapped tools:
  - create_jira_ticket: Create a Jira ticket for IT issues
  - query_ad_status: Query Active Directory account status
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Optional


@dataclass
class MCPToolResult:
    """Standardized result from an MCP tool call."""
    tool_name: str
    success: bool
    data: Any = None
    error: Optional[str] = None
    latency_ms: float = 0.0


async def create_jira_ticket(
    summary: str,
    description: str,
    issue_type: str = "Task",
    priority: str = "Medium",
    assignee: str | None = None,
) -> MCPToolResult:
    """Create a Jira ticket via the Jira MCP server.

    Args:
        summary: Ticket title/summary.
        description: Detailed description of the issue.
        issue_type: Jira issue type (Task, Bug, Incident, etc.).
        priority: Priority level.
        assignee: Username of the assignee.

    Returns:
        MCPToolResult with ticket details or error.
    """
    # TODO: Integrate with actual Jira MCP server
    # This is a stub that simulates the MCP tool call
    return MCPToolResult(
        tool_name="create_jira_ticket",
        success=True,
        data={
            "ticket_id": "JIRA-TODO",
            "summary": summary,
            "url": "https://jira.example.com/browse/JIRA-TODO",
        },
        latency_ms=0.0,
    )


async def query_ad_status(username: str) -> MCPToolResult:
    """Query Active Directory account status.

    Args:
        username: AD username to look up.

    Returns:
        MCPToolResult with account status details.
    """
    # TODO: Integrate with actual AD MCP server
    return MCPToolResult(
        tool_name="query_ad_status",
        success=True,
        data={
            "username": username,
            "account_enabled": True,
            "account_locked": False,
            "password_last_set": datetime.now().isoformat(),
            "groups": ["Domain Users", "IT-Support"],
        },
        latency_ms=0.0,
    )
