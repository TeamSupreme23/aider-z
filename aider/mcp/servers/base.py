"""
Base MCP Server Connector.

Provides base class for server-specific connectors.
"""

import os
from typing import Dict, Any, Optional


class BaseMCPServerConnector:
    """
    Base class for MCP server-specific connectors.

    Server connectors provide configuration templates and
    server-specific logic for different MCP servers.
    """

    def __init__(self):
        """Initialize the connector."""
        self.server_name = "base"
        self.requires_api_key = False
        self.env_var = None
        self.transport = "stdio"

    def get_config(self, api_key: Optional[str] = None) -> Dict[str, Any]:
        """
        Get server configuration.

        Args:
            api_key: Optional API key

        Returns:
            Configuration dict suitable for MCPRegistry
        """
        config = {
            'enabled': True,
            'transport': self.transport,
            'auto_connect': True,
        }

        if self.requires_api_key:
            env = {}
            if api_key:
                env[self.env_var] = api_key
            elif self.env_var:
                # Use environment variable placeholder
                env[self.env_var] = f"${{{self.env_var}}}"
            config['env'] = env

        return config

    def validate_config(self, config: Dict[str, Any]) -> bool:
        """
        Validate server configuration.

        Args:
            config: Configuration to validate

        Returns:
            True if valid

        Raises:
            ValueError: If configuration is invalid
        """
        if self.requires_api_key:
            if 'env' not in config or self.env_var not in config['env']:
                raise ValueError(f"Missing required environment variable: {self.env_var}")

        return True

    def check_api_key(self) -> bool:
        """
        Check if API key is available in environment.

        Returns:
            True if API key is set
        """
        if not self.requires_api_key:
            return True

        return bool(os.getenv(self.env_var))

    def get_api_key_instructions(self) -> str:
        """
        Get instructions for obtaining API key.

        Returns:
            Instructions string
        """
        if not self.requires_api_key:
            return "No API key required"

        return f"Set {self.env_var} environment variable"
