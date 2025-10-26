# Aider File Management - Executive Summary

## What I've Documented

I've created comprehensive documentation of Aider's file management system:

1. **AIDER_FILE_MANAGEMENT_ANALYSIS.md** (697 lines)
   - Complete technical architecture analysis
   - 9 major sections with detailed code locations
   - Current vs. proposed autonomous state
   - Comprehensive reference appendix

2. **ARCHITECTURE_QUICK_REFERENCE.md** (500+ lines)
   - Visual data flow diagrams
   - Quick lookup tables
   - Key classes and methods
   - Gotchas and non-obvious behaviors
   - Comparison of current vs. proposed flows

## Key Findings

### Current Architecture (Manual File Management)

**Core File Collections:**
- `abs_fnames` (Set) - Absolute paths to editable files
- `abs_read_only_fnames` (Set) - Absolute paths to reference files
- `repo` (GitRepo) - Git integration and file tracking

**File Addition Flow:**
```
User: /add pattern
  ↓ Commands.cmd_add()
  ↓ glob_filtered_to_repo(pattern)
  ↓ Validate (gitignore, git-tracked, permissions)
  ↓ Read file content
  ↓ abs_fnames.add(abs_path)
  ↓ Include in next message to LLM
```

**Key Constraint:** ONLY files explicitly added to `abs_fnames` are visible to LLM

### Existing File Discovery Capabilities

**1. RepoMap (repomap.py)**
- Uses `grep_ast` for AST parsing
- Extracts functions, classes, methods
- Caches results in `.aider.tags.cache/`
- **LIMITATION:** Informational only, doesn't auto-add files
- Included as read-only system message
- Ranked by mention relevance (~1024 tokens)

**2. ContextCoder (context_coder.py)**
- Analyzes LLM output for file mentions
- Compares against currently added files
- Updates `abs_fnames` if mismatch found
- **LIMITATION:** Max 3 reflection loops per message
- Requires user to explicitly invoke "context" mode

**3. File Mention Detection (base_coder.py)**
- `get_file_mentions()` - Text-based word matching
- `get_ident_filename_matches()` - Identifier to file mapping
- **LIMITATION:** Low precision, requires ≥5 char names

### Root Causes of Non-Autonomy

| Issue | Why | Impact |
|-------|-----|--------|
| Manual `/add` required | Only `abs_fnames` visible to LLM | Cannot discover dependencies |
| RepoMap read-only | Included as system message only | Structure visible but not selectable |
| ContextCoder limited | Only reflection loops, max 3 | Cannot analyze edit results |
| No import parser | No dependency graph built | Cannot find files that must edit together |
| No call graph | RepoMap shows structure only | Cannot rank by interaction importance |
| Context budget all-or-nothing | No intelligent allocation | Important files dropped for size |

---

## What Would Enable Autonomous File Discovery

### Minimal Changes (Quick Wins)
1. **Extend ContextCoder** in `/aider/coders/context_coder.py`
   - After LLM response, check if edits reference missing files
   - Auto-add as read-only if beneficial
   - Re-run edits if successful

2. **Enhance RepoMap** in `/aider/repomap.py`
   - Add `suggest_related_files(user_intent)` method
   - Return ranked list of candidate files
   - Use for auto-selection instead of info-only

3. **Smart Prompt Injection** in `base_coder.py:format_messages()`
   - Before sending to LLM: analyze user intent
   - Include prompt requesting file list
   - Parse structured response to auto-add

### Medium Effort (Significant Improvement)
1. **Dependency Parser** - New module `dep_analyzer.py`
   - Parse import statements (Python, JS, TS, Go)
   - Build file-to-file dependency graph
   - Rank by criticality (direct import > transitive)

2. **Semantic File Ranking** - Extend `base_coder.py`
   - Score relevance: mention count × import depth × recency
   - Sort: critical first, optional last
   - Use for token budget allocation

3. **Post-Edit Analysis** - Modify `apply_edits()`
   - Parse imports in new code
   - Check if imported files in chat
   - Warn or auto-add if missing

