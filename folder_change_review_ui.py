"""Two independent desktop actions with automatically managed local history."""
from collections import Counter
from datetime import datetime
from pathlib import Path
import queue
import threading
import tkinter as tk
from tkinter import font as tkfont
from tkinter import filedialog, messagebox, ttk

from folder_change_review import DEFAULT_WORKERS, OUTPUT_FILE, VERSION, capture_error_message, compare_files, create_snapshot, report_error_message
from runtime_safety import application_directory, offline_runtime, open_application_folder, pasted_path
from state_store import StateHistory, path_module

BACKGROUND = '#F3F4F6'
CARD = '#FFFFFF'
TEXT = '#17212F'
MUTED = '#586574'
ACTION_WIDTH = 20


class Application:
    def __init__(self, window, directory):
        self.window = window
        self.history = StateHistory(directory)
        self.messages = queue.Queue()
        self.busy = False
        self.active_operation = None
        self.items = []
        self.labels = []
        settings = self.history.settings()
        self.project = tk.StringVar(value=settings.get('project', ''))
        self.workers = tk.StringVar(value=str(settings.get('workers', DEFAULT_WORKERS)))
        if self.workers.get() not in ('16', '32'):
            self.workers.set(str(DEFAULT_WORKERS))
        self.before = tk.StringVar()
        self.after = tk.StringVar()
        self.before_root = tk.StringVar()
        self.after_root = tk.StringVar()
        self.capture_status = tk.StringVar()
        self.compare_status = tk.StringVar()
        self.history_summary = tk.StringVar()
        self.report_name = tk.StringVar(value='No report created in this session.')
        self.output_folder = tk.StringVar(value=settings.get('report_directory', str(self.history.directory)))
        self.poll_id = None
        window.title('Folder Change Review')
        window.configure(background=BACKGROUND)
        window.protocol('WM_DELETE_WINDOW', self.close)
        style = ttk.Style(window)
        style.configure('.', font=('Segoe UI', 10))
        style.configure('App.TFrame', background=BACKGROUND)
        style.configure('App.TLabel', background=BACKGROUND, foreground=TEXT)
        style.configure('Card.TFrame', background=CARD)
        style.configure('Card.TLabel', background=CARD, foreground=TEXT, font=('Segoe UI', 10))
        self.label_width = 112
        style.configure('Muted.Card.TLabel', background=CARD, foreground=MUTED, font=('Segoe UI', 9))
        style.configure('Title.Card.TLabel', background=CARD, foreground=TEXT, font=('Segoe UI', 14, 'bold'))
        style.configure('Step.Card.TLabel', background='#E5EFFB', foreground='#175C9E', font=('Segoe UI', 11, 'bold'), padding=(9, 4))
        style.configure('Action.TButton', padding=(10, 6))
        outer = ttk.Frame(window, style='App.TFrame', padding=20)
        outer.pack(fill='both', expand=True)
        outer.columnconfigure(0, weight=1)
        outer.rowconfigure(2, weight=1)
        ttk.Label(outer, text='Folder Change Review', style='App.TLabel', font=('Segoe UI', 18, 'bold')).grid(row=0, column=0, columnspan=2, sticky='w')
        introduction = ttk.Label(outer, text='Save a state now, or compare states you already have.', style='App.TLabel')
        introduction.grid(row=1, column=0, columnspan=2, sticky='w', pady=(4, 16))
        outer.bind('<Configure>', lambda event: introduction.configure(wraplength=max(100,event.width-40)))

        # Only the cards scroll on short screens; the output folder stays visible.
        self.canvas = tk.Canvas(outer, background=BACKGROUND, highlightthickness=0, width=1)
        self.canvas.grid(row=2, column=0, sticky='nsew')
        self.scrollbar = ttk.Scrollbar(outer, orient='vertical', command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=self.scrollbar.set)
        cards = ttk.Frame(self.canvas, style='App.TFrame')
        cards.columnconfigure(0, weight=1)
        self.cards = cards
        self.canvas_item = self.canvas.create_window(0, 0, window=cards, anchor='nw')
        self.canvas.bind('<Configure>', self.resize_cards)
        cards.bind('<Configure>', self.update_scroll)
        window.bind('<MouseWheel>', self.scroll_cards)
        window.bind('<Button-4>', self.scroll_cards)
        window.bind('<Button-5>', self.scroll_cards)

        capture = self.card(cards, 0, '1', 'Create a state',
                            "Save the project's current state. Repeat whenever you want a new capture.")
        ttk.Label(capture, text='Project folder', style='Card.TLabel').grid(row=2, column=0, sticky='w', padx=(0, 14))
        self.project_entry = ttk.Entry(capture, textvariable=self.project)
        self.project_entry.grid(row=2, column=1, sticky='ew')
        self.browse_button = ttk.Button(capture, text='Browse…', width=ACTION_WIDTH, style='Action.TButton', command=self.browse)
        self.browse_button.grid(row=2, column=2, sticky='e', padx=(12, 0))
        ttk.Label(capture, text='Read workers', style='Card.TLabel').grid(row=3, column=0, sticky='w', pady=(8, 0))
        options = ttk.Frame(capture, style='Card.TFrame')
        options.grid(row=3, column=1, columnspan=2, sticky='w', pady=(8, 0))
        self.worker_box = ttk.Combobox(options, textvariable=self.workers, values=('16', '32'), state='readonly', width=5)
        self.worker_box.pack(side='left')
        ttk.Label(options, text='16 by default; try 32 for an SMB share.', style='Muted.Card.TLabel').pack(side='left', padx=(12, 0))
        self.capture_button, self.capture_progress = self.action_row(capture, 4, self.capture_status, 'Create state', self.capture)
        ttk.Label(capture, text='States are saved automatically.', style='Muted.Card.TLabel').grid(row=5, column=0, columnspan=2, sticky='w', pady=(2, 0))
        self.capture_issues = []
        self.issues_button = ttk.Button(capture, text='Read issues…', width=ACTION_WIDTH, command=self.show_capture_issues)
        self.issues_button.grid(row=5, column=2, sticky='e', pady=(2, 0))

        compare = self.card(cards, 1, '2', 'Compare saved states',
                            'Choose two captures. The project folder does not need to be online.', self.history_summary)
        ttk.Label(compare, text='Before (A)', style='Card.TLabel').grid(row=2, column=0, sticky='w', padx=(0, 14))
        self.before_box = ttk.Combobox(compare, textvariable=self.before, state='readonly')
        self.before_box.grid(row=2, column=1, columnspan=2, sticky='ew')
        self.before_path = self.path_entry(compare, self.before_root)
        self.before_path.grid(row=3, column=1, columnspan=2, sticky='ew', pady=(2, 8))
        ttk.Label(compare, text='After (B)', style='Card.TLabel').grid(row=4, column=0, sticky='w', padx=(0, 14))
        self.after_box = ttk.Combobox(compare, textvariable=self.after, state='readonly')
        self.after_box.grid(row=4, column=1, columnspan=2, sticky='ew')
        self.after_path = self.path_entry(compare, self.after_root)
        self.after_path.grid(row=5, column=1, columnspan=2, sticky='ew', pady=(2, 0))
        self.compare_button, self.compare_progress = self.action_row(compare, 6, self.compare_status, 'Create Excel report', self.compare)
        ttk.Label(compare, textvariable=self.report_name, style='Muted.Card.TLabel').grid(row=7, column=0, columnspan=3, sticky='w', pady=(2, 0))
        self.before_box.bind('<<ComboboxSelected>>', self.selection_details)
        self.after_box.bind('<<ComboboxSelected>>', self.selection_details)
        self.field_frames = (capture, compare)
        self.field_labels = [capture.grid_slaves(row=2,column=0)[0],
                             capture.grid_slaves(row=3,column=0)[0],
                             compare.grid_slaves(row=2,column=0)[0],
                             compare.grid_slaves(row=4,column=0)[0]]

        footer = ttk.Frame(outer, style='App.TFrame')
        footer.grid(row=3, column=0, columnspan=2, sticky='ew', pady=(16, 0))
        footer.columnconfigure(0, weight=1)
        ttk.Label(footer, text='Report: ' + OUTPUT_FILE, style='App.TLabel').grid(row=0, column=0, sticky='w')
        self.folder_path = self.path_entry(footer, self.output_folder, background=BACKGROUND)
        self.folder_path.grid(row=1, column=0, sticky='ew', padx=(0, 12))
        self.open_button = ttk.Button(footer, text='Open report folder', width=ACTION_WIDTH, style='Action.TButton', command=self.open_folder)
        self.report_folder_button = ttk.Button(footer, text='Choose report folder…', width=ACTION_WIDTH, style='Action.TButton', command=self.choose_report_folder)
        self.report_folder_button.grid(row=0, column=1, sticky='e', padx=(0, 16))
        self.open_button.grid(row=1, column=1, sticky='e', padx=(0, 16), pady=(4, 0))
        ttk.Label(footer, text=f'v{VERSION}   •   Local execution; SMB folders supported', style='App.TLabel', foreground=MUTED, font=('Segoe UI', 9)).grid(row=2, column=0, columnspan=2, sticky='w', pady=(10, 0))
        window.bind_all('<Alt-s>', lambda event: self.capture())
        window.bind_all('<Alt-c>', lambda event: self.compare())
        self.project.trace_add('write', self.project_changed)
        self.project_changed()
        self.refresh(select_latest=True)
        window.update_idletasks()
        self.align_fields()
        self.canvas.configure(height=cards.winfo_reqheight())
        window.update_idletasks()
        available = max(440, window.winfo_screenheight()-100)
        window.geometry(f'960x{min(window.winfo_reqheight(), available)}')
        window.minsize(820, min(600, available))
        self.poll_id = window.after(100, self.poll)

    @staticmethod
    def path_entry(parent, variable, background=CARD):
        return tk.Entry(parent, textvariable=variable, state='readonly', relief='flat',
                        borderwidth=0, highlightthickness=0, readonlybackground=background,
                        foreground=MUTED, font=('Segoe UI', 9), width=1)

    def card(self, parent, row, number, title, description, summary=None):
        border = tk.Frame(parent, background=CARD, highlightbackground='#D7DDE4', highlightcolor='#D7DDE4', highlightthickness=1)
        border.grid(row=row, column=0, sticky='ew', pady=(0, 14) if row == 0 else 0)
        content = ttk.Frame(border, style='Card.TFrame', padding=14)
        content.pack(fill='both', expand=True)
        content.columnconfigure(0, minsize=self.label_width)
        content.columnconfigure(1, weight=1)
        heading = ttk.Frame(content, style='Card.TFrame')
        heading.grid(row=0, column=0, columnspan=3, sticky='ew')
        heading.columnconfigure(1, weight=1)
        ttk.Label(heading, text=number, style='Step.Card.TLabel').grid(row=0, column=0, padx=(0, 10))
        ttk.Label(heading, text=title, style='Title.Card.TLabel').grid(row=0, column=1, sticky='w')
        if summary is not None:
            ttk.Label(heading, textvariable=summary, style='Muted.Card.TLabel').grid(row=0, column=2, sticky='e')
        explanation = ttk.Label(content, text=description, style='Muted.Card.TLabel')
        explanation.grid(row=1, column=0, columnspan=3, sticky='w', pady=(6, 12))
        content.bind('<Configure>', lambda event: explanation.configure(wraplength=max(100,event.width-28)))
        return content

    @staticmethod
    def action_row(parent, row, status, text, command):
        actions = ttk.Frame(parent, style='Card.TFrame')
        actions.grid(row=row, column=0, columnspan=3, sticky='ew', pady=(10, 0))
        actions.columnconfigure(0, weight=1)
        height = max(42, tkfont.Font(parent, font=('Segoe UI', 10)).metrics('linespace')*2+4)
        area = ttk.Frame(actions, style='Card.TFrame', height=height)
        area.grid(row=0, column=0, sticky='ew', padx=(0, 12))
        area.grid_propagate(False)
        area.columnconfigure(0, weight=1)
        area.rowconfigure(0, weight=1)
        label = ttk.Label(area, textvariable=status, style='Card.TLabel')
        label.grid(row=0, column=0, sticky='w')
        area.bind('<Configure>', lambda event: label.configure(wraplength=max(100, event.width)))
        progress = ttk.Progressbar(area, mode='indeterminate')
        progress.grid(row=1, column=0, sticky='ew', pady=(3, 0))
        progress.grid_remove()
        button = ttk.Button(actions, text=text, width=ACTION_WIDTH, style='Action.TButton', command=command)
        button.grid(row=0, column=1, sticky='e')
        return button, progress

    def resize_cards(self, event):
        self.canvas.itemconfigure(self.canvas_item, width=event.width)
        self.align_fields()
        self.update_scroll()

    def align_fields(self):
        if not hasattr(self, 'field_labels'):
            return
        width = max(112, *(label.winfo_reqwidth()+14 for label in self.field_labels))
        if width != self.label_width:
            self.label_width = width
            for frame in self.field_frames:
                frame.columnconfigure(0,minsize=width)

    def update_scroll(self, event=None):
        self.canvas.configure(scrollregion=self.canvas.bbox('all'))
        overflow = self.cards.winfo_reqheight() > self.canvas.winfo_height()+1
        if overflow:
            self.scrollbar.grid(row=2, column=1, sticky='ns', padx=(8, 0))
        else:
            self.scrollbar.grid_remove()
            self.canvas.yview_moveto(0)
        if hasattr(self, 'open_button'):
            self.open_button.grid_configure(padx=(0,16+(self.scrollbar.winfo_reqwidth()+8 if overflow else 0)))
            self.report_folder_button.grid_configure(padx=(0,16+(self.scrollbar.winfo_reqwidth()+8 if overflow else 0)))

    def scroll_cards(self, event):
        if isinstance(event.widget, (ttk.Combobox, tk.Entry, ttk.Entry)) or not self.scrollbar.winfo_ismapped():
            return
        units = (-1 if event.num == 4 else 1) if event.num in (4, 5) else -int(event.delta/120)
        self.canvas.yview_scroll(units, 'units')

    def project_changed(self, *unused):
        if not self.busy:
            self.capture_status.set('Ready to create a new state.' if self.project.get().strip() else 'Choose a project folder to begin.')
            self.enable()

    def refresh(self, select_latest=False):
        previous_status = self.compare_status.get()
        selected = []
        for box in (self.before_box, self.after_box):
            index = box.current()
            selected.append(self.items[index]['path'] if 0 <= index < len(self.items) else None)
        self.items, errors = self.history.list_states()
        self.labels = []
        duplicates = Counter()
        for item in self.items:
            meta = item['metadata']
            date = datetime.fromisoformat(meta['completed_utc']).astimezone()
            folder = path_module(meta['root']).basename(meta['root'].rstrip('\\/')) or meta['root']
            label = f"{date:%Y-%m-%d %H:%M:%S}.{date.microsecond // 1000:03d}  |  {folder}  |  {meta['file_count']:,} files"
            if meta.get('read_error_count', 0):
                label += f"  |  {meta['read_error_count']:,} read issues"
            duplicates[label] += 1
            self.labels.append(label if duplicates[label] == 1 else f'{label} ({duplicates[label]})')
        paths = [item['path'] for item in self.items]
        for box, previous, default in ((self.before_box, selected[0], min(1,len(paths)-1)), (self.after_box, selected[1], 0)):
            box['values'] = self.labels
            if paths:
                box.current(paths.index(previous) if not select_latest and previous in paths else default)
            else:
                box.set('')
        self.history_summary.set(f'{len(paths)} saved states' + (f' • {len(errors)} unavailable' if errors else ''))
        self.selection_details()
        current = [self.items[box.current()]['path'] if 0 <= box.current() < len(self.items) else None
                   for box in (self.before_box, self.after_box)]
        if not select_latest and selected == current and previous_status:
            self.compare_status.set(previous_status)

    def selection_details(self, event=None):
        for box, variable in ((self.before_box, self.before_root), (self.after_box, self.after_root)):
            index = box.current()
            variable.set(self.items[index]['metadata']['root'] if 0 <= index < len(self.items) else '')
        if not self.busy:
            a, b = self.before_box.current(), self.after_box.current()
            if len(self.items) == 0:
                text = 'No saved states yet. Create your first state above.'
            elif len(self.items) == 1:
                text = 'One state saved. Create another at a later time.'
            elif a < 0 or b < 0 or a == b:
                text = 'Choose two different states to compare.'
            elif self.items[a]['metadata']['completed_utc'] > self.items[b]['metadata']['completed_utc']:
                text = 'A is newer than B. Swap them for a forward comparison.'
            else:
                text = 'Ready. The report will show changes from A to B.'
            if a >= 0 and b >= 0 and a != b:
                count = sum(self.items[index]['metadata'].get('read_error_count', 0) for index in (a, b))
                if count:
                    text += f'\nIncomplete coverage: {count:,} read issues. Affected files will be Unknown.'
            self.compare_status.set(text)
        self.enable()

    def enable(self):
        state = 'disabled' if self.busy else 'normal'
        for control in (self.project_entry, self.browse_button, self.open_button, self.report_folder_button):
            control.configure(state=state)
        self.capture_button.configure(state='normal' if not self.busy and self.project.get().strip() else 'disabled')
        self.worker_box.configure(state='disabled' if self.busy else 'readonly')
        self.issues_button.configure(state='normal' if self.capture_issues and not self.busy else 'disabled')
        for control in (self.before_box, self.after_box):
            control.configure(state='readonly' if not self.busy and self.items else 'disabled')
        a, b = self.before_box.current(), self.after_box.current()
        valid = 0 <= a < len(self.items) and 0 <= b < len(self.items) and a != b
        self.compare_button.configure(state='normal' if not self.busy and valid else 'disabled')

    def browse(self):
        value = filedialog.askdirectory(parent=self.window, title='Choose the project folder', initialdir=self.project.get() or str(self.history.directory), mustexist=True)
        if value:
            self.project.set(value)

    def open_folder(self):
        try:
            open_application_folder(self.output_folder.get())
        except Exception as error:
            messagebox.showerror('Open report folder', str(error), parent=self.window)

    def choose_report_folder(self):
        if not self.busy:
            value = filedialog.askdirectory(parent=self.window, title='Choose the report folder (local or SMB)', initialdir=self.output_folder.get(), mustexist=True)
            if value:
                self.output_folder.set(value)

    def show_capture_issues(self):
        if not self.capture_issues or self.busy:
            return
        dialog = tk.Toplevel(self.window)
        dialog.title('Read issues — Folder Change Review')
        dialog.geometry('820x420')
        dialog.transient(self.window)
        dialog.columnconfigure(0, weight=1)
        dialog.rowconfigure(1, weight=1)
        ttk.Label(dialog, text='This state has incomplete coverage. Affected files will be Unknown, not deleted.', wraplength=780).grid(row=0, column=0, sticky='w', padx=12, pady=12)
        text = tk.Text(dialog, wrap='none', font=('Segoe UI', 10))
        text.grid(row=1, column=0, sticky='nsew', padx=(12, 0))
        scroll = ttk.Scrollbar(dialog, command=text.yview)
        scroll.grid(row=1, column=1, sticky='ns', padx=(0, 12))
        horizontal = ttk.Scrollbar(dialog, orient='horizontal', command=text.xview)
        horizontal.grid(row=2, column=0, sticky='ew', padx=12)
        text.configure(yscrollcommand=scroll.set, xscrollcommand=horizontal.set)
        for issue in self.capture_issues:
            text.insert('end', f"{issue['kind']}: {issue['path']}\n{issue['message']}\n\n")
        text.configure(state='disabled')
        ttk.Button(dialog, text='Close', command=dialog.destroy).grid(row=3, column=0, sticky='e', padx=12, pady=12)

    def start(self, kind, operation):
        if self.busy:
            return
        self.busy = True
        self.active_operation = kind
        self.enable()
        progress = self.capture_progress if kind == 'state' else self.compare_progress
        progress['value'] = 0
        progress.grid()
        progress.start(15)
        def work():
            try:
                self.messages.put(('done', operation()))
            except Exception as error:
                self.messages.put(('error', capture_error_message(error) if kind == 'state' else report_error_message(error)))
        try:
            threading.Thread(target=work, daemon=False).start()
        except Exception as error:
            self.messages.put(('error', str(error)))

    def capture(self):
        if self.busy:
            return
        root = pasted_path(self.project.get())
        if not root:
            return
        workers = int(self.workers.get())
        report_directory = self.output_folder.get()
        self.capture_status.set('Reading files and creating a state…')
        def capture():
            # Filesystem/SMB checks belong on the worker, not the UI thread.
            self.history.save_settings({'project': root, 'workers': workers, 'report_directory': report_directory})
            output = self.history.new_state_path()
            state = create_snapshot(root, output, workers, lambda text: self.messages.put(('progress', text)))
            issues = state.get('read_errors', [])
            message = f"State saved: {len(state['files']):,} files."
            if issues:
                message += f"\nIncomplete coverage: {len(issues):,} read issues. See Read issues."
            return 'state', message, issues
        self.start('state', capture)

    def compare(self):
        if self.busy:
            return
        a, b = self.before_box.current(), self.after_box.current()
        if a < 0 or b < 0 or a == b:
            return
        before, after = self.items[a]['path'], self.items[b]['path']
        issue_count = sum(self.items[index]['metadata'].get('read_error_count', 0) for index in (a, b))
        output = Path(self.output_folder.get()) / OUTPUT_FILE
        self.compare_status.set('Comparing saved states and writing Excel…')
        def compare():
            settings = self.history.settings()
            self.history.save_settings({**settings, 'report_directory': str(output.parent)})
            counts = compare_files(before, after, output, lambda text: self.messages.put(('progress', text)))
            message = f"Added: {counts['Added']:,}   Deleted: {counts['Deleted']:,}   Changed: {counts['Changed']:,}\nUnchanged: {counts['Unchanged']:,}   Unknown: {counts['Unknown']:,}"
            if issue_count:
                message += f"   Read issues: {issue_count:,}"
            return 'report', message, output
        self.start('report', compare)

    def poll(self):
        try:
            while True:
                kind, value = self.messages.get_nowait()
                status = self.capture_status if self.active_operation == 'state' else self.compare_status
                if kind == 'progress':
                    status.set(value)
                    continue
                operation = self.active_operation
                self.busy = False
                self.active_operation = None
                for progress in (self.capture_progress, self.compare_progress):
                    progress.stop()
                    progress['value'] = 0
                    progress.grid_remove()
                self.refresh(select_latest=kind == 'done' and value[0] == 'state')
                if kind == 'error':
                    status.set('State was not saved. See the error details.' if operation == 'state' else 'Report was not saved. Try again.')
                    messagebox.showerror('Folder Change Review', value, parent=self.window)
                else:
                    operation, message, output = value
                    status.set(message)
                    if operation == 'state':
                        self.capture_issues = output or []
                        self.enable()
                    elif output:
                        self.report_name.set('Last report: ' + output.name)
        except queue.Empty:
            pass
        self.poll_id = self.window.after(100, self.poll)

    def close(self):
        if self.busy:
            status = self.capture_status if self.active_operation == 'state' else self.compare_status
            status.set('Please let this operation finish before closing.')
        else:
            if self.poll_id is not None:
                self.window.after_cancel(self.poll_id)
            self.window.destroy()


def launch():
    directory = application_directory()
    with offline_runtime(directory):
        window = tk.Tk()
        Application(window, directory)
        window.mainloop()
