# Aider File Management and Editing Architecture Analysis

## Overview

Aider is an interactive AI-assisted code editor that requires explicit user commands to add files to the chat. This analysis explores the current architecture, key limitations preventing autonomous file discovery, and systems that could be leveraged for enhancement.

---

## 1. Current Architecture for File Management

### 1.1 File Collections in Core Coder Class

**Location:** `/aider/coders/base_coder.py` (Lines 88-93, 391-392)

The `Coder` class maintains three key file collections:

```python
abs_fnames = None              # Set of absolute paths to editable files
abs_read_only_fnames = None   # Set of absolute paths to reference-only files  
repo = None                   # GitRepo instance for repository tracking
```

**Key Data Structures:**
- `abs_fnames`: Set of absolute file paths that can be edited by the AI
- `abs_read_only_fnames`: Set of absolute file paths visible but not editable
- Both stored as sets for O(1) lookup performance
- Root path cached (`abs_root_path_cache`) for efficiency

### 1.2 File Management Methods in Base Coder

**Location:** `/aider/coders/base_coder.py`

| Method | Purpose | Key Behavior |
|--------|---------|--------------|
| `add_rel_fname(rel_fname)` | Add file to chat | Converts relative→absolute, calls `check_added_files()` |
| `drop_rel_fname(fname)` | Remove file from chat | Removes from `abs_fnames` set |
| `get_inchat_relative_files()` | Get editable files | Returns sorted list of files in chat |
| `get_all_relative_files()` | Get all repo files | Returns all git-tracked files or inchat files |
| `get_addable_relative_files()` | Get available files | Returns: all_files - inchat_files - readonly_files |
| `abs_root_path(path)` | Path resolution | Converts relative path to absolute, uses cache |
| `get_rel_fname(fname)` | Path normalization | Converts absolute path to relative form |

### 1.3 File Addition Flow - `/add` Command

**Location:** `/aider/commands.py` (Lines 799-893)

The `/add` command orchestrates file addition through a sophisticated pipeline:

```
User Input (/add pattern) 
  → parse_quoted_filenames()
  → glob_filtered_to_repo()
  → Validate against gitignore/aiderignore
  → Check git tracking
  → Read file content
  → abs_fnames.add(abs_file_path)
  → Prompt to create if not found
```

**Key Features:**
- Supports glob patterns: `/add *.py`, `/add src/**/*.ts`
- Absolute path support: `/add /path/to/file.py`
- Directory expansion via `expand_subdir()`
- Git filter integration: `repo.get_tracked_files()`
- Gitignore validation: `repo.git_ignored_file()`
- Creates files on demand with confirmation
- Vision model support checks for images

### 1.4 File Content Access Methods

**Location:** `/aider/coders/base_coder.py` (Lines 598-670)

```python
def get_abs_fnames_content(self):
    """Generator: yields (fname, content) for files in chat"""
    # Reads actual file content
    # Drops files that can't be read
    # Handles image files separately

def get_files_content(self, fnames=None):
    """Formats file content for LLM with fence markers"""
    # Returns markdown-formatted content with triple-backticks
    # Includes relative filenames and language hints

def get_read_only_files_content(self):
    """Returns formatted read-only file content"""
    # Similar to get_files_content but for reference files
```

---

## 2. Core Chat and Coder Architecture

### 2.1 Coder Class Hierarchy

**Location:** `/aider/coders/` directory with 40+ subclasses

```
Coder (base_coder.py) - Base class with file management
├── EditBlockCoder (editblock_coder.py) - SEARCH/REPLACE blocks
├── WholFileCoder (wholefile_coder.py) - Full file rewrites
├── PatchCoder (patch_coder.py) - Unified diff format
├── UDiffCoder (udiff_coder.py) - Universal diff
├── ArchitectCoder (architect_coder.py) - Multi-model approach
├── AskCoder (ask_coder.py) - Read-only analysis mode
├── ContextCoder (context_coder.py) - Autonomous file discovery
└── HelpCoder (help_coder.py) - Interactive help system
```

Each coder has:
- `edit_format`: String identifier (e.g., "diff", "whole", "architect")
- `gpt_prompts`: Prompt templates for that edit format
- `get_edits()`: Parse LLM response for edits
- `apply_edits()`: Write changes to disk

