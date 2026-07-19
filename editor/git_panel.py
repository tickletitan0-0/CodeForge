"""
Git source-control panel for CodeForge.

Adds a "Source Control" tab next to Output/Terminal/Music with a
staged/unstaged/untracked file list, a diff preview, commit/push/pull, and
a branch switcher. Talks to git entirely by shelling out to the system
`git` executable (subprocess) - the same pattern app.py already uses for
the Terminal tab's shell process and the "Reveal in file explorer"
commands - so no extra pip package is required. The only external
dependency is a `git` executable somewhere on PATH.

If `git` isn't found, build_git_panel() shows an install hint instead of
the panel controls - the same graceful-fallback pattern music_player.py
uses for yt-dlp/python-vlc.
"""

import os
import re
import shutil
import subprocess
import sys
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog

GIT_EXE = shutil.which("git")


# ---------------- Low-level git plumbing ----------------

def _startupinfo():
    """Suppresses the console window git.exe would otherwise flash open
    on Windows for every single subprocess call."""
    if sys.platform != "win32":
        return None, 0
    si = subprocess.STARTUPINFO()
    si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    return si, subprocess.CREATE_NO_WINDOW


def _run(args, cwd, timeout=15):
    """Runs a git subcommand and returns (returncode, stdout, stderr).
    Never raises - callers get a nonzero code + stderr text back instead,
    so UI code can just check `code == 0` without wrapping every call
    site in its own try/except."""
    si, flags = _startupinfo()
    try:
        proc = subprocess.run(
            [GIT_EXE] + args,
            cwd=cwd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            startupinfo=si,
            creationflags=flags,
        )
        return proc.returncode, proc.stdout, proc.stderr
    except subprocess.TimeoutExpired:
        return 1, "", "git command timed out"
    except OSError as e:
        return 1, "", str(e)


def find_repo_root(path):
    """Walks up from `path` looking for a repo (handles worktrees, where
    .git is a file rather than a directory, since this just asks git
    itself rather than checking for .git by hand). Returns None if `path`
    isn't inside a git repo, or isn't a real directory at all."""
    if not path or not os.path.isdir(path):
        return None
    code, out, _ = _run(["rev-parse", "--show-toplevel"], cwd=path)
    if code != 0:
        return None
    return os.path.normpath(out.strip())


def get_branch_info(repo_root):
    """Returns (branch_name, ahead, behind). branch_name is "HEAD" for a
    detached HEAD. ahead/behind are 0 if there's no upstream configured
    (rev-list against @{upstream} just fails in that case, which we treat
    the same as "nothing to report" rather than an error)."""
    code, out, _ = _run(["rev-parse", "--abbrev-ref", "HEAD"], cwd=repo_root)
    branch = out.strip() if code == 0 else "?"
    ahead = behind = 0
    code2, out2, _ = _run(
        ["rev-list", "--left-right", "--count", "HEAD...@{upstream}"], cwd=repo_root
    )
    if code2 == 0:
        parts = out2.split()
        if len(parts) == 2:
            try:
                ahead, behind = int(parts[0]), int(parts[1])
            except ValueError:
                pass
    return branch, ahead, behind


def get_status(repo_root):
    """Returns {"staged": [...], "unstaged": [...], "untracked": [...],
    "error": str_or_None} - each list holding (status_char, relative_path)
    tuples - parsed from `git status --porcelain=v1`. Index (staged)
    status is the first column, worktree (unstaged) status is the second;
    a file with both an index and worktree change (e.g. staged, then
    edited again) correctly ends up in both lists."""
    code, out, err = _run(["status", "--porcelain=v1", "-uall"], cwd=repo_root)
    staged, unstaged, untracked = [], [], []
    if code != 0:
        return {"staged": staged, "unstaged": unstaged, "untracked": untracked, "error": err}
    for line in out.splitlines():
        if not line:
            continue
        x, y, rest = line[0], line[1], line[3:]
        if " -> " in rest:
            rest = rest.split(" -> ", 1)[1]
        if x == "?" and y == "?":
            untracked.append(("?", rest))
            continue
        if x not in (" ", "?"):
            staged.append((x, rest))
        if y not in (" ", "?"):
            unstaged.append((y, rest))
    return {"staged": staged, "unstaged": unstaged, "untracked": untracked, "error": None}


