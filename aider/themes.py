"""
Color themes for Aider.

This module contains pre-defined color themes for both dark and light terminals.
Each theme defines colors for different UI elements.
"""

from dataclasses import dataclass
from typing import Optional


@dataclass
class Theme:
    """Represents a color theme with all configurable colors."""

    name: str
    description: str
    category: str  # "dark" or "light"
    user_input_color: str
    assistant_output_color: str
    tool_output_color: Optional[str]
    tool_error_color: str
    tool_warning_color: str
    code_theme: str


# Dark terminal themes
NORD_AURORA = Theme(
    name="Nord Aurora",
    description="Cool & calming - soft blues and teals, perfect for long coding sessions",
    category="dark",
    user_input_color="#88c0d0",
    assistant_output_color="#81a1c1",
    tool_output_color="#d8dee9",
    tool_error_color="#bf616a",
    tool_warning_color="#ebcb8b",
    code_theme="monokai",
)

DRACULA = Theme(
    name="Dracula",
    description="Vibrant & energetic - popular dark theme with punchy colors",
    category="dark",
    user_input_color="#50fa7b",
    assistant_output_color="#bd93f9",
    tool_output_color="#f8f8f2",
    tool_error_color="#ff5555",
    tool_warning_color="#ffb86c",
    code_theme="dracula",
)

TOKYO_NIGHT = Theme(
    name="Tokyo Night",
    description="Deep & modern - modern dark theme with neon accents",
    category="dark",
    user_input_color="#7dcfff",
    assistant_output_color="#bb9af7",
    tool_output_color="#c0caf5",
    tool_error_color="#f7768e",
    tool_warning_color="#e0af68",
    code_theme="monokai",
)

GRUVBOX_DARK = Theme(
    name="Gruvbox Dark",
    description="Warm & retro - warm, muted colors for reduced eye strain",
    category="dark",
    user_input_color="#b8bb26",
    assistant_output_color="#83a598",
    tool_output_color="#ebdbb2",
    tool_error_color="#fb4934",
    tool_warning_color="#fabd2f",
    code_theme="gruvbox-dark",
)

# Light terminal themes
SOLARIZED_LIGHT = Theme(
    name="Solarized Light",
    description="Scientific & balanced - designed by color theory for optimal readability",
    category="light",
    user_input_color="#859900",
    assistant_output_color="#268bd2",
    tool_output_color="#657b83",
    tool_error_color="#dc322f",
    tool_warning_color="#cb4b16",
    code_theme="solarized-light",
)

GITHUB_LIGHT = Theme(
    name="Github Light",
    description="Clean & professional - familiar GitHub-style colors",
    category="light",
    user_input_color="#116329",
    assistant_output_color="#0969da",
    tool_output_color="#57606a",
    tool_error_color="#cf222e",
    tool_warning_color="#9a6700",
    code_theme="github-dark",
)

GRUVBOX_LIGHT = Theme(
    name="Gruvbox Light",
    description="Warm & soft - light variant with warm, gentle tones",
    category="light",
    user_input_color="#79740e",
    assistant_output_color="#076678",
    tool_output_color="#3c3836",
    tool_error_color="#9d0006",
    tool_warning_color="#b57614",
    code_theme="gruvbox-light",
)

AYU_LIGHT = Theme(
    name="Ayu Light",
    description="Minimal & airy - minimalist design with bright, open feel",
    category="light",
    user_input_color="#86b300",
    assistant_output_color="#399ee6",
    tool_output_color="#5c6166",
    tool_error_color="#f07171",
    tool_warning_color="#fa8d3e",
    code_theme="default",
)

# All themes organized
DARK_THEMES = [NORD_AURORA, DRACULA, TOKYO_NIGHT, GRUVBOX_DARK]
LIGHT_THEMES = [SOLARIZED_LIGHT, GITHUB_LIGHT, GRUVBOX_LIGHT, AYU_LIGHT]
ALL_THEMES = DARK_THEMES + LIGHT_THEMES

# Theme lookup by name (case-insensitive)
THEMES_BY_NAME = {theme.name.lower(): theme for theme in ALL_THEMES}


def get_theme(name: str) -> Optional[Theme]:
    """Get a theme by name (case-insensitive)."""
    return THEMES_BY_NAME.get(name.lower())


def get_themes_by_category(category: str) -> list[Theme]:
    """Get all themes for a specific category (dark or light)."""
    if category == "dark":
        return DARK_THEMES
    elif category == "light":
        return LIGHT_THEMES
    else:
        return ALL_THEMES
