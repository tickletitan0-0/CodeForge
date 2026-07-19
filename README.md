# CodeForge

A lightweight, dependency-free-by-default code editor built entirely on
Python's standard library `tkinter`/`ttk` — with a handful of optional
extras (drag-and-drop, background music, Git integration) layered on top
that gracefully disable themselves if their (few) third-party pieces
aren't installed.

## Features

- **Syntax-aware editing** for Python, JavaScript, HTML, CSS, and Java
- **Inline diagnostics** ("squiggly lines") — exact for Python via the
  stdlib `ast` module, `node --check` for JavaScript when Node is on
  PATH, and a generic bracket/quote-balance scanner as a fallback for
  everything else
- **Indentation-based code folding**, working identically across
  languages CodeForge doesn't otherwise have a dedicated grammar for
- **Go to Line / Symbol** popup (`Ctrl+P`) — exact function/class listing
  for Python via `ast`, best-effort regex extraction for JS/Java/CSS/HTML
- **Source Control tab** — staged/unstaged/untracked file list, diff
  preview, commit/push/pull, and branch switching, talking to a real
  `git` executable on PATH
- **Plugin system** — drop a `.py` file with a `setup(api)` function into
  your plugins folder and it shows up in the Plugins menu and the
  command palette; one broken plugin never takes down the others or the
  app itself
- **Background Music tab** — stream and play audio from a YouTube URL
  while you code
- **Cosmetic extras** — error flash / success glow on Run, a typing
  streak indicator, an idle mascot, and a Konami-code easter egg
- **Themeable** UI, drag-and-drop file opening, split editing, and more

Everything above that isn't pure stdlib fails soft: missing an optional
dependency just means that one feature shows an install hint instead of
its controls — the rest of the editor is unaffected.

## Requirements

- Python 3.9+
- Optional extras — see [`requirements.txt`](requirements.txt) for
  details and exact packages (`tkinterdnd2`, `yt-dlp`, `python-vlc`)
- Optional system tools: a `git` executable on PATH for the Source
  Control tab, and `node` on PATH for real JavaScript syntax checking

## Getting started

```bash
git clone <this repo>
cd CodeForge

# optional: only needed for drag-and-drop, the Music tab, etc.
pip install -r requirements.txt

python main.py
```

## Project layout

```
CodeForge/
├── main.py                 # entry point: from editor import app; app.run()
├── requirements.txt
├── editor/                 # the actual "editor" package
│   ├── app.py               # main window, menus, tabs, editing logic
│   ├── themes.py             # theme definitions + persisted settings
│   ├── linters.py            # background diagnostics ("squiggly lines")
│   ├── code_folding.py        # indentation-based fold engine
│   ├── goto.py                # Go to Line/Symbol popup's symbol extraction
│   ├── git_panel.py           # Source Control tab
│   ├── music_player.py        # background Music tab
│   ├── plugins.py             # plugin discovery/loading + PluginAPI
│   ├── fun_effects.py         # cosmetic flourishes (glow, mascot, ...)
│   ├── hover_defs.py           # hover-to-see-definition support
│   ├── terminal.py             # Terminal tab
│   ├── test.py                  # test suite
│   ├── icon.png, icon.ico        # app icon (window + exe/taskbar)
│   └── codeforge.spec             # PyInstaller build spec (lives here,
│                                    next to app.py — see the spec's own
│                                    header comment for build instructions)
└── ...
```

## Building a standalone executable

CodeForge can be packaged into a standalone Windows executable with
[PyInstaller](https://pyinstaller.org/). The spec file lives inside
`editor/`, alongside `app.py`:

```bash
pip install pyinstaller
cd editor
pyinstaller codeforge.spec
```

The built app lands in `editor/dist/CodeForge/`. See the comments at the
top of `editor/codeforge.spec` for why this is a onedir build rather than
onefile, and how to optionally bundle a standalone VLC runtime for the
Music tab.

## Plugins

Drop a `.py` file into your CodeForge plugins folder (`Plugins > Open
Plugins Folder`, or `~/.codeforge/plugins`) with a top-level `setup(api)`
function:

```python
def setup(api):
    api.register_command("Say Hello", lambda: api.show_message("Hello!"))
```

Then `Plugins > Reload Plugins` (or just restart CodeForge). See
`editor/plugins.py`'s module docstring, and the auto-generated
`hello_world.py` example it drops into that folder on first run, for the
full API surface.

## License

See [`LICENSE`](LICENSE) for details.