"""Small desktop interface; machine state files are managed automatically."""
from datetime import datetime
from pathlib import Path
import queue
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from folder_change_review import DEFAULT_WORKERS, VERSION, compare_files, create_snapshot
from runtime_safety import application_directory, inside, offline_runtime, open_application_folder, require_local
from state_store import StateHistory, path_module


class Application:
    def __init__(self, window, directory):
        self.window = window
        self.history = StateHistory(directory)
        self.messages = queue.Queue()
        self.busy = False
        self.items = []
        self.labels = []
        settings = self.history.settings()
        self.project = tk.StringVar(value=settings.get("project", ""))
        self.workers = tk.StringVar(value=str(settings.get("workers", DEFAULT_WORKERS)))
        if self.workers.get() not in ("16", "32"):
            self.workers.set(str(DEFAULT_WORKERS))
        self.before = tk.StringVar()
        self.after = tk.StringVar()
        self.before_root = tk.StringVar()
        self.after_root = tk.StringVar()
        self.status = tk.StringVar(value="Choose a project folder, then create a state.")
        self.result = tk.StringVar()
        window.title("Folder Change Review")
        window.geometry("900x620")
        window.minsize(760, 620)
        window.protocol("WM_DELETE_WINDOW", self.close)
        window.option_add("*Font", "{Segoe UI} 10")
        outer = ttk.Frame(window, padding=18)
        outer.pack(fill="both", expand=True)
        outer.columnconfigure(0, weight=1)
        ttk.Label(outer, text="Folder Change Review", font=("Segoe UI", 18, "bold")).grid(row=0, column=0, sticky="w")
        ttk.Label(outer, text="Create states manually. Compare two states to review project changes.").grid(row=1, column=0, sticky="w", pady=(4, 12))
        capture = ttk.LabelFrame(outer, text="Create a state", padding=12)
        capture.grid(row=2, column=0, sticky="ew")
        capture.columnconfigure(0, weight=1)
        ttk.Label(capture, text="Project folder (local folder, SMB share or mapped drive)").grid(row=0, column=0, columnspan=3, sticky="w")
        self.project_entry = ttk.Entry(capture, textvariable=self.project)
        self.project_entry.grid(row=1, column=0, sticky="ew", pady=(7, 8))
        self.browse_button = ttk.Button(capture, text="Browse...", command=self.browse)
        self.browse_button.grid(row=1, column=1, padx=(8, 0), pady=(7, 8))
        controls = ttk.Frame(capture)
        controls.grid(row=2, column=0, columnspan=2, sticky="ew")
        ttk.Label(controls, text="Workers").pack(side="left")
        self.worker_box = ttk.Combobox(controls, textvariable=self.workers, values=("16", "32"), state="readonly", width=5)
        self.worker_box.pack(side="left", padx=(8, 18))
        self.capture_button = ttk.Button(controls, text="Create state", command=self.capture, underline=7)
        self.capture_button.pack(side="left")
        ttk.Label(controls, text="State files are saved automatically.").pack(side="left", padx=16)
        compare = ttk.LabelFrame(outer, text="Compare states", padding=12)
        compare.grid(row=3, column=0, sticky="ew", pady=(12, 0))
        compare.columnconfigure(1, weight=1)
        ttk.Label(compare, text="Earlier state (A)").grid(row=0, column=0, sticky="w", padx=(0, 14))
        self.before_box = ttk.Combobox(compare, textvariable=self.before, state="readonly")
        self.before_box.grid(row=0, column=1, sticky="ew")
        ttk.Label(compare, textvariable=self.before_root, wraplength=650).grid(row=1, column=1, sticky="w", pady=(3, 6))
        ttk.Label(compare, text="Later state (B)").grid(row=2, column=0, sticky="w", padx=(0, 14))
        self.after_box = ttk.Combobox(compare, textvariable=self.after, state="readonly")
        self.after_box.grid(row=2, column=1, sticky="ew")
        ttk.Label(compare, textvariable=self.after_root, wraplength=650).grid(row=3, column=1, sticky="w", pady=(3, 6))
        self.compare_button = ttk.Button(compare, text="Compare states", command=self.compare, underline=0)
        self.compare_button.grid(row=4, column=1, sticky="w")
        self.before_box.bind("<<ComboboxSelected>>", self.selection_details)
        self.after_box.bind("<<ComboboxSelected>>", self.selection_details)
        self.progress = ttk.Progressbar(outer, mode="indeterminate")
        self.progress.grid(row=4, column=0, sticky="ew", pady=(12, 6))
        ttk.Label(outer, textvariable=self.status, wraplength=840).grid(row=5, column=0, sticky="w")
        ttk.Label(outer, textvariable=self.result, wraplength=840).grid(row=6, column=0, sticky="w", pady=(6, 0))
        footer = ttk.Frame(outer)
        footer.grid(row=7, column=0, sticky="ew", pady=(10, 0))
        self.open_button = ttk.Button(footer, text="Open report folder", command=lambda: open_application_folder(self.history.directory))
        self.open_button.pack(side="left")
        ttk.Label(footer, text=f"v{VERSION}  |  Local execution; SMB input allowed").pack(side="right")
        window.bind_all("<Alt-s>", lambda event: self.capture())
        window.bind_all("<Alt-c>", lambda event: self.compare())
        self.refresh()
        window.after(100, self.poll)

    def refresh(self):
        self.items, errors = self.history.list_states()
        self.labels = []
        for item in self.items:
            meta = item["metadata"]
            date = datetime.fromisoformat(meta["completed_utc"]).astimezone()
            folder = path_module(meta["root"]).basename(meta["root"].rstrip("\\/")) or meta["root"]
            self.labels.append(f"{date:%Y-%m-%d %H:%M:%S}.{date.microsecond // 1000:03d}  |  {folder}  |  {meta['file_count']:,} files")
        self.before_box["values"] = self.labels
        self.after_box["values"] = self.labels
        if self.labels:
            self.after_box.current(0)
            self.before_box.current(min(1, len(self.labels) - 1))
        self.selection_details()
        if errors:
            self.status.set(f"{len(errors)} state(s) could not be read. Valid states remain available.")
        self.enable()

    def selection_details(self, event=None):
        for box, variable in ((self.before_box, self.before_root), (self.after_box, self.after_root)):
            index = box.current()
            variable.set(self.items[index]["metadata"]["root"] if index >= 0 else "")

    def enable(self):
        state = "disabled" if self.busy else "normal"
        for control in (self.project_entry, self.browse_button, self.capture_button, self.open_button):
            control.configure(state=state)
        self.worker_box.configure(state="disabled" if self.busy else "readonly")
        for control in (self.before_box, self.after_box):
            control.configure(state="disabled" if self.busy else "readonly")
        self.compare_button.configure(state="normal" if not self.busy and len(self.items) >= 2 else "disabled")

    def browse(self):
        value = filedialog.askdirectory(parent=self.window, title="Choose the project folder", initialdir=self.project.get() or str(self.history.directory), mustexist=True)
        if value:
            self.project.set(value)

    def start(self, operation):
        if self.busy:
            return
        self.busy = True
        self.enable()
        self.result.set("")
        self.progress.start(12)
        def work():
            try:
                self.messages.put(("done", operation()))
            except Exception as error:
                self.messages.put(("error", str(error)))
        threading.Thread(target=work, daemon=False).start()

    def capture(self):
        if self.busy:
            return
        root = self.project.get().strip().strip('"')
        if not root:
            messagebox.showinfo("Project folder", "Choose the project folder first.", parent=self.window)
            return
        if inside(self.history.directory, root):
            messagebox.showerror("Local working folder", "Keep this application in a separate local folder outside the project.", parent=self.window)
            return
        workers = int(self.workers.get())
        self.status.set("Reading project files and creating a state...")
        def capture():
            self.history.save_settings({"project": root, "workers": workers})
            output = self.history.new_state_path()
            state = create_snapshot(root, output, workers, lambda text: self.messages.put(("progress", text)))
            return "state", f"State created: {len(state['files']):,} files.", None
        self.start(capture)

    def compare(self):
        if self.busy or len(self.items) < 2:
            return
        a, b = self.before_box.current(), self.after_box.current()
        if a < 0 or b < 0 or a == b:
            messagebox.showinfo("Choose states", "Choose two different states of the project.", parent=self.window)
            return
        before, after = self.items[a]["path"], self.items[b]["path"]
        output = self.history.new_report_path()
        self.status.set("Comparing states...")
        def compare():
            counts = compare_files(before, after, output, lambda text: self.messages.put(("progress", text)))
            return "report", "  |  ".join(f"{name}: {counts[name]:,}" for name in ("Added", "Deleted", "Changed", "Unchanged")), output
        self.start(compare)

    def poll(self):
        try:
            while True:
                kind, value = self.messages.get_nowait()
                if kind == "progress":
                    self.status.set(value)
                else:
                    self.busy = False
                    self.progress.stop()
                    self.refresh()
                    if kind == "error":
                        self.status.set("Operation failed. No incomplete state or report was saved.")
                        messagebox.showerror("Folder Change Review", value, parent=self.window)
                    else:
                        operation, message, output = value
                        self.status.set(message)
                        self.result.set("Report: " + str(output) if output else "Choose another capture time later, then compare the two states.")
        except queue.Empty:
            pass
        self.window.after(100, self.poll)

    def close(self):
        if self.busy:
            self.status.set("Please wait for the current operation to finish before closing.")
        else:
            self.window.destroy()


def launch():
    directory = application_directory()
    require_local(directory)
    with offline_runtime(directory):
        window = tk.Tk()
        Application(window, directory)
        window.mainloop()
