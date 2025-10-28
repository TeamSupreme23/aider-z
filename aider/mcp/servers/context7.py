"""
Context7 MCP Server Connector.

Provides configuration and setup for the Context7 documentation server.
Context7 provides version-specific documentation and code examples
for software libraries.
"""

from typing import Dict, Any, Optional
from .base import BaseMCPServerConnector


class Context7Connector(BaseMCPServerConnector):
    """
    Connector for Context7 MCP server.

    Context7 provides:
    - Documentation search across libraries
    - Version-specific code examples
    - Library context retrieval
    """

    def __init__(self):
        """Initialize Context7 connector."""
        super().__init__()
        self.server_name = "context7"
        self.requires_api_key = False  # API key is optional!
        self.env_var = "CONTEXT7_API_KEY"
        self.transport = "stdio"
        self.command = "npx"
        self.args = ["-y", "@upstash/context7-mcp"]
        self.description = "Get version-specific documentation and code examples"

    def get_config(self, api_key: Optional[str] = None) -> Dict[str, Any]:
        """
        Get Context7 server configuration.

        Args:
            api_key: Optional Context7 API key

        Returns:
            Configuration dict for Context7
        """
        config = super().get_config(api_key)

        config.update({
            'command': self.command,
            'args': self.args,
            'description': self.description,
        })

        return config

    def get_api_key_instructions(self) -> str:
        """
        Get instructions for obtaining Context7 API key.

        Returns:
            Instructions string
        """
        return """
To use Context7:

1. Context7 works WITHOUT an API key!
   Just ensure Node.js is installed and npx is available.

2. (Optional) For higher rate limits and private repos:
   - Visit https://context7.com/dashboard to get an API key
   - Set the environment variable:
     export CONTEXT7_API_KEY="your-api-key-here"

3. Context7 will auto-install via npx, or you can pre-install:
   npm install -g @upstash/context7-mcp

For more information: https://github.com/upstash/context7
"""

    def get_tool_descriptions(self) -> Dict[str, str]:
        """
        Get expected Context7 tool descriptions.

        Returns:
            Dict mapping tool names to descriptions
        """
        return {
            'resolve-library-id': 'Resolve package/product names to Context7 library IDs',
            'get-library-docs': 'Fetch up-to-date documentation for a specific library',
        }
