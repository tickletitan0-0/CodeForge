import tkinter as tk
from tkinter import filedialog
from tkinter import ttk
from tkinter import messagebox
import tkinter.font as tkfont
import re
import keyword
import subprocess
import tempfile
import os
import threading
import uuid
import shlex

try:
    import winpty  # pip install pywinpty - provides a real Windows pseudo-console
except ImportError:
    winpty = None

try:
    import pty  # stdlib, POSIX only
except ImportError:
    pty = None


# ---------------- Theme ----------------
# A single, cohesive "professional light" palette. Every color used anywhere
# in the UI is defined here so the whole app reads as one consistent theme.
THEME = {
    # Chrome / structural
    "app_bg":           "#f3f3f3",  # root window + sash background
    "sidebar_bg":       "#f3f3f3",  # explorer panel background
    "panel_header_bg":  "#e8e8e8",  # EXPLORER / Output header strips
    "panel_header_fg":  "#3b3b3b",
    "border":           "#d4d4d4",

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


def run():
    root = tk.Tk()
    root.title("CodeForge")
    root.geometry("800x600")
    root.config(bg=THEME["app_bg"])

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
        borderwidth=0
    )
    style.map(
        "Treeview",
        background=[("selected", THEME["editor_select_bg"])],
        foreground=[("selected", THEME["editor_select_fg"])]
    )

    style.configure("TNotebook", background=THEME["app_bg"], borderwidth=0)
    style.configure(
        "TNotebook.Tab",
        background=THEME["panel_header_bg"],
        foreground=THEME["panel_header_fg"],
        padding=(10, 4),
        borderwidth=0
    )
    style.map(
        "TNotebook.Tab",
        background=[("selected", THEME["editor_bg"])],
        foreground=[("selected", THEME["editor_fg"])]
    )

    for orientation in ("Vertical", "Horizontal"):
        style.configure(
            f"{orientation}.TScrollbar",
            background=THEME["panel_header_bg"],
            troughcolor=THEME["app_bg"],
            bordercolor=THEME["border"],
            arrowcolor=THEME["panel_header_fg"]
        )

    # ---------------- Status bar ----------------
    # Packed (not just created) before the main paned window so it reserves
    # its strip at the bottom instead of being squeezed out by expand=True.
    status_bar = tk.Frame(root, bg=THEME["panel_header_bg"], height=24)
    status_bar.pack(side="bottom", fill="x")
    status_bar.pack_propagate(False)

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
        sashrelief="raised",
        sashwidth=6,
        bg=THEME["app_bg"]
    )
    main_frame.pack(fill="both", expand=True)

    explorer_frame = tk.Frame(main_frame, width=220, bg=THEME["sidebar_bg"])
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

    main_frame.add(explorer_frame, width=220, minsize=120, stretch="never")

    center_frame = tk.Frame(main_frame)
    main_frame.add(center_frame, minsize=300, stretch="always")

    tab_control = ttk.Notebook(center_frame)
    tab_control.pack(fill="both", expand=True)

    project_path = None
    tab_editors = {}       # tab widget name (str) -> editor dict
    untitled_count = [0]   # counter used to name new blank tabs

    # ---------------- Output / Terminal panel ----------------

    output_frame = tk.Frame(main_frame, width=300)
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

    output_scrollbar = tk.Scrollbar(
        output_tab,
        command=output_area.yview,
        bg=THEME["panel_header_bg"],
        troughcolor=THEME["app_bg"],
        activebackground=THEME["border"],
        highlightthickness=0,
        border=0
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

    terminal_scrollbar = tk.Scrollbar(
        terminal_tab,
        command=terminal_area.yview,
        bg=THEME["panel_header_bg"],
        troughcolor=THEME["app_bg"],
        activebackground=THEME["border"],
        highlightthickness=0,
        border=0
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

    def _term_feed_with_mirror(raw):
        """Wraps _term_feed: while a "Run" is in flight, watches the raw
        shell output for its start/end markers and buffers whatever runs
        between them (still feeding everything to the real terminal as
        normal) so it can also be shown, plain-text, in the Output panel."""
        if not (run_state["awaiting_start"] or run_state["active"]):
            _term_feed(raw)
            return

        raw = run_state["scan_pending"] + raw
        run_state["scan_pending"] = ""

        if run_state["awaiting_start"]:
            m = run_state["start_marker"].search(raw)
            if not m:
                # Hold back a small tail in case the marker is split across
                # two reads; feed the rest through immediately.
                keep = min(len(raw), 64)
                _term_feed(raw[:-keep] if keep else raw)
                run_state["scan_pending"] = raw[-keep:] if keep else ""
                return
            _term_feed(raw[:m.end()])
            run_state["awaiting_start"] = False
            run_state["active"] = True
            raw = raw[m.end():]
            if not raw:
                return

        m = run_state["end_marker"].search(raw)
        if not m:
            keep = min(len(raw), 64)
            chunk = raw[:-keep] if keep else raw
            run_state["buffer"] += chunk
            run_state["scan_pending"] = raw[-keep:] if keep else ""
            _term_feed(chunk)
            return

        run_state["buffer"] += raw[:m.start()]
        _term_feed(raw[:m.end()])
        run_state["active"] = False
        _finish_run_mirror()
        remainder = raw[m.end():]
        if remainder:
            _term_feed_with_mirror(remainder)

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

        line_numbers.config(state="normal")
        line_numbers.delete("1.0", tk.END)

        num_lines = int(text_area.index("end-1c").split(".")[0])
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
        for guide in editor["guide_canvases"]:
            guide.destroy()
        editor["guide_canvases"] = []

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
        # instead of a whole-character-cell background block.
        guide = tk.Canvas(
            editor["editor_frame"],
            width=1,
            height=y_bottom - y_top,
            bg=THEME["indent_guide"],
            highlightthickness=0,
            bd=0
        )
        guide.place(in_=text_area, x=x, y=y_top)
        editor["guide_canvases"].append(guide)

    def update_indent_guides(editor):
        text_area = editor["text"]
        if not text_area.winfo_exists():
            return

        _clear_indent_guides(editor)

        text_area.update_idletasks()

        total_lines = int(text_area.index("end-1c").split(".")[0])
        indent_width = 4

        indent_lens = []
        for line_no in range(1, total_lines + 1):
            line_text = text_area.get(f"{line_no}.0", f"{line_no}.end")
            stripped = line_text.lstrip(" ")
            indent_lens.append(len(line_text) - len(stripped))

        max_indent = max(indent_lens) if indent_lens else 0
        if max_indent < indent_width:
            return

        # Column 0's pixel x-position, so every guide column can be placed
        # with exact pixel math instead of relying on tag-cell widths.
        first_visible = int(text_area.index("@0,0").split(".")[0])
        anchor_bbox = text_area.bbox(f"{first_visible}.0")
        if not anchor_bbox:
            return

        guide_font = tkfont.Font(font=text_area.cget("font"))
        char_width = guide_font.measure("0")
        left_x = anchor_bbox[0]

        for col in range(0, max_indent, indent_width):
            x = left_x + col * char_width
            row = 1
            while row <= total_lines:
                if indent_lens[row - 1] > col:
                    run_start = row
                    while row <= total_lines and indent_lens[row - 1] > col:
                        row += 1
                    _draw_guide_run(editor, run_start, row - 1, x)
                else:
                    row += 1

    def highlight_syntax(text_area):
        for tag in ("keyword", "string", "comment", "number", "function"):
            text_area.tag_remove(tag, "1.0", tk.END)

        content = text_area.get("1.0", tk.END)

        # Keywords
        kw_pattern = r'\b(' + '|'.join(keyword.kwlist) + r')\b'
        for match in re.finditer(kw_pattern, content):
            start = f"1.0+{match.start()}c"
            end = f"1.0+{match.end()}c"
            text_area.tag_add("keyword", start, end)

        # Strings (single, double - simple version)
        string_pattern = r'(\".*?\"|\'.*?\')'
        for match in re.finditer(string_pattern, content):
            start = f"1.0+{match.start()}c"
            end = f"1.0+{match.end()}c"
            text_area.tag_add("string", start, end)

        # Comments
        comment_pattern = r'#.*'
        for match in re.finditer(comment_pattern, content):
            start = f"1.0+{match.start()}c"
            end = f"1.0+{match.end()}c"
            text_area.tag_add("comment", start, end)

        # Numbers
        number_pattern = r'\b\d+\b'
        for match in re.finditer(number_pattern, content):
            start = f"1.0+{match.start()}c"
            end = f"1.0+{match.end()}c"
            text_area.tag_add("number", start, end)

        # Function calls/defs (word followed by parenthesis)
        function_pattern = r'\b([a-zA-Z_]\w*)\s*(?=\()'
        for match in re.finditer(function_pattern, content):
            start = f"1.0+{match.start(1)}c"
            end = f"1.0+{match.end(1)}c"
            text_area.tag_add("function", start, end)

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
        ac = {"popup": None, "listbox": None, "start": None, "accept": None, "close": None}
        editor["autocomplete"] = ac

        def close_popup():
            popup = ac["popup"]
            if popup is not None and popup.winfo_exists():
                popup.destroy()
            ac["popup"] = None
            ac["listbox"] = None
            ac["start"] = None
            ac["accept"] = None

        def current_prefix():
            before_cursor = text_area.get("insert linestart", "insert")
            match = re.search(r"[A-Za-z_]\w*$", before_cursor)
            if not match:
                return None, None
            line = text_area.index("insert").split(".")[0]
            start_index = f"{line}.{match.start()}"
            return match.group(0), start_index

        def gather_candidates(prefix):
            text = text_area.get("1.0", "end")
            words = set(re.findall(r"[A-Za-z_]\w{1,}", text))
            pool = words | set(keyword.kwlist)
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

            prefix, start_index = current_prefix()
            if not prefix or len(prefix) < 2:
                close_popup()
                return

            candidates = gather_candidates(prefix)
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

    def create_tab(path=None, content=""):
        tab_frame = tk.Frame(tab_control)

        editor_frame = tk.Frame(tab_frame)
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
            font=("Consolas", 12)
        )
        line_numbers.pack(side="left", fill="y")

        text_area = tk.Text(
            editor_frame,
            wrap="none",
            undo=True,
            font=("Consolas", 12),
            background=THEME["editor_bg"],
            foreground=THEME["editor_fg"],
            insertbackground=THEME["editor_insert"],
            selectbackground=THEME["editor_select_bg"],
            selectforeground=THEME["editor_select_fg"],
            highlightthickness=0,
            border=0
        )
        text_area.pack(side="left", fill="both", expand=True)

        text_scrollbar = tk.Scrollbar(
            editor_frame,
            command=text_area.yview,
            bg=THEME["panel_header_bg"],
            troughcolor=THEME["app_bg"],
            activebackground=THEME["border"],
            highlightthickness=0,
            border=0
        )
        text_scrollbar.pack(side="left", fill="y")

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

        text_area.config(yscrollcommand=on_text_scroll)

        def on_linenum_scroll(event, ta=text_area):
            ta.yview_scroll(int(-event.delta / 120), "units")
            return "break"

        line_numbers.bind("<MouseWheel>", on_linenum_scroll)

        tab_id = str(tab_frame)
        title = make_tab_title(path)

        editor = {
            "frame": tab_frame,
            "editor_frame": editor_frame,
            "text": text_area,
            "line_numbers": line_numbers,
            "path": path,
            "title": title,
            "dirty": False,
            "guide_canvases": [],
            "resize_job": None
        }
        tab_editors[tab_id] = editor

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

            ed["resize_job"] = ed["text"].after(120, do_redraw)

        text_area.bind("<Configure>", on_text_resize)

        setup_highlight_tags(text_area)

        if content:
            text_area.insert("1.0", content)

        # Inserting initial content trips the <<Modified>> flag - clear it so
        # a freshly opened/created tab doesn't show as dirty.
        text_area.edit_modified(False)

        def on_key_release(event, ed=editor):
            update_line_numbers(ed)
            highlight_syntax(ed["text"])
            highlight_current_line(ed["text"])
            highlight_brackets(ed["text"])
            update_indent_guides(ed)
            update_status_bar(ed)

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

        bind_auto_indent(text_area, editor)
        bind_bracket_completion(text_area, editor)
        bind_autocomplete(text_area, editor)
        bind_multicursor(text_area, editor)

        tab_control.add(tab_frame, text=title)
        tab_control.select(tab_frame)

        update_line_numbers(editor)
        highlight_syntax(text_area)
        highlight_current_line(text_area)
        highlight_brackets(text_area)
        update_indent_guides(editor)

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
            return
        refresh_window_title(editor)
        update_line_numbers(editor)
        highlight_syntax(editor["text"])
        highlight_current_line(editor["text"])
        highlight_brackets(editor["text"])
        update_indent_guides(editor)
        update_status_bar(editor)
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

    tab_context_menu = tk.Menu(tab_control, tearoff=0)

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
            update_line_numbers(current)
            highlight_syntax(current["text"])
            highlight_current_line(current["text"])
            highlight_brackets(current["text"])
            update_indent_guides(current)
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
        try:
            items = sorted(os.listdir(path))
        except PermissionError:
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
                add_directory(node, full_path)

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
        run_state["buffer"] = ""
        run_state["scan_pending"] = ""
        run_state["active"] = False
        run_state["awaiting_start"] = True

        output_area.config(state="normal")
        output_area.delete("1.0", tk.END)
        output_area.insert("1.0", "Running...\n")
        output_area.config(state="disabled")

        focus_terminal()
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
        highlight_syntax(editor["text"])
        highlight_current_line(editor["text"])
        highlight_brackets(editor["text"])
        update_indent_guides(editor)
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
    menu_bar = tk.Menu(root)
    file_menu = tk.Menu(menu_bar, tearoff=0)
    file_menu.add_command(label="New Tab", command=new_file, accelerator="Ctrl+N")
    file_menu.add_command(label="Open File", command=open_file, accelerator="Ctrl+O")
    file_menu.add_command(label="Open Folder", command=open_folder)
    file_menu.add_command(label="Save", command=save_file, accelerator="Ctrl+S")
    file_menu.add_command(label="Save As", command=save_as_file)
    file_menu.add_separator()
    file_menu.add_command(label="Close Tab", command=lambda: close_tab(), accelerator="Ctrl+W")
    file_menu.add_separator()

    def on_exit():
        for tab_id in list(tab_editors.keys()):
            editor = tab_editors.get(tab_id)
            if editor is None:
                continue
            if not prompt_save_if_dirty(editor, tab_id):
                return
        stop_shell()
        root.destroy()

    file_menu.add_command(label="Exit", command=on_exit)
    menu_bar.add_cascade(label="File", menu=file_menu)

    root.protocol("WM_DELETE_WINDOW", on_exit)

    edit_menu = tk.Menu(menu_bar, tearoff=0)
    edit_menu.add_command(label="Find...", command=lambda: open_find_replace("find"), accelerator="Ctrl+F")
    edit_menu.add_command(label="Replace...", command=lambda: open_find_replace("replace"), accelerator="Ctrl+H")
    menu_bar.add_cascade(label="Edit", menu=edit_menu)

    run_menu = tk.Menu(menu_bar, tearoff=0)
    run_menu.add_command(label="Run", command=run_code, accelerator="F5")
    menu_bar.add_cascade(label="Run", menu=run_menu)

    view_menu = tk.Menu(menu_bar, tearoff=0)
    view_menu.add_command(label="Terminal", command=focus_terminal, accelerator="Ctrl+`")
    menu_bar.add_cascade(label="View", menu=view_menu)

    root.config(menu=menu_bar)

    root.bind("<Control-n>", lambda e: new_file())
    root.bind("<Control-o>", lambda e: open_file())
    root.bind("<Control-s>", lambda e: save_file())
    root.bind("<Control-w>", lambda e: close_tab())
    root.bind("<F5>", lambda e: run_code())
    root.bind("<Control-f>", lambda e: open_find_replace("find"))
    root.bind("<Control-h>", lambda e: open_find_replace("replace"))
    root.bind("<Control-grave>", lambda e: focus_terminal())

    # Start with a single blank tab
    create_tab()

    root.mainloop()