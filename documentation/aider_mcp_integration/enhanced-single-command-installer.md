# Single-Command MCP Tool Installation

This enhancement adds a **one-command installer** for MCP tools, eliminating manual YAML editing.

## The Goal

```bash
# From terminal
aider --mcp-install serena

# From within Aider
> /mcp-install context7

# Auto-detect and install
> /mcp-discover
```

## Implementation

### File: `aider/mcp/installer.py`

```python
"""
MCP Server Installer
Enables single-command installation of MCP servers
"""

import os
import json
import subprocess
import logging
from pathlib import Path
from typing import Dict, Any, Optional, List
import requests

from .registry import MCPRegistry
from .exceptions import MCPConfigurationError

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
    
    # Alternative: Community registry
    COMMUNITY_REGISTRY = "https://mcpservers.org/api/registry.json"
    
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
    
    def _get_default_servers(self) -> Dict[str, Any]:
        """Hardcoded list of popular MCP servers"""
        return {
            "serena": {
                "name": "Serena",
                "description": "Search across library documentation",
                "type": "npm",
                "package": "@serena-mcp/server",
                "transport": "stdio",
                "command": "npx",
                "requires_api_key": True,
                "env_var": "SERENA_API_KEY",
                "docs": "https://serena.ai/docs"
            },
            "context7": {
                "name": "Context7",
                "description": "Get version-specific code examples",
                "type": "npm",
                "package": "context7-server",
                "transport": "stdio",
                "command": "context7-server",
                "requires_api_key": True,
                "env_var": "CONTEXT7_API_KEY",
                "docs": "https://context7.com/docs"
            },
            "filesystem": {
                "name": "Filesystem",
                "description": "Access local filesystem",
                "type": "python",
                "package": "mcp-server-filesystem",
                "transport": "stdio",
                "command": "python",
                "args": ["-m", "mcp_server_filesystem"],
                "requires_api_key": False,
                "docs": "https://github.com/modelcontextprotocol/servers"
            },
            "github": {
                "name": "GitHub",
                "description": "Interact with GitHub repositories",
                "type": "python",
                "package": "mcp-server-github",
                "transport": "stdio",
                "command": "python",
                "args": ["-m", "mcp_server_github"],
                "requires_api_key": True,
                "env_var": "GITHUB_TOKEN",
                "docs": "https://github.com/modelcontextprotocol/servers"
            },
            "slack": {
                "name": "Slack",
                "description": "Interact with Slack workspace",
                "type": "python",
                "package": "mcp-server-slack",
                "transport": "stdio",
                "command": "python",
                "args": ["-m", "mcp_server_slack"],
                "requires_api_key": True,
                "env_var": "SLACK_TOKEN",
                "docs": "https://github.com/modelcontextprotocol/servers"
            },
            "postgresql": {
                "name": "PostgreSQL",
                "description": "Query PostgreSQL databases",
                "type": "python",
                "package": "mcp-server-postgres",
                "transport": "stdio",
                "command": "python",
                "args": ["-m", "mcp_server_postgres"],
                "requires_api_key": False,
                "docs": "https://github.com/modelcontextprotocol/servers"
            }
        }
    
    def install(
        self, 
        server_name: str,
        api_key: Optional[str] = None,
        auto_connect: bool = True
    ) -> bool:
        """
        Install and configure an MCP server
        
        Args:
            server_name: Name of the server to install
            api_key: Optional API key
            auto_connect: Whether to auto-connect on startup
            
        Returns:
            True if installation successful
        """
        logger.info(f"Installing MCP server: {server_name}")
        
        # Check if already installed
        if self.registry.get_server_config(server_name):
            logger.info(f"Server {server_name} already configured")
            return True
        
        # Get server info
        server_info = self.available_servers.get(server_name)
        if not server_info:
            logger.error(f"Unknown server: {server_name}")
            print(f"❌ Server '{server_name}' not found in registry")
            print(f"Available servers: {', '.join(self.available_servers.keys())}")
            return False
        
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
                print(f"⚠️  Warning: No API key provided")
                print(f"   Set {server_info['env_var']} environment variable")
                print(f"   Or provide with: /mcp-install {server_name} --api-key YOUR_KEY")
        
        # Create configuration
        config = self._create_config(server_info, api_key, auto_connect)
        
        # Add to registry
        self.registry.register_server(server_name, config)
        
        # Save to config file
        self._save_config()
        
        print(f"✅ {server_info['name']} installed successfully!")
        
        if server_info.get('requires_api_key') and not api_key:
            print(f"⚠️  Remember to set {server_info['env_var']}")
        
        print(f"📖 Docs: {server_info.get('docs', 'N/A')}")
        
        return True
    
    def _install_dependencies(self, server_info: Dict[str, Any]) -> bool:
        """Install server dependencies"""
        server_type = server_info.get('type', 'npm')
        package = server_info.get('package')
        
        print(f"📥 Installing dependencies ({server_type})...")
        
        try:
            if server_type == 'npm':
                # NPM packages don't need pre-installation
                # npx will handle it
                print(f"   Using npx (auto-installed on first run)")
                return True
                
            elif server_type == 'python':
                # Install Python package
                cmd = ['pip', 'install', package, '--break-system-packages']
                result = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True
                )
                
                if result.returncode != 0:
                    print(f"❌ Installation failed:")
                    print(result.stderr)
                    return False
                
                print(f"   ✓ {package} installed")
                return True
                
            elif server_type == 'binary':
                # Binary needs to be downloaded
                print(f"   Please install manually: {package}")
                return False
                
            else:
                print(f"   Unknown type: {server_type}")
                return False
                
        except Exception as e:
            print(f"❌ Error installing dependencies: {e}")
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
        auto_connect: bool
    ) -> Dict[str, Any]:
        """Create server configuration"""
        config = {
            'enabled': True,
            'transport': server_info.get('transport', 'stdio'),
            'auto_connect': auto_connect,
            'description': server_info.get('description', '')
        }
        
        # Set command and args
        if server_info.get('type') == 'npm':
            config['command'] = 'npx'
            config['args'] = [server_info['package']]
        else:
            config['command'] = server_info.get('command')
            config['args'] = server_info.get('args', [])
        
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
            config_file = Path.home() / '.aider.mcp.yaml'
        
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
            return False
        
        print(f"🗑️  Uninstalling {server_name}...")
        
        # Remove from registry
        del self.registry.servers[server_name]
        
        # Save config
        self._save_config()
        
        print(f"✅ {server_name} uninstalled")
        
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
                    if '-mcp' in line or 'mcp-server' in line:
                        # Extract package name
                        # Example: "├── @serena-mcp/server@1.0.0"
                        parts = line.split('@')
                        if len(parts) >= 2:
                            pkg_name = parts[1].split('@')[0]
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
            print(f"\n✅ Discovered {len(discovered)} MCP servers")
        
        return discovered
```

