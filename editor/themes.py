"""
Theme definitions for CodeForge.

Every color used anywhere in the UI is defined in one of the palettes below,
so the whole app reads as one consistent theme regardless of which is active.

This module also stores/loads the user's last-selected theme so it persists
between runs (see load_theme_preference / save_theme_preference).
"""

import json
import os


# ---------------- Light theme ----------------
LIGHT_THEME = {
    # Chrome / structural
    "app_bg":           "#f3f3f3",  # root window + sash background
    "sidebar_bg":       "#f3f3f3",  # explorer panel background
    "panel_header_bg":  "#e8e8e8",  # EXPLORER / Output header strips
    "panel_header_fg":  "#3b3b3b",
    "border":           "#d4d4d4",
    "tree_active_bg":   "#dbeeff",  # explorer row for the file open in the current tab
    "tree_active_fg":   "#0067c0",

    # Editor surface
    "editor_bg":        "#ffffff",
    "editor_fg":        "#1e1e1e",
    "editor_insert":    "#1e1e1e",
    "editor_select_bg": "#cce4ff",
    "editor_select_fg": "#000000",
    "line_number_bg":   "#f5f5f5",
    "line_number_fg":   "#8a8a8a",
    "indent_guide":     "#e3e3e3",

    # Line / bracket / search highlighting
    "current_line_bg":  "#eef6ff",
    "bracket_match_bg":  "#ffe9a8",
    "search_match_bg":   "#fff2a8",
    "search_current_bg": "#ffb84d",

    # Accent (multi-cursor caret, popup selection, etc.)
    "accent":            "#0067c0",

    # Output console
    "output_bg":         "#fafafa",
    "output_fg":         "#1e1e1e",

    # Autocomplete popup
    "popup_bg":          "#ffffff",
    "popup_fg":          "#1e1e1e",
    "popup_border":      "#d0d0d0",
    "popup_select_bg":   "#0067c0",
    "popup_select_fg":   "#ffffff",

    # Misc text
    "muted_fg":          "#5f6368",

    # Syntax highlighting (tuned for a white/light background)
    "syntax_keyword":    "#0000ff",
    "syntax_string":     "#a31515",
    "syntax_comment":    "#008000",
    "syntax_number":     "#098658",
    "syntax_function":   "#795e26",
}


# ---------------- Dark theme ----------------
DARK_THEME = {
    # Chrome / structural
    "app_bg":           "#1e1e1e",
    "sidebar_bg":       "#252526",
    "panel_header_bg":  "#2d2d2d",
    "panel_header_fg":  "#cccccc",
    "border":           "#3c3c3c",
    "tree_active_bg":   "#37373d",
    "tree_active_fg":   "#4fc1ff",

    # Editor surface
    "editor_bg":        "#1e1e1e",
    "editor_fg":        "#d4d4d4",
    "editor_insert":    "#d4d4d4",
    "editor_select_bg": "#264f78",
    "editor_select_fg": "#ffffff",
    "line_number_bg":   "#1e1e1e",
    "line_number_fg":   "#858585",
    "indent_guide":     "#404040",

    # Line / bracket / search highlighting
    "current_line_bg":  "#2a2d2e",
    "bracket_match_bg":  "#515c6a",
    "search_match_bg":   "#613214",
    "search_current_bg": "#9e6a03",

    # Accent (multi-cursor caret, popup selection, etc.)
    "accent":            "#4fc1ff",

    # Output console
    "output_bg":         "#1e1e1e",
    "output_fg":         "#d4d4d4",

    # Autocomplete popup
    "popup_bg":          "#252526",
    "popup_fg":          "#d4d4d4",
    "popup_border":      "#454545",
    "popup_select_bg":   "#04395e",
    "popup_select_fg":   "#ffffff",

    # Misc text
    "muted_fg":          "#9d9d9d",

    # Syntax highlighting (tuned for a dark background, VS Code "Dark+"-like)
    "syntax_keyword":    "#569cd6",
    "syntax_string":     "#ce9178",
    "syntax_comment":    "#6a9955",
    "syntax_number":     "#b5cea8",
    "syntax_function":   "#dcdcaa",
}