### Full Implementation (Complete Autonomy)
1. All of above PLUS:
2. Call graph construction from RepoMap
3. Git history analysis (co-modified files)
4. Token budget intelligence (smart allocation)
5. Predictive preloading (what's next likely needed)

---

## Files That Control File Management

### Absolutely Critical
| File | Lines | Purpose | To Modify For |
|------|-------|---------|---------------|
| `base_coder.py` | 2000+ | File state + message building | Auto-selection logic |
| `commands.py` | 1695 | `/add` and file commands | Auto-discovery backend |
| `io.py` | 1500+ | File I/O operations | N/A (wrapper) |
| `repo.py` | 1000+ | Git integration | N/A (already complete) |

### Important for Discovery
| File | Lines | Purpose | To Modify For |
|------|-------|---------|---------------|
| `repomap.py` | 700+ | Code structure analysis | Auto-ranking suggestions |
| `context_coder.py` | 54 | Reflection loops | Dependency checking |
| `chat_chunks.py` | 200+ | Message formatting | Context prioritization |

### Edit Implementation
| File | Lines | Purpose | To Modify For |
|------|-------|---------|---------------|
| `editblock_coder.py` | 300+ | SEARCH/REPLACE edits | Post-edit analysis |
| `wholefile_coder.py` | 150+ | Full file edits | Post-edit analysis |
| `patch_coder.py` | 700+ | Unified diff | Post-edit analysis |

---

## Key Data Structures

### abs_fnames: Set[str]
```python
abs_fnames = {
    '/home/user/project/src/auth.py',
    '/home/user/project/src/models.py',
    '/home/user/project/api.py'
}
```
**Usage:**
- Checked before applying edits: `if file in self.abs_fnames: apply_edit()`
- Formatted into message: `get_files_content()` reads these
- Visible in `/ls` output
- Add via: `self.abs_fnames.add(abs_path)`
- Remove via: `self.abs_fnames.remove(abs_path)`

### abs_read_only_fnames: Set[str]
```python
abs_read_only_fnames = {
    '/home/user/project/lib/utils.py',  # Reference only
    '/home/user/project/config.py'      # Context only
}
```
**Usage:**
- Visible in message but NOT editable
- Cannot be modified via `apply_edits()`
- Useful for "show me how this works" scenarios
- Add via: `/read-only path/to/file.py`

### repo: GitRepo
```python
repo.get_tracked_files()      # → List[str] all git files
repo.git_ignored_file(path)   # → bool in .gitignore?
repo.ignored_file(path)       # → bool in .aiderignore?
repo.is_dirty(path)           # → bool uncommitted changes?
```

---

## Critical Methods Reference

### Main Entry Points (How to Hook In)

**`base_coder.py:run()` - Main interactive loop**
```python
def run(self, with_message=None, preproc=True):
    # THIS IS THE MAIN LOOP
    while True:
        user_message = self.get_input()
        self.run_one(user_message, preproc)
```
**Hook Point:** Could analyze user_message here before run_one()

**`base_coder.py:format_messages()` - Message building**
```python
def format_messages(self):
    # Builds complete message including:
    # - System prompt
    # - Repo map
    # - Read-only files
    # - Chat files (abs_fnames only!)
    # - Chat history
```
**Hook Point:** Modify abs_fnames BEFORE this is called

**`base_coder.py:reply_completed()` - After LLM response**
```python
def reply_completed(self):
    # Determines when to accept response vs. reflect
    # In ContextCoder: checks if mentions match abs_fnames
```
**Hook Point:** Extend to check for missing imports

**`apply_edits()` - Before/after applying changes**
```python
def apply_edits(self, edits):
    # Parses LLM response
    # Applies changes to disk
    # Validates file in abs_fnames
```
**Hook Point:** Analyze imports in new code after successful edit

### File Discovery Methods (Existing)

**`get_file_mentions(content)`**
```python
# Extract words from content that match filenames
# Returns: Set[str] matching relative filenames
# LIMITATION: Text matching only, low precision
```

**`get_ident_filename_matches(idents)`**
```python
# Match code identifiers to file stems
# Returns: Files likely related to identifiers
# LIMITATION: Requires ≥5 char names
```

**`get_all_relative_files()`**
```python
# Returns all available files in repo
# If git: repo.get_tracked_files()
# Else: get_inchat_relative_files()
```

**`get_addable_relative_files()`**
```python
# Returns files not yet in chat
# = all_files - inchat_files - readonly_files
```

---

## Constraints to Be Aware Of

### 1. Set Membership is Fast (O(1))
```python
if file_path in self.abs_fnames:  # Fast!
    apply_edit(file_path)
```
Good for: Tight loops, checking membership
Use for: File validation during edits

### 2. RepoMap Tokens are Limited
```python
# Default: 1024 tokens for repo map
# Only ranks top items within budget
# Can be disabled: --map-tokens=0
```

### 3. ContextCoder Max Reflections
```python
# Max 3 reflections per message
# After 3, stops even if mismatch
# Prevents infinite loops
```

### 4. Git-Tracked Only (Default)
```python
# /add only includes git-tracked files by default
# Exception: --add-gitignore-files flag
# Exception: Create new files with confirmation
```

### 5. Image Files Special-Cased
```python
# Base64 encoded if vision model
# Checked against model.supports_vision
# Not included in token counting
```

---

## Quick Start: Where to Make Changes

### To Add Import-Based File Discovery:
1. Create `/aider/dep_analyzer.py`
2. Implement parser for target languages
3. Call from `base_coder.py:format_messages()`
4. Update `abs_fnames` before LLM call

### To Auto-Rank Files by Relevance:
1. Extend `base_coder.py` with `score_file_importance()`
2. Sort `abs_fnames` by score
3. Include in message in priority order
4. Drop lowest-priority if over token budget

### To Analyze Edits for Missing Files:
1. Extend coder subclasses' `apply_edits()`
2. After successful edit, parse imports in new code
3. Check: `if imported_file not in abs_fnames:`
4. Offer to add as read-only or warn

### To Make ContextCoder Smarter:
1. Extend `context_coder.py:reply_completed()`
2. Not just check mentions, check imports too
3. Add files that new code would import from
4. Re-run with updated files

---

## Testing Your Changes

### Debugging Aids
```python
# In base_coder.py, add debugging:
from aider.dump import dump

# Use dump() to inspect data structures:
dump(self.abs_fnames)           # See current files
dump(self.get_all_relative_files())  # See all options
dump(self.get_repo_map())       # See what's visible
```

### Key Places to Add Logging
1. `format_messages()` - Before including files
2. `apply_edits()` - After parsing response
3. `reply_completed()` - After LLM response
4. Your new discovery function - Monitor ranking

### Testing Scenarios
```bash
# Test with small repo first
cd /tmp && mkdir test-repo && cd test-repo
git init

# Create some files with imports
echo "import models" > main.py
echo "class Model: pass" > models.py

# Start aider and test your changes
aider main.py
# Now test: should auto-add models.py?
```

---

## Performance Considerations

### File Set Operations (Fast)
- Check membership: O(1)
- Add file: O(1)
- Remove file: O(1)
- Iterate all: O(n)

### RepoMap Operations (Cached)
- First run: ~1s per 1000 files (depends on file size)
- Subsequent runs: ~100ms (cached results)
- Can be refreshed: `RepoMap.refresh = "always"`

### Message Formatting (Linear)
- Linear in file count and file sizes
- Each file read from disk once
- Formatted with markers and fences
- Total time: ~100ms-500ms typical repos

### Dependency Parsing (To Implement)
- Should be cached like RepoMap
- Incrementally updated on file changes
- Consider: Only parse files in chat + candidates?

---

## Next Steps for Implementation

1. **Create test scenario** - Small repo with dependencies
2. **Implement minimal parser** - Python imports only, start simple
3. **Add to ContextCoder** - Hook `reply_completed()`
4. **Test reflection loop** - Verify files auto-add
5. **Extend to other languages** - JS, TS, Go
6. **Add relevance scoring** - Rank by importance
7. **Implement token budgeting** - Smart allocation
8. **Performance optimize** - Caching, incremental updates

---

## Summary

**Current State:** Aider requires explicit `/add` commands because only `abs_fnames` are visible to LLM

**Root Cause:** No automatic file discovery or dependency resolution system

**Existing Assets:**
- RepoMap for code structure
- ContextCoder for reflection
- File mention detection
- Git integration for file lists

**To Enable Autonomy:**
- Dependency parser (import → files)
- Smart ranking (importance × relevance)
- Post-edit analysis (edits import what?)
- Auto-add mechanism (with safeguards)

**Effort Estimate:**
- Minimal (extend ContextCoder): 1-2 days
- Medium (add dependency parser): 1-2 weeks
- Full (complete autonomy): 2-4 weeks

**Key Files to Modify:**
- `/aider/coders/base_coder.py` - Main state + hooks
- `/aider/commands.py` - Command integration
- `/aider/repomap.py` - Ranking system
- `/aider/coders/context_coder.py` - Auto-discovery

The architecture is well-designed and extensible. All the pieces exist; they just need to be connected to enable autonomous file discovery.

