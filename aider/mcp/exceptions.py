"""
MCP-specific exceptions for Aider.

This module defines all custom exceptions used throughout
the MCP integration layer.
"""


class MCPError(Exception):
    """Base exception for all MCP-related errors."""

    pass


class MCPConnectionError(MCPError):
    """Raised when connection to an MCP server fails."""

    def __init__(self, server_name, message=None):
        self.server_name = server_name
        if message is None:
            message = f"Failed to connect to MCP server: {server_name}"
        super().__init__(message)


class MCPToolError(MCPError):
    """Raised when MCP tool execution fails."""

    def __init__(self, tool_name, message=None, original_error=None):
        self.tool_name = tool_name
        self.original_error = original_error
        if message is None:
            message = f"MCP tool '{tool_name}' execution failed"
            if original_error:
                message += f": {str(original_error)}"
        super().__init__(message)


class MCPTimeoutError(MCPError):
    """Raised when an MCP operation times out."""

    def __init__(self, operation, timeout_seconds=None):
        self.operation = operation
        self.timeout_seconds = timeout_seconds
        message = f"MCP operation '{operation}' timed out"
        if timeout_seconds:
            message += f" after {timeout_seconds}s"
        super().__init__(message)


class MCPConfigurationError(MCPError):
    """Raised when MCP configuration is invalid or missing."""

    pass


class MCPServerNotFoundError(MCPError):
    """Raised when trying to access a server that doesn't exist."""

    def __init__(self, server_name):
        self.server_name = server_name
        super().__init__(f"MCP server not found: {server_name}")


class MCPToolNotFoundError(MCPError):
    """Raised when trying to call a tool that doesn't exist."""

    def __init__(self, tool_name, server_name=None):
        self.tool_name = tool_name
        self.server_name = server_name
        message = f"MCP tool not found: {tool_name}"
        if server_name:
            message += f" on server {server_name}"
        super().__init__(message)


class MCPAuthenticationError(MCPError):
    """Raised when authentication with an MCP server fails."""

    def __init__(self, server_name, message=None):
        self.server_name = server_name
        if message is None:
            message = f"Authentication failed for MCP server: {server_name}"
        super().__init__(message)


class MCPTransportError(MCPError):
    """Raised when there's an error with the MCP transport layer."""

    def __init__(self, transport_type, message=None):
        self.transport_type = transport_type
        if message is None:
            message = f"Transport error ({transport_type})"
        super().__init__(message)
