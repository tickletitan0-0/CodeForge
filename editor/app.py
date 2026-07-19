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
import time
import pathlib
import webbrowser
import traceback
import weakref

try:
    # app.py is being imported as part of the "editor" package (e.g. main.py
    # does `from editor import app`) - use a relative import so Python looks
    # for themes.py inside this same package.
    from .themes import (
        THEMES, THEME_LABELS, load_theme_preference, save_theme_preference,
        load_session, save_session,
        load_font_size_preference, save_font_size_preference,
        DEFAULT_FONT_SIZE, MIN_FONT_SIZE, MAX_FONT_SIZE,
        load_font_family_preference, save_font_family_preference,
        DEFAULT_FONT_FAMILY, FONT_FAMILY_CHOICES,
        is_dark_theme, blend_hex,
        load_recent_files, save_recent_files, MAX_RECENT_FILES,
        load_recent_folders, save_recent_folders, MAX_RECENT_FOLDERS,
        load_stats, save_stats
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
        load_font_family_preference, save_font_family_preference,
        DEFAULT_FONT_FAMILY, FONT_FAMILY_CHOICES,
        is_dark_theme, blend_hex,
        load_recent_files, save_recent_files, MAX_RECENT_FILES,
        load_recent_folders, save_recent_folders, MAX_RECENT_FOLDERS,
        load_stats, save_stats
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

try:
    # linters.py is being imported as part of the "editor" package.
    from . import linters
except ImportError:
    # Standalone script - plain import, same fallback pattern as themes
    # above.
    import linters

try:
    # fun_effects.py is being imported as part of the "editor" package.
    from . import fun_effects
except ImportError:
    # Standalone script - plain import, same fallback pattern as themes
    # above.
    import fun_effects

try:
    # code_folding.py is being imported as part of the "editor" package.
    from . import code_folding
except ImportError:
    # Standalone script - plain import, same fallback pattern as themes
    # above.
    import code_folding

try:
    # goto.py is being imported as part of the "editor" package.
    from . import goto
except ImportError:
    # Standalone script - plain import, same fallback pattern as themes
    # above.
    import goto

try:
    # hover_defs.py is being imported as part of the "editor" package.
    from . import hover_defs
except ImportError:
    # Standalone script - plain import, same fallback pattern as themes
    # above.
    import hover_defs


try:
    # plugins.py is being imported as part of the "editor" package.
    from . import plugins
except ImportError:
    # Standalone script - plain import, same fallback pattern as themes
    # above.
    import plugins


def resource_path(filename):
    """Path to a bundled non-Python file (currently just icon.png), that
    works both running from source and as a frozen PyInstaller build.

    Source: files live next to this script.
    Frozen (onedir): PyInstaller's collect step copies datas from the spec
    into the same folder as the exe, and sys._MEIPASS points there - so
    the two cases actually resolve to the same "next to the executable"
    location, this just picks the right base dir for each.
    """
    base_dir = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base_dir, filename)


# ---------------- Theme ----------------
# The palettes themselves now live in themes.py. We just load whichever one
# the user last picked (defaulting to light) so the whole app reads as one
# consistent theme.
THEME_NAME = load_theme_preference()
# A *copy* of THEMES[THEME_NAME], never the same dict object - _apply_theme_live
# below does THEME.clear() + THEME.update(new_theme) to re-theme live, and if
# THEME were an alias of a THEMES[...] entry (as a plain `= THEMES[THEME_NAME]`
# would be), that clear() would corrupt THEMES' own copy of that palette. Once
# corrupted, switching back to that theme name later hands _apply_theme_live a
# `new_theme` that's literally the same (just-cleared) object as THEME itself,
# leaving both empty - which is exactly what caused the KeyError: 'app_bg'
# crash.


class _ThemeColor(str):
    """A color string that also remembers which THEME key produced it.

    Every palette in themes.py deliberately reuses the same hex value for
    several different keys (e.g. DARK_THEME's app_bg/editor_bg/output_bg
    are all "#1e1e1e"; LIGHT_THEME's app_bg and sidebar_bg are both
    "#f3f3f3"). That's harmless for widgets built fresh from THEME[key],
    but it used to break live re-theming (_apply_theme_live), which
    figured out each widget's new color by looking up its *current
    literal color* in a value->value remap - and when several keys
    shared that literal value, only one of them could win the lookup, so
    every widget actually keyed by one of the others silently got
    recolored from the wrong key instead (permanently, since the
    mis-colored widget doesn't visibly match the key it's supposed to be
    tracking, that widget just quietly drifts further every theme
    switch after that).

    Wrapping THEME's values in this subclass and reading `.theme_key`
    off of whatever gets passed into a widget's color options (see
    _install_theme_key_tracking below) lets the retheme code skip that
    guesswork entirely and just re-read THEME[key] directly.
    """
    __slots__ = ("theme_key",)

    def __new__(cls, value, key):
        obj = str.__new__(cls, value)
        obj.theme_key = key
        return obj


class _TrackedTheme(dict):
    """Drop-in replacement for a plain palette dict: behaves exactly like
    one everywhere (THEME.clear()/.update()/dict(THEME)/THEME.items() all
    still see and store plain strings, unchanged from before), except
    THEME["some_key"] hands back an _ThemeColor instead of a bare str, so
    that value carries its own key wherever it flows into a widget option.
    """

    def __getitem__(self, key):
        return _ThemeColor(dict.__getitem__(self, key), key)

    def get(self, key, default=None):
        if key in self:
            return self[key]
        return default


# THEME's values are wrapped in _ThemeColor (via _TrackedTheme) rather
# than plain str, so that live re-theming can track *which key* colored a
# given widget option, instead of re-deriving it from the literal color
# text - see _ThemeColor's docstring above for why that distinction turns
# out to matter.
THEME = _TrackedTheme(THEMES[THEME_NAME])

# Every widget's color options, keyed by THEME key rather than by literal
# color: {widget: {"bg": "output_bg", "fg": "muted_fg", ...}}. Populated
# automatically (see _install_theme_key_tracking) the moment any widget
# is constructed or configured with a value that came from THEME[...] -
# no call site anywhere else in the app needs to change. A
# WeakKeyDictionary so a closed tab's widgets don't linger here forever.
_widget_theme_keys = weakref.WeakKeyDictionary()


def _install_theme_key_tracking():
    """Hooks widget construction and .configure()/.config() so that any
    _ThemeColor passed as bg/fg/etc gets recorded into _widget_theme_keys
    before it's handed off to Tk - which only ever sees/stores a plain
    color string from that point on (Tk has no idea what an _ThemeColor
    is, and doesn't need to). No widget-creation call site anywhere in
    the app, git_panel.py, or music_player.py needs to change for
    tracking to work.

    Deliberately does NOT hook tkinter's shared low-level _options()
    helper, even though that would catch both these paths in one patch -
    Text.tag_configure(), Canvas.itemconfigure(), Menu.entryconfigure(),
    etc. all also funnel through that same helper on that same widget
    object, so a first attempt at this patched _options() directly and
    ended up recording e.g. a Text tag's search_current_bg color as if
    it were the Text *widget's* own bg/fg - which is exactly what made
    the editor start turning orange (search_current_bg's color) instead
    of tracking editor_bg. Hooking the widget-level entry points instead
    keeps tag/item/menu-entry coloring out of this table entirely - it
    was never meant to be covered by it, and doesn't need to be, since
    _apply_theme_live already re-runs the actual tag setup functions
    directly against the new THEME.
    """
    original_widget_init = tk.BaseWidget.__init__
    original_configure = tk.Misc.configure

    def _record(self, *sources):
        for source in sources:
            if not source:
                continue
            for opt, val in source.items():
                key = getattr(val, "theme_key", None)
                if key is None:
                    continue
                opt_name = opt[:-1] if opt.endswith("_") else opt
                _widget_theme_keys.setdefault(self, {})[opt_name] = key

    def _tracking_init(self, master=None, widgetName=None, cnf={}, kw={}, extra=()):
        _record(self, cnf, kw)
        original_widget_init(self, master, widgetName, cnf, kw, extra)

    def _tracking_configure(self, cnf=None, **kw):
        _record(self, cnf, kw)
        return original_configure(self, cnf, **kw)

    tk.BaseWidget.__init__ = _tracking_init
    tk.Misc.configure = _tracking_configure
    tk.Misc.config = _tracking_configure


_install_theme_key_tracking()


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

