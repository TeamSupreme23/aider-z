"""
MCP Tool Wrappers.

Provides adapter layer to convert MCP tools into formats usable
by Aider and LiteLLM, including OpenAI function calling format.
"""

import json
import logging
from typing import Dict, List, Any, Optional


logger = logging.getLogger(__name__)


class MCPToolWrapper:
    """
    Wrapper for MCP tools that adapts them to Aider's interface.

    Provides:
    - Tool metadata management
    - OpenAI function format conversion
    - Result formatting for LLM consumption
    """

    def __init__(
        self,
        name: str,
        description: str,
        input_schema: Dict[str, Any],
        server_name: str,
    ):
        """
        Initialize MCP tool wrapper.

        Args:
            name: Tool name
            description: Tool description
            input_schema: JSON Schema for tool inputs
            server_name: Name of the MCP server providing this tool
        """
        self.name = name
        self.description = description
        self.input_schema = input_schema
        self.server_name = server_name

    def to_openai_function(self) -> Dict[str, Any]:
        """
        Convert MCP tool to OpenAI function format.

        Returns:
            Dict in OpenAI function calling format
        """
        return {
            "name": self.name,
            "description": self.description,
            "parameters": self.input_schema,
        }

    def to_litellm_tool(self) -> Dict[str, Any]:
        """
        Convert MCP tool to LiteLLM tool format.

        Returns:
            Dict in LiteLLM tool format
        """
        return {
            "type": "function",
            "function": self.to_openai_function(),
        }

    def format_result_for_llm(self, result: Any) -> str:
        """
        Format MCP tool result for LLM consumption.

        Args:
            result: Raw result from MCP tool execution

        Returns:
            Formatted string suitable for LLM context
        """
        if result is None:
            return "Tool execution completed successfully (no output)"

        # Handle different result types
        if isinstance(result, str):
            return result

        if isinstance(result, dict):
            # Check for common MCP result structures
            if 'content' in result:
                return self._format_content(result['content'])
            elif 'text' in result:
                return result['text']
            else:
                # Return JSON representation
                return json.dumps(result, indent=2)

        if isinstance(result, list):
            # List of content items
            return self._format_content_list(result)

        # Fallback: convert to string
        return str(result)

    def _format_content(self, content: Any) -> str:
        """Format content field from MCP result."""
        if isinstance(content, str):
            return content

        if isinstance(content, list):
            return self._format_content_list(content)

        if isinstance(content, dict):
            # MCP content object
            if content.get('type') == 'text':
                return content.get('text', '')
            elif content.get('type') == 'resource':
                uri = content.get('uri', 'unknown')
                text = content.get('text', '')
                return f"Resource: {uri}\n{text}"
            elif content.get('type') == 'image':
                uri = content.get('uri', 'unknown')
                return f"[Image: {uri}]"

        return str(content)

    def _format_content_list(self, content_list: List[Any]) -> str:
        """Format a list of content items."""
        formatted_parts = []

        for item in content_list:
            if isinstance(item, dict):
                formatted_parts.append(self._format_content(item))
            else:
                formatted_parts.append(str(item))

        return "\n\n".join(formatted_parts)

    def get_metadata(self) -> Dict[str, Any]:
        """
        Get tool metadata.

        Returns:
            Dict with tool metadata
        """
        return {
            'name': self.name,
            'description': self.description,
            'server': self.server_name,
            'input_schema': self.input_schema,
        }

    def __repr__(self) -> str:
        return f"MCPToolWrapper(name='{self.name}', server='{self.server_name}')"


class MCPToolRegistry:
    """
    Registry for managing multiple MCP tools.

    Provides:
    - Tool registration and lookup
    - Batch conversion to OpenAI/LiteLLM formats
    - Tool filtering and search
    """

    def __init__(self):
        """Initialize the tool registry."""
        self.tools: Dict[str, MCPToolWrapper] = {}

    def register_tool(self, tool: MCPToolWrapper):
        """
        Register a tool in the registry.

        Args:
            tool: MCPToolWrapper instance to register
        """
        self.tools[tool.name] = tool
        logger.debug(f"Registered tool: {tool.name} from {tool.server_name}")

    def register_tools(self, tools: List[MCPToolWrapper]):
        """
        Register multiple tools.

        Args:
            tools: List of MCPToolWrapper instances
        """
        for tool in tools:
            self.register_tool(tool)

    def unregister_tool(self, tool_name: str) -> bool:
        """
        Unregister a tool.

        Args:
            tool_name: Name of tool to remove

        Returns:
            True if tool was removed, False if not found
        """
        if tool_name in self.tools:
            del self.tools[tool_name]
            logger.debug(f"Unregistered tool: {tool_name}")
            return True
        return False

    def get_tool(self, tool_name: str) -> Optional[MCPToolWrapper]:
        """
        Get a tool by name.

        Args:
            tool_name: Name of the tool

        Returns:
            MCPToolWrapper instance or None if not found
        """
        return self.tools.get(tool_name)

    def has_tool(self, tool_name: str) -> bool:
        """
        Check if a tool is registered.

        Args:
            tool_name: Name of the tool

        Returns:
            True if tool exists
        """
        return tool_name in self.tools

    def list_tools(self) -> List[str]:
        """
        List all registered tool names.

        Returns:
            List of tool names
        """
        return list(self.tools.keys())

    def list_tools_by_server(self, server_name: str) -> List[str]:
        """
        List tools from a specific server.

        Args:
            server_name: Name of the MCP server

        Returns:
            List of tool names from that server
        """
        return [
            name for name, tool in self.tools.items()
            if tool.server_name == server_name
        ]

    def get_all_openai_functions(self) -> List[Dict[str, Any]]:
        """
        Get all tools in OpenAI function format.

        Returns:
            List of OpenAI function dicts
        """
        return [tool.to_openai_function() for tool in self.tools.values()]

    def get_all_litellm_tools(self) -> List[Dict[str, Any]]:
        """
        Get all tools in LiteLLM tool format.

        Returns:
            List of LiteLLM tool dicts
        """
        return [tool.to_litellm_tool() for tool in self.tools.values()]

    def get_tools_for_prompt(self) -> str:
        """
        Generate a formatted string describing all tools for system prompt.

        Returns:
            Formatted tool descriptions for LLM prompt
        """
        if not self.tools:
            return ""

        lines = ["# Available MCP Tools\n"]

        # Group tools by server
        tools_by_server: Dict[str, List[MCPToolWrapper]] = {}
        for tool in self.tools.values():
            if tool.server_name not in tools_by_server:
                tools_by_server[tool.server_name] = []
            tools_by_server[tool.server_name].append(tool)

        # Format by server
        for server_name, server_tools in tools_by_server.items():
            lines.append(f"\n## From {server_name}:")
            for tool in server_tools:
                lines.append(f"\n### {tool.name}")
                lines.append(f"{tool.description}")

                # Add parameter info
                if tool.input_schema and 'properties' in tool.input_schema:
                    lines.append("\nParameters:")
                    for param_name, param_info in tool.input_schema['properties'].items():
                        param_type = param_info.get('type', 'any')
                        param_desc = param_info.get('description', '')
                        required = param_name in tool.input_schema.get('required', [])
                        req_marker = " (required)" if required else ""
                        lines.append(f"  - {param_name} ({param_type}){req_marker}: {param_desc}")

        return "\n".join(lines)

    def clear(self):
        """Clear all registered tools."""
        self.tools.clear()
        logger.debug("Cleared all tools from registry")

    def __len__(self) -> int:
        return len(self.tools)

    def __repr__(self) -> str:
        return f"MCPToolRegistry(tools={len(self.tools)})"
