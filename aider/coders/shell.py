shell_cmd_prompt = """
═══════════════════════════════════════════════════════════════════════════════
🚨 CRITICAL: Shell Command Format Requirements 🚨
═══════════════════════════════════════════════════════════════════════════════

When you want to suggest a shell command, YOU MUST ALWAYS use this format:

```bash
command here
```

EXAMPLE - This is the ONLY correct format:
User: "run the project"
You: "Here's how to run it:

```bash
python main.py
```
"

❌ WRONG - These formats will NOT work:
- Plain text: "run python main.py"
- Inline code: `python main.py`
- Numbered list: "1. Run python main.py"
- Without bash tag: ```python main.py```

✅ RIGHT - Always use bash code blocks:
```bash
python main.py
```

**When to use bash blocks**:
- User says "run", "execute", "start", "build", "test"
- After you make code changes that need testing
- When suggesting how to see the results of your changes
- When dependencies need to be installed

The user will be prompted to approve commands before they run.

System info:
{platform}

Examples of when to suggest shell commands:
- If you added a feature that needs a build command, suggest how to build it
- If you changed a CLI program, suggest the command to run it to see the new behavior
- If you added a test, suggest how to run it with the testing tool used by the project
- If your code changes add new dependencies, suggest the command to install them
- Suggest OS-appropriate commands to delete or rename files/directories when relevant
- If the user asks to "run" something, provide the command in a bash code block
- Etc.
"""  # noqa

no_shell_cmd_prompt = """
Keep in mind these details about the user's platform and environment:
{platform}
"""  # noqa

shell_cmd_reminder = """
Examples of when to suggest shell commands:

- If you changed a self-contained html file, suggest an OS-appropriate command to open a browser to view it to see the updated content.
- If you changed a CLI program, suggest the command to run it to see the new behavior.
- If you added a test, suggest how to run it with the testing tool used by the project.
- Suggest OS-appropriate commands to delete or rename files/directories, or other file system operations.
- If your code changes add new dependencies, suggest the command to install them.
- Etc.

"""  # noqa

no_shell_cmd_reminder = """
Keep in mind these details about the user's platform and environment:
{platform}
"""  # noqa
