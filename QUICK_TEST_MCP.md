# Quick Test: MCP Integration with Aider

## TL;DR - Test in 3 Steps

```bash
# 1. Install MCP dependencies
pip install mcp nest-asyncio

# 2. Start Aider with MCP (Context7 auto-installs via npx)
aider --enable-mcp

# 3. Try asking about a library
# At the Aider prompt:
> How do I use React hooks?
```

**That's it!** No API key needed. Context7 will auto-download via npx on first use.

## What You Should See

### On Startup:
```
Initializing MCP client...
MCP initialized: 1 servers, 2 tools available
Aider v0.86.1+less
...
>
```

### When Asking Questions:
If Context7 tools are working, you might see:
```
Calling MCP tool: mcp__context7__resolve-library-id
MCP tool result: ...
Calling MCP tool: mcp__context7__get-library-docs
MCP tool result: ...
[LLM provides answer with up-to-date documentation]
```

## Requirements

✅ **Must Have:**
- Python 3.10+
- Node.js (for npx)
- `pip install mcp nest-asyncio`

❌ **Don't Need:**
- Context7 API key (optional, only for higher rate limits)
- Pre-installing Context7 (npx handles it)

## Testing Without LLM Tool Calls

Even if your local LLM doesn't call the tools automatically, you can verify MCP is working:

```bash
# Run the test script
./test_mcp_basic.sh

# Should pass all tests and confirm:
# - MCP dependencies installed
# - npx available
# - Configuration valid
# - MCP modules import correctly
```

## Troubleshooting

### "AttributeError: 'EditBlockCoder' object has no attribute 'io'"
✅ **Fixed!** Make sure you're on the latest commit.

### "MCP dependencies not installed"
```bash
pip install mcp nest-asyncio
```

### "Failed to connect to MCP server"
- Check Node.js is installed: `node --version`
- Check npx is available: `npx --version`
- First run will download Context7 (may take a moment)

### Context7 not being called
- This is normal with some LLMs - they may not recognize when to use tools
- The tools are available, but the LLM decides whether to call them
- Try more specific questions: "Search the documentation for React hooks"

## Using with Local LLM

Aider with MCP works with any LLM! For example:

```bash
# With Ollama
aider --enable-mcp --model ollama/deepseek-coder

# With LM Studio
aider --enable-mcp --model openai/local-model --openai-api-base http://localhost:1234/v1

# The MCP tools are available regardless of which LLM you use
```

Whether the LLM actually *uses* the tools depends on:
- Whether the model supports function calling
- Whether the model recognizes the need for external info
- The quality of your prompt

## What's Next?

Once basic testing works:

1. **Test with different prompts** - See when Context7 gets called
2. **Add more MCP servers** - Edit `.aider.mcp.yaml` to add other servers
3. **Check verbose output** - Use `--verbose` to see tool discovery details

## Full Documentation

- **Complete setup**: See `MCP_README.md`
- **Testing guide**: See `MCP_TESTING_GUIDE.md`
- **Implementation details**: See `MCP_IMPLEMENTATION_SUMMARY.md`
