"""plugins.py - a small, best-effort plugin system for CodeForge.

A plugin is just a plain .py file dropped into PLUGIN_DIR (created
automatically the first time it's needed - see ensure_plugin_dir). Each
file gets imported once at startup (and again on demand via the Plugins
menu's "Reload Plugins"), and if it defines a top-level

    def setup(api):
        ...

function, that's called with a PluginAPI instance - the *only* surface a
plugin talks to the rest of the app through. Everything a plugin can do
goes through that object rather than reaching into app.py's internals
directly, so app.py's actual tab/editor/menu implementation stays free
to change shape later without every existing plugin breaking.

Design goals, matching the rest of this codebase:
  - No new dependencies - just the standard library (importlib).
  - Degrade quietly: a plugin that fails to import, or whose setup()
    raises, is skipped - with the error recorded so the Plugins menu can
    surface it - rather than taking the whole app down. One broken
    plugin can never stop the others, or CodeForge itself, from
    starting. Same philosophy as linters.py/goto.py/code_folding.py:
    a plugin failure is a nice-to-have missing, not a crash.
  - No sandboxing whatsoever: a plugin is a plain Python file running
    with CodeForge's own permissions, the same trust model as a VS Code
    extension or a Sublime Text plugin. This module only handles
    discovery/loading/the API surface - it does not and cannot protect
    against a plugin doing something malicious. Only install plugins you
    trust.
"""

import importlib.util
import os
import sys
import traceback

PLUGIN_DIR = os.path.join(os.path.expanduser("~"), ".codeforge", "plugins")

_README_TEXT = """CodeForge plugins
==================

Drop a .py file in this folder (or use Plugins > Open Plugins Folder to
get here) and then Plugins > Reload Plugins (or just restart CodeForge)
to load it.

A plugin is just a Python file with a setup(api) function:

    def setup(api):
        api.register_command("Say Hello", lambda: api.show_message("Hello!"))

`api` is a PluginAPI instance - see plugins.py's PluginAPI class for
everything available:

    api.register_command(label, callback)   add a Plugins-menu command
                                             (also shows up in the
                                             Ctrl+Shift+P command palette)
    api.on_save(callback)                   callback(path, content) after
                                             any file is saved
    api.on_open(callback)                   callback(path, content) after
                                             a file finishes loading into
                                             a tab
    api.get_current_text()                  text of the active tab, or
                                             None if no tab is open
    api.get_current_path()                  path backing the active tab,
                                             or None
    api.insert_text(text)                   inserts at the cursor in the
                                             active tab
    api.show_message(text)                  flashes text in the status bar
    api.get_theme()                         the active theme's color dict

See hello_world.py in this same folder for a complete working example.
"""

_EXAMPLE_PLUGIN_TEXT = '''"""hello_world.py - a tiny example CodeForge plugin.

Demonstrates the basics of the plugin API: adding a command, reading the
current file, inserting text, and reacting to saves. Feel free to edit
or delete this file - it's just a starting point, not something
CodeForge depends on.
"""
import datetime


def setup(api):
    def say_hello():
        path = api.get_current_path()
        where = f" ({path})" if path else ""
        api.show_message(f"Hello from hello_world.py{where}!")

    def insert_timestamp():
        api.insert_text(datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"))

    def word_count():
        text = api.get_current_text()
        if text is None:
            api.show_message("No file open.")
            return
        api.show_message(f"{len(text.split())} words, {len(text)} characters")

    api.register_command("Hello World: Say Hello", say_hello)
    api.register_command("Hello World: Insert Timestamp", insert_timestamp)
    api.register_command("Hello World: Word Count", word_count)

    def on_save(path, content):
        print(f"[hello_world plugin] saved {path} ({len(content)} chars)")

    api.on_save(on_save)
'''


def ensure_plugin_dir():
    """Creates PLUGIN_DIR (plus a README and a working example plugin)
    the first time it's needed, so there's somewhere obvious for "Open
    Plugins Folder" to point at - and something to look at/copy - even
    before anyone's written a plugin of their own. Safe to call every
    startup: only ever writes the README/example if they aren't already
    there, so it never clobbers anything the user has since edited."""
    try:
        os.makedirs(PLUGIN_DIR, exist_ok=True)
    except OSError:
        return

    readme_path = os.path.join(PLUGIN_DIR, "README.txt")
    if not os.path.exists(readme_path):
        try:
            with open(readme_path, "w", encoding="utf-8") as f:
                f.write(_README_TEXT)
        except OSError:
            pass

    example_path = os.path.join(PLUGIN_DIR, "hello_world.py")
    if not os.path.exists(example_path):
        try:
            with open(example_path, "w", encoding="utf-8") as f:
                f.write(_EXAMPLE_PLUGIN_TEXT)
        except OSError:
            pass


