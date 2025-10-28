# MCP Integration Testing Guide

## Quick Start Testing

### 1. Install MCP Dependencies

```bash
# Install Python MCP dependencies
pip install mcp nest-asyncio

# Context7 will auto-install via npx when first used
# Or optionally pre-install:
npm install -g @upstash/context7-mcp

# Verify npx is available (comes with Node.js)
which npx
npx --version
```

### 2. (Optional) Get Context7 API Key

**NOTE: Context7 works WITHOUT an API key!** The API key is only needed for:
- Higher rate limits
- Access to private repositories

If you want an API key:
1. Go to https://context7.com/dashboard
2. Sign up for an account
3. Get your API key from the dashboard

### 3. (Optional) Set Environment Variable

```bash
# OPTIONAL - Only if you have an API key
export CONTEXT7_API_KEY="your-api-key-here"

# Verify it's set
echo $CONTEXT7_API_KEY
```

### 4. Verify Configuration File

The configuration file `.aider.mcp.yaml` should already exist in the project root:

```bash
# Check if it exists
ls -la .aider.mcp.yaml

# View its contents
cat .aider.mcp.yaml
```

Expected content:
```yaml
mcp_servers:
  context7:
    enabled: true
    transport: stdio
    command: "context7-server"
    env:
      CONTEXT7_API_KEY: "${CONTEXT7_API_KEY}"
    auto_connect: true
    description: "Get version-specific documentation and code examples"

tool_settings:
  auto_discover: true
  timeout: 30
  retry_attempts: 3

ui:
  show_mcp_tools_in_help: true
  tool_call_notifications: true
```

## Testing Levels

### Level 1: Basic Startup Test

Test that Aider starts with MCP enabled without errors:

```bash
# Start Aider with MCP enabled
aider --enable-mcp

# Expected output:
# Initializing MCP client...
# MCP initialized: 1 servers, X tools available
```

**Success Criteria:**
- ✅ No AttributeError
- ✅ "Initializing MCP client..." message appears
- ✅ "MCP initialized: 1 servers, X tools available" message appears
- ✅ Aider prompt appears and is ready for input

**Common Errors:**
- "MCP dependencies not installed" → Run `pip install mcp nest-asyncio`
- "Failed to initialize MCP" → Check that `context7-server` is installed and API key is set
- No MCP messages → Check that `--enable-mcp` flag is used

### Level 2: Configuration Loading Test

Test that configuration is loaded correctly:

```bash
# Start with verbose output to see more details
aider --enable-mcp --verbose

# In Aider, type:
/exit
```

**Success Criteria:**
- ✅ Configuration file found and loaded
- ✅ Environment variable substitution works (${CONTEXT7_API_KEY})
- ✅ Server connection established
- ✅ Tools discovered and registered

### Level 3: Tool Discovery Test

Verify that MCP tools are available to the LLM:

```bash
# Start Aider with MCP
aider --enable-mcp

# Ask a question that would benefit from documentation
# For example:
> How do I use React useState hook?
```

**What Should Happen:**
1. Aider sends your question to the LLM
2. LLM receives the MCP tools in its function list
3. LLM decides to call a Context7 tool (e.g., `mcp__context7__resolve-library-id` or `mcp__context7__get-library-docs`)
4. You should see: "Calling MCP tool: mcp__context7__..."
5. You should see: "MCP tool result: ..."
6. LLM receives the documentation and provides an answer

**Success Criteria:**
- ✅ Tool call is detected
- ✅ Tool is executed via MCP
- ✅ Result is returned and displayed
- ✅ LLM uses the result to formulate its response

### Level 4: End-to-End Conversation Test

Test a full conversation flow with multiple tool calls:

```bash
aider --enable-mcp

# Test 1: Library documentation lookup
> How do I use React hooks? I need examples.

# Test 2: Version-specific documentation
> Show me how to use Next.js 14 server actions

# Test 3: Multiple libraries
> Compare useState from React with signals from Preact
```

**Success Criteria:**
- ✅ Multiple tool calls in sequence
- ✅ Conversation continues naturally after tool calls
- ✅ LLM integrates tool results into its responses
- ✅ No errors or hangs

## Testing Without Context7 (Mock Testing)

