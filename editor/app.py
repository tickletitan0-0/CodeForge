import tkinter as tk
from tkinter import filedialog
from tkinter import ttk
from tkinter import messagebox
import re
import keyword
import subprocess
import sys
import tempfile
import os


def run():
    root = tk.Tk()
    root.title("CodeForge")
    root.geometry("800x600")
    main_frame = tk.Frame(root)
    main_frame.pack(fill="both", expand=True)

    explorer_frame = tk.Frame(main_frame, width=220, bg="#252526")
    explorer_frame.pack(side="left", fill="y")
    explorer_frame.pack_propagate(False)

    tk.Label(
        explorer_frame,
        text="EXPLORER",
        bg="#252526",
        fg="white",
        anchor="w"
    ).pack(fill="x", padx=10, pady=5)

    project_tree = ttk.Treeview(explorer_frame)
    project_tree.pack(fill="both", expand=True)

    center_frame = tk.Frame(main_frame)
    center_frame.pack(side="left", fill="both", expand=True)

    tab_control = ttk.Notebook(center_frame)
    tab_control.pack(fill="both", expand=True)

    project_path = None
    tab_editors = {}       # tab widget name (str) -> editor dict
    untitled_count = [0]   # counter used to name new blank tabs

    # ---------------- Output ----------------

    output_frame = tk.Frame(main_frame, width=300)
    output_frame.pack(side="right", fill="y")
    output_frame.pack_propagate(False)

    output_label = tk.Label(
        output_frame,
        text="Output",
        anchor="w",
        bg="#333333",
        fg="white"
    )
    output_label.pack(fill="x")

    output_area = tk.Text(
        output_frame,
        font=("Consolas", 10),
        bg="#1e1e1e",
        fg="#dcdcdc",
        state="disabled",
        wrap="word"
    )
    output_area.pack(fill="both", expand=True)

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
        text_area.tag_configure("keyword", foreground="#569CD6")
        text_area.tag_configure("string", foreground="#CE9178")
        text_area.tag_configure("comment", foreground="#6A9955")
        text_area.tag_configure("number", foreground="#B5CEA8")
        text_area.tag_configure("function", foreground="#DCDCAA")

        # Background-only tag for the current line - keep it lowest priority
        # so it never hides syntax colors or the selection highlight.
        text_area.tag_configure("current_line", background="#e8f2ff")
        text_area.tag_lower("current_line")

        # Even lower priority than the current-line highlight, so the guide
        # is only visible outside the active line.
        text_area.tag_configure("indent_guide", background="#cfcfcf")
        text_area.tag_lower("indent_guide")

    def highlight_current_line(text_area):
        text_area.tag_remove("current_line", "1.0", tk.END)
        line = text_area.index("insert").split(".")[0]
        text_area.tag_add("current_line", f"{line}.0", f"{line}.0+1line")

    def update_indent_guides(text_area):
        text_area.tag_remove("indent_guide", "1.0", tk.END)

        total_lines = int(text_area.index("end-1c").split(".")[0])
        indent_width = 4

        for line_no in range(1, total_lines + 1):
            line_text = text_area.get(f"{line_no}.0", f"{line_no}.end")
            stripped = line_text.lstrip(" ")
            indent_len = len(line_text) - len(stripped)

            col = 0
            while col < indent_len:
                text_area.tag_add("indent_guide", f"{line_no}.{col}", f"{line_no}.{col + 1}")
                col += indent_width

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
    def bind_auto_indent(text_area):
        def on_return(event, ta=text_area):
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
    def bind_bracket_completion(text_area):
        def insert_pair(open_char, close_char):
            def handler(event, ta=text_area):
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
                next_char = ta.get("insert", "insert+1c")
                if next_char == close_char:
                    ta.mark_set("insert", "insert+1c")
                    return "break"
                return None
            return handler

        def handle_quote(quote_char):
            def handler(event, ta=text_area):
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
            background="#e8e8e8",
            state="disabled",
            wrap="none",
            font=("Consolas", 12)
        )
        line_numbers.pack(side="left", fill="y")

        text_area = tk.Text(
            editor_frame,
            wrap="none",
            undo=True,
            font=("Consolas", 12)
        )
        text_area.pack(side="left", fill="both", expand=True)

        text_scrollbar = tk.Scrollbar(editor_frame, command=text_area.yview)
        text_scrollbar.pack(side="left", fill="y")

        def on_text_scroll(first, last, ln=line_numbers, sb=text_scrollbar):
            sb.set(first, last)
            ln.yview_moveto(float(first))

        text_area.config(yscrollcommand=on_text_scroll)

        def on_linenum_scroll(event, ta=text_area):
            ta.yview_scroll(int(-event.delta / 120), "units")
            return "break"

        line_numbers.bind("<MouseWheel>", on_linenum_scroll)

        tab_id = str(tab_frame)
        title = make_tab_title(path)

        editor = {
            "frame": tab_frame,
            "text": text_area,
            "line_numbers": line_numbers,
            "path": path,
            "title": title,
            "dirty": False
        }
        tab_editors[tab_id] = editor

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
            update_indent_guides(ed["text"])

        def on_click(event, ed=editor):
            # Let the click land the cursor first, then re-highlight its line
            ed["text"].after_idle(lambda: highlight_current_line(ed["text"]))

        def on_modified(event, ed=editor):
            if ed["text"].edit_modified():
                mark_dirty(ed)
                ed["text"].edit_modified(False)

        text_area.bind("<KeyRelease>", on_key_release)
        text_area.bind("<ButtonRelease-1>", on_click)
        text_area.bind("<<Modified>>", on_modified)

        bind_auto_indent(text_area)
        bind_bracket_completion(text_area)

        tab_control.add(tab_frame, text=title)
        tab_control.select(tab_frame)

        update_line_numbers(editor)
        highlight_syntax(text_area)
        highlight_current_line(text_area)
        update_indent_guides(text_area)

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
        editor = get_current_editor()
        if not editor:
            return
        refresh_window_title(editor)
        update_line_numbers(editor)
        highlight_syntax(editor["text"])
        highlight_current_line(editor["text"])
        update_indent_guides(editor["text"])

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
            update_indent_guides(current["text"])
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
    def run_code():
        editor = get_current_editor()
        if not editor:
            return

        code = editor["text"].get("1.0", tk.END)

        # Write current code to a temp file so it can be run in its own process
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as tmp:
            tmp.write(code)
            tmp_path = tmp.name

        output_area.config(state="normal")
        output_area.delete("1.0", tk.END)
        output_area.insert("1.0", "Running...\n")
        output_area.config(state="disabled")
        root.update_idletasks()

        try:
            result = subprocess.run(
                [sys.executable, tmp_path],
                capture_output=True, text=True, timeout=10
            )
            output_text = result.stdout
            if result.stderr:
                output_text += result.stderr
        except subprocess.TimeoutExpired:
            output_text = "Error: code took too long to run (timeout after 10s)."
        finally:
            os.remove(tmp_path)

        output_area.config(state="normal")
        output_area.delete("1.0", tk.END)
        output_area.insert("1.0", output_text if output_text else "(no output)")
        output_area.config(state="disabled")

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
        root.destroy()

    file_menu.add_command(label="Exit", command=on_exit)
    menu_bar.add_cascade(label="File", menu=file_menu)

    root.protocol("WM_DELETE_WINDOW", on_exit)

    run_menu = tk.Menu(menu_bar, tearoff=0)
    run_menu.add_command(label="Run", command=run_code, accelerator="F5")
    menu_bar.add_cascade(label="Run", menu=run_menu)

    root.config(menu=menu_bar)

    root.bind("<Control-n>", lambda e: new_file())
    root.bind("<Control-o>", lambda e: open_file())
    root.bind("<Control-s>", lambda e: save_file())
    root.bind("<Control-w>", lambda e: close_tab())
    root.bind("<F5>", lambda e: run_code())

    # Start with a single blank tab
    create_tab()

    root.mainloop()