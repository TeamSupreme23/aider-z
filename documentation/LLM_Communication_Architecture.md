# Aider LLM Communication Architecture
## Technical Specification Document

**Version:** 1.0
**Date:** 2025-10-27
**Author:** System Architecture Analysis

---

## Table of Contents

1. [Executive Summary](#executive-summary)
2. [System Overview](#system-overview)
3. [Core Components](#core-components)
4. [Message Flow Architecture](#message-flow-architecture)
5. [Conversation Management](#conversation-management)
6. [Loop Controls and Limits](#loop-controls-and-limits)
7. [Coder Type Implementations](#coder-type-implementations)
8. [Error Handling and Retry Logic](#error-handling-and-retry-logic)
9. [Performance Optimizations](#performance-optimizations)
10. [Technical Reference](#technical-reference)

---

## Executive Summary

Aider implements a sophisticated LLM communication architecture that orchestrates multi-turn conversations between users and Large Language Models (LLMs) for collaborative code editing. The system uses the `litellm` library as its API layer, supports multiple edit formats, manages conversation history intelligently, and implements careful controls to prevent infinite loops while maximizing productivity.

### Key Characteristics

- **Communication Layer:** LiteLLM library (lazy-loaded)
- **Message Format:** OpenAI-compatible JSON format
- **Response Modes:** Streaming and non-streaming
- **Edit Formats:** SEARCH/REPLACE blocks, whole files, unified diffs, patches, JSON functions
- **Reflection Limit:** Hard cap of 3 automatic file additions per user message
- **Context Management:** Two-tier history system with automatic summarization
- **Retry Logic:** Exponential backoff up to 60 seconds
- **Cache Strategy:** Prompt cache warming with 5-minute window

---

## System Overview

### Architecture Layers

```
┌─────────────────────────────────────────────────────────┐
│                     User Interface                       │
│                   (aider/main.py)                        │
└─────────────────────┬───────────────────────────────────┘
                      │
┌─────────────────────▼───────────────────────────────────┐
│                 Coder Orchestration                      │
│              (aider/coders/base_coder.py)                │
│  • Message formatting                                    │
│  • History management                                    │
│  • Loop control                                          │
│  • Token checking                                        │
└─────────────────────┬───────────────────────────────────┘
                      │
┌─────────────────────▼───────────────────────────────────┐
│              Model Communication Layer                   │
│                 (aider/models.py)                        │
│  • Parameter preparation                                 │
│  • Request hashing                                       │
│  • Response parsing                                      │
└─────────────────────┬───────────────────────────────────┘
                      │
┌─────────────────────▼───────────────────────────────────┐
│                  LiteLLM API Layer                       │
│                   (aider/llm.py)                         │
│  • Lazy module loading                                   │
│  • API provider abstraction                              │
└─────────────────────┬───────────────────────────────────┘
                      │
              ┌───────┴────────┐
              │                │
    ┌─────────▼──────┐  ┌─────▼──────────┐
    │   OpenAI API   │  │  Anthropic API │  ... (other providers)
    └────────────────┘  └────────────────┘
```

### Data Flow Sequence

```
User Input
    │
    ├─> run() - Main interactive loop (base_coder.py:878)
    │
    ├─> run_one() - Single message processing (base_coder.py:926)
    │
    ├─> send_message() - Message orchestration (base_coder.py:1436)
    │     │
    │     ├─> format_messages() - Construct message array (base_coder.py:1350)
    │     │
    │     └─> send() - LLM API call (base_coder.py:1938)
    │           │
    │           └─> model.send_completion() - API invocation (models.py:949)
    │                 │
    │                 └─> litellm.completion() - Provider API (models.py:1000)
    │
    ├─> show_send_output[_stream]() - Response processing (base_coder.py:1991/2055)
    │
    ├─> get_edits() - Parse LLM response (coder-specific)
    │
    ├─> apply_edits() - Write to files (coder-specific)
    │
    └─> add_assistant_reply_to_cur_messages() - Update history (base_coder.py:1804)
```

---

## Core Components

### 1. LLM API Layer (`aider/llm.py`)

**Purpose:** Lazy-load the LiteLLM library to avoid expensive imports until needed.

**Key Implementation:**
```python
class LazyLiteLLM:
    def __init__(self):
        self._lazy_module = None

    @property
    def completion(self):
        if self._lazy_module is None:
            import litellm
            litellm.suppress_debug_info = True
            litellm.set_verbose = False
            self._lazy_module = litellm
        return self._lazy_module.completion
```

**Location:** `aider/llm.py:1-48`

**Design Rationale:**
- Defers import cost until first LLM call
- Configures production mode settings (suppresses debug output)
- Single instantiation pattern for module loading

---

### 2. Model Management (`aider/models.py`)

**Purpose:** Handles model-specific configurations and API communication.

**Key Method: `send_completion()`**

**Location:** `aider/models.py:949-1001`

**Responsibilities:**
1. Prepare API call parameters (messages, temperature, tools, etc.)
2. Create request hash for tracking
3. Invoke `litellm.completion()`
4. Handle streaming vs. non-streaming responses
5. Return completion object

**Example Code:**
```python
def send_completion(self, messages, functions, stream, temperature=None):
    kwargs = dict(
        model=self.name,
        messages=messages,
        temperature=temperature or self.get_temperature(),
        stream=stream,
        timeout=timeout,
        extra_headers=self.extra_headers,
    )

    if functions:
        kwargs["tools"] = [dict(type="function", function=f) for f in functions]

    # Hash request for tracking
    hash_object = hashlib.sha1(str(kwargs).encode())

    # Make API call
    res = litellm.completion(**kwargs)
    return res
```

**Supported Parameters:**
- `model`: Model identifier (e.g., "gpt-4", "claude-3-opus")
- `messages`: Array of conversation messages
- `temperature`: Randomness control (0.0-1.0)
- `stream`: Boolean for streaming responses
- `timeout`: Maximum wait time for response
- `tools`: Function calling definitions
- `extra_headers`: Provider-specific headers (e.g., Anthropic cache control)

---

### 3. Base Coder (`aider/coders/base_coder.py`)

**Purpose:** Core orchestration class for all LLM interactions.

**Key Attributes:**
```python
class Coder:
    cur_messages = []        # Current conversation messages
    done_messages = []       # Archived conversation history
    num_reflections = 0      # Counter for reflection loop
    max_reflections = 3      # Hard limit on reflections
    partial_response_content = ""  # Accumulated LLM response text
    partial_response_function_call = None  # Function call from LLM
```

**Critical Methods:**

#### `run()` - Main Interactive Loop
**Location:** `base_coder.py:878-895`

```python
def run(self, with_message=None):
    """Infinite loop for interactive chat sessions"""
    while True:
        user_message = self.io.get_input()
        if not user_message:
            continue

        if user_message.startswith('/'):
            # Handle slash commands
            continue

        self.run_one(user_message)
```

#### `run_one()` - Single User Message
**Location:** `base_coder.py:926-946`

```python
def run_one(self, user_message, preproc=True):
    """Process one user message, handling reflection loops"""
    self.init_before_message()
    message = self.preproc_user_input(user_message)

    while message:
        self.reflected_message = None
        list(self.send_message(message))

        if not self.reflected_message:
            break  # Normal completion

        # Reflection: LLM requested files
        if self.num_reflections >= self.max_reflections:
            self.io.tool_warning(
                f"Only {self.max_reflections} reflections allowed, stopping."
            )
            return

        self.num_reflections += 1
        message = self.reflected_message
```

**Reflection Definition:** When the LLM's response includes a request to add files to the conversation, Aider automatically adds those files and sends a follow-up message. This counts as a "reflection."

#### `send_message()` - Message Orchestration
**Location:** `base_coder.py:1436-1540`

```python
def send_message(self, inp):
    """Main orchestration method for sending messages to LLM"""
    # Add user message to conversation
    self.cur_messages += [dict(role="user", content=inp)]

    # Format all messages (system prompt + history + current)
    chunks = self.format_messages()
    messages = chunks.all_messages()

    # Check token limits
    if not self.check_tokens(messages):
        return

    # Retry loop with exponential backoff
    retry_delay = 0.125
    while True:
        try:
            yield from self.send(messages, functions=self.functions)
            break
        except litellm_exceptions as err:
            if should_retry(err):
                time.sleep(retry_delay)
                retry_delay *= 2
                if retry_delay > RETRY_TIMEOUT:
                    raise
            else:
                raise

    # Add assistant response to conversation
    self.add_assistant_reply_to_cur_messages()
```

#### `send()` - Core LLM Call
**Location:** `base_coder.py:1938-1990`

```python
def send(self, messages, functions=None):
    """Make the actual API call to the LLM"""
    # Call model's send_completion method
    completion = self.main_model.send_completion(
        messages=messages,
        functions=functions,
        stream=self.stream,
        temperature=self.temperature
    )

    # Handle response (streaming or non-streaming)
    if self.stream:
        yield from self.show_send_output_stream(completion)
    else:
        self.show_send_output(completion)
```

---

## Message Flow Architecture

### Message Structure

Aider uses OpenAI's standard message format:

```python
{
    "role": "user" | "assistant" | "system",
    "content": str | list,  # Text or structured content
    "function_call": dict,  # Optional: for function calling
    "tool_calls": list,     # Optional: for tool calling
}
```

### Message Assembly Pipeline

#### Stage 1: Choose Fence Markers
**Location:** `base_coder.py:644-690`

Determines code block delimiters to avoid conflicts:
```python
def choose_fence(self):
    """Select fence markers that won't conflict with code content"""
    # Try triple backticks first
    fence = "```"
    if self.fence_in_any_file(fence):
        fence = "~~~"  # Fallback to tildes
    return fence
```

#### Stage 2: Format Chat Chunks
**Location:** `base_coder.py:1243-1355`

Assembles message components:

```python
def format_messages(self):
    """Build complete message array for LLM"""
    chunks = ChatChunks()

    # 1. System prompt
    chunks.system = self.gpt_prompts.main_system

    # 2. Example messages (if any)
    chunks.example_messages = self.gpt_prompts.example_messages

    # 3. Done messages (conversation history)
    chunks.done_messages = self.done_messages

    # 4. Repository context
    chunks.repo_content = self.get_repo_map()

    # 5. Read-only file references
    chunks.readonly_files = self.format_readonly_files()

    # 6. Editable file contents
    chunks.chat_files = self.format_chat_files()

    # 7. Current messages (user input + any responses)
    chunks.cur_messages = self.cur_messages

    # 8. System reminder (if space available)
    chunks.reminder = self.gpt_prompts.system_reminder

    return chunks
```

#### Stage 3: Combine and Finalize
**Location:** `chat_chunks.py:16-26`

```python
class ChatChunks:
    def all_messages(self):
        """Combine all chunks into final message array"""
        messages = []

        if self.system:
            messages.append(dict(role="system", content=self.system))

        if self.example_messages:
            messages.extend(self.example_messages)

        if self.done_messages:
            messages.extend(self.done_messages)

        # Add context chunks (repo map, files, etc.)
        context = self.build_context()
        if context:
            messages.append(dict(role="user", content=context))

        messages.extend(self.cur_messages)

        if self.reminder:
            messages.append(dict(role="system", content=self.reminder))

        return messages
```

### Message Size and Token Management

#### Token Counting
**Location:** `base_coder.py:1413-1434`

```python
def check_tokens(self, messages):
    """Verify messages fit within model's context window"""
    input_tokens = self.main_model.token_count(messages)
    max_input_tokens = self.main_model.info.get("max_input_tokens", 0)

    if max_input_tokens and input_tokens >= max_input_tokens:
        self.io.tool_error(
            f"Chat context of {input_tokens:,} tokens "
            f"exceeds {max_input_tokens:,} limit!"
        )

        if not self.io.confirm_ask("Try to proceed anyway?"):
            return False

    return True
```

#### Context Window Exceeded Handling

When the context window is exceeded:
1. User is warned with token counts
2. Option to proceed anyway (may fail)
3. Automatic summarization triggered for next message
4. No retry on `ContextWindowExceededError`

---

## Conversation Management

### Two-Tier History System

Aider maintains conversation history in two separate lists:

```python
cur_messages = []   # Current exchange (sent with every request)
done_messages = []  # Archived history (may be summarized)
```

#### Current Messages (`cur_messages`)
- Contains messages for the ongoing exchange
- Always includes latest user input and assistant responses
- Cleared after each exchange completes
- Never summarized

#### Done Messages (`done_messages`)
- Contains completed exchanges
- Grows over time as conversation continues
- Subject to automatic summarization when too large
- Loaded from chat history file on startup

### History Flow Lifecycle

```
User sends message
    │
    ├─> Message added to cur_messages
    │
    ├─> LLM responds
    │
    ├─> Response added to cur_messages
    │
    ├─> Exchange completes
    │
    └─> summarize_end() called:
          │
          ├─> cur_messages → done_messages (archived)
          │
          └─> cur_messages = [] (cleared for next exchange)
```

**Location:** `base_coder.py:1039-1047`

```python
def summarize_end(self):
    """Archive current messages after exchange completes"""
    self.done_messages += self.cur_messages
    self.cur_messages = []

    # Optional: Add acknowledgment
    if self.aider_commit_message or self.reflected_message:
        self.done_messages += [
            dict(role="assistant", content="Ok")
        ]
```

### Chat History Persistence

#### Loading History on Startup
**Location:** `base_coder.py:522-524`

```python
history_md = self.io.read_text(self.io.chat_history_file)
if history_md:
    self.done_messages = utils.split_chat_history_markdown(history_md)
    self.summarize_start()
```

#### Saving History After Each Exchange
**Location:** `base_coder.py:1083-1091`

```python
# Auto-save to .aider.chat.history.md
self.io.write_chat_history(
    self.format_chat_history_markdown()
)
```

### Automatic Summarization

When conversation history becomes too large, Aider automatically summarizes it to fit within the model's context window.

#### Summarization Trigger
**Location:** `base_coder.py:1026-1036`

```python
def summarize_start(self):
    """Check if summarization needed, start background thread"""
    if not self.summarizer:
        return

    if self.summarizer.too_big(self.done_messages):
        # Start background summarization
        self.summarizer_thread = threading.Thread(
            target=self.summarizer.summarize,
            args=(self.done_messages,)
        )
        self.summarizer_thread.start()
```

#### Summarization Strategy

The `ChatSummary` class (implementation in separate file) uses the LLM itself to:
1. Identify key information in old messages
2. Generate concise summaries
3. Replace verbose exchanges with condensed versions
4. Preserve critical context (file changes, decisions)

**Key Characteristics:**
- Runs in background thread (non-blocking)
- Two-phase process: `summarize_start()` → `summarize_end()`
- Thread-safe with locks
- Only summarizes `done_messages`, never `cur_messages`

---

## Loop Controls and Limits

### 1. Reflection Loop Limit

**Hard Stop:** 3 reflections per user message

**Location:** `base_coder.py:100-101, 941-946`

```python
max_reflections = 3  # Class attribute

def run_one(self, user_message, preproc=True):
    while message:
        self.reflected_message = None
        list(self.send_message(message))

        if not self.reflected_message:
            break  # Normal completion

        # Check reflection limit
        if self.num_reflections >= self.max_reflections:
            self.io.tool_warning(
                f"Only {self.max_reflections} reflections allowed, stopping."
            )
            return  # Hard stop

        self.num_reflections += 1
        message = self.reflected_message
```

**What is a Reflection?**
When the LLM's response includes a request to add files to the conversation (using the special file request format), Aider:
1. Adds those files to the chat context
2. Sends a new message to the LLM with the file contents
3. Increments `num_reflections` counter

**Why the Limit?**
- Prevents infinite loops where LLM keeps requesting more files
- Balances thoroughness with efficiency
- User can manually add more files if needed

**Can This Be Changed?**
Yes, `max_reflections` is configurable. Users can:
- Pass `--max-reflections N` on command line
- Set in `.aider.conf.yml`
- Modify in code

---

### 2. Context Window Limit

**Soft Stop:** Model's `max_input_tokens` limit

**Location:** `base_coder.py:1413-1434`

```python
def check_tokens(self, messages):
    """Verify messages fit within context window"""
    input_tokens = self.main_model.token_count(messages)
    max_input_tokens = self.main_model.info.get("max_input_tokens", 0)

    if max_input_tokens and input_tokens >= max_input_tokens:
        self.io.tool_error(
            f"Chat context of {input_tokens:,} tokens "
            f"exceeds {max_input_tokens:,} limit!"
        )

        # User can choose to continue (may fail)
        if not self.io.confirm_ask("Try to proceed anyway?"):
            return False  # Stop

    return True  # Proceed
```

**Behavior:**
- **Warning:** User is notified of token overage
- **Choice:** User can proceed anyway or cancel
- **Auto-trigger:** Summarization started for next exchange
- **No Retry:** API call that fails with `ContextWindowExceededError` stops immediately

---

### 3. Output Token Limit

**Detection:** `finish_reason == "length"`

**Location:** `base_coder.py:2064-2066, 1509-1522`

```python
# In streaming response handler
if chunk.choices[0].finish_reason == "length":
    raise FinishReasonLength()  # Incomplete response

# In send_message() exception handler
except FinishReasonLength:
    if hasattr(self.main_model, "supports_assistant_prefill"):
        # Attempt to continue with prefill
        self.cur_messages.append(dict(
            role="assistant",
            content=self.partial_response_content
        ))
        message = "Continue..."
        continue  # Retry with continuation
    else:
        # Model doesn't support continuation
        self.io.tool_warning("Response truncated (output limit reached)")
        break  # Use partial response
```

**Behavior:**
1. Detect truncated response
2. If model supports assistant prefill (e.g., Claude):
   - Add partial response to history
   - Send "Continue..." prompt
   - LLM picks up where it left off
3. If not supported:
   - Warning displayed to user
   - Partial response still processed

---

### 4. Retry Timeout

**Hard Stop:** 60 seconds maximum retry delay

**Location:** `base_coder.py:1474-1505`

```python
RETRY_TIMEOUT = 60  # seconds

retry_delay = 0.125
while True:
    try:
        yield from self.send(messages, functions=self.functions)
        break  # Success
    except litellm_exceptions as err:
        ex_info = litellm_ex.get_ex_info(err)

        if ex_info.name == "ContextWindowExceededError":
            break  # Don't retry this error

        if ex_info.retry:
            retry_delay *= 2  # Exponential backoff

            if retry_delay > RETRY_TIMEOUT:
                # Exceeded max retry time
                should_retry = self.io.confirm_ask(
                    f"Retry again? (waited {retry_delay}s)"
                )
                if not should_retry:
                    raise  # Stop retrying
                retry_delay = 0.125  # Reset

            time.sleep(retry_delay)
        else:
            raise  # Don't retry this error
```

**Exponential Backoff:**
```
Attempt 1: 0.125s
Attempt 2: 0.25s
Attempt 3: 0.5s
Attempt 4: 1s
Attempt 5: 2s
Attempt 6: 4s
Attempt 7: 8s
Attempt 8: 16s
Attempt 9: 32s
Attempt 10: 64s → exceeds 60s limit, ask user
```

---

### 5. Infinite Loop Detection

**Response Deduplication:** Tracks request/response hashes

**Location:** `models.py:979-983, base_coder.py:2025-2030`

```python
# Request hash (before sending)
hash_object = hashlib.sha1(str(kwargs).encode())
self.chat_completion_call_hashes.append(hash_object.hexdigest())

# Response hash (after receiving)
resp_hash = dict(
    function_call=str(self.partial_response_function_call),
    content=self.partial_response_content
)
self.chat_completion_response_hashes.append(
    hashlib.sha1(str(resp_hash).encode()).hexdigest()
)
```

**Purpose:**
- Detect if LLM returns identical response repeatedly
- Identify potential infinite loops
- Enable debugging of stuck conversations

**Note:** Currently used for tracking/debugging. Not actively enforced as a hard stop.

---

## Coder Type Implementations

Aider supports multiple "edit formats" for how the LLM communicates code changes. Each format is implemented as a subclass of `Coder`.

### Class Hierarchy

```
Coder (base_coder.py)
├── EditBlockCoder (editblock_coder.py)
├── EditBlockFuncCoder (editblock_func_coder.py)
├── WholeFileCoder (wholefile_coder.py)
├── WholeFileFuncCoder (wholefile_func_coder.py)
├── UDiffCoder (udiff_coder.py)
├── PatchCoder (patch_coder.py)
├── AskCoder (ask_coder.py)
└── ArchitectCoder (architect_coder.py)
```

---

### EditBlockCoder

**Edit Format:** SEARCH/REPLACE blocks

**File:** `aider/coders/editblock_coder.py`

**How It Works:**
1. LLM returns response with SEARCH/REPLACE blocks
2. `get_edits()` parses blocks (line 21-48)
3. `apply_edits()` performs replacements (line 53-136)

**Example LLM Output:**
````
Here's the fix:

path/to/file.py
```python
<<<<<<< SEARCH
def old_function():
    return "old"
=======
def new_function():
    return "new"
>>>>>>> REPLACE
```
````

**Key Method: `get_edits()`**
**Location:** `editblock_coder.py:21-48`

```python
def get_edits(self):
    """Parse SEARCH/REPLACE blocks from LLM response"""
    content = self.partial_response_content

    # Extract file path and search/replace blocks
    edits = []
    for block in self.find_original_update_blocks(content):
        path = block.path
        search_block = block.search
        replace_block = block.replace

        edits.append(dict(
            path=path,
            search=search_block,
            replace=replace_block
        ))

    return edits
```

**Prompt Class:** `EditBlockPrompts` (editblock_prompts.py)

**Best For:**
- Surgical changes to specific sections
- Multiple small edits in one file
- Precise line-level modifications

---

### WholeFileCoder

**Edit Format:** Complete file contents

**File:** `aider/coders/wholefile_coder.py`

**How It Works:**
1. LLM returns entire file contents in code fence
2. `get_edits()` extracts file content (line 22-50)
3. File completely replaced

**Example LLM Output:**
````
Here's the updated file:

path/to/file.py
```python
def new_function():
    return "completely new file content"

def another_function():
    pass
```
````

**Key Method: `get_edits()`**
**Location:** `wholefile_coder.py:22-50`

```python
def get_edits(self):
    """Extract complete file contents from code fences"""
    content = self.partial_response_content

    # Find code blocks with file paths
    edits = []
    pattern = r'^(\S+)\n```[\w]*\n(.*?)```'

    for match in re.finditer(pattern, content, re.MULTILINE | re.DOTALL):
        path = match.group(1)
        new_content = match.group(2)

        edits.append(dict(
            path=path,
            content=new_content
        ))

    return edits
```

**Prompt Class:** `WholeFilePrompts` (wholefile_prompts.py)

**Best For:**
- Major refactoring
- New file creation
- Simple models that struggle with SEARCH/REPLACE

---

### ArchitectCoder

**Edit Format:** Two-stage planning + execution

**File:** `aider/coders/architect_coder.py`

**How It Works:**
1. **Stage 1:** Main LLM creates a plan (no file edits)
2. **Stage 2:** Separate "editor" coder executes the plan

**Key Method: `reply_completed()`**
**Location:** `architect_coder.py:11-48`

```python
def reply_completed(self):
    """Called after LLM provides plan"""
    plan = self.partial_response_content

    if not plan:
        return

    # Create a new editor coder
    from .editblock_coder import EditBlockCoder
    editor_coder = EditBlockCoder.create(
        self.main_model,
        self.edit_format,
        self.io,
        # ... other params
    )

    # Send the plan to the editor
    editor_coder.cur_messages = [
        dict(role="user", content=f"Please implement this plan:\n\n{plan}")
    ]

    # Execute
    list(editor_coder.send_message(editor_coder.cur_messages[-1]["content"]))
```

**Inheritance:** Extends `AskCoder` (no direct edits, only responses)

**Prompt Class:** `ArchitectPrompts` (architect_prompts.py)

**Best For:**
- Complex multi-file changes
- High-level reasoning models (planning) + fast models (execution)
- Budget-conscious workflows

---

### Function-Based Coders

**Edit Formats:** JSON function calling instead of text parsing

**Files:**
- `wholefile_func_coder.py`
- `editblock_func_coder.py`

**How It Works:**
1. Coders define JSON Schema for file operations
2. LLM returns structured function calls
3. No text parsing needed

**Example Function Definition:**
```python
functions = [
    {
        "name": "replace_file",
        "description": "Replace entire file contents",
        "parameters": {
            "type": "object",
            "properties": {
                "path": {"type": "string"},
                "content": {"type": "string"}
            },
            "required": ["path", "content"]
        }
    }
]
```

**Example LLM Response:**
```json
{
    "function_call": {
        "name": "replace_file",
        "arguments": {
            "path": "src/main.py",
            "content": "def main():\n    print('hello')\n"
        }
    }
}
```

**Best For:**
- Models with strong function calling support (GPT-4, Claude)
- Reducing parsing ambiguity
- Structured operations

---

## Error Handling and Retry Logic

### Exception Categories

Aider categorizes LLM API exceptions into three types:

1. **Retryable:** Transient errors (rate limits, timeouts)
2. **Non-Retryable:** Permanent errors (invalid API key, unsupported model)
3. **Special Cases:** Context window exceeded, output truncated

### Retry Flow

**Location:** `base_coder.py:1474-1505`

```python
retry_delay = 0.125
exhausted = False

while True:
    try:
        # Attempt API call
        yield from self.send(messages, functions=self.functions)
        break  # Success!

    except litellm_exceptions as err:
        ex_info = litellm_ex.get_ex_info(err)

        # Check if this error type is retryable
        if not ex_info.retry:
            self.io.tool_error(f"API Error: {ex_info.name}")
            raise  # Don't retry

        # Special case: Context window exceeded
        if ex_info.name == "ContextWindowExceededError":
            exhausted = True
            break  # Stop cleanly, trigger summarization

        # Exponential backoff
        retry_delay *= 2

        if retry_delay > RETRY_TIMEOUT:
            # Ask user if we should continue retrying
            should_retry = self.io.confirm_ask(
                f"Retry API call? (waited {retry_delay:.1f}s)"
            )
            if not should_retry:
                raise  # User chose to stop
            retry_delay = 0.125  # Reset delay

        # Wait before retry
        self.io.tool_output(f"Retrying in {retry_delay:.1f}s...")
        time.sleep(retry_delay)

# Post-loop handling
if exhausted:
    self.io.tool_warning("Context window full. Consider summarizing history.")
```

### Retry Schedule

| Attempt | Delay | Cumulative Time |
|---------|-------|-----------------|
| 1 | 0.125s | 0.125s |
| 2 | 0.25s | 0.375s |
| 3 | 0.5s | 0.875s |
| 4 | 1s | 1.875s |
| 5 | 2s | 3.875s |
| 6 | 4s | 7.875s |
| 7 | 8s | 15.875s |
| 8 | 16s | 31.875s |
| 9 | 32s | 63.875s |
| 10+ | Ask user | Paused |

### Error-Specific Handling

#### 1. Context Window Exceeded
**Behavior:**
- Stop retrying immediately
- Set `exhausted = True`
- Return gracefully (no exception)
- Trigger summarization for next message

#### 2. Output Truncated (`finish_reason == "length"`)
**Location:** `base_coder.py:1509-1522`

```python
except FinishReasonLength:
    if hasattr(self.main_model, "supports_assistant_prefill"):
        # Continue generation with prefill
        self.cur_messages.append(dict(
            role="assistant",
            content=self.partial_response_content
        ))
        message = "Continue..."
        continue  # Re-enter send loop
    else:
        # Model doesn't support continuation
        self.io.tool_warning("Response truncated (output limit reached)")
        break  # Use partial response
```

#### 3. Rate Limit Exceeded
**Behavior:**
- Retry with exponential backoff
- Respect API provider's `Retry-After` header (if provided)
- Ask user after 60s cumulative wait

#### 4. Invalid Request
**Behavior:**
- No retry
- Display error message
- Allow user to modify request

---

## Performance Optimizations

### 1. Prompt Caching

Aider supports prompt caching for providers that offer it (e.g., Anthropic Claude).

**How It Works:**
- System prompt and file contents marked as cacheable
- Provider caches these blocks for ~5 minutes
- Subsequent requests reuse cached content (faster, cheaper)

**Implementation:**
**Location:** `base_coder.py:1357-1411`

```python
def warm_cache(self, chunks):
    """Keep prompt cache alive with periodic pings"""

    if not self.main_model.cache_control:
        return  # Model doesn't support caching

    # Background thread to refresh cache
    def warm_cache_worker():
        while not self.cache_warming_stop:
            time.sleep(240)  # Every 4 minutes

            # Send lightweight request
            messages = chunks.all_messages()
            self.main_model.send_completion(
                messages=messages[:2],  # Just system prompt
                max_tokens=1  # Minimal response
            )

    self.cache_warming_thread = threading.Thread(
        target=warm_cache_worker,
        daemon=True
    )
    self.cache_warming_thread.start()
```

**Cache Control Headers:**
```python
extra_headers = {
    "anthropic-beta": "prompt-caching-2024-07-31"
}

# Mark cacheable blocks
messages = [
    {
        "role": "system",
        "content": "...",
        "cache_control": {"type": "ephemeral"}  # Cache this
    },
    # ... more messages
]
```

**Benefits:**
- **Speed:** 10-20x faster for cached content
- **Cost:** Significantly cheaper (cached tokens cost less)
- **UX:** Reduced latency for multi-turn conversations

---

### 2. Streaming Responses

**Location:** `base_coder.py:2055-2127`

```python
def show_send_output_stream(self, completion):
    """Process streaming response chunks"""
    for chunk in completion:
        # Extract reasoning (if supported)
        reasoning = chunk.choices[0].delta.reasoning_content
        if reasoning:
            self._accumulated_reasoning += reasoning

        # Extract content
        text = chunk.choices[0].delta.content or ""
        self.partial_response_content += text

        # Display to user in real-time
        self.live_incremental_response(False)

        yield text
```

**Benefits:**
- **Perceived Speed:** User sees output immediately
- **Better UX:** Real-time feedback, feels responsive
- **Early Cancellation:** User can interrupt if LLM goes off track

---

### 3. Lazy Module Loading

**Location:** `aider/llm.py:1-48`

```python
class LazyLiteLLM:
    """Defer expensive imports until first use"""
    def __init__(self):
        self._lazy_module = None

    @property
    def completion(self):
        if self._lazy_module is None:
            import litellm  # Import only when needed
            # ... configure
            self._lazy_module = litellm
        return self._lazy_module.completion
```

**Benefits:**
- **Faster Startup:** Aider starts quickly
- **Reduced Memory:** Don't load unused API clients
- **Better Testing:** Tests don't need API credentials

---

### 4. Incremental Response Rendering

For `WholeFileCoder`, Aider shows diffs in real-time as the LLM generates the response.

**Location:** `wholefile_coder.py:16-20`

```python
def render_incremental_response(self, final):
    """Show live diff as LLM generates new file content"""

    # Extract partial file content
    partial_edits = self.get_edits_from_partial_response()

    # Compute diff against current file
    for edit in partial_edits:
        old_content = self.read_file(edit['path'])
        new_content = edit['content']

        # Show colored diff
        diff = self.diff(old_content, new_content)
        self.io.tool_output(diff, highlight="diff")
```

**Benefits:**
- User sees what's changing in real-time
- Easier to interrupt if LLM goes wrong
- More engaging UX

---

## Technical Reference

### File Locations Quick Reference

| Component | File Path | Key Lines |
|-----------|-----------|-----------|
| **Core Architecture** | | |
| LLM lazy loading | `aider/llm.py` | 1-48 |
| Model management | `aider/models.py` | 949-1001 |
| Base coder | `aider/coders/base_coder.py` | Full file |
| | | |
| **Main Loop & Orchestration** | | |
| Interactive loop | `base_coder.py` | 878-895 |
| Single message | `base_coder.py` | 926-946 |
| Message sending | `base_coder.py` | 1436-1540 |
| Core LLM call | `base_coder.py` | 1938-1990 |
| | | |
| **Response Handling** | | |
| Non-streaming | `base_coder.py` | 1991-2037 |
| Streaming | `base_coder.py` | 2055-2127 |
| Add to history | `base_coder.py` | 1804-1814 |
| | | |
| **Message Formatting** | | |
| Format pipeline | `base_coder.py` | 1243-1355 |
| Chat chunks | `aider/coders/chat_chunks.py` | 1-65 |
| Fence selection | `base_coder.py` | 644-690 |
| | | |
| **History Management** | | |
| Archive messages | `base_coder.py` | 1039-1047 |
| Summarization start | `base_coder.py` | 1005-1036 |
| Load history | `base_coder.py` | 522-524 |
| | | |
| **Loop Controls** | | |
| Reflection limit | `base_coder.py` | 100-101, 941-946 |
| Token checking | `base_coder.py` | 1413-1434 |
| Retry logic | `base_coder.py` | 1474-1505 |
| Output truncation | `base_coder.py` | 1509-1522, 2064-2066 |
| Response hashing | `models.py` / `base_coder.py` | 979-983 / 2025-2030 |
| | | |
| **Coder Types** | | |
| EditBlock parser | `aider/coders/editblock_coder.py` | 21-48 |
| EditBlock apply | `aider/coders/editblock_coder.py` | 53-136 |
| WholeFile parser | `aider/coders/wholefile_coder.py` | 22-50 |
| Architect | `aider/coders/architect_coder.py` | 11-48 |
| | | |
| **Optimizations** | | |
| Prompt caching | `base_coder.py` | 1357-1411 |
| Incremental render | `wholefile_coder.py` | 16-20 |

---

### Key Constants and Configuration

```python
# Loop Limits
max_reflections = 3  # Hard limit on automatic file additions
RETRY_TIMEOUT = 60   # Maximum retry delay in seconds

# Streaming
stream = True  # Enable streaming responses by default

# Cache Warming
CACHE_REFRESH_INTERVAL = 240  # 4 minutes (for 5-minute cache TTL)

# Token Counting
# Models define their own max_input_tokens in models.py

# Temperature
default_temperature = None  # Use model's default
```

---

### Data Structures

#### Message Format
```python
{
    "role": "user" | "assistant" | "system",
    "content": str | list,
    "function_call": dict | None,  # Legacy function calling
    "tool_calls": list | None,     # Modern tool calling
    "cache_control": dict | None   # Provider-specific (Anthropic)
}
```

#### Edit Format (EditBlockCoder)
```python
{
    "path": str,           # File path
    "search": str,         # Original content
    "replace": str         # New content
}
```

#### Edit Format (WholeFileCoder)
```python
{
    "path": str,           # File path
    "content": str         # Complete new file content
}
```

#### Completion Response (Non-Streaming)
```python
{
    "choices": [
        {
            "message": {
                "role": "assistant",
                "content": str,
                "reasoning_content": str | None,  # o1-style reasoning
                "function_call": dict | None,
                "tool_calls": list | None
            },
            "finish_reason": "stop" | "length" | "function_call"
        }
    ],
    "usage": {
        "prompt_tokens": int,
        "completion_tokens": int,
        "total_tokens": int
    }
}
```

#### Completion Response (Streaming)
```python
# Each chunk:
{
    "choices": [
        {
            "delta": {
                "role": "assistant" | None,
                "content": str | None,
                "reasoning_content": str | None,
                "function_call": dict | None
            },
            "finish_reason": None | "stop" | "length" | "function_call"
        }
    ]
}
```

---

### API Call Example

**Full Flow:**

```python
# 1. User sends message
user_input = "Add a new function to calculate fibonacci"

# 2. Coder adds to current messages
self.cur_messages.append({
    "role": "user",
    "content": user_input
})

# 3. Format complete message array
messages = [
    {
        "role": "system",
        "content": "You are an expert programmer..."
    },
    {
        "role": "user",
        "content": "path/to/file.py:\n```\n[file contents]\n```"
    },
    {
        "role": "user",
        "content": "Add a new function to calculate fibonacci"
    }
]

# 4. Call LLM via litellm
completion = litellm.completion(
    model="gpt-4",
    messages=messages,
    temperature=0.7,
    stream=True
)

# 5. Process streaming response
for chunk in completion:
    text = chunk.choices[0].delta.content
    print(text, end="", flush=True)
    accumulated_response += text

# 6. Parse edits from response
edits = self.get_edits()  # Coder-specific parsing

# 7. Apply to files
for edit in edits:
    self.apply_edit(edit)

# 8. Add assistant response to history
self.cur_messages.append({
    "role": "assistant",
    "content": accumulated_response
})

# 9. Archive conversation
self.done_messages += self.cur_messages
self.cur_messages = []
```

---

### Prompt Structure Example

**Typical Message Array Sent to LLM:**

```python
[
    # System Prompt
    {
        "role": "system",
        "content": """You are an AI pair programmer using the SEARCH/REPLACE format...

        [Detailed instructions about edit format]

        ALWAYS specify a file path before each edit block."""
    },

    # Example (optional)
    {
        "role": "user",
        "content": "Change the greeting to 'Hello World'"
    },
    {
        "role": "assistant",
        "content": """Here's the change:

        main.py
        ```python
        <<<<<<< SEARCH
        print('Hi')
        =======
        print('Hello World')
        >>>>>>> REPLACE
        ```"""
    },

    # Previous conversation (done_messages)
    {
        "role": "user",
        "content": "Add a README file"
    },
    {
        "role": "assistant",
        "content": "I've created README.md..."
    },

    # Repository context
    {
        "role": "user",
        "content": """Here are the files in your repository:

        main.py
        utils.py
        tests/test_main.py"""
    },

    # File contents
    {
        "role": "user",
        "content": """main.py:
        ```python
        def main():
            print('Hello World')

        if __name__ == '__main__':
            main()
        ```"""
    },

    # Current user request
    {
        "role": "user",
        "content": "Add a new function to calculate fibonacci"
    },

    # System reminder (optional, if space available)
    {
        "role": "system",
        "content": "Remember to always specify file paths before edit blocks."
    }
]
```

---

## Answers to Key Questions

### Is There a Hard Stop on Back-and-Forths?

**Yes and No:**

#### Hard Stops:
1. **Reflection Loop:** Maximum 3 automatic file additions per user message
2. **Retry Timeout:** After 60s of retrying, user must confirm to continue
3. **User Cancellation:** User can press Ctrl+C at any time

#### Soft Stops:
1. **Context Window:** Warning when context exceeds limit, user can choose to proceed
2. **Budget Limits:** Provider-side limits (API quota, rate limits)

#### No Hard Stop:
- **Interactive Loop:** Main `run()` loop is infinite—user can chat as long as they want
- **Multi-turn Conversation:** No limit on number of separate exchanges
- **History Size:** Automatically summarized when too large, conversation continues

**Summary:** There's no hard limit on the overall conversation length. The main limits are:
- 3 reflections per user message (prevents automatic infinite loops)
- Context window size (managed via summarization)
- User can always continue or cancel

---

## Appendix: Glossary

**Terms Used in Aider LLM Communication:**

- **Coder:** Class that orchestrates LLM communication and code editing
- **Edit Format:** The syntax used by the LLM to specify code changes (SEARCH/REPLACE, whole file, etc.)
- **Reflection:** When the LLM requests additional files be added to context, triggering an automatic follow-up message
- **Current Messages (`cur_messages`):** Messages in the active exchange, sent with every request
- **Done Messages (`done_messages`):** Archived conversation history, may be summarized
- **Streaming:** API response mode where tokens arrive incrementally (vs. all at once)
- **Function Calling:** LLM returns structured JSON function calls instead of text
- **Tool Calling:** Modern term for function calling (same concept)
- **Prompt Caching:** Provider feature to cache and reuse parts of the prompt (faster, cheaper)
- **Context Window:** Maximum number of tokens the model can process in one request
- **Summarization:** Condensing old conversation history to fit within context window
- **Lazy Loading:** Deferring module imports until first use (performance optimization)
- **Exponential Backoff:** Retry strategy where delay doubles each time
- **Fence:** Code block delimiter (triple backticks or tildes)
- **Chat Chunks:** Logical sections of the message array (system, examples, history, files, etc.)
- **Assistant Prefill:** Starting the assistant's response with provided text (Claude-specific)

---

## Document Metadata

**Generated:** 2025-10-27
**Aider Version:** Based on current codebase state
**Analysis Scope:** Complete LLM communication architecture
**File Coverage:** 25+ source files analyzed

For questions or updates to this document, refer to the source code locations provided throughout.

---

**END OF TECHNICAL SPECIFICATION**