### 2.2 Main Execution Flow

**Location:** `/aider/main.py` (400+ lines)

```
main() 
  → setup_git()
  → parse arguments
  → initialize Models (main, editor, weak)
  → create Coder via Coder.create()
  → Coder.run() - Main interactive loop
```

### 2.3 Interactive Loop - `Coder.run()`

**Location:** `/aider/coders/base_coder.py`

```python
def run(self, with_message=None, preproc=True):
    if with_message:
        # Single message mode (non-interactive)
        self.run_one(with_message, preproc)
    else:
        # Interactive loop
        while True:
            user_message = self.get_input()  # Uses InputOutput for prompt
            self.run_one(user_message, preproc)
```

### 2.4 Message Processing - `run_one()`

**Location:** `/aider/coders/base_coder.py`

```
user_input
  → preproc_user_input() - Parse commands like /add
  → send_message() - Add to cur_messages, format context
  → format_messages() - Build system + file content + chat history
  → send() - Call LLM API
  → apply_edits() - Write changes
  → format_commit_message() - If auto-commits enabled
```

### 2.5 Message Formatting - `format_messages()`

**Location:** `/aider/coders/chat_chunks.py`

Builds complete message list:
1. **System prompt** - Edit format and instructions
2. **Repo map** - Repository structure overview
3. **Read-only files** - Reference files with markers
4. **Chat files** - Editable files with markers
5. **Chat history** - Previous conversation
6. **Current message** - User's latest input

---

## 3. File Edit Mechanics

### 3.1 Edit Format System

**Location:** `/aider/coders/editblock_coder.py`, `wholefile_coder.py`, etc.

Different edit formats for different LLM styles:

| Format | Approach | Pros | Cons |
|--------|----------|------|------|
| **diff** | SEARCH/REPLACE blocks | Precise, handles large files | Whitespace sensitive |
| **whole** | Full file replacement | Simple for small files | Token heavy |
| **patch** | Unified diff format | Standard format | Complex parsing |
| **udiff** | Simplified diff | LLM friendly | Custom format |
| **architect** | Two-model process | Better for complex changes | Higher latency |

### 3.2 EditBlockCoder - SEARCH/REPLACE Implementation

**Location:** `/aider/coders/editblock_coder.py` (Lines 21-124)

```python
def apply_edits(self, edits, dry_run=False):
    """
    Apply SEARCH/REPLACE blocks to files
    
    Flow:
    1. Parse LLM response for ORIG/UPD blocks
    2. For each block:
       a. Find exact match in file
       b. Try other files in chat if primary fails
       c. Replace if match found
    3. Return list of failed edits for user feedback
    """
    failed = []
    for path, original, updated in edits:
        full_path = self.abs_root_path(path)
        
        if do_replace(full_path, content, original, updated, self.fence):
            self.io.write_text(full_path, new_content)  # Actual write
            passed.append(edit)
        else:
            failed.append(edit)
```

### 3.3 File I/O Operations

**Location:** `/aider/io.py`

```python
def read_text(self, filename, silent=False):
    """Read file with fallbacks for images and encoding errors"""
    if is_image_file(filename):
        return self.read_image(filename)  # Base64 encoding
    with open(str(filename), "r", encoding=self.encoding) as f:
        return f.read()

def write_text(self, filename, content, max_retries=5, initial_delay=0.1):
    """Write file with retry logic for locked files"""
    for attempt in range(max_retries):
        try:
            with open(str(filename), "w", encoding=self.encoding) as f:
                f.write(content)
        except BlockingIOError:
            time.sleep(delay)
            delay *= 2
```

### 3.4 File Validation During Edit

**Filters applied:**
- Git tracking status: Only tracked files (unless `--add-gitignore-files`)
- Gitignore rules: Via `repo.git_ignored_file()`
- Aiderignore rules: Via `repo.ignored_file()`
- File existence: Dropped from chat if deleted
- Image support: Checked against model capabilities

---

## 4. Existing File Discovery and Mention Mechanisms

### 4.1 RepoMap - AST-Based Code Structure Analysis

**Location:** `/aider/repomap.py` (700+ lines)

RepoMap creates semantic understanding of repository:

```python
def get_repo_map(self, chat_files, other_files, 
                 mentioned_fnames=None, mentioned_idents=None):
    """
    Generate ranked map of repository structure
    
    Features:
    - Uses grep_ast library for code parsing
    - Extracts classes, functions, methods (Tags)
    - Caches AST results in .aider.tags.cache
    - Ranks relevance by mention in current message
    - Limits output to map_tokens budget (~1k tokens)
    """
```

**Ranking Algorithm:**
1. Extract mentioned identifiers from user message
2. Match against filename basenames
3. Match against code symbols (functions, classes)
4. Return highest-ranked files within token budget

### 4.2 File Mention Detection

**Location:** `/aider/coders/base_coder.py` (Lines 678-707)

```python
def get_file_mentions(self, content, ignore_current=False):
    """
    Extract potential filenames from text
    
    Process:
    1. Split content into words
    2. Strip quotes and punctuation
    3. Match against all_relative_files
    4. Skip common English words (via basename length heuristic)
    5. Return set of matching filenames
    """
    words = set(word.rstrip(",.!;:?") for word in content.split())
    addable_fnames = self.get_addable_relative_files()
    
    # Match word → filename
    matching = [f for f in addable_fnames if f.endswith(word)]
    return matching
```

### 4.3 Identifier Matching

**Location:** `/aider/coders/base_coder.py` (Lines 684-707)

```python
def get_ident_filename_matches(self, idents):
    """
    Match code identifiers to filenames
    
    Logic:
    - Extract filename stems (e.g., "auth" from "auth.py")
    - Match identifiers ≥5 chars to stems
    - Case-insensitive matching
    - Returns files likely to be related
    """
    for ident in idents:
        if len(ident) < 5: continue
        matches.update(all_fnames[ident.lower()])
```

### 4.4 ContextCoder - Autonomous File Selection

**Location:** `/aider/coders/context_coder.py` (54 lines)

```python
class ContextCoder(Coder):
    """Identify which files need to be edited"""
    
    def reply_completed(self):
        """
        After LLM response, check if mentioned files match added files
        
        Process:
        1. Extract mentioned filenames from LLM output
        2. Compare against currently added files
        3. If mismatch, update abs_fnames to mentioned files
        4. Return "try again" prompt to refine
        5. Max 3 reflections (configurable)
        """
        current_files = set(self.get_inchat_relative_files())
        mentioned_files = set(self.get_file_mentions(response))
        
        if mentioned_files != current_files:
            # Reflect: update files and ask LLM to reconsider
            self.abs_fnames = set()
            for fname in mentioned_files:
                self.add_rel_fname(fname)
            self.reflected_message = "Try again with the updated files"
```

---

## 5. Key Classes and Modules Involved

### 5.1 Core Classes

| Class | Location | Purpose |
|-------|----------|---------|
| `Coder` | `base_coder.py` | Base for all editing modes, file/message management |
| `InputOutput` | `io.py` | User I/O, file reading/writing, prompt handling |
| `GitRepo` | `repo.py` | Git integration, commit tracking, file filtering |
| `Commands` | `commands.py` | Command parser, /add /drop /git etc |
| `RepoMap` | `repomap.py` | Repository structure analysis and ranking |
| `Model` | `models.py` | LLM interface, token counting |

### 5.2 Important Modules

| Module | Lines | Purpose |
|--------|-------|---------|
| `coders/base_coder.py` | 2000+ | File management, message building, main loop |
| `commands.py` | 1695 | Command implementations (/add, /drop, etc) |
| `repo.py` | 1000+ | Git operations, file tracking |
| `io.py` | 1500+ | Terminal I/O, file access, user prompts |
| `repomap.py` | 700+ | Code structure analysis |
| `sendchat.py` | 62 | Message validation and formatting |

### 5.3 Command System

**Location:** `/aider/commands.py` (Lines 36-200+)

Command methods follow pattern: `cmd_<name>`

Key file-related commands:
- `cmd_add()` - Add files to chat (glob pattern support)
- `cmd_drop()` - Remove files from chat
- `cmd_read_only()` - Add reference-only files
- `cmd_ls()` - List repo files and chat status
- `cmd_map()` - View repository structure
- `cmd_reset()` - Clear files and history
- `cmd_save()`/`cmd_load()` - Save/restore chat state

---

## 6. Constraints Preventing Autonomous File Access

