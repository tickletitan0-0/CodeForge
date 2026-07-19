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
    "line_number_bg":   "#ebebeb",
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

    # Lint diagnostics ("squiggly line" colors)
    "lint_error":        "#e51400",
    "lint_warning":      "#b58900",

    # Syntax highlighting (tuned for a white/light background)
    "syntax_keyword":    "#0000ff",
    "syntax_string":     "#a31515",
    "syntax_comment":    "#008000",
    "syntax_number":     "#098658",
    "syntax_function":   "#795e26",

    # Minimap code-shape rectangles - deliberately much lighter/subtler
    # than the real syntax colors above. The minimap scales a single line
    # of text up into a filled block several pixels tall, so reusing the
    # same saturated colors used for actual on-screen text (pure blue/
    # green) reads as a solid wall of color rather than a faint "shape of
    # the code" preview. Other themes fall back to their normal syntax
    # colors (see render_minimap_content in app.py), since this effect is
    # specific to a white background.
    "minimap_keyword":   "#c8d4ee",
    "minimap_comment":   "#c3ddc3",
    "minimap_default":   "#d6d6d6",
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
    "line_number_bg":   "#303030",
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

    # Lint diagnostics ("squiggly line" colors)
    "lint_error":        "#f14c4c",
    "lint_warning":      "#cca700",

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
    "line_number_bg":   "#393b46",
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

    # Lint diagnostics ("squiggly line" colors)
    "lint_error":        "#ff5555",
    "lint_warning":      "#ffb86c",

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
    "line_number_bg":   "#383934",
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

    # Lint diagnostics ("squiggly line" colors)
    "lint_error":        "#f83333",
    "lint_warning":      "#fd971f",

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
    "line_number_bg":   "#3f444f",
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

    # Lint diagnostics ("squiggly line" colors)
    "lint_error":        "#bf616a",
    "lint_warning":      "#ebcb8b",

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
    "line_number_bg":   "#143c46",
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

    # Lint diagnostics ("squiggly line" colors)
    "lint_error":        "#dc322f",
    "lint_warning":      "#b58900",

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
    "line_number_bg":   "#393d44",
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

    # Lint diagnostics ("squiggly line" colors)
    "lint_error":        "#e06c75",
    "lint_warning":      "#e5c07b",

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
    "line_number_bg":   "#ebebeb",
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

    # Lint diagnostics ("squiggly line" colors)
    "lint_error":        "#cb2431",
    "lint_warning":      "#dbab09",

    "syntax_keyword":    "#d73a49",
    "syntax_string":     "#032f62",
    "syntax_comment":    "#6a737d",
    "syntax_number":     "#005cc5",
    "syntax_function":   "#6f42c1",

    # Minimap code-shape rectangles - lightened the same way as LIGHT_THEME
    # above, for the same reason: this is also a white-background theme, so
    # the full-strength syntax colors read as solid slabs once scaled up
    # into minimap rows instead of a faint "shape of the code" preview.
    "minimap_keyword":   "#f4c8cc",
    "minimap_comment":   "#bcc0c4",
    "minimap_default":   "#d6d6d6",
}


# ---------------- CRT / Retro Terminal ----------------
# Phosphor-green-on-black, styled after old amber/green CRT monitors. The
# editor's own "current line" and "scanline" tags do the rest of the retro
# look (see highlight_syntax/apply_crt_scanlines in app.py) - this palette
# just gives them the right base colors to work with.
CRT_THEME = {
    "app_bg":           "#0a0f0a",
    "sidebar_bg":       "#081008",
    "panel_header_bg":  "#0d160d",
    "panel_header_fg":  "#33ff33",
    "border":           "#1a331a",
    "tree_active_bg":   "#123312",
    "tree_active_fg":   "#66ff66",

    "editor_bg":        "#0a0f0a",
    "editor_fg":        "#33ff33",
    "editor_insert":    "#66ff66",
    "editor_select_bg": "#1f4d1f",
    "editor_select_fg": "#ccffcc",
    "line_number_bg":   "#1e221e",
    "line_number_fg":   "#1f6b1f",
    "indent_guide":     "#173317",

    "current_line_bg":  "#102010",
    "bracket_match_bg":  "#1f4d1f",
    "search_match_bg":   "#3a4d1e",
    "search_current_bg": "#4d7a1e",

    "accent":            "#66ff66",

    "output_bg":         "#0a0f0a",
    "output_fg":         "#33ff33",

    "popup_bg":          "#0d160d",
    "popup_fg":          "#33ff33",
    "popup_border":      "#1a331a",
    "popup_select_bg":   "#1f4d1f",
    "popup_select_fg":   "#ccffcc",

    "muted_fg":          "#1f6b1f",

    # Lint diagnostics ("squiggly line" colors) - a deliberate break from
    # the monochrome phosphor palette, the same way a real terminal still
    # shows errors in red rather than green.
    "lint_error":        "#ff5f5f",
    "lint_warning":      "#cccc33",

    # Muted so keywords/strings/etc still stand out a little from plain
    # text without breaking the monochrome phosphor feel.
    "syntax_keyword":    "#7fff7f",
    "syntax_string":     "#4dcc4d",
    "syntax_comment":    "#1f6b1f",
    "syntax_number":     "#a3ff9e",
    "syntax_function":   "#99ff66",
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
    "crt": CRT_THEME,
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
    "crt": "CRT / Retro Terminal",
}