If you don't have a Context7 API key, you can test the MCP infrastructure:

### 1. Test with Disabled MCP

```bash
# Should work normally without MCP
aider

# Or explicitly disable
aider --no-enable-mcp
```

### 2. Test Error Handling

```bash
# Test missing dependencies (after uninstalling mcp)
pip uninstall mcp nest-asyncio
aider --enable-mcp
# Should show: "MCP dependencies not installed..."

# Test invalid configuration
# Temporarily rename the config file
mv .aider.mcp.yaml .aider.mcp.yaml.bak
aider --enable-mcp
# Should show warning about missing config

# Restore config
mv .aider.mcp.yaml.bak .aider.mcp.yaml
```

### 3. Test Custom Config Path

```bash
# Create a test config
cp .aider.mcp.yaml test-mcp-config.yaml

# Use it
aider --enable-mcp --mcp-config test-mcp-config.yaml
```

## Debugging Tips

### Enable Verbose Mode

```bash
aider --enable-mcp --verbose
```

This shows:
- Detailed MCP initialization logs
- Tool discovery process
- Function calls to LLM
- Tool execution details

### Check MCP Client State

In verbose mode, you'll see:
- Which servers are connected
- How many tools are available
- Tool call arguments and results

### Common Issues

#### 1. "No tools available"
**Cause:** Context7 server not responding or API key invalid
**Fix:**
- Verify API key: `echo $CONTEXT7_API_KEY`
- Test Context7 manually: `context7-server --help`

#### 2. "Tool call failed"
**Cause:** Tool execution error
**Fix:**
- Check tool arguments in verbose output
- Verify network connectivity
- Check Context7 service status

#### 3. "MCP timeout"
**Cause:** Tool execution taking too long
**Fix:**
- Increase timeout in `.aider.mcp.yaml`:
  ```yaml
  tool_settings:
    timeout: 60  # Increase from 30
  ```

#### 4. LLM doesn't call tools
**Cause:** LLM doesn't recognize the need or tools aren't exposed properly
**Fix:**
- Use more specific questions that clearly need documentation
- Check that tools appear in verbose LLM output
- Try: "Search the documentation for React hooks"

## Manual Tool Testing

If you want to test MCP tools directly (without the LLM):

```python
# Create a test script: test_mcp.py
from aider.mcp import MCPClientManager

# Initialize
config_path = ".aider.mcp.yaml"
client = MCPClientManager(config_path)
client.initialize()

# List servers
print("Servers:", client.list_servers())

# List tools
print("Tools:", client.list_tools())

# Get tools for LLM
tools = client.get_tools_for_llm()
print(f"Found {len(tools)} tools")
for tool in tools:
    print(f"  - {tool['function']['name']}")

# Test a tool call (example)
# result = client.call_tool("mcp__context7__resolve-library-id", {"libraryName": "react"})
# print("Result:", result)
```

Run it:
```bash
python test_mcp.py
```

## Success Checklist

- [ ] MCP dependencies installed
- [ ] Context7 server installed
- [ ] API key set in environment
- [ ] Configuration file exists and is valid
- [ ] Aider starts with `--enable-mcp` without errors
- [ ] "MCP initialized" message appears
- [ ] Tools are discovered (count > 0)
- [ ] Can ask questions that trigger tool calls
- [ ] Tool calls execute successfully
- [ ] Tool results are displayed
- [ ] LLM uses results in its responses
- [ ] Conversation continues after tool calls
- [ ] No hangs or crashes

## Next Steps After Testing

Once basic testing passes:

1. **Unit Tests**: Add tests for MCPRegistry, MCPToolWrapper, MCPClientManager
2. **Integration Tests**: Mock MCP server for automated testing
3. **Performance Tests**: Test with large documentation sets
4. **Error Recovery Tests**: Test reconnection, retries, timeouts
5. **Multi-Server Tests**: Add additional MCP servers

## Getting Help

If you encounter issues:

1. Check the verbose output: `aider --enable-mcp --verbose`
2. Review MCP logs in the console
3. Check Context7 server logs
4. Verify network connectivity
5. Review MCP_README.md for detailed documentation
6. Check MCP_IMPLEMENTATION_SUMMARY.md for architecture details
