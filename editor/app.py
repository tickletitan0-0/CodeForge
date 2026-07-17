import tkinter as tk
from tkinter import filedialog
import re
import keyword
import subprocess
import sys
import tempfile
import os
import threading
import queue


def run():
    root = tk.Tk()
    root.title("CodeForge")
    root.geometry("800x600")

    # Top area: editor (left) + output panel (right), side by side
    top_frame = tk.Frame(root)
    top_frame.pack(fill="both", expand=True, side="top")

    # Frame to hold line numbers + text area side by side
    editor_frame = tk.Frame(top_frame)
    editor_frame.pack(fill="both", expand=True, side="left")

    line_numbers = tk.Text(
        editor_frame, width=4, padx=4, takefocus=0, border=0,
        background="#e8e8e8", state="disabled", wrap="none",
        font=("Consolas", 12)
    )
    line_numbers.pack(side="left", fill="y")

    text_area = tk.Text(editor_frame, wrap="none", undo=True, font=("Consolas", 12))
    text_area.pack(side="left", fill="both", expand=True)

    text_scrollbar = tk.Scrollbar(editor_frame, command=text_area.yview)
    text_scrollbar.pack(side="left", fill="y")

    def on_text_scroll(first, last):
        # Keeps the scrollbar and the line-number gutter in sync with
        # whatever moved the editor's viewport (wheel, keys, drag, resize).
        text_scrollbar.set(first, last)
        line_numbers.yview_moveto(float(first))

    text_area.config(yscrollcommand=on_text_scroll)

    def on_linenum_scroll(event):
        # Let scrolling while hovered over the gutter also scroll the editor.
        text_area.yview_scroll(int(-1 * (event.delta / 120)), "units")
        return "break"

    line_numbers.bind("<MouseWheel>", on_linenum_scroll)

    # Output panel for run results (now docked on the right)
    output_frame = tk.Frame(top_frame, width=300)
    output_frame.pack(fill="y", side="right")
    output_frame.pack_propagate(False)

    output_label = tk.Label(output_frame, text="Output", anchor="w", background="#333333", foreground="white")
    output_label.pack(fill="x")

    output_area = tk.Text(output_frame, font=("Consolas", 10), background="#1e1e1e", foreground="#dcdcdc", state="disabled", wrap="word")
    output_area.pack(fill="both", expand=True)

    # Terminal panel, docked below the editor/output row
    from editor.terminal import Terminal

    terminal = Terminal(root)
    terminal.pack(fill="x", side="bottom")

    def focus_terminal_entry(event=None):
        terminal_entry.focus_set()
        terminal_entry.icursor(tk.END)

        # Clicking anywhere in the terminal panel (output area, label, or the
        # panel background) sends focus to the actual input row, since it's easy
        # to click the read-only output area by mistake and think nothing responds.
        terminal_output.bind("<Button-1>", lambda e: root.after(1, focus_terminal_entry))
        terminal_label.bind("<Button-1>", focus_terminal_entry)
        terminal_frame.bind("<Button-1>", focus_terminal_entry)

    # ---------- Line numbers ----------
    def update_line_numbers(event=None):
        line_numbers.config(state="normal")
        line_numbers.delete("1.0", tk.END)

        num_lines = int(text_area.index("end-1c").split(".")[0])
        line_numbers_string = "\n".join(str(i) for i in range(1, num_lines + 1))
        line_numbers.insert("1.0", line_numbers_string)

        line_numbers.config(state="disabled")

    # ---------- Syntax highlighting ----------
    def setup_highlight_tags():
        text_area.tag_configure("keyword", foreground="#569CD6")
        text_area.tag_configure("string", foreground="#CE9178")
        text_area.tag_configure("comment", foreground="#6A9955")
        text_area.tag_configure("number", foreground="#B5CEA8")
        text_area.tag_configure("function", foreground="#DCDCAA")

    def highlight_syntax(event=None):
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

    def on_key_release(event=None):
        update_line_numbers()
        highlight_syntax()

    text_area.bind("<KeyRelease>", on_key_release)

    # ---------- File operations ----------
    def new_file():
        text_area.delete("1.0", tk.END)
        current_file["path"] = None
        root.title("CodeForge - Untitled")
        update_line_numbers()
        highlight_syntax()

    def open_file():
        path = filedialog.askopenfilename(
            filetypes=[("Python files", "*.py"), ("All files", "*.*")]
        )
        if path:
            with open(path, "r") as f:
                content = f.read()
            text_area.delete("1.0", tk.END)
            text_area.insert("1.0", content)
            current_file["path"] = path
            root.title(f"CodeForge - {path}")
            update_line_numbers()
            highlight_syntax()

    def save_file():
        if current_file["path"]:
            with open(current_file["path"], "w") as f:
                f.write(text_area.get("1.0", tk.END))
        else:
            save_as_file()

    def save_as_file():
        path = filedialog.asksaveasfilename(
            defaultextension=".py",
            filetypes=[("Python files", "*.py"), ("All files", "*.*")]
        )
        if path:
            with open(path, "w") as f:
                f.write(text_area.get("1.0", tk.END))
            current_file["path"] = path
            root.title(f"CodeForge - {path}")

    # ---------- Run code ----------
    def run_code():
        code = text_area.get("1.0", tk.END)

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
    file_menu.add_command(label="New", command=new_file, accelerator="Ctrl+N")
    file_menu.add_command(label="Open", command=open_file, accelerator="Ctrl+O")
    file_menu.add_command(label="Save", command=save_file, accelerator="Ctrl+S")
    file_menu.add_command(label="Save As", command=save_as_file)
    file_menu.add_separator()

    def on_exit():
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
    root.bind("<F5>", lambda e: run_code())

    setup_highlight_tags()
    update_line_numbers()
    highlight_syntax()

    # Windows sometimes never issues an initial paint for nested custom-
    # colored Frames (like the terminal's "$" prompt row) — a long-standing
    # Tk/Windows quirk. A same-size resize can get silently coalesced by
    # Windows and do nothing, so instead we minimize and immediately restore
    # the window once at startup; that forces a real, full repaint from the
    # OS rather than just a Tk-side layout recompute.
    def force_repaint():
        terminal_divider.lift()
        terminal_input_frame.lift()
        terminal_prompt.lift()
        terminal_entry.lift()
        root.update_idletasks()
        root.iconify()
        root.after(50, root.deiconify)
        root.after(100, root.focus_force)
        root.after(110, terminal_entry.focus_set)

    root.after(150, force_repaint)

    root.mainloop()