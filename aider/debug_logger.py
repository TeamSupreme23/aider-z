"""
Debug logger for shell command detection and other features.
Logs to a file to help diagnose issues with shell command detection.
"""

import logging
import os
from datetime import datetime

# Create logs directory if it doesn't exist
LOG_DIR = os.path.expanduser("~/.aider/debug_logs")
os.makedirs(LOG_DIR, exist_ok=True)

# Create a logger for shell command debugging
logger = logging.getLogger("aider.shell_debug")
logger.setLevel(logging.DEBUG)

# Create a logger for MCP debugging
mcp_logger = logging.getLogger("aider.mcp_debug")
mcp_logger.setLevel(logging.DEBUG)

# Create file handler for shell debug
log_file = os.path.join(LOG_DIR, "shell_debug.log")
file_handler = logging.FileHandler(log_file, mode='a')
file_handler.setLevel(logging.DEBUG)

# Create file handler for MCP debug
mcp_log_file = os.path.join(LOG_DIR, "mcp_debug.log")
mcp_file_handler = logging.FileHandler(mcp_log_file, mode='a')
mcp_file_handler.setLevel(logging.DEBUG)

# Create formatter
formatter = logging.Formatter(
    '%(asctime)s - %(name)s - %(levelname)s - %(funcName)s:%(lineno)d - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
file_handler.setFormatter(formatter)
mcp_file_handler.setFormatter(formatter)

# Add handlers to loggers
if not logger.handlers:  # Avoid adding duplicate handlers
    logger.addHandler(file_handler)
if not mcp_logger.handlers:
    mcp_logger.addHandler(mcp_file_handler)

def debug(msg, *args, **kwargs):
    """Log debug message"""
    logger.debug(msg, *args, **kwargs)

def info(msg, *args, **kwargs):
    """Log info message"""
    logger.info(msg, *args, **kwargs)

def warning(msg, *args, **kwargs):
    """Log warning message"""
    logger.warning(msg, *args, **kwargs)

def error(msg, *args, **kwargs):
    """Log error message"""
    logger.error(msg, *args, **kwargs)

def log_shell_commands(content, found_commands):
    """Log shell command detection"""
    debug(f"Response content length: {len(content)}")
    debug(f"Found {len(found_commands)} shell commands")
    for i, cmd in enumerate(found_commands):
        debug(f"  Command {i+1}: {cmd[:100]}..." if len(cmd) > 100 else f"  Command {i+1}: {cmd}")

def log_prompt_attributes(prompt_obj):
    """Log prompt object attributes"""
    info(f"Prompt class: {prompt_obj.__class__.__name__}")
    info(f"  shell_cmd_prompt length: {len(getattr(prompt_obj, 'shell_cmd_prompt', ''))}")
    info(f"  shell_cmd_prompt content: {repr(getattr(prompt_obj, 'shell_cmd_prompt', '')[:200])}")
    info(f"  no_shell_cmd_prompt length: {len(getattr(prompt_obj, 'no_shell_cmd_prompt', ''))}")

def log_formatted_prompt(prompt_text, label=""):
    """Log the formatted system prompt"""
    label_str = f" ({label})" if label else ""
    debug(f"Formatted system prompt{label_str} length: {len(prompt_text)}")

    # Check for shell_cmd_prompt placeholder
    if "{shell_cmd_prompt}" in prompt_text:
        debug(f"  WARNING: {{shell_cmd_prompt}} placeholder NOT replaced!")
    else:
        debug(f"  shell_cmd_prompt placeholder was replaced")

    # Look for shell command instruction in prompt
    if "```bash" in prompt_text:
        debug(f"  Found '```bash' instruction")
    else:
        debug(f"  WARNING: Did not find '```bash' instruction")

    if "suggest any shell commands" in prompt_text:
        debug(f"  Found 'suggest any shell commands' instruction")
    else:
        debug(f"  WARNING: Did not find 'suggest any shell commands' instruction")

    # Check for shell_cmd_reminder content
    if "Examples of when to suggest shell commands" in prompt_text:
        debug(f"  Found shell_cmd_reminder content in formatted prompt")
    else:
        debug(f"  WARNING: Did not find shell_cmd_reminder content in formatted prompt")

def log_response_content(content):
    """Log AI response content"""
    info(f"AI response length: {len(content)} characters")

    # Check for various code block markers
    markers = ["```bash", "```sh", "```shell", "bashpip", "bash pip"]
    for marker in markers:
        count = content.count(marker)
        if count > 0:
            debug(f"Found {count} occurrences of '{marker}'")

print(f"Debug logger initialized. Logging to: {log_file}")
print(f"MCP debug logger initialized. Logging to: {mcp_log_file}")

# MCP-specific logging functions
def mcp_debug(msg, *args, **kwargs):
    """Log MCP debug message"""
    mcp_logger.debug(msg, *args, **kwargs)

def mcp_info(msg, *args, **kwargs):
    """Log MCP info message"""
    mcp_logger.info(msg, *args, **kwargs)

def mcp_warning(msg, *args, **kwargs):
    """Log MCP warning message"""
    mcp_logger.warning(msg, *args, **kwargs)

def mcp_error(msg, *args, **kwargs):
    """Log MCP error message"""
    mcp_logger.error(msg, *args, **kwargs)
