"""
MCP Client Manager.

Manages connections to MCP servers, tool discovery, and tool execution.
Provides async-to-sync bridge for integration with Aider's synchronous codebase.
"""

import asyncio
import logging
from typing import Dict, List, Any, Optional
from functools import wraps

import nest_asyncio

from .exceptions import (
    MCPConnectionError,
    MCPToolError,
    MCPTimeoutError,
    MCPServerNotFoundError,
    MCPToolNotFoundError,
)
from .registry import MCPRegistry
from .tools import MCPToolWrapper, MCPToolRegistry


logger = logging.getLogger(__name__)

# Apply nest_asyncio to allow nested event loops
# This is needed because Aider is synchronous but MCP is async
nest_asyncio.apply()


def async_to_sync(async_func):
    """
    Decorator to convert async functions to sync.

    This allows MCP's async operations to be called from Aider's
    synchronous code without await syntax.
    """
    @wraps(async_func)
    def wrapper(*args, **kwargs):
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

        if loop.is_running():
            # We're already in an async context, use nest_asyncio
            return loop.run_until_complete(async_func(*args, **kwargs))
        else:
            # Start a new event loop
            return asyncio.run(async_func(*args, **kwargs))

    return wrapper


class MCPServerConnection:
    """
    Represents a connection to a single MCP server.

    Handles:
    - Server lifecycle (connect/disconnect)
    - Tool discovery
    - Tool execution
    """

    def __init__(self, server_name: str, config: Dict[str, Any]):
        """
        Initialize MCP server connection.

        Args:
            server_name: Name of the server
            config: Server configuration dict
        """
        self.server_name = server_name
        self.config = config
        self.client = None
        self.session = None
        self._stdio_context = None
        self.connected = False
        self.tools: List[MCPToolWrapper] = []

    async def connect(self):
        """
        Connect to the MCP server.

        Raises:
            MCPConnectionError: If connection fails
        """
        try:
            transport = self.config.get('transport', 'stdio')

            if transport == 'stdio':
                await self._connect_stdio()
            elif transport == 'sse':
                await self._connect_sse()
            elif transport == 'http':
                await self._connect_http()
            else:
                raise MCPConnectionError(
                    self.server_name,
                    f"Unknown transport: {transport}"
                )

            self.connected = True
            logger.info(f"Connected to MCP server: {self.server_name}")

            # Discover tools
            await self.discover_tools()

        except Exception as e:
            logger.error(f"Failed to connect to {self.server_name}: {e}")
            raise MCPConnectionError(self.server_name, str(e))

    async def _connect_stdio(self):
        """Connect using stdio transport."""
        # Import MCP SDK
        try:
            from mcp import ClientSession, StdioServerParameters
            from mcp.client.stdio import stdio_client
        except ImportError:
            raise MCPConnectionError(
                self.server_name,
                "MCP SDK not installed. Run: pip install mcp"
            )

        command = self.config.get('command')
        args = self.config.get('args', [])
        env = self.config.get('env', {})

        if not command:
            raise MCPConnectionError(
                self.server_name,
                "No command specified for stdio transport"
            )

        # Create server parameters
        server_params = StdioServerParameters(
            command=command,
            args=args,
            env=env if env else None,
        )

        # Connect - properly manage async context
        self._stdio_context = stdio_client(server_params)
        read, write = await self._stdio_context.__aenter__()
        self.session = ClientSession(read, write)
        await self.session.__aenter__()
        await self.session.initialize()

    async def _connect_sse(self):
        """Connect using SSE transport."""
        # TODO: Implement SSE transport
        # Will use litellm's experimental MCP client for this
        raise NotImplementedError("SSE transport not yet implemented")

    async def _connect_http(self):
        """Connect using HTTP transport."""
        # TODO: Implement HTTP transport
        # Will use litellm's experimental MCP client for this
        raise NotImplementedError("HTTP transport not yet implemented")

    async def disconnect(self):
        """Disconnect from the MCP server."""
        if self.session:
            try:
                await self.session.__aexit__(None, None, None)
            except Exception as e:
                logger.warning(f"Error disconnecting session from {self.server_name}: {e}")

        if self._stdio_context:
            try:
                await self._stdio_context.__aexit__(None, None, None)
            except Exception as e:
                logger.warning(f"Error disconnecting stdio from {self.server_name}: {e}")

        self.connected = False
        self.tools.clear()
        logger.info(f"Disconnected from MCP server: {self.server_name}")

    async def discover_tools(self):
        """
        Discover available tools from the server.

        Raises:
            MCPConnectionError: If not connected
        """
        if not self.connected or not self.session:
            raise MCPConnectionError(
                self.server_name,
                "Not connected to server"
            )

        try:
            # List tools from server
            tools_response = await self.session.list_tools()

            # Convert to MCPToolWrapper instances
            self.tools = []
            for tool in tools_response.tools:
                # Prefix tool name with mcp__servername__ for namespacing
                prefixed_name = f"mcp__{self.server_name}__{tool.name}"
                wrapper = MCPToolWrapper(
                    name=prefixed_name,
                    description=tool.description or "",
                    input_schema=tool.inputSchema or {},
                    server_name=self.server_name,
                )
                self.tools.append(wrapper)

            logger.info(
                f"Discovered {len(self.tools)} tools from {self.server_name}"
            )

        except Exception as e:
            logger.error(f"Failed to discover tools from {self.server_name}: {e}")
            raise

    async def call_tool(self, tool_name: str, arguments: Dict[str, Any]) -> Any:
        """
        Call a tool on this server.

        Args:
            tool_name: Name of the tool to call
            arguments: Tool arguments

        Returns:
            Tool result

        Raises:
            MCPToolError: If tool execution fails
            MCPToolNotFoundError: If tool doesn't exist
        """
        if not self.connected or not self.session:
            raise MCPConnectionError(
                self.server_name,
                "Not connected to server"
            )

        # Check if tool exists (with prefix)
        tool_exists = any(t.name == tool_name for t in self.tools)
        if not tool_exists:
            raise MCPToolNotFoundError(tool_name, self.server_name)

        # Strip the mcp__servername__ prefix for the actual MCP call
        # The MCP server expects the unprefixed tool name
        prefix = f"mcp__{self.server_name}__"
        if tool_name.startswith(prefix):
            unprefixed_name = tool_name[len(prefix):]
        else:
            unprefixed_name = tool_name

        try:
            # Call the tool with unprefixed name
            result = await self.session.call_tool(unprefixed_name, arguments)
            return result

        except Exception as e:
            logger.error(f"Tool execution failed: {tool_name} on {self.server_name}: {e}")
            raise MCPToolError(tool_name, original_error=e)


