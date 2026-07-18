import tkinter as tk
from tkinter import filedialog
from tkinter import ttk
from tkinter import messagebox
from tkinter import simpledialog
import tkinter.font as tkfont
import re
import random
import ast
import builtins
import importlib
import bisect
import keyword
import subprocess
import tempfile
import os
import shutil
import sys
import threading
import shlex

try:
    # app.py is being imported as part of the "editor" package (e.g. main.py
    # does `from editor import app`) - use a relative import so Python looks
    # for themes.py inside this same package.
    from .themes import (
        THEMES, THEME_LABELS, load_theme_preference, save_theme_preference,
        load_session, save_session,
        load_font_size_preference, save_font_size_preference,
        DEFAULT_FONT_SIZE, MIN_FONT_SIZE, MAX_FONT_SIZE,
        is_dark_theme,
        load_recent_files, save_recent_files, MAX_RECENT_FILES
    )
except ImportError:
    # app.py is being run directly as a standalone script - fall back to a
    # plain import, which works since Python adds the script's own folder
    # to sys.path automatically.
    from themes import (
        THEMES, THEME_LABELS, load_theme_preference, save_theme_preference,
        load_session, save_session,
        load_font_size_preference, save_font_size_preference,
        DEFAULT_FONT_SIZE, MIN_FONT_SIZE, MAX_FONT_SIZE,
        is_dark_theme,
        load_recent_files, save_recent_files, MAX_RECENT_FILES
    )

try:
    # Optional dependency (pip install tkinterdnd2) that lets the OS file
    # manager drag files/folders straight onto the app. Root has to be a
    # tkinterdnd2.TkinterDnD.Tk() (not a plain tk.Tk()) for drop targets to
    # work at all, so run() below picks the right constructor based on
    # whether this import succeeded. Falls back to no drag-and-drop
    # (open via File > Open still works normally) if it isn't installed.
    import tkinterdnd2
except ImportError:
    tkinterdnd2 = None

try:
    # music_player.py is being imported as part of the "editor" package.
    from . import music_player
except ImportError:
    # Standalone script - plain import, same fallback pattern as themes
    # above.
    import music_player

try:
    # git_panel.py is being imported as part of the "editor" package.
    from . import git_panel
except ImportError:
    # Standalone script - plain import, same fallback pattern as themes
    # above.
    import git_panel


# ---------------- Theme ----------------
# The palettes themselves now live in themes.py. We just load whichever one
# the user last picked (defaulting to light) so the whole app reads as one
# consistent theme.
THEME_NAME = load_theme_preference()
THEME = THEMES[THEME_NAME]


def _scanline_bg():
    """A background color for the CRT scanline bands: a small nudge away
    from the editor background (lighter on a dark theme, darker on a light
    one) so alternating lines read as a faint raster instead of being
    invisible on one theme and jarring on another."""
    hex_color = THEME["editor_bg"].lstrip("#")
    r, g, b = (int(hex_color[i:i + 2], 16) for i in (0, 2, 4))
    luminance = 0.299 * r + 0.587 * g + 0.114 * b
    step = 14 if luminance < 128 else -10
    r, g, b = (max(0, min(255, c + step)) for c in (r, g, b))
    return f"#{r:02x}{g:02x}{b:02x}"


def _apply_windows_dpi_awareness():
    """Best-effort: tell Windows this process handles its own DPI scaling,
    before any Tk window exists. Without this, Windows assumes the app is
    DPI-unaware, renders it at 100%, and then bitmap-stretches the whole
    window up to match the display's actual scale - a blunt pixel stretch
    that's what makes text (and everything else) look blurry/soft on
    scaled displays (125%, 150%, etc). Must run before tk.Tk() is created;
    setting it afterward is too late. Safe no-op on non-Windows platforms
    or older Windows builds that don't support the call.
    """
    if sys.platform != "win32":
        return
    try:
        import ctypes
        # PROCESS_SYSTEM_DPI_AWARE - scales once to match the monitor's
        # DPI rather than leaving Windows to stretch a 100%-rendered
        # window after the fact.
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        try:
            # Fallback for older Windows (Vista/7) that lack shcore.
            import ctypes
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass


def _apply_windows_dark_titlebar(root, dark):
    """Best-effort: ask Windows to draw the title bar/window frame in dark
    chrome to match the app. This is the one piece of "chrome" Tkinter can't
    style directly (the menu STRIP and title bar are drawn natively by the
    OS). Safe no-op on non-Windows platforms or older Windows builds that
    don't support the DWM attribute.
    """
    if sys.platform != "win32":
        return
    try:
        import ctypes
        root.update_idletasks()
        hwnd = ctypes.windll.user32.GetParent(root.winfo_id())
        value = ctypes.c_int(1 if dark else 0)
        # DWMWA_USE_IMMERSIVE_DARK_MODE is 20 on Windows 11 / newer Windows
        # 10 builds, and 19 on some earlier Windows 10 insider builds.
        for attribute in (20, 19):
            result = ctypes.windll.dwmapi.DwmSetWindowAttribute(
                hwnd, attribute, ctypes.byref(value), ctypes.sizeof(value)
            )
            if result == 0:
                break
    except Exception:
        pass


# ---------------- Syntax-highlighting patterns ----------------
# Compiled once here rather than inside highlight_syntax(), which used to
# rebuild (and for the keyword pattern, re-derive) these on every keystroke.
_KEYWORD_RE = re.compile(r'\b(' + '|'.join(keyword.kwlist) + r')\b')
_STRING_RE = re.compile(
    r'("""[\s\S]*?"""|\'\'\'[\s\S]*?\'\'\'|"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\')'
)
_COMMENT_RE = re.compile(r'#.*')
_NUMBER_RE = re.compile(r'\b\d+\.?\d*\b')
_FUNCTION_RE = re.compile(r'\b([a-zA-Z_]\w*)\s*(?=\()')