# ---------------- Dracula ----------------
# https://draculatheme.com/contribute - official palette
DRACULA_THEME = {
    "app_bg":           "#282a36",
    "sidebar_bg":       "#21222c",
    "panel_header_bg":  "#21222c",
    "panel_header_fg":  "#f8f8f2",
    "border":           "#191a21",
    "tree_active_bg":   "#44475a",
    "tree_active_fg":   "#8be9fd",

    "editor_bg":        "#282a36",
    "editor_fg":        "#f8f8f2",
    "editor_insert":    "#f8f8f2",
    "editor_select_bg": "#44475a",
    "editor_select_fg": "#f8f8f2",
    "line_number_bg":   "#282a36",
    "line_number_fg":   "#6272a4",
    "indent_guide":     "#3a3c4e",

    "current_line_bg":  "#2c2e3d",
    "bracket_match_bg":  "#44475a",
    "search_match_bg":   "#4a4638",
    "search_current_bg": "#ffb86c",

    "accent":            "#bd93f9",

    "output_bg":         "#282a36",
    "output_fg":         "#f8f8f2",

    "popup_bg":          "#21222c",
    "popup_fg":          "#f8f8f2",
    "popup_border":      "#191a21",
    "popup_select_bg":   "#44475a",
    "popup_select_fg":   "#f8f8f2",

    "muted_fg":          "#6272a4",

    "syntax_keyword":    "#ff79c6",
    "syntax_string":     "#f1fa8c",
    "syntax_comment":    "#6272a4",
    "syntax_number":     "#bd93f9",
    "syntax_function":   "#50fa7b",
}


# ---------------- Monokai ----------------
MONOKAI_THEME = {
    "app_bg":           "#272822",
    "sidebar_bg":       "#2d2e27",
    "panel_header_bg":  "#34352d",
    "panel_header_fg":  "#f8f8f2",
    "border":           "#1e1f1a",
    "tree_active_bg":   "#3e3d32",
    "tree_active_fg":   "#a6e22e",

    "editor_bg":        "#272822",
    "editor_fg":        "#f8f8f2",
    "editor_insert":    "#f8f8f2",
    "editor_select_bg": "#49483e",
    "editor_select_fg": "#f8f8f2",
    "line_number_bg":   "#272822",
    "line_number_fg":   "#75715e",
    "indent_guide":     "#3b3c34",

    "current_line_bg":  "#2e2f28",
    "bracket_match_bg":  "#49483e",
    "search_match_bg":   "#5a4b1e",
    "search_current_bg": "#e6db74",

    "accent":            "#66d9ef",

    "output_bg":         "#272822",
    "output_fg":         "#f8f8f2",

    "popup_bg":          "#2d2e27",
    "popup_fg":          "#f8f8f2",
    "popup_border":      "#1e1f1a",
    "popup_select_bg":   "#49483e",
    "popup_select_fg":   "#f8f8f2",

    "muted_fg":          "#75715e",

    "syntax_keyword":    "#f92672",
    "syntax_string":     "#e6db74",
    "syntax_comment":    "#75715e",
    "syntax_number":     "#ae81ff",
    "syntax_function":   "#a6e22e",
}


# ---------------- Nord ----------------
# https://www.nordtheme.com/docs/colors-and-palettes
NORD_THEME = {
    "app_bg":           "#2e3440",
    "sidebar_bg":       "#3b4252",
    "panel_header_bg":  "#3b4252",
    "panel_header_fg":  "#e5e9f0",
    "border":           "#4c566a",
    "tree_active_bg":   "#434c5e",
    "tree_active_fg":   "#88c0d0",

    "editor_bg":        "#2e3440",
    "editor_fg":        "#d8dee9",
    "editor_insert":    "#d8dee9",
    "editor_select_bg": "#434c5e",
    "editor_select_fg": "#eceff4",
    "line_number_bg":   "#2e3440",
    "line_number_fg":   "#4c566a",
    "indent_guide":     "#3b4252",

    "current_line_bg":  "#333a48",
    "bracket_match_bg":  "#4c566a",
    "search_match_bg":   "#4f4a2e",
    "search_current_bg": "#ebcb8b",

    "accent":            "#88c0d0",

    "output_bg":         "#2e3440",
    "output_fg":         "#d8dee9",

    "popup_bg":          "#3b4252",
    "popup_fg":          "#d8dee9",
    "popup_border":      "#4c566a",
    "popup_select_bg":   "#434c5e",
    "popup_select_fg":   "#eceff4",

    "muted_fg":          "#7b88a1",

    "syntax_keyword":    "#81a1c1",
    "syntax_string":     "#a3be8c",
    "syntax_comment":    "#4c566a",
    "syntax_number":     "#b48ead",
    "syntax_function":   "#8fbcbb",
}


