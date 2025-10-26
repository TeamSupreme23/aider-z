"""
Tests for theme functionality.
"""

import unittest

from aider.themes import (
    ALL_THEMES,
    AYU_LIGHT,
    DARK_THEMES,
    DRACULA,
    GITHUB_LIGHT,
    GRUVBOX_DARK,
    GRUVBOX_LIGHT,
    LIGHT_THEMES,
    NORD_AURORA,
    SOLARIZED_LIGHT,
    THEMES_BY_NAME,
    TOKYO_NIGHT,
    Theme,
    get_theme,
    get_themes_by_category,
)


class TestThemes(unittest.TestCase):
    def test_theme_dataclass(self):
        """Test that Theme dataclass has all required fields."""
        theme = NORD_AURORA
        self.assertIsInstance(theme, Theme)
        self.assertEqual(theme.name, "Nord Aurora")
        self.assertEqual(theme.category, "dark")
        self.assertIsNotNone(theme.user_input_color)
        self.assertIsNotNone(theme.assistant_output_color)
        self.assertIsNotNone(theme.tool_error_color)
        self.assertIsNotNone(theme.tool_warning_color)
        self.assertIsNotNone(theme.code_theme)
        self.assertIsNotNone(theme.description)

    def test_all_dark_themes(self):
        """Test that all dark themes are properly defined."""
        self.assertEqual(len(DARK_THEMES), 4)
        for theme in DARK_THEMES:
            self.assertEqual(theme.category, "dark")
            self.assertIsInstance(theme, Theme)

    def test_all_light_themes(self):
        """Test that all light themes are properly defined."""
        self.assertEqual(len(LIGHT_THEMES), 4)
        for theme in LIGHT_THEMES:
            self.assertEqual(theme.category, "light")
            self.assertIsInstance(theme, Theme)

    def test_all_themes_list(self):
        """Test that ALL_THEMES contains both dark and light themes."""
        self.assertEqual(len(ALL_THEMES), 8)
        self.assertEqual(ALL_THEMES, DARK_THEMES + LIGHT_THEMES)

    def test_get_theme_by_name_case_insensitive(self):
        """Test getting theme by name (case-insensitive)."""
        # Exact case
        theme = get_theme("Nord Aurora")
        self.assertEqual(theme, NORD_AURORA)

        # Lowercase
        theme = get_theme("nord aurora")
        self.assertEqual(theme, NORD_AURORA)

        # Mixed case
        theme = get_theme("NORD AURORA")
        self.assertEqual(theme, NORD_AURORA)

    def test_get_theme_not_found(self):
        """Test getting non-existent theme returns None."""
        theme = get_theme("Non Existent Theme")
        self.assertIsNone(theme)

    def test_get_themes_by_category_dark(self):
        """Test getting themes by dark category."""
        themes = get_themes_by_category("dark")
        self.assertEqual(themes, DARK_THEMES)

    def test_get_themes_by_category_light(self):
        """Test getting themes by light category."""
        themes = get_themes_by_category("light")
        self.assertEqual(themes, LIGHT_THEMES)

    def test_get_themes_by_category_all(self):
        """Test getting all themes when category is invalid."""
        themes = get_themes_by_category("invalid")
        self.assertEqual(themes, ALL_THEMES)

    def test_themes_by_name_dict(self):
        """Test that THEMES_BY_NAME dictionary is properly populated."""
        self.assertEqual(len(THEMES_BY_NAME), 8)
        self.assertIn("nord aurora", THEMES_BY_NAME)
        self.assertIn("dracula", THEMES_BY_NAME)
        self.assertIn("tokyo night", THEMES_BY_NAME)
        self.assertIn("gruvbox dark", THEMES_BY_NAME)
        self.assertIn("solarized light", THEMES_BY_NAME)
        self.assertIn("github light", THEMES_BY_NAME)
        self.assertIn("gruvbox light", THEMES_BY_NAME)
        self.assertIn("ayu light", THEMES_BY_NAME)

    def test_all_themes_have_valid_colors(self):
        """Test that all themes have valid hex color codes."""
        for theme in ALL_THEMES:
            # Check colors start with # and are valid hex
            self.assertTrue(
                theme.user_input_color.startswith("#"),
                f"{theme.name}: user_input_color should start with #",
            )
            self.assertTrue(
                theme.assistant_output_color.startswith("#"),
                f"{theme.name}: assistant_output_color should start with #",
            )
            self.assertTrue(
                theme.tool_error_color.startswith("#"),
                f"{theme.name}: tool_error_color should start with #",
            )
            self.assertTrue(
                theme.tool_warning_color.startswith("#"),
                f"{theme.name}: tool_warning_color should start with #",
            )

            # tool_output_color can be None
            if theme.tool_output_color:
                self.assertTrue(
                    theme.tool_output_color.startswith("#"),
                    f"{theme.name}: tool_output_color should start with #",
                )

    def test_specific_dark_themes(self):
        """Test specific dark theme definitions."""
        # Nord Aurora
        self.assertEqual(NORD_AURORA.name, "Nord Aurora")
        self.assertEqual(NORD_AURORA.user_input_color, "#88c0d0")

        # Dracula
        self.assertEqual(DRACULA.name, "Dracula")
        self.assertEqual(DRACULA.user_input_color, "#50fa7b")

        # Tokyo Night
        self.assertEqual(TOKYO_NIGHT.name, "Tokyo Night")
        self.assertEqual(TOKYO_NIGHT.user_input_color, "#7dcfff")

        # Gruvbox Dark
        self.assertEqual(GRUVBOX_DARK.name, "Gruvbox Dark")
        self.assertEqual(GRUVBOX_DARK.user_input_color, "#b8bb26")

    def test_specific_light_themes(self):
        """Test specific light theme definitions."""
        # Solarized Light
        self.assertEqual(SOLARIZED_LIGHT.name, "Solarized Light")
        self.assertEqual(SOLARIZED_LIGHT.user_input_color, "#859900")

        # Github Light
        self.assertEqual(GITHUB_LIGHT.name, "Github Light")
        self.assertEqual(GITHUB_LIGHT.user_input_color, "#116329")

        # Gruvbox Light
        self.assertEqual(GRUVBOX_LIGHT.name, "Gruvbox Light")
        self.assertEqual(GRUVBOX_LIGHT.user_input_color, "#79740e")

        # Ayu Light
        self.assertEqual(AYU_LIGHT.name, "Ayu Light")
        self.assertEqual(AYU_LIGHT.user_input_color, "#86b300")


if __name__ == "__main__":
    unittest.main()