def list_branches(repo_root):
    code, out, _ = _run(["branch", "--list"], cwd=repo_root)
    if code != 0:
        return []
    branches = []
    for line in out.splitlines():
        name = line[2:].strip() if line.startswith("* ") else line.strip()
        if name and "->" not in name:
            branches.append(name)
    return branches


def stage(repo_root, paths):
    return _run(["add", "--"] + list(paths), cwd=repo_root)


def unstage(repo_root, paths):
    return _run(["restore", "--staged", "--"] + list(paths), cwd=repo_root)


def discard(repo_root, paths):
    """Discards unstaged edits to tracked files. Not meant for untracked
    files (there's nothing to "restore" them to) - callers should delete
    those from disk instead, if that's ever wired up."""
    return _run(["checkout", "--"] + list(paths), cwd=repo_root)


def commit(repo_root, message):
    return _run(["commit", "-m", message], cwd=repo_root)


def push(repo_root):
    return _run(["push"], cwd=repo_root, timeout=60)


def pull(repo_root):
    return _run(["pull"], cwd=repo_root, timeout=60)


def checkout_branch(repo_root, name):
    return _run(["checkout", name], cwd=repo_root)


def create_branch(repo_root, name):
    return _run(["checkout", "-b", name], cwd=repo_root)


def init_repo(path):
    return _run(["init"], cwd=path)


def clone_repo(url, dest_path):
    """Clones `url` into `dest_path` (which must not already exist - git
    clone refuses a non-empty target). Longer timeout than other commands
    since a clone's duration depends on repo size/network, not just local
    disk work."""
    parent = os.path.dirname(dest_path) or "."
    return _run(["clone", url, dest_path], cwd=parent, timeout=180)


def repo_name_from_url(url):
    """Best-effort guess at the folder name `git clone` would pick on its
    own, so the destination folder can be shown/created before the clone
    actually runs. Handles both https://.../name.git and the scp-like
    git@host:user/name.git form."""
    name = url.strip().rstrip("/")
    if name.endswith(".git"):
        name = name[:-4]
    name = re.split(r"[/:]", name)[-1]
    return name or "repository"


def diff_file(repo_root, relative_path, staged=False):
    args = ["diff", "--no-color"]
    if staged:
        args.append("--cached")
    args += ["--", relative_path]
    code, out, err = _run(args, cwd=repo_root)
    if code != 0:
        return f"(couldn't diff: {err.strip() or out.strip()})"
    return out or "(no differences - the file may have just been staged/unstaged)"


_HUNK_RE = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")


