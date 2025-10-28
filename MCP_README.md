# MCP Integration for Aider

This document describes how to use MCP (Model Context Protocol) tools with Aider.

## What is MCP?

MCP (Model Context Protocol) is a standardized protocol for connecting AI assistants to external tools and data sources. With MCP integration, Aider can:

- Access up-to-date documentation via Context7
- Search across multiple library documentation sources
- Get version-specific code examples
- Connect to any MCP-compatible server

## Quick Start

### 1. Install Dependencies

```bash
pip install mcp nest-asyncio
```

### 2. Install Context7 (for documentation access)

Context7 will be automatically installed via npx when first used. You can also pre-install it:

```bash
npm install -g @upstash/context7-mcp
```

**Note:** The configuration uses `npx -y @upstash/context7-mcp` which will automatically download and run the package on first use.

### 3. Set API Key

```bash
export CONTEXT7_API_KEY="your-api-key-here"
```

Get your API key from: https://context7.com/

### 4. Create Configuration File

Create `.aider.mcp.yaml` in your project directory or `~/.aider.mcp.yaml` globally:

```yaml
mcp_servers:
  context7:
    enabled: true
    transport: stdio
    command: "npx"
    args: ["-y", "@upstash/context7-mcp"]
    env:
      CONTEXT7_API_KEY: "${CONTEXT7_API_KEY}"
    auto_connect: true

tool_settings:
  auto_discover: true
  timeout: 30
  retry_attempts: 3
```

### 5. Start Aider with MCP

```bash
aider --enable-mcp
```

## Usage

Once MCP is enabled, the LLM can automatically use available tools:

```
> How do I use React hooks?

[Aider automatically uses Context7 to search documentation]
[Returns latest React hooks documentation and examples]
```

## Configuration

### Configuration File Locations

Aider searches for MCP configuration in this order:

1. `./.aider.mcp.yaml` (project-local)
2. `~/.aider.mcp.yaml` (user-global)
3. Custom path via `--mcp-config`

### Configuration Format

```yaml
mcp_servers:
  <server_name>:
    enabled: true|false          # Enable/disable this server
    transport: stdio|sse|http    # Transport type
    command: "command-to-run"    # Command for stdio transport
    args: ["--arg1", "--arg2"]   # Optional command arguments
    env:                         # Environment variables
      API_KEY: "${API_KEY}"      # Use ${} for env var substitution
    auto_connect: true|false     # Connect automatically on startup
    description: "Server description"

tool_settings:
  auto_discover: true            # Auto-discover tools on connect
  timeout: 30                    # Timeout in seconds
  retry_attempts: 3              # Number of retry attempts

ui:
  show_mcp_tools_in_help: true   # Show tools in help
  tool_call_notifications: true  # Notify on tool calls
```

## Available Servers

### Context7

**Purpose**: Documentation search and version-specific code examples

**Installation**:
```bash
# Auto-installed via npx, or pre-install with:
npm install -g @upstash/context7-mcp
export CONTEXT7_API_KEY="your-key"
```

**Tools**:
- `resolve-library-id`: Resolve package names to Context7 library IDs
- `get-library-docs`: Fetch up-to-date documentation for a library
- Supports version-specific documentation

**Configuration**:
```yaml
context7:
  enabled: true
  transport: stdio
  command: "npx"
  args: ["-y", "@upstash/context7-mcp"]
  env:
    CONTEXT7_API_KEY: "${CONTEXT7_API_KEY}"
  auto_connect: true
```

## Command-Line Options

```bash
# Enable MCP integration
aider --enable-mcp

# Use custom config file
aider --enable-mcp --mcp-config /path/to/config.yaml

# Disable MCP
aider --no-enable-mcp
```

## Troubleshooting

### "MCP dependencies not installed"

Install the required packages:
```bash
pip install mcp nest-asyncio
```

### "Failed to connect to MCP server"

1. Check that npx is available:
   ```bash
   which npx
   npx --version
   ```

2. Verify API key is set:
   ```bash
   echo $CONTEXT7_API_KEY
   ```

3. Check server configuration in `.aider.mcp.yaml`

### "No MCP config file found"

Create `.aider.mcp.yaml` in your project directory or home directory.

### Connection Timeout

Increase timeout in configuration:
```yaml
tool_settings:
  timeout: 60  # Increase from default 30 seconds
```

## Architecture

### Components

1. **MCPRegistry**: Manages server configurations (YAML loading, env var substitution)
2. **MCPClientManager**: Handles server connections and tool discovery
3. **MCPToolWrapper**: Adapts MCP tools to Aider/LiteLLM format
4. **Server Connectors**: Pre-configured templates for popular servers

### Flow

1. User starts Aider with `--enable-mcp`
2. MCPRegistry loads configuration from YAML
3. MCPClientManager connects to auto-connect servers
4. Tools are discovered and registered
5. Tools exposed to LLM in OpenAI function format
6. LLM can call tools automatically
7. Results formatted and added to conversation

## Adding Custom MCP Servers

Add any MCP-compatible server to your configuration:

```yaml
mcp_servers:
  my_custom_server:
    enabled: true
    transport: stdio
    command: "my-mcp-server"
    args: ["--port", "8080"]
    env:
      MY_API_KEY: "${MY_API_KEY}"
    auto_connect: true
    description: "My custom MCP server"
```

## Development

### Project Structure

```
aider/mcp/
├── __init__.py           # Module exports
├── client.py             # MCPClientManager
├── registry.py           # Configuration management
├── tools.py              # Tool wrappers
├── exceptions.py         # MCP-specific exceptions
└── servers/
    ├── __init__.py
    ├── base.py          # Base connector
    └── context7.py      # Context7 connector
```

### Adding a New Server Connector

1. Create `aider/mcp/servers/myserver.py`:

```python
from .base import BaseMCPServerConnector

class MyServerConnector(BaseMCPServerConnector):
    def __init__(self):
        super().__init__()
        self.server_name = "myserver"
        self.requires_api_key = True
        self.env_var = "MYSERVER_API_KEY"
        self.command = "myserver-mcp"

    def get_config(self, api_key=None):
        config = super().get_config(api_key)
        config.update({
            'command': self.command,
            'args': [],
        })
        return config
```

2. Export in `aider/mcp/servers/__init__.py`:

```python
from .myserver import MyServerConnector

__all__ = [..., 'MyServerConnector']
```

## Resources

- **MCP Specification**: https://modelcontextprotocol.io/
- **Context7**: https://context7.com/
- **Aider MCP Integration Guide**: See `documentation/aider_mcp_integration/`

## Future Enhancements

- [ ] HTTP/SSE transport support
- [ ] MCP server installer (`/mcp-install` command)
- [ ] Auto-discovery of installed servers
- [ ] Tool result caching
- [ ] Multi-server tool namespacing
- [ ] Slash commands (`/mcp-list`, `/mcp-connect`, etc.)

## License

Same as Aider (Apache 2.0)
