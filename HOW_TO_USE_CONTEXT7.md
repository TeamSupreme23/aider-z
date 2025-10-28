# How to Use Context7 with Aider

## Quick Answer

**You don't manually invoke Context7** - the LLM decides when to use it based on your prompts. Context7 tools are automatically available when you start Aider with `--enable-mcp`.

## How It Works

### 1. Start Aider with MCP Enabled

```bash
# With your local LLM (e.g., Ollama)
aider --enable-mcp --model ollama/deepseek-coder

# With any LiteLLM-compatible model
aider --enable-mcp --model openai/gpt-4
```

You should see:
```
Initializing MCP client...
MCP initialized: 1 servers, 2 tools available
```

This means Context7 is loaded and ready!

### 2. The LLM Sees the Tools

When MCP is enabled, your LLM receives two additional "functions" it can call:

```json
{
  "name": "mcp__context7__resolve-library-id",
  "description": "Resolves a package/product name to a Context7-compatible library ID",
  "parameters": {
    "libraryName": "string - Library name to search for"
  }
}

{
  "name": "mcp__context7__get-library-docs",
  "description": "Fetches up-to-date documentation for a library",
  "parameters": {
    "context7CompatibleLibraryID": "string - Library ID from resolve-library-id",
    "topic": "string (optional) - Specific topic to focus on",
    "tokens": "number (optional) - Max tokens of docs to retrieve"
  }
}
```

### 3. When Does the LLM Use Context7?

The LLM will **automatically** use Context7 when:
- It recognizes a question about a library/framework
- It needs current documentation
- It determines external info would help

**Example prompts that might trigger Context7:**
```
> How do I use React hooks?
> Show me Next.js 14 server actions
> What's the syntax for useState in React?
> How do I configure Tailwind CSS?
```

## How to Know If It's Being Used

### Method 1: Watch for Tool Call Output

When Context7 is called, you'll see:
```
Calling MCP tool: mcp__context7__resolve-library-id
MCP tool result:
{
  "id": "/vercel/next.js",
  "name": "next.js",
  ...
}

Calling MCP tool: mcp__context7__get-library-docs
MCP tool result:
[Documentation content here]
```

### Method 2: Use Verbose Mode

```bash
aider --enable-mcp --verbose --model ollama/your-model
```

This shows:
- Tools being registered
- Function calls in LLM requests
- Tool execution details

### Method 3: Check the Response

If Context7 was used, the LLM's answer will often:
- Include very current information
- Reference specific versions
- Provide accurate API documentation

## Important: Not All LLMs Support Function Calling

**Context7 only works if your LLM supports function calling!**

### ✅ Models That Support Function Calling:
- **OpenAI**: GPT-4, GPT-3.5-turbo
- **Anthropic**: Claude 3.x series
- **Local Models (via Ollama)**:
  - `deepseek-coder` (limited support)
  - `qwen2.5-coder` (limited support)
  - `mistral` (some variants)
  - `llama3.1` (8B and up, limited)

### ❌ Models That May NOT Support Function Calling:
- Older or smaller models
- Many local models don't reliably use functions
- Base models without instruction tuning

## If Your LLM Doesn't Call the Tools

This is **completely normal** with many local LLMs. Here's what you can do:

### Option 1: Prompt More Explicitly

Instead of:
```
> How do I use React hooks?
```

Try:
```
> Search the documentation for React hooks and show me examples
> I need the latest docs on React useState hook
> Look up how to use Next.js server components
```

### Option 2: Use a Model with Better Function Calling

```bash
# Try a larger model
aider --enable-mcp --model ollama/qwen2.5-coder:32b

# Or use an API model
aider --enable-mcp --model anthropic/claude-3-5-sonnet-20241022
```

### Option 3: Test That MCP Is Working

Even if tools aren't being called, you can verify MCP is working:

```bash
# Run the test script
./test_mcp_basic.sh

# Or check manually with verbose mode
aider --enable-mcp --verbose
```

