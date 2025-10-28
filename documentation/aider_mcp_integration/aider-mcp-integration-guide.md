# Adding MCP Tools to Aider: Comprehensive Integration Guide

## Executive Summary

After analyzing the Aider codebase and the Model Context Protocol (MCP) ecosystem, I've identified **the most extendable approach** for integrating MCP tools into Aider. This will allow Aider to use MCP servers like Serena, Context7, and others as native capabilities.

## Key Findings

### Current State
1. **Aider's Architecture**: Modular design with `coders/` directory, `commands.py` for slash commands, and `base_coder.py` as the foundation
2. **Existing MCP Ecosystem**: Multiple MCP servers already exist that WRAP Aider (allowing other tools to call Aider), but nothing allows Aider to USE MCP tools
3. **Feature Request**: Issue #3658 on Aider's GitHub discusses making Aider an MCP server, but NOT consuming MCP tools

### The Problem
You want Aider to be an **MCP client** (consuming MCP tools), not an MCP server (exposing Aider's functionality to others).

## Recommended Architecture: MCP Client Integration Layer

### Option 1: Plugin-Based MCP Tool System (MOST EXTENDABLE) ⭐

This is the **best approach** for maximum extensibility and maintainability.

#### Architecture Overview

```
aider/
├── mcp/
│   ├── __init__.py
│   ├── client.py           # Core MCP client implementation
│   ├── registry.py         # MCP server registry/manager
│   ├── tools.py            # MCP tool wrapper/adapter
│   └── servers/
│       ├── __init__.py
│       ├── base.py         # Base MCP server connector
│       ├── serena.py       # Serena-specific connector
│       ├── context7.py     # Context7-specific connector
│       └── custom.py       # Template for custom servers
├── coders/
│   └── base_coder.py       # Enhanced with MCP tool support
├── commands.py             # New /mcp commands
└── config/
    └── mcp_config.yaml     # MCP server configurations
```

#### Key Components

##### 1. MCP Client Manager (`mcp/client.py`)

```python
"""
Core MCP client that handles:
- Connection management to MCP servers
- Tool discovery and registration
- Request/response handling
- Transport layer (stdio, SSE, HTTP)
"""

from typing import Dict, List, Any, Optional
import asyncio
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

class MCPClientManager:
    def __init__(self):
        self.servers: Dict[str, MCPServerConnection] = {}
        self.available_tools: Dict[str, MCPTool] = {}
        
    async def connect_server(
        self, 
        server_name: str, 
        server_config: Dict[str, Any]
    ) -> bool:
        """
        Connect to an MCP server and discover its tools
        
        Supports multiple transports:
        - stdio (for local servers)
        - SSE (Server-Sent Events)
        - HTTP with Streamable
        """
        # Implementation details...
        
    async def list_tools(self, server_name: Optional[str] = None) -> List[Dict]:
        """List all available tools from connected servers"""
        
    async def call_tool(
        self, 
        tool_name: str, 
        arguments: Dict[str, Any]
    ) -> Any:
        """Execute an MCP tool and return results"""
```

##### 2. MCP Registry (`mcp/registry.py`)

```python
"""
Manages MCP server configurations and lifecycle
"""

class MCPRegistry:
    def __init__(self, config_path: str = "mcp_config.yaml"):
        self.config_path = config_path
        self.servers = self.load_config()
        
    def load_config(self) -> Dict[str, ServerConfig]:
        """Load MCP server configurations from YAML"""
        
    def register_server(self, server_config: ServerConfig):
        """Register a new MCP server at runtime"""
        
    def discover_servers(self) -> List[str]:
        """Auto-discover available MCP servers"""
```

##### 3. MCP Tool Wrapper (`mcp/tools.py`)

```python
"""
Wraps MCP tools to make them accessible to Aider's coder
"""

class MCPToolWrapper:
    """
    Adapts MCP tools to Aider's internal tool interface
    Makes MCP tools feel native to Aider
    """
    
    def __init__(self, tool_info: Dict[str, Any], client: MCPClientManager):
        self.name = tool_info['name']
        self.description = tool_info['description']
        self.input_schema = tool_info['inputSchema']
        self.client = client
        
    async def execute(self, **kwargs) -> str:
        """Execute the tool and format results for Aider"""
        result = await self.client.call_tool(self.name, kwargs)
        return self.format_for_aider(result)
        
    def format_for_aider(self, result: Any) -> str:
        """Format MCP tool results for Aider's context"""
```

##### 4. Configuration (`config/mcp_config.yaml`)

```yaml
# MCP Server Configuration
mcp_servers:
  serena:
    enabled: true
    transport: stdio
    command: "npx"
    args: ["@serena-mcp/server"]
    env:
      SERENA_API_KEY: "${SERENA_API_KEY}"
    auto_connect: true
    
  context7:
    enabled: true
    transport: stdio
    command: "context7-server"
    env:
      CONTEXT7_API_KEY: "${CONTEXT7_API_KEY}"
    auto_connect: true
    
  custom_server:
    enabled: false
    transport: http_sse
    url: "http://localhost:8000/mcp"
    auth:
      type: "bearer"
      token: "${CUSTOM_API_KEY}"

# Tool-specific settings
tool_settings:
  auto_discover: true
  timeout: 30
  retry_attempts: 3
  
# UI Settings
ui:
  show_mcp_tools_in_help: true
  tool_call_notifications: true
```

#### Integration with Base Coder

Modify `aider/coders/base_coder.py`:

```python
class Coder:
    def __init__(self, ...):
        # Existing initialization...
        
        # Initialize MCP client
        self.mcp_client = None
        if self.use_mcp_tools:
            self.mcp_client = MCPClientManager()
            asyncio.run(self.mcp_client.initialize())
            self.available_mcp_tools = asyncio.run(
                self.mcp_client.list_tools()
            )
            
    def get_system_prompt(self):
        """Enhanced to include MCP tool descriptions"""
        base_prompt = super().get_system_prompt()
        
        if self.mcp_client:
            mcp_tools_section = self.format_mcp_tools_for_prompt(
                self.available_mcp_tools
            )
            return f"{base_prompt}\n\n{mcp_tools_section}"
            
        return base_prompt
        
    async def handle_mcp_tool_call(self, tool_name: str, arguments: Dict):
        """Handle LLM requests to use MCP tools"""
        result = await self.mcp_client.call_tool(tool_name, arguments)
        return self.format_tool_result(result)
```

#### New Slash Commands

Add to `aider/commands.py`:

```python
class Commands:
    def cmd_mcp_list(self, args):
        """List all available MCP servers and tools
        
        Usage:
            /mcp-list                 # List all connected servers
            /mcp-list serena          # List tools from specific server
            /mcp-list --tools         # List all tools
        """
        
    def cmd_mcp_connect(self, args):
        """Connect to an MCP server
        
        Usage:
            /mcp-connect serena
            /mcp-connect custom_server --url http://localhost:8000
        """
        
    def cmd_mcp_disconnect(self, args):
        """Disconnect from an MCP server
        
        Usage:
            /mcp-disconnect serena
        """
        
    def cmd_mcp_call(self, args):
        """Manually call an MCP tool
        
        Usage:
            /mcp-call search_docs --query "React hooks"
            /mcp-call get_context --library "pandas" --version "2.0"
        """
        
    def cmd_mcp_config(self, args):
        """View or modify MCP configuration
        
        Usage:
            /mcp-config                # Show current config
            /mcp-config --reload       # Reload from file
        """
```

### Option 2: Direct LiteLLM Tool Integration

A simpler but less flexible approach that leverages LiteLLM's function calling:

```python
# In base_coder.py

def send_with_mcp_tools(self, messages):
    """
    Send messages with MCP tools exposed as LLM functions
    """
    mcp_tools = self.get_mcp_tools_as_functions()
    
    response = litellm.completion(
        model=self.main_model.name,
        messages=messages,
        tools=mcp_tools,  # MCP tools exposed as OpenAI functions
        tool_choice="auto"
    )
    
    # Handle tool calls
    if response.choices[0].message.tool_calls:
        for tool_call in response.choices[0].message.tool_calls:
            if tool_call.function.name in self.mcp_tool_names:
                result = self.execute_mcp_tool(
                    tool_call.function.name,
                    json.loads(tool_call.function.arguments)
                )
                # Add result to conversation
```

**Pros:**
- Simpler implementation
- Works with existing LiteLLM integration
- Automatic tool calling via LLM

**Cons:**
- Less control over tool execution
- Harder to add custom MCP-specific features
- Limited to function-calling capable models

### Option 3: Hybrid Approach (RECOMMENDED FOR PRODUCTION) ⭐⭐

Combine both approaches for maximum flexibility:

1. **Core Layer**: Plugin-based MCP client (Option 1)
2. **LLM Integration**: Expose MCP tools as LiteLLM functions (Option 2)
3. **Manual Control**: Slash commands for direct tool access

This gives you:
- Automatic tool use by the LLM
- Manual control via slash commands
- Easy extension with new MCP servers
- Compatibility with all Aider features

## Implementation Roadmap

### Phase 1: Foundation (Week 1-2)
1. Create `mcp/` directory structure
2. Implement basic `MCPClientManager`
3. Add stdio transport support
4. Create configuration system

### Phase 2: Core Integration (Week 3-4)
1. Integrate with `base_coder.py`
2. Add MCP tools to system prompts
3. Implement tool call handling
4. Add basic error handling

### Phase 3: User Interface (Week 5-6)
1. Implement slash commands (`/mcp-*`)
2. Add configuration UI
3. Implement tool discovery
4. Add logging and debugging

### Phase 4: Extensions (Week 7-8)
1. Add SSE transport support
2. Add HTTP transport support
3. Implement server-specific connectors
4. Add authentication mechanisms

### Phase 5: Testing & Polish (Week 9-10)
1. Comprehensive testing
2. Documentation
3. Example configurations
4. Performance optimization

## Example Usage

After implementation, users would interact like this:

```bash
# Start Aider with MCP enabled
aider --mcp-config ~/.aider.mcp.yaml

# In Aider session:
> /mcp-list
Connected MCP Servers:
  ✓ serena (3 tools)
  ✓ context7 (5 tools)

Available Tools:
  - search_docs: Search documentation across libraries
  - get_context: Get version-specific code examples
  - analyze_error: Analyze error messages
  ...

# Automatic tool use by LLM:
> Help me understand how to use React useEffect

[Aider uses context7's get_context tool automatically]
[Retrieves React documentation]
[Provides answer with current best practices]

# Manual tool call:
> /mcp-call search_docs --query "pandas DataFrame merge"

[Returns: Documentation results...]

# In natural conversation:
> Can you check the latest documentation for FastAPI dependency injection?

[LLM decides to use search_docs tool]
[Retrieves current docs]
[Provides up-to-date answer]
```

## Technical Considerations

### 1. Async/Sync Bridge
MCP is async-first. Aider needs careful async handling:

```python
import asyncio
from functools import wraps

def async_to_sync(async_func):
    """Decorator to run async functions in sync context"""
    @wraps(async_func)
    def wrapper(*args, **kwargs):
        loop = asyncio.get_event_loop()
        if loop.is_running():
            # Running in async context
            return async_func(*args, **kwargs)
        else:
            # Running in sync context
            return loop.run_until_complete(async_func(*args, **kwargs))
    return wrapper
```

### 2. Transport Flexibility
Support all MCP transports from day one:

```python
class TransportFactory:
    @staticmethod
    def create(transport_type: str, config: Dict) -> Transport:
        if transport_type == "stdio":
            return StdioTransport(config)
        elif transport_type == "sse":
            return SSETransport(config)
        elif transport_type == "http":
            return HTTPTransport(config)
        else:
            raise ValueError(f"Unknown transport: {transport_type}")
```

### 3. Error Handling
Robust error handling for MCP operations:

```python
class MCPError(Exception):
    """Base exception for MCP operations"""
    
class MCPConnectionError(MCPError):
    """Server connection failed"""
    
class MCPToolError(MCPError):
    """Tool execution failed"""
    
class MCPTimeoutError(MCPError):
    """Operation timed out"""
```

### 4. Security Considerations
- Validate all MCP server configurations
- Sandbox tool execution
- Implement rate limiting
- Add API key encryption
- Audit tool calls

### 5. Performance Optimization
- Connection pooling for MCP servers
- Tool result caching
- Lazy server initialization
- Parallel tool execution where possible

## Advantages of This Approach

1. **Maximum Extensibility**: Adding new MCP servers is just configuration
2. **Clean Separation**: MCP logic isolated in `mcp/` directory
3. **Backward Compatible**: Doesn't break existing Aider functionality
4. **Future-Proof**: Can easily add new MCP features
5. **User-Friendly**: Both automatic and manual tool usage
6. **Standards-Based**: Uses official MCP SDKs
7. **Testable**: Each component can be tested independently

## Alternative Approaches Considered

### ❌ Hardcoded Tool Integration
- **Problem**: Not extendable, requires code changes for each tool
- **Why rejected**: Violates your requirement for extensibility

### ❌ Generic API Wrapper
- **Problem**: Doesn't leverage MCP's standardization
- **Why rejected**: MCP provides better structure and discoverability

### ❌ Fork LiteLLM with MCP Support
- **Problem**: Maintenance burden, upstream sync issues
- **Why rejected**: Too complex, not Aider-specific

## Required Dependencies

Add to `requirements.txt`:

```
mcp>=1.0.0                  # Official MCP SDK
pydantic>=2.0.0             # For configuration validation
aiohttp>=3.8.0              # For HTTP transport
pyyaml>=6.0                 # For configuration files
asyncio-throttle>=1.0.0     # For rate limiting
```

## Migration Path for Existing Users

1. MCP support is **opt-in** by default
2. Existing Aider workflows unaffected
3. New flag: `--enable-mcp` or config setting
4. Graceful degradation if MCP servers unavailable

## Documentation Needs

1. **User Guide**: How to configure MCP servers
2. **Developer Guide**: How to add new MCP server support
3. **API Reference**: MCP client API
4. **Examples**: Common MCP server configurations
5. **Troubleshooting**: Common issues and solutions

## Next Steps

1. **Discuss with Aider Maintainer**: Open an issue on GitHub proposing this architecture
2. **Prototype**: Build a minimal working version
3. **Test with Popular Servers**: Serena, Context7, etc.
4. **Gather Feedback**: From Aider community
5. **Submit PR**: With comprehensive tests and documentation

## Conclusion

The **Plugin-Based MCP Tool System (Option 1)** combined with **LiteLLM Integration (Option 2)** provides the most extendable, maintainable, and user-friendly approach to adding MCP tools to Aider. This architecture:

- ✅ Allows easy addition of new MCP servers via configuration
- ✅ Provides both automatic and manual tool usage
- ✅ Maintains Aider's existing workflow
- ✅ Leverages standard MCP protocols
- ✅ Can be incrementally developed and tested
- ✅ Scales to support many MCP servers

This design will enable Aider to become a true MCP client, capable of using any MCP server's tools while maintaining its core strengths as an AI pair programming tool.

---

## Quick Start Example

Here's a minimal proof-of-concept to validate the approach:

```python
# mcp/minimal_client.py
import asyncio
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

async def test_mcp_integration():
    server_params = StdioServerParameters(
        command="npx",
        args=["@serena-mcp/server"],
    )
    
    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            
            # List available tools
            tools = await session.list_tools()
            print("Available tools:", tools)
            
            # Call a tool
            result = await session.call_tool(
                "search_docs",
                arguments={"query": "React hooks"}
            )
            print("Result:", result)

# Run it
asyncio.run(test_mcp_integration())
```

This 20-line example proves the concept and can be expanded into the full architecture described above.
