"""fun_effects.py - playful, purely-cosmetic extras layered on top of the
editor: an error flash / success glow, a Konami-code easter egg, a
typing streak indicator, and an idle mascot.

Design goals, matching the rest of this codebase:
  - No new dependencies - just tkinter, same as everything else.
  - Fire-and-forget: every effect here owns its own widgets/after() jobs
    and tears itself down. Callers never have to hold a reference or
    remember to clean anything up.
  - Nothing here is safety/logic-critical - if a widget has already been
    destroyed (tab closed mid-animation, etc.) every step function just
    bails via winfo_exists() rather than raising.
"""
import tkinter as tk


# ---------------- Error flash ----------------

def error_flash(frame, color="#ff5555", pulses=3, interval=90):
    """Pulses `frame`'s border a couple of times in warning red - the
    "something just went wrong" cue for a new lint error or a failed Run,
    without touching the frame's actual layout (a true side-to-side shake
    isn't practical here since the editor frame is a fill+expand pack
    child - resizing its padding would squash its contents instead of
    moving them)."""
    if not frame or not frame.winfo_exists():
        return
    try:
        orig_thickness = frame.cget("highlightthickness")
        orig_bg = frame.cget("highlightbackground")
    except tk.TclError:
        return

    frame.configure(highlightthickness=3)

    def step(i=0, on=True):
        if not frame.winfo_exists():
            return
        if i >= pulses * 2:
            try:
                frame.configure(highlightthickness=orig_thickness, highlightbackground=orig_bg)
            except tk.TclError:
                pass
            return
        try:
            frame.configure(highlightbackground=color if on else orig_bg)
        except tk.TclError:
            return
        frame.after(interval, step, i + 1, not on)

    step()


def _blend_color(widget, color_a, color_b, t):
    """Linear-interpolate between two colors at t in [0, 1]. Colors are
    resolved through the widget's own winfo_rgb rather than parsed as
    '#rrggbb' text, because Tk's default highlightbackground (on a frame
    that never had it explicitly set, like output_frame) can come back as
    a platform color *name* (e.g. 'SystemButtonFace' on Windows) instead
    of hex - parsing that as hex digits used to raise partway through the
    very first fade step, which silently killed the whole fade loop and
    left the border stuck on the glow color forever."""
    ar, ag, ab = widget.winfo_rgb(color_a)
    br, bg, bb = widget.winfo_rgb(color_b)
    r = round(ar + (br - ar) * t) >> 8
    g = round(ag + (bg - ag) * t) >> 8
    b = round(ab + (bb - ab) * t) >> 8
    return f"#{r:02x}{g:02x}{b:02x}"


