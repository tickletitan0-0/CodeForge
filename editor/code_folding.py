"""code_folding.py - indentation-based code folding for CodeForge.

One FoldEngine is created per editor *pane* (so a split editor's second
pane gets its own independent fold state, same as VS Code). It owns three
Text widgets that all need to move together: the code itself, the line-
number gutter, and a dedicated one-character-wide "fold gutter" that shows
a small triangle next to any line that starts a foldable block.

Why indentation rather than a real per-language parser: CodeForge already
supports five very different languages (Python/JS/HTML/CSS/Java) and
doesn't want a bespoke folding grammar for each. Indentation is imperfect
(a one-line `if (x) foo();` in a brace language won't be *wrong* to skip,
but it also won't offer anything to fold) - in exchange it works
identically and predictably everywhere, including in files CodeForge
doesn't otherwise recognize.

How the three widgets stay in sync while collapsed: Tk's Text `elide`
option removes a character range from *display* entirely (no residual
blank line), but each widget's own line count/geometry only matches the
others if the exact same line-range is elided in all three. So every
fold/unfold applies the same "_cf_hidden" tag range (by line number, which
lines up 1:1 across all three widgets) to text, line_numbers, and
fold_gutter together. Because the tag ranges are then consistent
everywhere, the app's existing fraction-based scroll sync
(`yview_moveto(fraction)`) keeps working unmodified even with folds active.

Nothing here ever raises out to a caller - a widget destroyed mid-flight
(tab/pane closed) is just checked for with winfo_exists() and skipped,
matching the "degrade quietly" convention used elsewhere in this app.
"""

import tkinter as tk

FOLD_ICON_OPEN = "\u25bc"   # full-size down-triangle: expanded, click to collapse
FOLD_ICON_CLOSED = "\u25b6"  # full-size right-triangle: collapsed, click to expand
FOLD_ICON_NONE = " "
_HIDDEN_TAG = "_cf_hidden"


