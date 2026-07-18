import tkinter as tk
from tkinter import filedialog
from tkinter import ttk
from tkinter import messagebox
from tkinter import simpledialog
import tkinter.font as tkfont
import re
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
import uuid
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
        is_dark_theme
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
        is_dark_theme
    )

try:
    import winpty  # pip install pywinpty - provides a real Windows pseudo-console
except ImportError:
    winpty = None

try:
    import pty  # stdlib, POSIX only
except ImportError:
    pty = None


# ---------------- Theme ----------------
# The palettes themselves now live in themes.py. We just load whichever one
# the user last picked (defaulting to light) so the whole app reads as one
# consistent theme.
THEME_NAME = load_theme_preference()
THEME = THEMES[THEME_NAME]


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

    root = tk.Tk()
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

    main_frame.add(explorer_frame, width=220, minsize=120, stretch="never")

    center_frame = tk.Frame(main_frame, bg=THEME["app_bg"], highlightthickness=0, bd=0)
    main_frame.add(center_frame, minsize=300, stretch="always")

    tab_control = ttk.Notebook(center_frame)
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

    # Minimap - a zoomed-out overview of the whole file for quick
    # navigation, shared on/off state so new tabs match whatever the user
    # last chose.
    MINIMAP_WIDTH = 100
    minimap_state = {"visible": True}

    # ---------------- Output / Terminal panel ----------------

    output_frame = tk.Frame(main_frame, width=300, bg=THEME["app_bg"], highlightthickness=0, bd=0)
    output_frame.pack_propagate(False)

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

    # ---- Terminal tab (interactive shell-like console) ----
    terminal_tab = tk.Frame(bottom_panel, bg=THEME["output_bg"])
    bottom_panel.add(terminal_tab, text="Terminal")

    terminal_area = tk.Text(
        terminal_tab,
        font=("Consolas", 10),
        bg=THEME["output_bg"],
        fg=THEME["output_fg"],
        insertbackground=THEME["editor_insert"],
        selectbackground=THEME["editor_select_bg"],
        selectforeground=THEME["editor_select_fg"],
        highlightthickness=0,
        border=0,
        wrap="word",
        undo=False
    )
    terminal_area.pack(side="left", fill="both", expand=True)

    terminal_scrollbar = ttk.Scrollbar(
        terminal_tab,
        orient="vertical",
        command=terminal_area.yview,
        style="Vertical.TScrollbar"
    )
    terminal_scrollbar.pack(side="right", fill="y")
    terminal_area.config(yscrollcommand=terminal_scrollbar.set)
    terminal_area.tag_configure("term_error", foreground=THEME["syntax_string"])
    terminal_area.tag_configure("term_muted", foreground=THEME["muted_fg"])

    main_frame.add(output_frame, width=300, minsize=150, stretch="never")

    # ---------- Terminal engine ----------
    # Backed by a real pseudo-console (ConPTY on Windows via pywinpty, or the
    # stdlib pty module on macOS/Linux) rather than plain pipes. A plain pipe
    # makes the shell think it isn't attached to a terminal at all, so it
    # fully-buffers its output (you may never see a prompt) and does none of
    # its own line editing. A pseudo-console fixes both: the shell behaves
    # exactly as it would in a real terminal window, and handles its own
    # backspace/arrow-key/history editing - we just forward raw keystrokes
    # and mirror whatever the shell echoes back.
    IS_WINDOWS = (os.name == "nt")
    HAS_PTY_SUPPORT = bool(winpty) if IS_WINDOWS else bool(pty)

    terminal_state = {
        "proc": None,       # winpty.PtyProcess (Windows) or a dict of pty fds/pid (POSIX)
        "alive": False,
        "pending": "",      # a trailing, not-yet-complete escape sequence held over
    }                       # between reads so it isn't split across two chunks

    # "Run" sends the actual command straight into the live terminal (same
    # shell the user can type into) instead of a separate one-shot
    # subprocess, so the program can read stdin from the user just like it
    # would in a real terminal. To *also* mirror its printable output into
    # the Output panel, we watch the raw text flowing through for a unique
    # start/end marker pair that bracket the run, and buffer whatever shows
    # up in between.
    run_state = {
        "awaiting_start": False,
        "active": False,
        "start_marker": None,   # compiled regex - matches only once actually executed
        "end_marker": None,
        "buffer": "",           # raw text collected between the markers
        "scan_pending": "",     # partial marker text held over between reads
    }

    # ---- Mini VT100/ANSI terminal emulator ----
    # A real terminal doesn't just print raw bytes: escape codes move a
    # cursor around and erase pieces of the screen, and typed characters
    # OVERWRITE whatever is under the cursor rather than always being
    # appended at the end. PowerShell's line editor (PSReadLine) leans on
    # exactly this - it redraws in place using cursor-left/right and
    # erase-to-end-of-line codes (e.g. for backspace, arrow-key history,
    # and its inline suggestion text). Previously we only stripped the
    # escape codes and always appended at "end", which ignored those
    # cursor moves entirely - producing duplicated characters and dead
    # backspace/arrow keys. Instead we track a real cursor position (a Tk
    # mark) and apply each instruction the way a terminal would.
    # Params: 0x30-0x3F ("0-9:;<=>?"), intermediates: 0x20-0x2F (" " through
    # "/"), final byte: 0x40-0x7E ("@" through "~"). The earlier version only
    # allowed "[0-9;?]" with no intermediate bytes at all, so any sequence
    # outside that narrow set (e.g. cursor-shape codes like "\x1b[3 q", or
    # "<"/"="/">" prefixed sequences) could never match. That made it look
    # "incomplete" forever, so everything after it piled up unresolved in
    # the pending buffer instead of ever being displayed.
    _CSI_RE = re.compile(r'\x1b\[([0-9:;<=>?]*)[ -/]*([@-~])')
    _OSC_END_RE = re.compile(r'(\x07|\x1b\\)')

    def _term_cursor_idx():
        return terminal_area.index("term_cursor")

    def _term_last_line():
        return int(terminal_area.index("end-1c").split(".")[0])

    def _term_putc(ch):
        idx = _term_cursor_idx()
        line_end = terminal_area.index(f"{idx.split('.')[0]}.end")
        if terminal_area.compare(idx, "<", line_end):
            terminal_area.delete(idx, f"{idx}+1c")  # overwrite, don't insert
        terminal_area.insert(idx, ch)
        terminal_area.mark_set("term_cursor", f"{idx}+1c")

    def _term_trim_trailing_pad():
        # A destructive backspace (BS, " ", BS) moves the cursor left,
        # overwrites the erased character with a literal space, then moves
        # left again - correct on a real terminal's fixed-width grid, but
        # here lines are just strings, so that overwrite leaves a REAL
        # trailing space sitting after the cursor instead of actually
        # shrinking the line. Left in place, that stray space fools later
        # "are we at the true end of the buffer?" checks into thinking a
        # line already exists below us, so no new line ever gets inserted
        # and subsequent output keeps landing on this same row.
        #
        # Called after every cursor-moving step (not just before a "\n"),
        # because a "\r" (or any other jump) can reach the padding before
        # a "\n" does - trimming only inside the linefeed handler caught
        # some cases but not that one, which is why it only "sometimes"
        # showed a stray character.
        idx = _term_cursor_idx()
        line = int(idx.split(".")[0])
        if line != _term_last_line():
            return
        line_end_idx = terminal_area.index(f"{line}.end")
        if terminal_area.compare(idx, ">=", line_end_idx):
            return
        tail = terminal_area.get(idx, line_end_idx)
        if tail and tail.strip(" ") == "":
            terminal_area.delete(idx, line_end_idx)

    def _term_cr():
        line = _term_cursor_idx().split(".")[0]
        terminal_area.mark_set("term_cursor", f"{line}.0")

    def _term_lf():
        idx = _term_cursor_idx()
        line, col = idx.split(".")
        line, col = int(line), int(col)

        # Only insert a brand-new "\n" character if the cursor is sitting at
        # the very end of everything typed so far - if a line below already
        # exists (e.g. we scrolled up through history) just move onto it
        # instead of inserting another one, which was creating a fresh
        # blank line on every single line of output.
        if terminal_area.compare(idx, ">=", "end-1c"):
            terminal_area.insert("end-1c", "\n")
        new_col = min(col, int(terminal_area.index(f"{line + 1}.end").split(".")[1]))
        terminal_area.mark_set("term_cursor", f"{line + 1}.{new_col}")

    def _term_left(n=1):
        terminal_area.mark_set("term_cursor", f"term_cursor-{max(n, 1)}c")

    def _term_right(n=1):
        terminal_area.mark_set("term_cursor", f"term_cursor+{max(n, 1)}c")

    def _term_up(n=1):
        line, col = _term_cursor_idx().split(".")
        terminal_area.mark_set("term_cursor", f"{max(1, int(line) - n)}.{col}")

    def _term_down(n=1):
        line, col = _term_cursor_idx().split(".")
        terminal_area.mark_set("term_cursor", f"{min(_term_last_line(), int(line) + n)}.{col}")

    def _term_col(n=1):
        line = _term_cursor_idx().split(".")[0]
        terminal_area.mark_set("term_cursor", f"{line}.{max(0, n - 1)}")

    def _term_erase_to_eol():
        idx = _term_cursor_idx()
        terminal_area.delete(idx, f"{idx.split('.')[0]}.end")

    def _term_erase_to_bol():
        idx = _term_cursor_idx()
        terminal_area.delete(f"{idx.split('.')[0]}.0", idx)

    def _term_erase_line():
        line = _term_cursor_idx().split(".")[0]
        terminal_area.delete(f"{line}.0", f"{line}.end")
        terminal_area.mark_set("term_cursor", f"{line}.0")

    def _term_clear_screen():
        terminal_area.delete("1.0", "end")
        terminal_area.mark_set("term_cursor", "1.0")

    def _term_csi_action(params_str, final):
        parts = [p for p in params_str.lstrip("?").split(";") if p != ""]

        def num(i, default=1):
            try:
                return int(parts[i]) if i < len(parts) and parts[i] != "" else default
            except ValueError:
                return default

        if final == "A":
            return lambda: _term_up(num(0))
        if final == "B":
            return lambda: _term_down(num(0))
        if final == "C":
            return lambda: _term_right(num(0))
        if final == "D":
            return lambda: _term_left(num(0))
        if final == "G":
            return lambda: _term_col(num(0))
        if final in ("H", "f"):
            row, col = num(0), num(1)
            return lambda: terminal_area.mark_set(
                "term_cursor", f"{max(1, min(_term_last_line(), row))}.{max(0, col - 1)}"
            )
        if final == "K":
            mode = num(0, 0)
            return {0: _term_erase_to_eol, 1: _term_erase_to_bol}.get(mode, _term_erase_line)
        if final == "J":
            return _term_clear_screen
        return lambda: None  # SGR colors, mode toggles, cursor save/restore, etc: no-op

    def _consume_escape(text, i):
        """Returns (chars_consumed, action) for the escape sequence starting
        at i, or None if it's cut off at the end of this chunk (incomplete)."""
        n = len(text)
        if i + 1 >= n:
            return None
        nxt = text[i + 1]
        if nxt == "[":
            m = _CSI_RE.match(text, i)
            if not m:
                return None
            return m.end() - i, _term_csi_action(m.group(1), m.group(2))
        if nxt == "]":
            m = _OSC_END_RE.search(text, i + 2)
            if not m:
                return None
            return m.end() - i, (lambda: None)
        return 2, (lambda: None)  # other 2-byte "Fe" escapes: no visual effect we track

    def _term_feed(raw):
        """Feed real shell output through the emulator (cursor-aware)."""
        text = terminal_state["pending"] + raw
        terminal_state["pending"] = ""
        i, n = 0, len(text)
        while i < n:
            try:
                ch = text[i]
                if ch == "\x1b":
                    result = _consume_escape(text, i)
                    if result is None:
                        # A sequence genuinely split across two reads is
                        # only ever a handful of bytes. If far more than
                        # that is sitting unmatched, it's not a split -
                        # it's a sequence our parser doesn't recognize -
                        # so drop just the ESC and keep going rather than
                        # stalling forever.
                        if n - i > 128:
                            i += 1
                            continue
                        terminal_state["pending"] = text[i:]
                        break
                    consumed, action = result
                    action()
                    i += consumed
                elif ch == "\r":
                    _term_cr()
                    i += 1
                elif ch == "\n":
                    _term_lf()
                    i += 1
                elif ch == "\x08":
                    _term_left(1)
                    i += 1
                elif ch == "\x07":
                    i += 1  # bell
                else:
                    _term_putc(ch)
                    i += 1
                _term_trim_trailing_pad()
            except Exception:
                # Something in the emulator broke on this one character -
                # skip it rather than losing everything queued up after it.
                i += 1
        terminal_area.see("term_cursor")

    _MIRROR_CSI_RE = re.compile(r'\x1b\[[0-9:;<=>?]*[ -/]*[@-~]')
    _MIRROR_OSC_RE = re.compile(r'\x1b\][^\x07\x1b]*(\x07|\x1b\\)')

    def _strip_ansi_for_mirror(text):
        """Reduce real terminal output to plain text good enough for the
        Output panel - not a full emulation, just enough to drop escape
        codes and resolve simple backspace/carriage-return redraws so a
        program's actual printed output doesn't show control bytes."""
        text = _MIRROR_OSC_RE.sub("", text)
        text = _MIRROR_CSI_RE.sub("", text)
        text = re.sub(r'\x1b.', '', text)
        text = text.replace("\x07", "")

        out = []
        i, n = 0, len(text)
        while i < n:
            ch = text[i]
            if ch == "\x08":
                if out and out[-1] != "\n":
                    out.pop()
                i += 1
            elif ch == "\r":
                # A "\r\n" pair is just a normal (CRLF) line ending, not an
                # overwrite - skip the "\r" and let the "\n" append as
                # usual instead of erasing the line we just wrote. Only a
                # standalone "\r" (e.g. a progress bar redrawing in place)
                # should trigger the destructive rewind.
                if i + 1 < n and text[i + 1] == "\n":
                    i += 1
                    continue
                while out and out[-1] != "\n":
                    out.pop()
                i += 1
            else:
                out.append(ch)
                i += 1
        return "".join(out)

    def _finish_run_mirror():
        text = _strip_ansi_for_mirror(run_state["buffer"])
        run_state["buffer"] = ""
        output_area.config(state="normal")
        output_area.delete("1.0", tk.END)
        output_area.insert("1.0", text if text.strip() else "(no output)")
        output_area.config(state="disabled")

    def _strip_one_leading_newline(text):
        """Drop a single line-ending (CRLF or LF) off the front of text,
        if present - used to swallow the blank line that would otherwise
        be left behind where a marker line used to be."""
        if text[:2] == "\r\n":
            return text[2:]
        if text[:1] in ("\r", "\n"):
            return text[1:]
        return text

    def _unsafe_tail_len(text, literal_prefix):
        """How many trailing characters of `text` could be the start of
        `literal_prefix` (the fixed, non-digit part of a RUNSOF_/RUNEOF_
        marker) and so must be held back until more data arrives to
        confirm or rule it out. Returns 0 when the tail plainly isn't
        headed toward the marker - which is true for virtually all real
        program output and typed input, so that text can be shown right
        away instead of waiting for a fixed-size chunk to build up."""
        max_k = min(len(text), len(literal_prefix))
        for k in range(max_k, 0, -1):
            if text.endswith(literal_prefix[:k]):
                return k
        return 0

    def _term_feed_with_mirror(raw):
        """Wraps _term_feed: while a "Run" is in flight, watches the raw
        shell output for its start/end markers and buffers whatever runs
        between them, so it can be shown plain-text in the Output panel.
        The synthetic command app.py types (with the RUNSOF/RUNEOF marker
        names baked into it) and the marker echoes themselves are NEVER
        fed to the real terminal - only the program's actual output
        between them is, so the marker text never shows up on screen."""
        if not (run_state["awaiting_start"] or run_state["active"]):
            _term_feed(raw)
            return

        raw = run_state["scan_pending"] + raw
        run_state["scan_pending"] = ""

        if run_state["awaiting_start"]:
            m = run_state["start_marker"].search(raw)
            if not m:
                # Hold back only text that could actually be the start of
                # the marker; everything else is just the synthetic
                # command's own local echo - discard it silently, run_code()
                # already printed a clean, friendly line in its place.
                unsafe = _unsafe_tail_len(raw, run_state["start_prefix"])
                run_state["scan_pending"] = raw[-unsafe:] if unsafe else ""
                return
            run_state["awaiting_start"] = False
            run_state["active"] = True
            raw = _strip_one_leading_newline(raw[m.end():])
            if not raw:
                return

        m = run_state["end_marker"].search(raw)
        if not m:
            unsafe = _unsafe_tail_len(raw, run_state["end_prefix"])
            chunk = raw[:-unsafe] if unsafe else raw
            run_state["buffer"] += chunk
            run_state["scan_pending"] = raw[-unsafe:] if unsafe else ""
            _term_feed(chunk)
            return

        run_state["buffer"] += raw[:m.start()]
        _term_feed(raw[:m.start()])
        run_state["active"] = False
        _finish_run_mirror()
        remainder = _strip_one_leading_newline(raw[m.end():])
        if remainder:
            _term_feed(remainder)

    def _term_print(text, tag=None):
        """Print an internal (non-shell) message - plain text, always appended."""
        if not text:
            return
        if tag:
            terminal_area.insert("end", text, tag)
        else:
            terminal_area.insert("end", text)
        terminal_area.mark_set("term_cursor", "end")
        terminal_area.see("end")

    def _term_on_process_exit():
        if terminal_state["alive"]:
            terminal_state["alive"] = False
            _term_print("\n[shell exited]\n", "term_muted")

    def _term_reader_loop_windows(proc):
        try:
            while proc.isalive():
                try:
                    data = proc.read(4096)
                except EOFError:
                    break
                if data:
                    root.after(0, lambda t=data: _term_feed_with_mirror(t))
        except Exception:
            pass
        root.after(0, _term_on_process_exit)

    def _term_reader_loop_posix(master_fd):
        try:
            while True:
                try:
                    chunk = os.read(master_fd, 4096)
                except OSError:
                    break
                if not chunk:
                    break
                text = chunk.decode("utf-8", errors="replace")
                root.after(0, lambda t=text: _term_feed_with_mirror(t))
        except Exception:
            pass
        root.after(0, _term_on_process_exit)

    def start_shell():
        if not HAS_PTY_SUPPORT:
            if IS_WINDOWS:
                _term_print(
                    "Real terminal support needs the 'pywinpty' package, "
                    "which isn't installed.\nInstall it with:\n\n"
                    "    pip install pywinpty\n\n"
                    "then reopen this Terminal tab.\n",
                    "term_error"
                )
            else:
                _term_print(
                    "Couldn't load the 'pty' module, so a real terminal "
                    "isn't available on this system.\n",
                    "term_error"
                )
            return

        if IS_WINDOWS:
            try:
                proc = winpty.PtyProcess.spawn(
                    # wsl.exe launched from a Windows cwd automatically maps
                    # it to the matching /mnt/... path inside the distro.
                    ["wsl.exe"],
                    cwd=os.getcwd(),
                    dimensions=(32, 120)
                )
            except Exception as e:
                _term_print(
                    f"Failed to start WSL: {e}\n"
                    "Make sure WSL is installed and 'wsl.exe' is on your PATH "
                    "(run 'wsl --install' from an elevated prompt if it isn't set up).\n",
                    "term_error"
                )
                return
            terminal_state["proc"] = proc
            terminal_state["alive"] = True
            threading.Thread(target=_term_reader_loop_windows, args=(proc,), daemon=True).start()
        else:
            shell_path = os.environ.get("SHELL", "/bin/bash")
            master_fd, slave_fd = pty.openpty()
            try:
                proc = subprocess.Popen(
                    [shell_path],
                    cwd=os.getcwd(),
                    stdin=slave_fd,
                    stdout=slave_fd,
                    stderr=slave_fd,
                    preexec_fn=os.setsid,
                    close_fds=True
                )
            except Exception as e:
                os.close(master_fd)
                os.close(slave_fd)
                _term_print(f"Failed to start shell: {e}\n", "term_error")
                return
            os.close(slave_fd)
            terminal_state["proc"] = {"popen": proc, "master_fd": master_fd}
            terminal_state["alive"] = True
            threading.Thread(target=_term_reader_loop_posix, args=(master_fd,), daemon=True).start()

    def init_terminal():
        terminal_area.delete("1.0", "end")
        terminal_area.mark_set("term_cursor", "1.0")
        terminal_area.mark_gravity("term_cursor", "left")
        start_shell()

    def _term_send_raw(data):
        proc = terminal_state.get("proc")
        if not proc or not terminal_state["alive"]:
            return
        try:
            if IS_WINDOWS:
                proc.write(data)
            else:
                os.write(proc["master_fd"], data.encode("utf-8", errors="replace"))
        except (OSError, ValueError):
            pass

    def stop_shell():
        proc = terminal_state.get("proc")
        if not proc or not terminal_state["alive"]:
            return
        terminal_state["alive"] = False
        try:
            if IS_WINDOWS:
                proc.terminate(force=True)
            else:
                proc["popen"].terminate()
                os.close(proc["master_fd"])
        except Exception:
            pass

    # Every keystroke is forwarded raw to the shell; the widget's own
    # editing/self-insert is always suppressed ("break") so the buffer only
    # ever shows what the shell itself echoes back - keeping it byte-for-byte
    # consistent with a real terminal, including its own backspace handling.
    KEY_SEQUENCES = {
        "Return": "\r",
        "BackSpace": "\x7f",
        "Tab": "\t",
        "Up": "\x1b[A",
        "Down": "\x1b[B",
        "Right": "\x1b[C",
        "Left": "\x1b[D",
        "Home": "\x1b[H",
        "End": "\x1b[F",
        "Delete": "\x1b[3~",
        "Escape": "\x1b",
    }

    def terminal_key(event):
        if not terminal_state["alive"]:
            return "break"

        keysym = event.keysym

        if event.state & 0x4 and keysym.lower() == "c":  # Ctrl+C -> interrupt
            _term_send_raw("\x03")
            return "break"
        if event.state & 0x4 and keysym.lower() == "d":  # Ctrl+D -> EOF (POSIX)
            _term_send_raw("\x04")
            return "break"

        if keysym in KEY_SEQUENCES:
            _term_send_raw(KEY_SEQUENCES[keysym])
            return "break"

        if event.char and event.char.isprintable():
            _term_send_raw(event.char)
            return "break"

        # Unhandled key (modifier-only presses, function keys, etc.) - let it
        # pass through harmlessly without touching the buffer ourselves.
        return "break"

    terminal_area.bind("<KeyPress>", terminal_key)

    init_terminal()

    def focus_terminal():
        bottom_panel.select(terminal_tab)
        terminal_area.focus_set()
        terminal_area.mark_set("insert", "end")
        terminal_area.see("end")

    def on_bottom_panel_tab_changed(event=None):
        # Clicking the "Terminal" tab only switches which panel is visible -
        # it doesn't move keyboard focus by itself, so without this a typed
        # command (and Enter) would silently go to whatever had focus before
        # (usually the code editor) instead of the terminal.
        try:
            selected = bottom_panel.select()
        except tk.TclError:
            return
        if selected == str(terminal_tab):
            terminal_area.focus_set()
            terminal_area.mark_set("insert", "end")
            terminal_area.see("end")

    bottom_panel.bind("<<NotebookTabChanged>>", on_bottom_panel_tab_changed)

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

    def highlight_syntax(editor):
        text_area = editor["text"]
        for tag in ("keyword", "string", "comment", "number", "function"):
            text_area.tag_remove(tag, "1.0", tk.END)

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

        # One "row" per available pixel once there are more source lines
        # than the minimap has height for; each row then represents a
        # small bucket of lines rather than a single one, so the whole
        # file is always represented top-to-bottom regardless of length.
        row_count = max(1, min(total_lines, canvas_h))
        row_height = canvas_h / row_count
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
                3, y, 3 + width, y + max(1.0, row_height),
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

    tab_context_menu = tk.Menu(tab_control, tearoff=0, **menu_opts)

    def show_tab_context_menu(event):
        tab_id = tab_id_at_event(event)
        if not tab_id:
            return

        tab_context_menu.delete(0, tk.END)
        tab_context_menu.add_command(label="Close Tab", command=lambda: close_tab(tab_id))
        tab_context_menu.add_command(label="Close Other Tabs", command=lambda: close_other_tabs(tab_id))
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

    def _open_path_in_tab(path):
        existing_tab = find_tab_for_path(path)
        if existing_tab:
            tab_control.select(existing_tab)
            return

        with open(path, "r", encoding="utf-8") as f:
            content = f.read()

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

    # ---------- Explorer: refresh helpers ----------
    # Rebuilding the whole tree from disk (rather than surgically
    # inserting/removing nodes) keeps New/Rename/Delete simple and always
    # correct - the only cost is that ttk.Treeview forgets which folders
    # were expanded, so we snapshot and restore that ourselves.
    def _walk_tree_nodes(parent=""):
        for node in project_tree.get_children(parent):
            yield node
            yield from _walk_tree_nodes(node)

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
        do this automatically."""
        editor = get_current_editor()
        path = editor["path"] if editor else None
        for node in _walk_tree_nodes():
            if project_tree.item(node, "tags"):
                project_tree.item(node, tags=())
        if not path:
            return
        norm_path = os.path.normpath(path)
        for node in _walk_tree_nodes():
            values = project_tree.item(node, "values")
            if values and os.path.normpath(values[0]) == norm_path:
                project_tree.item(node, tags=("active_file",))
                project_tree.see(node)
                return

    def refresh_tree(select_path=None):
        if not project_path:
            return
        expanded = _get_expanded_paths()
        populate_tree(project_path)
        _restore_expanded_paths(expanded)
        if select_path:
            _select_tree_path(select_path)
        highlight_active_file()

    # Catches files created/deleted/renamed outside the app (another
    # editor, git, a terminal command) by refreshing whenever the window
    # regains focus - cheap enough to just always do, and avoids pulling
    # in a filesystem-watcher dependency for something this infrequent.
    def _on_app_focus_in(event):
        if event.widget is root:
            refresh_tree()

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
    # (a real WSL/bash session), instead of a one-shot subprocess whose
    # output could only be captured after the fact. That means a program
    # asking for input() (or reading stdin generally) actually gets it,
    # the same as running it in a real terminal by hand. The Output panel
    # still gets the plain, un-annotated printed output too - see the
    # start/end marker handling in _term_feed_with_mirror above.
    RUNNERS = {
        "Python": "python3",
        "JavaScript": "node",
        "Shell Script": "bash",
    }

    def run_code():
        editor = get_current_editor()
        if not editor:
            return

        if not terminal_state["alive"]:
            messagebox.showinfo(
                "Run",
                "The terminal isn't running, so there's nowhere to run this. "
                "Open the Terminal tab first."
            )
            return

        if editor["path"]:
            save_editor(editor)
            if editor["dirty"]:
                return  # save was cancelled/failed
            run_path = editor["path"]
        else:
            # Unsaved buffer - drop it next to the shell's own working
            # directory so no Windows<->WSL path translation is needed,
            # then just reference it by filename.
            with tempfile.NamedTemporaryFile(
                mode="w", suffix=".py", dir=os.getcwd(), delete=False
            ) as tmp:
                tmp.write(editor["text"].get("1.0", "end-1c"))
                run_path = tmp.name

        interpreter = RUNNERS.get(get_language_label(run_path))
        if not interpreter:
            messagebox.showinfo(
                "Run", f"Don't know how to run {get_language_label(run_path)} files."
            )
            return

        try:
            rel_path = os.path.relpath(run_path, os.getcwd())
        except ValueError:
            rel_path = run_path  # e.g. different drive on Windows
        shell_path = rel_path.replace(os.sep, "/")

        run_id = uuid.uuid4().hex[:8]
        # "$$" (the shell's own PID) is expanded only when the line actually
        # *runs* - the terminal's local echo of what we typed still shows
        # the literal "$$", so matching for digits here can't confuse the
        # keystroke echo with the real, executed marker.
        run_state["start_marker"] = re.compile(f"RUNSOF_{run_id}P" + r"\d+")
        run_state["end_marker"] = re.compile(f"RUNEOF_{run_id}P" + r"\d+")
        run_state["start_prefix"] = f"RUNSOF_{run_id}P"
        run_state["end_prefix"] = f"RUNEOF_{run_id}P"
        run_state["buffer"] = ""
        run_state["scan_pending"] = ""
        run_state["active"] = False
        run_state["awaiting_start"] = True

        output_area.config(state="normal")
        output_area.delete("1.0", tk.END)
        output_area.insert("1.0", "Running...\n")
        output_area.config(state="disabled")

        focus_terminal()
        _term_print(f"{interpreter} {shell_path}\n")
        command = (
            f"echo RUNSOF_{run_id}P$$; "
            f"{interpreter} {shlex.quote(shell_path)}; "
            f"echo RUNEOF_{run_id}P$$\r"
        )
        _term_send_raw(command)

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
        save_current_session()
        stop_shell()
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

        stop_shell()
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

    file_menu.add_command(label="Exit", command=on_exit)

    root.protocol("WM_DELETE_WINDOW", on_exit)

    edit_menu = tk.Menu(root, tearoff=0, **menu_opts)
    edit_menu.add_command(label="Find...", command=lambda: open_find_replace("find"), accelerator="Ctrl+F")
    edit_menu.add_command(label="Replace...", command=lambda: open_find_replace("replace"), accelerator="Ctrl+H")

    run_menu = tk.Menu(root, tearoff=0, **menu_opts)
    run_menu.add_command(label="Run", command=run_code, accelerator="F5")

    view_menu = tk.Menu(root, tearoff=0, **menu_opts)
    view_menu.add_command(label="Terminal", command=focus_terminal, accelerator="Ctrl+`")
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
    root.bind("<Control-f>", lambda e: open_find_replace("find"))
    root.bind("<Control-h>", lambda e: open_find_replace("replace"))
    root.bind("<Control-grave>", lambda e: focus_terminal())
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