def glow(frame, color, hold_ms=2000, fade_ms=600, thickness=3):
    """Lights up `frame`'s border in `color` and holds it there, then eases
    back to the original border over `fade_ms` - the "everything's fine
    for a few seconds" cousin of error_flash's urgent pulsing. Used for
    Run results: green for a clean exit, red for a non-zero one.

    Safe to call again on the same frame while an earlier glow on it is
    still holding/fading (e.g. Run pressed twice quickly) - it cancels
    whatever that call had pending and takes over, rather than the two
    competing to set the border and possibly leaving it on a stale color.
    """
    if not frame or not frame.winfo_exists():
        return

    state = getattr(frame, "_fun_effects_glow_state", None)
    if state is None:
        try:
            orig_thickness = frame.cget("highlightthickness")
            orig_bg = frame.cget("highlightbackground")
        except tk.TclError:
            return
        state = {"orig_thickness": orig_thickness, "orig_bg": orig_bg, "job": None}
        frame._fun_effects_glow_state = state
    elif state["job"] is not None:
        try:
            frame.after_cancel(state["job"])
        except (ValueError, tk.TclError):
            pass
        state["job"] = None

    try:
        frame.configure(highlightthickness=thickness, highlightbackground=color)
    except tk.TclError:
        return

    fade_steps = 10

    def fade(i=0):
        if not frame.winfo_exists():
            return
        if i > fade_steps:
            try:
                frame.configure(highlightthickness=state["orig_thickness"], highlightbackground=state["orig_bg"])
            except tk.TclError:
                pass
            state["job"] = None
            try:
                del frame._fun_effects_glow_state
            except AttributeError:
                pass
            return
        try:
            blended = _blend_color(frame, color, state["orig_bg"], i / fade_steps)
            frame.configure(highlightbackground=blended)
        except tk.TclError:
            state["job"] = None
            return
        state["job"] = frame.after(max(fade_ms // fade_steps, 1), fade, i + 1)

    state["job"] = frame.after(hold_ms, fade)


# ---------------- Cursor pulse ----------------

_CURSOR_PULSE_TAG = "_fun_effects_cursor_pulse"


def cursor_pulse(text_widget, index, color, base_color, hold_ms=120, fade_ms=450, fade_steps=8):
    """Briefly highlights the line containing `index` in `color`, then
    eases back to `base_color` over `fade_ms` - glow()'s quieter cousin,
    for "you just landed here" cues (a search jump, etc.) rather than
    glow's "this finished" cue, so it holds for a shorter beat and never
    touches the widget's actual layout/border. `base_color` is passed in
    rather than read off the widget beforehand (the way glow() reads the
    frame's own highlightbackground) because a Text tag has no single
    "current" background to read back - the line under it might be plain
    editor background, the current-line tag, a search match, etc. - so
    the caller just says what it should settle back into.

    Safe to call again on the same widget while an earlier pulse is
    still fading (e.g. jumping between search matches quickly) - it
    cancels whatever that call had pending and restarts at the new
    location, rather than the two competing over the tag.
    """
    if not text_widget or not text_widget.winfo_exists():
        return

    state = getattr(text_widget, "_fun_effects_pulse_state", None)
    if state is not None and state.get("job") is not None:
        try:
            text_widget.after_cancel(state["job"])
        except (ValueError, tk.TclError):
            pass
    state = {"job": None}
    text_widget._fun_effects_pulse_state = state

    try:
        text_widget.tag_remove(_CURSOR_PULSE_TAG, "1.0", "end")
        line_start = text_widget.index(f"{index} linestart")
        line_end = text_widget.index(f"{index} lineend+1c")
        text_widget.tag_configure(_CURSOR_PULSE_TAG, background=color)
        text_widget.tag_add(_CURSOR_PULSE_TAG, line_start, line_end)
        # Above the current-line/search-match tags so the pulse actually
        # reads as a distinct flash rather than being masked by whichever
        # of those the line already has.
        text_widget.tag_raise(_CURSOR_PULSE_TAG)
    except tk.TclError:
        return

    fade_steps = max(fade_steps, 1)

    def fade(i=0):
        if not text_widget.winfo_exists():
            return
        if i > fade_steps:
            try:
                text_widget.tag_remove(_CURSOR_PULSE_TAG, "1.0", "end")
            except tk.TclError:
                pass
            state["job"] = None
            return
        try:
            blended = _blend_color(text_widget, color, base_color, i / fade_steps)
            text_widget.tag_configure(_CURSOR_PULSE_TAG, background=blended)
        except tk.TclError:
            state["job"] = None
            return
        state["job"] = text_widget.after(max(fade_ms // fade_steps, 1), fade, i + 1)

    state["job"] = text_widget.after(hold_ms, fade)


# ---------------- Konami code easter egg ----------------

_KONAMI_SEQUENCE = [
    "Up", "Up", "Down", "Down", "Left", "Right", "Left", "Right", "b", "a"
]


def install_konami_code(root, on_trigger):
    """Watches keysyms globally (bind_all, so it fires no matter which
    widget has focus) for the classic up-up-down-down-left-right-left-
    right-b-a sequence. Calls on_trigger() once when matched, then resets -
    holding a rolling buffer rather than a strict position pointer so a
    stray keystroke mid-sequence doesn't force starting over from scratch
    unless it actually breaks the match."""
    state = {"buffer": []}

    def on_key(event):
        keysym = event.keysym
        buf = state["buffer"]
        buf.append(keysym)
        if len(buf) > len(_KONAMI_SEQUENCE):
            buf.pop(0)
        if buf == _KONAMI_SEQUENCE:
            state["buffer"] = []
            on_trigger()

    root.bind_all("<Key>", on_key, add="+")


# ---------------- Typing streak ----------------

class StreakTracker:
    """Tracks how long someone has been actively typing without a pause
    longer than `pause_limit` seconds, and renders it as a status-bar-
    friendly flame string. Session-only (not persisted) - it's meant as a
    little in-the-moment nudge, not another number added to the all-time
    stats file.
    """

    TIERS = [
        (0, ""),
        (20, "\U0001F525"),
        (60, "\U0001F525\U0001F525"),
        (180, "\U0001F525\U0001F525\U0001F525"),
    ]

    def __init__(self, pause_limit=8):
        self.pause_limit = pause_limit
        self.streak_started = None
        self.last_keystroke = None

    def keystroke(self):
        """Call on every keystroke. Returns the current display string."""
        import time
        now = time.time()
        if self.last_keystroke is None or (now - self.last_keystroke) > self.pause_limit:
            self.streak_started = now
        self.last_keystroke = now
        return self.display(now)

    def display(self, now=None):
        import time
        if now is None:
            now = time.time()
        if self.last_keystroke is None or (now - self.last_keystroke) > self.pause_limit:
            self.streak_started = None
            return ""
        elapsed = now - self.streak_started
        icon = ""
        for threshold, label in self.TIERS:
            if elapsed >= threshold:
                icon = label
        if not icon:
            return ""
        minutes, seconds = divmod(int(elapsed), 60)
        time_str = f"{minutes}m{seconds:02d}s" if minutes else f"{seconds}s"
        return f"{icon} {time_str}"


# ---------------- Idle mascot ----------------

_MASCOT_FRAMES = ["( o.o)", "( -.-)", "( o.o)", "( ^.^)"]


def install_idle_mascot(root, get_target, theme, idle_seconds=45, check_interval_ms=2000):
    """Shows a tiny sleepy ASCII face in the bottom-right corner of
    whatever widget `get_target()` returns (called fresh each time, so it
    naturally follows the active tab) after `idle_seconds` with no
    keyboard/mouse activity, and clears it the moment activity resumes.

    get_target: zero-arg callable returning the widget to anchor to (e.g.
    the current tab's editor_frame), or None if there's nothing to anchor
    to right now (no tabs open).
    """
    state = {"last_activity": None, "mascot": None, "anim_job": None}

    import time

    def mark_active(event=None):
        state["last_activity"] = time.time()
        _clear_mascot()

    def _clear_mascot():
        if state["mascot"] is not None and state["mascot"].winfo_exists():
            state["mascot"].destroy()
        state["mascot"] = None
        if state["anim_job"] is not None:
            try:
                root.after_cancel(state["anim_job"])
            except (ValueError, tk.TclError):
                pass
            state["anim_job"] = None

    def _animate(frame_idx=0):
        mascot = state["mascot"]
        if mascot is None or not mascot.winfo_exists():
            return
        mascot.configure(text=_MASCOT_FRAMES[frame_idx % len(_MASCOT_FRAMES)])
        state["anim_job"] = root.after(700, _animate, frame_idx + 1)

    def _show_mascot():
        target = get_target()
        if target is None or not target.winfo_exists():
            return
        if state["mascot"] is not None:
            return
        label = tk.Label(
            target, text=_MASCOT_FRAMES[0],
            bg=theme.get("panel_header_bg", "#2a2a2a"),
            fg=theme.get("muted_fg", "#888888"),
            font=("Courier New", 10),
            padx=6, pady=2
        )
        label.place(relx=1.0, rely=1.0, x=-6, y=-6, anchor="se")
        label.bind("<Button-1>", lambda e: mark_active())
        state["mascot"] = label
        _animate()

    def _tick():
        if state["last_activity"] is not None:
            idle_for = time.time() - state["last_activity"]
            if idle_for >= idle_seconds and state["mascot"] is None:
                _show_mascot()
        root.after(check_interval_ms, _tick)

    state["last_activity"] = time.time()
    root.bind_all("<Key>", mark_active, add="+")
    root.bind_all("<Motion>", mark_active, add="+")
    root.after(check_interval_ms, _tick)