DEFAULT_THEME_NAME = "light"

# ---------------- Editor font size ----------------
DEFAULT_FONT_SIZE = 12
MIN_FONT_SIZE = 8
MAX_FONT_SIZE = 32

# ---------------- Editor font family ----------------
# Curated shortlist for the Settings dialog's font picker - common
# monospace fonts likely to be installed, cross-platform. The dialog
# intersects this with tkinter.font.families() at runtime so only fonts
# actually present on the machine are offered (falling back to just the
# saved/default choice if none of these happen to be installed).
DEFAULT_FONT_FAMILY = "Consolas"
FONT_FAMILY_CHOICES = [
    "Consolas",
    "Cascadia Code",
    "Cascadia Mono",
    "Fira Code",
    "JetBrains Mono",
    "Source Code Pro",
    "Courier New",
    "Menlo",
    "Monaco",
    "DejaVu Sans Mono",
    "Ubuntu Mono",
    "Lucida Console",
]

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


MAX_RECENT_FILES = 10


def load_recent_files():
    """Return the recently-opened file paths, most-recent first. Missing/
    corrupt data just comes back as an empty list."""
    files = _load_settings().get("recent_files")
    if not isinstance(files, list):
        return []
    return [f for f in files if isinstance(f, str)][:MAX_RECENT_FILES]


def save_recent_files(paths):
    """Persist the recent-files list. Callers are expected to have already
    de-duped and capped it to MAX_RECENT_FILES - this just writes whatever
    it's given."""
    data = _load_settings()
    data["recent_files"] = list(paths)[:MAX_RECENT_FILES]
    _save_settings(data)


MAX_RECENT_FOLDERS = 10


def load_recent_folders():
    """Return the recently-opened project folders, most-recent first.
    Missing/corrupt data just comes back as an empty list. Kept as its own
    settings key (and its own MAX) rather than folded into recent_files -
    a folder isn't a file and the two lists are surfaced separately (Open
    Recent vs Open Recent Folder, and the Start Page's two columns)."""
    folders = _load_settings().get("recent_folders")
    if not isinstance(folders, list):
        return []
    return [f for f in folders if isinstance(f, str)][:MAX_RECENT_FOLDERS]


def save_recent_folders(paths):
    """Persist the recent-folders list. Callers are expected to have
    already de-duped and capped it to MAX_RECENT_FOLDERS - this just
    writes whatever it's given."""
    data = _load_settings()
    data["recent_folders"] = list(paths)[:MAX_RECENT_FOLDERS]
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


def blend_hex(color_a, color_b, t):
    """Linearly interpolate between two '#rrggbb' colors. t=0 -> color_a,
    t=1 -> color_b. Used to make a soft tint (e.g. a glow band) from colors
    a theme already defines, instead of hand-picking a new one per theme."""
    a = color_a.lstrip("#")
    b = color_b.lstrip("#")
    ar, ag, ab = (int(a[i:i + 2], 16) for i in (0, 2, 4))
    br, bg, bb = (int(b[i:i + 2], 16) for i in (0, 2, 4))
    r = round(ar + (br - ar) * t)
    g = round(ag + (bg - ag) * t)
    bch = round(ab + (bb - ab) * t)
    return f"#{r:02x}{g:02x}{bch:02x}"


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


def load_font_family_preference():
    """Return the saved editor font family, defaulting to DEFAULT_FONT_FAMILY.
    Unlike font size there's no numeric range to clamp to - an installed-font
    check happens where this is consumed (the Settings dialog), since that's
    the only place tkinter.font.families() is available/relevant."""
    family = _load_settings().get("font_family")
    if not isinstance(family, str) or not family.strip():
        return DEFAULT_FONT_FAMILY
    return family


def save_font_family_preference(family):
    """Persist the chosen editor font family so it's restored on next launch."""
    data = _load_settings()
    data["font_family"] = family or DEFAULT_FONT_FAMILY
    _save_settings(data)


def load_stats():
    """Return cumulative usage stats that outlive any single run: total
    seconds the editor has been open, and total commits made through the
    Source Control tab. Missing/corrupt data comes back zeroed rather than
    raising, same tolerance as the rest of this file's loaders."""
    stats = _load_settings().get("stats", {})
    if not isinstance(stats, dict):
        stats = {}
    total_seconds = stats.get("total_seconds")
    total_commits = stats.get("total_commits")
    return {
        "total_seconds": total_seconds if isinstance(total_seconds, (int, float)) else 0,
        "total_commits": total_commits if isinstance(total_commits, int) else 0,
    }


def save_stats(stats):
    """Persist the cumulative stats dict (total_seconds/total_commits).
    Called periodically (not just on exit) so a crash or the theme-switch
    relaunch doesn't lose whatever hasn't been flushed yet."""
    data = _load_settings()
    data["stats"] = {
        "total_seconds": stats.get("total_seconds", 0),
        "total_commits": stats.get("total_commits", 0),
    }
    _save_settings(data)


def load_last_music_url():
    """Return the last URL entered in the Music tab, or "" if none/corrupt -
    lets the tab pre-fill (and auto-load) whatever playlist was playing last
    time, instead of starting blank every launch."""
    url = _load_settings().get("last_music_url")
    return url if isinstance(url, str) else ""


def save_last_music_url(url):
    """Persist the Music tab's URL so it can be restored next launch."""
    data = _load_settings()
    data["last_music_url"] = url
    _save_settings(data)