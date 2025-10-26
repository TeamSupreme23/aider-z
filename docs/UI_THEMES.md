# UI Color Themes

Aider now includes built-in color themes to make the interface easier on your eyes!

## Using the `/ui-theme` Command

The `/ui-theme` command provides an interactive way to select and apply color themes.

### Interactive Menu

Simply type `/ui-theme` in Aider to open an interactive menu:

```
/ui-theme
```

This will display a menu with all available themes, organized by category (Dark and Light). Use arrow keys to navigate, Space to select, and Enter to confirm.

### Direct Theme Selection

You can also apply a theme directly by name:

```
/ui-theme nord aurora
/ui-theme dracula
/ui-theme solarized light
```

Theme names are case-insensitive.

## Available Themes

### Dark Terminal Themes

#### 1. Nord Aurora
**Description**: Cool & calming - soft blues and teals, perfect for long coding sessions

- User Input: `#88c0d0` (Frost cyan)
- Assistant Output: `#81a1c1` (Soft blue)
- Tool Output: `#d8dee9` (Snow white)
- Tool Error: `#bf616a` (Aurora red)
- Tool Warning: `#ebcb8b` (Aurora yellow)
- Code Theme: `monokai`

#### 2. Dracula
**Description**: Vibrant & energetic - popular dark theme with punchy colors

- User Input: `#50fa7b` (Mint green)
- Assistant Output: `#bd93f9` (Purple)
- Tool Output: `#f8f8f2` (Foreground)
- Tool Error: `#ff5555` (Red)
- Tool Warning: `#ffb86c` (Orange)
- Code Theme: `dracula`

#### 3. Tokyo Night
**Description**: Deep & modern - modern dark theme with neon accents

- User Input: `#7dcfff` (Sky blue)
- Assistant Output: `#bb9af7` (Purple)
- Tool Output: `#c0caf5` (Foreground)
- Tool Error: `#f7768e` (Red)
- Tool Warning: `#e0af68` (Yellow)
- Code Theme: `monokai`

#### 4. Gruvbox Dark
**Description**: Warm & retro - warm, muted colors for reduced eye strain

- User Input: `#b8bb26` (Green)
- Assistant Output: `#83a598` (Aqua)
- Tool Output: `#ebdbb2` (Foreground)
- Tool Error: `#fb4934` (Red)
- Tool Warning: `#fabd2f` (Yellow)
- Code Theme: `gruvbox-dark`

### Light Terminal Themes

#### 5. Solarized Light
**Description**: Scientific & balanced - designed by color theory for optimal readability

- User Input: `#859900` (Green)
- Assistant Output: `#268bd2` (Blue)
- Tool Output: `#657b83` (Base00)
- Tool Error: `#dc322f` (Red)
- Tool Warning: `#cb4b16` (Orange)
- Code Theme: `solarized-light`

#### 6. Github Light
**Description**: Clean & professional - familiar GitHub-style colors

- User Input: `#116329` (Green)
- Assistant Output: `#0969da` (Blue)
- Tool Output: `#57606a` (Gray)
- Tool Error: `#cf222e` (Red)
- Tool Warning: `#9a6700` (Yellow)
- Code Theme: `github-dark`

#### 7. Gruvbox Light
**Description**: Warm & soft - light variant with warm, gentle tones

- User Input: `#79740e` (Green)
- Assistant Output: `#076678` (Aqua)
- Tool Output: `#3c3836` (Foreground)
- Tool Error: `#9d0006` (Red)
- Tool Warning: `#b57614` (Yellow)
- Code Theme: `gruvbox-light`

#### 8. Ayu Light
**Description**: Minimal & airy - minimalist design with bright, open feel

- User Input: `#86b300` (Green)
- Assistant Output: `#399ee6` (Blue)
- Tool Output: `#5c6166` (Foreground)
- Tool Error: `#f07171` (Red)
- Tool Warning: `#fa8d3e` (Orange)
- Code Theme: `default`

## Saving Themes

When you select a theme using `/ui-theme`, you'll see a preview of the colors. You'll then be asked if you want to save the theme to `~/.aider.conf.yml`. If you choose yes, the theme will be automatically applied every time you launch Aider.

## Manual Configuration

You can also manually configure colors in your `~/.aider.conf.yml` file:

```yaml
# Example: Nord Aurora theme
user-input-color: "#88c0d0"
assistant-output-color: "#81a1c1"
tool-output-color: "#d8dee9"
tool-error-color: "#bf616a"
tool-warning-color: "#ebcb8b"
code-theme: monokai
```

## Recommendations

- **Dark terminal users**: Try **Nord Aurora** or **Dracula**
- **Light terminal users**: Try **Solarized Light** or **Github Light**
- **For minimal eye strain**: Try **Gruvbox Dark** or **Gruvbox Light**
- **To replace the bright green default**: Any of the 8 themes use softer, more eye-friendly colors

## Troubleshooting

If colors don't appear correctly:
1. Make sure your terminal supports 256 colors or true color
2. Try a different terminal emulator
3. Check that the `NO_COLOR` environment variable is not set
4. Verify that `pretty` is set to `true` in your config (it's on by default)