class FoldEngine:
    def __init__(self, text, line_numbers, fold_gutter, on_toggle=None):
        """`on_toggle` is an optional zero-arg callback fired after a
        fold/unfold from a gutter click, so the caller can piggyback its
        own post-toggle bookkeeping (re-rendering the minimap viewport,
        redrawing indent guides, etc.) without this module needing to
        know those systems exist."""
        self.text = text
        self.line_numbers = line_numbers
        self.fold_gutter = fold_gutter
        self.on_toggle = on_toggle
        self.ranges = {}   # start_line -> end_line (1-based, inclusive)
        self.folded = set()  # start_lines currently collapsed
        self._last_content = None    # last content compute_ranges() scanned
        self._last_marks = None      # last gutter icon list render() drew

        for widget in (text, line_numbers, fold_gutter):
            widget.tag_configure(_HIDDEN_TAG, elide=True)

        fold_gutter.bind("<Button-1>", self._on_click)

    # ---------------- range detection ----------------

    @staticmethod
    def _indent(line):
        """Indentation width of `line`, or None if it's blank (blank
        lines don't participate in fold-range detection on their own -
        they just ride along inside whatever region they're sandwiched
        between)."""
        stripped = line.lstrip(" \t")
        if not stripped:
            return None
        return len(line) - len(stripped)

    def compute_ranges(self):
        if not self.text.winfo_exists():
            return
        try:
            content = self.text.get("1.0", "end-1c")
        except tk.TclError:
            return

        # A fold/unfold click never touches the document itself - only
        # elide tags - so on every click after the first this is exactly
        # the same content already scanned last time. Re-walking a huge
        # file line by line on every single click is where the lag on
        # big files was coming from, for no payoff (the ranges can't
        # have changed). Only worth re-scanning once the text is
        # actually different from what's already on record.
        if content == self._last_content:
            return
        self._last_content = content

        lines = content.split("\n")
        n = len(lines)
        ranges = {}

        for i in range(n):
            indent = self._indent(lines[i])
            if indent is None:
                continue

            # First non-blank line after this one - if it isn't more
            # indented, line i has nothing under it to fold.
            j = i + 1
            while j < n and self._indent(lines[j]) is None:
                j += 1
            if j >= n or self._indent(lines[j]) <= indent:
                continue

            # Extend through every subsequent line that's either blanker
            # (rides along) or still more indented than the fold's start;
            # stop at the first line that dedents back to <= indent.
            # Trailing blank lines right before that dedent are left out
            # of `end` so a fold never swallows the blank separator above
            # the next block.
            end = j
            k = j
            while k < n:
                ind_k = self._indent(lines[k])
                if ind_k is None:
                    k += 1
                    continue
                if ind_k > indent:
                    end = k
                    k += 1
                else:
                    break

            ranges[i + 1] = end + 1  # to 1-based line numbers

        self.ranges = ranges
        # A fold whose start line is no longer foldable (its block got
        # deleted, dedented, etc.) can't stay meaningfully collapsed.
        still_valid = self.folded & set(ranges.keys())
        for stale in self.folded - still_valid:
            self._remove_hidden_everywhere(stale)
        self.folded = still_valid

    # ---------------- fold / unfold ----------------

    def fold(self, start_line):
        end_line = self.ranges.get(start_line)
        if not end_line or start_line in self.folded:
            return
        self.folded.add(start_line)
        self._apply_hidden(start_line, end_line)

    def unfold(self, start_line):
        if start_line not in self.folded:
            return
        self.folded.discard(start_line)
        self._remove_hidden_everywhere(start_line)

    def toggle(self, start_line):
        if start_line not in self.ranges:
            return
        if start_line in self.folded:
            self.unfold(start_line)
        else:
            self.fold(start_line)

    def fold_all(self):
        self.compute_ranges()
        # Outermost blocks first so an already-collapsed ancestor doesn't
        # make a nested descendant's line range look empty/unreachable.
        for start in sorted(self.ranges):
            self.fold(start)
        self.render()

    def unfold_all(self):
        for widget in (self.text, self.line_numbers, self.fold_gutter):
            if widget.winfo_exists():
                widget.tag_remove(_HIDDEN_TAG, "1.0", "end")
        self.folded.clear()
        self.render()

    def _apply_hidden(self, start_line, end_line):
        for widget in (self.text, self.line_numbers, self.fold_gutter):
            if not widget.winfo_exists():
                continue
            try:
                widget.tag_add(_HIDDEN_TAG, f"{start_line}.end", f"{end_line}.end")
            except tk.TclError:
                pass

    def _remove_hidden_everywhere(self, start_line):
        end_line = self.ranges.get(start_line)

        if not end_line:
            # Range no longer known (e.g. block was deleted out from
            # under a stale fold) - clear the whole line to be safe
            # rather than leave orphaned hidden text.
            for widget in (self.text, self.line_numbers, self.fold_gutter):
                if not widget.winfo_exists():
                    continue
                try:
                    widget.tag_remove(_HIDDEN_TAG, f"{start_line}.0", f"{start_line}.end+50l")
                except tk.TclError:
                    pass
            return

        # Any OTHER fold still collapsed *inside* this range (e.g. a
        # method left folded while its containing class gets re-expanded)
        # has to stay hidden. Unhiding the whole start_line..end_line
        # span unconditionally would strip its hidden tag out from under
        # it on every widget including text - self.folded would still
        # list it as collapsed, but render() only ever re-asserts the
        # hidden tag on line_numbers/fold_gutter (see render()'s docstring),
        # never on text. That leaves text showing lines the two gutters
        # keep eliding, permanently offsetting every line number/arrow
        # below it from the code line it's meant to label. So: only
        # unhide the gaps between still-folded nested children, not
        # their own collapsed bodies.
        nested = sorted(
            s for s in self.folded
            if s != start_line and start_line < s <= end_line and self.ranges.get(s)
        )

        segments = []
        cursor = start_line
        for child_start in nested:
            child_end = self.ranges[child_start]
            if child_start > cursor:
                segments.append((cursor, child_start))
            cursor = max(cursor, child_end)
        if cursor < end_line:
            segments.append((cursor, end_line))

        for widget in (self.text, self.line_numbers, self.fold_gutter):
            if not widget.winfo_exists():
                continue
            for seg_start, seg_end in segments:
                try:
                    widget.tag_remove(_HIDDEN_TAG, f"{seg_start}.end", f"{seg_end}.end")
                except tk.TclError:
                    pass

    # ---------------- gutter rendering ----------------

    def render(self):
        """Rebuilds the fold-triangle gutter to match the current
        document, and re-applies elide ranges to the line-number gutter
        for any still-folded region - line_numbers gets its text fully
        torn down and reinserted whenever the line count changes (see
        update_line_numbers in app.py), which wipes any tags that were on
        it, so those ranges need reasserting every render() pass rather
        than just once at fold time."""
        if not self.fold_gutter.winfo_exists() or not self.text.winfo_exists():
            return
        self.compute_ranges()
        try:
            num_lines = int(self.text.index("end-1c").split(".")[0])
        except tk.TclError:
            return

        marks = []
        for i in range(1, num_lines + 1):
            if i in self.ranges:
                marks.append(FOLD_ICON_CLOSED if i in self.folded else FOLD_ICON_OPEN)
            else:
                marks.append(FOLD_ICON_NONE)

        try:
            if self._last_marks is not None and len(self._last_marks) == len(marks):
                # Same line count as last render - nothing was inserted or
                # deleted, just a fold toggled - so the vast majority of
                # rows are identical to what's already drawn. Rewriting
                # only the rows whose icon actually changed (usually just
                # the one that was clicked) avoids the full delete+insert
                # of the whole gutter, which is both the visible blink and
                # the real lag on a many-thousand-line file.
                self.fold_gutter.config(state="normal")
                for i, (old, new) in enumerate(zip(self._last_marks, marks), start=1):
                    if old != new:
                        self.fold_gutter.delete(f"{i}.0", f"{i}.end")
                        self.fold_gutter.insert(f"{i}.0", new)
                self.fold_gutter.config(state="disabled")
            else:
                self.fold_gutter.config(state="normal")
                self.fold_gutter.delete("1.0", "end")
                self.fold_gutter.insert("1.0", "\n".join(marks))
                self.fold_gutter.config(state="disabled")
        except tk.TclError:
            return
        self._last_marks = marks

        for start_line in self.folded:
            end_line = self.ranges.get(start_line)
            if not end_line:
                continue
            for widget in (self.line_numbers, self.fold_gutter):
                if widget.winfo_exists():
                    try:
                        widget.tag_add(_HIDDEN_TAG, f"{start_line}.end", f"{end_line}.end")
                    except tk.TclError:
                        pass

    def _on_click(self, event):
        try:
            index = self.fold_gutter.index(f"@{event.x},{event.y}")
        except tk.TclError:
            return "break"
        line = int(index.split(".")[0])
        self.toggle(line)
        self.render()
        if self.on_toggle:
            self.on_toggle()
        return "break"

    def toggle_at_line(self, line):
        """Toggle whichever fold *contains* `line` (not just one that
        starts exactly on it) - used for the "Toggle Fold" keyboard
        shortcut, fired from wherever the cursor happens to be inside a
        block rather than requiring the cursor sit on the header line."""
        self.compute_ranges()
        start = None
        for s, e in self.ranges.items():
            if s <= line <= e:
                if start is None or s > start:
                    start = s
        if start is None and line in self.ranges:
            start = line
        if start is not None:
            self.toggle(start)
            self.render()