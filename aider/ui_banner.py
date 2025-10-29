"""
Aider startup banner and UI enhancement module.

Provides welcome banner, ASCII art icons, and styled output for the Aider CLI.
"""

from rich.console import Console
from rich.text import Text
from rich.style import Style


# Space Invaders enemy ASCII art icon
SPACE_INVADER_ICON = """
  ◾ ◾   ◾ ◾
   ◾◾◾◾◾◾
  ◾ ◾ ◾ ◾ ◾
  ◾◾◾◾◾◾◾◾
"""

# Simpler Space Invaders enemy (single line style)
SPACE_INVADER_SIMPLE = "◾ ◾ ◾ ◾ ◾"

# Compact Space Invaders enemy
SPACE_INVADER_COMPACT = """
  ◾◾ ◾◾
 ◾◾◾◾◾◾
  ◾◾◾◾
"""


def create_magnifying_glass(color: str = "grey70") -> Text:
    """
    Create a colored magnifying glass icon.

    Args:
        color: Color name or hex code (default: "grey70")

    Returns:
        Rich Text object with colored icon
    """
    icon = """
    ◯───◯
     ◾
    ╲ ╲
     ╲ ●"""

    return Text(icon, style=Style(color=color, bold=True))


def truncate_path(path: str, max_length: int = 45) -> str:
    """
    Truncate a path to fit within max_length, showing the most recent directories.

    Args:
        path: Full path string
        max_length: Maximum length for truncated path

    Returns:
        Truncated path with ellipsis if needed
    """
    if len(path) <= max_length:
        return path

    # Show the end of the path
    truncated = "..." + path[-(max_length - 3):]
    return truncated


def truncate_model_name(model: str, max_length: int = 40) -> str:
    """
    Truncate a model name intelligently, showing provider and key parts.

    Args:
        model: Full model name
        max_length: Maximum length for truncated name

    Returns:
        Truncated model name
    """
    if len(model) <= max_length:
        return model

    # Try to keep the provider part and truncate the model part
    if "/" in model:
        parts = model.split("/")
        provider = parts[0]
        model_part = parts[1] if len(parts) > 1 else ""

        # Calculate available space for model part
        available = max_length - len(provider) - 1  # -1 for the "/"

        if available > 3:
            truncated_model = model_part[:available - 3] + "..."
            return f"{provider}/{truncated_model}"

    # Fallback: just truncate from the end
    return model[:max_length - 3] + "..."