def diff_line_status(repo_root, relative_path):
    """Returns {"added": set(line_no), "modified": set(line_no), "untracked": bool}
    - the 1-based line numbers in the *current working copy* that differ
    from HEAD, used to paint the editor minimap's git-heatmap strip.

    Parses `git diff -U0` hunk headers the same way gutter-diff plugins do:
    a hunk with an old line count of 0 is a pure insertion (those new
    lines are "added"); anything else that touches both old and new
    content marks the corresponding new lines "modified". Pure deletions
    (new count 0) have nothing left in the current file to mark, so
    they're skipped - there's no line left to color.

    Untracked files aren't part of `git diff`'s output at all, so they're
    detected separately and reported via "untracked": True instead, with
    both sets left empty - callers should treat that as "the whole file is
    new" the same way the explorer's git_untracked tag does.

    Returns all-empty/False on any failure (git missing, not a repo, file
    not found, etc.) rather than raising - callers should treat that as
    "nothing to show".
    """
    empty = {"added": set(), "modified": set(), "untracked": False}
    if not GIT_EXE or not repo_root:
        return empty

    rel = relative_path.replace("\\", "/")

    code, _, _ = _run(["ls-files", "--error-unmatch", "--", rel], cwd=repo_root)
    if code != 0:
        # Not tracked (or outside the repo) - nothing to diff against.
        return {"added": set(), "modified": set(), "untracked": True}

    code, out, _ = _run(["diff", "--no-color", "-U0", "--", rel], cwd=repo_root)
    if code != 0 or not out:
        return empty

    added, modified = set(), set()
    for line in out.splitlines():
        m = _HUNK_RE.match(line)
        if not m:
            continue
        old_count = int(m.group(2) or "1")
        new_start = int(m.group(3))
        new_count = int(m.group(4) or "1")
        if new_count == 0:
            continue
        target = added if old_count == 0 else modified
        target.update(range(new_start, new_start + new_count))

    return {"added": added, "modified": modified, "untracked": False}


# ---------------- UI ----------------