### 6.1 Explicit Manual File Addition Required

**Issue:** Users must explicitly use `/add` to bring files into context

**Root Cause:**
- Line 799: `cmd_add()` requires user input matching available files
- File validation is strict (lines 811-893)
- Only files explicitly added to `abs_fnames` are visible to LLM
- No background discovery process

**Implications:**
- LLM cannot autonomously examine code to find dependencies
- Large refactoring requires user to know all affected files
- Multiple chat turns needed for exploratory work

### 6.2 RepoMap is Informational, Not Selective

**Issue:** RepoMap shows repository structure but doesn't auto-add files

**Root Cause:**
- RepoMap included in messages read-only (line 750-761)
- No mechanism to promote RepoMap entries to editable files
- ContextCoder requires user to trigger "context" mode explicitly
- Limited to reflection loops within single message

**Architecture Limitation:**
```python
# From base_coder.py: get_repo_messages()
# RepoMap added as informational system message
# But doesn't modify abs_fnames
repo_messages += [
    dict(role="user", content=repo_content),
    dict(role="assistant", content="Ok, I won't edit those files...")
]
# abs_fnames unchanged!
```

### 6.3 File Mention Detection Has Low Precision

**Issue:** `get_file_mentions()` uses text matching, not semantic analysis

**Limitations:**
- Word-based matching prone to false positives
- No understanding of import statements
- No dependency analysis
- No call-graph traversal
- Identifier matching requires ≥5 character names

**Example Problem:**
```python
# User: "Fix the auth bug"
# get_file_mentions() might not match "auth.py" if mentioned as "authorization"
# User must type exact filename or use glob
```

### 6.4 No Autonomous Dependency Resolution

**Issue:** No system to automatically find files that must be modified together

**Missing Capabilities:**
- No import statement parsing to find dependencies
- No cross-file reference analysis
- No type system integration
- No call-graph building
- No "ripple effect" analysis

**Example:**
```python
# If user adds "api.py" which imports from "models.py"
# The system doesn't automatically include "models.py"
# User must explicitly: /add models.py
```

### 6.5 File Access is Context-Window Limited

**Issue:** File budget determined by token limits, no semantic prioritization

**Current Approach:**
```python
# From commands.py: cmd_tokens()
# Only reports token usage, no auto-prioritization
tokens = calculate_token_usage(files)
if tokens > context_limit:
    # User must manually /drop files
    # No automatic least-important file removal
```

### 6.6 Read-Only Files Must Be Explicitly Added

**Issue:** Reference files don't auto-populate from dependencies

**Current Flow:**
```python
# User must: /read-only path/to/lib.py
# No mechanism to auto-add as read-only when dependency detected
# No "suggest additional context" feature
```

---

## 7. Existing Capabilities That Could Be Leveraged

### 7.1 Metadata Already Collected

**File Metadata Available:**
```python
# From repo.py, base_coder.py
repo.get_tracked_files()        # All git-tracked files
repo.ignored_file(path)         # Aiderignore matching
repo.git_ignored_file(path)     # Gitignore matching
repo.is_dirty(path)             # Uncommitted changes
```

### 7.2 Code Structure Analysis Exists

**RepoMap AST Extraction:**
```python
# From repomap.py
grep_ast library provides:
- Function/class/method extraction
- Line number mapping
- Scope information
- Call relationships (partial)
```

### 7.3 Message History Available

**Complete Chat Context:**
```python
# From base_coder.py
cur_messages          # Current conversation
done_messages         # Previous turns
commit_before_message # Commit points
```

### 7.4 Multiple Entry Points for Hooks

**Potential Integration Points:**
```python
# In base_coder.py
1. format_messages() - Before sending to LLM (can analyze user intent)
2. reply_completed() - After receiving LLM response (can extract needs)
3. apply_edits() - Before applying (can check for missing files)
4. run_one() - Main message loop (can orchestrate discovery)
```

### 7.5 Existing File Matching Infrastructure

**Available Utilities:**
```python
# From commands.py
glob_filtered_to_repo()  # Glob pattern handling
expand_subdir()          # Directory traversal
parse_quoted_filenames() # Argument parsing

# From base_coder.py
get_all_relative_files()      # Full file list
get_addable_relative_files()  # Available files
get_ident_filename_matches()  # Symbol-to-file mapping
```