class PluginAPI:
    """The only interface a plugin gets. Built once per app run (see
    app.py's run()) and handed to every plugin's setup() - the callables
    passed in below are supplied by app.py and do the actual work; this
    class is just a small, stable, documented wrapper in front of them
    so a plugin never has to reach into app.py's own closures/globals
    directly.
    """

    def __init__(self, *, register_command, add_on_save, add_on_open,
                 get_current_text, get_current_path, insert_text,
                 show_message, get_theme):
        self._register_command = register_command
        self._add_on_save = add_on_save
        self._add_on_open = add_on_open
        self._get_current_text = get_current_text
        self._get_current_path = get_current_path
        self._insert_text = insert_text
        self._show_message = show_message
        self._get_theme = get_theme

    def register_command(self, label, callback):
        """Adds `label` to the Plugins menu - and, automatically, to the
        Ctrl+Shift+P command palette, the same way every other menu item
        in CodeForge does - so selecting/clicking it calls callback().
        callback takes no arguments. A callback that raises is caught
        and reported in an error dialog rather than crashing CodeForge."""
        self._register_command(label, callback)

    def on_save(self, callback):
        """Registers callback(path, content) to fire after any file is
        saved to disk (Save or Save As), with the path it was saved to
        and the exact text that was written. A callback that raises is
        caught and ignored (degrade quietly, same as every other
        optional hook in this app) rather than blocking the save or
        crashing CodeForge."""
        self._add_on_save(callback)

    def on_open(self, callback):
        """Registers callback(path, content) to fire after a file
        finishes loading into a tab (File > Open, an Explorer double-
        click, drag-and-drop, or session restore all count). Same
        failure handling as on_save."""
        self._add_on_open(callback)

    def get_current_text(self):
        """The full text of whichever tab is currently active, or None
        if no tab is open."""
        return self._get_current_text()

    def get_current_path(self):
        """The file path backing the current tab, or None - either no
        tab is open, or the current tab has never been saved."""
        return self._get_current_path()

    def insert_text(self, text):
        """Inserts `text` into the current tab at the cursor position.
        No-op if there's no tab open."""
        self._insert_text(text)

    def show_message(self, text):
        """Briefly shows `text` in the status bar - the same mechanism
        CodeForge itself uses for things like save confirmations."""
        self._show_message(text)

    def get_theme(self):
        """A copy of the active theme's color dict (see themes.py) -
        it's a copy, so editing it doesn't affect CodeForge's own
        colors."""
        return self._get_theme()


def discover_plugin_files():
    """Every .py file directly inside PLUGIN_DIR, sorted for a
    deterministic load order. Doesn't recurse into subfolders, and skips
    names starting with "_" (room for a plugin to keep private helper
    modules alongside its real one without those being loaded as
    separate top-level plugins) - a plugin is meant to be a single file,
    keeping this whole system "basic" rather than growing into a
    package/dependency manager."""
    ensure_plugin_dir()
    try:
        names = sorted(os.listdir(PLUGIN_DIR))
    except OSError:
        return []
    return [
        os.path.join(PLUGIN_DIR, name) for name in names
        if name.endswith(".py") and not name.startswith("_")
    ]


def load_plugins(api):
    """Imports every plugin file found by discover_plugin_files() and
    calls its setup(api) if it defines one. Returns a list of
    {"name", "path", "error"} dicts, one per plugin file - "error" is
    None on success, or a formatted traceback string on failure - so the
    caller (the Plugins menu) can show what loaded and what didn't
    without needing to know anything about the import machinery itself.

    Every failure mode - a syntax error in the plugin file, an exception
    raised inside setup(), a plugin with no setup() at all (silently
    fine, just does nothing) - is caught right here and recorded rather
    than propagated: a broken plugin should never be able to stop
    CodeForge from starting, or stop any *other* plugin from loading."""
    results = []
    for path in discover_plugin_files():
        name = os.path.splitext(os.path.basename(path))[0]
        module_name = f"_codeforge_plugin_{name}"
        try:
            spec = importlib.util.spec_from_file_location(module_name, path)
            if spec is None or spec.loader is None:
                raise ImportError(f"couldn't load a module spec for {path}")
            module = importlib.util.module_from_spec(spec)
            # Registered in sys.modules *before* exec_module, same as a
            # normal import - lets a plugin that does e.g.
            # `import dataclasses; @dataclasses.dataclass` at its own
            # top level, or anything else that expects a real module
            # object to already be registered, behave normally instead
            # of tripping over a half-initialized module.
            sys.modules[module_name] = module
            spec.loader.exec_module(module)
            setup_fn = getattr(module, "setup", None)
            if setup_fn is not None:
                setup_fn(api)
            results.append({"name": name, "path": path, "error": None})
        except Exception:
            sys.modules.pop(module_name, None)
            results.append({"name": name, "path": path, "error": traceback.format_exc()})
    return results