## Manual Testing (Without LLM)

You can test Context7 directly with Python:

```python
# test_context7.py
from aider.mcp import MCPClientManager

# Initialize
client = MCPClientManager(".aider.mcp.yaml")
client.initialize()

# List available tools
print("Available tools:", client.list_tools())

# Call resolve-library-id
result = client.call_tool(
    "mcp__context7__resolve-library-id",
    {"libraryName": "react"}
)
print("Library ID:", result)

# Call get-library-docs
result = client.call_tool(
    "mcp__context7__get-library-docs",
    {
        "context7CompatibleLibraryID": "/facebook/react",
        "topic": "hooks"
    }
)
print("Docs:", result[:500])  # First 500 chars
```

Run it:
```bash
python test_context7.py
```

This bypasses the LLM entirely and tests MCP directly.

## Configuration Options

### Default Configuration (`.aider.mcp.yaml`):

```yaml
mcp_servers:
  context7:
    enabled: true
    transport: stdio
    command: "npx"
    args: ["-y", "@upstash/context7-mcp"]
    auto_connect: true
```

### With API Key (Optional - Higher Rate Limits):

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
```

### Disable Auto-Connect:

```yaml
mcp_servers:
  context7:
    enabled: true
    auto_connect: false  # Won't connect on startup
```

Then start Aider without `--enable-mcp`, or manually connect later.

## Troubleshooting

### "No tools being called"

**Likely cause**: Your LLM doesn't support function calling or doesn't recognize when to use tools.

**Solutions**:
1. Try a different model with better function calling
2. Be more explicit in your prompts
3. Use `--verbose` to see if tools are even being offered to the LLM

### "MCP initialized: 1 servers, 0 tools available"

**Cause**: Context7 server connected but no tools discovered.

**Solutions**:
1. Check that npx can run Context7: `npx @upstash/context7-mcp --help`
2. Look for errors in verbose output
3. Ensure Node.js is up to date (v18+)

### "Failed to initialize MCP"

**Cause**: Connection to Context7 server failed.

**Solutions**:
1. Check Node.js is installed: `node --version`
2. Check npx is available: `npx --version`
3. First run may be slow (downloading package)
4. Check `--verbose` output for specific error

## Example Session

Here's what a successful session looks like:

```bash
$ aider --enable-mcp --model anthropic/claude-3-5-sonnet-20241022

Initializing MCP client...
MCP initialized: 1 servers, 2 tools available

Aider v0.86.1+less
Model: claude-3-5-sonnet-20241022
...

> How do I use React useState hook?

Calling MCP tool: mcp__context7__resolve-library-id
MCP tool result: {"id": "/facebook/react", ...}

Calling MCP tool: mcp__context7__get-library-docs
MCP tool result: [React hooks documentation...]

The useState hook in React allows you to add state to functional components.
Here's how to use it:

import { useState } from 'react';

function Counter() {
  const [count, setCount] = useState(0);

  return (
    <button onClick={() => setCount(count + 1)}>
      Count: {count}
    </button>
  );
}

[LLM provides detailed explanation using the fetched docs...]

> Thanks!

You're welcome! Let me know if you need help with anything else.

> /exit
```

## Summary

**To use Context7 with Aider:**

1. ✅ Start Aider with `--enable-mcp`
2. ✅ Make sure you see "MCP initialized: 1 servers, 2 tools available"
3. ✅ Ask questions about libraries/frameworks
4. ✅ Watch for "Calling MCP tool" messages

**You DON'T need to:**
- ❌ Manually invoke Context7
- ❌ Use special commands
- ❌ Configure anything (works out of box)
- ❌ Have an API key (optional only)

**The LLM decides when to use Context7** - you just ask your questions naturally!

If your LLM never calls the tools, that's a limitation of the model's function-calling capabilities, not an MCP issue. The tools are there and working - the LLM just needs to be "smart enough" to use them.