# ---------------- Solarized Dark ----------------
# https://ethanschoonover.com/solarized/
SOLARIZED_DARK_THEME = {
    "app_bg":           "#002b36",
    "sidebar_bg":       "#073642",
    "panel_header_bg":  "#073642",
    "panel_header_fg":  "#93a1a1",
    "border":           "#586e75",
    "tree_active_bg":   "#0a4552",
    "tree_active_fg":   "#268bd2",

    "editor_bg":        "#002b36",
    "editor_fg":        "#839496",
    "editor_insert":    "#93a1a1",
    "editor_select_bg": "#1c4b57",
    "editor_select_fg": "#eee8d5",
    "line_number_bg":   "#002b36",
    "line_number_fg":   "#586e75",
    "indent_guide":     "#073642",

    "current_line_bg":  "#073642",
    "bracket_match_bg":  "#586e75",
    "search_match_bg":   "#5b4c00",
    "search_current_bg": "#b58900",

    "accent":            "#268bd2",

    "output_bg":         "#002b36",
    "output_fg":         "#839496",

    "popup_bg":          "#073642",
    "popup_fg":          "#93a1a1",
    "popup_border":      "#586e75",
    "popup_select_bg":   "#0a4552",
    "popup_select_fg":   "#eee8d5",

    "muted_fg":          "#586e75",

    "syntax_keyword":    "#859900",
    "syntax_string":     "#2aa198",
    "syntax_comment":    "#586e75",
    "syntax_number":     "#d33682",
    "syntax_function":   "#268bd2",
}


# ---------------- One Dark (Atom) ----------------
ONE_DARK_THEME = {
    "app_bg":           "#282c34",
    "sidebar_bg":       "#21252b",
    "panel_header_bg":  "#21252b",
    "panel_header_fg":  "#abb2bf",
    "border":           "#181a1f",
    "tree_active_bg":   "#2c313a",
    "tree_active_fg":   "#61afef",

    "editor_bg":        "#282c34",
    "editor_fg":        "#abb2bf",
    "editor_insert":    "#abb2bf",
    "editor_select_bg": "#3e4451",
    "editor_select_fg": "#ffffff",
    "line_number_bg":   "#282c34",
    "line_number_fg":   "#495162",
    "indent_guide":     "#3b4048",

    "current_line_bg":  "#2c313c",
    "bracket_match_bg":  "#3e4451",
    "search_match_bg":   "#5c4a1e",
    "search_current_bg": "#e5c07b",

    "accent":            "#61afef",

    "output_bg":         "#282c34",
    "output_fg":         "#abb2bf",

    "popup_bg":          "#21252b",
    "popup_fg":          "#abb2bf",
    "popup_border":      "#181a1f",
    "popup_select_bg":   "#3e4451",
    "popup_select_fg":   "#ffffff",

    "muted_fg":          "#5c6370",

    "syntax_keyword":    "#c678dd",
    "syntax_string":     "#98c379",
    "syntax_comment":    "#5c6370",
    "syntax_number":     "#d19a66",
    "syntax_function":   "#61afef",
}


# ---------------- GitHub Light ----------------
GITHUB_LIGHT_THEME = {
    "app_bg":           "#ffffff",
    "sidebar_bg":       "#f6f8fa",
    "panel_header_bg":  "#f6f8fa",
    "panel_header_fg":  "#24292e",
    "border":           "#e1e4e8",
    "tree_active_bg":   "#e7f0ff",
    "tree_active_fg":   "#0366d6",

    "editor_bg":        "#ffffff",
    "editor_fg":        "#24292e",
    "editor_insert":    "#24292e",
    "editor_select_bg": "#c8e1ff",
    "editor_select_fg": "#24292e",
    "line_number_bg":   "#ffffff",
    "line_number_fg":   "#8c959f",
    "indent_guide":     "#eaecef",

    "current_line_bg":  "#f6f8fa",
    "bracket_match_bg":  "#ffea7f",
    "search_match_bg":   "#fff5b1",
    "search_current_bg": "#ffd33d",

    "accent":            "#0366d6",

    "output_bg":         "#f6f8fa",
    "output_fg":         "#24292e",

    "popup_bg":          "#ffffff",
    "popup_fg":          "#24292e",
    "popup_border":      "#e1e4e8",
    "popup_select_bg":   "#0366d6",
    "popup_select_fg":   "#ffffff",

    "muted_fg":          "#6a737d",

    "syntax_keyword":    "#d73a49",
    "syntax_string":     "#032f62",
    "syntax_comment":    "#6a737d",
    "syntax_number":     "#005cc5",
    "syntax_function":   "#6f42c1",
}


