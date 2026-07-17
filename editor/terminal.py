import tkinter as tk


class Terminal(tk.Frame):
    def __init__(self, parent):
        super().__init__(parent)

        self.configure(bg="#1e1e1e")

        self.label = tk.Label(
            self,
            text="Terminal",
            bg="#333333",
            fg="white",
            anchor="w"
        )
        self.label.pack(fill="x")

        # Native terminal will go here later
        self.host = tk.Frame(
            self,
            bg="black",
            height=250
        )

        self.host.pack(fill="both", expand=True)