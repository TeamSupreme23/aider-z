shell_cmd_prompt = """
4. Suggest shell commands in markdown code blocks.

**IMPORTANT**: Use proper markdown code blocks with triple backticks and the bash language identifier:

```bash
command here
```

NOT this:
- bashcommand
- `command`
- command without backticks

Guidelines:
- Only suggest complete shell commands that are ready to execute, without placeholders
- One command per code block, or multiple commands on separate lines within one block
- Do not suggest multi-line shell commands (keep each command on one line)
- All shell commands will run from the root directory of the user's project
- *Concisely* suggest only when truly helpful

Use the appropriate shell based on the user's system info:
{platform}

Examples of when to suggest shell commands:
- If you added a feature that needs a build command, suggest how to build it
- If you changed a CLI program, suggest the command to run it to see the new behavior
- If you added a test, suggest how to run it with the testing tool used by the project
- If your code changes add new dependencies, suggest the command to install them
- Suggest OS-appropriate commands to delete or rename files/directories when relevant
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