THEMES = {
    "light": LIGHT_THEME,
    "dark": DARK_THEME,
    "dracula": DRACULA_THEME,
    "monokai": MONOKAI_THEME,
    "one_dark": ONE_DARK_THEME,
    "nord": NORD_THEME,
    "solarized_dark": SOLARIZED_DARK_THEME,
    "github_light": GITHUB_LIGHT_THEME,
}

# Display names for the theme picker menu / status bar - only needed where
# straight title-casing of the key wouldn't look right (e.g. "one_dark"
# should read "One Dark", not "One_Dark", and "github_light" should keep
# GitHub's brand capitalization).
THEME_LABELS = {
    "light": "Light",
    "dark": "Dark",
    "dracula": "Dracula",
    "monokai": "Monokai",
    "one_dark": "One Dark",
    "nord": "Nord",
    "solarized_dark": "Solarized Dark",
    "github_light": "GitHub Light",
}

DEFAULT_THEME_NAME = "light"

# ---------------- Editor font size ----------------
DEFAULT_FONT_SIZE = 12
MIN_FONT_SIZE = 8
MAX_FONT_SIZE = 32

# Where we remember the user's last-picked theme between runs.
_CONFIG_DIR = os.path.join(os.path.expanduser("~"), ".codeforge")
_CONFIG_PATH = os.path.join(_CONFIG_DIR, "settings.json")


def _load_settings():
    """Read the whole settings file as a dict, tolerating a missing or
    corrupt file by just starting fresh."""
    try:
        with open(_CONFIG_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict):
            return data
    except (OSError, ValueError):
        pass
    return {}


def _save_settings(data):
    try:
        os.makedirs(_CONFIG_DIR, exist_ok=True)
        with open(_CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f)
    except OSError:
        pass


def load_theme_preference():
    """Return the saved theme name, defaulting to light."""
    name = _load_settings().get("theme")
    return name if name in THEMES else DEFAULT_THEME_NAME


def save_theme_preference(name):
    """Persist the chosen theme name so it's restored on next launch."""
    if name not in THEMES:
        name = DEFAULT_THEME_NAME
    data = _load_settings()
    data["theme"] = name
    _save_settings(data)


def load_session():
    """Return the last-saved session: which folder was open, which files
    were open (as a list of paths, in tab order), and which one was active.
    Missing/corrupt data just comes back as an empty session."""
    session = _load_settings().get("session", {})
    if not isinstance(session, dict):
        session = {}
    return {
        "folder": session.get("folder"),
        "open_files": session.get("open_files") or [],
        "active_path": session.get("active_path"),
    }


def save_session(folder, open_files, active_path):
    """Persist which folder/files were open so the next launch (or a
    theme-change restart) can restore them. Only real, saved files belong in
    open_files - there's nothing to restore an unsaved buffer's text from,
    so callers should skip those rather than pass a path-less entry."""
    data = _load_settings()
    data["session"] = {
        "folder": folder,
        "open_files": list(open_files),
        "active_path": active_path,
    }
    _save_settings(data)


def get_theme(name):
    """Return the palette dict for a theme name, falling back to light."""
    return THEMES.get(name, LIGHT_THEME)


def _hex_luminance(hex_color):
    """Perceived brightness (0-255) of a '#rrggbb' color, used to decide
    whether native OS chrome (the Windows title bar) should be drawn in
    dark mode to match - so any new theme added to THEMES gets the right
    title bar automatically instead of needing a manual light/dark flag."""
    hex_color = hex_color.lstrip("#")
    r, g, b = (int(hex_color[i:i + 2], 16) for i in (0, 2, 4))
    return 0.299 * r + 0.587 * g + 0.114 * b


def is_dark_theme(name):
    """True if the named theme's background is dark enough that the app
    should be treated as a 'dark' theme (Windows title bar chrome, the
    status-bar icon, etc)."""
    return _hex_luminance(get_theme(name)["app_bg"]) < 128


def load_font_size_preference():
    """Return the saved editor font size, defaulting to DEFAULT_FONT_SIZE and
    clamping to the supported range in case the settings file was hand-edited
    or came from a build with different bounds."""
    size = _load_settings().get("font_size")
    if not isinstance(size, int):
        return DEFAULT_FONT_SIZE
    return max(MIN_FONT_SIZE, min(MAX_FONT_SIZE, size))


def save_font_size_preference(size):
    """Persist the chosen editor font size so it's restored on next launch."""
    size = max(MIN_FONT_SIZE, min(MAX_FONT_SIZE, size))
    data = _load_settings()
    data["font_size"] = size
    _save_settings(data)