def create_startup_banner(
    version: str = "0.1.0",
    model: str = "Claude API",
    weak_model: str = None,
    working_dir: str = ".",
    edit_format: str = None,
    git_info: str = None,
    repo_map_info: str = None,
    console: Console = None,
    accent_color: str = "grey70"  # Grey
) -> None:
    """
    Display a Claude Code-style startup banner for Aider.
    Intelligently handles multiline content while maintaining neat appearance.

    Args:
        version: Aider version string
        model: Main LLM model being used
        weak_model: Weak model (optional)
        working_dir: Current working directory
        edit_format: Edit format being used
        git_info: Git repository information
        repo_map_info: Repository map information
        console: Rich Console instance
        accent_color: Accent color for banner (hex code or color name)
    """
    if console is None:
        console = Console()

    # Get terminal width (default to 80 if can't determine)
    try:
        term_width = console.width
    except Exception:
        term_width = 80

    # Ensure minimum width and use standard 80 chars for narrow banner
    if term_width < 80:
        term_width = 80

    # Calculate banner content width (accounting for borders)
    banner_width = min(term_width - 4, 100)  # Max 100 chars, min 80
    content_width = banner_width - 4  # Account for side borders and spacing

    # Prepare left side: System Info
    # Format lines as tuples of (label, value) for intelligent wrapping
    left_info = [
        ("Aider", f"v{version}"),
        ("Main model", model),
    ]

    if edit_format:
        left_info.append(("  Edit format", edit_format))

    if weak_model:
        left_info.append(("Weak model", weak_model))

    if git_info:
        left_info.append(("Git repo", git_info))

    if repo_map_info:
        left_info.append(("Repo-map", repo_map_info))

    # Prepare right side: Tips
    right_tips = [
        "Run /init to create",
        ".aider.conf",
        "",
        "Add files with /add",
        "or mention them",
        "",
        "Use /help to see",
        "all commands",
    ]

    # Calculate dimensions for two-column layout
    left_width = banner_width // 2 - 1
    right_width = banner_width - left_width - 3
    col_width = left_width - 1

    # Format left content with intelligent wrapping of long values
    wrapped_left = []

    for label, value in left_info:
        full_line = f"{label}: {value}"

        if len(full_line) <= col_width:
            # Fits on one line
            wrapped_left.append(full_line)
        else:
            # Line too long - put label and value on separate lines
            wrapped_left.append(f"{label}:")

            # Wrap the value if it's too long
            if len(value) <= col_width:
                wrapped_left.append(value)
            else:
                # Value is very long, wrap it with indentation
                words = value.split()
                current_line = ""

                for word in words:
                    test_line = current_line + (" " + word if current_line else word)
                    if len(test_line) <= col_width - 2:  # -2 for indent
                        current_line = test_line
                    else:
                        if current_line:
                            wrapped_left.append("  " + current_line)
                        current_line = word

                if current_line:
                    wrapped_left.append("  " + current_line)

    # Top border
    console.print(f"[{accent_color}]╭{'─' * (banner_width - 2)}╮[/]")

    # ASCII Art Title
    ascii_art = [
        " _________ .__                   .___        ____  __.__.__  .__                ",
        " \\_   ___ \\|  | _____   __ __  __| _/____   |    |/ _|__|  | |  |   ___________ ",
        " /    \\  \\/|  | \\__  \\ |  |  \\/ __ |/ __ \\  |      < |  |  | |  | _/ __ \\_  __ \\",
        " \\     \\___|  |__/ __ \\|  |  / /_/ \\  ___/  |    |  \\|  |  |_|  |_\\  ___/|  | \\/",
        "  \\______  /____(____  /____/\\____ |\\___  > |____|__ \\__|____/____/\\___  >__|   ",
        "         \\/          \\/           \\/    \\/          \\/                 \\/       "
    ]

    for line in ascii_art:
        # Truncate line if it's too long for the banner
        if len(line) > content_width:
            line = line[:content_width]
        padding = content_width - len(line)
        console.print(f"[{accent_color}]│ {line}{' ' * max(0, padding)} │[/]")

    # Welcome message
    welcome = "Welcome back!"
    padding = content_width - len(welcome)
    console.print(f"[{accent_color}]│ {welcome}{' ' * max(0, padding)} │[/]")

    # Divider
    console.print(f"[{accent_color}]├{'─' * left_width}┬{'─' * right_width}┤[/]")

    # Display header row
    left_label = "System Info"
    right_label = "Tips"
    left_label_padded = left_label.ljust(left_width - 1)
    right_label_padded = right_label.ljust(right_width - 1)
    console.print(
        f"[{accent_color}]│ [{accent_color} bold]{left_label_padded}[/][{accent_color}]│ "
        f"[{accent_color} bold]{right_label_padded}[/][{accent_color}]│[/]"
    )

    # Display content rows - intelligently handle different lengths
    max_rows = max(len(wrapped_left), len(right_tips))
    for i in range(max_rows):
        left_text = wrapped_left[i] if i < len(wrapped_left) else ""
        right_text = right_tips[i] if i < len(right_tips) else ""

        left_padded = left_text.ljust(left_width - 1)
        right_padded = right_text.ljust(right_width - 1)

        console.print(f"[{accent_color}]│ {left_padded}[{accent_color}]│ {right_padded}[{accent_color}]│[/]")

    # Bottom border
    console.print(f"[{accent_color}]╰{'─' * left_width}┴{'─' * right_width}╯[/]")

    # Spacing
    console.print()


def create_simple_startup_banner(
    version: str = "0.1.0",
    model: str = "Claude API",
    working_dir: str = ".",
    console: Console = None,
    accent_color: str = "grey70"
) -> None:
    """
    Display a simpler startup banner (minimal style).

    Args:
        version: Aider version string
        model: LLM model being used
        working_dir: Current working directory
        console: Rich Console instance
        accent_color: Accent color for banner
    """
    if console is None:
        console = Console()

    # Simple banner with centered layout
    console.print()
    console.print(f"[bold {accent_color}]Aider v{version}[/]")
    console.print(f"[{accent_color}]{'─' * 60}[/]")
    console.print(f"[{accent_color}]Model:[/] {model}")
    console.print(f"[{accent_color}]Directory:[/] {working_dir}")
    console.print(f"[{accent_color}]{'─' * 60}[/]")
    console.print()


def display_quick_tips(console: Console = None, accent_color: str = "grey70") -> None:
    """
    Display quick tips for getting started.

    Args:
        console: Rich Console instance
        accent_color: Accent color for tips
    """
    if console is None:
        console = Console()

    tips = [
        "[bold]Tips for getting started:[/]",
        "  • Run [bold]/init[/] to create a configuration file",
        "  • Use [bold]/add <file>[/] to add files to chat",
        "  • Type [bold]/help[/] to see all available commands",
        "  • Press [bold]Alt-Enter[/] for multi-line input",
    ]

    for tip in tips:
        console.print(f"[{accent_color}]{tip}[/]")

    console.print()


if __name__ == "__main__":
    # Test the banner
    console = Console()
    create_startup_banner(
        version="0.37.0",
        model="Claude 3.5 Sonnet",
        working_dir="/Users/test/project"
    )
    display_quick_tips()
