#!/usr/bin/env python3
"""
Fullscreen "Locked by Dad" overlay.

Launched by agent.py on /api/lock and terminated on /api/unlock. It covers the
screen with a lock message and keeps re-raising itself so it's hard to click or
Cmd-Tab away from. This is a userland friction lock, not a vault — a determined,
technical user can still escape it (force-quit, Mission Control). Pairs with the
agent's watchdog, which relaunches this if it's force-quit while still locked.

Pure Python 3 stdlib (tkinter). Set MCPAUSE_OVERLAY_TEST=1 for a small, non-
fullscreen, self-closing window (used for testing without hijacking the screen).
"""
import os
import sys
import tkinter as tk

MSG = sys.argv[1] if len(sys.argv) > 1 else "Locked by Dad"
TEST = os.environ.get("MCPAUSE_OVERLAY_TEST") == "1"

root = tk.Tk()
root.title("Locked")
root.configure(bg="#0b0b0d")

sw = root.winfo_screenwidth()
sh = root.winfo_screenheight()

if TEST:
    root.geometry("340x180+80+80")
    root.after(1200, root.destroy)
else:
    root.overrideredirect(True)                 # borderless
    root.geometry(f"{sw}x{sh}+0+0")             # cover the main display
    root.attributes("-topmost", True)
    try:
        root.config(cursor="none")
    except Exception:
        pass

frame = tk.Frame(root, bg="#0b0b0d")
frame.place(relx=0.5, rely=0.5, anchor="center")
tk.Label(frame, text="\U0001F512", font=("Helvetica", 96),
         bg="#0b0b0d", fg="#ff5b5b").pack()
tk.Label(frame, text=MSG, font=("Helvetica", 40, "bold"), bg="#0b0b0d",
         fg="#e9e9ee", wraplength=min(sw - 200, 1100), justify="center").pack(pady=24)
tk.Label(frame, text="Ask Dad to unlock.", font=("Helvetica", 22),
         bg="#0b0b0d", fg="#9a9aa6").pack()

# Best-effort: swallow the common escape shortcuts.
for seq in ("<Escape>", "<Command-q>", "<Command-w>", "<Command-h>",
            "<Command-m>", "<Command-Key-Tab>"):
    try:
        root.bind_all(seq, lambda e: "break")
    except Exception:
        pass


def _reassert():
    if TEST:
        return
    try:
        root.attributes("-topmost", True)
        root.lift()
        root.focus_force()
    except Exception:
        pass
    root.after(400, _reassert)


root.after(150, _reassert)
root.mainloop()
