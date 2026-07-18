"""
Background music mini-player for CodeForge.

Streams audio-only from a YouTube video or playlist URL and plays it in the
background while you code - a "Music" tab next to Output/Terminal with
Play/Pause/Next/Prev and a volume slider.

This needs two optional third-party pieces that are NOT part of the
standard library:

    pip install yt-dlp python-vlc

python-vlc is just Python bindings - it talks to the real VLC engine, which
also needs to be installed on the system: https://www.videolan.org/vlc/

Both imports are wrapped in try/except so the rest of the app works fine
without them installed; build_music_panel() just shows an install hint
instead of transport controls in that case, the same pattern app.py already
uses for the optional winpty/pty/tkinterdnd2 imports.
"""

import threading
import tkinter as tk

try:
    import yt_dlp
except ImportError:
    yt_dlp = None

try:
    import vlc
except ImportError:
    vlc = None

try:
    # music_player.py is being imported as part of the "editor" package.
    from .themes import load_last_music_url, save_last_music_url
except ImportError:
    # Standalone script - plain import, same fallback pattern app.py uses
    # for themes.py.
    from themes import load_last_music_url, save_last_music_url

DEPENDENCIES_OK = yt_dlp is not None and vlc is not None


class _Queue:
    """Just the list of tracks pulled from the last loaded URL, plus which
    one is current - kept separate from the UI so the transport functions
    below don't need a dozen nonlocal declarations apiece."""

    def __init__(self):
        self.entries = []  # [{"title": str, "url": str}, ...]
        self.index = -1

    def current(self):
        if 0 <= self.index < len(self.entries):
            return self.entries[self.index]
        return None


def _video_url(entry, fallback):
    """yt-dlp's flat playlist extraction gives back a bare video id in
    'url' for some extractors and a full URL for others - normalize to a
    full watch URL either way so the later per-track resolve step always
    gets something it can re-extract."""
    raw = entry.get("url")
    if raw and raw.startswith("http"):
        return raw
    vid = entry.get("id") or raw
    if vid:
        return f"https://www.youtube.com/watch?v={vid}"
    return entry.get("webpage_url") or fallback


