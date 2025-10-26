# Aider File Management - Quick Reference Guide

## File Data Flow Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                         USER INTERACTION                        │
│  Terminal Input (/add, /drop, chat messages, /read-only)        │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│                      COMMANDS SYSTEM                            │
│ (/aider/commands.py)                                            │
│  - cmd_add() - Manual file selection                            │
│  - cmd_drop() - Remove from context                             │
│  - cmd_read_only() - Add reference files                        │
│  - cmd_ls() - List available files                              │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│                    CODER MAIN STATE                             │
│ (/aider/coders/base_coder.py)                                   │
│                                                                 │
│ ┌─────────────────────────────────────────────────────────┐   │
│ │ abs_fnames = {'/path/to/file1.py', '/path/to/file2.py'} │   │
│ │ abs_read_only_fnames = {'/path/to/lib.py'}              │   │
│ │ repo = GitRepo(...)                                      │   │
│ └─────────────────────────────────────────────────────────┘   │
│                                                                 │
│ Key Methods:                                                    │
│ - add_rel_fname() - Internal add operation                      │
│ - drop_rel_fname() - Internal remove operation                  │
│ - get_inchat_relative_files() - List what's in chat            │
│ - get_all_relative_files() - List all available                │
│ - get_addable_relative_files() - List candidates for /add      │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│                     FILE DISCOVERY LAYER                        │
│ (/aider/repomap.py, /aider/coders/context_coder.py)           │
│                                                                 │
│ RepoMap (AST-based)                                             │
│ ├─ Parses code structure (grep_ast)                            │
│ ├─ Extracts functions, classes, methods                        │
│ ├─ Caches in .aider.tags.cache/                               │
│ └─ Returns ranked overview (INFORMATIONAL ONLY)               │
│                                                                 │
│ ContextCoder (Autonomous Mode)                                 │
│ ├─ Analyzes LLM output for file mentions                       │
│ ├─ Compares against currently added files                      │
│ ├─ Updates abs_fnames if mismatch detected                    │
│ └─ Reflects back to LLM (max 3 iterations)                    │
│                                                                 │
│ File Mention Detection                                          │
│ ├─ get_file_mentions() - Text-based word matching              │
│ ├─ get_ident_filename_matches() - Code identifier → files      │
│ └─ Limited precision (5+ char identifiers)                     │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│                    MESSAGE FORMATTING                           │
│ (/aider/coders/chat_chunks.py)                                  │
│                                                                 │
│ 1. System Prompt - Edit format instructions                     │
│ 2. Repo Map - Repository structure (read-only hint)            │
│ 3. Read-Only Files - Reference content with markers            │
│ 4. Chat Files - Files to edit with markers                     │
│ 5. Chat History - Previous conversation context                │
│ 6. Current Input - User's latest message                       │
│                                                                 │
│ Only abs_fnames and abs_read_only_fnames content included!     │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│                     LLM API CALL                                │
│ (/aider/llm.py, /aider/models.py)                              │
│  - Sends formatted message list                                 │
│  - Receives edit instructions                                   │
│  - Processes streaming response                                 │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│                   EDIT APPLICATION                              │
│ (/aider/coders/editblock_coder.py, wholefile_coder.py, etc.)  │
│                                                                 │
│ get_edits() - Parse LLM response for edit blocks                │
│   ↓                                                              │
│ apply_edits() - Apply changes to disk                           │
│   ├─ Validate file is in abs_fnames                            │
│   ├─ Perform search/replace (format-dependent)                 │
│   ├─ Handle failures with user feedback                        │
│   └─ Write to disk via io.write_text()                         │
│                                                                 │
│ LIMITATION: Cannot edit files not in abs_fnames!               │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│                    FILE I/O OPERATIONS                          │
│ (/aider/io.py - InputOutput class)                             │
│                                                                 │
│ read_text(filename)                                             │
│   └─ Handles images (base64), encoding errors, missing files    │
│                                                                 │
│ write_text(filename, content)                                   │
│   └─ Retry logic for locked files, respect encoding            │
│                                                                 │
│ Git Integration (/aider/repo.py - GitRepo)                     │
│   ├─ get_tracked_files() - All git-tracked files              │
│   ├─ git_ignored_file() - Check gitignore                      │
│   ├─ ignored_file() - Check .aiderignore                       │
│   └─ is_dirty() - Check for uncommitted changes                │
└─────────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│                    GIT & COMMITS                                │
│ Auto-commit changes if auto_commits=True                        │
│ Skip if file in repo.need_commit_before_edits                   │
└─────────────────────────────────────────────────────────────────┘
```

---

## Key Classes and Responsibilities

### Coder (base_coder.py) - 2000+ lines
**Responsibility:** File management + message orchestration

**Core Attributes:**
- `abs_fnames` - Set of editable file absolute paths
- `abs_read_only_fnames` - Set of reference file absolute paths
- `root` - Repository root directory
- `repo` - GitRepo instance
- `cur_messages` - Current conversation
- `done_messages` - Previous turns
- `io` - InputOutput instance
- `main_model` - Active LLM model
- `repo_map` - RepoMap instance (optional)

**Critical Methods:**
- `run()` - Main interactive loop
- `run_one(msg)` - Process single message
- `send_message()` - Format and send to LLM
- `format_messages()` - Build complete message list
- `apply_edits()` - Write changes to disk
- `get_inchat_relative_files()` - List editable files
- `get_all_relative_files()` - List available files
- `get_file_mentions()` - Extract filenames from text

---

### Commands (commands.py) - 1695 lines
**Responsibility:** User command parsing and execution

**Key Commands (for file management):**

| Command | Flow | Limitation |
|---------|------|-----------|
| `/add PATTERN` | Parse → glob → validate → add to abs_fnames | Requires user knowing pattern |
| `/drop [PATTERN]` | Remove from abs_fnames (or clear all) | User must explicitly drop |
| `/read-only PATTERN` | Similar to /add but adds to abs_read_only_fnames | Requires explicit user command |
| `/ls` | Show chat files vs. available files | Informational only |
| `/reset` | Clear abs_fnames and chat history | Nuclear option |
| `/save FILE` | Save `/add` commands to reconstruct session | Manual save required |
| `/load FILE` | Execute `/add` commands from file | Manual load required |

**Important Implementation Details:**
- `glob_filtered_to_repo()` - Handles glob patterns
- `parse_quoted_filenames()` - Parses command arguments
- `expand_subdir()` - Recursively expands directories
- All validation happens here (gitignore, git-tracked, etc.)

---

### RepoMap (repomap.py) - 700+ lines
**Responsibility:** Code structure analysis and ranking

**Key Features:**
- Uses `grep_ast` library for AST parsing
- Extracts: functions, classes, methods, variables
- Caches results in `.aider.tags.cache.v{VERSION}/`
- Generates "map" of repository showing related code
- **INFORMATIONAL ONLY** - doesn't auto-add files

**How It Works:**
1. Parse all code files in repo (cached)
2. Extract semantic tags (functions, classes)
3. Rank by relevance to current message
4. Include top N items within token budget
5. Add to message as read-only context

**Ranking Algorithm:**
1. Extract mentioned filenames/identifiers from user text
2. Score each file based on:
   - Exact filename matches
   - Identifier matches in file
   - Proximity to mentioned files
3. Return ranked list within map_tokens budget

---

### InputOutput (io.py) - 1500+ lines
**Responsibility:** User I/O and file access

**Key Methods:**
```python
read_text(filename)          # Read file content
write_text(filename, content)  # Write file content
get_input(...)               # Get user input with autocomplete
confirm_ask(msg)             # Yes/no prompts
tool_output(msg)             # Display to user
tool_error(msg)              # Error messages
```

**Autocomplete Integration:**
- Suggests files from `abs_fnames`
- Suggests files from `addable_relative_files`
- Suggests commands
- Suggests code identifiers (tokenized on demand)

---

### GitRepo (repo.py) - 1000+ lines
**Responsibility:** Git operations and file filtering

**Key Methods:**
```python
get_tracked_files()          # All git-tracked files
git_ignored_file(path)       # Check gitignore
ignored_file(path)           # Check .aiderignore
is_dirty(path)               # Uncommitted changes
commit(message=...)          # Create commit
```

**Integration Points:**
- `cmd_add()` uses `get_tracked_files()` to filter candidates
- `cmd_add()` checks `git_ignored_file()` for each file
- `.aiderignore` file support (like `.gitignore`)
- Automatic `.gitignore` entry for `.aider*`

---

## File Selection Flow Comparison

### Current Manual Flow
```
User types: /add src/*.py
     ↓
Commands.cmd_add() parses
     ↓
glob_filtered_to_repo("src/*.py") matches files
     ↓
Filter: Check gitignore, aiderignore, git-tracked
     ↓
Validate: Read file content, check permissions
     ↓
Add to abs_fnames
     ↓
Next message includes files in context
```

### ContextCoder (Reflection) Flow
```
User provides initial message
     ↓
LLM suggests files needed
     ↓
ContextCoder.reply_completed() extracts mentions
     ↓
Compare: LLM mentions ≠ abs_fnames?
     ↓
If yes: Update abs_fnames to LLM mentions
     ↓
Return "Try again" prompt
     ↓
Go back to LLM with updated files
     ↓
Max 3 reflections per message
```

### Proposed Autonomous Flow (MISSING)
```
User provides initial message
     ↓
[NEW] Analyze user intent → identify base files
     ↓
[NEW] Parse imports in base files → dependency graph
     ↓
[NEW] RepoMap suggests related structures
     ↓
[NEW] Smart ranking: (importance × relevance × size)
     ↓
[NEW] Auto-select top N files within token budget
     ↓
Format message with selected files
     ↓
LLM processes with full context
     ↓
Auto-detect if edits reference missing files
     ↓
Offer to add → re-run if needed
```

---

## Constraints That Prevent Autonomy

### 1. Manual `/add` Required
**Why:** Only `abs_fnames` are visible to LLM
**Impact:** Cannot discover needed files automatically
**Needed Fix:** Dependency parser + auto-ranking system

### 2. RepoMap Read-Only
**Why:** RepoMap included as system message, not files
**Impact:** Structure visible but files not selectable
**Needed Fix:** Convert high-ranking repo map items to files

### 3. ContextCoder Limited to Reflection
**Why:** Only compares current message mentions, max 3 loops
**Impact:** Cannot analyze edit results or dependencies
**Needed Fix:** Post-edit analysis + dependency extraction

### 4. No Import Analysis
**Why:** No code parsing for dependencies
**Impact:** Cannot find files that MUST be edited together
**Needed Fix:** Python/JS/TS/Go import parser

### 5. No Call Graph
**Why:** RepoMap only shows structure, not relationships
**Impact:** Cannot rank by interaction importance
**Needed Fix:** Call/reference graph construction

### 6. Context Budget Not Intelligent
**Why:** Token budget is all-or-nothing
**Impact:** Important files might be dropped for large ones
**Needed Fix:** Semantic prioritization + smart allocation

---

## Extension Points (Where to Add Features)

### For Autonomous File Discovery
1. **In `base_coder.py:format_messages()`**
   - Before building message list
   - Analyze user intent
   - Call dependency analyzer
   - Rank and select files
   
2. **New module: `dep_analyzer.py`**
   - Parse import statements
   - Build dependency graph
   - Score file importance
   
3. **In `repomap.py`**
   - Add `suggest_files()` method
   - Return ranked file list
   - Consider imports + mentions

4. **In `context_coder.py:reply_completed()`**
   - Extend beyond reply mentions
   - Check if edits reference missing files
   - Auto-add as read-only if useful

### For Autonomous Context Selection
1. **In `Coder` initialization**
   - Add file scoring system
   - Implement token budgeter
   - Sort files by importance
   
2. **In `apply_edits()`**
   - Analyze imports in new code
   - Check against missing files
   - Warn or auto-add

3. **In `format_messages()`**
   - Implement intelligent order
   - Most critical files first
   - Drop strategy if over budget

---

## Critical Data Structures

### abs_fnames (Set[str])
**Purpose:** Files LLM can edit
**Usage:** 
- Checked before applying edits
- Formatted into message context
- Visible in `/ls` output
**Type:** Set (for O(1) lookup)

### abs_read_only_fnames (Set[str])
**Purpose:** Files LLM can see but not edit
**Usage:**
- Formatted as reference in messages
- Marked with "read-only" in output
- Cannot be edited via apply_edits()
**Type:** Set (for O(1) lookup)

### repo (GitRepo instance)
**Purpose:** Access git metadata
**Usage:**
- Get all tracked files
- Check gitignore status
- Validate file edits
- Manage commits
**Key Methods:**
- `get_tracked_files()` → List[str]
- `git_ignored_file(path)` → bool
- `ignored_file(path)` → bool
- `is_dirty(path)` → bool

### cur_messages (List[Dict])
**Purpose:** Current conversation
**Format:** `[{"role": "user"|"assistant", "content": str}, ...]`
**Usage:**
- Sent to LLM as context
- Analyzed for file mentions
- Auto-truncated if over tokens

### repo_map (RepoMap instance)
**Purpose:** Code structure overview
**Usage:**
- Generates ranked repository map
- Included in messages as hint
- Used for file suggestion
**LIMITATION:** Informational only, doesn't add files

---

## Gotchas and Non-Obvious Behaviors

1. **Files Must Be Git-Tracked**
   - By default, only git-tracked files can be added
   - Use `--add-gitignore-files` to allow ignored files
   - New files auto-created only with user confirmation

2. **Path Normalization Matters**
   - `abs_root_path()` caches conversions
   - Relative paths converted relative to repo root
   - Absolute paths must be under repo root

3. **RepoMap Costs Tokens**
   - RepoMap.max_map_tokens = ~1024 by default
   - Can be disabled with `--map-tokens=0`
   - Auto-refreshed only in "context" mode

4. **ContextCoder Not Default**
   - Type `/context` to enter reflection mode
   - Or use `--chat-mode=context`
   - Max 3 reflections per message

5. **Image Files Handled Specially**
   - Base64 encoded for vision models
   - Not all models support images
   - Checked against model capabilities

6. **Command Parsing is Sequential**
   - Commands in message processed in order
   - `/add X /drop Y /add Z` executes as sequence
   - No atomic transactions

7. **Dry-Run Mode Useful for Testing**
   - `apply_edits(dry_run=True)` doesn't write
   - Validates without changing files
   - Used in some workflows

---

## File System Architecture Summary

**Question:** How does Aider decide what the LLM can see?

**Answer:** 
1. Only files in `abs_fnames` (editable)
2. Plus files in `abs_read_only_fnames` (reference)
3. Plus RepoMap (structure hint)
4. Plus git history/diffs

**Question:** How does the LLM edit files?

**Answer:**
1. LLM outputs edits in configured format
2. Coder parses edits from response
3. Validates file is in `abs_fnames`
4. Applies changes to disk
5. User confirms via git commit

**Question:** What prevents autonomous file discovery?

**Answer:**
1. `abs_fnames` only includes user-explicitly-added files
2. No automatic dependency resolution
3. RepoMap informational only
4. No post-edit analysis for missing files
5. ContextCoder limited to reflection loops

**Question:** What would enable it?

**Answer:**
1. Import parser → dependency graph
2. Smart file ranking system
3. Auto-add based on dependencies
4. Post-edit analysis for missing files
5. Intelligent token budget management

