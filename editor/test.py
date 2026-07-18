import tkinter as tk

root = tk.Tk()
root.geometry("300x100")

menu = tk.Menu(root, tearoff=0)
menu.add_command(label="Hello", command=lambda: print("clicked!"))

def show_menu(event):
    try:
        menu.tk_popup(event.x_root, event.y_root)
    finally:
        menu.grab_release()

btn = tk.Button(root, text="File", relief="flat")
btn.bind("<Button-1>", show_menu)
btn.pack(side="left")

root.mainloop()