### Enhanced Commands in `aider/commands.py`

```python
class Commands:
    def __init__(self, io, coder):
        self.io = io
        self.coder = coder
        
        # Initialize MCP installer
        if hasattr(coder, 'mcp_client') and coder.mcp_client:
            from aider.mcp.installer import MCPInstaller
            from aider.mcp.registry import MCPRegistry
            
            registry = MCPRegistry(coder.mcp_config)
            self.mcp_installer = MCPInstaller(registry)
        else:
            self.mcp_installer = None
    
    def cmd_mcp_install(self, args):
        """Install an MCP server with a single command
        
        Usage:
          /mcp-install serena
          /mcp-install context7 --api-key sk-xxxxx
          /mcp-install github --no-auto-connect
        
        Examples:
          /mcp-install serena              # Install Serena
          /mcp-install context7 --api-key KEY  # With API key
        """
        if not self.mcp_installer:
            self.io.tool_error("MCP not enabled. Use --enable-mcp")
            return
        
        # Parse arguments
        parts = args.split()
        if not parts:
            self.io.tool_error("Usage: /mcp-install <server-name> [--api-key KEY]")
            return
        
        server_name = parts[0]
        api_key = None
        auto_connect = True
        
        # Parse options
        i = 1
        while i < len(parts):
            if parts[i] == '--api-key' and i + 1 < len(parts):
                api_key = parts[i + 1]
                i += 2
            elif parts[i] == '--no-auto-connect':
                auto_connect = False
                i += 1
            else:
                i += 1
        
        # Install
        success = self.mcp_installer.install(
            server_name,
            api_key=api_key,
            auto_connect=auto_connect
        )
        
        if success and auto_connect:
            # Auto-connect
            self.io.tool_output(f"\n🔗 Connecting to {server_name}...")
            
            registry = MCPRegistry(self.coder.mcp_config)
            config = registry.get_server_config(server_name)
            
            try:
                import asyncio
                asyncio.run(
                    self.coder.mcp_client.connect_server(server_name, config)
                )
                
                # Refresh tools
                self.coder.mcp_tools = asyncio.run(
                    self.coder.mcp_client.list_tools()
                )
                
                self.io.tool_output(f"✅ Connected! Ready to use.")
                
            except Exception as e:
                self.io.tool_error(f"Connection failed: {e}")
    
    def cmd_mcp_available(self, args):
        """List available MCP servers that can be installed
        
        Usage:
          /mcp-available              # List all
          /mcp-available --installed  # Show only installed
        """
        if not self.mcp_installer:
            self.io.tool_error("MCP not enabled")
            return
        
        show_installed = '--installed' in args
        
        servers = self.mcp_installer.list_available()
        
        if show_installed:
            servers = [s for s in servers if s['installed']]
        
        self.io.tool_output("Available MCP Servers:\n")
        
        for server in servers:
            status = "✓" if server['installed'] else " "
            api_key_marker = "🔑" if server['requires_api_key'] else ""
            
            self.io.tool_output(
                f"  [{status}] {server['title']} {api_key_marker}\n"
                f"      {server['description']}\n"
                f"      Install: /mcp-install {server['name']}"
            )
            
            if server.get('docs'):
                self.io.tool_output(f"      Docs: {server['docs']}")
            
            self.io.tool_output("")
    
    def cmd_mcp_discover(self, args):
        """Auto-discover installed MCP servers
        
        Usage:
          /mcp-discover
        """
        if not self.mcp_installer:
            self.io.tool_error("MCP not enabled")
            return
        
        discovered = self.mcp_installer.discover()
        
        if discovered:
            self.io.tool_output(
                f"\nFound {len(discovered)} MCP servers. "
                f"Use /mcp-install to configure them."
            )
    
    def cmd_mcp_uninstall(self, args):
        """Uninstall an MCP server
        
        Usage:
          /mcp-uninstall serena
        """
        if not self.mcp_installer:
            self.io.tool_error("MCP not enabled")
            return
        
        server_name = args.strip()
        if not server_name:
            self.io.tool_error("Usage: /mcp-uninstall <server-name>")
            return
        
        success = self.mcp_installer.uninstall(server_name)
        
        if success:
            # Disconnect if connected
            if self.coder.mcp_client.is_connected(server_name):
                import asyncio
                asyncio.run(
                    self.coder.mcp_client.disconnect_server(server_name)
                )
                
                self.io.tool_output(f"Disconnected from {server_name}")
```