### 7.6 Prompt System is Modular

**Architecture:**
```python
# Each Coder has configurable prompts
gpt_prompts = EditBlockPrompts()
# Can be extended to request file lists:
"Please analyze what files you need and output them..."
```

---

## 8. Systems That Would Need Modification

### 8.1 To Enable Autonomous File Discovery

**Required Changes:**

1. **Add Import/Dependency Parser**
   - Location: New module `dep_analyzer.py`
   - Scan for: `import X`, `from X import Y`, `require()`, etc.
   - Build file-to-file dependency graph
   - Rank by criticality

2. **Extend RepoMap with Auto-Selection**
   - Location: Modify `repomap.py` class
   - Add: `suggest_related_files(query_term)` method
   - Return: Ranked list of likely-needed files
   - Consider: imports, naming similarity, git history

3. **Create Smart Prompt Injection**
   - Location: Modify `format_messages()` in `base_coder.py`
   - Parse user intent before sending to LLM
   - Prompt LLM to request files
   - Auto-add based on structured response

4. **Implement Reflection Loop for Files**
   - Location: Extend `reply_completed()` logic
   - Track if edits reference files not in chat
   - Offer to add missing files
   - Re-run edits if successful

5. **Add Dependency Modification Hook**
   - Location: Modify `apply_edits()` in coder subclasses
   - Before writing, parse imports in changes
   - Check if imports point to files not in chat
   - Optionally auto-add or warn user

### 8.2 To Enable Autonomous Context Selection

**Required Changes:**

1. **Smart Token Budget Allocation**
   - Implement: `allocate_tokens_by_importance(files, budget)`
   - Factor: recency, mention count, edit frequency
   - Sort: critical first, optional last
   - Auto-drop: lowest priority if over budget

2. **Semantic File Relevance Scoring**
   - Build: `score_file_relevance(fname, message, repo_map)`
   - Consider: 
     - Mentioned identifiers in user text
     - Import statements
     - Call graph proximity
     - Naming similarity

3. **Predictive File Preloading**
   - Hook: Before `send_message()`
   - Analyze: What might LLM need next?
   - Preload: High-probability dependencies
   - Cache: Using disk/memory

### 8.3 Files Currently Blocking Autonomous Operation

| File | Issue | Could Modify |
|------|-------|---------------|
| `commands.py:cmd_add()` | Requires explicit user input | Add auto-discovery backend |
| `base_coder.py:format_messages()` | Includes repo map read-only | Promote entries to editable |
| `context_coder.py:reply_completed()` | Limited to reflection | Extend with dependency checking |
| `repomap.py:get_repo_map()` | Informational only | Add selectivity scoring |

---

## 9. Summary: Current vs. Needed Architecture

### Current State
```
User Input 
  → /add [explicit pattern]
  → Query repo.get_tracked_files()
  → Validate & add to abs_fnames
  → Message formats with what's explicitly in chat
  → LLM processes only visible files
  → Edit result written directly
  → User manually adds missing files if edits fail
```

### Proposed Autonomous State
```
User Input
  → Analyze intent (what does user want?)
  → Identify base file to modify
  → Use dependency analyzer to find imports
  → Use RepoMap to find related structures
  → Use git history to find frequently-co-modified files
  → Intelligently rank and select files
  → Include in message with confidence scores
  → LLM works with full context
  → Edits use full context
  → Validate edits against all changes
  → Offer to add related files if found in diffs
```

---

## Appendix: Key File Locations Reference

**Core Architecture:**
- `/aider/coders/base_coder.py` - Main Coder class
- `/aider/commands.py` - Command system
- `/aider/io.py` - I/O and file access
- `/aider/repo.py` - Git integration

**File Discovery:**
- `/aider/repomap.py` - Code structure analysis
- `/aider/coders/context_coder.py` - Autonomous file selection
- `/aider/special.py` - File filtering utilities

**Edit Implementation:**
- `/aider/coders/editblock_coder.py` - SEARCH/REPLACE
- `/aider/coders/wholefile_coder.py` - Full file edits
- `/aider/coders/patch_coder.py` - Diff-based edits

**Configuration & Models:**
- `/aider/models.py` - Model definitions
- `/aider/llm.py` - LLM interface
- `/aider/args.py` - Command-line arguments

