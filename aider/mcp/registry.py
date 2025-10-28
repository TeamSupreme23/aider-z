"""
MCP Server Registry.

Manages MCP server configurations, including loading from YAML files,
environment variable substitution, and server discovery.
"""

import os
import re
import logging
from pathlib import Path
from typing import Dict, List, Optional, Any

import yaml

from .exceptions import MCPConfigurationError, MCPServerNotFoundError


logger = logging.getLogger(__name__)


class MCPRegistry:
    """
    Registry for MCP server configurations.

    Handles:
    - Loading configurations from YAML files
    - Environment variable substitution
    - Server registration and lookup
    - Configuration file discovery
    """

    def __init__(self, config_path: Optional[str] = None):
        """
        Initialize the MCP registry.

        Args:
            config_path: Optional path to configuration file.
                        If None, will search standard locations.
        """
        self.config_path = config_path
        self.servers: Dict[str, Dict[str, Any]] = {}
        self.tool_settings: Dict[str, Any] = {}

        # Load configuration
        self._load_configuration()

    def _find_config_file(self) -> Optional[Path]:
        """
        Find MCP configuration file in standard locations.

        Search order:
        1. Explicitly provided config_path
        2. ./.aider.mcp.yaml (project-local)
        3. ~/.aider.mcp.yaml (user-global)

        Returns:
            Path to config file, or None if not found
        """
        if self.config_path:
            path = Path(self.config_path)
            if path.exists():
                return path
            else:
                logger.warning(f"Specified config file not found: {self.config_path}")
                return None

        # Check project-local config
        project_config = Path(".aider.mcp.yaml")
        if project_config.exists():
            logger.info(f"Using project config: {project_config}")
            return project_config

        # Check user-global config
        home_config = Path.home() / ".aider.mcp.yaml"
        if home_config.exists():
            logger.info(f"Using user config: {home_config}")
            return home_config

        logger.info("No MCP config file found")
        return None

    def _load_configuration(self):
        """Load configuration from YAML file."""
        config_file = self._find_config_file()

        if not config_file:
            logger.info("No MCP configuration loaded - using defaults")
            self._set_defaults()
            return

        try:
            with open(config_file, 'r') as f:
                config = yaml.safe_load(f)

            if not config:
                logger.warning(f"Empty config file: {config_file}")
                self._set_defaults()
                return

            # Load servers
            if 'mcp_servers' in config:
                self.servers = config['mcp_servers']
                logger.info(f"Loaded {len(self.servers)} MCP server configurations")

            # Load tool settings
            if 'tool_settings' in config:
                self.tool_settings = config['tool_settings']
            else:
                self._set_default_tool_settings()

            # Substitute environment variables
            self._substitute_env_vars()

        except yaml.YAMLError as e:
            raise MCPConfigurationError(f"Invalid YAML in config file: {e}")
        except Exception as e:
            raise MCPConfigurationError(f"Error loading config: {e}")

    def _set_defaults(self):
        """Set default configuration."""
        self.servers = {}
        self._set_default_tool_settings()

    def _set_default_tool_settings(self):
        """Set default tool settings."""
        self.tool_settings = {
            'auto_discover': True,
            'timeout': 30,
            'retry_attempts': 3,
        }

    def _substitute_env_vars(self):
        """
        Substitute environment variables in server configurations.

        Supports:
        - ${VAR_NAME} syntax
        - Nested substitution in strings
        """
        for server_name, config in self.servers.items():
            if 'env' in config and isinstance(config['env'], dict):
                for key, value in config['env'].items():
                    if isinstance(value, str):
                        # Replace ${VAR_NAME} with actual env var value
                        config['env'][key] = self._expand_env_var(value)

    def _expand_env_var(self, value: str) -> str:
        """
        Expand environment variables in a string.

        Args:
            value: String possibly containing ${VAR_NAME} patterns

        Returns:
            String with environment variables expanded
        """
        # Pattern to match ${VAR_NAME}
        pattern = r'\$\{([^}]+)\}'

        def replace_var(match):
            var_name = match.group(1)
            env_value = os.getenv(var_name)
            if env_value is None:
                logger.warning(
                    f"Environment variable '{var_name}' not set, "
                    f"leaving as ${{{var_name}}}"
                )
                return match.group(0)  # Keep original ${VAR_NAME}
            return env_value

        return re.sub(pattern, replace_var, value)

    def get_server_config(self, server_name: str) -> Optional[Dict[str, Any]]:
        """
        Get configuration for a specific server.

        Args:
            server_name: Name of the MCP server

        Returns:
            Server configuration dict, or None if not found
        """
        return self.servers.get(server_name)

    def list_servers(self) -> List[str]:
        """
        List all registered server names.

        Returns:
            List of server names
        """
        return list(self.servers.keys())

    def list_enabled_servers(self) -> List[str]:
        """
        List all enabled server names.

        Returns:
            List of enabled server names
        """
        return [
            name for name, config in self.servers.items()
            if config.get('enabled', True)
        ]

    def register_server(self, server_name: str, config: Dict[str, Any]):
        """
        Register a new MCP server or update existing one.

        Args:
            server_name: Name of the server
            config: Server configuration dict
        """
        self.servers[server_name] = config
        logger.info(f"Registered MCP server: {server_name}")

    def unregister_server(self, server_name: str):
        """
        Unregister an MCP server.

        Args:
            server_name: Name of the server to remove

        Raises:
            MCPServerNotFoundError: If server doesn't exist
        """
        if server_name not in self.servers:
            raise MCPServerNotFoundError(server_name)

        del self.servers[server_name]
        logger.info(f"Unregistered MCP server: {server_name}")

    def is_server_enabled(self, server_name: str) -> bool:
        """
        Check if a server is enabled.

        Args:
            server_name: Name of the server

        Returns:
            True if server exists and is enabled
        """
        config = self.get_server_config(server_name)
        if not config:
            return False
        return config.get('enabled', True)

    def get_auto_connect_servers(self) -> List[str]:
        """
        Get list of servers configured for auto-connect.

        Returns:
            List of server names that should auto-connect
        """
        return [
            name for name, config in self.servers.items()
            if config.get('enabled', True) and config.get('auto_connect', False)
        ]

    def get_tool_settings(self) -> Dict[str, Any]:
        """
        Get tool settings configuration.

        Returns:
            Tool settings dict
        """
        return self.tool_settings.copy()

    def save_configuration(self, path: Optional[str] = None):
        """
        Save current configuration to YAML file.

        Args:
            path: Optional path to save to. If None, uses current config_path
                  or ~/.aider.mcp.yaml
        """
        if path:
            save_path = Path(path)
        elif self.config_path:
            save_path = Path(self.config_path)
        else:
            save_path = Path.home() / ".aider.mcp.yaml"

        config = {
            'mcp_servers': self.servers,
            'tool_settings': self.tool_settings,
        }

        # Create parent directories if needed
        save_path.parent.mkdir(parents=True, exist_ok=True)

        with open(save_path, 'w') as f:
            yaml.dump(config, f, default_flow_style=False, sort_keys=False)

        logger.info(f"Saved MCP configuration to: {save_path}")

    def validate_server_config(self, config: Dict[str, Any]) -> bool:
        """
        Validate a server configuration.

        Args:
            config: Server configuration to validate

        Returns:
            True if valid

        Raises:
            MCPConfigurationError: If configuration is invalid
        """
        required_fields = ['transport', 'command']

        for field in required_fields:
            if field not in config:
                raise MCPConfigurationError(
                    f"Server configuration missing required field: {field}"
                )

        # Validate transport type
        valid_transports = ['stdio', 'sse', 'http']
        if config['transport'] not in valid_transports:
            raise MCPConfigurationError(
                f"Invalid transport type: {config['transport']}. "
                f"Must be one of: {', '.join(valid_transports)}"
            )

        return True
