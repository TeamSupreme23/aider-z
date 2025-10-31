"""
MCP Server Installer
Enables single-command installation of MCP servers
"""

import os
import subprocess
import logging
from pathlib import Path
from typing import Dict, Any, Optional, List

try:
    import requests
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False

from .registry import MCPRegistry

logger = logging.getLogger(__name__)


class MCPInstaller:
    """
    Handles automatic installation and configuration of MCP servers

    Supports:
    - Installing from MCP registry
    - Auto-detecting server types (npm, Python, etc.)
    - Updating configuration automatically
    - Managing dependencies
    """

    # Official MCP registry
    REGISTRY_URL = "https://raw.githubusercontent.com/modelcontextprotocol/servers/main/registry.json"

    def __init__(self, registry: MCPRegistry):
        """
        Initialize installer

        Args:
            registry: MCPRegistry instance to update
        """
        self.registry = registry
        self.available_servers = {}
        self.load_registry()

    def load_registry(self):
        """Load available MCP servers from registry"""
        if HAS_REQUESTS:
            try:
                # Try official registry first
                response = requests.get(self.REGISTRY_URL, timeout=5)
                if response.status_code == 200:
                    self.available_servers = response.json()
                    logger.info(
                        f"Loaded {len(self.available_servers)} servers "
                        f"from MCP registry"
                    )
                    return
            except Exception as e:
                logger.warning(f"Could not load official registry: {e}")

        # Fallback to hardcoded popular servers
        self.available_servers = self._get_default_servers()
        logger.info("Using default server list")

    def _detect_package_type(self, server_name: str) -> tuple:
        """
        Auto-detect if a package is npm or Python-based

        Priority:
        1. Check heuristics for known MCP server patterns (highest priority)
        2. Check if exists in npm/PyPI registries
        3. Default based on naming patterns

        Returns:
            Tuple of (package_type, package_info)
        """
        # FIRST: Check if it looks like a Python MCP server (highest priority)
        # This catches known MCP servers that might have npm name collisions
        python_indicators = [
            'mcp-server-' in server_name.lower(),
            server_name.lower().endswith('-mcp'),
            'serena' in server_name.lower(),  # Known Python MCP servers
            'memory' in server_name.lower() and 'bank' not in server_name.lower(),
        ]

        if any(python_indicators):
            logger.info(f"Package name matches Python MCP pattern, using uvx")
            return 'uvx', {
                'command': 'uvx',
                'package': server_name,
                'args': []
            }

        # SECOND: Check registries
        npm_exists = self._check_npm_package(server_name)
        python_exists = self._check_python_package(server_name)

        if npm_exists and not python_exists:
            return 'npm', {
                'command': 'npx',
                'package': server_name,
                'args': ['-y', server_name]
            }
        elif python_exists and not npm_exists:
            return 'uvx', {
                'command': 'uvx',
                'package': server_name,
                'args': []
            }
        elif npm_exists and python_exists:
            # Both exist - prefer npm for generic packages
            logger.info(f"Package exists in both npm and Python, defaulting to npm")
            return 'npm', {
                'command': 'npx',
                'package': server_name,
                'args': ['-y', server_name]
            }
        else:
            # Neither found - default to npm
            logger.info(f"Package not found in registries, defaulting to npm")
            return 'npm', {
                'command': 'npx',
                'package': server_name,
                'args': ['-y', server_name]
            }

    def _check_npm_package(self, package_name: str) -> bool:
        """Check if an npm package exists"""
        try:
            result = subprocess.run(
                ['npm', 'view', package_name, 'name'],
                capture_output=True,
                text=True,
                timeout=10
            )
            return result.returncode == 0
        except Exception as e:
            logger.debug(f"Error checking npm package: {e}")
            return False

    def _find_github_repo(self, package_name: str) -> Optional[str]:
        """
        Try to find the GitHub repository for an MCP server

        Returns org/repo or None
        """
        if not HAS_REQUESTS:
            return None

        # Common GitHub search patterns for MCP servers
        search_patterns = [
            f"{package_name}",  # Exact name
            f"mcp-{package_name}",
            f"{package_name}-mcp",
            f"mcp-server-{package_name}",
        ]

        for pattern in search_patterns:
            try:
                # Search GitHub for MCP server repositories
                response = requests.get(
                    f"https://api.github.com/search/repositories",
                    params={
                        'q': f'{pattern} mcp server in:name,description',
                        'sort': 'stars',
                        'order': 'desc'
                    },
                    timeout=5,
                    headers={'Accept': 'application/vnd.github.v3+json'}
                )

                if response.status_code == 200:
                    data = response.json()
                    if data.get('items'):
                        # Return the most starred result
                        repo = data['items'][0]
                        full_name = repo['full_name']  # org/repo
                        logger.info(f"Found GitHub repo for {package_name}: {full_name}")
                        return full_name

            except Exception as e:
                logger.debug(f"GitHub search error for {pattern}: {e}")

        return None

    def _get_mcp_subcommand(self, package_name: str) -> Optional[str]:
        """
        Determine if an MCP server needs a subcommand

        Some MCP servers require subcommands like 'start-mcp-server'
        """
        # Known MCP servers that need subcommands
        subcommand_map = {
            'serena': 'start-mcp-server',
            # Add more as discovered
        }

        return subcommand_map.get(package_name.lower())

    def _get_mcp_default_args(self, package_name: str) -> List[str]:
        """
        Get default arguments for specific MCP servers

        Some MCP servers need specific arguments to work properly
        """
        # Known MCP servers that need default arguments
        if package_name.lower() == 'serena':
            # Serena needs --project to specify the working directory
            # Use $PWD as placeholder - will be resolved at runtime
            return ['--project', '${PWD}']

        return []

    def _check_python_package(self, package_name: str) -> bool:
        """Check if a Python package exists on PyPI"""
        if not HAS_REQUESTS:
            return False

        try:
            # Check PyPI
            response = requests.get(
                f"https://pypi.org/pypi/{package_name}/json",
                timeout=5
            )
            if response.status_code == 200:
                return True

            # Also check common GitHub patterns for uvx packages
            # Many MCP servers use: github.com/org/package-name
            if '-' in package_name or '/' in package_name:
                return True  # Likely a GitHub-based uvx package

            return False
        except Exception as e:
            logger.debug(f"Error checking Python package: {e}")
            return False

    def _get_default_servers(self) -> Dict[str, Any]:
        """Hardcoded list of popular MCP servers"""
        return {
            "context7": {
                "name": "Context7",
                "description": "Get version-specific code examples and documentation",
                "type": "npm",
                "package": "@upstash/context7-mcp",
                "transport": "stdio",
                "command": "npx",
                "requires_api_key": False,
                "env_var": "CONTEXT7_API_KEY",
                "docs": "https://context7.com/docs"
            },
            "filesystem": {
                "name": "Filesystem",
                "description": "Access local filesystem",
                "type": "npm",
                "package": "@modelcontextprotocol/server-filesystem",
                "transport": "stdio",
                "command": "npx",
                "requires_api_key": False,
                "docs": "https://github.com/modelcontextprotocol/servers"
            },
            "github": {
                "name": "GitHub",
                "description": "Interact with GitHub repositories",
                "type": "npm",
                "package": "@modelcontextprotocol/server-github",
                "transport": "stdio",
                "command": "npx",
                "requires_api_key": True,
                "env_var": "GITHUB_TOKEN",
                "docs": "https://github.com/modelcontextprotocol/servers"
            },
            "slack": {
                "name": "Slack",
                "description": "Interact with Slack workspace",
                "type": "npm",
                "package": "@modelcontextprotocol/server-slack",
                "transport": "stdio",
                "command": "npx",
                "requires_api_key": True,
                "env_var": "SLACK_TOKEN",
                "docs": "https://github.com/modelcontextprotocol/servers"
            },
            "postgresql": {
                "name": "PostgreSQL",
                "description": "Query PostgreSQL databases",
                "type": "npm",
                "package": "@modelcontextprotocol/server-postgres",
                "transport": "stdio",
                "command": "npx",
                "requires_api_key": False,
                "docs": "https://github.com/modelcontextprotocol/servers"
            },
            "brave-search": {
                "name": "Brave Search",
                "description": "Web search using Brave Search API",
                "type": "npm",
                "package": "@modelcontextprotocol/server-brave-search",
                "transport": "stdio",
                "command": "npx",
                "requires_api_key": True,
                "env_var": "BRAVE_API_KEY",
                "docs": "https://github.com/modelcontextprotocol/servers"
            },
            "puppeteer": {
                "name": "Puppeteer",
                "description": "Browser automation for web scraping",
                "type": "npm",
                "package": "@modelcontextprotocol/server-puppeteer",
                "transport": "stdio",
                "command": "npx",
                "requires_api_key": False,
                "docs": "https://github.com/modelcontextprotocol/servers"
            },
            "memory": {
                "name": "Memory",
                "description": "Knowledge graph for persistent memory",
                "type": "npm",
                "package": "@modelcontextprotocol/server-memory",
                "transport": "stdio",
                "command": "npx",
                "requires_api_key": False,
                "docs": "https://github.com/modelcontextprotocol/servers"
            }
        }

    def install(
        self,
        server_name: str,
        api_key: Optional[str] = None,
        auto_connect: bool = True,
        additional_args: Optional[List[str]] = None
    ) -> bool:
        """
        Install and configure an MCP server

        Args:
            server_name: Name from registry OR npm package name (e.g., 'context7' or 'mcp-server-serena')
            api_key: Optional API key
            auto_connect: Whether to auto-connect on startup
            additional_args: Optional additional command arguments

        Returns:
            True if installation successful

        Examples:
            # From registry
            installer.install('context7')

            # Direct npm package
            installer.install('mcp-server-serena')
            installer.install('@anthropic/mcp-server-custom')
        """
        logger.info(f"Installing MCP server: {server_name}")

        # Check if already installed - if so, reinstall (remove and install)
        if self.registry.get_server_config(server_name):
            logger.info(f"Server {server_name} already configured, reinstalling...")
            print(f"🔄 Server '{server_name}' is already installed")
            print(f"   Removing old version and reinstalling...")

            # Uninstall old version
            del self.registry.servers[server_name]
        # Get server info from registry (if exists)
        server_info = self.available_servers.get(server_name)

        # If not in registry, auto-detect package type
        if not server_info:
            logger.info(f"Server not in registry, auto-detecting package type: {server_name}")
            print(f"📦 Installing MCP server: {server_name}")
            print(f"   (Not in registry, auto-detecting package type...)")

            # Auto-detect package type
            package_type, package_info = self._detect_package_type(server_name)

            # Create basic server info
            server_info = {
                'name': server_name,
                'description': f'MCP server: {server_name}',
                'type': package_type,
                'package': package_info['package'],
                'transport': 'stdio',
                'command': package_info['command'],
                'args': package_info.get('args', []),
                'requires_api_key': bool(api_key),
                'docs': None
            }

            print(f"   ✓ Detected as {package_type} package")
        else:
            print(f"📦 Installing {server_info['name']}...")
            print(f"   {server_info['description']}")

        # Install dependencies
        if not self._install_dependencies(server_info):
            return False

        # Check for API key
        if server_info.get('requires_api_key'):
            if not api_key:
                api_key = self._get_api_key(server_info)

            if not api_key:
                print(f"⚠️  Warning: No API key provided")
                print(f"   Set {server_info['env_var']} environment variable")
                print(f"   Or provide with: /mcp-install {server_name} --api-key YOUR_KEY")

        # Create configuration
        config = self._create_config(server_info, api_key, auto_connect, additional_args)

        # Add to registry
        self.registry.register_server(server_name, config)

        # Save to config file
        self._save_config()

        print(f" {server_info['name']} installed successfully!")

        if server_info.get('requires_api_key') and not api_key:
            print(f"⚠️  Remember to set {server_info['env_var']}")

        print(f"📦 Docs: {server_info.get('docs', 'N/A')}")

        return True

    def _install_dependencies(self, server_info: Dict[str, Any]) -> bool:
        """Install server dependencies"""
        server_type = server_info.get('type', 'npm')
        package = server_info.get('package')

        print(f"📦 Installing dependencies ({server_type})...")

        try:
            if server_type == 'npm':
                # NPM packages don't need pre-installation
                # npx will handle it
                print(f"   Using npx (auto-installed on first run)")
                return True

            elif server_type == 'uvx':
                # uvx packages don't need pre-installation
                # uvx will handle it automatically
                print(f"   Using uvx (auto-installed on first run)")

                # Check if uv is installed
                result = subprocess.run(
                    ['which', 'uvx'],
                    capture_output=True,
                    text=True
                )

                if result.returncode != 0:
                    print(f"   ⚠️  Warning: uvx not found in PATH")
                    print(f"   Install uv: https://docs.astral.sh/uv/getting-started/installation/")
                    print(f"   Or run: curl -LsSf https://astral.sh/uv/install.sh | sh")

                return True

            elif server_type == 'python':
                # Install Python package
                cmd = ['pip', 'install', package]
                result = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True
                )

                if result.returncode != 0:
                    print(f"L Installation failed:")
                    print(result.stderr)
                    return False

                print(f"    {package} installed")
                return True

            elif server_type == 'binary':
                # Binary needs to be downloaded
                print(f"   Please install manually: {package}")
                return False

            else:
                print(f"   Unknown type: {server_type}")
                return False

        except Exception as e:
            print(f"L Error installing dependencies: {e}")
            return False

    def _get_api_key(self, server_info: Dict[str, Any]) -> Optional[str]:
        """Try to get API key from environment"""
        env_var = server_info.get('env_var')
        if env_var:
            return os.getenv(env_var)
        return None

    def _create_config(
        self,
        server_info: Dict[str, Any],
        api_key: Optional[str],
        auto_connect: bool,
        additional_args: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """Create server configuration"""
        config = {
            'enabled': True,
            'transport': server_info.get('transport', 'stdio'),
            'auto_connect': auto_connect,
            'description': server_info.get('description', '')
        }

        # Set command and args based on server type
        server_type = server_info.get('type', 'npm')

        if server_type == 'npm':
            config['command'] = 'npx'
            args = ['-y', server_info['package']]
            if additional_args:
                args.extend(additional_args)
            config['args'] = args

        elif server_type == 'uvx':
            # uvx-based Python package
            config['command'] = 'uvx'
            package = server_info['package']

            # Try to find GitHub repo for known MCP servers
            github_repo = self._find_github_repo(package)

            if github_repo:
                # GitHub-based package
                repo_name = github_repo.split('/')[-1]

                # Check if it needs a subcommand (like 'start-mcp-server')
                subcommand = self._get_mcp_subcommand(package)

                if subcommand:
                    args = ['--from', f'git+https://github.com/{github_repo}', repo_name, subcommand]
                else:
                    args = ['--from', f'git+https://github.com/{github_repo}', repo_name]
            elif package.startswith('git+') or '/' in package:
                # Already formatted as git URL or org/repo
                repo_name = package.split('/')[-1]
                args = ['--from', package, repo_name]
            else:
                # Regular PyPI package
                args = [package]

            # Add default args for this MCP server (if any)
            default_args = self._get_mcp_default_args(package)
            if default_args:
                args.extend(default_args)

            # Add user-provided additional args
            if additional_args:
                args.extend(additional_args)

            config['args'] = args

        else:
            # Generic command from server_info
            config['command'] = server_info.get('command')
            args = server_info.get('args', [])
            if additional_args:
                args.extend(additional_args)
            config['args'] = args

        # Set environment variables
        if api_key and server_info.get('env_var'):
            config['env'] = {
                server_info['env_var']: api_key
            }
        elif server_info.get('env_var'):
            config['env'] = {
                server_info['env_var']: f"${{{server_info['env_var']}}}"
            }

        return config

    def _save_config(self):
        """Save updated configuration to file"""
        config_file = self.registry._find_config_file()

        if not config_file:
            # Create default config file
            config_file = Path.cwd() / '.aider.mcp.yaml'

        import yaml

        # Load existing config
        if config_file.exists():
            with open(config_file, 'r') as f:
                full_config = yaml.safe_load(f) or {}
        else:
            full_config = {}

        # Update servers section
        if 'mcp_servers' not in full_config:
            full_config['mcp_servers'] = {}

        full_config['mcp_servers'].update(self.registry.servers)

        # Save
        config_file.parent.mkdir(parents=True, exist_ok=True)
        with open(config_file, 'w') as f:
            yaml.dump(full_config, f, default_flow_style=False)

        logger.info(f"Configuration saved to {config_file}")
        print(f"   Configuration saved to {config_file}")

    def list_available(self) -> List[Dict[str, Any]]:
        """List all available MCP servers"""
        servers = []

        for name, info in self.available_servers.items():
            installed = bool(self.registry.get_server_config(name))

            servers.append({
                'name': name,
                'title': info.get('name', name),
                'description': info.get('description', ''),
                'type': info.get('type', 'unknown'),
                'requires_api_key': info.get('requires_api_key', False),
                'installed': installed,
                'docs': info.get('docs', '')
            })

        return servers

    def uninstall(self, server_name: str) -> bool:
        """Uninstall an MCP server"""
        if server_name not in self.registry.servers:
            logger.warning(f"Server not installed: {server_name}")
            print(f"L Server '{server_name}' is not installed")
            return False

        print(f"📦  Uninstalling {server_name}...")

        # Remove from registry
        del self.registry.servers[server_name]

        # Save config
        self._save_config()

        print(f" {server_name} uninstalled")
        print(f"   Configuration removed from .aider.mcp.yaml")

        return True

    def discover(self) -> List[str]:
        """
        Auto-discover MCP servers

        Looks for:
        - Installed npm packages matching @*-mcp/server
        - Python packages matching mcp-server-*
        - Common MCP server binaries
        """
        discovered = []

        print("🔍 Discovering MCP servers...")

        # Check npm global packages
        try:
            result = subprocess.run(
                ['npm', 'list', '-g', '--depth=0'],
                capture_output=True,
                text=True,
                timeout=5
            )

            if result.returncode == 0:
                for line in result.stdout.split('\n'):
                    if '-mcp' in line or 'mcp-server' in line or 'context7' in line:
                        # Extract package name
                        if '@' in line:
                            parts = line.split('@')
                            if len(parts) >= 2:
                                pkg_name = '@' + parts[1].split('@')[0]
                                if pkg_name not in discovered:
                                    discovered.append(pkg_name)
                                    print(f"   Found: {pkg_name} (npm)")
        except Exception as e:
            logger.debug(f"NPM discovery failed: {e}")

        # Check Python packages
        try:
            result = subprocess.run(
                ['pip', 'list'],
                capture_output=True,
                text=True,
                timeout=5
            )

            if result.returncode == 0:
                for line in result.stdout.split('\n'):
                    if 'mcp-server' in line.lower():
                        pkg_name = line.split()[0]
                        if pkg_name not in discovered:
                            discovered.append(pkg_name)
                            print(f"   Found: {pkg_name} (Python)")
        except Exception as e:
            logger.debug(f"Python discovery failed: {e}")

        if not discovered:
            print("   No MCP servers found")
        else:
            print(f"\n Discovered {len(discovered)} MCP servers")

        return discovered