def build_git_panel(parent, theme, get_project_path, on_status_change=None, on_open_file=None, on_repo_cloned=None, on_commit=None):
    """Builds the Source Control panel UI inside `parent`.

    get_project_path is a zero-arg callable returning the folder currently
    open in the explorer (app.py's `project_path`, which can change via
    Open Folder / drag-drop / session restore) - called fresh every
    refresh() rather than captured once, so the panel always reflects
    whatever's open right now.

    on_status_change(branch_or_None, ahead, behind), if given, fires
    whenever refresh() completes - lets a caller (e.g. the main status
    bar) mirror the current branch without polling.

    on_open_file(absolute_path), if given, fires on double-click of a
    file row - lets a caller open that file in an editor tab.

    on_repo_cloned(absolute_path), if given, fires after "Clone
    Repository..." finishes successfully - lets a caller open the newly
    cloned folder as the project (populate the explorer tree, etc.),
    the same way it would after File > Open Folder.

    on_commit(), if given, fires after a commit actually succeeds - lets
    a caller track a commit counter/stat without polling git log.

    Returns a dict of control functions (refresh/stage_all/etc.) - used
    by app.py to refresh the panel after saves/tree changes, the same
    pattern music_player.py uses for its returned control dict.
    """

    panel = tk.Frame(parent, bg=theme["output_bg"])
    panel.pack(fill="both", expand=True)

    if GIT_EXE is None:
        tk.Label(
            panel,
            text=(
                "\u2325  Source control needs Git installed and on your PATH.\n\n"
                "    https://git-scm.com/downloads\n\n"
                "Then restart CodeForge and this tab will turn into a Git panel."
            ),
            bg=theme["output_bg"], fg=theme["muted_fg"], justify="left",
            padx=16, pady=16, anchor="w",
        ).pack(anchor="w", fill="x")
        return {"refresh": lambda: None}

    # Flipped off the moment `panel` is destroyed - same reasoning as the
    # `alive` flag in music_player.py: background threads hand results
    # back to the UI thread via panel.after(0, ...), and a theme switch
    # (root.destroy() + os.execv) can leave those callbacks sitting in
    # Tk's event queue after the widgets are already gone.
    alive = {"value": True}
    state = {"repo_root": None, "branch": None, "ahead": 0, "behind": 0, "status": None}

    btn_opts = dict(
        bg=theme["panel_header_bg"], fg=theme["panel_header_fg"],
        activebackground=theme["editor_select_bg"], activeforeground=theme["editor_select_fg"],
        relief="flat", bd=0, highlightthickness=0, padx=8, pady=3, cursor="hand2",
    )

    # ---- Message view (shown when there's no folder open, or the folder
    # isn't a git repo yet) vs. the main panel - only one packed at a time,
    # both built once so refresh() never has to reconstruct widgets. ----
    msg_frame = tk.Frame(panel, bg=theme["output_bg"])
    msg_label = tk.Label(
        msg_frame, text="", bg=theme["output_bg"], fg=theme["muted_fg"],
        justify="left", padx=16, pady=16, anchor="w", wraplength=420,
    )
    msg_label.pack(anchor="w", fill="x")
    init_btn = tk.Button(msg_frame, text="Initialize Repository (git init)", **btn_opts)
    init_btn.pack(anchor="w", padx=16, pady=(0, 16))

    clone_row = tk.Frame(msg_frame, bg=theme["output_bg"])
    clone_row.pack(anchor="w", padx=16, pady=(0, 16))
    clone_btn = tk.Button(clone_row, text="Clone Repository...", **btn_opts)
    clone_btn.pack(side="left")
    clone_status_label = tk.Label(
        clone_row, text="", bg=theme["output_bg"], fg=theme["muted_fg"], padx=8,
    )
    clone_status_label.pack(side="left")

    main_frame = tk.Frame(panel, bg=theme["output_bg"])

    def _show_msg(text, show_init_btn):
        main_frame.pack_forget()
        msg_label.config(text=text)
        if show_init_btn:
            init_btn.pack(anchor="w", padx=16, pady=(0, 16))
        else:
            init_btn.pack_forget()
        msg_frame.pack(fill="both", expand=True)

    def _show_main():
        msg_frame.pack_forget()
        main_frame.pack(fill="both", expand=True)

    # ---- Header row: branch + ahead/behind, refresh, pull, push ----
    header_row = tk.Frame(main_frame, bg=theme["output_bg"])
    header_row.pack(fill="x", padx=10, pady=(10, 4))

    branch_label = tk.Label(
        header_row, text="\u2325 -", bg=theme["output_bg"], fg=theme["accent"],
        cursor="hand2",
    )
    branch_label.pack(side="left")

    refresh_btn = tk.Button(header_row, text="\u27F3", **btn_opts)
    refresh_btn.pack(side="left", padx=(10, 0))

    pull_btn = tk.Button(header_row, text="\u2B07 Pull", **btn_opts)
    pull_btn.pack(side="left", padx=(6, 0))

    push_btn = tk.Button(header_row, text="\u2B06 Push", **btn_opts)
    push_btn.pack(side="left", padx=(6, 0))

    status_label = tk.Label(
        main_frame, text="", bg=theme["output_bg"], fg=theme["muted_fg"], anchor="w", padx=10
    )
    status_label.pack(fill="x")

    def set_status_msg(text):
        status_label.config(text=text)

    def _branch_text():
        text = f"\u2325 {state['branch'] or '?'}"
        if state["ahead"]:
            text += f"  \u2191{state['ahead']}"
        if state["behind"]:
            text += f"  \u2193{state['behind']}"
        return text

    # ---- Staged / Changes / Untracked lists ----
    lists_frame = tk.Frame(main_frame, bg=theme["output_bg"])
    lists_frame.pack(fill="both", expand=True, padx=10)

    def _make_section(title_text, action_text):
        section = tk.Frame(lists_frame, bg=theme["output_bg"])
        section.pack(fill="x", pady=(6, 0))
        head = tk.Frame(section, bg=theme["output_bg"])
        head.pack(fill="x")
        title_label = tk.Label(
            head, text=title_text, bg=theme["output_bg"], fg=theme["output_fg"], anchor="w"
        )
        title_label.pack(side="left")
        action_btn = tk.Button(head, text=action_text, **btn_opts)
        action_btn.pack(side="right")
        listbox = tk.Listbox(
            section, bg=theme["popup_bg"], fg=theme["popup_fg"],
            selectbackground=theme["popup_select_bg"], selectforeground=theme["popup_select_fg"],
            relief="flat", highlightthickness=0, activestyle="none", height=4, exportselection=False,
        )
        listbox.pack(fill="x", pady=(2, 0))
        return title_label, action_btn, listbox

    staged_title, unstage_all_btn, staged_list = _make_section("STAGED CHANGES (0)", "Unstage All")
    unstaged_title, stage_all_btn, unstaged_list = _make_section("CHANGES (0)", "Stage All")
    untracked_title, stage_untracked_btn, untracked_list = _make_section("UNTRACKED (0)", "Stage All")

    # ---- Diff preview ----
    tk.Label(
        main_frame, text="DIFF", bg=theme["output_bg"], fg=theme["muted_fg"], anchor="w", padx=10
    ).pack(fill="x", pady=(8, 0))

    diff_text = tk.Text(
        main_frame, font=("Consolas", 9), bg=theme["popup_bg"], fg=theme["popup_fg"],
        relief="flat", highlightthickness=0, height=8, wrap="none", state="disabled",
    )
    diff_text.pack(fill="both", expand=True, padx=10, pady=(2, 6))
    diff_text.tag_configure("diff_add", foreground=theme["syntax_comment"])
    diff_text.tag_configure("diff_del", foreground=theme["syntax_string"])
    diff_text.tag_configure("diff_hunk", foreground=theme["accent"])

    # ---- Commit box ----
    commit_row = tk.Frame(main_frame, bg=theme["output_bg"])
    commit_row.pack(fill="x", padx=10, pady=(0, 10))

    commit_text = tk.Text(
        commit_row, font=("Consolas", 10), bg=theme["popup_bg"], fg=theme["popup_fg"],
        insertbackground=theme["output_fg"], relief="flat", highlightthickness=1,
        highlightbackground=theme["border"], highlightcolor=theme["accent"],
        height=2, width=1, wrap="word",
    )
    commit_text.pack(side="left", fill="x", expand=True)

    commit_btn = tk.Button(commit_row, text="\u2713 Commit", **btn_opts)
    commit_btn.pack(side="left", padx=(6, 0), anchor="n")

    # ---------------- Helpers ----------------
    def _clear_diff():
        diff_text.config(state="normal")
        diff_text.delete("1.0", "end")
        diff_text.config(state="disabled")

    def _show_diff(text):
        diff_text.config(state="normal")
        diff_text.delete("1.0", "end")
        diff_text.insert("1.0", text)
        for i, line in enumerate(text.splitlines(), start=1):
            if line.startswith("+++") or line.startswith("---"):
                continue
            if line.startswith("+"):
                diff_text.tag_add("diff_add", f"{i}.0", f"{i}.end")
            elif line.startswith("-"):
                diff_text.tag_add("diff_del", f"{i}.0", f"{i}.end")
            elif line.startswith("@@"):
                diff_text.tag_add("diff_hunk", f"{i}.0", f"{i}.end")
        diff_text.config(state="disabled")

    def _entries_for(kind):
        s = state["status"] or {"staged": [], "unstaged": [], "untracked": []}
        return s.get(kind, [])

    def _selected_paths(listbox, kind):
        entries = _entries_for(kind)
        return [entries[i][1] for i in listbox.curselection() if i < len(entries)]

    def _preview_diff(listbox, kind):
        sel = listbox.curselection()
        if not sel:
            return
        entries = _entries_for(kind)
        if sel[0] >= len(entries):
            return
        _, relpath = entries[sel[0]]
        repo_root = state["repo_root"]
        if kind == "untracked":
            _show_diff(
                "New file - not yet tracked by Git.\n"
                "Stage it to include its contents in the next commit."
            )
            return

        def worker():
            text = diff_file(repo_root, relpath, staged=(kind == "staged"))

            def apply():
                if alive["value"]:
                    _show_diff(text)

            panel.after(0, apply)

        threading.Thread(target=worker, daemon=True).start()

    def _open_selected(listbox, kind, event=None):
        if on_open_file is None:
            return
        sel = listbox.curselection()
        entries = _entries_for(kind)
        if not sel or sel[0] >= len(entries):
            return
        _, relpath = entries[sel[0]]
        on_open_file(os.path.join(state["repo_root"], relpath))

    def _run_and_refresh(action, *args, busy_msg="Working...", done_msg=None):
        repo_root = state["repo_root"]
        if not repo_root:
            return
        set_status_msg(busy_msg)

        def worker():
            code, out, err = action(repo_root, *args)

            def apply():
                if not alive["value"]:
                    return
                if code == 0:
                    set_status_msg(done_msg or "Done.")
                else:
                    set_status_msg((err or out).strip() or "Command failed.")
                refresh()

            panel.after(0, apply)

        threading.Thread(target=worker, daemon=True).start()

    # ---------------- Actions ----------------
    def stage_selected():
        paths = _selected_paths(unstaged_list, "unstaged") or _selected_paths(untracked_list, "untracked")
        if paths:
            _run_and_refresh(stage, paths, busy_msg="Staging...", done_msg="Staged.")

    def stage_all_unstaged():
        paths = [p for _, p in _entries_for("unstaged")]
        if paths:
            _run_and_refresh(stage, paths, busy_msg="Staging...", done_msg="Staged all changes.")

    def stage_all_untracked():
        paths = [p for _, p in _entries_for("untracked")]
        if paths:
            _run_and_refresh(stage, paths, busy_msg="Staging...", done_msg="Staged all untracked files.")

    def unstage_selected():
        paths = _selected_paths(staged_list, "staged")
        if paths:
            _run_and_refresh(unstage, paths, busy_msg="Unstaging...", done_msg="Unstaged.")

    def unstage_all():
        paths = [p for _, p in _entries_for("staged")]
        if paths:
            _run_and_refresh(unstage, paths, busy_msg="Unstaging...", done_msg="Unstaged all.")

    def discard_selected():
        paths = _selected_paths(unstaged_list, "unstaged")
        if not paths:
            return
        if not messagebox.askyesno(
            "Discard Changes",
            f"Discard unsaved changes to {len(paths)} file(s)? This can't be undone.",
        ):
            return
        _run_and_refresh(discard, paths, busy_msg="Discarding...", done_msg="Discarded changes.")

    def do_commit():
        if not state["repo_root"]:
            return
        if not _entries_for("staged"):
            set_status_msg("Nothing staged - stage some changes first.")
            return
        message = commit_text.get("1.0", "end-1c").strip()
        if not message:
            set_status_msg("Enter a commit message first.")
            return
        repo_root = state["repo_root"]
        commit_btn.config(state="disabled")
        set_status_msg("Committing...")

        def worker():
            code, out, err = commit(repo_root, message)

            def apply():
                commit_btn.config(state="normal")
                if not alive["value"]:
                    return
                if code == 0:
                    commit_text.delete("1.0", "end")
                    set_status_msg("Committed.")
                    if on_commit:
                        on_commit()
                else:
                    set_status_msg((err or out).strip() or "Commit failed.")
                refresh()

            panel.after(0, apply)

        threading.Thread(target=worker, daemon=True).start()

    def do_push():
        push_btn.config(state="disabled")

        def worker():
            code, out, err = push(state["repo_root"])

            def apply():
                push_btn.config(state="normal")
                if not alive["value"]:
                    return
                set_status_msg((err or out).strip() or ("Pushed." if code == 0 else "Push failed."))
                refresh()

            panel.after(0, apply)

        if state["repo_root"]:
            set_status_msg("Pushing...")
            threading.Thread(target=worker, daemon=True).start()
        else:
            push_btn.config(state="normal")

    def do_pull():
        pull_btn.config(state="disabled")

        def worker():
            code, out, err = pull(state["repo_root"])

            def apply():
                pull_btn.config(state="normal")
                if not alive["value"]:
                    return
                set_status_msg((err or out).strip() or ("Pulled." if code == 0 else "Pull failed."))
                refresh()

            panel.after(0, apply)

        if state["repo_root"]:
            set_status_msg("Pulling...")
            threading.Thread(target=worker, daemon=True).start()
        else:
            pull_btn.config(state="normal")

    def do_init():
        path = get_project_path()
        if not path:
            return
        init_btn.config(state="disabled")

        def worker():
            code, out, err = init_repo(path)

            def apply():
                init_btn.config(state="normal")
                if not alive["value"]:
                    return
                if code != 0:
                    messagebox.showerror("git init", (err or out).strip() or "Failed to initialize repository.")
                refresh()

            panel.after(0, apply)

        threading.Thread(target=worker, daemon=True).start()

    def do_clone():
        url = simpledialog.askstring("Clone Repository", "Repository URL:", parent=panel)
        if not url:
            return
        url = url.strip()
        if not url:
            return

        parent_dir = filedialog.askdirectory(title="Choose a folder to clone into")
        if not parent_dir:
            return

        name = repo_name_from_url(url)
        dest = os.path.join(parent_dir, name)
        if os.path.exists(dest):
            messagebox.showerror(
                "Clone Repository",
                f"'{name}' already exists in that folder - choose a different location "
                "or remove/rename the existing folder first.",
            )
            return

        clone_btn.config(state="disabled")
        init_btn.config(state="disabled")
        clone_status_label.config(text=f"Cloning {name}...")

        def worker():
            code, out, err = clone_repo(url, dest)

            def apply():
                clone_btn.config(state="normal")
                init_btn.config(state="normal")
                if not alive["value"]:
                    return
                if code != 0:
                    clone_status_label.config(text="")
                    messagebox.showerror("Clone Repository", (err or out).strip() or "Clone failed.")
                    return
                clone_status_label.config(text="Cloned.")
                if on_repo_cloned:
                    on_repo_cloned(dest)
                refresh()

            panel.after(0, apply)

        threading.Thread(target=worker, daemon=True).start()

    def _do_checkout(name):
        _run_and_refresh(lambda root, n=name: checkout_branch(root, n), busy_msg=f"Switching to {name}...", done_msg=f"Switched to {name}.")

    def _do_new_branch():
        repo_root = state["repo_root"]
        if not repo_root:
            return
        name = simpledialog.askstring("New Branch", "Branch name:", parent=panel)
        if not name:
            return
        _run_and_refresh(lambda root, n=name: create_branch(root, n), busy_msg=f"Creating {name}...", done_msg=f"Created and switched to {name}.")

    def show_branch_menu(event=None):
        repo_root = state["repo_root"]
        if not repo_root:
            return
        menu = tk.Menu(panel, tearoff=0)
        for name in list_branches(repo_root):
            prefix = "\u2713 " if name == state["branch"] else "    "
            menu.add_command(label=prefix + name, command=lambda n=name: _do_checkout(n))
        menu.add_separator()
        menu.add_command(label="+ New Branch...", command=_do_new_branch)
        x = branch_label.winfo_rootx()
        y = branch_label.winfo_rooty() + branch_label.winfo_height()
        menu.tk_popup(x, y)

    # ---------------- Populate ----------------
    def _fill_list(listbox, entries):
        listbox.delete(0, tk.END)
        for code, relpath in entries:
            listbox.insert(tk.END, f"{code}  {relpath}" if code != "?" else relpath)

    def _populate(status):
        state["status"] = status
        staged_title.config(text=f"STAGED CHANGES ({len(status['staged'])})")
        unstaged_title.config(text=f"CHANGES ({len(status['unstaged'])})")
        untracked_title.config(text=f"UNTRACKED ({len(status['untracked'])})")
        _fill_list(staged_list, status["staged"])
        _fill_list(unstaged_list, status["unstaged"])
        _fill_list(untracked_list, status["untracked"])
        _clear_diff()
        if status.get("error"):
            set_status_msg(status["error"].strip())
        elif not any((status["staged"], status["unstaged"], status["untracked"])):
            set_status_msg("Nothing to commit, working tree clean.")
        else:
            set_status_msg("")

    # ---------------- Refresh ----------------
    def refresh():
        if not alive["value"]:
            return
        path = get_project_path()
        if not path:
            state["repo_root"] = None
            _show_msg("Open a folder (File \u2192 Open Folder) to use source control.", show_init_btn=False)
            if on_status_change:
                on_status_change(None, 0, 0)
            return

        def worker():
            repo_root = find_repo_root(path)
            if repo_root is None:
                def apply_none():
                    if not alive["value"]:
                        return
                    state["repo_root"] = None
                    _show_msg(f"'{os.path.basename(path)}' isn't a Git repository yet.", show_init_btn=True)
                    if on_status_change:
                        on_status_change(None, 0, 0)

                panel.after(0, apply_none)
                return

            branch, ahead, behind = get_branch_info(repo_root)
            status = get_status(repo_root)

            def apply():
                if not alive["value"]:
                    return
                state["repo_root"] = repo_root
                state["branch"], state["ahead"], state["behind"] = branch, ahead, behind
                _show_main()
                branch_label.config(text=_branch_text())
                _populate(status)
                if on_status_change:
                    on_status_change(branch, ahead, behind)

            panel.after(0, apply)

        threading.Thread(target=worker, daemon=True).start()

    # ---------------- Wiring ----------------
    init_btn.config(command=do_init)
    clone_btn.config(command=do_clone)
    refresh_btn.config(command=refresh)
    pull_btn.config(command=do_pull)
    push_btn.config(command=do_push)
    branch_label.bind("<Button-1>", show_branch_menu)
    commit_btn.config(command=do_commit)

    unstage_all_btn.config(command=unstage_all)
    stage_all_btn.config(command=stage_all_unstaged)
    stage_untracked_btn.config(command=stage_all_untracked)

    staged_list.bind("<<ListboxSelect>>", lambda e: _preview_diff(staged_list, "staged"))
    unstaged_list.bind("<<ListboxSelect>>", lambda e: _preview_diff(unstaged_list, "unstaged"))
    untracked_list.bind("<<ListboxSelect>>", lambda e: _preview_diff(untracked_list, "untracked"))
    staged_list.bind("<Double-Button-1>", lambda e: _open_selected(staged_list, "staged"))
    unstaged_list.bind("<Double-Button-1>", lambda e: _open_selected(unstaged_list, "unstaged"))
    untracked_list.bind("<Double-Button-1>", lambda e: _open_selected(untracked_list, "untracked"))

    # Right-click context menus - one per list, since the available
    # actions differ (you can't "unstage" an untracked file, etc).
    def _bind_context_menu(listbox, items):
        menu = tk.Menu(panel, tearoff=0)
        for label, command in items:
            menu.add_command(label=label, command=command)

        def show(event):
            index = listbox.nearest(event.y)
            if index >= 0:
                listbox.selection_clear(0, tk.END)
                listbox.selection_set(index)
                listbox.event_generate("<<ListboxSelect>>")
            menu.tk_popup(event.x_root, event.y_root)

        listbox.bind("<Button-3>", show)

    _bind_context_menu(staged_list, [("Unstage", unstage_selected), ("Unstage All", unstage_all)])
    _bind_context_menu(
        unstaged_list,
        [("Stage", stage_selected), ("Stage All", stage_all_unstaged), ("Discard Changes", discard_selected)],
    )
    _bind_context_menu(untracked_list, [("Stage", stage_selected), ("Stage All", stage_all_untracked)])

    def _on_panel_destroy(event):
        if event.widget is panel:
            alive["value"] = False

    panel.bind("<Destroy>", _on_panel_destroy)

    refresh()

    return {
        "refresh": refresh,
        "stage_all": stage_all_unstaged,
        "unstage_all": unstage_all,
        "get_repo_root": lambda: state["repo_root"],
        "get_status": lambda: state["status"],
    }