# ---- C-like languages (Java, JavaScript) ----
_C_LIKE_KEYWORDS = {
    # Shared / control flow
    "break", "case", "const", "continue", "default", "do", "else", "enum",
    "for", "if", "int", "long", "return", "short", "static", "switch",
    "void", "while", "class", "public", "private", "protected", "virtual",
    "override", "try", "catch", "throw",
    # Java
    "package", "import", "interface", "implements", "extends", "final",
    "abstract", "synchronized", "native", "transient", "throws",
    "instanceof", "super", "boolean", "byte", "char", "double", "float",
    "volatile",
    # JavaScript
    "function", "var", "let", "export", "from", "as",
    "async", "await", "yield", "of", "in", "typeof", "delete", "new",
    "this", "null", "undefined", "true", "false", "get", "set",
}
_C_LIKE_KEYWORD_RE = re.compile(r'\b(' + '|'.join(sorted(_C_LIKE_KEYWORDS)) + r')\b')
_C_LIKE_STRING_RE = re.compile(
    r'("(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'|`(?:\\.|[^`\\])*`)'
)
_C_LIKE_COMMENT_RE = re.compile(r'//.*|/\*[\s\S]*?\*/')
_C_LIKE_NUMBER_RE = re.compile(r'\b0[xX][0-9a-fA-F]+\b|\b\d+\.?\d*[fFlLuU]?\b')

# ---- HTML ----
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
    "plaintext": {},
}

_EXT_TO_SYNTAX_PROFILE = {
    ".py": "python", ".pyw": "python",
    ".js": "c_like",
    ".java": "c_like",
    ".html": "html", ".htm": "html",
    ".css": "css",
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


def _offset_to_index_in_window(offset, starts, window_start_line):
    """Same as _offset_to_index, but for a regex match found in a
    *windowed* substring (some padded range of lines, not the whole
    document) - shifts the resulting line number back to the real
    document line the window started at."""
    idx = _offset_to_index(offset, starts)
    line_str, col_str = idx.split(".", 1)
    return f"{int(line_str) + window_start_line - 1}.{col_str}"


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


def _build_color_remap(old_theme, new_theme):
    """Maps every literal color value in `old_theme` to whatever the
    corresponding key holds in `new_theme` - e.g. old editor_bg's hex ->
    new editor_bg's hex. This is now only a *fallback* for widgets
    _remap_widget_colors couldn't identify a THEME key for (see there) -
    the palettes routinely reuse the same hex for several different keys
    (DARK_THEME's app_bg/editor_bg/output_bg are all "#1e1e1e", for
    instance), so two different keys can easily share the same old color
    here, and only one of them can win a plain value->value lookup. That
    ambiguity used to be the *only* mechanism re-theming had, which is
    what caused colors to silently drift to the wrong key's value on
    every switch; now it's a rare fallback rather than the main path, so
    the ambiguity mostly just doesn't come up in practice.
    """
    remap = {}
    for key, old_val in old_theme.items():
        new_val = new_theme.get(key)
        if new_val is None or new_val == old_val:
            continue
        remap.setdefault(old_val, new_val)
    return remap


# Every widget option name (across plain tk widgets - ttk widgets are
# themed through ttk.Style instead, and don't respond to these) that ever
# holds one of THEME's literal color values anywhere in this app. bg/
# background and fg/foreground are true Tk aliases for the same
# underlying option (not two independent ones), so they're grouped here
# rather than listed separately - see _remap_widget_colors for why that
# distinction matters.
_THEMEABLE_COLOR_OPTION_GROUPS = (
    ("bg", "background"),
    ("fg", "foreground"),
    ("highlightbackground",),
    ("highlightcolor",),
    ("insertbackground",),
    ("selectbackground",),
    ("selectforeground",),
    ("activebackground",),
    ("activeforeground",),
    ("disabledforeground",),
    ("readonlybackground",),
    ("troughcolor",),
)


def _remap_widget_colors(widget, remap):
    """Recursively walks `widget` and every descendant, updating any
    color option that was ever set from THEME. For each option, this
    tries two things in order:

      1. Key-based (exact): if _widget_theme_keys recorded which THEME
         key colored this option (see _install_theme_key_tracking), just
         re-read THEME[key] directly. Immune to the "two keys share the
         same hex" collisions the old value-based approach couldn't
         resolve - this is the actual fix for colors drifting/becoming
         inconsistent across repeated theme switches.
      2. Literal-value fallback: for anything not built while tracking
         was active (in practice this shouldn't happen for this app's
         own widgets, since tracking is installed before any UI is
         built, but it's a safe net for e.g. third-party widget code),
         fall back to the old best-effort remap-by-current-color.

    bg/background and fg/foreground are resolved once per group rather
    than as independent options: a widget built with `bg=THEME["x"]` is
    only ever tracked under the name "bg", so treating "background" as a
    separate option would miss the tracked key, fall back to the
    collision-prone value guess for it instead, and then silently
    clobber the correct "bg" update with a wrong "background" one when
    both land in the same final configure() call (they're the same
    underlying Tk option, so whichever gets applied last wins).

    Safe to call on anything - ttk widgets and any option a given widget
    class doesn't support both just raise TclError, which is caught and
    skipped rather than needing a widget-type allowlist."""
    try:
        supported = widget.configure()
    except tk.TclError:
        supported = None

    if supported:
        updates = {}
        tracked = _widget_theme_keys.get(widget)
        for group in _THEMEABLE_COLOR_OPTION_GROUPS:
            present = [o for o in group if o in supported]
            if not present:
                continue

            tracked_key = None
            if tracked:
                for alias in group:
                    if alias in tracked:
                        tracked_key = tracked[alias]
                        break

            opt = present[0]
            if tracked_key is not None and tracked_key in THEME:
                new_value = THEME[tracked_key]
                try:
                    current_value = str(widget.cget(opt))
                except tk.TclError:
                    current_value = None
                if current_value != new_value:
                    updates[opt] = new_value
                continue

            try:
                current_value = widget.cget(opt)
            except tk.TclError:
                continue
            # Tkinter sometimes hands back a _tkinter.Tcl_Obj instead of a
            # plain str for a given widget/option combo (e.g. some ttk-
            # adjacent widgets, or platform-specific color reprs) - and
            # that Tcl_Obj isn't guaranteed hashable, which made this dict
            # lookup itself raise ("unhashable type: '_tkinter.Tcl_Obj'")
            # rather than just failing to match anything. THEME's own
            # values (and therefore remap's keys) are always plain str,
            # so coercing here is exactly what's needed to compare like
            # with like - and str() is always hashable, unlike Tcl_Obj.
            try:
                current_value = str(current_value)
            except Exception:
                continue
            new_value = remap.get(current_value)
            if new_value is not None:
                updates[opt] = new_value
        if updates:
            try:
                widget.configure(**updates)
            except tk.TclError:
                pass

    try:
        children = widget.winfo_children()
    except tk.TclError:
        return
    for child in children:
        _remap_widget_colors(child, remap)


# Rendered as the Start Page's title in place of a plain "CodeForge" label -
# a monospace figlet-style banner, drawn with Courier New at a small enough
# size that its fixed-width alignment survives (see _populate_start_page).
_STARTUP_BANNER = r"""
      _____           _____         _____        ______         _____         _____         _____         _____         ______   
  ___|\    \     ____|\    \    ___|\    \   ___|\     \   ____|\    \   ____|\    \    ___|\    \    ___|\    \    ___|\     \  
 /    /\    \   /     /\    \  |    |\    \ |     \     \ |    | \    \ /     /\    \  |    |\    \  /    /\    \  |     \     \ 
|    |  |    | /     /  \    \ |    | |    ||     ,_____/||    |______//     /  \    \ |    | |    ||    |  |____| |     ,_____/|
|    |  |____||     |    |    ||    | |    ||     \--'\_|/|    |----'\|     |    |    ||    |/____/ |    |    ____ |     \--'\_|/
|    |   ____ |     |    |    ||    | |    ||     /___/|  |    |_____/|     |    |    ||    |\    \ |    |   |    ||     /___/|  
|    |  |    ||\     \  /    /||    | |    ||     \____|\ |    |      |\     \  /    /||    | |    ||    |   |_,  ||     \____|\ 
|\ ___\/    /|| \_____\/____/ ||____|/____/||____ '     /||____|      | \_____\/____/ ||____| |____||\ ___\___/  /||____ '     /|
| |   /____/ | \ |    ||    | /|    /    | ||    /_____/ ||    |       \ |    ||    | /|    | |    || |   /____ / ||    /_____/ |
 \|___|    | /  \|____||____|/ |____|____|/ |____|     | /|____|        \|____||____|/ |____| |____| \|___|    | / |____|     | /
   \( |____|/      \(    )/      \(    )/     \( |_____|/   )/             \(    )/      \(     )/     \( |____|/    \( |_____|/ 
    '   )/          '    '        '    '       '    )/      '               '    '        '     '       '   )/        '    )/    
        '                                           '                                                       '              '
"""


def run():
    _apply_windows_dpi_awareness()

    root = tkinterdnd2.TkinterDnD.Tk() if tkinterdnd2 else tk.Tk()
    root.title("CodeForge")

    # Window/taskbar icon. Wrapped in try/except since a missing or
    # corrupt icon.png shouldn't be able to stop the app from starting -
    # worst case you just get Tk's default feather icon instead.
    try:
        _icon_img = tk.PhotoImage(file=resource_path("icon.png"))
        root.iconphoto(True, _icon_img)
        # Keep a reference somewhere that outlives this function's locals
        # so Tk doesn't garbage-collect the image out from under itself.
        root._icon_img_ref = _icon_img
    except (tk.TclError, FileNotFoundError):
        pass

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

    def _apply_ttk_styles():
        """(Re-)applies every ttk.Style rule this app uses, reading
        current THEME values. Split out from initial setup so a live
        theme switch can just call this again instead of duplicating the
        whole block - ttk widgets take their colors from named styles
        rather than per-instance options, so they need this rather than
        the plain-widget value-remap _remap_widget_colors does."""
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

        # Used by the Settings dialog's font/theme dropdowns.
        style.configure(
            "Settings.TCombobox",
            fieldbackground=THEME["popup_bg"],
            background=THEME["panel_header_bg"],
            foreground=THEME["popup_fg"],
            arrowcolor=THEME["panel_header_fg"],
            bordercolor=THEME["border"],
            lightcolor=THEME["popup_bg"],
            darkcolor=THEME["popup_bg"],
            selectbackground=THEME["popup_bg"],
            selectforeground=THEME["popup_fg"],
            insertcolor=THEME["editor_insert"],
            padding=4,
        )
        style.map(
            "Settings.TCombobox",
            fieldbackground=[("readonly", THEME["popup_bg"])],
            foreground=[("readonly", THEME["popup_fg"])],
            selectbackground=[("readonly", THEME["popup_bg"])],
            selectforeground=[("readonly", THEME["popup_fg"])],
        )
        root.option_add("*TCombobox*Listbox.background", THEME["popup_bg"])
        root.option_add("*TCombobox*Listbox.foreground", THEME["popup_fg"])
        root.option_add("*TCombobox*Listbox.selectBackground", THEME["popup_select_bg"])
        root.option_add("*TCombobox*Listbox.selectForeground", THEME["popup_select_fg"])

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
        #
        # The three PhotoImage objects are created exactly once and kept
        # alive on the style object (ttk holds element images by name only,
        # so losing the last Python reference lets Tk garbage-collect the
        # pixel data even though the name is still registered). A live
        # theme switch redraws new colors onto these same objects rather
        # than creating fresh ones - the ttk element bound "EditorTab.close"
        # to these specific image names at creation time and doesn't support
        # being pointed at different images later, but it *does* pick up
        # new pixels drawn onto the image it's already showing.
        def _draw_close_icon(img, color, size=12):
            img.blank()
            inset = 3
            for i in range(inset, size - inset):
                img.put(color, (i, i))
                img.put(color, (i, i + 1))
                img.put(color, (size - 1 - i, i))
                img.put(color, (size - 1 - i, i + 1))

        existing_icons = getattr(style, "_close_tab_icons", None)
        if existing_icons is None:
            icon_normal = tk.PhotoImage(width=12, height=12)
            icon_active = tk.PhotoImage(width=12, height=12)
            icon_pressed = tk.PhotoImage(width=12, height=12)
            style._close_tab_icons = (icon_normal, icon_active, icon_pressed)
        else:
            icon_normal, icon_active, icon_pressed = existing_icons

        _draw_close_icon(icon_normal, THEME["muted_fg"])
        _draw_close_icon(icon_active, THEME["panel_header_fg"])
        _draw_close_icon(icon_pressed, THEME["panel_header_fg"])

        # element_create raises if an element of this name already exists
        # (true on every call after the first, e.g. a live theme switch) -
        # harmless to skip, since the element already points at the same
        # image objects whose pixels were just redrawn above.
        if "EditorTab.close" not in style.element_names():
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
            padding=(16, 9, 12, 9),
            font=("Segoe UI", 10),
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
            darkcolor=[("selected", THEME["editor_bg"])],
            # clam's built-in Tab element shrinks the padding on
            # non-selected tabs (and by extension makes the selected one
            # look bigger/smaller relative to it depending on platform) -
            # pin padding to the same fixed size in every state so the
            # bigger tab size above always holds, regardless of selection.
            padding=[("selected", (16, 9, 12, 9)), ("!selected", (16, 9, 12, 9))],
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

    _apply_ttk_styles()

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
        "border": THEME["popup_border"],
        "relief": "flat",
        "borderwidth": 0,
        "activeborderwidth": 0,
    }

    # ---------------- Themed dropdown menus ----------------
    # Even with borderwidth/relief above zeroed out, a real tk.Menu popup on
    # Windows still shows a thick light outline around the whole dropdown -
    # that ring is the OS's own popup-window chrome, not anything Tk paints,
    # and (confirmed the hard way) Menu doesn't support highlightthickness/
    # highlightbackground the way most widgets do, so there's no widget
    # option that reaches it.
    #
    # This gives dropdown menus the same treatment already used for the menu
    # STRIP (custom Menubuttons instead of native chrome) and the
    # autocomplete popup (a plain Toplevel(overrideredirect=True) holding a
    # Frame with our own highlightthickness/highlightbackground border): a
    # window with zero OS-drawn chrome at all, so the border is entirely
    # ours to color. Only the slice of tk.Menu's API actually used elsewhere
    # in this file is implemented: add_command/add_separator/add_cascade,
    # entryconfig (label/state), index(END), delete(0, END), and
    # popup/tk_popup/grab_release.
    class ThemedMenu:
        _open_stack = []  # every currently-open ThemedMenu, root first
        _all_instances = []  # every ThemedMenu ever created, for live retheme

        def __init__(self, master, tearoff=0, **opts):
            self.master = master
            self.opts = opts
            self.items = []
            self.toplevel = None
            self.row_widgets = []
            self._child = None
            ThemedMenu._all_instances.append(self)

        @classmethod
        def retheme_all(cls, new_opts):
            """Updates every ThemedMenu's own color options in place to
            `new_opts` - each instance got its own copy of menu_opts via
            **opts in __init__ rather than a shared reference, so a live
            theme switch has to reach every instance individually rather
            than just updating menu_opts itself. Safe to call while a menu
            is open: popup() reads self.opts fresh each time it (re)draws
            a menu, so an open menu just needs closing/reopening to show
            the new colors, which close_all() elsewhere already handles."""
            for instance in cls._all_instances:
                instance.opts.update(new_opts)

        def add_command(self, label="", command=None, accelerator="", state="normal"):
            self.items.append({
                "type": "command", "label": label, "command": command,
                "accelerator": accelerator, "state": state,
            })

        def add_separator(self):
            self.items.append({"type": "separator"})

        def add_cascade(self, label="", menu=None):
            self.items.append({"type": "cascade", "label": label, "menu": menu, "state": "normal"})

        def delete(self, start, end=None):
            self.items = []

        def index(self, _end):
            return len(self.items) - 1

        def entryconfig(self, idx, label=None, state=None):
            item = self.items[idx]
            if label is not None:
                item["label"] = label
            if state is not None:
                item["state"] = state
            if idx < len(self.row_widgets) and self.row_widgets[idx][0] is not None:
                lbl = self.row_widgets[idx][0]
                if label is not None:
                    lbl.config(text=self._display_text(item))
                self._style_row(lbl, item)

        def grab_release(self):
            # No-op - kept so call sites that mirror the old
            # tk_popup(...) + grab_release() pattern don't need to change.
            pass

        def tk_popup(self, x, y):
            self.popup(x, y)

        def close(self):
            if self._child is not None:
                self._child.close()
                self._child = None
            if self.toplevel is not None:
                try:
                    self.toplevel.destroy()
                except tk.TclError:
                    pass
                self.toplevel = None
                self.row_widgets = []
            if self in ThemedMenu._open_stack:
                ThemedMenu._open_stack.remove(self)

        @classmethod
        def close_all(cls):
            for m in list(cls._open_stack):
                m.close()
            cls._open_stack.clear()

        def _display_text(self, item):
            text = item["label"]
            if item.get("accelerator"):
                text = text + ("  " * 3) + item["accelerator"]
            return text

        def _style_row(self, lbl, item, active=False):
            if item.get("state") == "disabled":
                lbl.config(bg=self.opts["bg"], fg=self.opts.get("disabledforeground", "#888888"))
            elif active:
                lbl.config(bg=self.opts["activebackground"], fg=self.opts["activeforeground"])
            else:
                lbl.config(bg=self.opts["bg"], fg=self.opts["fg"])

        def popup(self, x, y, _root_menu=True):
            if _root_menu:
                ThemedMenu.close_all()
            self.close()

            border_color = self.opts.get("border", self.opts["bg"])
            top = tk.Toplevel(self.master)
            top.wm_overrideredirect(True)
            try:
                top.attributes("-topmost", True)
            except tk.TclError:
                pass

            frame = tk.Frame(
                top, bg=self.opts["bg"], bd=0,
                highlightthickness=1, highlightbackground=border_color, highlightcolor=border_color,
            )
            frame.pack()

            self.row_widgets = []
            self._child = None

            for item in self.items:
                if item["type"] == "separator":
                    sep = tk.Frame(frame, bg=border_color, height=1)
                    sep.pack(fill="x", padx=6, pady=3)
                    self.row_widgets.append((None, sep))
                    continue

                lbl = tk.Label(
                    frame, text=self._display_text(item), anchor="w",
                    bg=self.opts["bg"], padx=14, pady=4, cursor="hand2",
                )
                self._style_row(lbl, item)
                lbl.pack(fill="x")
                self.row_widgets.append((lbl, lbl))

                if item.get("state") == "disabled":
                    continue

                def on_enter(e, i=item, l=lbl):
                    self._style_row(l, i, active=True)

                def on_leave(e, i=item, l=lbl):
                    self._style_row(l, i, active=False)

                lbl.bind("<Enter>", on_enter)
                lbl.bind("<Leave>", on_leave)

                if item["type"] == "command":
                    def on_click(e, it=item):
                        cmd = it.get("command")
                        ThemedMenu.close_all()
                        if cmd:
                            cmd()
                        return "break"
                    lbl.bind("<Button-1>", on_click)
                elif item["type"] == "cascade":
                    def on_click(e, it=item, l=lbl):
                        self._open_cascade(it, l)
                        return "break"
                    lbl.bind("<Button-1>", on_click)

            top.update_idletasks()
            w, h = top.winfo_reqwidth(), top.winfo_reqheight()
            sw, sh = top.winfo_screenwidth(), top.winfo_screenheight()
            if x + w > sw:
                x = max(0, sw - w)
            if y + h > sh:
                y = max(0, sh - h)
            top.wm_geometry(f"+{x}+{y}")

            self.toplevel = top
            ThemedMenu._open_stack.append(self)
            top.bind("<Escape>", lambda e: ThemedMenu.close_all())

        def _open_cascade(self, item, label_widget):
            submenu = item.get("menu")
            if submenu is None:
                return
            if self._child is not None:
                self._child.close()
            x = label_widget.winfo_rootx() + label_widget.winfo_width()
            y = label_widget.winfo_rooty()
            submenu.popup(x, y, _root_menu=False)
            self._child = submenu

    def _themed_menu_dismiss(event):
        # A single app-wide click watcher rather than a per-menu grab, so
        # hovering back and forth between a cascade (Open Recent, Theme) and
        # its parent doesn't fight over an exclusive grab. Clicking anywhere
        # that isn't inside one of the currently-open menu windows closes
        # all of them.
        if not ThemedMenu._open_stack:
            return
        try:
            clicked_top = event.widget.winfo_toplevel()
        except tk.TclError:
            clicked_top = None
        for m in ThemedMenu._open_stack:
            if m.toplevel is not None and clicked_top is m.toplevel:
                return
        ThemedMenu.close_all()

    root.bind_all("<Button-1>", _themed_menu_dismiss, add="+")

    # ---------------- Custom menu bar ----------------
    # A native tk.Menu's top-level STRIP is drawn by the OS on Windows and
    # ignores bg/fg entirely (only the dropdowns that open from it respect
    # theme colors) - that's what left the "File Edit Run View" row stuck
    # white even in dark mode. Building the strip ourselves out of themed
    # Menubuttons (each still posting a themed ThemedMenu dropdown) fixes
    # that completely. It's packed here, before the status bar/main pane, so
    # it claims the top strip; the actual Menubuttons/dropdowns are filled
    # in near the end of run() once their commands (new_file, save_file,
    # etc.) exist.
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

    # Squiggly-line diagnostic summary for whichever tab is active - kept
    # in sync by update_lint_status_label(), called from the same places
    # (re-lint completing, tab switch) that update the squiggles themselves.
    status_lint_label = tk.Label(
        status_bar,
        text="",
        bg=THEME["panel_header_bg"],
        fg=THEME["muted_fg"],
        anchor="w",
        padx=10
    )
    status_lint_label.pack(side="left")

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

    # A generic, transient "flash a message for a few seconds" slot - used
    # by the plugin API's show_message() below, kept separate from the
    # other status labels (each of which mirrors some persistent bit of
    # state) since this one is meant to appear and then clear itself.
    status_message_label = tk.Label(
        status_bar,
        text="",
        bg=THEME["panel_header_bg"],
        fg=THEME["accent"],
        anchor="w",
        padx=10
    )
    status_message_label.pack(side="left")

    status_focus_label = tk.Label(
        status_bar,
        text="",
        bg=THEME["panel_header_bg"],
        fg=THEME["accent"],
        anchor="w",
        padx=10
    )
    status_focus_label.pack(side="left")

    # Live "time spent coding this session" - ticks up on its own further
    # down once the rest of run() (root, after()) exists; clicking it
    # jumps to the Stats tab for the full picture (all-time totals, commit
    # counts) instead of cramming all of that into the status bar itself.
    status_timer_label = tk.Label(
        status_bar,
        text="\u23F1 0m",
        bg=THEME["panel_header_bg"],
        fg=THEME["panel_header_fg"],
        anchor="w",
        padx=10,
        cursor="hand2"
    )
    status_timer_label.pack(side="left")

    # Little "you've been typing for a while" flame - purely cosmetic,
    # session-only (see fun_effects.StreakTracker), updated from
    # on_key_release below and ticked down on its own by _streak_tick.
    status_streak_label = tk.Label(
        status_bar,
        text="",
        bg=THEME["panel_header_bg"],
        fg=THEME["accent"],
        anchor="w",
        padx=6
    )
    status_streak_label.pack(side="left")

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
        ".html": "HTML",
        ".htm": "HTML",
        ".css": "CSS",
        ".java": "Java",
        ".txt": "Plain Text",
    }

    def get_language_label(path):
        if not path:
            return "Plain Text"
        _, ext = os.path.splitext(path)
        return LANGUAGE_LABELS.get(ext.lower(), "Plain Text")

    # ---------- Comment/uncomment ----------
    # Same "supported languages only" scope as linters.py/goto.py - an
    # unrecognized extension (or a path-less unsaved buffer) just means
    # Ctrl+/ does nothing, rather than guessing at a comment syntax that
    # might be wrong. Python/JS/Java get a real per-line "//"/"#" toggle;
    # CSS and HTML don't have a line-comment syntax at all, so they get a
    # single block wrapped around the whole selection instead.
    COMMENT_STYLES = {
        ".py":   {"line": "#"},
        ".pyw":  {"line": "#"},
        ".js":   {"line": "//"},
        ".java": {"line": "//"},
        ".css":  {"block": ("/*", "*/")},
        ".html": {"block": ("<!--", "-->")},
        ".htm":  {"block": ("<!--", "-->")},
    }

    def _comment_style_for_path(path):
        if not path:
            return None
        _, ext = os.path.splitext(path)
        return COMMENT_STYLES.get(ext.lower())

    # ---------- Explorer: filetype/folder icons ----------
    # Small flat glyphs drawn pixel-by-pixel (tk.PhotoImage.put), the same
    # technique _make_close_icon uses for the tab close button - no image
    # assets, no new dependencies, just Tk. Colors are fixed (not pulled
    # from THEME) and loosely follow the color coding most editors/GitHub
    # already use for these languages, so they read the same regardless
    # of which app theme is active.
    _FILETYPE_ICON_COLORS = {
        # Python gets its own two-tone body (blue over yellow) below,
        # rather than one flat color, echoing the language's own logo.
        ".py": ("#4b8bbe", "#ffd43b"),
        ".pyw": ("#4b8bbe", "#ffd43b"),
        ".js": "#f0db4f",
        ".html": "#e34c26",
        ".htm": "#e34c26",
        ".css": "#1572b6",
        ".java": "#ea2d2e",
        ".txt": "#9da5b4",
    }
    _FILETYPE_ICON_FALLBACK = "#9da5b4"
    _FOLDER_ICON_COLOR = "#dcb67a"

    def _lighten_hex(color, factor):
        color = color.lstrip("#")
        r, g, b = int(color[0:2], 16), int(color[2:4], 16), int(color[4:6], 16)
        r = int(r + (255 - r) * factor)
        g = int(g + (255 - g) * factor)
        b = int(b + (255 - b) * factor)
        return f"#{r:02x}{g:02x}{b:02x}"

    def _make_file_icon(color, size=14):
        """A plain document silhouette with a lightened notch in the top-
        right corner standing in for a folded page corner. `color` is
        either one hex string, or a (top, bottom) pair for a two-tone
        body like Python's icon - everything else about the shape stays
        the same either way."""
        img = tk.PhotoImage(width=size, height=size)
        x0, y0, x1, y1 = 2, 1, size - 2, size - 2
        mid = (y0 + y1) // 2
        top_color, bottom_color = color if isinstance(color, tuple) else (color, color)
        for y in range(y0, y1):
            row_color = top_color if y < mid else bottom_color
            for x in range(x0, x1):
                img.put(row_color, (x, y))
        corner = 3
        light = _lighten_hex(top_color, 0.4)
        for y in range(y0, y0 + corner):
            for x in range(x1 - corner, x1):
                img.put(light, (x, y))
        return img

    def _make_folder_icon(color, size=14):
        """A tab-topped folder silhouette (small raised tab over a wider
        body) - a distinct shape from the file icon's plain rectangle so
        folders and files are tellable apart at a glance even before
        reading the label."""
        img = tk.PhotoImage(width=size, height=size)
        for y in range(2, 4):
            for x in range(2, 8):
                img.put(color, (x, y))
        for y in range(4, size - 2):
            for x in range(2, size - 2):
                img.put(color, (x, y))
        return img

    def _build_filetype_icons():
        folder_icon = _make_folder_icon(_FOLDER_ICON_COLOR)
        generic_icon = _make_file_icon(_FILETYPE_ICON_FALLBACK)
        file_icons = {
            ext: _make_file_icon(color)
            for ext, color in _FILETYPE_ICON_COLORS.items()
        }
        return folder_icon, file_icons, generic_icon

    FOLDER_ICON, FILE_ICONS, GENERIC_FILE_ICON = _build_filetype_icons()

    def tree_icon_for(path, is_dir):
        if is_dir:
            return FOLDER_ICON
        _, ext = os.path.splitext(path)
        return FILE_ICONS.get(ext.lower(), GENERIC_FILE_ICON)

    _status_message_state = {"job": None}

    def show_status_message(text, duration_ms=4000):
        """Flashes `text` in the status bar's message slot for
        `duration_ms`, then clears it - used by the plugin API's
        show_message() (see PluginAPI/register below). Safe to call
        again before a previous message's timer has fired: it cancels
        the pending clear and restarts the clock, the same "latest call
        wins" pattern used for every other debounced timer in this file
        (highlight_job, resize_job, etc.), so a burst of messages just
        shows the last one for the full duration instead of flickering."""
        pending = _status_message_state["job"]
        if pending is not None:
            try:
                root.after_cancel(pending)
            except (ValueError, tk.TclError):
                pass
        status_message_label.config(text=text)

        def clear():
            _status_message_state["job"] = None
            try:
                status_message_label.config(text="")
            except tk.TclError:
                pass

        _status_message_state["job"] = root.after(duration_ms, clear)

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
        bg=THEME["app_bg"],
        opaqueresize=False,
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

    def _apply_project_tree_theme():
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

    _apply_project_tree_theme()

    main_frame.add(explorer_frame, width=220, minsize=120, stretch="never")

    center_frame = tk.Frame(main_frame, bg=THEME["app_bg"], highlightthickness=0, bd=0)
    main_frame.add(center_frame, minsize=300, stretch="always")

    tab_control = ttk.Notebook(center_frame, style="EditorTabs.TNotebook")
    tab_control.pack(fill="both", expand=True)

    # Shown instead of tab_control whenever there are zero tabs open (a
    # fresh window, "File > New Window", or the last tab just got closed) -
    # see _show_start_page/_hide_start_page further down, defined once the
    # actions/recent-lists it links to all exist. Built here, empty and
    # unpacked, so it's a permanent child of center_frame from the start -
    # that keeps it in the same widget subtree _remap_widget_colors already
    # walks on every theme switch, with no separate re-theming path needed.
    start_page_frame = tk.Frame(center_frame, bg=THEME["editor_bg"], highlightthickness=0, bd=0)

    # ---------- Sliding tab-bottom indicator ----------
    # A thin accent-colored bar that glides to the selected tab instead of
    # the selection just jumping there (VS Code / browser-tab style). Kept
    # as a plain Canvas floated on top of the notebook via place() - ttk
    # doesn't expose the tab strip as its own widget to pack something
    # below, but placing a child directly on the Notebook and positioning
    # it in pixel coordinates works the same way a floating scrollbar would.
    tab_indicator = tk.Canvas(
        tab_control, height=3, highlightthickness=0, bd=0, bg=THEME["editor_bg"]
    )
    tab_indicator_bar = tab_indicator.create_rectangle(
        0, 0, 0, 3, fill=THEME["accent"], width=0
    )
    tab_indicator_state = {"anim_job": None}

    def _tab_strip_bottom_y():
        tabs = tab_control.tabs()
        if not tabs:
            return None
        try:
            bbox = tab_control.bbox(tabs[0])
        except tk.TclError:
            return None
        if not bbox:
            return None
        _, y, _, h = bbox
        return y + h

    def _animate_tab_indicator(target_x, target_w, duration_ms=140):
        pending = tab_indicator_state["anim_job"]
        if pending is not None:
            tab_indicator.after_cancel(pending)
            tab_indicator_state["anim_job"] = None

        x1, _, x2, _ = tab_indicator.coords(tab_indicator_bar)
        start_x, start_w = x1, x2 - x1
        steps = max(1, duration_ms // 16)
        progress = {"i": 0}

        def step():
            progress["i"] += 1
            t = min(1.0, progress["i"] / steps)
            eased = 1 - (1 - t) ** 3  # ease-out cubic - quick start, soft landing
            cur_x = start_x + (target_x - start_x) * eased
            cur_w = start_w + (target_w - start_w) * eased
            tab_indicator.coords(tab_indicator_bar, cur_x, 0, cur_x + cur_w, 3)
            if t < 1.0:
                tab_indicator_state["anim_job"] = tab_indicator.after(16, step)
            else:
                tab_indicator_state["anim_job"] = None

        step()

    def update_tab_indicator(animate=True):
        bottom_y = _tab_strip_bottom_y()
        if bottom_y is None:
            tab_indicator.place_forget()
            return
        # y is the bottom edge of the tab strip / top edge of the editor
        # content (line-number gutter, fold gutter, text). The indicator
        # bar itself needs to stay *above* that line - not start there and
        # extend downward into it - so its top is offset up by its own
        # height, leaving its bottom edge flush with the boundary instead
        # of painting over the top few pixels of the gutter/content below.
        indicator_height = 3
        tab_indicator.place(x=0, y=bottom_y - indicator_height, relwidth=1.0, height=indicator_height)
        # Every editor tab frame is added as a sibling *after* this canvas,
        # which would otherwise draw on top of it (later-added siblings win
        # the stacking order), so it needs raising above whichever tab frame
        # is currently showing. Canvas overrides *both* .lift() and
        # .tkraise() as aliases for its own tag_raise() (a canvas-item op
        # that expects a tag/id argument, not widget-stacking) - so neither
        # Python method can be used here. Call Tcl's `raise` directly on
        # the widget path instead, bypassing the shadowed methods entirely.
        tab_indicator.tk.call("raise", tab_indicator._w)

        current_tab = tab_control.select()
        if not current_tab:
            return
        try:
            x, _, w, _ = tab_control.bbox(current_tab)
        except tk.TclError:
            return

        if animate:
            _animate_tab_indicator(x, w)
        else:
            tab_indicator.coords(tab_indicator_bar, x, 0, x + w, 3)

    # Covers window resize/first mapping - individual tab positions don't
    # shift on resize (tabs are label-sized, not stretched), but the strip's
    # bottom y isn't known correctly until the notebook is actually mapped.
    tab_control.bind("<Configure>", lambda e: update_tab_indicator(animate=False), add="+")

    project_path = None
    tab_editors = {}       # tab widget name (str) -> editor dict
    untitled_count = [0]   # counter used to name new blank tabs

    # Editor font size/family - shared across all tabs (like most editors'
    # zoom), persisted so it's restored on next launch. Kept in a dict rather
    # than bare variables so nested functions can mutate them without
    # `nonlocal`.
    font_state = {
        "size": load_font_size_preference(),
        "family": load_font_family_preference(),
    }

    def current_editor_font():
        return (font_state["family"], font_state["size"])

    # Recently-opened files, most-recent first - persisted so "Open Recent"
    # survives a restart. Kept in a dict (like font_state) so nested
    # functions can mutate the list without `nonlocal`.
    recent_files_state = {"paths": load_recent_files()}
    recent_folders_state = {"paths": load_recent_folders()}

    # Minimap - a zoomed-out overview of the whole file for quick
    # navigation, shared on/off state so new tabs match whatever the user
    # last chose.
    MINIMAP_WIDTH = 100
    minimap_state = {"visible": True}

    # Word wrap defaults off (matches the wrap="none" every tab used to be
    # hard-coded to) - toggling it applies to every open tab/pane at once,
    # the same "one setting, all tabs" pattern font size/theme already use.
    word_wrap_state = {"enabled": False}
    # Every row in the minimap is always this many pixels tall, in every
    # file, regardless of file size - rows never stretch or shrink to fill
    # the panel. The strip never scrolls either: once a file has more
    # lines than fit at this fixed height, extra lines are bucketed
    # together into the same row count instead (see render_minimap_content),
    # so the whole file is always visible, just more heavily summarized for
    # a longer file. MINIMAP_MAX_ROWS is only a sanity cap for extreme
    # files (tens of thousands of lines) so one redraw doesn't have to
    # create more canvas rectangles than that.
    MINIMAP_ROW_HEIGHT = 3
    MINIMAP_MAX_ROWS = 20000

    # Minimap git-heatmap - a thin strip along the minimap's right edge
    # marking rows that contain lines added/modified since HEAD (or, for
    # an untracked file, the whole thing). Shares the same on/off-toggle
    # pattern as minimap_state. The actual `git diff` subprocess call is
    # too slow to run on every keystroke, so it's only ever done by
    # refresh_minimap_heat() (save/commit/tab-switch triggered, threaded)
    # - render_minimap_content() just paints whatever's cached in each
    # editor's "git_heat" entry, which means the heatmap reflects the
    # last-saved contents vs HEAD rather than unsaved in-buffer edits.
    MINIMAP_HEAT_WIDTH = 4
    git_heatmap_state = {"visible": True}

    # CRT Scanlines - off by default so it doesn't surprise anyone who
    # just picks the CRT theme for the colors. Shared across tabs like
    # minimap_state, for the same reason (new tabs need to match whatever
    # was last chosen).
    crt_state = {"scanlines": False}

    # ---------------- Session timer / usage stats ----------------
    # session_stats tracks *this run* (elapsed time, commits made this
    # session); the cumulative all-time totals live on disk via
    # load_stats/save_stats and get flushed periodically below rather than
    # only on a clean exit, so a crash or the theme-switch relaunch
    # (root.destroy() + os.execv) doesn't lose whatever hasn't been saved.
    session_stats = {
        "start": time.time(),
        "last_flush": time.time(),
        "commits": 0,
    }

    # Purely cosmetic typing-streak flame (see fun_effects.StreakTracker) -
    # updated eagerly on every keystroke from on_key_release, and ticked
    # here so it also clears itself a few seconds after typing stops
    # rather than waiting for the next keystroke that never comes.
    streak_tracker = fun_effects.StreakTracker()

    def _streak_tick():
        status_streak_label.config(text=streak_tracker.display())
        root.after(1000, _streak_tick)

    root.after(1000, _streak_tick)

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

    music_controls = {}
    music_panel_state = {"built": False}

    def _ensure_music_panel_built():
        # Actually constructing the panel is what triggers music_player's
        # lazy yt-dlp/vlc import - deferring this call to first-tab-visit
        # (rather than building it eagerly like every other bottom-panel
        # tab) is the whole point: most sessions never touch Music at all,
        # so most launches now skip that import cost entirely.
        if music_panel_state["built"]:
            return
        music_panel_state["built"] = True
        music_controls.update(music_player.build_music_panel(
            music_tab, THEME, on_track_change=_update_music_status_label
        ))

    def _on_bottom_panel_tab_changed(event=None):
        try:
            current_tab_text = bottom_panel.tab(bottom_panel.select(), "text")
        except tk.TclError:
            return
        if "Music" in current_tab_text:
            _ensure_music_panel_built()

    bottom_panel.bind("<<NotebookTabChanged>>", _on_bottom_panel_tab_changed, add="+")

    def _focus_music_tab(event=None):
        bottom_panel.select(music_tab)  # fires <<NotebookTabChanged>> above, which builds the panel if needed

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
        on_repo_cloned=lambda p: _open_project_folder(p),
        on_commit=lambda: _record_commit(),
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
        for ed in tab_editors.values():
            refresh_minimap_heat(ed)

    # ---- Stats tab (session timer + all-time totals) ----
    # A small "fun but honest" dashboard: nothing here is computed by
    # polling anything expensive - session numbers are just time.time()
    # math and an in-memory counter, and the all-time numbers are read
    # straight off the same persisted stats dict the periodic flush below
    # writes to.
    stats_tab = tk.Frame(bottom_panel, bg=THEME["output_bg"])
    bottom_panel.add(stats_tab, text="\U0001F4CA Stats")

    def _format_duration(total_seconds):
        total_seconds = int(total_seconds)
        hrs, rem = divmod(total_seconds, 3600)
        mins, secs = divmod(rem, 60)
        if hrs:
            return f"{hrs}h {mins}m"
        if mins:
            return f"{mins}m {secs}s"
        return f"{secs}s"

    def _make_stat_row(label_text):
        row = tk.Frame(stats_tab, bg=THEME["output_bg"])
        row.pack(fill="x", padx=16, pady=(14, 0))
        tk.Label(
            row, text=label_text, bg=THEME["output_bg"], fg=THEME["muted_fg"], anchor="w"
        ).pack(side="left")
        value_label = tk.Label(
            row, text="-", bg=THEME["output_bg"], fg=THEME["output_fg"],
            anchor="e", font=("Consolas", 11, "bold")
        )
        value_label.pack(side="right")
        return value_label

    stats_session_time_value = _make_stat_row("This session")
    stats_total_time_value = _make_stat_row("Total time coded")
    stats_session_commits_value = _make_stat_row("Commits this session")
    stats_total_commits_value = _make_stat_row("Total commits")

    tk.Frame(stats_tab, bg=THEME["border"], height=1).pack(fill="x", padx=16, pady=14)

    stats_fun_label = tk.Label(
        stats_tab, text="", bg=THEME["output_bg"], fg=THEME["accent"],
        anchor="w", padx=16, wraplength=360, justify="left"
    )
    stats_fun_label.pack(fill="x")

    _FUN_STAT_MILESTONES = (
        (60 * 60 * 10, "Double digits! 10+ hours in CodeForge."),
        (60 * 60 * 5, "5 hours coded - halfway to double digits."),
        (60 * 60, "Past the 1-hour mark."),
    )

    def refresh_stats_panel():
        session_elapsed = time.time() - session_stats["start"]
        persisted = load_stats()
        # persisted["total_seconds"] only holds *previous* runs' time as of
        # the last flush - add this session's elapsed time so the total
        # shown is accurate between flushes instead of jumping every 30s.
        all_time_seconds = persisted["total_seconds"] + session_elapsed
        all_time_commits = persisted["total_commits"]

        stats_session_time_value.config(text=_format_duration(session_elapsed))
        stats_total_time_value.config(text=_format_duration(all_time_seconds))
        stats_session_commits_value.config(text=str(session_stats["commits"]))
        stats_total_commits_value.config(text=str(all_time_commits))

        for threshold, message in _FUN_STAT_MILESTONES:
            if all_time_seconds >= threshold:
                stats_fun_label.config(text="\u2728 " + message)
                break
        else:
            stats_fun_label.config(text="")

    def _focus_stats_tab(event=None):
        bottom_panel.select(stats_tab)
        refresh_stats_panel()

    status_timer_label.bind("<Button-1>", _focus_stats_tab)

    def _record_commit():
        session_stats["commits"] += 1
        stats = load_stats()
        stats["total_commits"] = stats["total_commits"] + 1
        save_stats(stats)
        refresh_stats_panel()

    def _flush_session_stats():
        """Roll this run's elapsed-since-last-flush time into the
        persisted all-time total. Called on a timer (not just at exit) so
        a crash or the theme-switch relaunch (root.destroy() + os.execv)
        only ever loses at most one flush interval's worth of time."""
        now = time.time()
        delta = now - session_stats["last_flush"]
        session_stats["last_flush"] = now
        stats = load_stats()
        stats["total_seconds"] = stats["total_seconds"] + delta
        save_stats(stats)

    def _tick_session_timer():
        elapsed = time.time() - session_stats["start"]
        hrs, rem = divmod(int(elapsed), 3600)
        mins = rem // 60
        status_timer_label.config(text=f"\u23F1 {hrs}h {mins}m" if hrs else f"\u23F1 {mins}m")
        _flush_session_stats()
        refresh_stats_panel()
        root.after(30000, _tick_session_timer)

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

    def _spawn_run_console_multi(argv_steps, run_dir):
        """Like _spawn_run_console, but runs a sequence of steps (each an
        argv list, e.g. ["gcc", "main.c", "-o", "main"]) instead of a single
        interpreter+file invocation - what compiled languages need (compile,
        then execute), chained so a failed step (compile error) stops before
        the next one runs, the same as shell "&&". Interpreted languages
        still go through _spawn_run_console below, which is just this with
        a single step.

        Returns (proc, code_path). `proc` is the Popen handle for the
        console wrapper (cmd.exe / terminal emulator) - its own exit status
        is NOT the program's exit status, since the wrapper's last command
        is the "press a key to close" prompt, not the program itself (and
        closing the window instead of pressing a key makes that prompt
        exit non-zero on its own, which used to get misread as the
        program having failed). `code_path` is a temp file the wrapper
        writes the program's real exit code into right after it finishes,
        before the prompt runs - the caller reads it once `proc` exits.
        """
        fd, code_path = tempfile.mkstemp(prefix="editor_run_", suffix=".exitcode")
        os.close(fd)

        if IS_WINDOWS:
            tokens = []
            for i, step in enumerate(argv_steps):
                if i:
                    tokens.append("&&")
                tokens.extend(step)
            # Same reasoning as the single-step Windows branch used to have:
            # every token passed as its own list element (not pre-joined
            # into one string) so subprocess's list2cmdline quotes only the
            # tokens that actually need it, and cmd.exe's own parsing of
            # "&&"/"&"/">" as separate arguments works the way it expects.
            #
            # !errorlevel! (not %errorlevel%) is deliberate: cmd.exe
            # expands every %variable% in a command line ONCE, before
            # running any part of it - so %errorlevel% here would always
            # read cmd's errorlevel from before the program even ran (0),
            # regardless of what actually happened. /v:on turns on delayed
            # expansion, where !errorlevel! is resolved at the moment that
            # echo actually executes, after the real chain has finished.
            return subprocess.Popen(
                ["cmd.exe", "/v:on", "/c"] + tokens
                + ["&", "echo", "!errorlevel!", ">", code_path]
                + ["&", "echo.", "&", "pause"],
                cwd=run_dir,
                creationflags=subprocess.CREATE_NEW_CONSOLE,
            ), code_path

        command_line = " && ".join(
            " ".join(shlex.quote(tok) for tok in step) for step in argv_steps
        )

        if sys.platform == "darwin":
            script = (
                f"cd {shlex.quote(run_dir)}\n"
                f"{command_line}\n"
                f"echo $? > {shlex.quote(code_path)}\n"
                "echo\nread -n 1 -s -r -p 'Press any key to close...'\n"
            )
            with tempfile.NamedTemporaryFile(mode="w", suffix=".command", delete=False) as tmp:
                tmp.write(script)
                script_path = tmp.name
            os.chmod(script_path, 0o755)
            return subprocess.Popen(["open", script_path]), code_path

        inner = (
            f"cd {shlex.quote(run_dir)} && {command_line}; "
            f"echo $? > {shlex.quote(code_path)}; "
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
                return subprocess.Popen([path] + args), code_path
        raise RuntimeError(
            "No terminal emulator found to run the program in "
            "(tried gnome-terminal, konsole, xfce4-terminal, xterm)."
        )

    def _spawn_run_console(interpreter, filename, run_dir):
        """Spawns a new console window that runs `interpreter filename`
        (cwd=run_dir) and pauses at the end so the output stays on screen
        - the same handoff Code::Blocks/Dev-C++ do for "Run". Returns
        (proc, code_path) - see _spawn_run_console_multi for what each is."""
        return _spawn_run_console_multi([[interpreter, filename]], run_dir)

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
    # Colors for rainbow bracket-pair coloring, cycling through theme keys
    # that already read well against the editor background (reusing them
    # rather than adding a bracket-specific palette to every theme).
    BRACKET_DEPTH_KEYS = ("syntax_keyword", "syntax_function", "syntax_number", "accent")
    BRACKET_DEPTH_TAGS = tuple(f"bracket_depth_{i}" for i in range(len(BRACKET_DEPTH_KEYS)))

    # When an editor is split, the second pane's content is a mirror of
    # the first rather than being lexed independently - these are the
    # tags copied across on every sync, i.e. everything that colors the
    # text itself. Cursor/selection-adjacent tags (current_line,
    # bracket_match, search_match/current) are deliberately left out:
    # each pane has its own cursor and its own search state, so those
    # should stay local to whichever pane they're actually happening in.
    SPLIT_MIRROR_TAGS = ("keyword", "string", "comment", "number", "function") + BRACKET_DEPTH_TAGS

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

        # Rainbow bracket-pair coloring: each nesting depth gets its own
        # foreground color, cycling through colors the theme already
        # defines for syntax highlighting (so every theme gets a matching
        # set for free instead of needing its own bracket palette).
        for i, tag_name in enumerate(BRACKET_DEPTH_TAGS):
            key = BRACKET_DEPTH_KEYS[i % len(BRACKET_DEPTH_KEYS)]
            text_area.tag_configure(tag_name, foreground=THEME[key])

        # Highlights for the bracket under/next to the cursor and its pair.
        # Configured after the depth tags so its background always wins
        # over their foreground-only coloring.
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

    def setup_line_number_tags(line_numbers):
        # A soft tint blended from the gutter's own background towards the
        # accent color for the band, plus full accent + bold for the digits
        # themselves - reads as a glow without needing real blur/alpha,
        # which Tk doesn't support anyway.
        glow_bg = blend_hex(THEME["line_number_bg"], THEME["accent"], 0.16)
        font = current_editor_font()
        line_numbers.tag_configure(
            "active_line_number",
            foreground=THEME["accent"],
            background=glow_bg,
            font=(font[0], font[1], "bold"),
        )

    def highlight_current_line(editor):
        text_area = editor["text"]
        text_area.tag_remove("current_line", "1.0", tk.END)
        line = text_area.index("insert").split(".")[0]
        text_area.tag_add("current_line", f"{line}.0", f"{line}.0+1line")

        # Mirror onto the gutter: bright accent-colored, bold, with a soft
        # tinted band behind it - a "glow" for the active line number, same
        # idea as VS Code dimming every other line number.
        line_numbers = editor.get("line_numbers")
        if line_numbers is not None:
            line_numbers.tag_remove("active_line_number", "1.0", tk.END)
            line_numbers.tag_add("active_line_number", f"{line}.0", f"{line}.0+1line")

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

    def highlight_bracket_pairs(text_area, content, starts, skip_spans):
        # skip_spans are (start_offset, end_offset) character ranges already
        # known to be strings/comments (collected during the syntax pass
        # below) - brackets inside those don't count towards nesting depth,
        # same reasoning as _is_code_position for the single-pair matcher
        # above, just done here as a cheap sorted-list lookup instead of a
        # tag_names() call per character since this runs over every
        # bracket in the whole file.
        skip_spans = sorted(skip_spans)
        skip_starts = [s for s, _ in skip_spans]

        def in_skip_span(offset):
            if not skip_starts:
                return False
            i = bisect.bisect_right(skip_starts, offset) - 1
            if i < 0:
                return False
            s, e = skip_spans[i]
            return s <= offset < e

        depth = 0
        n_colors = len(BRACKET_DEPTH_TAGS)
        for offset, ch in enumerate(content):
            if ch not in BRACKET_OPENERS and ch not in BRACKET_CLOSERS:
                continue
            if in_skip_span(offset):
                continue
            if ch in BRACKET_OPENERS:
                tag = BRACKET_DEPTH_TAGS[depth % n_colors]
                depth += 1
            else:
                depth = max(depth - 1, 0)
                tag = BRACKET_DEPTH_TAGS[depth % n_colors]
            idx = _offset_to_index(offset, starts)
            text_area.tag_add(tag, idx, f"{idx}+1c")

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

    SYNTAX_WINDOW_PAD_LINES = 150

    def highlight_syntax(editor, changed_line=None):
        """Dispatches to a full-document re-highlight or a fast windowed
        one, depending on what kind of edit just happened.

        changed_line=None (file just opened, theme/font change, Find &
        Replace, etc.) always means "do the full, correct thing" - none
        of those callers know or care about a specific edited line, so
        there's no safe way to scope the work.

        When a specific line IS known (the common "someone is typing"
        case from on_key_release below), a full rescan is still only
        used if the total line count changed since the last pass - that
        covers structural edits (new/deleted lines, which can introduce
        or remove multi-line strings/comments) with the same full
        correctness as before. Otherwise only a padded window of lines
        around the edit gets its token tags redone - see
        _highlight_syntax_window's docstring for what that does and
        doesn't cover.
        """
        text_area = editor["text"]
        num_lines = int(text_area.index("end-1c").split(".")[0])
        prev_count = editor.get("highlight_last_line_count")
        do_full = changed_line is None or prev_count is None or prev_count != num_lines
        editor["highlight_last_line_count"] = num_lines

        if do_full:
            _highlight_syntax_full(editor)
        else:
            _highlight_syntax_window(editor, changed_line, num_lines)

    def _highlight_syntax_full(editor):
        text_area = editor["text"]
        for tag in ("keyword", "string", "comment", "number", "function"):
            text_area.tag_remove(tag, "1.0", tk.END)
        for tag in BRACKET_DEPTH_TAGS:
            text_area.tag_remove(tag, "1.0", tk.END)
        apply_crt_scanlines(editor)

        content = text_area.get("1.0", tk.END)
        starts = _line_starts(content)

        profile = _get_syntax_profile(editor.get("path"))
        # Bracket-pair depth coloring skips brackets that live inside a
        # string or comment (e.g. a "(" in a docstring shouldn't count
        # towards nesting) - collected here as a byproduct of the regular
        # syntax pass instead of a second full-document tag_names() scan.
        string_comment_spans = []

        if profile:
            for tag_name, patterns in profile.items():
                for pattern in patterns:
                    if isinstance(pattern, tuple):
                        regex, group = pattern
                    else:
                        regex, group = pattern, 0
                    for match in regex.finditer(content):
                        s, e = match.start(group), match.end(group)
                        start = _offset_to_index(s, starts)
                        end = _offset_to_index(e, starts)
                        text_area.tag_add(tag_name, start, end)
                        if tag_name in ("string", "comment"):
                            string_comment_spans.append((s, e))

        highlight_bracket_pairs(text_area, content, starts, string_comment_spans)

    def _highlight_syntax_window(editor, changed_line, num_lines):
        """Fast path for the overwhelmingly common case: typing inside an
        existing line, same total line count as the last pass. Only the
        token tags (keyword/string/comment/number/function) get cleared
        and reapplied, and only within a padded window of lines around
        the edit - not the whole document. This is what actually removes
        the per-keystroke-pause cost that used to scale with file size:
        re-running every regex pattern over the entire buffer on every
        typing pause, regardless of how small the actual edit was, was
        the single biggest cost in the editor on anything but a small
        file.

        Two things are intentionally left untouched here, both with
        bounded, self-correcting staleness:

        - Bracket-depth coloring: depth is cumulative from the start of
          the file, so it can't be correctly recomputed from a window
          alone. It stays exactly as the last full pass drew it, which is
          only wrong if the edit itself added/removed a bracket - and
          that gets caught and fixed by the slower full-reconciliation
          pass scheduled from on_key_release, shortly after typing stops.
        - CRT scanlines: they only depend on line *count* parity, and any
          line-count change already forces a full pass (see
          highlight_syntax above), so scanlines can never actually go
          stale here.
        """
        text_area = editor["text"]
        window_start = max(1, changed_line - SYNTAX_WINDOW_PAD_LINES)
        window_end = min(num_lines, changed_line + SYNTAX_WINDOW_PAD_LINES)

        window_start_index = f"{window_start}.0"
        window_end_index = f"{window_end}.0 lineend"

        for tag in ("keyword", "string", "comment", "number", "function"):
            text_area.tag_remove(tag, window_start_index, window_end_index)

        profile = _get_syntax_profile(editor.get("path"))
        if not profile:
            return

        content = text_area.get(window_start_index, window_end_index)
        starts = _line_starts(content)

        for tag_name, patterns in profile.items():
            for pattern in patterns:
                if isinstance(pattern, tuple):
                    regex, group = pattern
                else:
                    regex, group = pattern, 0
                for match in regex.finditer(content):
                    s, e = match.start(group), match.end(group)
                    start = _offset_to_index_in_window(s, starts, window_start)
                    end = _offset_to_index_in_window(e, starts, window_start)
                    text_area.tag_add(tag_name, start, end)

    # ---------- Squiggly-line diagnostics (linting) ----------
    # Tkinter's Text widget only supports a plain straight "underline" tag,
    # so an actual wavy squiggle has to be faked the same way the indent
    # guides above are: a pool of tiny reusable Canvas strips, placed with
    # pixel-exact .place(in_=text_area, ...) coordinates on top of the text
    # rather than anything backed by a Text tag. Unlike the guides (which
    # only care about a column's x position) each squiggle also needs the
    # pixel width of the specific span it's underlining, so this measures
    # bbox() at both ends of the diagnostic instead of a fixed column.
    LINT_HOVER_DELAY_MS = 300
    DEF_HOVER_DELAY_MS = 350

    def _lint_diag_span(text_area, diag):
        """The (start_index, end_index) run of text a diagnostic should be
        underlined across. Checkers that know exactly which characters are
        wrong (e.g. Python's SyntaxError offset) set end_col; ones that only
        know a position (e.g. "unterminated string starting here") don't,
        so this falls back to Tk's own word-boundary logic rather than
        underlining just one lonely character."""
        line = diag["line"]
        col = diag["col"]
        start_index = f"{line}.{col}"
        end_col = diag.get("end_col")
        if end_col is not None and end_col > col:
            return start_index, f"{line}.{end_col}"
        end_index = text_area.index(f"{start_index} wordend")
        if text_area.compare(end_index, "<=", start_index):
            end_index = f"{start_index}+1c"
        return start_index, end_index

    def _clear_lint_squiggles(editor):
        editor["lint_pool_used"] = 0

    def _hide_unused_lint_squiggles(editor):
        pool = editor["lint_canvases"]
        for canvas in pool[editor["lint_pool_used"]:]:
            canvas.place_forget()

    def _draw_lint_run(editor, x_start, x_end, y, color):
        text_area = editor["text"]
        width = max(int(x_end - x_start), 4)
        amplitude = 2
        period = 4
        points = []
        x = 0
        up = True
        while x <= width:
            points.extend([x, 0 if up else amplitude])
            x += period
            up = not up
        if len(points) < 4:
            points = [0, amplitude, width, 0]

        pool = editor["lint_canvases"]
        idx = editor["lint_pool_used"]
        if idx < len(pool):
            canvas = pool[idx]
            canvas.configure(width=width, height=amplitude + 2, bg=THEME["editor_bg"])
            canvas.delete("all")
        else:
            canvas = tk.Canvas(
                editor["editor_frame"],
                width=width,
                height=amplitude + 2,
                bg=THEME["editor_bg"],
                highlightthickness=0,
                bd=0
            )
            pool.append(canvas)
        canvas.create_line(*points, fill=color, width=1)
        canvas.place(in_=text_area, x=x_start, y=y)
        editor["lint_pool_used"] = idx + 1

    def update_lint_squiggles(editor):
        """Redraws the squiggle overlay for whatever's currently in
        editor["diagnostics"] against the on-screen portion of the text -
        called after every re-lint, and again on scroll/resize/zoom since
        those change the pixel coordinates the previous pass computed
        without changing the diagnostics themselves."""
        text_area = editor["text"]
        if not text_area.winfo_exists():
            return

        _clear_lint_squiggles(editor)
        try:
            diagnostics = editor.get("diagnostics") or []
            if not diagnostics:
                return

            text_area.update_idletasks()
            widget_height = text_area.winfo_height()
            first_visible = int(text_area.index("@0,0").split(".")[0])
            last_visible = int(text_area.index(f"@0,{max(widget_height - 1, 0)}").split(".")[0])

            colors = {"error": THEME["lint_error"], "warning": THEME["lint_warning"]}

            for diag in diagnostics:
                line = diag.get("line", 1)
                if line < first_visible - 1 or line > last_visible + 1:
                    continue

                line_info = text_area.dlineinfo(f"{line}.0")
                if not line_info:
                    continue

                try:
                    start_index, end_index = _lint_diag_span(text_area, diag)
                    start_bbox = text_area.bbox(start_index)
                    end_bbox = text_area.bbox(f"{end_index}-1c") or start_bbox
                except tk.TclError:
                    continue
                if not start_bbox:
                    continue

                x_start = start_bbox[0]
                x_end = end_bbox[0] + end_bbox[2]
                if x_end <= x_start:
                    x_end = x_start + 4

                _, line_y, _, line_height, _ = line_info
                squiggle_y = line_y + line_height - 3
                color = colors.get(diag.get("severity"), colors["error"])
                _draw_lint_run(editor, x_start, x_end, squiggle_y, color)
        finally:
            _hide_unused_lint_squiggles(editor)

    def _diag_at_position(editor, index):
        text_area = editor["text"]
        line = int(index.split(".")[0])
        for diag in editor.get("diagnostics") or []:
            if diag.get("line") != line:
                continue
            try:
                start_index, end_index = _lint_diag_span(text_area, diag)
                if text_area.compare(index, ">=", start_index) and text_area.compare(index, "<", end_index):
                    return diag
            except tk.TclError:
                continue
        return None

    def hide_lint_tooltip(editor):
        tooltip = editor.get("lint_tooltip")
        if tooltip is not None:
            editor["lint_tooltip"] = None
            try:
                tooltip.destroy()
            except tk.TclError:
                pass

    def show_lint_tooltip(editor, diag, x_root, y_root):
        hide_lint_tooltip(editor)
        tooltip = tk.Toplevel(editor["text"])
        tooltip.wm_overrideredirect(True)
        tooltip.wm_geometry(f"+{x_root}+{y_root}")
        try:
            tooltip.attributes("-topmost", True)
        except tk.TclError:
            pass
        icon = "\u2716" if diag.get("severity") == "error" else "\u26A0"
        tk.Label(
            tooltip,
            text=f"{icon} {diag.get('message', 'Problem')}",
            bg=THEME["popup_bg"],
            fg=THEME["popup_fg"],
            highlightthickness=1,
            highlightbackground=THEME["popup_border"],
            highlightcolor=THEME["popup_border"],
            padx=8,
            pady=4,
            justify="left",
            wraplength=420,
            font=("Consolas", 10),
        ).pack()
        editor["lint_tooltip"] = tooltip

    def bind_lint_hover(text_area, editor):
        def cancel_hover_job(ed=editor):
            pending = ed.get("lint_hover_job")
            if pending is not None:
                try:
                    ed["text"].after_cancel(pending)
                except tk.TclError:
                    pass
                ed["lint_hover_job"] = None

        def on_motion(event, ed=editor, ta=text_area):
            cancel_hover_job(ed)

            def check(ed=ed, ta=ta, x=event.x, y=event.y):
                ed["lint_hover_job"] = None
                if not ta.winfo_exists():
                    return
                try:
                    index = ta.index(f"@{x},{y}")
                except tk.TclError:
                    return
                diag = _diag_at_position(ed, index)
                if diag is None:
                    hide_lint_tooltip(ed)
                    return
                x_root = ta.winfo_rootx() + x + 12
                y_root = ta.winfo_rooty() + y + 20
                show_lint_tooltip(ed, diag, x_root, y_root)

            ed["lint_hover_job"] = ta.after(LINT_HOVER_DELAY_MS, check)

        def on_leave(event, ed=editor):
            cancel_hover_job(ed)
            hide_lint_tooltip(ed)

        text_area.bind("<Motion>", on_motion, add="+")
        text_area.bind("<Leave>", on_leave, add="+")

    # ---------- Definition-on-hover ----------
    # Same shape as the lint hover above (debounced <Motion>, a floating
    # Toplevel as the tooltip), but answering "where is this name defined"
    # instead of "what's wrong with this span" - see hover_defs.py for how
    # that lookup actually works per language.
    _DEF_KIND_LABELS = {
        "function": "function", "async function": "async function",
        "class": "class", "parameter": "parameter", "import": "import",
        "exception": "exception variable", "variable": "variable",
        "method": "method", "type": "type", "const": "const",
        "rule": "CSS rule", "id": "HTML id",
    }

    def hide_def_tooltip(editor):
        tooltip = editor.get("def_tooltip")
        if tooltip is not None:
            editor["def_tooltip"] = None
            try:
                tooltip.destroy()
            except tk.TclError:
                pass

    def show_def_tooltip(editor, defn, x_root, y_root):
        hide_def_tooltip(editor)
        tooltip = tk.Toplevel(editor["text"])
        tooltip.wm_overrideredirect(True)
        tooltip.wm_geometry(f"+{x_root}+{y_root}")
        try:
            tooltip.attributes("-topmost", True)
        except tk.TclError:
            pass

        body = tk.Frame(
            tooltip, bg=THEME["popup_bg"], highlightthickness=1,
            highlightbackground=THEME["popup_border"], highlightcolor=THEME["popup_border"]
        )
        body.pack()

        kind_label = _DEF_KIND_LABELS.get(defn["kind"], defn["kind"])
        tk.Label(
            body, text=f"{kind_label} \u00b7 line {defn['line']}",
            bg=THEME["popup_bg"], fg=THEME["muted_fg"], anchor="w", justify="left",
            padx=8, pady=0, font=("Segoe UI", 8, "bold")
        ).pack(fill="x", pady=(4, 0))
        tk.Label(
            body, text=defn["preview"] or defn["name"],
            bg=THEME["popup_bg"], fg=THEME["popup_fg"], anchor="w", justify="left",
            padx=8, pady=0, font=("Consolas", 10), wraplength=420
        ).pack(fill="x", pady=(0, 4 if not defn.get("doc") else 0))
        if defn.get("doc"):
            tk.Label(
                body, text=defn["doc"],
                bg=THEME["popup_bg"], fg=THEME["muted_fg"], anchor="w", justify="left",
                padx=8, pady=0, font=("Segoe UI", 9, "italic"), wraplength=420
            ).pack(fill="x", pady=(2, 4))

        editor["def_tooltip"] = tooltip

    def bind_definition_hover(text_area, editor):
        def cancel_hover_job(ed=editor):
            pending = ed.get("def_hover_job")
            if pending is not None:
                try:
                    ed["text"].after_cancel(pending)
                except tk.TclError:
                    pass
                ed["def_hover_job"] = None

        def on_motion(event, ed=editor, ta=text_area):
            cancel_hover_job(ed)

            def check(ed=ed, ta=ta, x=event.x, y=event.y):
                ed["def_hover_job"] = None
                if not ta.winfo_exists():
                    return
                try:
                    index = ta.index(f"@{x},{y}")
                except tk.TclError:
                    return

                # A lint diagnostic already claims this spot - let that
                # tooltip own it rather than racing two popups over the
                # same corner of the screen.
                if _diag_at_position(ed, index) is not None:
                    return

                try:
                    word_start = ta.index(f"{index} wordstart")
                    word_end = ta.index(f"{index} wordend")
                    word = ta.get(word_start, word_end)
                except tk.TclError:
                    return
                if not word or not (word[0].isalpha() or word[0] == "_"):
                    hide_def_tooltip(ed)
                    return

                content = ta.get("1.0", "end-1c")
                hover_line = int(index.split(".")[0])
                defn = hover_defs.find_definition(ed.get("path"), content, word, hover_line)
                if defn is None or defn["line"] == hover_line:
                    # No match, or hovering right over the definition
                    # itself - either way there's nothing useful to show.
                    hide_def_tooltip(ed)
                    return

                x_root = ta.winfo_rootx() + x + 12
                y_root = ta.winfo_rooty() + y + 20
                show_def_tooltip(ed, defn, x_root, y_root)

            ed["def_hover_job"] = ta.after(DEF_HOVER_DELAY_MS, check)

        def on_leave(event, ed=editor):
            cancel_hover_job(ed)
            hide_def_tooltip(ed)

        text_area.bind("<Motion>", on_motion, add="+")
        text_area.bind("<Leave>", on_leave, add="+")

    def update_lint_status_label(editor):
        """Mirrors the active editor's diagnostic counts onto the status
        bar, VS Code-style. Guarded against a background tab's lint pass
        finishing after the user has already switched away from it."""
        if editor is not get_current_editor():
            return
        diagnostics = editor.get("diagnostics") or []
        errors = sum(1 for d in diagnostics if d.get("severity") == "error")
        warnings = sum(1 for d in diagnostics if d.get("severity") == "warning")
        if not errors and not warnings:
            status_lint_label.config(text="\u2713 No problems", fg=THEME["muted_fg"])
        else:
            parts = []
            if errors:
                parts.append(f"\u2716 {errors}")
            if warnings:
                parts.append(f"\u26A0 {warnings}")
            status_lint_label.config(text="  ".join(parts), fg=THEME["lint_error"] if errors else THEME["lint_warning"])

    def run_lint(editor):
        """(Re-)schedules a background lint pass for `editor`, debounced so
        a fast typist doesn't spawn a subprocess (several checkers below
        shell out to a real compiler) on every keystroke - only once
        typing has actually paused for a moment."""
        pending = editor.get("lint_job")
        if pending is not None:
            try:
                editor["text"].after_cancel(pending)
            except tk.TclError:
                pass

        def do_lint(ed=editor):
            ed["lint_job"] = None
            text_area = ed["text"]
            if not text_area.winfo_exists():
                return

            ed["lint_seq"] = ed.get("lint_seq", 0) + 1
            seq = ed["lint_seq"]
            content = text_area.get("1.0", "end-1c")
            path = ed.get("path")

            def worker(seq=seq, content=content, path=path, ed=ed):
                try:
                    diagnostics = linters.lint(path, content)
                except Exception:
                    diagnostics = []

                def apply(ed=ed, seq=seq, diagnostics=diagnostics):
                    # A newer edit (and thus a newer scheduled lint pass)
                    # has already superseded this one - drop it rather
                    # than flash stale squiggles back onto the screen.
                    if ed.get("lint_seq") != seq:
                        return
                    if not ed["text"].winfo_exists():
                        return
                    ed["diagnostics"] = diagnostics
                    update_lint_squiggles(ed)
                    update_lint_status_label(ed)

                    error_count = sum(1 for d in diagnostics if d.get("severity") == "error")
                    prev_count = ed.get("_prev_lint_error_count", 0)
                    if error_count > prev_count:
                        fun_effects.error_flash(ed["editor_frame"])
                    ed["_prev_lint_error_count"] = error_count

                try:
                    ed["text"].after(0, apply)
                except tk.TclError:
                    pass

            threading.Thread(target=worker, daemon=True).start()

        editor["lint_job"] = editor["text"].after(500, do_lint)

    # ---------- Minimap ----------
    # A zoomed-out overview of the whole file rendered as a strip of tiny
    # bars (one per line, or one per bucket of lines once the file has more
    # lines than MINIMAP_MAX_ROWS) plus a draggable box showing what's
    # currently visible in the real editor - the same idea as VS Code/
    # Sublime's minimap, done cheaply with a handful of rectangles on a
    # Canvas rather than actually rendering miniature text. The strip
    # itself is stationary - it always shows the entire file squeezed into
    # the panel's current height, so there's nothing to pan or scroll;
    # navigation happens entirely through the viewport box.
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

        # Every row is always MINIMAP_ROW_HEIGHT tall, in every file,
        # regardless of how many lines it has - rows never stretch or
        # shrink to match the panel height. To keep the whole file
        # visible with no scrolling, longer files just bucket more source
        # lines into each row instead: row_count is capped at however many
        # fixed-height rows actually fit in canvas_h, so a big file is
        # summarized down to fit while a small one only fills part of the
        # panel and leaves the rest blank underneath.
        row_height = MINIMAP_ROW_HEIGHT
        max_rows_that_fit = max(1, int(canvas_h / row_height))
        row_count = min(total_lines, max_rows_that_fit, MINIMAP_MAX_ROWS)
        lines_per_row = total_lines / row_count
        virtual_height = row_count * row_height
        editor["minimap_virtual_height"] = virtual_height

        # Git heatmap - reserve a thin strip on the right edge for rows
        # whose lines were added/modified since HEAD. Uses whatever
        # refresh_minimap_heat() last cached on this editor; see the
        # comment by git_heatmap_state for why the actual `git diff` call
        # doesn't happen in here.
        heat = editor.get("git_heat") or {}
        added_lines = heat.get("added") or set()
        modified_lines = heat.get("modified") or set()
        untracked = bool(heat.get("untracked"))
        show_heat = git_heatmap_state["visible"] and (added_lines or modified_lines or untracked)
        heat_reserve = MINIMAP_HEAT_WIDTH + 2 if show_heat else 0

        longest = max((len(line.rstrip()) for line in lines if line.strip()), default=0)
        longest = min(max(longest, 1), 200)
        scale = (canvas_w - 6 - heat_reserve) / longest

        # Themes can optionally define softer minimap-only variants of
        # these colors (see LIGHT_THEME in themes.py) since a color that
        # reads fine as actual on-screen text can look like a solid slab
        # once it's filling a whole minimap row - themes that don't
        # define these just keep using their normal syntax colors here.
        keyword_color = THEME.get("minimap_keyword", THEME["syntax_keyword"])
        comment_color = THEME.get("minimap_comment", THEME["syntax_comment"])
        default_color = THEME.get("minimap_default", THEME.get("muted_fg", THEME["editor_fg"]))
        # Same color language as the explorer's git status tags (see
        # apply_git_status_tags): green for new content, amber for
        # changed-but-preexisting content.
        heat_added_color = THEME["syntax_comment"]
        heat_modified_color = THEME["search_current_bg"]

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

            y = row * row_height

            if color is not None and max_len > 0:
                width = min(canvas_w - 6 - heat_reserve, max(2, max_len * scale))
                canvas.create_rectangle(
                    3, y, 3 + width, y + row_height,
                    fill=color, outline="", tags="bars"
                )

            if show_heat:
                # Bucket's source lines, 1-based, inclusive.
                bucket_first, bucket_last = start + 1, end
                if untracked or any(
                    l in added_lines for l in range(bucket_first, bucket_last + 1)
                ):
                    heat_color = heat_added_color
                elif any(
                    l in modified_lines for l in range(bucket_first, bucket_last + 1)
                ):
                    heat_color = heat_modified_color
                else:
                    heat_color = None
                if heat_color:
                    canvas.create_rectangle(
                        canvas_w - MINIMAP_HEAT_WIDTH, y, canvas_w, y + row_height,
                        fill=heat_color, outline="", tags="heat"
                    )

        render_minimap_viewport(editor)

    def refresh_minimap_heat(editor):
        """Recomputes editor["git_heat"] against HEAD on a background
        thread (git diff is a subprocess call - far too slow to run
        inline from the debounced on-keystroke redraw) and repaints the
        minimap once the result lands. Called after saves, git operations
        (via refresh_git_state), and tab open/switch - never from typing
        itself."""
        text_area = editor.get("text")
        if text_area is None or not text_area.winfo_exists():
            return

        path = editor.get("path")
        if not path or not project_path or not git_heatmap_state["visible"]:
            editor["git_heat"] = {"added": set(), "modified": set(), "untracked": False}
            render_minimap_content(editor)
            return

        def worker(path=path):
            repo_root = git_panel.find_repo_root(project_path)
            if not repo_root:
                result = {"added": set(), "modified": set(), "untracked": False}
            else:
                try:
                    rel = os.path.relpath(path, repo_root)
                except ValueError:
                    rel = None
                if rel is None:
                    result = {"added": set(), "modified": set(), "untracked": False}
                else:
                    result = git_panel.diff_line_status(repo_root, rel)

            def apply(ed=editor, result=result):
                if not ed["text"].winfo_exists():
                    return
                ed["git_heat"] = result
                render_minimap_content(ed)

            root.after(0, apply)

        threading.Thread(target=worker, daemon=True).start()

    def render_minimap_viewport(editor):
        canvas = editor.get("minimap")
        if canvas is None or not canvas.winfo_exists():
            return

        canvas.delete("viewport")

        canvas_w = canvas.winfo_width()
        canvas_h = canvas.winfo_height()
        if canvas_w <= 1 or canvas_h <= 1:
            return

        # The rendered rows only fill minimap_virtual_height pixels (a
        # short file doesn't stretch to fill the whole panel - see
        # render_minimap_content), so the viewport box maps against that,
        # not the panel's full canvas_h.
        virtual_height = editor.get("minimap_virtual_height") or canvas_h
        first, last = editor["text"].yview()
        y1 = first * virtual_height
        y2 = last * virtual_height
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
        virtual_height = ed.get("minimap_virtual_height") or canvas.winfo_height()
        if virtual_height <= 1:
            return "break"

        frac = min(max(event.y / virtual_height, 0.0), 1.0)
        first, last = ed["text"].yview()
        visible = max(last - first, 0.0)
        target = frac - visible / 2
        target = min(max(target, 0.0), max(0.0, 1.0 - visible))
        ed["text"].yview_moveto(target)
        render_minimap_viewport(ed)
        return "break"

    def minimap_press(event, editor):
        minimap_navigate(event, editor)
        return "break"

    def minimap_drag(event, editor):
        minimap_navigate(event, editor)
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
            "import_map": {}, "import_source": None,
            # Cache for the whole-buffer identifier scan gather_candidates()
            # uses for plain-word completion (as opposed to the "attr" path,
            # which already has its own cache via import_source above).
            # Populated by _refresh_word_pool below.
            "word_pool": frozenset(), "word_pool_job": None,
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

        def _refresh_word_pool():
            # A full text_area.get("1.0", "end") + regex scan over the
            # whole buffer - same cost profile as the syntax highlighter's
            # full-document pass, so it gets the same treatment: debounced
            # rather than run inline on every keystroke (see
            # _schedule_word_pool_refresh below). Previously this ran
            # straight in gather_candidates() on every single keystroke
            # while a completion prefix was active, which made typing an
            # identifier in a large file noticeably laggier than typing
            # anywhere else in the editor.
            ac["word_pool_job"] = None
            if not text_area.winfo_exists():
                return
            text = text_area.get("1.0", "end")
            ac["word_pool"] = frozenset(re.findall(r"[A-Za-z_]\w{1,}", text))

        def _schedule_word_pool_refresh():
            pending = ac["word_pool_job"]
            if pending is not None:
                text_area.after_cancel(pending)
            ac["word_pool_job"] = text_area.after(400, _refresh_word_pool)

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

            # Word pool is refreshed on a debounce (see
            # _schedule_word_pool_refresh) rather than rescanned here on
            # every keystroke; a moment of staleness (missing an
            # identifier someone is mid-way through typing elsewhere in
            # the file) is a fine trade for not re-scanning the whole
            # buffer per character, same reasoning as the syntax
            # highlighter's own debounced full-document pass.
            if not ac["word_pool"] and ac["word_pool_job"] is None:
                # Nothing cached yet this session (popup opened before the
                # first debounce fired) - do one synchronous scan so
                # completion still works immediately rather than staying
                # empty until the timer catches up.
                _refresh_word_pool()
            pool = ac["word_pool"] | set(keyword.kwlist) | _BUILTIN_NAMES
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

            _schedule_word_pool_refresh()

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
        editor["line_numbers"].tag_configure(
            "active_line_number", font=(font[0], font[1], "bold")
        )
        fold_gutter = editor.get("fold_gutter")
        if fold_gutter is not None:
            fold_gutter.config(font=font)
        pane2 = editor.get("pane2")
        if pane2 is not None:
            pane2["text"].config(font=font)
            pane2["line_numbers"].config(font=font)
            pane2["fold_gutter"].config(font=font)
        update_indent_guides(editor)
        update_lint_squiggles(editor)

    def set_font_size(new_size):
        new_size = max(MIN_FONT_SIZE, min(MAX_FONT_SIZE, new_size))
        if new_size == font_state["size"]:
            return
        font_state["size"] = new_size
        for editor in tab_editors.values():
            apply_font_size_to_editor(editor)
        save_font_size_preference(new_size)

    def set_font_family(new_family):
        new_family = (new_family or DEFAULT_FONT_FAMILY).strip() or DEFAULT_FONT_FAMILY
        if new_family == font_state["family"]:
            return
        font_state["family"] = new_family
        for editor in tab_editors.values():
            apply_font_size_to_editor(editor)
        save_font_family_preference(new_family)

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

    def _on_fold_toggled(editor):
        """A gutter click just hid or revealed a chunk of lines - anything
        that was positioned/drawn against the old set of visible lines
        needs to catch up, the same set of "the viewport just changed
        underneath us" follow-ups on_text_scroll already does for regular
        scrolling."""
        update_indent_guides(editor)
        mc = editor.get("multi_cursor")
        if mc and mc["cursors"]:
            mc["draw_carets"]()
        render_minimap_viewport(editor)
        update_lint_squiggles(editor)

    def _build_editor_pane(parent, wrap_mode):
        """Builds one gutter+fold-gutter+text+scrollbar group - the unit
        that create_tab uses for the primary pane, and split_editor()
        below reuses verbatim for a second pane. Returns the individual
        widgets rather than a dict since the two call sites want them
        merged into differently-shaped structures (the top-level `editor`
        dict vs. a nested "pane2" dict)."""
        pane_frame = tk.Frame(parent, bg=THEME["editor_bg"], highlightthickness=0, bd=0)

        line_numbers = tk.Text(
            pane_frame,
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
        setup_line_number_tags(line_numbers)

        # One-character-wide gutter for the little fold triangles, kept
        # as its own Text widget (rather than folded into line_numbers'
        # own text) so the fold engine can rebuild it on every keystroke
        # pause without touching the line-number digits or their
        # active-line glow tag.
        fold_gutter = tk.Text(
            pane_frame,
            width=1,
            padx=1,
            takefocus=0,
            border=0,
            background=THEME["line_number_bg"],
            foreground=THEME["lint_warning"],
            state="disabled",
            wrap="none",
            cursor="arrow",
            font=current_editor_font()
        )
        fold_gutter.pack(side="left", fill="y")

        text_area = tk.Text(
            pane_frame,
            wrap=wrap_mode,
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
            pane_frame,
            orient="vertical",
            command=text_area.yview,
            style="Vertical.TScrollbar"
        )
        text_scrollbar.pack(side="left", fill="y")

        def on_linenum_scroll(event, ta=text_area):
            ta.yview_scroll(int(-event.delta / 120), "units")
            return "break"

        line_numbers.bind("<MouseWheel>", on_linenum_scroll)
        line_numbers.bind("<Control-MouseWheel>", on_editor_ctrl_wheel)
        fold_gutter.bind("<MouseWheel>", on_linenum_scroll)

        # Bound on the widget itself (not root) and returning "break" -
        # Tk's Text widget has a built-in class binding on Control-slash
        # that selects the whole buffer, which takes priority over a
        # plain root.bind() for the same keysym. Binding directly on
        # text_area is the only way to reliably override that default.
        def on_toggle_comment_key(event):
            toggle_comment()
            return "break"

        text_area.bind("<Control-slash>", on_toggle_comment_key)

        # Dropping a file straight onto the editor surface (not just the
        # tab bar or the explorer tree) opens it too. _on_files_dropped
        # itself is defined further down in this same function - wrapped
        # in a lambda so the name is only looked up when a drop actually
        # happens, by which point it's long since been defined (this
        # whole app is one big function body, executed top to bottom
        # before the mainloop starts).
        if tkinterdnd2:
            text_area.drop_target_register(tkinterdnd2.DND_FILES)
            text_area.dnd_bind("<<Drop>>", lambda e: _on_files_dropped(e))

        return pane_frame, line_numbers, fold_gutter, text_area, text_scrollbar

    def create_tab(path=None, content=""):
        _hide_start_page()

        tab_frame = tk.Frame(tab_control, bg=THEME["editor_bg"], highlightthickness=0, bd=0)

        editor_frame = tk.Frame(tab_frame, bg=THEME["editor_bg"], highlightthickness=0, bd=0)
        editor_frame.pack(fill="both", expand=True)

        # A PanedWindow holding just the one pane, to begin with -
        # split_editor() adds a second draggable-divider pane into this
        # same widget later without anything above it needing to change.
        panes = ttk.PanedWindow(editor_frame, orient="horizontal")
        panes.pack(side="left", fill="both", expand=True)

        pane_frame, line_numbers, fold_gutter, text_area, text_scrollbar = _build_editor_pane(
            panes, "word" if word_wrap_state["enabled"] else "none"
        )
        panes.add(pane_frame, weight=1)

        minimap = tk.Canvas(
            editor_frame,
            width=MINIMAP_WIDTH,
            highlightthickness=0,
            bd=0,
            bg=THEME["editor_bg"]
        )
        if minimap_state["visible"]:
            minimap.pack(side="left", fill="y")

        def on_text_scroll(first, last, ln=line_numbers, fg=fold_gutter, sb=text_scrollbar):
            sb.set(first, last)
            ln.yview_moveto(float(first))
            fg.yview_moveto(float(first))
            # Scrolling shifts which lines/pixels are on screen, so the
            # guide overlay (positioned in real pixel coordinates) needs
            # to be redrawn to match.
            update_indent_guides(editor)
            mc = editor.get("multi_cursor")
            if mc and mc["cursors"]:
                mc["draw_carets"]()
            render_minimap_viewport(editor)
            update_lint_squiggles(editor)

        text_area.config(yscrollcommand=on_text_scroll)

        tab_id = str(tab_frame)
        title = make_tab_title(path)

        editor = {
            "frame": tab_frame,
            "editor_frame": editor_frame,
            "panes": panes,
            "pane1_frame": pane_frame,
            "pane2": None,
            "text": text_area,
            "line_numbers": line_numbers,
            "fold_gutter": fold_gutter,
            "minimap": minimap,
            "path": path,
            "title": title,
            "dirty": False,
            "guide_canvases": [],
            "guide_pool_used": 0,
            "resize_job": None,
            "highlight_job": None,
            "full_highlight_job": None,
            "highlight_last_line_count": None,
            "minimap_resize_job": None,
            "minimap_virtual_height": None,
            "last_line_count": None,
            "git_heat": {"added": set(), "modified": set(), "untracked": False},
            "diagnostics": [],
            "lint_job": None,
            "lint_seq": 0,
            "lint_canvases": [],
            "lint_pool_used": 0,
            "lint_tooltip": None,
            "lint_hover_job": None,
            "def_tooltip": None,
            "def_hover_job": None,
            "wrap_enabled": word_wrap_state["enabled"],
        }
        editor["fold"] = code_folding.FoldEngine(
            text_area, line_numbers, fold_gutter,
            on_toggle=lambda ed=editor: _on_fold_toggled(ed)
        )
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
        minimap.bind("<Button-1>", lambda e, ed=editor: minimap_press(e, ed))
        minimap.bind("<B1-Motion>", lambda e, ed=editor: minimap_drag(e, ed))
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
                update_lint_squiggles(ed)

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
            hide_lint_tooltip(ed)
            hide_def_tooltip(ed)
            highlight_current_line(ed)
            highlight_brackets(ed["text"])
            update_status_bar(ed)
            status_streak_label.config(text=streak_tracker.keystroke())

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
                _run_editor_heavy_update(ed)

            ed["highlight_job"] = ed["text"].after(80, do_heavy_update)

            # The fast path above may have only re-highlighted a window of
            # lines around the edit (see _highlight_syntax_window), which
            # deliberately skips bracket-depth recoloring since depth is
            # cumulative from the start of the file. This slower, longer
            # debounce catches that up with a full pass once typing has
            # actually paused for a bit, so an edit that adds/removes a
            # bracket never stays visually wrong for more than a moment.
            pending_full = ed.get("full_highlight_job")
            if pending_full is not None:
                ed["text"].after_cancel(pending_full)

            def do_full_reconcile(ed=ed):
                ed["full_highlight_job"] = None
                if not ed["text"].winfo_exists():
                    return
                _highlight_syntax_full(ed)
                ed["highlight_last_line_count"] = int(ed["text"].index("end-1c").split(".")[0])

            ed["full_highlight_job"] = ed["text"].after(600, do_full_reconcile)

        def on_click(event, ed=editor):
            ac = ed.get("autocomplete")
            if ac and ac.get("close"):
                ac["close"]()

            mc = ed.get("multi_cursor")
            if mc and mc["cursors"] and not (event.state & 0x4):
                mc["clear"]()

            # Let the click land the cursor first, then re-highlight its line
            def refresh():
                highlight_current_line(ed)
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
        bind_lint_hover(text_area, editor)
        bind_definition_hover(text_area, editor)

        tab_control.add(tab_frame, text=title)
        tab_control.select(tab_frame)

        update_line_numbers(editor)
        highlight_syntax(editor)
        highlight_current_line(editor)
        highlight_brackets(text_area)
        update_indent_guides(editor)
        editor["fold"].render()
        text_area.after_idle(lambda ed=editor: render_minimap_content(ed))
        text_area.after_idle(lambda ed=editor: refresh_minimap_heat(ed))
        run_lint(editor)

        text_area.focus_set()

        return editor

    def save_editor(editor):
        if editor["path"]:
            content = editor["text"].get("1.0", "end-1c")
            with open(editor["path"], "w", encoding="utf-8") as f:
                f.write(content)
            mark_clean(editor)
            refresh_git_state()
            _notify_plugins_on_save(editor["path"], content)
            return True
        else:
            return save_editor_as(editor)

    def save_editor_as(editor):
        path = filedialog.asksaveasfilename(
            defaultextension=".py",
            filetypes=[("Python files", "*.py"), ("All files", "*.*")]
        )
        if not path:
            return False
        content = editor["text"].get("1.0", "end-1c")
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
        editor["path"] = path
        editor["title"] = os.path.basename(path)
        mark_clean(editor)
        update_status_bar(editor)
        refresh_tree()
        refresh_git_state()
        _remember_recent_file(path)
        highlight_syntax(editor)
        run_lint(editor)
        _notify_plugins_on_save(path, content)
        return True

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

        pending = editor.get("full_highlight_job")
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

        pending = editor.get("lint_job")
        if pending is not None:
            try:
                editor["text"].after_cancel(pending)
            except tk.TclError:
                pass

        pending = editor.get("lint_hover_job")
        if pending is not None:
            try:
                editor["text"].after_cancel(pending)
            except tk.TclError:
                pass

        hide_lint_tooltip(editor)

        pending = editor.get("def_hover_job")
        if pending is not None:
            try:
                editor["text"].after_cancel(pending)
            except tk.TclError:
                pass

        hide_def_tooltip(editor)

        ac = editor.get("autocomplete")
        if ac and ac.get("close"):
            ac["close"]()
        if ac:
            pending = ac.get("word_pool_job")
            if pending is not None:
                try:
                    editor["text"].after_cancel(pending)
                except tk.TclError:
                    pass

        mc = editor.get("multi_cursor")
        if mc and mc.get("clear"):
            mc["clear"]()

        pending = editor.get("pane2_highlight_job")
        pane2 = editor.get("pane2")
        if pending is not None and pane2 is not None:
            try:
                pane2["text"].after_cancel(pending)
            except tk.TclError:
                pass

        del tab_editors[tab_id]
        tab_control.forget(editor["frame"])
        editor["frame"].destroy()

        # Never let the editor end up with a bare empty notebook and
        # nothing to do - show the Start Page instead of quietly spawning
        # a blank "Untitled" tab nobody asked for.
        if not tab_control.tabs():
            _show_start_page()

    def close_other_tabs(tab_id):
        for other_id in list(tab_editors.keys()):
            if other_id != tab_id:
                close_tab(other_id)

    # ---------------- Word wrap ----------------
    def toggle_word_wrap():
        word_wrap_state["enabled"] = not word_wrap_state["enabled"]
        mode = "word" if word_wrap_state["enabled"] else "none"
        for ed in tab_editors.values():
            ed["wrap_enabled"] = word_wrap_state["enabled"]
            ed["text"].config(wrap=mode)
            pane2 = ed.get("pane2")
            if pane2:
                pane2["text"].config(wrap=mode)
        view_menu.entryconfig(
            word_wrap_menu_index,
            label="Disable Word Wrap" if word_wrap_state["enabled"] else "Enable Word Wrap"
        )

    # ---------------- Code folding commands ----------------
    def _focused_pane(editor):
        """Whichever of the (up to two) panes currently has focus - fold
        commands act on that one specifically, since a split editor's two
        panes fold independently."""
        pane2 = editor.get("pane2")
        if pane2 and pane2["text"].winfo_exists():
            try:
                if root.focus_get() is pane2["text"]:
                    return pane2
            except tk.TclError:
                pass
        return editor

    def toggle_fold_at_cursor(editor=None):
        editor = editor or get_current_editor()
        if not editor:
            return
        target = _focused_pane(editor)
        line = int(target["text"].index("insert").split(".")[0])
        target["fold"].toggle_at_line(line)
        _on_fold_toggled(editor)

    def fold_all_current(editor=None):
        editor = editor or get_current_editor()
        if not editor:
            return
        target = _focused_pane(editor)
        target["fold"].fold_all()
        _on_fold_toggled(editor)

    def unfold_all_current(editor=None):
        editor = editor or get_current_editor()
        if not editor:
            return
        target = _focused_pane(editor)
        target["fold"].unfold_all()
        _on_fold_toggled(editor)

    # ---------------- Heavy update pipeline (shared by both panes) ----------------
    def _run_editor_heavy_update(ed):
        """The full recompute pass that runs (debounced) after any edit:
        gutter rebuild, syntax re-tagging, indent guides, minimap, lint,
        fold gutter, and - if this editor is split - mirroring the fresh
        result over to the second pane. Factored out of create_tab's
        on_key_release closure so a split pane's own KeyRelease handler
        (see split_editor below) can trigger the exact same pipeline
        rather than maintaining a second, diverging copy of it."""
        if not ed["text"].winfo_exists():
            return
        update_line_numbers(ed)
        changed_line = int(ed["text"].index(tk.INSERT).split(".")[0])
        highlight_syntax(ed, changed_line=changed_line)
        update_indent_guides(ed)
        render_minimap_content(ed)
        run_lint(ed)
        fold = ed.get("fold")
        if fold:
            fold.render()
        sync_split_pane(ed, source="text")

    # ---------------- Split editor (multiple panes on one file) ----------------
    def sync_split_pane(editor, source="text"):
        """If `editor` currently has a second pane open, mirrors content
        from `source` ("text" for the primary pane, "text2" for the
        split one) into the other pane - both showing the same
        underlying file, just possibly scrolled/folded differently, the
        same way two split views onto one file behave in a "real"
        editor. When the primary is the source, its already-computed
        syntax-highlight tag ranges are copied over too rather than
        re-lexing the second pane from scratch; when the split pane is
        the source, tags are left alone since _run_editor_heavy_update
        recomputes the primary's own highlighting right afterward and
        that pass re-syncs (with tags) back out to the split pane anyway.
        """
        pane2 = editor.get("pane2")
        if not pane2:
            return
        if editor.get("_pane_syncing"):
            return

        src = editor["text"] if source == "text" else pane2["text"]
        dst = pane2["text"] if source == "text" else editor["text"]
        if not src.winfo_exists() or not dst.winfo_exists():
            return

        src_content = src.get("1.0", "end-1c")
        if src_content == dst.get("1.0", "end-1c"):
            return

        editor["_pane_syncing"] = True
        try:
            yview = dst.yview()
            dst.delete("1.0", "end")
            dst.insert("1.0", src_content)
            dst.edit_modified(False)
            try:
                dst.yview_moveto(yview[0])
            except tk.TclError:
                pass

            if source == "text":
                for tag in SPLIT_MIRROR_TAGS:
                    dst.tag_remove(tag, "1.0", "end")
                    ranges = src.tag_ranges(tag)
                    for i in range(0, len(ranges), 2):
                        dst.tag_add(tag, ranges[i], ranges[i + 1])

            dst_line_numbers = pane2["line_numbers"] if source == "text" else editor["line_numbers"]
            num_lines = int(dst.index("end-1c").split(".")[0])
            dst_line_numbers.config(state="normal")
            dst_line_numbers.delete("1.0", tk.END)
            dst_line_numbers.insert("1.0", "\n".join(str(i) for i in range(1, num_lines + 1)))
            dst_line_numbers.config(state="disabled")

            dst_fold = pane2["fold"] if source == "text" else editor["fold"]
            dst_fold.render()
        finally:
            editor["_pane_syncing"] = False

    def _pane2_key_release(event, ed):
        pending = ed.get("pane2_highlight_job")
        if pending is not None:
            try:
                ed["pane2"]["text"].after_cancel(pending)
            except tk.TclError:
                pass

        def do_update(ed=ed):
            ed["pane2_highlight_job"] = None
            pane2 = ed.get("pane2")
            if not pane2 or not pane2["text"].winfo_exists():
                return
            mark_dirty(ed)
            # The split pane is a mirror, not its own lexer - push its
            # edit into the primary text widget and let the normal heavy
            # pipeline (numbering/highlighting/lint/fold/minimap) run
            # once there, then re-mirror the freshly-computed result
            # back out. Two-step, but it means there's exactly one place
            # that actually re-lexes the file.
            sync_split_pane(ed, source="text2")
            _run_editor_heavy_update(ed)

        ed["pane2_highlight_job"] = ed["pane2"]["text"].after(80, do_update)

    def split_editor(editor=None):
        editor = editor or get_current_editor()
        if not editor or editor.get("pane2"):
            return

        pane_frame, line_numbers2, fold_gutter2, text_area2, text_scrollbar2 = _build_editor_pane(
            editor["panes"], "word" if word_wrap_state["enabled"] else "none"
        )
        editor["panes"].add(pane_frame, weight=1)
        setup_highlight_tags(text_area2)

        pane2 = {
            "frame": pane_frame,
            "text": text_area2,
            "line_numbers": line_numbers2,
            "fold_gutter": fold_gutter2,
        }
        pane2["fold"] = code_folding.FoldEngine(
            text_area2, line_numbers2, fold_gutter2,
            on_toggle=lambda ed=editor: _on_fold_toggled(ed)
        )
        editor["pane2"] = pane2

        def on_pane2_scroll(first, last, ln=line_numbers2, fg=fold_gutter2, sb=text_scrollbar2):
            sb.set(first, last)
            ln.yview_moveto(float(first))
            fg.yview_moveto(float(first))

        text_area2.config(yscrollcommand=on_pane2_scroll)

        def on_pane2_click(event, ed=editor):
            def refresh(ed=ed):
                pane2 = ed.get("pane2")
                if pane2 and pane2["text"].winfo_exists():
                    highlight_brackets(pane2["text"])
            ed["text"].after_idle(refresh)

        text_area2.bind("<KeyRelease>", lambda e, ed=editor: _pane2_key_release(e, ed))
        text_area2.bind("<ButtonRelease-1>", on_pane2_click)
        text_area2.bind("<Control-MouseWheel>", on_editor_ctrl_wheel)

        # Seed pane 2 with the primary's current content/highlighting
        # right away rather than waiting for the next edit.
        sync_split_pane(editor, source="text")
        text_area2.focus_set()

    def close_split(editor=None):
        editor = editor or get_current_editor()
        if not editor:
            return
        pane2 = editor.get("pane2")
        if not pane2:
            return

        pending = editor.get("pane2_highlight_job")
        if pending is not None:
            try:
                pane2["text"].after_cancel(pending)
            except tk.TclError:
                pass

        try:
            editor["panes"].forget(pane2["frame"])
        except tk.TclError:
            pass
        pane2["frame"].destroy()
        editor["pane2"] = None
        editor["text"].focus_set()

    # ---------------- Comment / uncomment ----------------
    def _comment_target_lines(text):
        """The 1-based (start, end) line range Ctrl+/ should act on: the
        selection if there is one, otherwise just the line the cursor is
        on. A selection that runs down to column 0 of its last line (the
        common result of dragging or Shift-Down through whole lines,
        including the trailing newline) doesn't actually select anything
        on that last line, so it's excluded - otherwise toggling a
        3-line selection would also comment out the untouched 4th line
        sitting right below it."""
        try:
            sel_start = text.index("sel.first")
            sel_end = text.index("sel.last")
        except tk.TclError:
            line = int(text.index("insert").split(".")[0])
            return line, line

        start_line = int(sel_start.split(".")[0])
        end_line, end_col = sel_end.split(".")
        end_line = int(end_line)
        if int(end_col) == 0 and end_line > start_line:
            end_line -= 1
        return start_line, end_line

    def _toggle_line_comments(text, start_line, end_line, prefix):
        lines = [text.get(f"{ln}.0", f"{ln}.end") for ln in range(start_line, end_line + 1)]
        non_blank = [line for line in lines if line.strip()]
        if not non_blank:
            return

        all_commented = all(line.lstrip().startswith(prefix) for line in non_blank)

        if all_commented:
            for ln in range(start_line, end_line + 1):
                line = text.get(f"{ln}.0", f"{ln}.end")
                stripped = line.lstrip()
                if not stripped.startswith(prefix):
                    continue
                indent_len = len(line) - len(stripped)
                remove_len = len(prefix) + 1 if stripped.startswith(prefix + " ") else len(prefix)
                text.delete(f"{ln}.{indent_len}", f"{ln}.{indent_len + remove_len}")
        else:
            # Align every inserted marker to the shallowest indentation
            # in the block (matching most editors' Ctrl+/ behavior),
            # rather than each line commenting itself at its own indent -
            # an if-block's body would otherwise end up with its markers
            # in a jagged column instead of a clean flush left edge.
            indents = [len(line) - len(line.lstrip()) for line in non_blank]
            min_indent = min(indents)
            for ln in range(start_line, end_line + 1):
                if not text.get(f"{ln}.0", f"{ln}.end").strip():
                    continue
                text.insert(f"{ln}.{min_indent}", prefix + " ")

    def _toggle_block_comment(text, start_line, end_line, open_marker, close_marker):
        start_idx, end_idx = f"{start_line}.0", f"{end_line}.end"
        content = text.get(start_idx, end_idx)
        stripped = content.strip()

        if stripped.startswith(open_marker) and stripped.endswith(close_marker):
            open_pos = content.find(open_marker)
            close_pos = content.rfind(close_marker)
            if open_pos == -1 or close_pos == -1 or close_pos <= open_pos:
                return
            inner = content[open_pos + len(open_marker):close_pos]
            if inner.startswith(" "):
                inner = inner[1:]
            if inner.endswith(" "):
                inner = inner[:-1]
            new_content = content[:open_pos] + inner + content[close_pos + len(close_marker):]
        else:
            new_content = f"{open_marker} {content} {close_marker}"

        text.delete(start_idx, end_idx)
        text.insert(start_idx, new_content)

    def toggle_comment(editor=None):
        editor = editor or get_current_editor()
        if not editor:
            return
        style = _comment_style_for_path(editor.get("path"))
        if not style:
            return

        target = _focused_pane(editor)
        text = target["text"]
        start_line, end_line = _comment_target_lines(text)

        # Group the whole toggle (which may be several inserts/deletes
        # across many lines) into a single Ctrl+Z step rather than
        # leaving the user to undo it one line at a time.
        text.config(autoseparators=False)
        text.edit_separator()
        try:
            if "line" in style:
                _toggle_line_comments(text, start_line, end_line, style["line"])
            else:
                open_marker, close_marker = style["block"]
                _toggle_block_comment(text, start_line, end_line, open_marker, close_marker)
        finally:
            text.edit_separator()
            text.config(autoseparators=True)

        mark_dirty(editor)
        if target is editor.get("pane2"):
            sync_split_pane(editor, source="text2")
        _run_editor_heavy_update(editor)

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
            status_lint_label.config(text="")
            highlight_active_file()
            update_tab_indicator()
            return
        refresh_window_title(editor)
        update_line_numbers(editor)
        highlight_syntax(editor)
        highlight_current_line(editor)
        highlight_brackets(editor["text"])
        update_indent_guides(editor)
        render_minimap_content(editor)
        refresh_minimap_heat(editor)
        update_status_bar(editor)
        update_lint_squiggles(editor)
        update_lint_status_label(editor)
        fold = editor.get("fold")
        if fold:
            fold.render()
        pane2 = editor.get("pane2")
        if pane2:
            pane2["fold"].render()
        highlight_active_file()
        update_tab_indicator()
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

    tab_context_menu = ThemedMenu(tab_control, tearoff=0, **menu_opts)

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
        # Same reasoning as the theme-switch relaunch: don't hand the new
        # process this one's PyInstaller onefile temp-extraction paths.
        # _MEIPASS2 (not _MEIPASS - that one's a sys attribute, not an env
        # var) is the actual one that matters: PyInstaller's onefile
        # bootloader sets it so a frozen app's own subprocess can skip
        # re-extracting and reuse the parent's temp folder - which is
        # exactly wrong here, since that folder disappears once the
        # parent exits.
        for var in ("TCL_LIBRARY", "TK_LIBRARY", "_MEIPASS2"):
            env.pop(var, None)
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

    def _remember_recent_folder(folder):
        """Same bookkeeping as _remember_recent_file, but for project
        folders - pushed to front (de-duped), capped, persisted, and the
        Open Recent Folder submenu refreshed to match."""
        if not folder:
            return
        paths = recent_folders_state["paths"]
        paths[:] = [p for p in paths if p != folder]
        paths.insert(0, folder)
        del paths[MAX_RECENT_FOLDERS:]
        save_recent_folders(paths)
        _rebuild_recent_folders_menu()

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
            highlight_current_line(current)
            highlight_brackets(current["text"])
            update_indent_guides(current)
            render_minimap_content(current)
            refresh_minimap_heat(current)
            highlight_active_file()
        else:
            create_tab(path=path, content=content)
        _remember_recent_file(path)
        _notify_plugins_on_open(path, content)

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
            is_dir = os.path.isdir(full_path)

            node = project_tree.insert(
                parent,
                "end",
                text=item,
                open=False,
                values=[full_path],
                image=tree_icon_for(full_path, is_dir)
            )

            if is_dir:
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
            values=[folder],
            image=FOLDER_ICON
        )

        add_directory(root_node, folder)

    def _open_project_folder(folder):
        nonlocal project_path
        project_path = folder
        populate_tree(folder)
        highlight_active_file()
        refresh_git_state()
        _remember_recent_folder(folder)
        _hide_start_page()

    def open_folder():
        folder = filedialog.askdirectory()

        if not folder:
            return

        _open_project_folder(folder)

    # ---------- Drag and drop ----------
    # Only active when tkinterdnd2 is installed (see the optional import at
    # the top of this file) - root is a plain tk.Tk() otherwise, which has
    # no drop_target_register/dnd_bind at all, so this whole block is
    # skipped rather than erroring.
    def _on_files_dropped(event):
        try:
            paths = root.tk.splitlist(event.data)
        except tk.TclError:
            return
        for dropped_path in paths:
            if os.path.isdir(dropped_path):
                _open_project_folder(dropped_path)
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

    # Bumped on every apply_git_status_tags() call so a slow background
    # `git status` that finishes after a newer refresh has already been
    # kicked off (rapid focus-in/focus-out, a save right after a folder
    # switch, etc.) knows to drop its now-stale result instead of painting
    # tags for the wrong project over whatever the newer pass already drew.
    _git_status_tag_state = {"seq": 0}

    def apply_git_status_tags():
        """Recolors explorer rows to reflect `git status` - accent for
        staged files, an attention color for modified-but-unstaged files,
        and a muted-green for untracked ones. Does nothing if project_path
        isn't inside a git repo (or no folder is open at all).

        The actual `git status` call is a subprocess (see git_panel._run)
        and runs on a background thread, the same pattern already used for
        every other git call in this file (refresh_minimap_heat, git_panel's
        own refresh()/do_commit()/etc.) - it used to run straight on the UI
        thread here, which meant every tree refresh, every save, and every
        time the window regained focus (see _on_app_focus_in) froze the
        whole editor for as long as `git status` took, which is very much
        not "cheap enough to call liberally" on a large repo or a slow
        (e.g. network) filesystem."""
        git_tags = ("git_staged", "git_modified", "git_untracked")

        def _clear(node):
            tags = _node_tags(node)
            kept = tuple(t for t in tags if t not in git_tags)
            if kept != tags:
                project_tree.item(node, tags=kept)

        _git_status_tag_state["seq"] += 1
        seq = _git_status_tag_state["seq"]
        path = project_path

        if not path:
            for node in _walk_tree_nodes():
                _clear(node)
            return

        def worker(path=path, seq=seq):
            repo_root = git_panel.find_repo_root(path)
            status = git_panel.get_status(repo_root) if repo_root else None

            def apply():
                if _git_status_tag_state["seq"] != seq:
                    return  # superseded by a newer refresh - drop it
                if not project_tree.winfo_exists():
                    return
                if not repo_root or status.get("error"):
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
                    node_path = os.path.normpath(values[0])
                    if node_path in staged_paths:
                        tag = "git_staged"
                    elif node_path in modified_paths:
                        tag = "git_modified"
                    elif node_path in untracked_paths:
                        tag = "git_untracked"
                    else:
                        continue
                    project_tree.item(node, tags=_node_tags(node) + (tag,))

            root.after(0, apply)

        threading.Thread(target=worker, daemon=True).start()

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
    tree_context_menu = ThemedMenu(project_tree, tearoff=0, **menu_opts)

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
        if editor and save_editor(editor):
            fun_effects.glow(editor["editor_frame"], "#2ecc71")

    def save_as_file():
        editor = get_current_editor()
        if editor and save_editor_as(editor):
            fun_effects.glow(editor["editor_frame"], "#2ecc71")

    # ---------- Run code ----------
    # Runs the file through the same live shell backing the Terminal tab
    # ---------- Run ----------
    # Spawns the program in its own console window (see _spawn_run_console
    # above) - the same handoff Code::Blocks/Dev-C++ do - rather than
    # piping it through an embedded shell. Interactive input (input(),
    # Console.ReadLine(), etc.) just works, since it's a real console.
    # Each entry describes how to go from "a saved file" to "something
    # running", as a dict with a "kind":
    #   "interpret" - run straight through an interpreter: [cmd, filename]
    #   "java"      - javac then java, keyed off the class name (which by
    #                 Java's own rules already has to match the filename
    #                 for a public top-level class)
    #   "browser"   - not run as a process at all; opened in the system's
    #                 default web browser instead
    if IS_WINDOWS:
        RUNNERS = {
            "Python": {"kind": "interpret", "cmd": "python"},
            "JavaScript": {"kind": "interpret", "cmd": "node"},
        }
    else:
        RUNNERS = {
            "Python": {"kind": "interpret", "cmd": "python3"},
            "JavaScript": {"kind": "interpret", "cmd": "node"},
        }
    RUNNERS.update({
        "Java": {"kind": "java"},
        "HTML": {"kind": "browser"},
    })

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

        language = get_language_label(run_path)
        spec = RUNNERS.get(language)
        if not spec:
            messagebox.showinfo("Run", f"Don't know how to run {language} files.")
            return

        run_dir = os.path.dirname(run_path) or _project_cwd()
        filename = os.path.basename(run_path)
        stem = os.path.splitext(filename)[0]

        if spec["kind"] == "browser":
            # HTML isn't a process - just hand it to the system browser and
            # leave the Output panel as-is (no console to wait on, nothing
            # for Kill to terminate).
            try:
                webbrowser.open_new_tab(pathlib.Path(run_path).as_uri())
            except Exception as e:
                messagebox.showerror("Run", f"Couldn't open in browser:\n{e}")
                return
            output_area.config(state="normal")
            output_area.delete("1.0", tk.END)
            output_area.insert("1.0", f"Opened {filename} in your default browser.\n")
            output_area.config(state="disabled")
            bottom_panel.select(output_tab)
            return

        if spec["kind"] == "java":
            steps = [["javac", filename], ["java", stem]]
        else:  # "interpret"
            steps = [[spec["cmd"], filename]]

        output_area.config(state="normal")
        output_area.delete("1.0", tk.END)
        output_area.insert("1.0", f"Running {filename} in a separate window...\n")
        output_area.config(state="disabled")
        bottom_panel.select(output_tab)

        try:
            proc, code_path = _spawn_run_console_multi(steps, run_dir)
        except Exception as e:
            output_area.config(state="normal")
            output_area.insert(tk.END, f"\nFailed to launch: {e}\n")
            output_area.config(state="disabled")
            return

        run_state["proc"] = proc

        def wait_for_exit(p=proc, code_path=code_path):
            p.wait()

            # The wrapper (cmd.exe / terminal emulator) has now closed, so
            # the real exit code - written to code_path right after the
            # program itself finished, before the "press a key" prompt
            # could run - is ready to read. Falls back to None (unknown)
            # if it's missing/unreadable, e.g. the window was killed before
            # the program ever got a chance to run.
            code = None
            try:
                with open(code_path, "r", encoding="utf-8") as f:
                    code = int(f.read().strip())
            except (OSError, ValueError):
                pass
            finally:
                try:
                    os.remove(code_path)
                except OSError:
                    pass

            def report():
                # A newer Run may have started (and finished) while this
                # one's console window was still open - only report if
                # this is still the process anyone would care about.
                if run_state.get("proc") is p:
                    output_area.config(state="normal")
                    shown_code = code if code is not None else "unknown"
                    output_area.insert(tk.END, f"\n[process exited with code {shown_code}]\n")
                    output_area.config(state="disabled")
                    if code == 0:
                        fun_effects.glow(output_frame, "#2ecc71")
                    elif code is not None:
                        fun_effects.glow(output_frame, "#ff5555")

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
        highlight_current_line(editor)
        highlight_brackets(editor["text"])
        update_indent_guides(editor)
        render_minimap_content(editor)
        update_status_bar(editor)
        # update_line_numbers() above may have torn down and reinserted the
        # line-numbers gutter (if the replace changed the line count),
        # which wipes any fold-hidden tag ranges on it - reapply them here
        # so it stays in sync with the text/fold gutter, same as every
        # other update_line_numbers() call site already does.
        fold = editor.get("fold")
        if fold:
            fold.render()

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
        fun_effects.cursor_pulse(text_area, pos, THEME["accent"], THEME["editor_bg"])
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

    # ---------- Settings dialog ----------
    # A single "Preferences" window for the stuff that's otherwise scattered
    # across the View menu (font, theme, minimap/heatmap/scanlines toggles).
    # Font family/size and the toggles apply live as you change them - and
    # now so does theme, via set_theme() -> _apply_theme_live() (no more
    # relaunch, just an in-place recolor of everything already on screen).
    settings_state = {"window": None}

    def _installed_font_choices():
        # Intersect the curated cross-platform shortlist with whatever's
        # actually installed, so the dropdown never offers a font that would
        # silently fall back to Tk's default. Always keep the current
        # family selectable even if it isn't in the curated list or isn't
        # detected as installed (e.g. a hand-edited settings file) - better
        # to show an unusual value than to silently discard it.
        try:
            installed = set(tkfont.families(root))
        except tk.TclError:
            installed = set()
        choices = [f for f in FONT_FAMILY_CHOICES if f in installed] or list(FONT_FAMILY_CHOICES)
        current = font_state["family"]
        if current not in choices:
            choices = [current] + choices
        return choices

    def _build_settings_window():
        win = tk.Toplevel(root)
        win.title("Settings")
        win.resizable(False, False)
        win.transient(root)
        win.config(bg=THEME["app_bg"], padx=14, pady=12)

        label_opts = {"bg": THEME["app_bg"], "fg": THEME["panel_header_fg"]}
        section_opts = {
            "bg": THEME["app_bg"], "fg": THEME["muted_fg"],
            "font": ("Consolas", 9, "bold"),
        }
        check_opts = {
            "bg": THEME["app_bg"], "fg": THEME["panel_header_fg"],
            "activebackground": THEME["app_bg"], "activeforeground": THEME["panel_header_fg"],
            "selectcolor": THEME["editor_bg"], "highlightthickness": 0,
        }
        button_opts = {
            "bg": THEME["panel_header_bg"], "fg": THEME["panel_header_fg"],
            "activebackground": THEME["editor_select_bg"], "activeforeground": THEME["editor_fg"],
            "relief": "flat", "highlightthickness": 0,
        }

        row = 0

        def next_row():
            nonlocal row
            row += 1
            return row

        tk.Label(win, text="EDITOR", **section_opts).grid(
            row=row, column=0, columnspan=3, sticky="w", pady=(0, 4)
        )

        r = next_row()
        tk.Label(win, text="Font family:", **label_opts).grid(row=r, column=0, sticky="w", pady=3)
        font_family_var = tk.StringVar(value=font_state["family"])
        font_family_box = ttk.Combobox(
            win, textvariable=font_family_var, values=_installed_font_choices(),
            state="readonly", style="Settings.TCombobox", width=22,
        )
        font_family_box.grid(row=r, column=1, columnspan=2, sticky="we", pady=3, padx=(8, 0))

        r = next_row()
        tk.Label(win, text="Font size:", **label_opts).grid(row=r, column=0, sticky="w", pady=3)
        font_size_var = tk.IntVar(value=font_state["size"])
        font_size_spin = tk.Spinbox(
            win, from_=MIN_FONT_SIZE, to=MAX_FONT_SIZE, width=5,
            textvariable=font_size_var, justify="center",
            bg=THEME["popup_bg"], fg=THEME["popup_fg"],
            insertbackground=THEME["editor_insert"], relief="flat",
            highlightthickness=1, highlightbackground=THEME["border"],
            highlightcolor=THEME["accent"], buttonbackground=THEME["panel_header_bg"],
        )
        font_size_spin.grid(row=r, column=1, sticky="w", pady=3, padx=(8, 0))

        r = next_row()
        preview_label = tk.Label(
            win, text="AaBbCc 0123  the quick brown fox",
            bg=THEME["output_bg"], fg=THEME["output_fg"],
            anchor="w", padx=8, pady=6,
            font=(font_state["family"], font_state["size"]),
        )
        preview_label.grid(row=r, column=0, columnspan=3, sticky="we", pady=(4, 8))

        def _refresh_preview():
            try:
                size = int(font_size_var.get())
            except (tk.TclError, ValueError):
                return
            preview_label.config(font=(font_family_var.get(), size))

        def _on_font_family_change(*_args):
            set_font_family(font_family_var.get())
            _refresh_preview()

        def _on_font_size_change(*_args):
            try:
                size = int(font_size_var.get())
            except (tk.TclError, ValueError):
                return
            set_font_size(size)
            _refresh_preview()

        font_family_box.bind("<<ComboboxSelected>>", _on_font_family_change)
        font_size_var.trace_add("write", _on_font_size_change)

        tk.Label(win, text="THEME", **section_opts).grid(
            row=next_row(), column=0, columnspan=3, sticky="w", pady=(4, 4)
        )

        r = next_row()
        tk.Label(win, text="Color theme:", **label_opts).grid(row=r, column=0, sticky="w", pady=3)
        theme_display_to_name = {
            THEME_LABELS.get(name, name.replace("_", " ").title()): name
            for name in THEMES
        }
        theme_var = tk.StringVar(
            value=THEME_LABELS.get(THEME_NAME, THEME_NAME.replace("_", " ").title())
        )
        theme_box = ttk.Combobox(
            win, textvariable=theme_var, values=list(theme_display_to_name.keys()),
            state="readonly", style="Settings.TCombobox", width=22,
        )
        theme_box.grid(row=r, column=1, columnspan=2, sticky="we", pady=3, padx=(8, 0))

        def _on_theme_change(*_args):
            chosen = theme_display_to_name.get(theme_var.get())
            if chosen:
                # Applies live via _apply_theme_live() - this window's own
                # colors get swept up in that same pass since it's just
                # another widget in the tree, so it doesn't need to be
                # closed/reopened to pick up the new palette.
                set_theme(chosen)

        theme_box.bind("<<ComboboxSelected>>", _on_theme_change)

        tk.Label(win, text="VIEW", **section_opts).grid(
            row=next_row(), column=0, columnspan=3, sticky="w", pady=(4, 4)
        )

        minimap_var = tk.BooleanVar(value=minimap_state["visible"])
        heatmap_var = tk.BooleanVar(value=git_heatmap_state["visible"])
        crt_var = tk.BooleanVar(value=crt_state["scanlines"])

        def _on_minimap_toggle():
            toggle_minimap()
            minimap_var.set(minimap_state["visible"])

        def _on_heatmap_toggle():
            toggle_git_heatmap()
            heatmap_var.set(git_heatmap_state["visible"])

        def _on_crt_toggle():
            toggle_crt_scanlines()
            crt_var.set(crt_state["scanlines"])

        tk.Checkbutton(
            win, text="Show minimap", variable=minimap_var,
            command=_on_minimap_toggle, **check_opts
        ).grid(row=next_row(), column=0, columnspan=3, sticky="w", pady=2)

        tk.Checkbutton(
            win, text="Show Git change heatmap", variable=heatmap_var,
            command=_on_heatmap_toggle, **check_opts
        ).grid(row=next_row(), column=0, columnspan=3, sticky="w", pady=2)

        tk.Checkbutton(
            win, text="Show CRT scanlines", variable=crt_var,
            command=_on_crt_toggle, **check_opts
        ).grid(row=next_row(), column=0, columnspan=3, sticky="w", pady=2)

        def _reset_defaults():
            font_family_var.set(DEFAULT_FONT_FAMILY)
            font_size_var.set(DEFAULT_FONT_SIZE)
            set_font_family(DEFAULT_FONT_FAMILY)
            set_font_size(DEFAULT_FONT_SIZE)
            _refresh_preview()

        btn_frame = tk.Frame(win, bg=THEME["app_bg"])
        btn_frame.grid(row=next_row(), column=0, columnspan=3, sticky="e", pady=(10, 0))
        tk.Button(btn_frame, text="Reset to Defaults", command=_reset_defaults, **button_opts).pack(
            side="left", padx=(0, 6)
        )
        tk.Button(btn_frame, text="Close", command=lambda: win.withdraw(), **button_opts).pack(
            side="left"
        )

        win.columnconfigure(1, weight=1)
        win.protocol("WM_DELETE_WINDOW", win.withdraw)
        win.bind("<Escape>", lambda e: win.withdraw())

        settings_state["window"] = win

    def open_settings_dialog():
        win = settings_state["window"]
        if win is None or not win.winfo_exists():
            _build_settings_window()
            win = settings_state["window"]
        win.deiconify()
        win.lift()
        win.focus_set()

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

    file_menu = ThemedMenu(root, tearoff=0, **menu_opts)
    file_menu.add_command(label="New Tab", command=new_file, accelerator="Ctrl+N")
    file_menu.add_command(label="New Window", command=new_window, accelerator="Ctrl+Shift+N")
    file_menu.add_command(label="Open File", command=open_file, accelerator="Ctrl+O")
    file_menu.add_command(label="Open Folder", command=open_folder)

    recent_files_menu = ThemedMenu(root, tearoff=0, **menu_opts)

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

    recent_folders_menu = ThemedMenu(root, tearoff=0, **menu_opts)

    def _open_recent_folder(folder):
        if not os.path.isdir(folder):
            messagebox.showerror("Open Recent Folder", f"{folder}\n\nThis folder no longer exists.")
            paths = recent_folders_state["paths"]
            if folder in paths:
                paths.remove(folder)
                save_recent_folders(paths)
                _rebuild_recent_folders_menu()
            return
        _open_project_folder(folder)

    def _clear_recent_folders():
        recent_folders_state["paths"] = []
        save_recent_folders([])
        _rebuild_recent_folders_menu()

    def _rebuild_recent_folders_menu():
        recent_folders_menu.delete(0, tk.END)
        paths = recent_folders_state["paths"]
        if not paths:
            recent_folders_menu.add_command(label="(No Recent Folders)", state="disabled")
            return
        for recent_folder in paths:
            recent_folders_menu.add_command(
                label=recent_folder, command=lambda f=recent_folder: _open_recent_folder(f)
            )
        recent_folders_menu.add_separator()
        recent_folders_menu.add_command(label="Clear Recent Folders", command=_clear_recent_folders)

    _rebuild_recent_folders_menu()
    file_menu.add_cascade(label="Open Recent Folder", menu=recent_folders_menu)

    # ---------------- Start Page ----------------
    # Shown in start_page_frame (built up by tab_control, see above) instead
    # of a blank "Untitled" tab whenever there are zero tabs open. Rebuilt
    # from scratch every time it's shown so its two Recent columns always
    # reflect whatever's newest - the same "just redraw it" approach the
    # Recent Files/Folders menus already take, rather than trying to keep a
    # live view in sync.
    def _start_page_row(parent, icon, primary_text, secondary_text, command):
        row = tk.Frame(parent, bg=THEME["editor_bg"], cursor="hand2")
        row.pack(fill="x", pady=1)

        icon_label = tk.Label(
            row, text=icon, bg=THEME["editor_bg"], fg=THEME["muted_fg"],
            font=("Segoe UI", 11), width=2
        )
        icon_label.pack(side="left", padx=(4, 6))

        text_frame = tk.Frame(row, bg=THEME["editor_bg"])
        text_frame.pack(side="left", fill="both", expand=True)

        primary = tk.Label(
            text_frame, text=primary_text, bg=THEME["editor_bg"],
            fg=THEME["editor_fg"], anchor="w", font=("Segoe UI", 10)
        )
        primary.pack(fill="x")

        widgets = [row, icon_label, text_frame, primary]
        if secondary_text:
            secondary = tk.Label(
                text_frame, text=secondary_text, bg=THEME["editor_bg"],
                fg=THEME["muted_fg"], anchor="w", font=("Segoe UI", 8)
            )
            secondary.pack(fill="x")
            widgets.append(secondary)

        # Hover highlight - every widget in the row swaps together so the
        # whole row reads as one clickable target, not just whichever
        # label the mouse happens to be over.
        def _enter(_event=None):
            for w in widgets:
                try:
                    w.configure(bg=THEME["tree_active_bg"])
                except tk.TclError:
                    pass

        def _leave(_event=None):
            for w in widgets:
                try:
                    w.configure(bg=THEME["editor_bg"])
                except tk.TclError:
                    pass

        for w in widgets:
            w.bind("<Enter>", _enter)
            w.bind("<Leave>", _leave)
            w.bind("<Button-1>", lambda _e: command())

        return row

    def _populate_start_page():
        for child in start_page_frame.winfo_children():
            child.destroy()

        center = tk.Frame(start_page_frame, bg=THEME["editor_bg"])
        # pack(expand=True) centers on the frame's *actual* rendered size,
        # unlike place(relx/rely=..., anchor="center") - which pins the
        # center of a fixed fraction and, if the content turns out taller
        # than expected, happily shoves the top of it above y=0 and off
        # the visible frame instead of just centering what's left.
        center.pack(expand=True)

        tk.Label(
            center, text=_STARTUP_BANNER.strip("\n"), bg=THEME["editor_bg"], fg=THEME["accent"],
            # A NEGATIVE font size is pixels, not points - points get run
            # through Tk's points-per-inch conversion, which scales up
            # with the display's DPI (see _apply_windows_dpi_awareness -
            # this app declares itself DPI-aware so Windows hands Tk the
            # real DPI instead of a virtualized 96). A "6pt" banner could
            # therefore render several times taller than intended on a
            # scaled display, blowing this label's height way past the
            # frame and leaving only its last couple of lines visible.
            # Pixels sidestep that scaling entirely, so the banner is the
            # same physical size in every DPI setting.
            font=("Courier New", -16), justify="left"
        ).pack(anchor="w")

        tk.Label(
            center, text="Start something new, or pick up where you left off.",
            bg=THEME["editor_bg"], fg=THEME["muted_fg"], font=("Segoe UI", 10)
        ).pack(anchor="w", pady=(4, 24))

        columns = tk.Frame(center, bg=THEME["editor_bg"])
        columns.pack(fill="both", expand=True)

        start_col = tk.Frame(columns, bg=THEME["editor_bg"])
        start_col.pack(side="left", anchor="n", padx=(0, 70))

        tk.Label(
            start_col, text="START", bg=THEME["editor_bg"], fg=THEME["muted_fg"],
            font=("Segoe UI", 9, "bold")
        ).pack(anchor="w", pady=(0, 6))

        _start_page_row(start_col, "\U0001F4C4", "New File", "Ctrl+N", new_file)
        _start_page_row(start_col, "\U0001F4C2", "Open File...", "Ctrl+O", open_file)
        _start_page_row(start_col, "\U0001F4C1", "Open Folder...", "", open_folder)

        recent_col = tk.Frame(columns, bg=THEME["editor_bg"])
        recent_col.pack(side="left", anchor="n")

        tk.Label(
            recent_col, text="RECENT FOLDERS", bg=THEME["editor_bg"], fg=THEME["muted_fg"],
            font=("Segoe UI", 9, "bold")
        ).pack(anchor="w", pady=(0, 6))

        recent_folders = recent_folders_state["paths"][:6]
        if recent_folders:
            for folder in recent_folders:
                _start_page_row(
                    recent_col, "\U0001F4C1", os.path.basename(folder.rstrip("/\\")) or folder,
                    folder, lambda f=folder: _open_recent_folder(f)
                )
        else:
            tk.Label(
                recent_col, text="No recent folders", bg=THEME["editor_bg"],
                fg=THEME["muted_fg"], font=("Segoe UI", 9, "italic")
            ).pack(anchor="w")

        tk.Label(
            recent_col, text="RECENT FILES", bg=THEME["editor_bg"], fg=THEME["muted_fg"],
            font=("Segoe UI", 9, "bold")
        ).pack(anchor="w", pady=(18, 6))

        recent_files = recent_files_state["paths"][:6]
        if recent_files:
            for path in recent_files:
                _start_page_row(
                    recent_col, "\U0001F4C4", os.path.basename(path) or path,
                    path, lambda p=path: _open_recent(p)
                )
        else:
            tk.Label(
                recent_col, text="No recent files", bg=THEME["editor_bg"],
                fg=THEME["muted_fg"], font=("Segoe UI", 9, "italic")
            ).pack(anchor="w")

    def _show_start_page():
        # Not winfo_ismapped()-gated on purpose: that flag isn't reliable
        # before the window's ever actually been drawn (the very first
        # call here happens pre-mainloop, during startup), so it can read
        # False for a widget that's genuinely packed and about to show.
        # Trusting it meant tab_control's pack_forget() got skipped on
        # first launch, leaving an empty notebook visibly stacked above
        # the Start Page instead of hidden. pack_forget() on an already-
        # unmanaged widget (and pack() on an already-managed one) are both
        # harmless no-ops, so there's nothing to gain from checking first.
        tab_control.pack_forget()
        _populate_start_page()
        start_page_frame.pack(fill="both", expand=True)

    def _hide_start_page():
        start_page_frame.pack_forget()
        tab_control.pack(fill="both", expand=True)

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

    def _apply_theme_live(new_theme_name):
        """Re-themes the whole running app in place - no relaunch, no
        save-and-reopen dance, and critically no window destroy/recreate,
        which is what caused the visible minimize/maximize flicker the
        old relaunch-based switch had.

        Every widget in this app is colored with a literal value pulled
        from THEME[...] at creation time rather than a live reference, so
        "switch theme" comes down to two kinds of refresh:
          - ttk-styled widgets (Treeview, tabs, scrollbars, comboboxes)
            and Text tag colors (syntax highlighting, current line,
            brackets, search, line-number glow) aren't reachable through
            plain widget options at all - those get fixed by re-running
            the same setup functions that configured them from THEME the
            first time, now reading the new palette.
          - every other plain tk widget (the hundreds of Frames/Labels/
            Buttons/etc. scattered across app.py, git_panel.py, and
            music_player.py) gets fixed generically: build a map from
            every old literal color value to its new counterpart, then
            walk the whole widget tree swapping any matching option.
        """
        global THEME_NAME
        if new_theme_name == THEME_NAME or new_theme_name not in THEMES:
            return

        old_theme_snapshot = dict(THEME)
        new_theme = THEMES[new_theme_name]
        remap = _build_color_remap(old_theme_snapshot, new_theme)

        THEME.clear()
        THEME.update(new_theme)
        THEME_NAME = new_theme_name

        save_theme_preference(new_theme_name)
        _apply_windows_dark_titlebar(root, is_dark_theme(new_theme_name))

        # ttk styles, menu popup colors, and the explorer's git/active-file
        # tag colors all live outside the plain-widget-option world the
        # generic remap below can reach.
        _apply_ttk_styles()
        _apply_project_tree_theme()
        menu_opts.update({
            "bg": THEME["panel_header_bg"],
            "fg": THEME["panel_header_fg"],
            "activebackground": THEME["editor_select_bg"],
            "activeforeground": THEME["editor_select_fg"],
            "disabledforeground": THEME["muted_fg"],
            "border": THEME["popup_border"],
        })
        ThemedMenu.close_all()
        ThemedMenu.retheme_all(menu_opts)
        _rebuild_theme_menu()

        # Every plain tk widget anywhere in the app (this window, any open
        # dialogs, the git/music panels, etc.), recolored by literal-value
        # swap rather than needing each one's creation site touched.
        root.config(bg=THEME["app_bg"])
        _remap_widget_colors(root, remap)

        # Text-tag colors aren't widget options, so the generic remap
        # above can't see them - each open editor pane needs its tag
        # setup and canvas-drawn overlays (minimap, indent guides, lint
        # squiggles) redone against the new THEME.
        for editor in tab_editors.values():
            setup_highlight_tags(editor["text"])
            setup_line_number_tags(editor["line_numbers"])
            highlight_syntax(editor)
            highlight_current_line(editor)
            highlight_brackets(editor["text"])
            update_indent_guides(editor)
            update_lint_squiggles(editor)
            render_minimap_content(editor)
            pane2 = editor.get("pane2")
            if pane2 is not None:
                setup_highlight_tags(pane2["text"])
                setup_line_number_tags(pane2["line_numbers"])

        status_theme_label.config(
            text="\U0001F3A8 " + THEME_LABELS.get(THEME_NAME, THEME_NAME.title())
        )

    def cycle_theme():
        # Steps to the next theme in THEMES' definition order, wrapping
        # back to the first after the last - this is what the status-bar
        # click and the Ctrl+Shift+D shortcut use so they keep working as
        # a quick "next theme" action now that there are more than two.
        names = list(THEMES.keys())
        idx = names.index(THEME_NAME)
        new_theme_name = names[(idx + 1) % len(names)]
        _apply_theme_live(new_theme_name)

    def set_theme(name):
        if name == THEME_NAME:
            return
        _apply_theme_live(name)

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

    edit_menu = ThemedMenu(root, tearoff=0, **menu_opts)
    edit_menu.add_command(label="Find...", command=lambda: open_find_replace("find"), accelerator="Ctrl+F")
    edit_menu.add_command(label="Replace...", command=lambda: open_find_replace("replace"), accelerator="Ctrl+H")
    edit_menu.add_separator()
    edit_menu.add_command(label="Toggle Line Comment", command=lambda: toggle_comment(), accelerator="Ctrl+/")

    run_menu = ThemedMenu(root, tearoff=0, **menu_opts)
    run_menu.add_command(label="Run", command=run_code, accelerator="F5")
    run_menu.add_command(label="Kill", command=kill_running)
    run_menu.add_separator()
    run_menu.add_command(label="Clear Output", command=clear_output, accelerator="Ctrl+K")

    view_menu = ThemedMenu(root, tearoff=0, **menu_opts)
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

    view_menu.add_command(
        label="Enable Word Wrap", command=toggle_word_wrap, accelerator="Alt+Z"
    )
    word_wrap_menu_index = view_menu.index(tk.END)

    view_menu.add_separator()
    view_menu.add_command(
        label="Split Editor Right", command=lambda: split_editor(), accelerator="Ctrl+\\"
    )
    view_menu.add_command(label="Close Split", command=lambda: close_split())
    view_menu.add_separator()
    view_menu.add_command(
        label="Toggle Fold", command=lambda: toggle_fold_at_cursor(), accelerator="Ctrl+Shift+["
    )
    view_menu.add_command(label="Fold All", command=lambda: fold_all_current(), accelerator="Ctrl+Alt+[")
    view_menu.add_command(label="Unfold All", command=lambda: unfold_all_current(), accelerator="Ctrl+Alt+]")

    def toggle_git_heatmap():
        git_heatmap_state["visible"] = not git_heatmap_state["visible"]
        for ed in tab_editors.values():
            if git_heatmap_state["visible"]:
                refresh_minimap_heat(ed)
            else:
                render_minimap_content(ed)
        view_menu.entryconfig(
            git_heatmap_menu_index,
            label="Hide Git Heatmap" if git_heatmap_state["visible"] else "Show Git Heatmap"
        )

    view_menu.add_command(label="Hide Git Heatmap", command=toggle_git_heatmap)
    git_heatmap_menu_index = view_menu.index(tk.END)

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
    # re-themes the app live.
    theme_menu = ThemedMenu(root, tearoff=0, **menu_opts)

    def _rebuild_theme_menu():
        theme_menu.delete(0, tk.END)
        for theme_name in THEMES:
            label = THEME_LABELS.get(theme_name, theme_name.replace("_", " ").title())
            if theme_name == THEME_NAME:
                label = "\u2713 " + label
            theme_menu.add_command(label=label, command=lambda n=theme_name: set_theme(n))

    _rebuild_theme_menu()
    view_menu.add_cascade(label="Theme", menu=theme_menu)
    view_menu.add_command(
        label="Next Theme",
        command=cycle_theme,
        accelerator="Ctrl+Shift+D"
    )
    view_menu.add_separator()
    view_menu.add_command(
        label="Command Palette...",
        command=lambda: open_command_palette(),
        accelerator="Ctrl+Shift+P"
    )
    view_menu.add_command(
        label="Go to Line/Symbol...",
        command=lambda: open_goto(),
        accelerator="Ctrl+P"
    )

    settings_menu = ThemedMenu(root, tearoff=0, **menu_opts)
    settings_menu.add_command(
        label="Preferences...",
        command=open_settings_dialog,
        accelerator="Ctrl+,"
    )

    # ---------------- Plugins ----------------
    # A basic, best-effort plugin system - see plugins.py for the actual
    # file discovery/loading and the PluginAPI class docstrings for what
    # a plugin can do. Everything below is just the app.py side of that
    # contract: the callables a PluginAPI needs, the Plugins menu itself,
    # and the on_save/on_open hook lists that save_editor/save_editor_as/
    # _open_path_in_tab (defined earlier) already call into by name.
    _plugin_save_callbacks = []
    _plugin_open_callbacks = []
    _plugin_commands = []   # [(label, safe_callback), ...] - see _plugin_register_command
    _plugin_load_results = []  # [{"name", "path", "error"}, ...] - see plugins.load_plugins

    def _notify_plugins_on_save(path, content):
        for callback in _plugin_save_callbacks:
            try:
                callback(path, content)
            except Exception:
                # A plugin's own hook misbehaving should never be able to
                # break the save it's reacting to, or stop any other
                # plugin's hook in this same list from running - same
                # "degrade quietly" convention as the rest of the app.
                # Unlike a menu command the user just clicked on purpose
                # (see _plugin_register_command below), there's no good
                # place to surface this to the user, so it's silent.
                pass

    def _notify_plugins_on_open(path, content):
        for callback in _plugin_open_callbacks:
            try:
                callback(path, content)
            except Exception:
                pass

    plugins_menu = ThemedMenu(root, tearoff=0, **menu_opts)

    def _open_plugins_folder():
        plugins.ensure_plugin_dir()
        reveal_in_file_explorer(plugins.PLUGIN_DIR)

    def _show_plugin_errors():
        errors = [r for r in _plugin_load_results if r["error"]]
        if not errors:
            messagebox.showinfo("Plugin Errors", "No plugin errors - everything loaded cleanly.")
            return
        win = tk.Toplevel(root)
        win.title("Plugin Errors")
        win.geometry("700x400")
        win.config(bg=THEME["output_bg"])
        box = tk.Text(
            win, wrap="word", bg=THEME["output_bg"], fg=THEME["output_fg"],
            insertbackground=THEME["output_fg"], relief="flat", padx=10, pady=10,
        )
        box.pack(fill="both", expand=True)
        text = "\n\n".join(f"{r['name']} ({r['path']}):\n{r['error']}" for r in errors)
        box.insert("1.0", text)
        box.config(state="disabled")

    def _plugin_register_command(label, callback):
        def safe_callback(cb=callback, label=label):
            try:
                cb()
            except Exception:
                # Unlike on_save/on_open hooks (which fire in the
                # background, unasked, as a side effect of something
                # else), this only runs when the user deliberately picked
                # the command - so a failure here is worth telling them
                # about rather than swallowing silently.
                messagebox.showerror(
                    "Plugin Error",
                    f"'{label}' raised an error:\n\n{traceback.format_exc()}"
                )
        _plugin_commands.append((label, safe_callback))

    def _plugin_get_current_text():
        editor = get_current_editor()
        return editor["text"].get("1.0", "end-1c") if editor else None

    def _plugin_get_current_path():
        editor = get_current_editor()
        return editor["path"] if editor else None

    def _plugin_insert_text(text):
        editor = get_current_editor()
        if editor:
            editor["text"].insert("insert", text)

    def _plugin_get_theme():
        return dict(THEME)

    plugin_api = plugins.PluginAPI(
        register_command=_plugin_register_command,
        add_on_save=_plugin_save_callbacks.append,
        add_on_open=_plugin_open_callbacks.append,
        get_current_text=_plugin_get_current_text,
        get_current_path=_plugin_get_current_path,
        insert_text=_plugin_insert_text,
        show_message=show_status_message,
        get_theme=_plugin_get_theme,
    )

    def _rebuild_plugins_menu():
        plugins_menu.delete(0, tk.END)
        plugins_menu.add_command(label="Open Plugins Folder", command=_open_plugins_folder)
        plugins_menu.add_command(label="Reload Plugins", command=_reload_plugins)
        error_count = sum(1 for r in _plugin_load_results if r["error"])
        if error_count:
            plugins_menu.add_command(
                label=f"Show Plugin Errors ({error_count})...",
                command=_show_plugin_errors,
            )
        if _plugin_commands or error_count:
            plugins_menu.add_separator()
        for label, safe_callback in _plugin_commands:
            plugins_menu.add_command(label=label, command=safe_callback)
        for result in _plugin_load_results:
            if result["error"]:
                plugins_menu.add_command(
                    label=f"\u26A0 {result['name']} (failed to load)", state="disabled"
                )

    def _load_all_plugins():
        # Rebuilding these from scratch (rather than trying to diff old
        # vs. new) keeps Reload Plugins simple and always correct, the
        # same reasoning refresh_tree() uses for the explorer - the only
        # cost is that a plugin's on_save/on_open registrations and menu
        # commands all get re-registered from a clean slate every time,
        # which is exactly what "reload" should do anyway.
        _plugin_commands.clear()
        _plugin_save_callbacks.clear()
        _plugin_open_callbacks.clear()
        _plugin_load_results.clear()
        _plugin_load_results.extend(plugins.load_plugins(plugin_api))
        _rebuild_plugins_menu()

    def _reload_plugins():
        _load_all_plugins()
        show_status_message(f"Reloaded plugins ({len(_plugin_load_results)} found).")

    _load_all_plugins()

    for label, dropdown in (
        ("File", file_menu),
        ("Edit", edit_menu),
        ("Run", run_menu),
        ("View", view_menu),
        ("Settings", settings_menu),
        ("Plugins", plugins_menu),
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
    root.bind("<Control-p>", lambda e: open_goto())
    root.bind("<Control-grave>", lambda e: open_external_terminal())
    root.bind("<Control-comma>", lambda e: open_settings_dialog())
    root.bind("<Control-Shift-D>", lambda e: cycle_theme())
    root.bind("<Control-Shift-d>", lambda e: cycle_theme())
    root.bind("<Control-plus>", lambda e: zoom_in())
    root.bind("<Control-equal>", lambda e: zoom_in())
    root.bind("<Control-KP_Add>", lambda e: zoom_in())
    root.bind("<Control-minus>", lambda e: zoom_out())
    root.bind("<Control-KP_Subtract>", lambda e: zoom_out())
    root.bind("<Control-0>", lambda e: zoom_reset())
    root.bind("<Alt-z>", lambda e: toggle_word_wrap())
    root.bind("<Alt-Z>", lambda e: toggle_word_wrap())
    root.bind("<Control-backslash>", lambda e: split_editor())
    root.bind("<Control-Shift-bracketleft>", lambda e: toggle_fold_at_cursor())
    root.bind("<Control-Alt-bracketleft>", lambda e: fold_all_current())
    root.bind("<Control-Alt-bracketright>", lambda e: unfold_all_current())
    root.bind("<Control-KP_0>", lambda e: zoom_reset())
    root.bind("<Control-m>", lambda e: toggle_minimap())
    root.bind("<Control-Shift-Z>", lambda e: toggle_zen_mode())
    root.bind("<Control-Shift-z>", lambda e: toggle_zen_mode())
    root.bind("<Control-Shift-F>", lambda e: toggle_focus_session())
    root.bind("<Control-Shift-f>", lambda e: toggle_focus_session())
    root.bind("<Control-Shift-P>", lambda e: open_command_palette())
    root.bind("<Control-Shift-p>", lambda e: open_command_palette())

    # ---------- Command Palette ----------
    # Ctrl+Shift+P, VS Code style: a fuzzy-searchable list of every live
    # menu command. Rather than maintaining a second hand-written list of
    # "all the things you can do" alongside File/Edit/Run/View (which
    # would inevitably drift out of sync as menu items are added/renamed),
    # this walks the real tk.Menu objects at open-time and invokes real
    # menu entries - so anything that shows up in a menu shows up here
    # automatically, always current, always doing exactly what clicking
    # it would do.
    command_palette_state = {"window": None, "entry": None, "listbox": None,
                              "commands": [], "filtered": []}

    def _collect_menu_commands(menu, prefix=""):
        """Walks one ThemedMenu (recursing into cascades/submenus) and
        returns [(label, callable), ...] for every enabled, non-separator
        entry. ThemedMenu is this app's own hand-rolled menu widget (see
        the ThemedMenu class near the top of run()) - it keeps its
        entries as a plain list of dicts on `.items` rather than being a
        real tk.Menu, so this reads that list directly instead of using
        tk.Menu's index()/type()/entrycget()/invoke() API, which
        ThemedMenu doesn't implement."""
        commands = []
        for item in getattr(menu, "items", []):
            item_type = item.get("type")
            if item_type == "separator":
                continue
            label = item.get("label")
            if not label:
                continue
            full_label = prefix + label
            if item_type == "cascade":
                submenu = item.get("menu")
                if submenu is not None:
                    commands.extend(_collect_menu_commands(submenu, prefix=full_label + ": "))
                continue
            if item.get("state") == "disabled":
                continue
            command = item.get("command")
            if command is None:
                continue
            commands.append((full_label, command))
        return commands

    def _all_palette_commands():
        commands = []
        for prefix, menu in (
            ("File", file_menu), ("Edit", edit_menu),
            ("Run", run_menu), ("View", view_menu),
            ("Settings", settings_menu), ("Plugins", plugins_menu),
        ):
            commands.extend(_collect_menu_commands(menu, prefix=prefix + ": "))
        return commands

    def _fuzzy_score(query, text):
        """Subsequence fuzzy match (VS Code palette style): every
        character of `query` must appear in `text`, in order, case-
        insensitively. Returns None on no match; otherwise a score where
        lower means a tighter match (consecutive/early hits beat
        scattered ones), so results sort with the most obviously-intended
        command first."""
        if not query:
            return 0
        q = query.lower()
        t = text.lower()
        search_from = 0
        score = 0
        last_match = -1
        for ch in q:
            idx = t.find(ch, search_from)
            if idx == -1:
                return None
            score += idx - last_match - 1
            last_match = idx
            search_from = idx + 1
        return score

    def _filter_palette(*_args):
        query = command_palette_state["entry"].get().strip()
        scored = []
        for label, command in command_palette_state["commands"]:
            score = _fuzzy_score(query, label)
            if score is not None:
                scored.append((score, label, command))
        scored.sort(key=lambda t: (t[0], t[1]))
        command_palette_state["filtered"] = scored

        listbox = command_palette_state["listbox"]
        listbox.delete(0, tk.END)
        for _, label, _ in scored[:200]:
            listbox.insert(tk.END, label)
        if scored:
            listbox.selection_set(0)

    def _move_palette_selection(delta):
        listbox = command_palette_state["listbox"]
        size = listbox.size()
        if size == 0:
            return
        current = listbox.curselection()
        i = current[0] if current else -1
        i = min(max(i + delta, 0), size - 1)
        listbox.selection_clear(0, tk.END)
        listbox.selection_set(i)
        listbox.see(i)

    def close_command_palette():
        win = command_palette_state["window"]
        if win is not None and win.winfo_exists():
            win.destroy()
        command_palette_state["window"] = None

    def _run_selected_palette_command(event=None):
        listbox = command_palette_state["listbox"]
        selection = listbox.curselection()
        if not selection:
            return "break"
        _, _, command = command_palette_state["filtered"][selection[0]]
        close_command_palette()
        # A short defer so the palette window is fully torn down (and
        # focus restored to the main window) before the command runs -
        # some commands (Find, Save As, ...) open their own window and
        # want to grab focus cleanly rather than fight the closing popup.
        root.after(10, command)
        return "break"

    def _palette_focus_out(event, win):
        def check(win=win):
            if command_palette_state["window"] is not win or not win.winfo_exists():
                return
            # Creating the window and handing focus to its entry causes a
            # spurious FocusOut on the window itself on some platforms
            # (focus briefly "leaves" the bare toplevel as it's handed to
            # the entry inside it) - ignore anything in the first moment
            # after opening so that doesn't immediately close the palette
            # before the person even sees it.
            if time.time() - command_palette_state.get("opened_at", 0) < 0.25:
                return
            focused = root.focus_get()
            if focused is None or not str(focused).startswith(str(win)):
                close_command_palette()
        win.after(80, check)

    def open_command_palette():
        existing = command_palette_state["window"]
        if existing is not None and existing.winfo_exists():
            command_palette_state["entry"].focus_set()
            return

        win = tk.Toplevel(root)
        win.overrideredirect(True)
        win.config(bg=THEME["border"])
        win.transient(root)

        frame = tk.Frame(win, bg=THEME["popup_bg"])
        frame.pack(padx=1, pady=1, fill="both", expand=True)

        entry = tk.Entry(
            frame, font=("Consolas", 12),
            bg=THEME["popup_bg"], fg=THEME["popup_fg"],
            insertbackground=THEME["popup_fg"],
            relief="flat", highlightthickness=0, bd=0,
        )
        entry.pack(fill="x", padx=10, pady=8)

        listbox = tk.Listbox(
            frame, bg=THEME["popup_bg"], fg=THEME["popup_fg"],
            selectbackground=THEME["popup_select_bg"], selectforeground=THEME["popup_select_fg"],
            relief="flat", highlightthickness=0, activestyle="none",
            height=12, font=("Consolas", 10),
        )
        listbox.pack(fill="both", expand=True, padx=1, pady=(0, 1))

        command_palette_state.update({
            "window": win, "entry": entry, "listbox": listbox,
            "commands": _all_palette_commands(), "filtered": [],
            "opened_at": time.time(),
        })

        def _position_palette():
            if not win.winfo_exists():
                return
            win.update_idletasks()
            w, h = 480, 320
            # Relative to the app's own window, not the primary screen -
            # winfo_screenwidth() reports the primary monitor only, so on
            # a multi-monitor setup with the app on a different monitor
            # that centered on the wrong screen entirely.
            x = root.winfo_rootx() + max(0, (root.winfo_width() - w) // 2)
            y = root.winfo_rooty() + max(0, int(root.winfo_height() * 0.12))
            win.geometry(f"{w}x{h}+{x}+{y}")

        _position_palette()
        win.lift()
        win.attributes("-topmost", True)
        # Overrideredirect windows on Windows frequently ignore the very
        # first geometry() call made before the window is actually
        # realized/mapped, landing at whatever default position the OS
        # picks instead - reasserting it once more a tick later is what
        # actually sticks.
        win.after(10, _position_palette)

        def on_entry_key(event):
            # Navigation/execution keys are handled by their own specific
            # bindings below - re-filtering on their KeyRelease too would
            # just redo the same query pointlessly.
            if event.keysym in ("Up", "Down", "Return", "Escape"):
                return
            _filter_palette()

        entry.bind("<KeyRelease>", on_entry_key)
        entry.bind("<Down>", lambda e: (_move_palette_selection(1), "break")[1])
        entry.bind("<Up>", lambda e: (_move_palette_selection(-1), "break")[1])
        entry.bind("<Return>", _run_selected_palette_command)
        entry.bind("<Escape>", lambda e: close_command_palette())
        listbox.bind("<Double-Button-1>", _run_selected_palette_command)
        win.bind("<FocusOut>", lambda e, w=win: _palette_focus_out(e, w))

        _filter_palette()
        # A raw focus_set() called this early can be a no-op on some
        # platforms if the window hasn't actually been mapped by the WM
        # yet - deferring one tick makes sure it lands.
        win.after(10, entry.focus_set)

    # ---------- Go to Line / Symbol ----------
    # Same overrideredirect popup + fuzzy-score-and-filter shape as the
    # Command Palette above, just pointed at a different list: symbols
    # parsed out of the current file (via goto.extract_symbols) instead
    # of menu commands. A query that's just digits (optionally prefixed
    # with ":", so ":42" also works like most editors' goto-line
    # shortcut) jumps straight to that line number instead of fuzzy-
    # matching symbol names - the two modes share one popup rather than
    # needing a separate dialog each, since "jump somewhere in this file"
    # is really one feature with two ways of describing the destination.
    goto_state = {"window": None, "entry": None, "listbox": None,
                  "symbols": [], "filtered": []}

    def _goto_line_count():
        editor = get_current_editor()
        if not editor:
            return 1
        try:
            return int(editor["text"].index("end-1c").split(".")[0])
        except tk.TclError:
            return 1

    def _jump_to_line(line, editor=None):
        editor = editor or get_current_editor()
        if not editor:
            return
        text_area = editor["text"]
        # A leftover multi-cursor selection from before Goto was opened
        # would otherwise keep intercepting every keystroke (see the <Key>
        # binding in bind_multicursor) and inserting at those old
        # positions instead of the line just jumped to - clicking
        # elsewhere in the editor already clears this (see on_click), so
        # jumping via Goto should too.
        mc = editor.get("multi_cursor")
        if mc and mc.get("clear"):
            mc["clear"]()
        max_line = _goto_line_count()
        line = min(max(1, line), max_line)
        index = f"{line}.0"
        text_area.mark_set("insert", index)
        text_area.see(index)
        # Center-ish rather than just "on screen" - a line freshly jumped
        # to via this popup is the thing the person is about to look at
        # in detail, not just something scrolled past, so it's worth the
        # extra half-page nudge over a bare .see().
        text_area.update_idletasks()
        try:
            text_area.yview(f"{index} -{text_area.winfo_height() // 40} lines")
        except tk.TclError:
            pass
        # focus_set() only updates Tk's internal bookkeeping of which
        # widget should have focus - it assumes the containing toplevel
        # already has real OS-level keyboard focus. The Goto popup is an
        # overrideredirect() window (no window-manager decoration), and
        # those are notorious for leaving the OS's actual keyboard focus
        # stranded on them (or on nothing) even after being destroyed, so
        # focus_set() alone can leave the editor with no visible/blinking
        # cursor and no way to type - focus_force() forces real input
        # focus back, not just Tk's internal notion of it.
        text_area.focus_force()
        fun_effects.cursor_pulse(text_area, index, THEME["accent"], THEME["editor_bg"])

    def _filter_goto(*_args):
        query = goto_state["entry"].get().strip()
        listbox = goto_state["listbox"]
        listbox.delete(0, tk.END)

        stripped = query[1:] if query.startswith(":") else query
        if stripped.isdigit():
            goto_state["filtered"] = [("line", int(stripped), None)]
            listbox.insert(tk.END, f"Go to line {stripped}")
            listbox.selection_set(0)
            return

        if not query and not goto_state["symbols"]:
            goto_state["filtered"] = []
            listbox.insert(tk.END, "(no symbols in this file - type a line number)")
            return

        scored = []
        for sym in goto_state["symbols"]:
            score = _fuzzy_score(query, sym["name"])
            if score is not None:
                scored.append((score, sym))
        scored.sort(key=lambda t: (t[0], t[1]["line"]))

        filtered = []
        for _, sym in scored[:200]:
            label = ("  " * sym["indent"]) + f"{sym['kind']} {sym['name']}" + f"   :{sym['line']}"
            listbox.insert(tk.END, label)
            filtered.append(("symbol", sym["line"], sym))
        goto_state["filtered"] = filtered
        if filtered:
            listbox.selection_set(0)

    def close_goto_popup():
        win = goto_state["window"]
        if win is not None and win.winfo_exists():
            win.destroy()
        goto_state["window"] = None
        # Escape / click-away destroy the popup without ever landing focus
        # back on the editor, leaving typing (and the blinking cursor)
        # dead - and since this popup is an overrideredirect() window,
        # destroying it doesn't reliably hand real OS keyboard focus back
        # to the main window on its own. focus_force() (not focus_set())
        # reclaims actual input focus so every dismissal path (Escape,
        # focus-out, and a real selection) ends up back in the editor.
        editor = get_current_editor()
        if editor and editor["text"].winfo_exists():
            editor["text"].focus_force()

    def _goto_selected(event=None):
        listbox = goto_state["listbox"]
        selection = listbox.curselection()
        if not selection:
            return "break"
        _, line, _ = goto_state["filtered"][selection[0]]
        close_goto_popup()
        root.after(10, lambda: _jump_to_line(line))
        return "break"

    def _goto_focus_out(event, win):
        def check(win=win):
            if goto_state["window"] is not win or not win.winfo_exists():
                return
            if time.time() - goto_state.get("opened_at", 0) < 0.25:
                return
            focused = root.focus_get()
            if focused is None or not str(focused).startswith(str(win)):
                close_goto_popup()
        win.after(80, check)

    def open_goto():
        editor = get_current_editor()
        if not editor:
            return

        existing = goto_state["window"]
        if existing is not None and existing.winfo_exists():
            goto_state["entry"].focus_force()
            return

        win = tk.Toplevel(root)
        win.overrideredirect(True)
        win.config(bg=THEME["border"])
        win.transient(root)

        frame = tk.Frame(win, bg=THEME["popup_bg"])
        frame.pack(padx=1, pady=1, fill="both", expand=True)

        entry = tk.Entry(
            frame, font=("Consolas", 12),
            bg=THEME["popup_bg"], fg=THEME["popup_fg"],
            insertbackground=THEME["popup_fg"],
            relief="flat", highlightthickness=0, bd=0,
        )
        entry.pack(fill="x", padx=10, pady=8)

        listbox = tk.Listbox(
            frame, bg=THEME["popup_bg"], fg=THEME["popup_fg"],
            selectbackground=THEME["popup_select_bg"], selectforeground=THEME["popup_select_fg"],
            relief="flat", highlightthickness=0, activestyle="none",
            height=12, font=("Consolas", 10),
        )
        listbox.pack(fill="both", expand=True, padx=1, pady=(0, 1))

        symbols = goto.extract_symbols(editor.get("path"), editor["text"].get("1.0", "end-1c"))
        goto_state.update({
            "window": win, "entry": entry, "listbox": listbox,
            "symbols": symbols, "filtered": [],
            "opened_at": time.time(),
        })

        def _position_goto():
            if not win.winfo_exists():
                return
            win.update_idletasks()
            w, h = 480, 320
            x = root.winfo_rootx() + max(0, (root.winfo_width() - w) // 2)
            y = root.winfo_rooty() + max(0, int(root.winfo_height() * 0.12))
            win.geometry(f"{w}x{h}+{x}+{y}")

        _position_goto()
        win.lift()
        win.attributes("-topmost", True)
        win.after(10, _position_goto)

        def on_entry_key(event):
            if event.keysym in ("Up", "Down", "Return", "Escape"):
                return
            _filter_goto()

        def _move_goto_selection(delta):
            size = listbox.size()
            if size == 0:
                return
            current = listbox.curselection()
            i = current[0] if current else -1
            i = min(max(i + delta, 0), size - 1)
            listbox.selection_clear(0, tk.END)
            listbox.selection_set(i)
            listbox.see(i)

        entry.bind("<KeyRelease>", on_entry_key)
        entry.bind("<Down>", lambda e: (_move_goto_selection(1), "break")[1])
        entry.bind("<Up>", lambda e: (_move_goto_selection(-1), "break")[1])
        entry.bind("<Return>", _goto_selected)
        entry.bind("<Escape>", lambda e: close_goto_popup())
        listbox.bind("<Double-Button-1>", _goto_selected)
        win.bind("<FocusOut>", lambda e, w=win: _goto_focus_out(e, w))

        _filter_goto()
        # focus_set() assumes the popup's toplevel already has real OS
        # keyboard focus - for an overrideredirect() window like this one,
        # that's not guaranteed, and without it the popup can end up
        # never actually receiving keystrokes (and the focus-out check
        # above can then see focus as having left immediately and close
        # the popup on its own). focus_force() claims real input focus.
        win.after(10, entry.focus_force)

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
    # meant to start fresh alongside whatever's already open (the Start
    # Page below), not clone it.
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
        _show_start_page()
    else:
        active_path = session.get("active_path")
        active_tab = find_tab_for_path(active_path) if active_path else None
        if active_tab:
            tab_control.select(active_tab)
        highlight_active_file()

    _tick_session_timer()

    # ---------------- Fun extras: easter egg + idle mascot ----------------
    def _konami_triggered():
        status_streak_label.config(text="\U0001F389 KONAMI!")
        root.after(3000, lambda: status_streak_label.config(text=streak_tracker.display()))

    fun_effects.install_konami_code(root, _konami_triggered)

    def _idle_mascot_target():
        ed = get_current_editor()
        return ed["editor_frame"] if ed else None

    fun_effects.install_idle_mascot(root, _idle_mascot_target, THEME)

    root.mainloop()


if __name__ == "__main__":
    # Lets app.py work as a standalone entry point (which is what the
    # PyInstaller build targets) in addition to being imported as
    # `from editor import app` by a separate main.py - this guard simply
    # doesn't fire in that import case, so both paths keep working.
    run()