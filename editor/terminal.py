import tkinter as tk
from tkinter.scrolledtext import ScrolledText
from winpty import PtyProcess
import threading


class Terminal(tk.Frame):
    def __init__(self, parent):
        super().__init__(parent, bg="#1e1e1e")

        self.proc = None

        title = tk.Label(
            self,
            text="Terminal",
            bg="#333333",
            fg="white",
            anchor="w"
        )
        title.pack(fill="x")

        self.output = ScrolledText(
            self,
            bg="#0c0c0c",
            fg="white",
            insertbackground="white",
            wrap="word"
        )
        self.output.pack(fill="both", expand=True)

        self.output.config(state="disabled")

        self.entry = tk.Entry(
            self,
            bg="#1e1e1e",
            fg="white",
            insertbackground="white",
            relief="flat"
        )
        self.entry.pack(fill="x")

        self.entry.bind("<Return>", self.send_command)

    def start(self):
        self.proc = PtyProcess.spawn("powershell.exe")

        threading.Thread(
            target=self.read_loop,
            daemon=True
        ).start()

        self.entry.focus_set()

    def read_loop(self):
        while True:
            try:
                data = self.proc.read(1024)

                if data:
                    self.output.after(
                        0,
                        lambda d=data: self.append(d)
                    )

            except Exception:
                break

    def append(self, text):
        self.output.config(state="normal")
        self.output.insert("end", text)
        self.output.see("end")
        self.output.config(state="disabled")

    def send_command(self, event=None):
        cmd = self.entry.get()

        self.proc.write(cmd + "\r\n")

        self.entry.delete(0, tk.END)

        return "break"
    
    def focus_set(self):
        self.entry.focus_set()