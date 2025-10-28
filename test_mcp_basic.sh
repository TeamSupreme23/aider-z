#!/bin/bash

# Basic MCP Testing Script
# Tests MCP integration step by step

set -e  # Exit on error

echo "======================================"
echo "MCP Integration Basic Test"
echo "======================================"
echo ""

# Color codes
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Test counter
PASSED=0
FAILED=0

test_step() {
    echo -e "${YELLOW}TEST:${NC} $1"
}

test_pass() {
    echo -e "${GREEN}✓ PASS:${NC} $1"
    PASSED=$((PASSED + 1))
    echo ""
}

test_fail() {
    echo -e "${RED}✗ FAIL:${NC} $1"
    FAILED=$((FAILED + 1))
    echo ""
}

# Test 1: Check Python version
test_step "Checking Python version (need 3.10+)"
PYTHON_VERSION=$(python3 --version 2>&1 | awk '{print $2}')
MAJOR=$(echo $PYTHON_VERSION | cut -d. -f1)
MINOR=$(echo $PYTHON_VERSION | cut -d. -f2)

if [ "$MAJOR" -ge 3 ] && [ "$MINOR" -ge 10 ]; then
    test_pass "Python $PYTHON_VERSION is compatible"
else
    test_fail "Python $PYTHON_VERSION is too old (need 3.10+)"
    exit 1
fi

# Test 2: Check if in aider directory
test_step "Checking if in aider-z directory"
if [ -f "aider/main.py" ]; then
    test_pass "In correct directory"
else
    test_fail "Not in aider-z directory. Please cd to the project root."
    exit 1
fi

# Test 3: Check if virtualenv exists or create one
test_step "Checking Python environment"
if [ ! -d "aider_env" ]; then
    echo "Creating virtual environment..."
    python3 -m venv aider_env
    test_pass "Created aider_env"
else
    test_pass "Virtual environment exists"
fi

# Test 4: Activate virtualenv and install dependencies
test_step "Installing MCP dependencies"
source aider_env/bin/activate
pip install -q mcp nest-asyncio 2>/dev/null
if python3 -c "import mcp; import nest_asyncio" 2>/dev/null; then
    test_pass "MCP dependencies installed (mcp, nest-asyncio)"
else
    test_fail "Failed to install MCP dependencies"
    exit 1
fi

# Test 5: Check Node.js
test_step "Checking Node.js (needed for context7-server)"
if command -v node &> /dev/null; then
    NODE_VERSION=$(node --version)
    test_pass "Node.js $NODE_VERSION found"

    # Test 6: Check if npx is available (comes with npm)
    test_step "Checking npx (needed to run @upstash/context7-mcp)"
    if command -v npx &> /dev/null; then
        NPX_VERSION=$(npx --version)
        test_pass "npx $NPX_VERSION is available"
        echo "Context7 will be auto-installed via: npx -y @upstash/context7-mcp"
    else
        test_fail "npx not found (should come with Node.js/npm)"
        echo "Reinstall Node.js from: https://nodejs.org/"
    fi
else
    test_fail "Node.js not found (needed for context7-server)"
    echo "Install Node.js from: https://nodejs.org/"
fi

# Test 7: Check CONTEXT7_API_KEY (optional)
test_step "Checking CONTEXT7_API_KEY (optional - only for higher rate limits)"
if [ -z "$CONTEXT7_API_KEY" ]; then
    echo -e "${YELLOW}INFO:${NC} CONTEXT7_API_KEY not set (this is OK!)"
    echo "Context7 works without an API key."
    echo "API key only needed for higher rate limits and private repos."
    echo "Get one at: https://context7.com/dashboard"
    test_pass "Context7 will work without API key"
else
    test_pass "CONTEXT7_API_KEY is set (higher rate limits enabled)"
fi

# Test 8: Check configuration file
test_step "Checking .aider.mcp.yaml configuration file"
if [ -f ".aider.mcp.yaml" ]; then
    test_pass "Configuration file exists"
    echo "Content preview:"
    head -n 10 .aider.mcp.yaml
    echo ""
else
    test_fail "Configuration file .aider.mcp.yaml not found"
    exit 1
fi

# Test 9: Try to import MCP modules
test_step "Testing MCP module imports"
python3 -c "
from aider.mcp import MCPClientManager, MCPRegistry
from aider.mcp.exceptions import MCPError
print('Successfully imported MCP modules')
" 2>/dev/null

if [ $? -eq 0 ]; then
    test_pass "MCP modules can be imported"
else
    test_fail "Failed to import MCP modules"
    echo "Make sure you're in the project directory with aider/ folder"
    exit 1
fi

# Test 10: Try basic MCP initialization (without connecting)
test_step "Testing MCP registry initialization"
python3 << 'PYEOF'
import sys
sys.path.insert(0, '.')

from aider.mcp import MCPRegistry

try:
    registry = MCPRegistry('.aider.mcp.yaml')
    servers = registry.list_servers()
    print(f"Found {len(servers)} configured servers: {', '.join(servers)}")

    config = registry.get_server_config('context7')
    if config:
        print(f"Context7 config loaded: enabled={config.get('enabled')}")
    sys.exit(0)
except Exception as e:
    print(f"Error: {e}")
    sys.exit(1)
PYEOF

if [ $? -eq 0 ]; then
    test_pass "MCP registry initialization successful"
else
    test_fail "MCP registry initialization failed"
fi

# Summary
echo "======================================"
echo "Test Summary"
echo "======================================"
echo -e "${GREEN}Passed: $PASSED${NC}"
echo -e "${RED}Failed: $FAILED${NC}"
echo ""

if [ $FAILED -eq 0 ]; then
    echo -e "${GREEN}✓ All tests passed!${NC}"
    echo ""
    echo "You can now test Aider with MCP:"
    echo "  source aider_env/bin/activate"
    echo "  python -m aider.main --enable-mcp"
    echo ""
    echo "Or try a simple question:"
    echo '  echo "How do I use React hooks?" | python -m aider.main --enable-mcp --yes'
else
    echo -e "${RED}✗ Some tests failed.${NC}"
    echo "Please fix the issues above before testing MCP integration."
    exit 1
fi