# ---- C-like languages (C, C++, Java, JavaScript/JSX, TypeScript/TSX) ----
_C_LIKE_KEYWORDS = {
    # C / C++
    "auto", "break", "case", "char", "const", "continue", "default", "do",
    "double", "else", "enum", "extern", "float", "for", "goto", "if",
    "inline", "int", "long", "register", "restrict", "return", "short",
    "signed", "sizeof", "static", "struct", "switch", "typedef", "union",
    "unsigned", "void", "volatile", "while", "class", "namespace",
    "template", "typename", "public", "private", "protected", "virtual",
    "override", "friend", "operator", "using", "try", "catch", "throw",
    "nullptr", "bool",
    # Java
    "package", "import", "interface", "implements", "extends", "final",
    "abstract", "synchronized", "native", "transient", "throws",
    "instanceof", "super", "boolean", "byte",
    # JavaScript / TypeScript
    "function", "var", "let", "const", "export", "default", "from", "as",
    "async", "await", "yield", "of", "in", "typeof", "delete", "new",
    "this", "null", "undefined", "true", "false", "void", "type",
    "declare", "readonly", "enum", "keyof", "infer", "module", "get", "set",
    "static",
}
_C_LIKE_KEYWORD_RE = re.compile(r'\b(' + '|'.join(sorted(_C_LIKE_KEYWORDS)) + r')\b')
_C_LIKE_STRING_RE = re.compile(
    r'("(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'|`(?:\\.|[^`\\])*`)'
)
_C_LIKE_COMMENT_RE = re.compile(r'//.*|/\*[\s\S]*?\*/')
_C_LIKE_NUMBER_RE = re.compile(r'\b0[xX][0-9a-fA-F]+\b|\b\d+\.?\d*[fFlLuU]?\b')

# ---- HTML / XML ----
_HTML_TAG_RE = re.compile(r'</?[a-zA-Z][\w-]*')
_HTML_STRING_RE = re.compile(r'"[^"]*"|\'[^\']*\'')
_HTML_COMMENT_RE = re.compile(r'<!--[\s\S]*?-->')

# ---- CSS ----
_CSS_KEYWORD_RE = re.compile(
    r'@[a-zA-Z-]+|\b(important|inherit|initial|unset|none|auto|solid|'
    r'dashed|dotted|flex|grid|block|inline|inline-block|absolute|'
    r'relative|fixed|sticky|bold|italic|normal|center|left|right|top|'
    r'bottom|hidden|visible|pointer)\b'
)
_CSS_STRING_RE = _HTML_STRING_RE
_CSS_COMMENT_RE = re.compile(r'/\*[\s\S]*?\*/')
_CSS_NUMBER_RE = re.compile(
    r'\b\d+\.?\d*(px|em|rem|%|vh|vw|vmin|vmax|s|ms|deg|fr)?\b'
)

# ---- JSON ----
_JSON_KEYWORD_RE = re.compile(r'\b(true|false|null)\b')
_JSON_KEY_RE = re.compile(r'"(?:\\.|[^"\\])*"(?=\s*:)')
_JSON_STRING_RE = re.compile(r'"(?:\\.|[^"\\])*"')
_JSON_NUMBER_RE = re.compile(r'-?\b\d+\.?\d*([eE][+-]?\d+)?\b')

# ---- YAML ----
_YAML_COMMENT_RE = re.compile(r'#.*')
_YAML_KEY_RE = re.compile(r'^\s*[\w.-]+(?=\s*:)', re.MULTILINE)
_YAML_STRING_RE = re.compile(r'"[^"]*"|\'[^\']*\'')
_YAML_NUMBER_RE = re.compile(r'\b\d+\.?\d*\b')

# ---- SQL ----
_SQL_KEYWORDS = {
    "select", "insert", "update", "delete", "from", "where", "join",
    "inner", "outer", "left", "right", "full", "on", "group", "by",
    "order", "having", "values", "into", "create", "table", "alter",
    "drop", "index", "primary", "key", "foreign", "references", "not",
    "null", "default", "and", "or", "as", "distinct", "limit", "offset",
    "union", "all", "exists", "in", "between", "like", "is", "case",
    "when", "then", "else", "end", "set", "view", "trigger", "cascade",
}
_SQL_KEYWORD_RE = re.compile(
    r'\b(' + '|'.join(sorted(_SQL_KEYWORDS)) + r')\b', re.IGNORECASE
)
_SQL_STRING_RE = re.compile(r"'(?:''|[^'])*'")
_SQL_COMMENT_RE = re.compile(r'--.*|/\*[\s\S]*?\*/')
_SQL_NUMBER_RE = re.compile(r'\b\d+\.?\d*\b')

# ---- Shell ----
_SHELL_KEYWORDS = {
    "if", "then", "else", "elif", "fi", "for", "while", "do", "done",
    "case", "esac", "function", "return", "export", "local", "readonly",
    "shift", "break", "continue", "in", "select", "until", "time", "echo",
}
_SHELL_KEYWORD_RE = re.compile(r'\b(' + '|'.join(sorted(_SHELL_KEYWORDS)) + r')\b')
_SHELL_STRING_RE = re.compile(r'"(?:\\.|[^"\\])*"|\'[^\']*\'')
_SHELL_COMMENT_RE = re.compile(r'#.*')
_SHELL_NUMBER_RE = re.compile(r'\b\d+\.?\d*\b')

# ---- Markdown ----
_MD_HEADER_RE = re.compile(r'^#{1,6}\s.*$', re.MULTILINE)
_MD_EMPHASIS_RE = re.compile(
    r'\*\*[^*]+\*\*|\*[^*]+\*|__[^_]+__|_[^_]+_'
)
_MD_CODE_RE = re.compile(r'```[\s\S]*?```|`[^`]+`')
_MD_LINK_RE = re.compile(r'\[[^\]]*\]\([^)]*\)')

# Each profile maps a highlight tag name to a list of patterns to apply for
# that tag. A list entry is either a compiled regex (the whole match is
# tagged) or a (regex, group) tuple (only that capture group is tagged) -
# used for _FUNCTION_RE, which matches trailing "(" as context but should
# only tag the name itself.
_LANGUAGE_PROFILES = {
    "python": {
        "comment": [_COMMENT_RE],
        "string": [_STRING_RE],
        "keyword": [_KEYWORD_RE],
        "number": [_NUMBER_RE],
        "function": [(_FUNCTION_RE, 1)],
    },
    "c_like": {
        "comment": [_C_LIKE_COMMENT_RE],
        "string": [_C_LIKE_STRING_RE],
        "keyword": [_C_LIKE_KEYWORD_RE],
        "number": [_C_LIKE_NUMBER_RE],
        "function": [(_FUNCTION_RE, 1)],
    },
    "html": {
        "comment": [_HTML_COMMENT_RE],
        "string": [_HTML_STRING_RE],
        "keyword": [_HTML_TAG_RE],
        "number": [],
        "function": [],
    },
    "css": {
        "comment": [_CSS_COMMENT_RE],
        "string": [_CSS_STRING_RE],
        "keyword": [_CSS_KEYWORD_RE],
        "number": [_CSS_NUMBER_RE],
        "function": [],
    },
    "json": {
        "comment": [],
        "string": [_JSON_STRING_RE],
        "keyword": [_JSON_KEYWORD_RE],
        "number": [_JSON_NUMBER_RE],
        "function": [_JSON_KEY_RE],
    },
    "yaml": {
        "comment": [_YAML_COMMENT_RE],
        "string": [_YAML_STRING_RE],
        "keyword": [],
        "number": [_YAML_NUMBER_RE],
        "function": [_YAML_KEY_RE],
    },
    "sql": {
        "comment": [_SQL_COMMENT_RE],
        "string": [_SQL_STRING_RE],
        "keyword": [_SQL_KEYWORD_RE],
        "number": [_SQL_NUMBER_RE],
        "function": [(_FUNCTION_RE, 1)],
    },
    "shell": {
        "comment": [_SHELL_COMMENT_RE],
        "string": [_SHELL_STRING_RE],
        "keyword": [_SHELL_KEYWORD_RE],
        "number": [_SHELL_NUMBER_RE],
        "function": [(_FUNCTION_RE, 1)],
    },
    "markdown": {
        "comment": [_MD_CODE_RE],
        "string": [_MD_EMPHASIS_RE],
        "keyword": [_MD_HEADER_RE],
        "number": [],
        "function": [_MD_LINK_RE],
    },
    "plaintext": {},
}

_EXT_TO_SYNTAX_PROFILE = {
    ".py": "python", ".pyw": "python",
    ".js": "c_like", ".jsx": "c_like", ".ts": "c_like", ".tsx": "c_like",
    ".c": "c_like", ".h": "c_like", ".cpp": "c_like", ".hpp": "c_like",
    ".java": "c_like",
    ".html": "html", ".htm": "html", ".xml": "html",
    ".css": "css",
    ".json": "json",
    ".yml": "yaml", ".yaml": "yaml",
    ".sql": "sql",
    ".sh": "shell",
    ".md": "markdown",
}


def _get_syntax_profile(path):
    """Pick the highlighting pattern set for a file, keyed by extension.
    A path-less (unsaved) buffer defaults to Python, matching this editor's
    long-standing default for new files."""
    if not path:
        return _LANGUAGE_PROFILES["python"]
    _, ext = os.path.splitext(path)
    name = _EXT_TO_SYNTAX_PROFILE.get(ext.lower(), "plaintext")
    return _LANGUAGE_PROFILES[name]


def _line_starts(content):
    """Cumulative character offset of the start of each line in `content`
    (0-indexed). Used to turn a regex match's character offset directly
    into a "line.col" Tk text index."""
    starts = [0]
    for line in content.split("\n")[:-1]:
        starts.append(starts[-1] + len(line) + 1)
    return starts


def _offset_to_index(offset, starts):
    """Convert a character offset (as produced by re.finditer over the
    whole-document string) into a "line.col" Tk index via binary search,
    instead of asking the Text widget to resolve "1.0+Nc" - which makes it
    recount characters from the start of the document for every match.
    With hundreds of matches per keystroke on a large file, that widget-side
    counting was the single biggest cost in syntax highlighting."""
    line = bisect.bisect_right(starts, offset) - 1
    col = offset - starts[line]
    return f"{line + 1}.{col}"


# ---------------- Autocompletion ----------------
# Dot-completion (os.path.j -> join, ...) needs to actually import whatever
# module is being completed on so it can introspect its real attributes.
# Blindly importlib.import_module()-ing any name the user typed would run
# that module's top-level code - fine for "os", not fine if the file being
# edited (which may not even be trusted) imports something with side
# effects. So this is restricted to the standard library only: it's the
# overwhelming majority of what people want completions for (os, sys, re,
# json, pathlib, itertools, ...) and every one of these modules is already
# on disk as part of the Python install, not something the file's author
# controls.
try:
    _STDLIB_MODULES = set(sys.stdlib_module_names)  # Python 3.10+
except AttributeError:
    _STDLIB_MODULES = {
        "os", "sys", "re", "io", "json", "math", "random", "time", "datetime",
        "collections", "itertools", "functools", "pathlib", "subprocess",
        "shutil", "tempfile", "typing", "string", "textwrap", "copy",
        "heapq", "bisect", "array", "struct", "hashlib", "hmac", "base64",
        "binascii", "csv", "sqlite3", "threading", "multiprocessing",
        "queue", "socket", "ssl", "http", "urllib", "email", "html", "xml",
        "argparse", "logging", "unittest", "traceback", "warnings",
        "contextlib", "abc", "enum", "dataclasses", "operator", "types",
        "inspect", "importlib", "glob", "fnmatch", "shlex", "platform",
        "getpass", "uuid", "secrets", "statistics", "decimal", "fractions",
        "zipfile", "tarfile", "gzip", "pickle", "copyreg", "weakref",
        "keyword", "tkinter",
    }

_BUILTIN_NAMES = set(dir(builtins))

_DOT_CHAIN_RE = re.compile(r'([A-Za-z_]\w*(?:\.[A-Za-z_]\w*)*)\.(\w*)$')
_WORD_TAIL_RE = re.compile(r'[A-Za-z_]\w*$')


def _extract_import_lines(content):
    """Pull out just the import statements so the AST parse (and the cache
    check below) stay cheap even on a large file - re-parsing the whole
    document on every keystroke just to see if the *imports* changed would
    defeat the point of caching."""
    return "\n".join(
        line for line in content.splitlines()
        if line.lstrip().startswith(("import ", "from "))
    )


def _build_import_map(import_source):
    """Parse only the import statements (never the rest of the file - this
    never executes anything the user wrote) and resolve each imported name
    to the real module object, but only for standard-library modules. Third
    -party or local imports are left unresolved, so completion on them is
    silently skipped rather than guessed at."""
    import_map = {}
    try:
        tree = ast.parse(import_source)
    except SyntaxError:
        return import_map

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                top_name = alias.name.split(".")[0]
                if top_name not in _STDLIB_MODULES:
                    continue
                local_name = alias.asname or top_name
                module_name = alias.name if alias.asname else top_name
                try:
                    import_map[local_name] = importlib.import_module(module_name)
                except Exception:
                    pass

        elif isinstance(node, ast.ImportFrom):
            if node.level or not node.module:
                continue  # relative import - nothing safe to resolve against
            top_name = node.module.split(".")[0]
            if top_name not in _STDLIB_MODULES:
                continue
            try:
                base_module = importlib.import_module(node.module)
            except Exception:
                continue
            for alias in node.names:
                if alias.name == "*":
                    continue
                local_name = alias.asname or alias.name
                obj = getattr(base_module, alias.name, None)
                if obj is None:
                    try:
                        obj = importlib.import_module(f"{node.module}.{alias.name}")
                    except Exception:
                        continue
                import_map[local_name] = obj

    return import_map


def _resolve_chain(chain_parts, import_map):
    if not chain_parts:
        return None
    obj = import_map.get(chain_parts[0])
    if obj is None:
        return None
    for part in chain_parts[1:]:
        obj = getattr(obj, part, None)
        if obj is None:
            return None
    return obj


def _attribute_candidates(obj, attr_prefix):
    try:
        names = dir(obj)
    except Exception:
        return []
    prefix_lower = attr_prefix.lower()
    show_private = attr_prefix.startswith("_")
    matches = sorted(
        n for n in names
        if n.lower().startswith(prefix_lower) and (show_private or not n.startswith("_"))
    )
    return matches[:8]


def _maximize_window(root):
    """Best-effort: open the window filling the screen instead of a small
    fixed size, using whichever mechanism the platform/window-manager
    actually supports.

    There's no single cross-platform way to do this in Tkinter - "zoomed"
    is the Windows (and some Linux WM) spelling, "-zoomed" is what most
    other Linux WMs want, and neither exists on macOS or a handful of
    minimal WMs, so each is tried in turn and we fall back to sizing the
    window to the full screen dimensions rather than leaving it small.
    """
    try:
        root.state("zoomed")
        return
    except tk.TclError:
        pass
    try:
        root.attributes("-zoomed", True)
        return
    except tk.TclError:
        pass
    root.geometry(f"{root.winfo_screenwidth()}x{root.winfo_screenheight()}+0+0")


def run():
    _apply_windows_dpi_awareness()

    root = tkinterdnd2.TkinterDnD.Tk() if tkinterdnd2 else tk.Tk()
    root.title("CodeForge")
    root.geometry("800x600")  # fallback size if maximizing isn't supported
    _maximize_window(root)
    root.config(bg=THEME["app_bg"], highlightthickness=0, bd=0)
    _apply_windows_dark_titlebar(root, is_dark_theme(THEME_NAME))

    # ttk widgets (Treeview, Notebook, Scrollbar) don't take bg=/fg=
    # directly, so give them a matching light theme via ttk.Style.
    style = ttk.Style()
    try:
        style.theme_use("clam")
    except tk.TclError:
        pass

    style.configure(
        "Treeview",
        background=THEME["sidebar_bg"],
        fieldbackground=THEME["sidebar_bg"],
        foreground=THEME["editor_fg"],
        borderwidth=0,
        bordercolor=THEME["sidebar_bg"],
        lightcolor=THEME["sidebar_bg"],
        darkcolor=THEME["sidebar_bg"]
    )
    style.map(
        "Treeview",
        background=[("selected", THEME["editor_select_bg"])],
        foreground=[("selected", THEME["editor_select_fg"])]
    )

    style.configure(
        "TNotebook",
        background=THEME["app_bg"],
        borderwidth=0,
        bordercolor=THEME["border"],
        # clam draws a light/dark bevel around the notebook and its tabs by
        # default; without pinning these too (same fix as the scrollbars
        # below), that bevel shows up as a stray white edge around every
        # tab strip in dark mode.
        lightcolor=THEME["app_bg"],
        darkcolor=THEME["app_bg"]
    )
    style.configure(
        "TNotebook.Tab",
        background=THEME["panel_header_bg"],
        foreground=THEME["panel_header_fg"],
        padding=(10, 4),
        borderwidth=0,
        bordercolor=THEME["border"],
        lightcolor=THEME["panel_header_bg"],
        darkcolor=THEME["panel_header_bg"]
    )
    style.map(
        "TNotebook.Tab",
        background=[("selected", THEME["editor_bg"])],
        foreground=[("selected", THEME["editor_fg"])],
        lightcolor=[("selected", THEME["editor_bg"])],
        darkcolor=[("selected", THEME["editor_bg"])]
    )

    # Editor tabs get their own style (rather than restyling "TNotebook.Tab"
    # globally) so the little close "x" only shows up on file tabs - the
    # Output/Terminal/Music tabs on bottom_panel keep the plain look, since
    # those aren't closable.
    #
    # tk.PhotoImage has no real alpha blending, but a freshly created one is
    # fully transparent until pixels are explicitly set - so drawing just the
    # X's diagonals and leaving everything else untouched gives a clean
    # icon that sits correctly on top of both selected and unselected tab
    # colors, in every theme, without needing a background color at all.
    def _make_close_icon(color, size=12):
        img = tk.PhotoImage(width=size, height=size)
        inset = 3
        for i in range(inset, size - inset):
            img.put(color, (i, i))
            img.put(color, (i, i + 1))
            img.put(color, (size - 1 - i, i))
            img.put(color, (size - 1 - i, i + 1))
        return img

    # Referenced by the style's element images - kept alive on the style
    # object itself since ttk holds the images by name only. Losing the
    # last live Python reference to a PhotoImage lets Tk garbage-collect
    # its pixel data even though the name is still registered.
    style._close_tab_icons = (
        _make_close_icon(THEME["muted_fg"]),
        _make_close_icon(THEME["panel_header_fg"]),
        _make_close_icon(THEME["panel_header_fg"]),
    )
    icon_normal, icon_active, icon_pressed = style._close_tab_icons

    style.element_create(
        "EditorTab.close", "image", icon_normal,
        ("pressed", icon_pressed), ("active", icon_active),
        border=6, sticky=""
    )
    style.layout(
        "EditorTabs.TNotebook.Tab",
        [("TNotebook.tab", {"sticky": "nswe", "children": [
            ("TNotebook.padding", {"side": "top", "sticky": "nswe", "children": [
                ("TNotebook.focus", {"side": "top", "sticky": "nswe", "children": [
                    ("TNotebook.label", {"side": "left", "sticky": ""}),
                    ("EditorTab.close", {"side": "right", "sticky": ""}),
                ]}),
            ]}),
        ]})]
    )
    style.configure(
        "EditorTabs.TNotebook",
        background=THEME["app_bg"],
        borderwidth=0,
        bordercolor=THEME["border"],
        lightcolor=THEME["app_bg"],
        darkcolor=THEME["app_bg"]
    )
    style.configure(
        "EditorTabs.TNotebook.Tab",
        background=THEME["panel_header_bg"],
        foreground=THEME["panel_header_fg"],
        padding=(10, 4, 6, 4),
        borderwidth=0,
        bordercolor=THEME["border"],
        lightcolor=THEME["panel_header_bg"],
        darkcolor=THEME["panel_header_bg"]
    )
    style.map(
        "EditorTabs.TNotebook.Tab",
        background=[("selected", THEME["editor_bg"])],
        foreground=[("selected", THEME["editor_fg"])],
        lightcolor=[("selected", THEME["editor_bg"])],
        darkcolor=[("selected", THEME["editor_bg"])]
    )

    for orientation in ("Vertical", "Horizontal"):
        style.configure(
            f"{orientation}.TScrollbar",
            background=THEME["panel_header_bg"],
            troughcolor=THEME["app_bg"],
            bordercolor=THEME["border"],
            arrowcolor=THEME["panel_header_fg"],
            # clam draws a light/dark bevel around the trough and thumb by
            # default; without pinning these too, that bevel shows up as a
            # stray light edge around every scrollbar in dark mode.
            lightcolor=THEME["panel_header_bg"],
            darkcolor=THEME["panel_header_bg"],
            relief="flat"
        )
        style.map(
            f"{orientation}.TScrollbar",
            background=[("active", THEME["border"])],
            lightcolor=[("active", THEME["border"])],
            darkcolor=[("active", THEME["border"])]
        )

    # tk.Menu doesn't inherit from THEME automatically, so every menu (the
    # top bar's dropdowns and the two right-click context menus) needs these
    # colors explicitly - otherwise they'd pop up in the OS's default light
    # style even with the rest of the app in dark mode.
    # Note: on Windows, the top-level menu STRIP itself is drawn natively by
    # the OS and ignores these colors - but the dropdowns that open from it
    # (File, Edit, Run, View) and the right-click context menus do respect
    # them, so this is what actually fixes the "light popup in dark mode"
    # look.
    menu_opts = {
        "bg": THEME["panel_header_bg"],
        "fg": THEME["panel_header_fg"],
        "activebackground": THEME["editor_select_bg"],
        "activeforeground": THEME["editor_select_fg"],
        "disabledforeground": THEME["muted_fg"],
        "relief": "flat",
        "borderwidth": 0,
        "activeborderwidth": 0,
    }

    # ---------------- Custom menu bar ----------------
    # A native tk.Menu's top-level STRIP is drawn by the OS on Windows and
    # ignores bg/fg entirely (only the dropdowns that open from it respect
    # theme colors) - that's what left the "File Edit Run View" row stuck
    # white even in dark mode. Building the strip ourselves out of themed
    # Menubuttons (each still posting a themed tk.Menu dropdown) fixes that
    # completely. It's packed here, before the status bar/main pane, so it
    # claims the top strip; the actual Menubuttons/dropdowns are filled in
    # near the end of run() once their commands (new_file, save_file, etc.)
    # exist.
    menu_bar_frame = tk.Frame(root, bg=THEME["panel_header_bg"], highlightthickness=0, bd=0)
    menu_bar_frame.pack(side="top", fill="x")

    # ---------------- Status bar ----------------
    # Packed (not just created) before the main paned window so it reserves
    # its strip at the bottom instead of being squeezed out by expand=True.
    status_bar = tk.Frame(
        root,
        bg=THEME["panel_header_bg"],
        height=24,
        highlightthickness=0,
        bd=0
    )
    status_bar.pack(side="bottom", fill="x")
    status_bar.pack_propagate(False)

    # Thin divider so the status bar reads as its own panel instead of
    # blending into (or clashing with) the editor area above it.
    status_bar_divider = tk.Frame(root, bg=THEME["border"], height=1)
    status_bar_divider.pack(side="bottom", fill="x")

    status_position_label = tk.Label(
        status_bar,
        text="Ln 1, Col 1",
        bg=THEME["panel_header_bg"],
        fg=THEME["panel_header_fg"],
        anchor="w",
        padx=10
    )
    status_position_label.pack(side="left")

    # Mirrors whatever's loaded in the Music tab so you can see/skip
    # tracks without switching off the tab you're actually working in.
    # Text and click-to-focus-tab binding are wired up once the Music tab
    # itself exists further down in run().
    status_music_label = tk.Label(
        status_bar,
        text="",
        bg=THEME["panel_header_bg"],
        fg=THEME["panel_header_fg"],
        anchor="w",
        padx=10,
        cursor="hand2"
    )
    status_music_label.pack(side="left")

    # Mirrors the current branch from the Source Control tab, the same
    # way status_music_label mirrors the Music tab - text/click-to-focus
    # binding wired up once the Source Control tab itself exists further
    # down in run().
    status_git_label = tk.Label(
        status_bar,
        text="",
        bg=THEME["panel_header_bg"],
        fg=THEME["panel_header_fg"],
        anchor="w",
        padx=10,
        cursor="hand2"
    )
    status_git_label.pack(side="left")

    status_focus_label = tk.Label(
        status_bar,
        text="",
        bg=THEME["panel_header_bg"],
        fg=THEME["accent"],
        anchor="w",
        padx=10
    )
    status_focus_label.pack(side="left")

    status_filetype_label = tk.Label(
        status_bar,
        text="Plain Text",
        bg=THEME["panel_header_bg"],
        fg=THEME["panel_header_fg"],
        anchor="e",
        padx=10
    )
    status_filetype_label.pack(side="right")

    status_theme_label = tk.Label(
        status_bar,
        text="\U0001F3A8 " + THEME_LABELS.get(THEME_NAME, THEME_NAME.title()),
        bg=THEME["panel_header_bg"],
        fg=THEME["panel_header_fg"],
        anchor="e",
        padx=10,
        cursor="hand2"
    )
    status_theme_label.pack(side="right")
    status_theme_label.bind("<Button-1>", lambda e: cycle_theme())

    LANGUAGE_LABELS = {
        ".py": "Python",
        ".pyw": "Python",
        ".js": "JavaScript",
        ".jsx": "JavaScript (React)",
        ".ts": "TypeScript",
        ".tsx": "TypeScript (React)",
        ".html": "HTML",
        ".htm": "HTML",
        ".css": "CSS",
        ".json": "JSON",
        ".md": "Markdown",
        ".txt": "Plain Text",
        ".sh": "Shell Script",
        ".c": "C",
        ".h": "C Header",
        ".cpp": "C++",
        ".hpp": "C++ Header",
        ".java": "Java",
        ".xml": "XML",
        ".yml": "YAML",
        ".yaml": "YAML",
        ".sql": "SQL",
    }

    def get_language_label(path):
        if not path:
            return "Plain Text"
        _, ext = os.path.splitext(path)
        return LANGUAGE_LABELS.get(ext.lower(), "Plain Text")

    def update_status_bar(editor):
        if not editor:
            status_position_label.config(text="")
            status_filetype_label.config(text="")
            return

        text_area = editor["text"]
        try:
            line, col = text_area.index("insert").split(".")
            status_position_label.config(text=f"Ln {line}, Col {int(col) + 1}")
        except tk.TclError:
            status_position_label.config(text="")

        status_filetype_label.config(text=get_language_label(editor["path"]))

    main_frame = tk.PanedWindow(
        root,
        orient="horizontal",
        sashrelief="flat",
        sashwidth=4,
        bd=0,
        bg=THEME["app_bg"]
    )
    main_frame.pack(fill="both", expand=True)

    explorer_frame = tk.Frame(main_frame, width=220, bg=THEME["sidebar_bg"], highlightthickness=0, bd=0)
    explorer_frame.pack_propagate(False)

    tk.Label(
        explorer_frame,
        text="EXPLORER",
        bg=THEME["panel_header_bg"],
        fg=THEME["panel_header_fg"],
        anchor="w"
    ).pack(fill="x", padx=10, pady=5)

    project_tree = ttk.Treeview(explorer_frame, show="tree")
    project_tree.pack(fill="both", expand=True)
    project_tree.tag_configure(
        "active_file",
        background=THEME["tree_active_bg"],
        foreground=THEME["tree_active_fg"]
    )
    # Explorer row colors mirroring `git status` - staged/modified/
    # untracked - refreshed by apply_git_status_tags() below whenever the
    # tree or the Source Control tab reports new status.
    project_tree.tag_configure("git_staged", foreground=THEME["accent"])
    project_tree.tag_configure("git_modified", foreground=THEME["search_current_bg"])
    project_tree.tag_configure("git_untracked", foreground=THEME["syntax_comment"])

    main_frame.add(explorer_frame, width=220, minsize=120, stretch="never")

    center_frame = tk.Frame(main_frame, bg=THEME["app_bg"], highlightthickness=0, bd=0)
    main_frame.add(center_frame, minsize=300, stretch="always")

    tab_control = ttk.Notebook(center_frame, style="EditorTabs.TNotebook")
    tab_control.pack(fill="both", expand=True)

    project_path = None
    tab_editors = {}       # tab widget name (str) -> editor dict
    untitled_count = [0]   # counter used to name new blank tabs

    # Editor font size - shared across all tabs (like most editors' zoom),
    # persisted so it's restored on next launch. Kept in a dict rather than
    # a bare variable so nested functions can mutate it without `nonlocal`.
    font_state = {"size": load_font_size_preference()}

    def current_editor_font():
        return ("Consolas", font_state["size"])

    # Recently-opened files, most-recent first - persisted so "Open Recent"
    # survives a restart. Kept in a dict (like font_state) so nested
    # functions can mutate the list without `nonlocal`.
    recent_files_state = {"paths": load_recent_files()}

    # Minimap - a zoomed-out overview of the whole file for quick
    # navigation, shared on/off state so new tabs match whatever the user
    # last chose.
    MINIMAP_WIDTH = 100
    minimap_state = {"visible": True}
    # Fixed pixel height for every line-bar in the minimap - like VS Code/
    # Sublime, a line is always a thin mark. row_height used to be
    # canvas_h / row_count, which *stretched* each row to fill the whole
    # strip vertically - fine for a long file, but on a short one it blew
    # each line up into a tall, chunky block instead of leaving the rest
    # of the strip empty underneath.
    MINIMAP_ROW_HEIGHT = 3

    # CRT Scanlines - off by default so it doesn't surprise anyone who
    # just picks the CRT theme for the colors. Shared across tabs like
    # minimap_state, for the same reason (new tabs need to match whatever
    # was last chosen).
    crt_state = {"scanlines": False}

    # ---------------- Output / Terminal panel ----------------

    output_frame = tk.Frame(main_frame, width=300, bg=THEME["app_bg"], highlightthickness=0, bd=0)
    output_frame.pack_propagate(False)

    # Toolbar row above the Output/Terminal tabs - quick access to the
    # three actions you'd otherwise have to dig into the Run menu for.
    # Defined here (before run_code/kill_running/clear_output exist)
    # is fine: the button `command` lambdas only look those names up when
    # actually clicked, by which point run() has finished defining them.
    terminal_toolbar_opts = {
        "bg": THEME["panel_header_bg"],
        "fg": THEME["panel_header_fg"],
        "activebackground": THEME["editor_select_bg"],
        "activeforeground": THEME["editor_select_fg"],
        "relief": "flat",
        "bd": 0,
        "highlightthickness": 0,
        "padx": 8,
        "pady": 3,
        "cursor": "hand2",
    }
    terminal_toolbar = tk.Frame(output_frame, bg=THEME["panel_header_bg"], highlightthickness=0, bd=0)
    terminal_toolbar.pack(side="top", fill="x")

    run_button = tk.Button(
        terminal_toolbar, text="\u25B6 Run", command=lambda: run_code(),
        **terminal_toolbar_opts
    )
    run_button.pack(side="left")

    kill_button = tk.Button(
        terminal_toolbar, text="\u25A0 Kill", command=lambda: kill_running(),
        **terminal_toolbar_opts
    )
    kill_button.pack(side="left")

    clear_button = tk.Button(
        terminal_toolbar, text="\u2716 Clear", command=lambda: clear_output(),
        **terminal_toolbar_opts
    )
    clear_button.pack(side="left")

    toolbar_divider = tk.Frame(output_frame, bg=THEME["border"], height=1)
    toolbar_divider.pack(side="top", fill="x")

    bottom_panel = ttk.Notebook(output_frame)
    bottom_panel.pack(fill="both", expand=True)

    # ---- Output tab (Run results) ----
    output_tab = tk.Frame(bottom_panel, bg=THEME["output_bg"])
    bottom_panel.add(output_tab, text="Output")

    output_area = tk.Text(
        output_tab,
        font=("Consolas", 10),
        bg=THEME["output_bg"],
        fg=THEME["output_fg"],
        insertbackground=THEME["editor_insert"],
        selectbackground=THEME["editor_select_bg"],
        selectforeground=THEME["editor_select_fg"],
        highlightthickness=0,
        border=0,
        state="disabled",
        wrap="word"
    )
    output_area.pack(side="left", fill="both", expand=True)

    output_scrollbar = ttk.Scrollbar(
        output_tab,
        orient="vertical",
        command=output_area.yview,
        style="Vertical.TScrollbar"
    )
    output_scrollbar.pack(side="right", fill="y")
    output_area.config(yscrollcommand=output_scrollbar.set)
    output_area.tag_configure("taunt", foreground="orange")

    # ---- Terminal tab (spawns your real system terminal) ----
    # No embedded shell/pseudo-console here on purpose - trying to emulate
    # a terminal (cursor tracking, line wrapping, escape codes, PSReadLine
    # redraws...) inside a Tk Text widget is a deep rabbit hole and never
    # quite matches the real thing. Instead this just launches your OS's
    # actual terminal app (Windows Terminal/PowerShell, macOS Terminal,
    # or whatever's on Linux) as its own separate window, the same way
    # Code::Blocks/Dev-C++ hand off to a real console for "Run" below.
    terminal_tab = tk.Frame(bottom_panel, bg=THEME["output_bg"])
    bottom_panel.add(terminal_tab, text="Terminal")

    tk.Label(
        terminal_tab,
        text=(
            "\U0001F5A5  Opens your system's own terminal app in the "
            "current project folder - a separate window, not an emulated "
            "one inside CodeForge."
        ),
        bg=THEME["output_bg"], fg=THEME["muted_fg"], justify="left",
        wraplength=260, padx=16, pady=16, anchor="w",
    ).pack(anchor="w", fill="x")

    _term_tab_btn_opts = {
        "bg": THEME["panel_header_bg"], "fg": THEME["panel_header_fg"],
        "activebackground": THEME["editor_select_bg"], "activeforeground": THEME["editor_select_fg"],
        "relief": "flat", "bd": 0, "highlightthickness": 0, "padx": 10, "pady": 4, "cursor": "hand2",
    }
    open_terminal_btn = tk.Button(
        terminal_tab, text="\u25B6 Open Terminal", command=lambda: open_external_terminal(),
        **_term_tab_btn_opts
    )
    open_terminal_btn.pack(anchor="w", padx=16, pady=(0, 16))

    # ---- Music tab (background YouTube playlist player) ----
    # Fully optional - degrades to an install hint if yt-dlp/python-vlc
    # aren't present, same graceful-fallback pattern as tkinterdnd2 above.
    # Placed after Terminal so the notebook reads Output / Terminal /
    # Music left to right.
    music_tab = tk.Frame(bottom_panel, bg=THEME["output_bg"])
    bottom_panel.add(music_tab, text="\u266A Music")

    def _update_music_status_label(title, is_playing):
        if title:
            icon = "\u266A" if is_playing else "\u23F8"
            status_music_label.config(text=f"{icon} {title}")
        else:
            status_music_label.config(text="")

    music_controls = music_player.build_music_panel(
        music_tab, THEME, on_track_change=_update_music_status_label
    )

    def _focus_music_tab(event=None):
        bottom_panel.select(music_tab)

    status_music_label.bind("<Button-1>", _focus_music_tab)

    # ---- Source Control tab (git status/stage/commit/push/pull) ----
    # Fully optional - degrades to an install hint if a `git` executable
    # isn't on PATH, same graceful-fallback pattern as Music above.
    git_tab = tk.Frame(bottom_panel, bg=THEME["output_bg"])
    bottom_panel.add(git_tab, text="\u2325 Git")

    def _update_git_status_label(branch, ahead, behind):
        if branch:
            text = f"\u2325 {branch}"
            if ahead:
                text += f" \u2191{ahead}"
            if behind:
                text += f" \u2193{behind}"
            status_git_label.config(text=text)
        else:
            status_git_label.config(text="")

    git_controls = git_panel.build_git_panel(
        git_tab, THEME,
        get_project_path=lambda: project_path,
        on_status_change=_update_git_status_label,
        on_open_file=lambda p: _open_path_in_tab(p),
    )

    def _focus_git_tab(event=None):
        bottom_panel.select(git_tab)

    status_git_label.bind("<Button-1>", _focus_git_tab)

    def refresh_git_state():
        """Called after anything that can change git status - a save, a
        folder open, an external refresh - so the Source Control tab and
        the explorer's status colors both stay current. Cheap to call
        liberally: both halves no-op quickly if nothing's actually
        changed."""
        git_controls["refresh"]()
        apply_git_status_tags()

    main_frame.add(output_frame, width=300, minsize=150, stretch="never")

    # ---------- External terminal + run process ----------
    # Both the Terminal tab and "Run" hand off to a real, separate OS
    # process/window instead of an embedded pseudo-console - no shell
    # output is piped back into CodeForge and parsed/replayed here, so
    # there's no cursor tracking, escape-code parsing, or line-wrap math
    # to get out of sync with the real thing (which is what made the old
    # embedded terminal glitchy, especially with PowerShell's own
    # cursor-heavy redraws). It also means whatever you run keeps working
    # normally for interactive input (input()/Console.ReadLine()/etc.),
    # exactly like Code::Blocks or Dev-C++ popping open a console window.
    IS_WINDOWS = (os.name == "nt")

    # Tracks the most recent external process spawned by Run, so "Kill"
    # has something to terminate. Not used for Terminal - that window is
    # fully independent of CodeForge once opened.
    run_state = {"proc": None}

    def _project_cwd():
        return project_path if project_path and os.path.isdir(project_path) else os.getcwd()

    def open_external_terminal():
        """Launches the user's own terminal app in a new window, cwd'd to
        the current project folder (or CodeForge's own cwd if no folder
        is open)."""
        cwd = _project_cwd()
        try:
            if IS_WINDOWS:
                wt = shutil.which("wt") or shutil.which("wt.exe")
                if wt:
                    subprocess.Popen([wt, "-d", cwd])
                else:
                    subprocess.Popen(
                        ["powershell.exe", "-NoExit", "-Command",
                         f"Set-Location -LiteralPath '{cwd}'"],
                        cwd=cwd,
                        creationflags=subprocess.CREATE_NEW_CONSOLE,
                    )
            elif sys.platform == "darwin":
                subprocess.Popen(["open", "-a", "Terminal", cwd])
            else:
                for exe, args in (
                    ("x-terminal-emulator", []),
                    ("gnome-terminal", [f"--working-directory={cwd}"]),
                    ("konsole", ["--workdir", cwd]),
                    ("xfce4-terminal", [f"--working-directory={cwd}"]),
                    ("xterm", []),
                ):
                    path = shutil.which(exe)
                    if path:
                        subprocess.Popen([path] + args, cwd=cwd)
                        return
                messagebox.showerror(
                    "Open Terminal",
                    "Couldn't find a terminal emulator on this system "
                    "(tried gnome-terminal, konsole, xfce4-terminal, xterm).\n"
                    "Install one and try again."
                )
        except Exception as e:
            messagebox.showerror("Open Terminal", f"Couldn't open a terminal:\n{e}")

    def _spawn_run_console(interpreter, filename, run_dir):
        """Spawns a new console window that runs `interpreter filename`
        (cwd=run_dir) and pauses at the end so the output stays on screen
        - the same handoff Code::Blocks/Dev-C++ do for "Run". Returns the
        Popen handle for the spawned process."""
        if IS_WINDOWS:
            # NOT a hand-built '{interpreter} "{filename}" & ...' string -
            # cmd.exe's own quote handling doesn't treat backslash-quote
            # as an escape the way subprocess's list2cmdline (which runs
            # on any string passed as a single list element) assumes it
            # will. The two disagree on what the quotes mean, and the
            # result is cmd.exe misparsing the whole line - which is what
            # spliced the current directory in front of the filename with
            # a stray quote and doubled backslashes. Passing each token as
            # its own list element instead lets subprocess quote only the
            # filename (and only if it actually needs it), which both
            # subprocess and cmd.exe agree on.
            return subprocess.Popen(
                ["cmd.exe", "/c", interpreter, filename, "&", "echo.", "&", "pause"],
                cwd=run_dir,
                creationflags=subprocess.CREATE_NEW_CONSOLE,
            )
        if sys.platform == "darwin":
            # macOS Terminal.app can be pointed at a script file directly
            # (a ".command" file), which is simpler and more reliable than
            # driving it via osascript.
            script = (
                f"cd {shlex.quote(run_dir)}\n"
                f"{interpreter} {shlex.quote(filename)}\n"
                "echo\nread -n 1 -s -r -p 'Press any key to close...'\n"
            )
            with tempfile.NamedTemporaryFile(mode="w", suffix=".command", delete=False) as tmp:
                tmp.write(script)
                script_path = tmp.name
            os.chmod(script_path, 0o755)
            return subprocess.Popen(["open", script_path])

        inner = (
            f"cd {shlex.quote(run_dir)} && {interpreter} {shlex.quote(filename)}; "
            "echo; read -n 1 -s -r -p 'Press any key to close...'"
        )
        for exe, args in (
            ("x-terminal-emulator", ["-e", "bash", "-c", inner]),
            ("gnome-terminal", ["--", "bash", "-c", inner]),
            ("konsole", ["-e", "bash", "-c", inner]),
            ("xfce4-terminal", ["-e", f"bash -c {shlex.quote(inner)}"]),
            ("xterm", ["-e", "bash", "-c", inner]),
        ):
            path = shutil.which(exe)
            if path:
                return subprocess.Popen([path] + args)
        raise RuntimeError(
            "No terminal emulator found to run the program in "
            "(tried gnome-terminal, konsole, xfce4-terminal, xterm)."
        )

    def kill_running():
        """Force-closes the most recent Run's console window/process
        tree. Harmless no-op if nothing's currently running."""
        proc = run_state.get("proc")
        if not proc or proc.poll() is not None:
            return
        try:
            if IS_WINDOWS:
                # proc is cmd.exe, with the real interpreter as a child -
                # plain terminate() only kills cmd.exe and leaves the
                # child running, so kill the whole tree instead.
                subprocess.run(
                    ["taskkill", "/F", "/T", "/PID", str(proc.pid)],
                    capture_output=True
                )
            else:
                proc.terminate()
        except Exception:
            pass

    def clear_output():
        """Wipes the Output panel."""
        output_area.config(state="normal")
        output_area.delete("1.0", tk.END)
        output_area.config(state="disabled")


    # ---------- Current-tab helpers ----------
    def get_current_tab():
        tabs = tab_control.tabs()
        if not tabs:
            return None
        return tab_control.select()

    def get_current_editor():
        tab = get_current_tab()
        if not tab:
            return None
        return tab_editors.get(tab)

    # ---------- Line numbers ----------
    def update_line_numbers(editor):
        text_area = editor["text"]
        line_numbers = editor["line_numbers"]

        num_lines = int(text_area.index("end-1c").split(".")[0])

        # Typing within an existing line (the overwhelmingly common case)
        # never changes the line count, so the gutter's text is identical
        # to what's already there - skip the delete/rebuild/reinsert and
        # its state toggling entirely in that case.
        if editor.get("last_line_count") == num_lines:
            return
        editor["last_line_count"] = num_lines

        line_numbers.config(state="normal")
        line_numbers.delete("1.0", tk.END)
        line_numbers.insert("1.0", "\n".join(str(i) for i in range(1, num_lines + 1)))
        line_numbers.config(state="disabled")

    # ---------- Syntax highlighting ----------
    def setup_highlight_tags(text_area):
        text_area.tag_configure("keyword", foreground=THEME["syntax_keyword"])
        text_area.tag_configure("string", foreground=THEME["syntax_string"])
        text_area.tag_configure("comment", foreground=THEME["syntax_comment"])
        text_area.tag_configure("number", foreground=THEME["syntax_number"])
        text_area.tag_configure("function", foreground=THEME["syntax_function"])

        # Background-only tag for the current line - keep it lowest priority
        # so it never hides syntax colors or the selection highlight.
        text_area.tag_configure("current_line", background=THEME["current_line_bg"])
        text_area.tag_lower("current_line")

        # Highlights for the bracket under/next to the cursor and its pair.
        text_area.tag_configure(
            "bracket_match",
            background=THEME["bracket_match_bg"],
            borderwidth=1,
            relief="solid"
        )

        # Find/replace highlights - all matches, and the one currently selected.
        text_area.tag_configure("search_match", background=THEME["search_match_bg"])
        text_area.tag_configure("search_current", background=THEME["search_current_bg"])

        # Faint banding on every other line - the "CRT Scanlines" View menu
        # toggle turns this on/off. Configured here (colors baked in at
        # creation like every other tag) but only ever *applied* to text
        # when the toggle is on, in apply_crt_scanlines() below. Lowered
        # last so it always sits underneath current_line/selection/syntax
        # colors instead of muddying them.
        text_area.tag_configure("crt_scanline", background=_scanline_bg())
        text_area.tag_lower("crt_scanline")

    def highlight_current_line(text_area):
        text_area.tag_remove("current_line", "1.0", tk.END)
        line = text_area.index("insert").split(".")[0]
        text_area.tag_add("current_line", f"{line}.0", f"{line}.0+1line")

    # ---------- Bracket-match highlighting ----------
    BRACKET_OPENERS = {"(": ")", "[": "]", "{": "}"}
    BRACKET_CLOSERS = {v: k for k, v in BRACKET_OPENERS.items()}

    def _is_code_position(text_area, index):
        # Ignore brackets that live inside strings/comments so matching
        # doesn't get thrown off by e.g. a "(" inside a string literal.
        tags = text_area.tag_names(index)
        return "string" not in tags and "comment" not in tags

    def find_matching_bracket(text_area, index):
        char = text_area.get(index)
        doc_start = "1.0"
        doc_end = text_area.index("end-1c")

        if char in BRACKET_OPENERS:
            close_char = BRACKET_OPENERS[char]
            depth = 1
            pos = text_area.index(f"{index}+1c")
            while text_area.compare(pos, "<", doc_end):
                if _is_code_position(text_area, pos):
                    c = text_area.get(pos)
                    if c == char:
                        depth += 1
                    elif c == close_char:
                        depth -= 1
                        if depth == 0:
                            return pos
                pos = text_area.index(f"{pos}+1c")
            return None

        if char in BRACKET_CLOSERS:
            open_char = BRACKET_CLOSERS[char]
            depth = 1
            pos = text_area.index(f"{index}-1c")
            while True:
                if _is_code_position(text_area, pos):
                    c = text_area.get(pos)
                    if c == char:
                        depth += 1
                    elif c == open_char:
                        depth -= 1
                        if depth == 0:
                            return pos
                if text_area.compare(pos, "<=", doc_start):
                    return None
                pos = text_area.index(f"{pos}-1c")

        return None

    def highlight_brackets(text_area):
        text_area.tag_remove("bracket_match", "1.0", tk.END)

        doc_end = text_area.index("end-1c")
        candidates = [text_area.index("insert-1c"), text_area.index("insert")]

        for index in candidates:
            if text_area.compare(index, ">=", doc_end):
                continue
            char = text_area.get(index)
            if char in BRACKET_OPENERS or char in BRACKET_CLOSERS:
                match = find_matching_bracket(text_area, index)
                if match:
                    text_area.tag_add("bracket_match", index, f"{index}+1c")
                    text_area.tag_add("bracket_match", match, f"{match}+1c")
                break

    def _clear_indent_guides(editor):
        # Reset the reuse pool for this redraw. The canvases themselves are
        # kept alive (not destroyed) - destroying and recreating a Canvas
        # per guide run on every scroll tick was expensive enough to leave
        # a visible gap each time, which is what made the guides look like
        # they were flickering in and out while scrolling. Repositioning
        # existing widgets instead is effectively instant.
        editor["guide_pool_used"] = 0

    def _hide_unused_guides(editor):
        pool = editor["guide_canvases"]
        for guide in pool[editor["guide_pool_used"]:]:
            guide.place_forget()

    def _draw_guide_run(editor, start_row, end_row, x):
        text_area = editor["text"]
        widget_height = text_area.winfo_height()

        top_info = text_area.dlineinfo(f"{start_row}.0")
        bottom_info = text_area.dlineinfo(f"{end_row}.0")

        if not top_info and not bottom_info:
            return  # this run is scrolled fully out of view

        y_top = max(top_info[1] if top_info else 0, 0)
        y_bottom = min(
            (bottom_info[1] + bottom_info[3]) if bottom_info else widget_height,
            widget_height
        )

        if y_bottom <= y_top:
            return

        # A 1px-wide canvas strip *is* the line - true pixel precision,
        # instead of a whole-character-cell background block. Reuse a
        # pooled canvas if one's free instead of always creating a new one.
        pool = editor["guide_canvases"]
        idx = editor["guide_pool_used"]
        if idx < len(pool):
            guide = pool[idx]
            guide.configure(height=y_bottom - y_top, bg=THEME["indent_guide"])
        else:
            guide = tk.Canvas(
                editor["editor_frame"],
                width=1,
                height=y_bottom - y_top,
                bg=THEME["indent_guide"],
                highlightthickness=0,
                bd=0
            )
            pool.append(guide)
        guide.place(in_=text_area, x=x, y=y_top)
        editor["guide_pool_used"] = idx + 1

    def update_indent_guides(editor):
        text_area = editor["text"]
        if not text_area.winfo_exists():
            return

        _clear_indent_guides(editor)
        try:
            text_area.update_idletasks()

            total_lines = int(text_area.index("end-1c").split(".")[0])
            indent_width = 4

            # Guides are only ever drawn for on-screen lines (see
            # _draw_guide_run's dlineinfo check), so there's no point
            # scanning and measuring every line of the document here - that
            # used to make every redraw (including one per keystroke) cost
            # O(file size). A small pad above/below keeps guide runs that
            # straddle the viewport edge looking continuous.
            widget_height = text_area.winfo_height()
            first_visible = int(text_area.index("@0,0").split(".")[0])
            last_visible = int(text_area.index(f"@0,{max(widget_height - 1, 0)}").split(".")[0])
            first_visible = max(1, first_visible - 5)
            last_visible = min(total_lines, last_visible + 5)

            indent_lens = {}
            for line_no in range(first_visible, last_visible + 1):
                line_text = text_area.get(f"{line_no}.0", f"{line_no}.end")
                stripped = line_text.lstrip(" ")
                indent_lens[line_no] = len(line_text) - len(stripped)

            max_indent = max(indent_lens.values()) if indent_lens else 0
            if max_indent < indent_width:
                return

            # Column 0's pixel x-position, so every guide column can be
            # placed with exact pixel math instead of relying on tag-cell
            # widths.
            anchor_bbox = text_area.bbox(f"{first_visible}.0")
            if not anchor_bbox:
                return

            guide_font = tkfont.Font(font=text_area.cget("font"))
            char_width = guide_font.measure("0")
            left_x = anchor_bbox[0]

            for col in range(0, max_indent, indent_width):
                x = left_x + col * char_width
                row = first_visible
                while row <= last_visible:
                    if indent_lens.get(row, 0) > col:
                        run_start = row
                        while row <= last_visible and indent_lens.get(row, 0) > col:
                            row += 1
                        _draw_guide_run(editor, run_start, row - 1, x)
                    else:
                        row += 1
        finally:
            # Whichever way update_indent_guides exits, any pooled canvases
            # left over from a previous redraw (e.g. this one found fewer
            # runs than last time) still need to be hidden - otherwise a
            # guide from before would keep showing after it should've gone.
            _hide_unused_guides(editor)

    def apply_crt_scanlines(editor):
        # Bands every other logical line. Tags stay attached to whichever
        # characters they were applied to as text shifts around, so unlike
        # a "paint pixel row N" overlay this needs recomputing after every
        # edit (not just on toggle/theme change) or the banding would drift
        # out of odd/even sync with the visible lines - which is exactly
        # why this is called from highlight_syntax, the existing per-edit
        # hook, rather than wired up separately.
        text_area = editor["text"]
        text_area.tag_remove("crt_scanline", "1.0", tk.END)
        if not crt_state["scanlines"]:
            return
        line_count = int(text_area.index("end-1c").split(".")[0])
        for line in range(2, line_count + 1, 2):
            text_area.tag_add("crt_scanline", f"{line}.0", f"{line}.0+1line")

    def highlight_syntax(editor):
        text_area = editor["text"]
        for tag in ("keyword", "string", "comment", "number", "function"):
            text_area.tag_remove(tag, "1.0", tk.END)
        apply_crt_scanlines(editor)

        profile = _get_syntax_profile(editor.get("path"))
        if not profile:
            return  # plaintext - no patterns to apply

        content = text_area.get("1.0", tk.END)
        starts = _line_starts(content)

        for tag_name, patterns in profile.items():
            for pattern in patterns:
                if isinstance(pattern, tuple):
                    regex, group = pattern
                else:
                    regex, group = pattern, 0
                for match in regex.finditer(content):
                    start = _offset_to_index(match.start(group), starts)
                    end = _offset_to_index(match.end(group), starts)
                    text_area.tag_add(tag_name, start, end)

    # ---------- Minimap ----------
    # A zoomed-out overview of the whole file rendered as a strip of tiny
    # bars (one per line, or one per bucket of lines once the file is
    # taller than the strip has pixels for) plus a draggable box showing
    # what's currently visible in the real editor - the same idea as
    # VS Code/Sublime's minimap, done cheaply with a handful of rectangles
    # on a Canvas rather than actually rendering miniature text.
    def render_minimap_content(editor):
        canvas = editor.get("minimap")
        if canvas is None or not canvas.winfo_exists():
            return

        canvas.delete("all")

        text_area = editor["text"]
        content = text_area.get("1.0", "end-1c")
        lines = content.split("\n")
        total_lines = len(lines)

        canvas_w = canvas.winfo_width()
        canvas_h = canvas.winfo_height()
        if canvas_w <= 1 or canvas_h <= 1 or total_lines == 0:
            return

        # A row is always MINIMAP_ROW_HEIGHT tall, like a real minimap - it
        # never stretches to fill the strip. Once there are more source
        # lines than fit at that height, each row instead represents a
        # bucket of several lines, so a long file still gets compressed to
        # fit top-to-bottom; a short file just leaves the rest blank.
        row_height = MINIMAP_ROW_HEIGHT
        max_rows = max(1, int(canvas_h / row_height))
        row_count = min(total_lines, max_rows)
        lines_per_row = total_lines / row_count

        longest = max((len(line.rstrip()) for line in lines if line.strip()), default=0)
        longest = min(max(longest, 1), 200)
        scale = (canvas_w - 6) / longest

        keyword_color = THEME["syntax_keyword"]
        comment_color = THEME["syntax_comment"]
        default_color = THEME.get("muted_fg", THEME["editor_fg"])

        for row in range(row_count):
            start = int(row * lines_per_row)
            end = int((row + 1) * lines_per_row)
            if end <= start:
                end = start + 1
            bucket = lines[start:end]

            max_len = 0
            color = None
            for line in bucket:
                stripped = line.strip()
                if not stripped:
                    continue
                max_len = max(max_len, len(line.rstrip()))
                if color is None:
                    if stripped.startswith("#"):
                        color = comment_color
                    elif stripped.startswith(("def ", "class ", "async def ")):
                        color = keyword_color
                    else:
                        color = default_color

            if color is None or max_len == 0:
                continue

            width = min(canvas_w - 6, max(2, max_len * scale))
            y = row * row_height
            canvas.create_rectangle(
                3, y, 3 + width, y + row_height,
                fill=color, outline="", tags="bars"
            )

        render_minimap_viewport(editor)

    def render_minimap_viewport(editor):
        canvas = editor.get("minimap")
        if canvas is None or not canvas.winfo_exists():
            return

        canvas.delete("viewport")

        canvas_w = canvas.winfo_width()
        canvas_h = canvas.winfo_height()
        if canvas_w <= 1 or canvas_h <= 1:
            return

        first, last = editor["text"].yview()
        y1 = first * canvas_h
        y2 = last * canvas_h
        if y2 - y1 < 3:
            y2 = y1 + 3

        canvas.create_rectangle(
            1, y1, canvas_w - 1, y2,
            outline=THEME["accent"], width=2, tags="viewport"
        )

    def minimap_navigate(event, editor=None):
        """Click or drag on the minimap to jump the real editor there,
        centering the clicked point rather than snapping its top edge to
        the cursor - that's what makes dragging the box feel natural."""
        ed = editor
        canvas = ed["minimap"]
        canvas_h = canvas.winfo_height()
        if canvas_h <= 1:
            return "break"

        frac = min(max(event.y / canvas_h, 0.0), 1.0)
        first, last = ed["text"].yview()
        visible = max(last - first, 0.0)
        target = frac - visible / 2
        target = min(max(target, 0.0), max(0.0, 1.0 - visible))
        ed["text"].yview_moveto(target)
        render_minimap_viewport(ed)
        return "break"

    # ---------- Dirty / title tracking ----------
    def set_tab_title(editor):
        title = editor["title"]
        if editor["dirty"]:
            title = "*" + title
        tab_control.tab(editor["frame"], text=title)

    def refresh_window_title(editor):
        if editor is not get_current_editor():
            return
        path = editor["path"]
        title = f"CodeForge - {path}" if path else "CodeForge - Untitled"
        if editor["dirty"]:
            title = "*" + title
        root.title(title)

    def mark_dirty(editor):
        if not editor["dirty"]:
            editor["dirty"] = True
            set_tab_title(editor)
            refresh_window_title(editor)

    def mark_clean(editor):
        editor["dirty"] = False
        set_tab_title(editor)
        refresh_window_title(editor)

    # ---------- Auto-indentation ----------
    def bind_auto_indent(text_area, editor):
        def on_return(event, ta=text_area):
            ac = editor.get("autocomplete")
            if ac and ac.get("popup") is not None and ac["popup"].winfo_exists():
                ac["accept"]()
                return "break"

            mc = editor.get("multi_cursor")
            if mc and mc["cursors"]:
                mc["newline"]()
                return "break"

            current_line = ta.get("insert linestart", "insert lineend")
            text_before_cursor = ta.get("insert linestart", "insert")
            stripped = current_line.lstrip(" ")
            indent = current_line[:len(current_line) - len(stripped)]

            char_before = ta.get("insert-1c", "insert")
            char_after = ta.get("insert", "insert+1c")
            bracket_pairs = {"(": ")", "[": "]", "{": "}"}

            if char_before in bracket_pairs and char_after == bracket_pairs[char_before]:
                # Cursor sits inside an empty pair e.g. "(|)" - expand it
                # into three lines with the cursor indented on the middle one.
                inner_indent = indent + "    "
                ta.insert("insert", "\n" + inner_indent)
                cursor_pos = ta.index("insert")
                ta.insert("insert", "\n" + indent)
                ta.mark_set("insert", cursor_pos)
            else:
                if text_before_cursor.rstrip().endswith(":"):
                    indent += "    "
                ta.insert("insert", "\n" + indent)

            return "break"

        text_area.bind("<Return>", on_return)

    # ---------- Bracket / quote completion ----------
    def bind_bracket_completion(text_area, editor):
        def insert_pair(open_char, close_char):
            def handler(event, ta=text_area):
                mc = editor.get("multi_cursor")
                if mc and mc["cursors"]:
                    mc["insert_text"](open_char)
                    return "break"

                if ta.tag_ranges("sel"):
                    sel_start = ta.index("sel.first")
                    sel_end = ta.index("sel.last")
                    selected = ta.get(sel_start, sel_end)
                    ta.delete(sel_start, sel_end)
                    ta.insert(sel_start, open_char + selected + close_char)
                    ta.mark_set("insert", f"{sel_start}+{len(selected) + 2}c")
                    return "break"

                ta.insert("insert", open_char + close_char)
                ta.mark_set("insert", "insert-1c")
                return "break"
            return handler

        def skip_or_insert_close(close_char):
            def handler(event, ta=text_area):
                mc = editor.get("multi_cursor")
                if mc and mc["cursors"]:
                    mc["insert_text"](close_char)
                    return "break"

                next_char = ta.get("insert", "insert+1c")
                if next_char == close_char:
                    ta.mark_set("insert", "insert+1c")
                    return "break"
                return None
            return handler

        def handle_quote(quote_char):
            def handler(event, ta=text_area):
                mc = editor.get("multi_cursor")
                if mc and mc["cursors"]:
                    mc["insert_text"](quote_char)
                    return "break"

                if ta.tag_ranges("sel"):
                    sel_start = ta.index("sel.first")
                    sel_end = ta.index("sel.last")
                    selected = ta.get(sel_start, sel_end)
                    ta.delete(sel_start, sel_end)
                    ta.insert(sel_start, quote_char + selected + quote_char)
                    ta.mark_set("insert", f"{sel_start}+{len(selected) + 2}c")
                    return "break"

                next_char = ta.get("insert", "insert+1c")
                if next_char == quote_char:
                    ta.mark_set("insert", "insert+1c")
                    return "break"

                ta.insert("insert", quote_char + quote_char)
                ta.mark_set("insert", "insert-1c")
                return "break"
            return handler

        def handle_backspace(event, ta=text_area):
            mc = editor.get("multi_cursor")
            if mc and mc["cursors"]:
                mc["backspace"]()
                return "break"

            if ta.tag_ranges("sel"):
                return None

            prev_char = ta.get("insert-1c", "insert")
            next_char = ta.get("insert", "insert+1c")
            closers = {"(": ")", "[": "]", "{": "}", "'": "'", '"': '"'}

            if prev_char in closers and next_char == closers[prev_char]:
                ta.delete("insert-1c", "insert+1c")
                return "break"
            return None

        text_area.bind("<KeyPress-parenleft>", insert_pair("(", ")"))
        text_area.bind("<KeyPress-bracketleft>", insert_pair("[", "]"))
        text_area.bind("<KeyPress-braceleft>", insert_pair("{", "}"))

        text_area.bind("<KeyPress-parenright>", skip_or_insert_close(")"))
        text_area.bind("<KeyPress-bracketright>", skip_or_insert_close("]"))
        text_area.bind("<KeyPress-braceright>", skip_or_insert_close("}"))

        text_area.bind("<KeyPress-quotedbl>", handle_quote('"'))
        text_area.bind("<KeyPress-apostrophe>", handle_quote("'"))

        text_area.bind("<BackSpace>", handle_backspace)

    # ---------- Multi-cursor ----------
    def bind_multicursor(text_area, editor):
        # A "cursor" is a dict: {"point": mark_name, "sel_start": mark_name|None}.
        # The primary caret is represented by the literal mark "insert" so it
        # participates in every multi-cursor op without needing a shadow mark.
        mc_state = {"cursors": [], "term": None, "search_from": None,
                    "carets": [], "seq": 0}
        editor["multi_cursor"] = mc_state

        def new_mark(index, gravity="right"):
            mc_state["seq"] += 1
            name = f"mc_{id(editor)}_{mc_state['seq']}"
            text_area.mark_set(name, index)
            if gravity != "right":
                text_area.mark_gravity(name, gravity)
            return name

        def clear_carets():
            for c in mc_state["carets"]:
                if c.winfo_exists():
                    c.destroy()
            mc_state["carets"] = []

        def draw_carets():
            clear_carets()
            for c in mc_state["cursors"]:
                if c["point"] == "insert":
                    continue  # the OS already renders the primary caret
                try:
                    idx = text_area.index(c["point"])
                except tk.TclError:
                    continue
                bbox = text_area.bbox(idx)
                if not bbox:
                    continue
                x, y, _, h = bbox
                caret = tk.Canvas(
                    editor["editor_frame"],
                    width=2,
                    height=max(h, 4),
                    bg=THEME["accent"],
                    highlightthickness=0,
                    bd=0
                )
                caret.place(in_=text_area, x=x, y=y)
                mc_state["carets"].append(caret)

        def clear_all(event=None):
            for c in mc_state["cursors"]:
                for mark in (c["point"], c.get("sel_start")):
                    if mark and mark != "insert":
                        try:
                            text_area.mark_unset(mark)
                        except tk.TclError:
                            pass
            mc_state["cursors"] = []
            mc_state["term"] = None
            mc_state["search_from"] = None
            text_area.tag_remove("sel", "1.0", "end")
            clear_carets()

        def rebuild_sel_tag():
            text_area.tag_remove("sel", "1.0", "end")
            for c in mc_state["cursors"]:
                sel_start = c.get("sel_start")
                if not sel_start:
                    continue
                try:
                    s = text_area.index(sel_start)
                    p = text_area.index(c["point"])
                except tk.TclError:
                    continue
                if text_area.compare(s, "<", p):
                    text_area.tag_add("sel", s, p)
            draw_carets()

        def sorted_desc():
            def sort_key(c):
                line, col = text_area.index(c["point"]).split(".")
                return (int(line), int(col))
            return sorted(mc_state["cursors"], key=sort_key, reverse=True)

        def apply_edit(op):
            # Applied right-to-left (bottom of the document first) so an
            # edit at one cursor never invalidates the *position we're
            # about to read* for another - Tk marks auto-adjust for edits
            # elsewhere, but resolving each index right before its own op
            # keeps this correct regardless of ordering subtleties.
            for c in sorted_desc():
                idx = text_area.index(c["point"])
                sel_start = c.get("sel_start")
                sel_idx = None
                if sel_start:
                    try:
                        sel_idx = text_area.index(sel_start)
                    except tk.TclError:
                        sel_idx = None
                op(idx, sel_idx)
                c["sel_start"] = None
            rebuild_sel_tag()
            mark_dirty(editor)

        def mc_insert_text(text_to_insert):
            def op(idx, sel_idx):
                if sel_idx and text_area.compare(sel_idx, "<", idx):
                    text_area.delete(sel_idx, idx)
                    text_area.insert(sel_idx, text_to_insert)
                else:
                    text_area.insert(idx, text_to_insert)
            apply_edit(op)

        def mc_backspace():
            def op(idx, sel_idx):
                if sel_idx and text_area.compare(sel_idx, "<", idx):
                    text_area.delete(sel_idx, idx)
                elif text_area.compare(idx, ">", "1.0"):
                    text_area.delete(f"{idx}-1c", idx)
            apply_edit(op)

        def mc_delete_forward():
            def op(idx, sel_idx):
                if sel_idx and text_area.compare(sel_idx, "<", idx):
                    text_area.delete(sel_idx, idx)
                else:
                    text_area.delete(idx, f"{idx}+1c")
            apply_edit(op)

        def mc_newline():
            def op(idx, sel_idx):
                if sel_idx and text_area.compare(sel_idx, "<", idx):
                    text_area.delete(sel_idx, idx)
                    idx = sel_idx
                line_text = text_area.get(f"{idx} linestart", f"{idx} lineend")
                stripped = line_text.lstrip(" ")
                indent = line_text[:len(line_text) - len(stripped)]
                text_area.insert(idx, "\n" + indent)
            apply_edit(op)

        mc_state["clear"] = clear_all
        mc_state["insert_text"] = mc_insert_text
        mc_state["backspace"] = mc_backspace
        mc_state["delete_forward"] = mc_delete_forward
        mc_state["newline"] = mc_newline
        mc_state["draw_carets"] = draw_carets

        # ---- Ctrl+Click: add or remove a point cursor ----
        def on_ctrl_click(event):
            click_index = text_area.index(f"@{event.x},{event.y}")

            if not mc_state["cursors"]:
                mc_state["cursors"].append({"point": "insert", "sel_start": None})

            for c in list(mc_state["cursors"]):
                if c["point"] != "insert" and text_area.compare(c["point"], "==", click_index):
                    text_area.mark_unset(c["point"])
                    mc_state["cursors"].remove(c)
                    if len(mc_state["cursors"]) <= 1:
                        clear_all()
                    else:
                        draw_carets()
                    return "break"

            mark = new_mark(click_index)
            mc_state["cursors"].append({"point": mark, "sel_start": None})
            draw_carets()
            return "break"

        text_area.bind("<Control-Button-1>", on_ctrl_click)

        # ---- Ctrl+D: select word under cursor, then each next occurrence ----
        def add_occurrence(start, end):
            text_area.tag_add("sel", start, end)
            sel_mark = new_mark(start, gravity="left")
            point_mark = new_mark(end)
            mc_state["cursors"].append({"point": point_mark, "sel_start": sel_mark})
            mc_state["search_from"] = end

        def select_next(event=None):
            if not mc_state["cursors"]:
                sel_ranges = text_area.tag_ranges("sel")
                if sel_ranges:
                    term = text_area.get(sel_ranges[0], sel_ranges[1])
                    start, end = str(sel_ranges[0]), str(sel_ranges[1])
                else:
                    start = text_area.index("insert wordstart")
                    end = text_area.index("insert wordend")
                    term = text_area.get(start, end)
                if not term.strip():
                    return "break"
                mc_state["term"] = term
                add_occurrence(start, end)
                draw_carets()
                return "break"

            term = mc_state["term"]
            pos = text_area.search(term, mc_state["search_from"], stopindex="end", nocase=False)
            if not pos:
                pos = text_area.search(term, "1.0", stopindex=mc_state["search_from"], nocase=False)
            if not pos:
                return "break"

            end = f"{pos}+{len(term)}c"
            for c in mc_state["cursors"]:
                sel_start = c.get("sel_start")
                if sel_start and text_area.compare(text_area.index(sel_start), "==", pos):
                    # Already tracking this occurrence - keep looking.
                    mc_state["search_from"] = end
                    return select_next()

            add_occurrence(pos, end)
            draw_carets()
            return "break"

        text_area.bind("<Control-d>", select_next)
        text_area.bind("<Control-D>", select_next)

        # ---- Escape collapses back to a single cursor ----
        def on_escape(event):
            if not mc_state["cursors"]:
                return None
            clear_all()
            return "break"

        text_area.bind("<Escape>", on_escape, add="+")

        # ---- Delete key, forward-delete at every cursor ----
        def on_delete_key(event):
            if not mc_state["cursors"]:
                return None
            mc_delete_forward()
            return "break"

        text_area.bind("<Delete>", on_delete_key)

        # ---- Ordinary printable characters (letters, digits, punctuation
        # without a dedicated bracket/quote binding above) ----
        def on_key(event):
            if not mc_state["cursors"]:
                return None
            if not event.char or ord(event.char) < 32:
                return None
            mc_insert_text(event.char)
            return "break"

        text_area.bind("<Key>", on_key)

        return mc_state

    # ---------- Autocomplete ----------
    NAV_IGNORED_KEYS = {
        "Up", "Down", "Left", "Right", "Return", "KP_Enter", "Tab",
        "Escape", "Shift_L", "Shift_R", "Control_L", "Control_R",
        "Alt_L", "Alt_R", "Caps_Lock", "Home", "End", "Prior", "Next"
    }

    def bind_autocomplete(text_area, editor):
        ac = {
            "popup": None, "listbox": None, "start": None, "accept": None, "close": None,
            "import_map": {}, "import_source": None
        }
        editor["autocomplete"] = ac

        def close_popup():
            popup = ac["popup"]
            if popup is not None and popup.winfo_exists():
                popup.destroy()
            ac["popup"] = None
            ac["listbox"] = None
            ac["start"] = None
            ac["accept"] = None

        def get_import_map():
            content = text_area.get("1.0", "end")
            import_source = _extract_import_lines(content)
            # Re-parsing/re-importing is only worth doing when the import
            # lines themselves changed - typing inside a function body
            # keeps hitting this on every keystroke otherwise.
            if import_source != ac["import_source"]:
                ac["import_map"] = _build_import_map(import_source)
                ac["import_source"] = import_source
            return ac["import_map"]

        def current_completion_context():
            before_cursor = text_area.get("insert linestart", "insert")
            line = text_area.index("insert").split(".")[0]

            dot_match = _DOT_CHAIN_RE.search(before_cursor)
            if dot_match:
                chain = dot_match.group(1).split(".")
                attr_prefix = dot_match.group(2)
                start_index = f"{line}.{dot_match.start(2)}"
                return "attr", chain, attr_prefix, start_index

            word_match = _WORD_TAIL_RE.search(before_cursor)
            if word_match:
                start_index = f"{line}.{word_match.start()}"
                return "word", None, word_match.group(0), start_index

            return None, None, None, None

        def gather_candidates(kind, chain, prefix):
            if kind == "attr":
                obj = _resolve_chain(chain, get_import_map())
                if obj is None:
                    # Not a known standard-library import (could be a local
                    # variable, a third-party module, or just not resolved
                    # yet) - stay silent rather than guess.
                    return []
                return _attribute_candidates(obj, prefix)

            text = text_area.get("1.0", "end")
            words = set(re.findall(r"[A-Za-z_]\w{1,}", text))
            pool = words | set(keyword.kwlist) | _BUILTIN_NAMES
            prefix_lower = prefix.lower()
            matches = sorted(
                w for w in pool
                if w != prefix and w.lower().startswith(prefix_lower)
            )
            return matches[:8]

        def accept():
            listbox = ac["listbox"]
            if not listbox or not listbox.curselection():
                close_popup()
                return
            chosen = listbox.get(listbox.curselection()[0])
            start = ac["start"]
            text_area.delete(start, "insert")
            text_area.insert(start, chosen)
            close_popup()

        def move_selection(delta):
            listbox = ac["listbox"]
            if not listbox:
                return
            size = listbox.size()
            if size == 0:
                return
            current = listbox.curselection()
            idx = ((current[0] + delta) % size) if current else 0
            listbox.select_clear(0, "end")
            listbox.select_set(idx)
            listbox.see(idx)

        def open_popup(start_index, candidates):
            close_popup()
            bbox = text_area.bbox(start_index)
            if not bbox:
                return
            x, y, _, h = bbox
            abs_x = text_area.winfo_rootx() + x
            abs_y = text_area.winfo_rooty() + y + h

            popup = tk.Toplevel(text_area)
            popup.wm_overrideredirect(True)
            popup.wm_geometry(f"+{abs_x}+{abs_y}")
            try:
                popup.attributes("-topmost", True)
            except tk.TclError:
                pass

            listbox = tk.Listbox(
                popup,
                height=min(len(candidates), 8),
                activestyle="none",
                bg=THEME["popup_bg"],
                fg=THEME["popup_fg"],
                selectbackground=THEME["popup_select_bg"],
                selectforeground=THEME["popup_select_fg"],
                highlightthickness=1,
                highlightbackground=THEME["popup_border"],
                font=("Consolas", 11),
                bd=0
            )
            for candidate in candidates:
                listbox.insert("end", candidate)
            listbox.select_set(0)
            listbox.pack()
            listbox.bind("<Double-Button-1>", lambda e: accept())

            ac["popup"] = popup
            ac["listbox"] = listbox
            ac["start"] = start_index
            ac["accept"] = accept

        def on_key_release(event):
            if event.keysym in NAV_IGNORED_KEYS:
                return

            kind, chain, prefix, start_index = current_completion_context()
            if kind is None:
                close_popup()
                return

            # Dot-completion is useful the instant you type the dot (an
            # empty prefix should list everything available), but plain
            # identifier completion waits for a couple characters so the
            # popup doesn't jump in on every keystroke of a short word.
            if kind == "word" and len(prefix) < 2:
                close_popup()
                return

            candidates = gather_candidates(kind, chain, prefix)
            if not candidates:
                close_popup()
                return

            open_popup(start_index, candidates)

        def on_down(event):
            if ac["popup"] is None:
                return None
            move_selection(1)
            return "break"

        def on_up(event):
            if ac["popup"] is None:
                return None
            move_selection(-1)
            return "break"

        def on_tab(event):
            if ac["popup"] is None:
                return None
            accept()
            return "break"

        def on_escape(event):
            if ac["popup"] is None:
                return None
            close_popup()
            return "break"

        text_area.bind("<KeyRelease>", on_key_release, add="+")
        text_area.bind("<Down>", on_down, add="+")
        text_area.bind("<Up>", on_up, add="+")
        text_area.bind("<Tab>", on_tab)
        text_area.bind("<Escape>", on_escape, add="+")
        ac["close"] = close_popup
        return close_popup

    # ---------- Tab creation / management ----------
    def make_tab_title(path):
        if path:
            return os.path.basename(path)
        untitled_count[0] += 1
        return "Untitled" if untitled_count[0] == 1 else f"Untitled-{untitled_count[0]}"

    # ---------- Font size (zoom) ----------
    def apply_font_size_to_editor(editor):
        font = current_editor_font()
        editor["text"].config(font=font)
        editor["line_numbers"].config(font=font)
        update_indent_guides(editor)

    def set_font_size(new_size):
        new_size = max(MIN_FONT_SIZE, min(MAX_FONT_SIZE, new_size))
        if new_size == font_state["size"]:
            return
        font_state["size"] = new_size
        for editor in tab_editors.values():
            apply_font_size_to_editor(editor)
        save_font_size_preference(new_size)

    def zoom_in():
        set_font_size(font_state["size"] + 1)

    def zoom_out():
        set_font_size(font_state["size"] - 1)

    def zoom_reset():
        set_font_size(DEFAULT_FONT_SIZE)

    def on_editor_ctrl_wheel(event):
        # Positive delta = wheel up = zoom in, matching Ctrl+scroll in every
        # other editor/browser.
        if event.delta > 0:
            zoom_in()
        else:
            zoom_out()
        return "break"

    def create_tab(path=None, content=""):
        tab_frame = tk.Frame(tab_control, bg=THEME["editor_bg"], highlightthickness=0, bd=0)

        editor_frame = tk.Frame(tab_frame, bg=THEME["editor_bg"], highlightthickness=0, bd=0)
        editor_frame.pack(fill="both", expand=True)

        line_numbers = tk.Text(
            editor_frame,
            width=4,
            padx=4,
            takefocus=0,
            border=0,
            background=THEME["line_number_bg"],
            foreground=THEME["line_number_fg"],
            state="disabled",
            wrap="none",
            font=current_editor_font()
        )
        line_numbers.pack(side="left", fill="y")

        text_area = tk.Text(
            editor_frame,
            wrap="none",
            undo=True,
            font=current_editor_font(),
            background=THEME["editor_bg"],
            foreground=THEME["editor_fg"],
            insertbackground=THEME["editor_insert"],
            selectbackground=THEME["editor_select_bg"],
            selectforeground=THEME["editor_select_fg"],
            highlightthickness=0,
            border=0
        )
        text_area.pack(side="left", fill="both", expand=True)

        text_scrollbar = ttk.Scrollbar(
            editor_frame,
            orient="vertical",
            command=text_area.yview,
            style="Vertical.TScrollbar"
        )
        text_scrollbar.pack(side="left", fill="y")

        minimap = tk.Canvas(
            editor_frame,
            width=MINIMAP_WIDTH,
            highlightthickness=0,
            bd=0,
            bg=THEME["line_number_bg"]
        )
        if minimap_state["visible"]:
            minimap.pack(side="left", fill="y")

        def on_text_scroll(first, last, ln=line_numbers, sb=text_scrollbar):
            sb.set(first, last)
            ln.yview_moveto(float(first))
            # Scrolling shifts which lines/pixels are on screen, so the
            # guide overlay (positioned in real pixel coordinates) needs
            # to be redrawn to match.
            update_indent_guides(editor)
            mc = editor.get("multi_cursor")
            if mc and mc["cursors"]:
                mc["draw_carets"]()
            render_minimap_viewport(editor)

        text_area.config(yscrollcommand=on_text_scroll)

        def on_linenum_scroll(event, ta=text_area):
            ta.yview_scroll(int(-event.delta / 120), "units")
            return "break"

        line_numbers.bind("<MouseWheel>", on_linenum_scroll)
        line_numbers.bind("<Control-MouseWheel>", on_editor_ctrl_wheel)

        tab_id = str(tab_frame)
        title = make_tab_title(path)

        editor = {
            "frame": tab_frame,
            "editor_frame": editor_frame,
            "text": text_area,
            "line_numbers": line_numbers,
            "minimap": minimap,
            "path": path,
            "title": title,
            "dirty": False,
            "guide_canvases": [],
            "guide_pool_used": 0,
            "resize_job": None,
            "highlight_job": None,
            "minimap_resize_job": None,
            "last_line_count": None
        }
        tab_editors[tab_id] = editor

        def on_minimap_resize(event, ed=editor):
            # Redraw on a debounce, same reasoning as on_text_resize below -
            # a window/sash drag fires this continuously and a full rescan
            # of every line on each tick would visibly lag.
            pending = ed.get("minimap_resize_job")
            if pending is not None:
                ed["minimap"].after_cancel(pending)

            def do_redraw(ed=ed):
                ed["minimap_resize_job"] = None
                render_minimap_content(ed)

            ed["minimap_resize_job"] = ed["minimap"].after(120, do_redraw)

        def on_minimap_wheel(event, ta=text_area, ed=editor):
            ta.yview_scroll(int(-event.delta / 120), "units")
            render_minimap_viewport(ed)
            return "break"

        minimap.bind("<Configure>", on_minimap_resize)
        minimap.bind("<Button-1>", lambda e, ed=editor: minimap_navigate(e, ed))
        minimap.bind("<B1-Motion>", lambda e, ed=editor: minimap_navigate(e, ed))
        minimap.bind("<MouseWheel>", on_minimap_wheel)

        def on_text_resize(event, ed=editor):
            # <Configure> fires on every pixel while a panel/sash is being
            # dragged. Redrawing the guides (a full-document scan that
            # rebuilds a Canvas per segment) on every one of those ticks is
            # what causes the visible lag/twitching, so debounce it: cancel
            # any pending redraw and schedule a fresh one a moment out,
            # meaning only the *last* tick in a burst actually does the work.
            pending = ed.get("resize_job")
            if pending is not None:
                ed["text"].after_cancel(pending)

            def do_redraw(ed=ed):
                ed["resize_job"] = None
                update_indent_guides(ed)
                mc = ed.get("multi_cursor")
                if mc and mc["cursors"]:
                    mc["draw_carets"]()
                render_minimap_viewport(ed)

            ed["resize_job"] = ed["text"].after(120, do_redraw)

        text_area.bind("<Configure>", on_text_resize)

        setup_highlight_tags(text_area)

        if content:
            text_area.insert("1.0", content)

        # Inserting initial content trips the <<Modified>> flag - clear it so
        # a freshly opened/created tab doesn't show as dirty.
        text_area.edit_modified(False)

        def on_key_release(event, ed=editor):
            # Cheap and purely cursor-local - keep these instant so typing
            # never feels like it's waiting on anything.
            highlight_current_line(ed["text"])
            highlight_brackets(ed["text"])
            update_status_bar(ed)

            # The full-document passes (gutter rebuild, syntax re-tagging,
            # indent guides) are debounced: a fast typist re-triggers
            # KeyRelease many times a second, and redoing all of that on
            # every single one is what caused visible stutter, especially
            # in larger files. Collapsing a burst into one recompute
            # shortly after it stops keeps typing smooth without the
            # highlighting ever feeling stale.
            pending = ed.get("highlight_job")
            if pending is not None:
                ed["text"].after_cancel(pending)

            def do_heavy_update(ed=ed):
                ed["highlight_job"] = None
                if not ed["text"].winfo_exists():
                    return
                update_line_numbers(ed)
                highlight_syntax(ed)
                update_indent_guides(ed)
                render_minimap_content(ed)

            ed["highlight_job"] = ed["text"].after(80, do_heavy_update)

        def on_click(event, ed=editor):
            ac = ed.get("autocomplete")
            if ac and ac.get("close"):
                ac["close"]()

            mc = ed.get("multi_cursor")
            if mc and mc["cursors"] and not (event.state & 0x4):
                mc["clear"]()

            # Let the click land the cursor first, then re-highlight its line
            def refresh():
                highlight_current_line(ed["text"])
                highlight_brackets(ed["text"])
                update_status_bar(ed)
            ed["text"].after_idle(refresh)

        def on_modified(event, ed=editor):
            if ed["text"].edit_modified():
                mark_dirty(ed)
                ed["text"].edit_modified(False)

        text_area.bind("<KeyRelease>", on_key_release)
        text_area.bind("<ButtonRelease-1>", on_click)
        text_area.bind("<<Modified>>", on_modified)
        text_area.bind("<Control-MouseWheel>", on_editor_ctrl_wheel)

        bind_auto_indent(text_area, editor)
        bind_bracket_completion(text_area, editor)
        bind_autocomplete(text_area, editor)
        bind_multicursor(text_area, editor)

        tab_control.add(tab_frame, text=title)
        tab_control.select(tab_frame)

        update_line_numbers(editor)
        highlight_syntax(editor)
        highlight_current_line(text_area)
        highlight_brackets(text_area)
        update_indent_guides(editor)
        text_area.after_idle(lambda ed=editor: render_minimap_content(ed))

        text_area.focus_set()

        return editor

    def save_editor(editor):
        if editor["path"]:
            with open(editor["path"], "w", encoding="utf-8") as f:
                f.write(editor["text"].get("1.0", "end-1c"))
            mark_clean(editor)
            refresh_git_state()
        else:
            save_editor_as(editor)

    def save_editor_as(editor):
        path = filedialog.asksaveasfilename(
            defaultextension=".py",
            filetypes=[("Python files", "*.py"), ("All files", "*.*")]
        )
        if not path:
            return
        with open(path, "w", encoding="utf-8") as f:
            f.write(editor["text"].get("1.0", "end-1c"))
        editor["path"] = path
        editor["title"] = os.path.basename(path)
        mark_clean(editor)
        update_status_bar(editor)
        refresh_tree()
        refresh_git_state()
        _remember_recent_file(path)

    def prompt_save_if_dirty(editor, tab_id):
        """Returns True if it's OK to proceed (close/exit), False to abort."""
        if not editor["dirty"]:
            return True

        tab_control.select(tab_id)
        response = messagebox.askyesnocancel(
            "Unsaved changes",
            f"Save changes to {editor['title']} before closing?"
        )
        if response is None:
            return False
        if response:
            save_editor(editor)
            if editor["dirty"]:
                # Save As dialog was cancelled - treat like Cancel
                return False
        return True

    def close_tab(tab_id=None):
        if tab_id is None:
            tab_id = get_current_tab()

        if not tab_id or tab_id not in tab_editors:
            return

        editor = tab_editors[tab_id]

        if not prompt_save_if_dirty(editor, tab_id):
            return

        pending = editor.get("resize_job")
        if pending is not None:
            try:
                editor["text"].after_cancel(pending)
            except tk.TclError:
                pass

        pending = editor.get("highlight_job")
        if pending is not None:
            try:
                editor["text"].after_cancel(pending)
            except tk.TclError:
                pass

        pending = editor.get("minimap_resize_job")
        if pending is not None:
            try:
                editor["minimap"].after_cancel(pending)
            except tk.TclError:
                pass

        ac = editor.get("autocomplete")
        if ac and ac.get("close"):
            ac["close"]()

        mc = editor.get("multi_cursor")
        if mc and mc.get("clear"):
            mc["clear"]()

        del tab_editors[tab_id]
        tab_control.forget(editor["frame"])
        editor["frame"].destroy()

        # Never let the editor end up with zero tabs open
        if not tab_control.tabs():
            create_tab()

    def close_other_tabs(tab_id):
        for other_id in list(tab_editors.keys()):
            if other_id != tab_id:
                close_tab(other_id)

    def on_tab_changed(event=None):
        for ed in tab_editors.values():
            ac = ed.get("autocomplete")
            if ac and ac.get("close"):
                ac["close"]()
            mc = ed.get("multi_cursor")
            if mc and mc.get("clear"):
                mc["clear"]()

        editor = get_current_editor()
        if not editor:
            update_status_bar(None)
            highlight_active_file()
            return
        refresh_window_title(editor)
        update_line_numbers(editor)
        highlight_syntax(editor)
        highlight_current_line(editor["text"])
        highlight_brackets(editor["text"])
        update_indent_guides(editor)
        render_minimap_content(editor)
        update_status_bar(editor)
        highlight_active_file()
        # Matches found in the previous tab don't apply to this one.
        find_state["matches"] = []
        find_state["current"] = -1

    tab_control.bind("<<NotebookTabChanged>>", on_tab_changed)

    def tab_id_at_event(event):
        try:
            index = tab_control.index(f"@{event.x},{event.y}")
        except tk.TclError:
            return None
        tabs = tab_control.tabs()
        if index is None or index >= len(tabs):
            return None
        return tabs[index]

    def on_tab_middle_click(event):
        tab_id = tab_id_at_event(event)
        if tab_id:
            close_tab(tab_id)

    tab_control.bind("<Button-2>", on_tab_middle_click)

    # ---------- Click-to-close (the little "x" on each tab) ----------
    # Standard ttk recipe: press arms the close element only if the press
    # actually landed on it, release fires the close only if the button
    # comes back up over that same element on the same tab - so a press
    # that drags off the "x" before releasing (or lands elsewhere) doesn't
    # close anything, same as a normal button.
    tab_close_state = {"pressed_tab": None}

    def on_tab_close_press(event):
        elem = tab_control.identify(event.x, event.y)
        if "close" not in elem:
            tab_close_state["pressed_tab"] = None
            return
        tab_close_state["pressed_tab"] = tab_id_at_event(event)
        tab_control.state(["pressed"])

    def on_tab_close_release(event):
        if tab_close_state["pressed_tab"] is None:
            return
        elem = tab_control.identify(event.x, event.y)
        tab_control.state(["!pressed"])
        if "close" in elem and tab_id_at_event(event) == tab_close_state["pressed_tab"]:
            close_tab(tab_close_state["pressed_tab"])
        tab_close_state["pressed_tab"] = None

    tab_control.bind("<ButtonPress-1>", on_tab_close_press)
    tab_control.bind("<ButtonRelease-1>", on_tab_close_release)

    tab_context_menu = tk.Menu(tab_control, tearoff=0, **menu_opts)

    def show_tab_context_menu(event):
        tab_id = tab_id_at_event(event)
        if not tab_id:
            return

        editor = tab_editors.get(tab_id)
        tab_context_menu.delete(0, tk.END)
        tab_context_menu.add_command(label="Close Tab", command=lambda: close_tab(tab_id))
        tab_context_menu.add_command(label="Close Other Tabs", command=lambda: close_other_tabs(tab_id))
        if editor and editor["path"]:
            tab_context_menu.add_separator()
            tab_context_menu.add_command(
                label="Copy Path", command=lambda: copy_path(editor["path"])
            )
            tab_context_menu.add_command(
                label="Copy Relative Path", command=lambda: copy_relative_path(editor["path"])
            )
        tab_context_menu.tk_popup(event.x_root, event.y_root)

    tab_control.bind("<Button-3>", show_tab_context_menu)

    # ---------- File operations ----------
    def find_tab_for_path(path):
        for tab_id, editor in tab_editors.items():
            if editor["path"] == path:
                return tab_id
        return None

    def new_file():
        create_tab()

    def new_window():
        """Open a second, fully independent CodeForge window rather than a
        second tab in this one. Everything about a running window - open
        tabs, the project tree, undo history, the terminal/shell process -
        lives in globals and closures scoped to a single run() call, so
        there's no clean way to host two live "sessions" in one process.
        Spawning a second OS process gets a real second window with its
        own independent state instead.

        The new process is told (via an env var, so we don't have to
        assume anything about how the entry-point script parses argv) to
        skip restoring the last-saved session and start with a single
        blank tab - otherwise it would just reopen whatever files/folder
        this window already has open.
        """
        env = os.environ.copy()
        env["CODEFORGE_NEW_WINDOW"] = "1"
        try:
            subprocess.Popen([sys.executable] + sys.argv, env=env)
        except OSError:
            messagebox.showerror("New Window", "Couldn't open a new window.")

    def _remember_recent_file(path):
        """Push path to the front of the recent-files list (de-duping any
        earlier entry for it), cap it, persist it, and refresh the Open
        Recent submenu so it reflects the change immediately."""
        if not path:
            return
        paths = recent_files_state["paths"]
        paths[:] = [p for p in paths if p != path]
        paths.insert(0, path)
        del paths[MAX_RECENT_FILES:]
        save_recent_files(paths)
        _rebuild_recent_files_menu()

    def _open_path_in_tab(path):
        existing_tab = find_tab_for_path(path)
        if existing_tab:
            tab_control.select(existing_tab)
            _remember_recent_file(path)
            return

        try:
            with open(path, "r", encoding="utf-8") as f:
                content = f.read()
        except UnicodeDecodeError:
            messagebox.showerror(
                "Open File",
                f"Couldn't open '{os.path.basename(path)}': it doesn't look like a "
                "UTF-8 text file (it may be binary, or use a different encoding)."
            )
            return
        except OSError as e:
            messagebox.showerror("Open File", f"Couldn't open '{os.path.basename(path)}': {e}")
            return

        current = get_current_editor()
        # Reuse a blank, untouched "Untitled" tab instead of piling up empty ones
        if current and current["path"] is None and not current["dirty"] \
                and current["text"].get("1.0", "end-1c") == "":
            current["path"] = path
            current["title"] = os.path.basename(path)
            current["text"].insert("1.0", content)
            current["text"].edit_modified(False)
            mark_clean(current)
            set_tab_title(current)
            update_line_numbers(current)
            highlight_syntax(current)
            highlight_current_line(current["text"])
            highlight_brackets(current["text"])
            update_indent_guides(current)
            render_minimap_content(current)
            highlight_active_file()
        else:
            create_tab(path=path, content=content)
        _remember_recent_file(path)

    def open_file():
        path = filedialog.askopenfilename(
            filetypes=[("Python files", "*.py"), ("All files", "*.*")]
        )
        if path:
            _open_path_in_tab(path)

    def open_from_tree(event):
        selected = project_tree.selection()

        if not selected:
            return

        item = selected[0]
        values = project_tree.item(item, "values")

        if not values:
            return

        path = values[0]

        if os.path.isdir(path):
            return

        _open_path_in_tab(path)

    project_tree.bind("<Double-1>", open_from_tree)

    def add_directory(parent, path):
        # Only the immediate children are actually listed/inserted here.
        # Subfolders get a single dummy child instead of a full recursive
        # walk - that's what makes the expand arrow show up without the
        # cost of statting every file in the whole project up front.
        # _on_tree_expand replaces the dummy with the real contents the
        # first time that folder is actually opened.
        try:
            items = sorted(os.listdir(path))
        except (PermissionError, OSError):
            return

        for item in items:
            full_path = os.path.join(path, item)

            node = project_tree.insert(
                parent,
                "end",
                text=item,
                open=False,
                values=[full_path]
            )

            if os.path.isdir(full_path):
                project_tree.insert(node, "end", text="", values=[])

    def _on_tree_expand(event):
        node = project_tree.focus()
        children = project_tree.get_children(node)
        # A lazily-added directory has exactly one dummy child, and only
        # the dummy has no "values" (real nodes always carry their path
        # there) - that's how we tell "never opened yet" apart from
        # "opened, and it just happens to be empty".
        if len(children) == 1 and not project_tree.item(children[0], "values"):
            project_tree.delete(children[0])
            path = project_tree.item(node, "values")[0]
            add_directory(node, path)
            apply_git_status_tags()

    project_tree.bind("<<TreeviewOpen>>", _on_tree_expand)

    def populate_tree(folder):
        project_tree.delete(*project_tree.get_children())

        root_node = project_tree.insert(
            "",
            "end",
            text=os.path.basename(folder),
            open=True,
            values=[folder]
        )

        add_directory(root_node, folder)

    def open_folder():
        nonlocal project_path

        folder = filedialog.askdirectory()

        if not folder:
            return

        project_path = folder
        populate_tree(folder)
        highlight_active_file()
        refresh_git_state()

    # ---------- Drag and drop ----------
    # Only active when tkinterdnd2 is installed (see the optional import at
    # the top of this file) - root is a plain tk.Tk() otherwise, which has
    # no drop_target_register/dnd_bind at all, so this whole block is
    # skipped rather than erroring.
    def _on_files_dropped(event):
        nonlocal project_path
        try:
            paths = root.tk.splitlist(event.data)
        except tk.TclError:
            return
        for dropped_path in paths:
            if os.path.isdir(dropped_path):
                project_path = dropped_path
                populate_tree(dropped_path)
                highlight_active_file()
                refresh_git_state()
            elif os.path.isfile(dropped_path):
                try:
                    _open_path_in_tab(dropped_path)
                except (OSError, UnicodeDecodeError) as e:
                    messagebox.showerror("Open", f"Couldn't open {dropped_path}: {e}")

    if tkinterdnd2:
        tab_control.drop_target_register(tkinterdnd2.DND_FILES)
        tab_control.dnd_bind("<<Drop>>", _on_files_dropped)
        project_tree.drop_target_register(tkinterdnd2.DND_FILES)
        project_tree.dnd_bind("<<Drop>>", _on_files_dropped)

    # ---------- Explorer: refresh helpers ----------
    # Rebuilding the whole tree from disk (rather than surgically
    # inserting/removing nodes) keeps New/Rename/Delete simple and always
    # correct - the only cost is that ttk.Treeview forgets which folders
    # were expanded, so we snapshot and restore that ourselves.
    def _walk_tree_nodes(parent=""):
        for node in project_tree.get_children(parent):
            yield node
            yield from _walk_tree_nodes(node)

    def _node_tags(node):
        """Tk's Treeview.item(node, "tags") returns a tuple when there are
        0 or 2+ tags, but a bare string when there's exactly 1 - normalize
        to always-a-tuple so tag logic elsewhere doesn't have to special-
        case that (that mismatch is what caused the "can only concatenate
        str (not tuple) to str" crash in apply_git_status_tags)."""
        tags = project_tree.item(node, "tags")
        if isinstance(tags, str):
            return (tags,) if tags else ()
        return tuple(tags)

    def _get_expanded_paths():
        expanded = set()
        for node in _walk_tree_nodes():
            if project_tree.item(node, "open"):
                values = project_tree.item(node, "values")
                if values:
                    expanded.add(values[0])
        return expanded

    def _restore_expanded_paths(expanded):
        # Programmatically setting open=True (unlike a user click on the
        # disclosure triangle) does NOT fire <<TreeviewOpen>>, so a folder
        # that was expanded before a refresh would otherwise come back
        # showing just its lazy-load placeholder. Load its real children
        # directly here instead of relying on the event.
        for node in _walk_tree_nodes():
            values = project_tree.item(node, "values")
            if values and values[0] in expanded:
                project_tree.item(node, open=True)
                children = project_tree.get_children(node)
                if len(children) == 1 and not project_tree.item(children[0], "values"):
                    project_tree.delete(children[0])
                    add_directory(node, values[0])

    def _select_tree_path(path):
        for node in _walk_tree_nodes():
            values = project_tree.item(node, "values")
            if values and values[0] == path:
                project_tree.selection_set(node)
                project_tree.focus(node)
                project_tree.see(node)
                return

    def highlight_active_file():
        """Tag whichever explorer row backs the file open in the current
        tab, so it's visually obvious which file you're editing - and
        clear the tag everywhere else first, since ttk.Treeview doesn't
        do this automatically. Only touches the "active_file" tag itself
        (rather than wiping every tag on the row) so it doesn't clobber
        the git status tags apply_git_status_tags() applies separately."""
        editor = get_current_editor()
        path = editor["path"] if editor else None
        for node in _walk_tree_nodes():
            tags = _node_tags(node)
            if "active_file" in tags:
                project_tree.item(node, tags=tuple(t for t in tags if t != "active_file"))
        if not path:
            return
        norm_path = os.path.normpath(path)
        for node in _walk_tree_nodes():
            values = project_tree.item(node, "values")
            if values and os.path.normpath(values[0]) == norm_path:
                tags = _node_tags(node)
                project_tree.item(node, tags=tags + ("active_file",))
                project_tree.see(node)
                return

    def apply_git_status_tags():
        """Recolors explorer rows to reflect `git status` - accent for
        staged files, an attention color for modified-but-unstaged files,
        and a muted-green for untracked ones. Cheap enough to call after
        every tree refresh/save; does nothing if project_path isn't
        inside a git repo (or no folder is open at all)."""
        git_tags = ("git_staged", "git_modified", "git_untracked")

        def _clear(node):
            tags = _node_tags(node)
            kept = tuple(t for t in tags if t not in git_tags)
            if kept != tags:
                project_tree.item(node, tags=kept)

        if not project_path:
            for node in _walk_tree_nodes():
                _clear(node)
            return

        repo_root = git_panel.find_repo_root(project_path)
        if not repo_root:
            for node in _walk_tree_nodes():
                _clear(node)
            return

        status = git_panel.get_status(repo_root)
        if status.get("error"):
            for node in _walk_tree_nodes():
                _clear(node)
            return

        def _abs_paths(entries):
            return {os.path.normpath(os.path.join(repo_root, p)) for _, p in entries}

        staged_paths = _abs_paths(status["staged"])
        modified_paths = _abs_paths(status["unstaged"])
        untracked_paths = _abs_paths(status["untracked"])

        for node in _walk_tree_nodes():
            values = project_tree.item(node, "values")
            _clear(node)
            if not values:
                continue
            path = os.path.normpath(values[0])
            if path in staged_paths:
                tag = "git_staged"
            elif path in modified_paths:
                tag = "git_modified"
            elif path in untracked_paths:
                tag = "git_untracked"
            else:
                continue
            project_tree.item(node, tags=_node_tags(node) + (tag,))

    def refresh_tree(select_path=None):
        if not project_path:
            return
        expanded = _get_expanded_paths()
        populate_tree(project_path)
        _restore_expanded_paths(expanded)
        if select_path:
            _select_tree_path(select_path)
        highlight_active_file()
        apply_git_status_tags()

    # Catches files created/deleted/renamed outside the app (another
    # editor, git, a terminal command) by refreshing whenever the window
    # regains focus - cheap enough to just always do, and avoids pulling
    # in a filesystem-watcher dependency for something this infrequent.
    def _on_app_focus_in(event):
        if event.widget is root:
            refresh_tree()
            git_controls["refresh"]()

    root.bind("<FocusIn>", _on_app_focus_in)

    # ---------- Explorer: right-click context menu ----------
    tree_context_menu = tk.Menu(project_tree, tearoff=0, **menu_opts)

    def tree_new_file(target_dir):
        name = simpledialog.askstring("New File", "File name:", parent=root)
        if not name:
            return
        new_path = os.path.join(target_dir, name)
        if os.path.exists(new_path):
            messagebox.showerror("New File", f"'{name}' already exists.")
            return
        try:
            with open(new_path, "w", encoding="utf-8"):
                pass
        except OSError as e:
            messagebox.showerror("New File", f"Couldn't create file: {e}")
            return
        refresh_tree(select_path=new_path)
        _open_path_in_tab(new_path)

    def tree_new_folder(target_dir):
        name = simpledialog.askstring("New Folder", "Folder name:", parent=root)
        if not name:
            return
        new_path = os.path.join(target_dir, name)
        if os.path.exists(new_path):
            messagebox.showerror("New Folder", f"'{name}' already exists.")
            return
        try:
            os.makedirs(new_path)
        except OSError as e:
            messagebox.showerror("New Folder", f"Couldn't create folder: {e}")
            return
        refresh_tree(select_path=new_path)

    def _retarget_open_tabs(old_path, new_path):
        """After a rename on disk, point any open tabs at the new location
        instead of leaving them referencing a path that no longer exists
        - handles both a single renamed file and a renamed folder's
        already-open descendants."""
        old_prefix = old_path + os.sep
        for editor in tab_editors.values():
            p = editor["path"]
            if p is None:
                continue
            if p == old_path:
                editor["path"] = new_path
                editor["title"] = os.path.basename(new_path)
                set_tab_title(editor)
            elif p.startswith(old_prefix):
                editor["path"] = new_path + p[len(old_path):]
        current = get_current_editor()
        if current:
            refresh_window_title(current)

    def tree_rename(target_path):
        old_name = os.path.basename(target_path)
        new_name = simpledialog.askstring(
            "Rename", "New name:", initialvalue=old_name, parent=root
        )
        if not new_name or new_name == old_name:
            return
        new_path = os.path.join(os.path.dirname(target_path), new_name)
        if os.path.exists(new_path):
            messagebox.showerror("Rename", f"'{new_name}' already exists.")
            return
        try:
            os.rename(target_path, new_path)
        except OSError as e:
            messagebox.showerror("Rename", f"Couldn't rename: {e}")
            return
        _retarget_open_tabs(target_path, new_path)
        refresh_tree(select_path=new_path)

    def tree_delete(target_path):
        name = os.path.basename(target_path)
        is_dir = os.path.isdir(target_path)
        kind = "folder" if is_dir else "file"
        if not messagebox.askyesno(
            "Delete",
            f"Are you sure you want to delete the {kind} '{name}'? "
            "This cannot be undone."
        ):
            return
        try:
            if is_dir:
                shutil.rmtree(target_path)
            else:
                os.remove(target_path)
        except OSError as e:
            messagebox.showerror("Delete", f"Couldn't delete: {e}")
            return

        # Close any open tabs for the deleted file (or anything that lived
        # inside a deleted folder) - there's nothing left on disk to save.
        prefix = target_path + os.sep
        for tab_id, editor in list(tab_editors.items()):
            p = editor["path"]
            if p == target_path or (p and p.startswith(prefix)):
                editor["dirty"] = False
                close_tab(tab_id)

        refresh_tree()

    def reveal_in_file_explorer(target_path):
        try:
            if IS_WINDOWS:
                subprocess.run(["explorer", "/select,", os.path.normpath(target_path)])
            elif os.uname().sysname == "Darwin":
                subprocess.run(["open", "-R", target_path])
            else:
                folder = target_path if os.path.isdir(target_path) else os.path.dirname(target_path)
                subprocess.run(["xdg-open", folder])
        except Exception as e:
            messagebox.showerror("Reveal", f"Couldn't open file explorer: {e}")

    def _copy_to_clipboard(text):
        root.clipboard_clear()
        root.clipboard_append(text)

    def copy_path(target_path):
        _copy_to_clipboard(os.path.normpath(target_path))

    def copy_relative_path(target_path):
        base = project_path or os.path.dirname(target_path)
        try:
            rel = os.path.relpath(target_path, base)
        except ValueError:
            rel = target_path  # e.g. different drive on Windows
        _copy_to_clipboard(rel.replace(os.sep, "/"))

    def show_tree_context_menu(event):
        if project_path is None:
            return  # nothing open yet - nowhere to create/rename/delete

        item = project_tree.identify_row(event.y)
        if item:
            project_tree.selection_set(item)
            project_tree.focus(item)
            values = project_tree.item(item, "values")
            target_path = values[0] if values else project_path
        else:
            target_path = project_path

        is_dir = os.path.isdir(target_path)
        target_dir = target_path if is_dir else os.path.dirname(target_path)
        is_root = (os.path.normpath(target_path) == os.path.normpath(project_path))

        tree_context_menu.delete(0, tk.END)
        tree_context_menu.add_command(
            label="New File...", command=lambda: tree_new_file(target_dir)
        )
        tree_context_menu.add_command(
            label="New Folder...", command=lambda: tree_new_folder(target_dir)
        )
        if not is_root:
            tree_context_menu.add_separator()
            tree_context_menu.add_command(
                label="Rename...", command=lambda: tree_rename(target_path)
            )
            tree_context_menu.add_command(
                label="Delete", command=lambda: tree_delete(target_path)
            )
        tree_context_menu.add_separator()
        tree_context_menu.add_command(
            label="Reveal in File Explorer",
            command=lambda: reveal_in_file_explorer(target_path)
        )
        tree_context_menu.add_separator()
        tree_context_menu.add_command(
            label="Copy Path", command=lambda: copy_path(target_path)
        )
        tree_context_menu.add_command(
            label="Copy Relative Path", command=lambda: copy_relative_path(target_path)
        )
        tree_context_menu.tk_popup(event.x_root, event.y_root)

    project_tree.bind("<Button-3>", show_tree_context_menu)

    def save_file():
        editor = get_current_editor()
        if editor:
            save_editor(editor)

    def save_as_file():
        editor = get_current_editor()
        if editor:
            save_editor_as(editor)

    # ---------- Run code ----------
    # Runs the file through the same live shell backing the Terminal tab
    # ---------- Run ----------
    # Spawns the program in its own console window (see _spawn_run_console
    # above) - the same handoff Code::Blocks/Dev-C++ do - rather than
    # piping it through an embedded shell. Interactive input (input(),
    # Console.ReadLine(), etc.) just works, since it's a real console.
    if IS_WINDOWS:
        RUNNERS = {
            "Python": "python",
            "JavaScript": "node",
        }
    else:
        RUNNERS = {
            "Python": "python3",
            "JavaScript": "node",
            "Shell Script": "bash",
        }

    def run_code():
        editor = get_current_editor()
        if not editor:
            return

        if editor["path"]:
            save_editor(editor)
            if editor["dirty"]:
                return  # save was cancelled/failed
            run_path = editor["path"]
        else:
            # Unsaved buffer - drop it next to the project folder (or
            # CodeForge's own cwd) so there's a real file to point the
            # spawned console at.
            with tempfile.NamedTemporaryFile(
                mode="w", suffix=".py", dir=_project_cwd(), delete=False
            ) as tmp:
                tmp.write(editor["text"].get("1.0", "end-1c"))
                run_path = tmp.name

        interpreter = RUNNERS.get(get_language_label(run_path))
        if not interpreter:
            messagebox.showinfo(
                "Run", f"Don't know how to run {get_language_label(run_path)} files."
            )
            return

        run_dir = os.path.dirname(run_path) or _project_cwd()
        filename = os.path.basename(run_path)

        output_area.config(state="normal")
        output_area.delete("1.0", tk.END)
        output_area.insert("1.0", f"Running {filename} in a separate window...\n")
        output_area.config(state="disabled")
        bottom_panel.select(output_tab)

        try:
            proc = _spawn_run_console(interpreter, filename, run_dir)
        except Exception as e:
            output_area.config(state="normal")
            output_area.insert(tk.END, f"\nFailed to launch: {e}\n")
            output_area.config(state="disabled")
            return

        run_state["proc"] = proc

        def wait_for_exit(p=proc):
            code = p.wait()

            def report():
                # A newer Run may have started (and finished) while this
                # one's console window was still open - only report if
                # this is still the process anyone would care about.
                if run_state.get("proc") is p:
                    output_area.config(state="normal")
                    output_area.insert(tk.END, f"\n[process exited with code {code}]\n")
                    output_area.config(state="disabled")

            root.after(0, report)

        threading.Thread(target=wait_for_exit, daemon=True).start()

    # ---------- Find / Replace ----------
    find_state = {
        "window": None,
        "entry": None,
        "replace_entry": None,
        "match_case": None,
        "status_label": None,
        "matches": [],
        "current": -1,
        "last_term": None,
        "last_case": None,
    }

    def _refresh_editor_view(editor):
        # Text changed programmatically (replace) - the usual on-keystroke
        # refreshes don't fire for that, so do them by hand.
        update_line_numbers(editor)
        highlight_syntax(editor)
        highlight_current_line(editor["text"])
        highlight_brackets(editor["text"])
        update_indent_guides(editor)
        render_minimap_content(editor)
        update_status_bar(editor)

    def _clear_search_highlights(editor):
        editor["text"].tag_remove("search_match", "1.0", tk.END)
        editor["text"].tag_remove("search_current", "1.0", tk.END)

    def _run_search(term, match_case):
        editor = get_current_editor()
        find_state["matches"] = []
        find_state["current"] = -1

        if not editor:
            return []

        _clear_search_highlights(editor)

        if not term:
            return []

        text_area = editor["text"]
        matches = []
        start = "1.0"
        while True:
            pos = text_area.search(term, start, stopindex="end", nocase=not match_case)
            if not pos:
                break
            end = f"{pos}+{len(term)}c"
            matches.append((pos, end))
            text_area.tag_add("search_match", pos, end)
            start = end

        find_state["matches"] = matches
        return matches

    def _update_status():
        label = find_state["status_label"]
        if not label:
            return
        total = len(find_state["matches"])
        if not find_state["entry"].get():
            label.config(text="")
        elif total == 0:
            label.config(text="No matches")
        else:
            label.config(text=f"{find_state['current'] + 1} of {total}")

    def _select_match(index):
        editor = get_current_editor()
        matches = find_state["matches"]
        if not editor or not matches:
            _update_status()
            return

        index = index % len(matches)
        find_state["current"] = index
        pos, end = matches[index]

        text_area = editor["text"]
        text_area.tag_remove("search_current", "1.0", tk.END)
        text_area.tag_add("search_current", pos, end)
        text_area.mark_set("insert", pos)
        text_area.see(pos)
        _update_status()

    def _search_term_changed():
        term = find_state["entry"].get()
        match_case = find_state["match_case"].get()
        return term != find_state["last_term"] or match_case != find_state["last_case"]

    def _ensure_current_search():
        term = find_state["entry"].get()
        match_case = find_state["match_case"].get()
        if _search_term_changed():
            _run_search(term, match_case)
            find_state["last_term"] = term
            find_state["last_case"] = match_case

    def live_search(event=None):
        _ensure_current_search()
        if find_state["matches"]:
            _select_match(0)
        else:
            _update_status()

    def find_next(event=None):
        _ensure_current_search()
        if not find_state["matches"]:
            _update_status()
            return
        _select_match(find_state["current"] + 1)

    def find_prev(event=None):
        _ensure_current_search()
        if not find_state["matches"]:
            _update_status()
            return
        _select_match(find_state["current"] - 1)

    def replace_current():
        editor = get_current_editor()
        if not editor:
            return

        _ensure_current_search()
        if find_state["current"] == -1 or not find_state["matches"]:
            find_next()
            return

        text_area = editor["text"]
        pos, end = find_state["matches"][find_state["current"]]
        replacement = find_state["replace_entry"].get()

        text_area.delete(pos, end)
        text_area.insert(pos, replacement)
        mark_dirty(editor)
        _refresh_editor_view(editor)

        # The document shifted - re-run the search and land on whatever
        # match now sits at/after this position.
        term = find_state["entry"].get()
        match_case = find_state["match_case"].get()
        _run_search(term, match_case)

        matches = find_state["matches"]
        next_index = 0
        for i, (m_start, _) in enumerate(matches):
            if text_area.compare(m_start, ">=", pos):
                next_index = i
                break
        else:
            next_index = 0

        if matches:
            _select_match(next_index)
        else:
            _update_status()

    def replace_all():
        editor = get_current_editor()
        term = find_state["entry"].get()
        if not editor or not term:
            return

        replacement = find_state["replace_entry"].get()
        match_case = find_state["match_case"].get()
        text_area = editor["text"]

        count = 0
        start = "1.0"
        while True:
            pos = text_area.search(term, start, stopindex="end", nocase=not match_case)
            if not pos:
                break
            end = f"{pos}+{len(term)}c"
            text_area.delete(pos, end)
            text_area.insert(pos, replacement)
            start = f"{pos}+{len(replacement)}c"
            count += 1

        if count:
            mark_dirty(editor)
            _refresh_editor_view(editor)

        _run_search(term, match_case)
        label = find_state["status_label"]
        if label:
            label.config(text=f"Replaced {count} occurrence(s)")

    def _build_find_window():
        win = tk.Toplevel(root)
        win.title("Find & Replace")
        win.resizable(True, True)
        win.minsize(320, 140)
        win.transient(root)
        win.config(bg=THEME["app_bg"])

        label_opts = {"bg": THEME["app_bg"], "fg": THEME["panel_header_fg"]}
        entry_opts = {
            "bg": THEME["editor_bg"],
            "fg": THEME["editor_fg"],
            "insertbackground": THEME["editor_insert"],
            "selectbackground": THEME["editor_select_bg"],
            "selectforeground": THEME["editor_select_fg"],
            "highlightthickness": 1,
            "highlightbackground": THEME["border"],
            "highlightcolor": THEME["accent"],
            "relief": "flat"
        }
        button_opts = {
            "bg": THEME["panel_header_bg"],
            "fg": THEME["panel_header_fg"],
            "activebackground": THEME["editor_select_bg"],
            "activeforeground": THEME["editor_fg"],
            "relief": "flat",
            "highlightthickness": 0
        }

        tk.Label(win, text="Find:", **label_opts).grid(row=0, column=0, sticky="w", padx=6, pady=(8, 2))
        entry = tk.Entry(win, width=32, **entry_opts)
        entry.grid(row=0, column=1, columnspan=3, sticky="we", padx=6, pady=(8, 2))

        tk.Label(win, text="Replace:", **label_opts).grid(row=1, column=0, sticky="w", padx=6, pady=2)
        replace_entry = tk.Entry(win, width=32, **entry_opts)
        replace_entry.grid(row=1, column=1, columnspan=3, sticky="we", padx=6, pady=2)

        match_case_var = tk.BooleanVar(value=False)
        tk.Checkbutton(
            win, text="Match case", variable=match_case_var, command=live_search,
            bg=THEME["app_bg"], fg=THEME["panel_header_fg"],
            activebackground=THEME["app_bg"], activeforeground=THEME["panel_header_fg"],
            selectcolor=THEME["editor_bg"], highlightthickness=0
        ).grid(row=2, column=0, columnspan=2, sticky="w", padx=6)

        status_label = tk.Label(win, text="", fg=THEME["muted_fg"], bg=THEME["app_bg"], anchor="e")
        status_label.grid(row=2, column=1, columnspan=3, sticky="e", padx=6)

        btn_frame = tk.Frame(win, bg=THEME["app_bg"])
        btn_frame.grid(row=3, column=0, columnspan=4, pady=(6, 8))

        tk.Button(btn_frame, text="Find Next", command=find_next, **button_opts).pack(side="left", padx=3)
        tk.Button(btn_frame, text="Find Prev", command=find_prev, **button_opts).pack(side="left", padx=3)
        tk.Button(btn_frame, text="Replace", command=replace_current, **button_opts).pack(side="left", padx=3)
        tk.Button(btn_frame, text="Replace All", command=replace_all, **button_opts).pack(side="left", padx=3)

        win.columnconfigure(1, weight=1)
        win.rowconfigure(0, weight=1)
        win.rowconfigure(1, weight=1)

        def on_close():
            editor = get_current_editor()
            if editor:
                _clear_search_highlights(editor)
            find_state["matches"] = []
            find_state["current"] = -1
            find_state["last_term"] = None
            win.withdraw()

        win.protocol("WM_DELETE_WINDOW", on_close)
        win.bind("<Escape>", lambda e: on_close())
        entry.bind("<Return>", find_next)
        entry.bind("<Shift-Return>", find_prev)
        entry.bind("<KeyRelease>", live_search)
        replace_entry.bind("<Return>", lambda e: replace_current())

        find_state.update({
            "window": win,
            "entry": entry,
            "replace_entry": replace_entry,
            "match_case": match_case_var,
            "status_label": status_label,
        })

    def open_find_replace(focus="find"):
        win = find_state["window"]
        if win is None or not win.winfo_exists():
            _build_find_window()
            win = find_state["window"]
        else:
            win.deiconify()
            win.lift()

        editor = get_current_editor()
        if editor:
            sel_ranges = editor["text"].tag_ranges("sel")
            if sel_ranges:
                selected = editor["text"].get(sel_ranges[0], sel_ranges[1])
                if selected and "\n" not in selected:
                    find_state["entry"].delete(0, tk.END)
                    find_state["entry"].insert(0, selected)

        target = find_state["replace_entry"] if focus == "replace" else find_state["entry"]
        target.focus_set()
        target.select_range(0, tk.END)
        live_search()

    # ---------- Menu bar ----------
    # Each dropdown is still a real tk.Menu (so separators, accelerators,
    # etc. all work as before) - only the top-level strip that shows/posts
    # them changes, from a native OS menu to themed Menubuttons packed into
    # menu_bar_frame (reserved near the top of run()).
    # NOTE: these used to be tk.Menubutton(menu=dropdown) widgets, relying on
    # Tk's automatic Menubutton->Menu posting. On some Tk builds/window
    # managers that posting silently does nothing on click (confirmed with
    # a minimal repro) - explicitly posting the menu ourselves on
    # <Button-1> is a much more portable pattern and sidesteps it entirely.
    menubutton_opts = {
        "bg": THEME["panel_header_bg"],
        "fg": THEME["panel_header_fg"],
        "activebackground": THEME["editor_select_bg"],
        "activeforeground": THEME["editor_select_fg"],
        "relief": "flat",
        "bd": 0,
        "highlightthickness": 0,
        "padx": 10,
        "pady": 4,
    }

    def _make_menu_launcher(parent, label, dropdown):
        btn = tk.Button(parent, text=label, **menubutton_opts)

        def post_menu(event, m=dropdown, b=btn):
            # Anchor to the button's own bottom-left corner rather than the
            # cursor's click position, so the menu always drops straight
            # down from the button like a normal menu bar - clicking near
            # an edge of the button no longer makes it pop up off to the
            # side.
            x = b.winfo_rootx()
            y = b.winfo_rooty() + b.winfo_height()
            try:
                m.tk_popup(x, y)
            finally:
                # Without this, the implicit grab tk_popup() takes can stick
                # around after the menu closes and swallow the next click.
                m.grab_release()
            # "break" stops this click from also reaching the Button
            # widget's own built-in "pressed" bindings. Those rely on a
            # matching <ButtonRelease-1> to restore the normal look, but
            # tk_popup()'s grab sends that release to the menu instead of
            # the button, which is what left File/Edit stuck highlighted
            # blue after the menu closed.
            return "break"

        btn.bind("<Button-1>", post_menu)
        return btn

    file_menu = tk.Menu(root, tearoff=0, **menu_opts)
    file_menu.add_command(label="New Tab", command=new_file, accelerator="Ctrl+N")
    file_menu.add_command(label="New Window", command=new_window, accelerator="Ctrl+Shift+N")
    file_menu.add_command(label="Open File", command=open_file, accelerator="Ctrl+O")
    file_menu.add_command(label="Open Folder", command=open_folder)

    recent_files_menu = tk.Menu(root, tearoff=0, **menu_opts)

    def _open_recent(path):
        if not os.path.isfile(path):
            messagebox.showerror("Open Recent", f"{path}\n\nThis file no longer exists.")
            paths = recent_files_state["paths"]
            if path in paths:
                paths.remove(path)
                save_recent_files(paths)
                _rebuild_recent_files_menu()
            return
        _open_path_in_tab(path)

    def _clear_recent_files():
        recent_files_state["paths"] = []
        save_recent_files([])
        _rebuild_recent_files_menu()

    def _rebuild_recent_files_menu():
        recent_files_menu.delete(0, tk.END)
        paths = recent_files_state["paths"]
        if not paths:
            recent_files_menu.add_command(label="(No Recent Files)", state="disabled")
            return
        for recent_path in paths:
            recent_files_menu.add_command(
                label=recent_path, command=lambda p=recent_path: _open_recent(p)
            )
        recent_files_menu.add_separator()
        recent_files_menu.add_command(label="Clear Recent Files", command=_clear_recent_files)

    _rebuild_recent_files_menu()
    file_menu.add_cascade(label="Open Recent", menu=recent_files_menu)

    file_menu.add_command(label="Save", command=save_file, accelerator="Ctrl+S")
    file_menu.add_command(label="Save As", command=save_as_file)
    file_menu.add_separator()
    file_menu.add_command(label="Close Tab", command=lambda: close_tab(), accelerator="Ctrl+W")
    file_menu.add_separator()

    def save_current_session():
        # Only real files can be restored (we'd have nothing to fill an
        # unsaved "Untitled" tab's text back in with), so those are skipped
        # here - they're still caught by the usual "unsaved changes?" prompt
        # before we ever get this far, so nothing is silently lost.
        open_paths = []
        active_path = None
        current = get_current_editor()
        for tab_id in tab_control.tabs():
            editor = tab_editors.get(tab_id)
            if editor is None or not editor["path"]:
                continue
            open_paths.append(editor["path"])
            if editor is current:
                active_path = editor["path"]
        save_session(project_path, open_paths, active_path)

    def on_exit():
        for tab_id in list(tab_editors.keys()):
            editor = tab_editors.get(tab_id)
            if editor is None:
                continue
            if not prompt_save_if_dirty(editor, tab_id):
                return
        stop_focus_session()
        save_current_session()
        root.destroy()

    def _switch_theme_and_relaunch(new_theme_name):
        # Applying a new palette touches colors baked into dozens of widgets
        # at creation time (editor surfaces, tabs, popups, the terminal...).
        # Rather than hunt down and re-configure every one of them, we save
        # the new preference and relaunch the app so it comes up fully
        # re-themed - same trick VS Code uses for some settings that need a
        # reload. We still run the normal "unsaved changes?" checks first,
        # and we save the open files/folder so the relaunch reopens them
        # instead of coming back up blank.
        for tab_id in list(tab_editors.keys()):
            editor = tab_editors.get(tab_id)
            if editor is None:
                continue
            if not prompt_save_if_dirty(editor, tab_id):
                return

        save_theme_preference(new_theme_name)
        save_current_session()

        root.destroy()
        os.execv(sys.executable, [sys.executable] + sys.argv)

    def cycle_theme():
        # Steps to the next theme in THEMES' definition order, wrapping
        # back to the first after the last - this is what the status-bar
        # click and the Ctrl+Shift+D shortcut use so they keep working as
        # a quick "next theme" action now that there are more than two.
        names = list(THEMES.keys())
        idx = names.index(THEME_NAME)
        new_theme_name = names[(idx + 1) % len(names)]
        _switch_theme_and_relaunch(new_theme_name)

    def set_theme(name):
        if name == THEME_NAME:
            return
        _switch_theme_and_relaunch(name)

    # ---------- Zen / distraction-free mode ----------
    # Hides everything but the editor surface itself: menu bar, explorer,
    # output/terminal panel, minimap, and status bar. Nothing here is
    # destroyed, just unpacked/forgotten from its parent, so re-entering
    # normal mode is a straight replay of the original pack()/add() calls
    # captured at startup - no state to reconstruct.
    zen_state = {"active": False}

    def _enter_zen_mode():
        zen_state["active"] = True
        zen_state["minimap_was_visible"] = minimap_state["visible"]

        menu_bar_frame.pack_forget()
        status_bar_divider.pack_forget()
        status_bar.pack_forget()

        # PanedWindow panes have to be forgotten (not just their contents
        # hidden) or their sash/width reservation keeps eating screen space
        # even at zero content.
        try:
            main_frame.forget(explorer_frame)
        except tk.TclError:
            pass
        try:
            main_frame.forget(output_frame)
        except tk.TclError:
            pass

        if minimap_state["visible"]:
            toggle_minimap()

    def _exit_zen_mode():
        zen_state["active"] = False

        # Re-pack in the exact same order as startup (menu bar, then status
        # bar/divider, then main_frame last) so the packer's carve-out order
        # comes out identical to a fresh launch. main_frame is forgotten and
        # immediately re-packed right here (rather than back in
        # _enter_zen_mode) so it's never actually missing from the screen -
        # it stays visible the whole time zen mode is active. Packing it
        # last here means it claims whatever's left over (the middle), the
        # same as it did at startup, rather than keeping a stale earlier
        # position in the packing list that leaves the others nothing to
        # carve from.
        main_frame.pack_forget()
        menu_bar_frame.pack(side="top", fill="x")
        status_bar.pack(side="bottom", fill="x")
        status_bar_divider.pack(side="bottom", fill="x")
        main_frame.pack(fill="both", expand=True)

        try:
            main_frame.add(explorer_frame, width=220, minsize=120, stretch="never", before=center_frame)
        except tk.TclError:
            pass
        try:
            main_frame.add(output_frame, width=300, minsize=150, stretch="never")
        except tk.TclError:
            pass

        if zen_state.get("minimap_was_visible") and not minimap_state["visible"]:
            toggle_minimap()

    # ---------- Focus session (Zen + Pomodoro + auto-pause music) ----------
    # Work period: Zen Mode on, music (if any) keeps playing. Break period:
    # Zen Mode drops so panels are usable again, and music auto-pauses so
    # it doesn't keep playing while you're away - then both flip back when
    # the next work period starts. Runs on a plain root.after loop rather
    # than a thread since it only ever touches Tk widgets.
    focus_state = {"active": False, "after_id": None}

    def _focus_update_label():
        mins, secs = divmod(max(focus_state["remaining"], 0), 60)
        icon = "\U0001F345" if focus_state["phase"] == "work" else "\u2615"
        phase_label = "Focus" if focus_state["phase"] == "work" else "Break"
        status_focus_label.config(text=f"{icon} {phase_label} {mins:02d}:{secs:02d}")

    def _focus_switch_phase():
        root.bell()
        if focus_state["phase"] == "work":
            focus_state["phase"] = "break"
            focus_state["remaining"] = focus_state["break_seconds"]
            is_playing = music_controls.get("is_playing")
            pause = music_controls.get("pause")
            focus_state["music_was_playing"] = bool(is_playing and is_playing())
            if focus_state["music_was_playing"] and pause:
                pause()
            if zen_state["active"]:
                _exit_zen_mode()
        else:
            focus_state["phase"] = "work"
            focus_state["remaining"] = focus_state["work_seconds"]
            if focus_state.get("music_was_playing"):
                resume = music_controls.get("resume")
                if resume:
                    resume()
            if not zen_state["active"]:
                _enter_zen_mode()
        view_menu.entryconfig(
            zen_menu_index,
            label="Exit Zen Mode" if zen_state["active"] else "Enter Zen Mode"
        )

    def _focus_tick():
        if not focus_state["active"]:
            return
        if focus_state["remaining"] <= 0:
            _focus_switch_phase()
        _focus_update_label()
        focus_state["remaining"] -= 1
        focus_state["after_id"] = root.after(1000, _focus_tick)

    def start_focus_session():
        if focus_state["active"]:
            return
        work_minutes = simpledialog.askinteger(
            "Focus Session", "Work minutes:", initialvalue=25, minvalue=1, maxvalue=180, parent=root
        )
        if work_minutes is None:
            return
        break_minutes = simpledialog.askinteger(
            "Focus Session", "Break minutes:", initialvalue=5, minvalue=1, maxvalue=60, parent=root
        )
        if break_minutes is None:
            return

        focus_state["active"] = True
        focus_state["phase"] = "work"
        focus_state["work_seconds"] = work_minutes * 60
        focus_state["break_seconds"] = break_minutes * 60
        focus_state["remaining"] = focus_state["work_seconds"]
        focus_state["was_zen_before"] = zen_state["active"]
        if not zen_state["active"]:
            _enter_zen_mode()
            view_menu.entryconfig(zen_menu_index, label="Exit Zen Mode")
        view_menu.entryconfig(focus_menu_index, label="Stop Focus Session")
        _focus_tick()

    def stop_focus_session():
        if not focus_state["active"]:
            return
        focus_state["active"] = False
        if focus_state.get("after_id") is not None:
            try:
                root.after_cancel(focus_state["after_id"])
            except Exception:
                pass
            focus_state["after_id"] = None
        status_focus_label.config(text="")
        if zen_state["active"] and not focus_state.get("was_zen_before"):
            _exit_zen_mode()
            view_menu.entryconfig(zen_menu_index, label="Enter Zen Mode")
        view_menu.entryconfig(focus_menu_index, label="Start Focus Session")

    def toggle_focus_session():
        if focus_state["active"]:
            stop_focus_session()
        else:
            start_focus_session()

    file_menu.add_command(label="Exit", command=on_exit)

    root.protocol("WM_DELETE_WINDOW", on_exit)

    edit_menu = tk.Menu(root, tearoff=0, **menu_opts)
    edit_menu.add_command(label="Find...", command=lambda: open_find_replace("find"), accelerator="Ctrl+F")
    edit_menu.add_command(label="Replace...", command=lambda: open_find_replace("replace"), accelerator="Ctrl+H")

    run_menu = tk.Menu(root, tearoff=0, **menu_opts)
    run_menu.add_command(label="Run", command=run_code, accelerator="F5")
    run_menu.add_command(label="Kill", command=kill_running)
    run_menu.add_separator()
    run_menu.add_command(label="Clear Output", command=clear_output, accelerator="Ctrl+K")

    view_menu = tk.Menu(root, tearoff=0, **menu_opts)
    view_menu.add_command(label="Open Terminal", command=open_external_terminal, accelerator="Ctrl+`")
    view_menu.add_separator()
    view_menu.add_command(label="Zoom In", command=zoom_in, accelerator="Ctrl++")
    view_menu.add_command(label="Zoom Out", command=zoom_out, accelerator="Ctrl+-")
    view_menu.add_command(label="Reset Zoom", command=zoom_reset, accelerator="Ctrl+0")
    view_menu.add_separator()

    def toggle_minimap():
        minimap_state["visible"] = not minimap_state["visible"]
        for ed in tab_editors.values():
            canvas = ed.get("minimap")
            if canvas is None:
                continue
            if minimap_state["visible"]:
                canvas.pack(side="left", fill="y")
                render_minimap_content(ed)
            else:
                canvas.pack_forget()
        view_menu.entryconfig(
            minimap_menu_index,
            label="Hide Minimap" if minimap_state["visible"] else "Show Minimap"
        )

    view_menu.add_command(label="Hide Minimap", command=toggle_minimap, accelerator="Ctrl+M")
    minimap_menu_index = view_menu.index(tk.END)

    def toggle_crt_scanlines():
        crt_state["scanlines"] = not crt_state["scanlines"]
        for ed in tab_editors.values():
            apply_crt_scanlines(ed)
        view_menu.entryconfig(
            crt_menu_index,
            label="Hide CRT Scanlines" if crt_state["scanlines"] else "Show CRT Scanlines"
        )

    view_menu.add_command(label="Show CRT Scanlines", command=toggle_crt_scanlines)
    crt_menu_index = view_menu.index(tk.END)

    def toggle_zen_mode():
        if zen_state["active"]:
            _exit_zen_mode()
        else:
            _enter_zen_mode()
        view_menu.entryconfig(
            zen_menu_index,
            label="Exit Zen Mode" if zen_state["active"] else "Enter Zen Mode"
        )

    view_menu.add_command(label="Enter Zen Mode", command=toggle_zen_mode, accelerator="Ctrl+Shift+Z")
    zen_menu_index = view_menu.index(tk.END)

    view_menu.add_command(label="Start Focus Session", command=toggle_focus_session, accelerator="Ctrl+Shift+F")
    focus_menu_index = view_menu.index(tk.END)

    view_menu.add_separator()

    # Theme submenu - one entry per palette in THEMES, with a checkmark
    # next to whichever is currently active. Picking any entry (including
    # the active one, harmlessly - set_theme no-ops on a no-op change)
    # relaunches the app themed accordingly.
    theme_menu = tk.Menu(root, tearoff=0, **menu_opts)
    for theme_name in THEMES:
        label = THEME_LABELS.get(theme_name, theme_name.replace("_", " ").title())
        if theme_name == THEME_NAME:
            label = "\u2713 " + label
        theme_menu.add_command(label=label, command=lambda n=theme_name: set_theme(n))
    view_menu.add_cascade(label="Theme", menu=theme_menu)
    view_menu.add_command(
        label="Next Theme",
        command=cycle_theme,
        accelerator="Ctrl+Shift+D"
    )

    for label, dropdown in (
        ("File", file_menu),
        ("Edit", edit_menu),
        ("Run", run_menu),
        ("View", view_menu),
    ):
        _make_menu_launcher(menu_bar_frame, label, dropdown).pack(side="left")

    root.bind("<Control-n>", lambda e: new_file())
    root.bind("<Control-Shift-N>", lambda e: new_window())
    root.bind("<Control-Shift-n>", lambda e: new_window())
    root.bind("<Control-o>", lambda e: open_file())
    root.bind("<Control-s>", lambda e: save_file())
    root.bind("<Control-w>", lambda e: close_tab())
    root.bind("<F5>", lambda e: run_code())
    root.bind("<Control-k>", lambda e: clear_output())
    root.bind("<Control-f>", lambda e: open_find_replace("find"))
    root.bind("<Control-h>", lambda e: open_find_replace("replace"))
    root.bind("<Control-grave>", lambda e: open_external_terminal())
    root.bind("<Control-Shift-D>", lambda e: cycle_theme())
    root.bind("<Control-Shift-d>", lambda e: cycle_theme())
    root.bind("<Control-plus>", lambda e: zoom_in())
    root.bind("<Control-equal>", lambda e: zoom_in())
    root.bind("<Control-KP_Add>", lambda e: zoom_in())
    root.bind("<Control-minus>", lambda e: zoom_out())
    root.bind("<Control-KP_Subtract>", lambda e: zoom_out())
    root.bind("<Control-0>", lambda e: zoom_reset())
    root.bind("<Control-KP_0>", lambda e: zoom_reset())
    root.bind("<Control-m>", lambda e: toggle_minimap())
    root.bind("<Control-Shift-Z>", lambda e: toggle_zen_mode())
    root.bind("<Control-Shift-z>", lambda e: toggle_zen_mode())
    root.bind("<Control-Shift-F>", lambda e: toggle_focus_session())
    root.bind("<Control-Shift-f>", lambda e: toggle_focus_session())

    # ---------- Media keys ----------
    # Lets you control the Music tab without switching to it. Real hardware
    # media keys (XF86Audio*) work in Tk on Linux and some Windows builds,
    # but support is inconsistent - Ctrl+Alt+Space/Left/Right are bound as
    # reliable fallbacks that work everywhere regardless of keyboard/OS
    # support for the physical media keys.
    def _media_play_pause(event=None):
        toggle = music_controls.get("toggle_play_pause")
        if toggle:
            toggle()

    def _media_next(event=None):
        nxt = music_controls.get("play_next")
        if nxt:
            nxt()

    def _media_prev(event=None):
        prev = music_controls.get("play_prev")
        if prev:
            prev()

    for keysym in ("<XF86AudioPlay>", "<XF86AudioPause>", "<Control-Alt-space>"):
        root.bind(keysym, _media_play_pause)
    for keysym in ("<XF86AudioNext>", "<Control-Alt-Right>"):
        root.bind(keysym, _media_next)
    for keysym in ("<XF86AudioPrev>", "<Control-Alt-Left>"):
        root.bind(keysym, _media_prev)

    # ---------- Restore previous session ----------
    # Bring back whatever folder/files were open last time (including right
    # after a dark-mode restart, so toggling never looks like it lost work).
    # A window opened via File > New Window is the one exception - it's
    # meant to start blank alongside whatever's already open, not clone it.
    is_new_window = os.environ.get("CODEFORGE_NEW_WINDOW") == "1"
    session = {} if is_new_window else load_session()
    restored_any = False

    saved_folder = session.get("folder")
    if saved_folder and os.path.isdir(saved_folder):
        project_path = saved_folder
        populate_tree(saved_folder)
        refresh_git_state()

    for saved_path in session.get("open_files", []):
        if not saved_path or not os.path.isfile(saved_path):
            continue
        try:
            with open(saved_path, "r", encoding="utf-8") as f:
                saved_content = f.read()
        except OSError:
            continue
        create_tab(path=saved_path, content=saved_content)
        restored_any = True

    if not restored_any:
        create_tab()
    else:
        active_path = session.get("active_path")
        active_tab = find_tab_for_path(active_path) if active_path else None
        if active_tab:
            tab_control.select(active_tab)
        highlight_active_file()

    root.mainloop()