class MCPClientManager:
    """
    Main MCP client manager for Aider.

    Manages:
    - Multiple MCP server connections
    - Global tool registry
    - Tool discovery and execution
    - Configuration via MCPRegistry
    """

    def __init__(self, config_path: Optional[str] = None):
        """
        Initialize MCP client manager.

        Args:
            config_path: Optional path to MCP configuration file
        """
        self.registry = MCPRegistry(config_path)
        self.connections: Dict[str, MCPServerConnection] = {}
        self.tool_registry = MCPToolRegistry()
        self.timeout = self.registry.get_tool_settings().get('timeout', 30)

    @async_to_sync
    async def initialize(self):
        """
        Initialize the MCP client manager.

        Connects to auto-connect servers and discovers tools.
        """
        logger.info("Initializing MCP client manager")

        # Connect to auto-connect servers
        auto_connect_servers = self.registry.get_auto_connect_servers()

        for server_name in auto_connect_servers:
            try:
                await self.connect_server(server_name)
            except Exception as e:
                logger.warning(
                    f"Failed to auto-connect to {server_name}: {e}"
                )

        logger.info(
            f"MCP initialization complete. "
            f"Connected to {len(self.connections)} servers, "
            f"{len(self.tool_registry)} tools available"
        )

    @async_to_sync
    async def connect_server(self, server_name: str):
        """
        Connect to an MCP server.

        Args:
            server_name: Name of the server to connect to

        Raises:
            MCPServerNotFoundError: If server not in registry
            MCPConnectionError: If connection fails
        """
        config = self.registry.get_server_config(server_name)
        if not config:
            raise MCPServerNotFoundError(server_name)

        if server_name in self.connections:
            logger.info(f"Already connected to {server_name}")
            return

        connection = MCPServerConnection(server_name, config)
        await connection.connect()

        self.connections[server_name] = connection

        # Register tools
        self.tool_registry.register_tools(connection.tools)

        logger.info(f"Successfully connected to {server_name}")

    @async_to_sync
    async def disconnect_server(self, server_name: str):
        """
        Disconnect from an MCP server.

        Args:
            server_name: Name of the server to disconnect from

        Raises:
            MCPServerNotFoundError: If not connected
        """
        if server_name not in self.connections:
            raise MCPServerNotFoundError(server_name)

        connection = self.connections[server_name]
        await connection.disconnect()

        # Unregister tools from this server
        for tool_name in self.tool_registry.list_tools_by_server(server_name):
            self.tool_registry.unregister_tool(tool_name)

        del self.connections[server_name]

        logger.info(f"Disconnected from {server_name}")

    def list_servers(self) -> List[str]:
        """
        List all connected servers.

        Returns:
            List of connected server names
        """
        return list(self.connections.keys())

    def is_connected(self, server_name: str) -> bool:
        """
        Check if connected to a server.

        Args:
            server_name: Name of the server

        Returns:
            True if connected
        """
        return server_name in self.connections

    def list_tools(self) -> List[str]:
        """
        List all available tools.

        Returns:
            List of tool names
        """
        return self.tool_registry.list_tools()

    def get_tool(self, tool_name: str) -> Optional[MCPToolWrapper]:
        """
        Get a tool by name.

        Args:
            tool_name: Name of the tool

        Returns:
            MCPToolWrapper or None if not found
        """
        return self.tool_registry.get_tool(tool_name)

    @async_to_sync
    async def call_tool(self, tool_name: str, arguments: Dict[str, Any]) -> Any:
        """
        Execute an MCP tool.

        Args:
            tool_name: Name of the tool to execute
            arguments: Tool arguments dict

        Returns:
            Tool execution result

        Raises:
            MCPToolNotFoundError: If tool doesn't exist
            MCPToolError: If execution fails
        """
        # Find which server has this tool
        tool = self.tool_registry.get_tool(tool_name)
        if not tool:
            raise MCPToolNotFoundError(tool_name)

        server_name = tool.server_name

        if server_name not in self.connections:
            raise MCPConnectionError(
                server_name,
                f"Not connected to server providing tool: {tool_name}"
            )

        connection = self.connections[server_name]

        try:
            # Call the tool with timeout
            result = await asyncio.wait_for(
                connection.call_tool(tool_name, arguments),
                timeout=self.timeout
            )
            return result

        except asyncio.TimeoutError:
            raise MCPTimeoutError(f"call_tool({tool_name})", self.timeout)

    def get_tools_for_llm(self) -> List[Dict[str, Any]]:
        """
        Get all tools in LiteLLM format for the LLM.

        Returns:
            List of tool definitions
        """
        return self.tool_registry.get_all_litellm_tools()

    def get_tools_description(self) -> str:
        """
        Get formatted description of all tools for system prompt.

        Returns:
            Formatted string describing available tools
        """
        return self.tool_registry.get_tools_for_prompt()

    @async_to_sync
    async def shutdown(self):
        """Disconnect from all servers and cleanup."""
        logger.info("Shutting down MCP client manager")

        for server_name in list(self.connections.keys()):
            try:
                await self.disconnect_server(server_name)
            except Exception as e:
                logger.warning(f"Error disconnecting from {server_name}: {e}")

        self.tool_registry.clear()
        logger.info("MCP client manager shutdown complete")