def build_music_panel(parent, theme, on_track_change=None):
    """Build the mini player UI inside `parent`. Returns a dict of control
    functions (load_url/play_next/play_prev/toggle_play_pause/stop) - used
    by app.py for the global media-key bindings and the status bar mirror,
    though the panel is also fully self-contained via its own buttons.

    on_track_change(title_or_None, is_playing), if given, is called
    whenever the current track or playing/paused state changes - lets a
    caller (e.g. the main status bar) mirror "now playing" without polling.
    """

    panel = tk.Frame(parent, bg=theme["output_bg"])
    panel.pack(fill="both", expand=True)

    if not DEPENDENCIES_OK:
        missing = " ".join(
            name for name, mod in (("yt-dlp", yt_dlp), ("python-vlc", vlc)) if mod is None
        )
        tk.Label(
            panel,
            text=(
                "\U0001F3B5  Background music needs a couple of extra packages.\n\n"
                f"    pip install {missing}\n\n"
                "python-vlc also needs the VLC app installed on your system:\n"
                "    https://www.videolan.org/vlc/\n\n"
                "Then restart CodeForge and this tab will turn into a player."
            ),
            bg=theme["output_bg"],
            fg=theme["muted_fg"],
            justify="left",
            padx=16,
            pady=16,
            anchor="w",
        ).pack(anchor="w", fill="x")
        return {}

    instance = vlc.Instance("--no-video")
    player = instance.media_player_new()
    queue = _Queue()
    state = {"playing": False, "volume": 70}
    player.audio_set_volume(state["volume"])

    # Flipped off the moment `panel` is destroyed (see _on_panel_destroy
    # below). load_url()/_play_index() do their real work on background
    # threads and hand results back to the UI thread via panel.after(0, ...)
    # - if the app is closing or relaunching (theme switch does
    # root.destroy() + os.execv), those callbacks can still be sitting in
    # Tk's event queue and fire *after* the widgets are gone, which used to
    # blow up with "invalid command name ...": every deferred callback below
    # checks this flag first and bails out instead of touching dead widgets.
    alive = {"value": True}

    def _notify():
        if not alive["value"] or on_track_change is None:
            return
        entry = queue.current()
        title = entry["title"] if entry else None
        on_track_change(title, state["playing"])

    # ---------------- UI ----------------
    url_row = tk.Frame(panel, bg=theme["output_bg"])
    url_row.pack(fill="x", padx=10, pady=(10, 4))

    tk.Label(
        url_row, text="YouTube playlist / video URL:",
        bg=theme["output_bg"], fg=theme["output_fg"]
    ).pack(side="left")

    url_entry = tk.Entry(
        url_row, bg=theme["popup_bg"], fg=theme["popup_fg"],
        insertbackground=theme["output_fg"], relief="flat",
        highlightthickness=1, highlightbackground=theme["border"],
        highlightcolor=theme["accent"],
    )
    url_entry.pack(side="left", fill="x", expand=True, padx=(6, 6))
    last_url = load_last_music_url()
    if last_url:
        url_entry.insert(0, last_url)

    btn_opts = dict(
        bg=theme["panel_header_bg"], fg=theme["panel_header_fg"],
        activebackground=theme["editor_select_bg"], activeforeground=theme["editor_select_fg"],
        relief="flat", bd=0, highlightthickness=0, padx=10, pady=4, cursor="hand2",
    )

    load_btn = tk.Button(url_row, text="Load", **btn_opts)
    load_btn.pack(side="left")

    now_playing_label = tk.Label(
        panel, text="Nothing loaded yet - paste a playlist link above and hit Load.",
        bg=theme["output_bg"], fg=theme["accent"], anchor="w", padx=10,
        wraplength=420, justify="left",
    )
    now_playing_label.pack(fill="x", pady=(2, 2))

    status_label = tk.Label(
        panel, text="", bg=theme["output_bg"], fg=theme["muted_fg"], anchor="w", padx=10
    )
    status_label.pack(fill="x")

    controls_row = tk.Frame(panel, bg=theme["output_bg"])
    controls_row.pack(fill="x", padx=10, pady=10)

    prev_btn = tk.Button(controls_row, text="\u23EE Prev", **btn_opts)
    prev_btn.pack(side="left", padx=(0, 6))

    play_pause_btn = tk.Button(controls_row, text="\u25B6 Play", **btn_opts)
    play_pause_btn.pack(side="left", padx=(0, 6))

    next_btn = tk.Button(controls_row, text="Next \u23ED", **btn_opts)
    next_btn.pack(side="left", padx=(0, 6))

    tk.Label(
        controls_row, text="Vol", bg=theme["output_bg"], fg=theme["output_fg"]
    ).pack(side="left", padx=(18, 4))

    volume_slider = tk.Scale(
        controls_row, from_=0, to=100, orient="horizontal", showvalue=False,
        bg=theme["output_bg"], fg=theme["output_fg"],
        troughcolor=theme["panel_header_bg"], highlightthickness=0, length=110,
        bd=0,
    )
    volume_slider.set(state["volume"])
    volume_slider.pack(side="left")

    queue_list = tk.Listbox(
        panel, bg=theme["popup_bg"], fg=theme["popup_fg"],
        selectbackground=theme["popup_select_bg"], selectforeground=theme["popup_select_fg"],
        relief="flat", highlightthickness=0, activestyle="none",
    )
    queue_list.pack(fill="both", expand=True, padx=10, pady=(0, 10))

    # ---------------- Helpers ----------------
    def set_status(text):
        status_label.config(text=text)

    def refresh_now_playing():
        entry = queue.current()
        now_playing_label.config(
            text=("\u266A " + entry["title"]) if entry
            else "Nothing loaded yet - paste a playlist link above and hit Load."
        )
        queue_list.selection_clear(0, tk.END)
        if queue.index >= 0:
            queue_list.selection_set(queue.index)
            queue_list.see(queue.index)

    def refresh_queue_list():
        queue_list.delete(0, tk.END)
        for entry in queue.entries:
            queue_list.insert(tk.END, entry["title"])

    # ---------------- Transport ----------------
    def load_url(url=None, autoplay=True):
        if url is None:
            url = url_entry.get().strip()
        elif url != url_entry.get().strip():
            url_entry.delete(0, tk.END)
            url_entry.insert(0, url)
        if not url:
            return
        save_last_music_url(url)
        set_status("Loading playlist...")
        load_btn.config(state="disabled")

        def worker():
            try:
                ydl_opts = {"quiet": True, "extract_flat": "in_playlist", "skip_download": True}
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    info = ydl.extract_info(url, download=False)
            except Exception as exc:
                def report_error():
                    if not alive["value"]:
                        return
                    set_status(f"Couldn't load that URL ({exc})")
                    load_btn.config(state="normal")

                panel.after(0, report_error)
                return

            raw_entries = info.get("entries") if info and "entries" in info else [info]
            raw_entries = [e for e in (raw_entries or []) if e]
            entries = [
                {"title": e.get("title") or "Untitled", "url": _video_url(e, url)}
                for e in raw_entries
            ]

            def apply():
                if not alive["value"]:
                    return
                queue.entries = entries
                queue.index = -1
                refresh_queue_list()
                load_btn.config(state="normal")
                if not entries:
                    set_status("Loaded 0 tracks.")
                    return
                if autoplay:
                    set_status(f"Loaded {len(entries)} track(s).")
                    play_next()
                else:
                    set_status(f"Loaded {len(entries)} track(s) - press Play when ready.")
                    now_playing_label.config(text="\u266A Up next: " + entries[0]["title"])

            panel.after(0, apply)

        threading.Thread(target=worker, daemon=True).start()

    def _resolve_stream_url(webpage_url):
        ydl_opts = {"quiet": True, "format": "bestaudio/best", "skip_download": True}
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(webpage_url, download=False)
        return info["url"]

    def _play_index(i):
        if not queue.entries:
            return
        i = i % len(queue.entries)
        queue.index = i
        entry = queue.entries[i]
        set_status("Buffering...")

        def worker():
            try:
                stream_url = _resolve_stream_url(entry["url"])
            except Exception as exc:
                def report_error():
                    if alive["value"]:
                        set_status(f"Couldn't play that track ({exc})")

                panel.after(0, report_error)
                return

            def apply():
                if not alive["value"]:
                    return
                media = instance.media_new(stream_url)
                player.set_media(media)
                player.play()
                state["playing"] = True
                refresh_now_playing()
                set_status("Playing")
                play_pause_btn.config(text="\u23F8 Pause")
                _notify()

            panel.after(0, apply)

        threading.Thread(target=worker, daemon=True).start()

    def play_next():
        if queue.entries:
            _play_index(queue.index + 1 if queue.index + 1 < len(queue.entries) else 0)

    def play_prev():
        if queue.entries:
            _play_index(queue.index - 1 if queue.index > 0 else len(queue.entries) - 1)

    def toggle_play_pause():
        if queue.current() is None:
            if queue.entries:
                play_next()
            else:
                load_url()
            return
        if state["playing"]:
            player.pause()
            state["playing"] = False
            play_pause_btn.config(text="\u25B6 Play")
            set_status("Paused")
        else:
            player.play()
            state["playing"] = True
            play_pause_btn.config(text="\u23F8 Pause")
            set_status("Playing")
        _notify()

    def on_volume(val):
        vol = int(float(val))
        state["volume"] = vol
        player.audio_set_volume(vol)

    def play_selected(event=None):
        selection = queue_list.curselection()
        if selection:
            _play_index(selection[0])

    def stop():
        try:
            player.stop()
        except Exception:
            pass
        state["playing"] = False
        _notify()

    def pause():
        if state["playing"]:
            toggle_play_pause()

    def resume():
        if not state["playing"] and queue.current() is not None:
            toggle_play_pause()

    def is_playing():
        return state["playing"]

    load_btn.config(command=load_url)
    prev_btn.config(command=play_prev)
    play_pause_btn.config(command=toggle_play_pause)
    next_btn.config(command=play_next)
    volume_slider.config(command=on_volume)
    url_entry.bind("<Return>", lambda e: load_url())
    queue_list.bind("<Double-Button-1>", play_selected)

    def _on_panel_destroy(event):
        if event.widget is panel:
            alive["value"] = False
            stop()

    panel.bind("<Destroy>", _on_panel_destroy)

    if last_url:
        # Preload only - fetch the track list so Play is instant, but don't
        # start audio unprompted the moment the app opens.
        panel.after(200, lambda: load_url(last_url, autoplay=False))

    return {
        "load_url": load_url,
        "play_next": play_next,
        "play_prev": play_prev,
        "toggle_play_pause": toggle_play_pause,
        "pause": pause,
        "resume": resume,
        "is_playing": is_playing,
        "stop": stop,
    }