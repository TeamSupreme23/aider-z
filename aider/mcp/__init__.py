"""
MCP (Model Context Protocol) Integration for Aider.

This module provides MCP client functionality, allowing Aider to connect
to and use tools from MCP servers like Context7, Serena, and others.
"""

from .client import MCPClientManager, MCPServerConnection
from .registry import MCPRegistry
from .tools import MCPToolWrapper, MCPToolRegistry
from .exceptions import (
    MCPError,
    MCPConnectionError,
    MCPToolError,
    MCPTimeoutError,
    MCPConfigurationError,
    MCPServerNotFoundError,
    MCPToolNotFoundError,
    MCPAuthenticationError,
    MCPTransportError,
)

__all__ = [
    # Client
    'MCPClientManager',
    'MCPServerConnection',
    # Registry
    'MCPRegistry',
    # Tools
    'MCPToolWrapper',
    'MCPToolRegistry',
    # Exceptions
    'MCPError',
    'MCPConnectionError',
    'MCPToolError',
    'MCPTimeoutError',
    'MCPConfigurationError',
    'MCPServerNotFoundError',
    'MCPToolNotFoundError',
    'MCPAuthenticationError',
    'MCPTransportError',
]

__version__ = '0.1.0'