## Usage Examples

### 1. Install from Aider Command Line

```bash
# Install and auto-connect
aider --enable-mcp --mcp-install serena

# Install without connecting
aider --enable-mcp --mcp-install serena --no-auto-connect
```

### 2. Install from Within Aider

```bash
# Start Aider with MCP enabled
aider --enable-mcp

# Inside Aider session:
> /mcp-available
Available MCP Servers:

  [ ] Serena 🔑
      Search across library documentation
      Install: /mcp-install serena

  [ ] Context7 🔑
      Get version-specific code examples
      Install: /mcp-install context7

  [ ] GitHub 🔑
      Interact with GitHub repositories
      Install: /mcp-install github

# Install Serena
> /mcp-install serena
📦 Installing Serena...
   Search across library documentation
📥 Installing dependencies (npm)...
   Using npx (auto-installed on first run)
✅ Serena installed successfully!
⚠️  Remember to set SERENA_API_KEY
📖 Docs: https://serena.ai/docs

🔗 Connecting to serena...
✅ Connected! Ready to use.

# Now use it
> /mcp-list
Connected MCP Servers:
  ✓ serena (3 tools)

> Can you search for React useEffect documentation?
[Aider uses Serena automatically...]
```

### 3. Discover Existing MCP Servers

```bash
> /mcp-discover
🔍 Discovering MCP servers...
   Found: @serena-mcp/server (npm)
   Found: mcp-server-github (Python)

✅ Discovered 2 MCP servers

> /mcp-install github
📦 Installing GitHub...
...
```

