# REQUEST_FILE Feature Implementation

## Overview

This feature allows LLMs to explicitly request files from the repository by using a simple command syntax, enabling autonomous file discovery without requiring users to manually add files to the chat.

## Motivation

**Problem:** Aider previously required users to manually `/add` files they wanted to edit. Users needed to know the exact file structure and which files needed modification.

**Solution:** With REQUEST_FILE, the LLM can see the repository structure (via RepoMap) and explicitly request files it needs, making Aider more autonomous like Claude Code.

## How It Works

### User Experience

**Before:**
```
User: "Fix the login bug"
Aider: [Waiting]
User: /add auth.py
User: /add models.py
Aider: "Fixed the bug in auth.py..."
```

**After:**
```
User: "Fix the login bug"
Aider: [Sees RepoMap]
LLM: "REQUEST_FILE: auth.py
      REQUEST_FILE: models.py"
Aider: "Adding requested files: auth.py, models.py"
LLM: "Fixed the bug in auth.py..."
```

### REQUEST_FILE Syntax

The LLM can request files using this format:

```
REQUEST_FILE: path/to/file.py
REQUEST_FILE: another/file.js
```

Requirements:
- Must be at the start of a line (not inline)
- Path should be relative to repository root
- File must exist in the repository

## Implementation Details

### Files Modified

1. **aider/coders/base_prompts.py**
   - Updated `repo_content_prefix` to include REQUEST_FILE instructions
   - All coder types now inform LLMs about this syntax

2. **aider/coders/context_prompts.py**
   - Updated `repo_content_prefix` for ContextCoder
   - Added explicit REQUEST_FILE syntax examples

3. **aider/coders/base_coder.py**
   - Added `parse_file_requests()` method (line ~1761)
     - Parses REQUEST_FILE commands from LLM responses
     - Validates files exist in repository
     - Supports fuzzy path matching

   - Updated `reply_completed()` method (line ~1625)
     - Checks for REQUEST_FILE commands
     - Adds requested files to chat
     - Triggers reflection loop with new files
     - Respects max_reflections limit

4. **aider/coders/context_coder.py**
   - Updated `reply_completed()` to handle both:
     - Explicit REQUEST_FILE commands
     - Implicit file mentions (existing behavior)
   - Combines both sources for maximum flexibility

### Technical Flow

```
1. User sends message
   ↓
2. LLM receives RepoMap (shows all files)
   ↓
3. LLM responds with REQUEST_FILE commands
   ↓
4. reply_completed() parses response
   ↓
5. parse_file_requests() extracts file paths
   ↓
6. Validates files exist in repository
   ↓
7. Adds files to abs_fnames
   ↓
8. Sets reflected_message
   ↓
9. Returns False → triggers reflection loop
   ↓
10. LLM receives message with full file contents
    ↓
11. LLM proceeds with actual edits
```

### Key Methods

**`parse_file_requests(content)` in base_coder.py:**
```python
def parse_file_requests(self, content):
    """Parse REQUEST_FILE commands from LLM response.

    Returns a set of relative file paths that were explicitly requested.
    """
    # Uses regex: r'^REQUEST_FILE:\s*(.+)$'
    # Validates against repository files
    # Supports fuzzy matching for partial paths
    return requested_files
```

**`reply_completed()` in base_coder.py:**
```python
def reply_completed(self):
    """Check if LLM requested files and add them if needed.

    Returns False if reflection is needed (files were added), True otherwise.
    """
    # Parse REQUEST_FILE commands
    # Check against current files
    # Add new files and trigger reflection
    # Respects max_reflections limit
```

## Features

✅ **Universal Support**: Works in all coder modes (editblock, wholefile, udiff, etc.), not just ContextCoder

✅ **Fuzzy Matching**: Handles partial paths (e.g., "auth.py" matches "src/auth.py")

✅ **Validation**: Only adds files that actually exist in repository

✅ **Reflection Control**: Respects max_reflections limit to prevent infinite loops

✅ **User Feedback**: Shows which files were added via tool_output

✅ **Backward Compatible**: Doesn't break existing file mention detection

✅ **ContextCoder Enhanced**: Now handles both REQUEST_FILE and implicit mentions

## Testing

All modified files pass Python syntax validation:
```bash
python3 -m py_compile aider/coders/base_coder.py        # ✓
python3 -m py_compile aider/coders/context_coder.py     # ✓
python3 -m py_compile aider/coders/base_prompts.py      # ✓
python3 -m py_compile aider/coders/context_prompts.py   # ✓
```

REQUEST_FILE parsing verified with test cases:
- ✓ Parses multiple REQUEST_FILE commands
- ✓ Returns empty set when none present
- ✓ Ignores inline REQUEST_FILE (must be at line start)

## Benefits

1. **Reduced User Burden**: Users don't need to know exact file locations
2. **Faster Workflow**: No manual `/add` commands needed
3. **Better LLM Context**: LLM sees RepoMap and can make informed decisions
4. **Explicit Intent**: REQUEST_FILE is clearer than implicit file mentions
5. **Debuggable**: Easy to see which files were requested and why

## Limitations

⚠️ Uses one reflection turn (API call) to request files
⚠️ Limited by max_reflections (default 3)
⚠️ Requires RepoMap to be enabled (for LLM to see file structure)
⚠️ Fuzzy matching may occasionally select wrong file if multiple matches exist

## Future Enhancements

Potential improvements:
- Import-based dependency detection
- Automatic file ranking by relevance
- Predictive preloading of likely files
- Smart token budget allocation
- Integration with IDE file navigation

## Example Usage

**Scenario: Fix a bug across multiple files**

```
$ aider

User: "The user authentication is broken, fix it"

Aider → LLM: [Sends RepoMap showing auth.py, models.py, api.py, etc.]

LLM: "REQUEST_FILE: src/auth.py
      REQUEST_FILE: src/models.py

      I need to see these files to diagnose the issue."

Aider: "Adding requested files: src/auth.py, src/models.py"

Aider → LLM: [Sends full contents of auth.py and models.py]

LLM: "Found the issue. The password validation in auth.py:45 is missing
      a null check. Here are the fixes:

      src/auth.py
      <<<<<<< SEARCH
      def validate_password(password):
          return len(password) >= 8
      =======
      def validate_password(password):
          if password is None:
              return False
          return len(password) >= 8
      >>>>>>> REPLACE"

Aider: "Applied changes to src/auth.py"
```

## Conclusion

The REQUEST_FILE feature bridges the gap between Aider's manual file management and Claude Code's autonomous approach. By giving LLMs the ability to explicitly request files they need, we've made Aider significantly more autonomous while maintaining control and transparency.

The implementation is minimal (~80 lines of code), backward compatible, and leverages existing reflection loop infrastructure.