### 4. Install with API Key

```bash
> /mcp-install serena --api-key sk-xxxxx
📦 Installing Serena...
✅ Serena installed successfully!
🔗 Connecting to serena...
✅ Connected! Ready to use.
```

### 5. List Installed Servers

```bash
> /mcp-available --installed
Available MCP Servers:

  [✓] Serena 🔑
      Search across library documentation
      Install: /mcp-install serena
```

## Terminal Command Support

Add to `aider/args.py`:

```python
parser.add_argument(
    '--mcp-install',
    type=str,
    metavar='SERVER',
    help='Install MCP server and start Aider',
    env_var='AIDER_MCP_INSTALL'
)
```

Modify `aider/main.py`:

```python
def main(args=None):
    # ... existing code ...
    
    # Handle MCP installation from CLI
    if args.mcp_install:
        from aider.mcp.installer import MCPInstaller
        from aider.mcp.registry import MCPRegistry
        
        print(f"Installing MCP server: {args.mcp_install}")
        
        registry = MCPRegistry(args.mcp_config)
        installer = MCPInstaller(registry)
        
        success = installer.install(args.mcp_install, auto_connect=True)
        
        if not success:
            sys.exit(1)
        
        # Enable MCP for this session
        args.enable_mcp = True
    
    # ... rest of main ...
```

## Benefits

✅ **Single Command**: `/mcp-install serena` - that's it!
✅ **Auto-Configuration**: Creates YAML config automatically
✅ **Dependency Management**: Handles npm/Python packages
✅ **Discovery**: Finds already-installed MCP servers
✅ **Registry-Based**: Uses official MCP server registry
✅ **Smart Defaults**: Sensible configuration out of the box

## Complete Workflow

```bash
# 1. Start Aider with MCP
aider --enable-mcp

# 2. See what's available
> /mcp-available

# 3. Install what you need (one command!)
> /mcp-install serena
> /mcp-install context7
> /mcp-install github

# 4. Use them immediately
> Can you search for React documentation?
[Tools work automatically]

# 5. Manage later
> /mcp-list
> /mcp-uninstall serena
```

## Summary

**Yes!** With this enhancement, you get **true single-command installation**:

1. **From terminal**: `aider --mcp-install serena`
2. **From Aider**: `/mcp-install context7`
3. **Auto-discovery**: `/mcp-discover`

The installer:
- ✅ Downloads dependencies automatically
- ✅ Creates configuration automatically  
- ✅ Connects automatically
- ✅ No manual YAML editing needed
- ✅ Works with official MCP registry

This is **as easy as**: `/mcp-install <server-name>` 🚀
