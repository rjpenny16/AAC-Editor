import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox, filedialog
import time
import json
import requests
from typing import List, Dict, Optional
import threading
import os

import td_snap_pageset

class TDSnapAIAssistantPro:
    def __init__(self, root):
        self.root = root
        self.root.title("TD Snap Page Builder")
        self.root.geometry("900x880")
        self.root.minsize(820, 700)

        # Light, Apple-inspired palette: airy, high-contrast, one accent color.
        self.colors = {
            'bg': '#f5f5f7',            # window background (Apple light gray)
            'surface': '#ffffff',       # cards / panels
            'surface_alt': '#f5f5f7',   # subtle alternate fill
            'primary': '#0071e3',       # Apple blue (accent)
            'primary_dark': '#0077ed',  # hover / pressed blue
            'success': '#34c759',       # Apple green
            'danger': '#ff3b30',        # Apple red
            'text': '#1d1d1f',          # primary text (near black)
            'text_muted': '#86868b',    # secondary text (gray)
            'border': '#d2d2d7',        # hairline border
            'field_border': '#c7c7cc',  # input border
        }

        # Resolve clean, system-appropriate fonts (San Francisco on Apple devices).
        self.ui_font = self._resolve_font_family(
            ("SF Pro Text", "SF Pro Display", "Helvetica Neue", "Segoe UI",
             "Roboto", "Arial")
        )
        self.mono_font = self._resolve_font_family(
            ("SF Mono", "Menlo", "Consolas", "DejaVu Sans Mono", "Courier New")
        )

        # Configure window background
        self.root.configure(bg=self.colors['bg'])

        # Store the current operation status
        self.is_processing = False

        # Page set editing state (export -> edit -> import workflow)
        self.pageset_path = None          # the .spb/.sps the user exported
        self.pageset_conn = None          # open SQLite connection to a working copy
        self.pages = []                   # [(Id, name)] for the parent-page dropdown

        # Ollama configuration
        self.ollama_host = "http://localhost:11434"
        self.ollama_model = "llama3.2"  # Default model
        self.use_ollama = True  # Use Ollama by default

        # Whether the (secondary) activity log disclosure is expanded.
        self.log_visible = False

        # Setup styles before UI
        self.setup_modern_styles()
        self.setup_ui()

    def _resolve_font_family(self, preferred):
        """Return the first installed family from *preferred*, else a sane default.

        Lets the UI use the platform's native typeface (e.g. San Francisco on a
        Mac) without hard-coding a font that may be missing elsewhere.
        """
        try:
            from tkinter import font as tkfont
            available = set(tkfont.families())
        except Exception:
            return preferred[0]
        for family in preferred:
            if family in available:
                return family
        return preferred[-1]

    def setup_modern_styles(self):
        """Configure a clean, light ttk theme (Apple-inspired)."""
        style = ttk.Style()
        style.theme_use('clam')

        c = self.colors
        f = self.ui_font

        # Frames
        style.configure('Modern.TFrame', background=c['bg'])
        style.configure('Surface.TFrame', background=c['surface'], borderwidth=0)

        # Labels
        style.configure('Modern.TLabel', background=c['surface'],
                        foreground=c['text'], font=(f, 12))
        style.configure('OnBg.TLabel', background=c['bg'],
                        foreground=c['text'], font=(f, 12))
        style.configure('Title.TLabel', background=c['bg'],
                        foreground=c['text'], font=(f, 30, 'bold'))
        style.configure('Subtitle.TLabel', background=c['bg'],
                        foreground=c['text_muted'], font=(f, 13))
        style.configure('Heading.TLabel', background=c['surface'],
                        foreground=c['text'], font=(f, 15, 'bold'))
        style.configure('Muted.TLabel', background=c['surface'],
                        foreground=c['text_muted'], font=(f, 11))
        style.configure('Value.TLabel', background=c['surface'],
                        foreground=c['primary'], font=(f, 12, 'bold'))

        # Primary (filled blue) button — the one action that matters per screen.
        style.configure('Primary.TButton', background=c['primary'],
                        foreground='#ffffff', borderwidth=0, focuscolor='none',
                        font=(f, 12, 'bold'), padding=(22, 12))
        style.map('Primary.TButton',
                  background=[('disabled', '#aebfd6'),
                              ('active', c['primary_dark']),
                              ('pressed', c['primary_dark'])],
                  foreground=[('disabled', '#f0f0f0')],
                  relief=[('pressed', 'flat'), ('!pressed', 'flat')])

        # Secondary (tinted) button — subtle, gray fill, blue text.
        style.configure('Secondary.TButton', background='#e8e8ed',
                        foreground=c['primary'], borderwidth=0, focuscolor='none',
                        font=(f, 11), padding=(16, 10))
        style.map('Secondary.TButton',
                  background=[('active', '#dcdce1'), ('pressed', '#d2d2d7')],
                  relief=[('pressed', 'flat'), ('!pressed', 'flat')])

        # Success (green) button — connection test.
        style.configure('Success.TButton', background=c['success'],
                        foreground='#ffffff', borderwidth=0, focuscolor='none',
                        font=(f, 12, 'bold'), padding=(22, 12))
        style.map('Success.TButton',
                  background=[('active', '#2fb350'), ('pressed', '#28a745')],
                  relief=[('pressed', 'flat'), ('!pressed', 'flat')])

        # Warning / Stop (red) button.
        style.configure('Warning.TButton', background=c['danger'],
                        foreground='#ffffff', borderwidth=0, focuscolor='none',
                        font=(f, 12, 'bold'), padding=(22, 12))
        style.map('Warning.TButton',
                  background=[('disabled', '#f1b3af'),
                              ('active', '#e0352b'), ('pressed', '#cc2f26')],
                  foreground=[('disabled', '#f7f7f7')],
                  relief=[('pressed', 'flat'), ('!pressed', 'flat')])

        # Text entry — white field with a hairline border, blue on focus.
        style.configure('Modern.TEntry', fieldbackground='#ffffff',
                        foreground=c['text'], borderwidth=1,
                        insertcolor=c['primary'], relief='solid',
                        bordercolor=c['field_border'], padding=10)
        style.map('Modern.TEntry',
                  bordercolor=[('focus', c['primary'])],
                  lightcolor=[('focus', c['primary'])],
                  darkcolor=[('focus', c['primary'])])

        # Combobox — match the entry styling.
        style.configure('Modern.TCombobox', fieldbackground='#ffffff',
                        background='#ffffff', foreground=c['text'],
                        bordercolor=c['field_border'], borderwidth=1,
                        arrowcolor=c['text_muted'], relief='solid', padding=8)
        style.map('Modern.TCombobox',
                  fieldbackground=[('readonly', '#ffffff')],
                  bordercolor=[('focus', c['primary'])])

        # Notebook tabs — flat, segmented-control feel.
        style.configure('Modern.TNotebook', background=c['bg'],
                        borderwidth=0, tabmargins=(0, 0, 0, 0))
        style.configure('Modern.TNotebook.Tab', background=c['bg'],
                        foreground=c['text_muted'], padding=(26, 12),
                        borderwidth=0, font=(f, 12, 'bold'))
        style.map('Modern.TNotebook.Tab',
                  background=[('selected', c['surface'])],
                  foreground=[('selected', c['primary'])],
                  expand=[('selected', (0, 0, 0, 0))])


    def _card(self, parent, heading=None, subtitle=None):
        """Create a white, hairline-bordered card and return its content frame.

        Cards are the building block of the layout: a single idea per card, with
        generous padding and plenty of breathing room.
        """
        outer = tk.Frame(parent, bg=self.colors['surface'],
                         highlightbackground=self.colors['border'],
                         highlightcolor=self.colors['border'],
                         highlightthickness=1, bd=0)
        inner = tk.Frame(outer, bg=self.colors['surface'])
        inner.pack(fill=tk.BOTH, expand=True, padx=24, pady=18)
        inner.columnconfigure(0, weight=1)

        row = 0
        if heading:
            ttk.Label(inner, text=heading, style='Heading.TLabel').grid(
                row=row, column=0, sticky=tk.W)
            row += 1
        if subtitle:
            ttk.Label(inner, text=subtitle, style='Muted.TLabel',
                      wraplength=720, justify=tk.LEFT).grid(
                row=row, column=0, sticky=tk.W, pady=(4, 0))
            row += 1

        body = tk.Frame(inner, bg=self.colors['surface'])
        body.grid(row=row, column=0, sticky=(tk.W, tk.E, tk.N, tk.S),
                  pady=(14 if row else 0, 0))
        body.columnconfigure(0, weight=1)
        return outer, body

    def setup_ui(self):
        # Root layout
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)

        main_frame = ttk.Frame(self.root, padding=(40, 24, 40, 16),
                               style='Modern.TFrame')
        main_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        main_frame.columnconfigure(0, weight=1)
        main_frame.rowconfigure(1, weight=1)

        # Header — title + one-line description, lots of whitespace.
        header = ttk.Frame(main_frame, style='Modern.TFrame')
        header.grid(row=0, column=0, sticky=(tk.W, tk.E), pady=(0, 16))
        header.columnconfigure(0, weight=1)
        ttk.Label(header, text="Page Builder", style='Title.TLabel').grid(
            row=0, column=0, sticky=tk.W)
        ttk.Label(header,
                  text="Add new vocabulary pages to your TD Snap page set.",
                  style='Subtitle.TLabel').grid(row=1, column=0, sticky=tk.W,
                                                pady=(6, 0))

        # Numbered tabs convey the natural order of the workflow.
        notebook = ttk.Notebook(main_frame, style='Modern.TNotebook')
        notebook.grid(row=1, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))

        pageset_tab = ttk.Frame(notebook, padding=24, style='Surface.TFrame')
        notebook.add(pageset_tab, text="1  Open File")
        self.setup_pageset_tab(pageset_tab)

        control_tab = ttk.Frame(notebook, padding=24, style='Surface.TFrame')
        notebook.add(control_tab, text="2  Build a Page")
        self.setup_control_tab(control_tab)

        settings_tab = ttk.Frame(notebook, padding=24, style='Surface.TFrame')
        notebook.add(settings_tab, text="3  Settings")
        self.setup_settings_tab(settings_tab)

        # Footer: a friendly status line plus a discreet "Activity log" disclosure.
        self.setup_footer(main_frame)

        # Quiet, friendly startup messages live in the (hidden) activity log.
        self.log("Welcome to Page Builder.")
        self.log("Everything runs locally on your computer — nothing is uploaded.")
        self.log("Step 1: open the page set you exported from TD Snap.")
        self.log("Step 2: describe a category to add (e.g. “Add a drinks page”).")
        self.log("Step 3: re-import the new file into TD Snap.")

    def setup_footer(self, parent):
        """Build the status line and the collapsible activity log."""
        footer = ttk.Frame(parent, style='Modern.TFrame')
        footer.grid(row=2, column=0, sticky=(tk.W, tk.E), pady=(14, 0))
        footer.columnconfigure(0, weight=1)

        # Status row: a colored dot + a plain-language status message.
        status_row = tk.Frame(footer, bg=self.colors['bg'])
        status_row.grid(row=0, column=0, sticky=(tk.W, tk.E))
        status_row.columnconfigure(1, weight=1)

        self.status_dot = tk.Label(status_row, text="●",
                                   bg=self.colors['bg'],
                                   fg=self.colors['success'],
                                   font=(self.ui_font, 11))
        self.status_dot.grid(row=0, column=0, padx=(0, 8))

        self.status_var = tk.StringVar(value="Ready")
        tk.Label(status_row, textvariable=self.status_var,
                 bg=self.colors['bg'], fg=self.colors['text'],
                 anchor=tk.W, font=(self.ui_font, 12)).grid(
            row=0, column=1, sticky=tk.W)

        # Disclosure toggle — keeps the technical log out of the way by default.
        self.log_toggle = tk.Label(status_row, text="Activity log  ›",
                                   bg=self.colors['bg'],
                                   fg=self.colors['text_muted'], cursor="hand2",
                                   font=(self.ui_font, 11))
        self.log_toggle.grid(row=0, column=2, sticky=tk.E)
        self.log_toggle.bind("<Button-1>", lambda e: self.toggle_log())

        # The log itself, hidden until the user opens the disclosure.
        self.log_container = tk.Frame(footer, bg=self.colors['bg'])
        self.log_container.grid(row=1, column=0, sticky=(tk.W, tk.E, tk.N, tk.S),
                                pady=(10, 0))
        self.log_container.columnconfigure(0, weight=1)
        footer.rowconfigure(1, weight=0)

        self.log_text = scrolledtext.ScrolledText(
            self.log_container, height=8, wrap=tk.WORD,
            bg='#ffffff', fg=self.colors['text_muted'],
            insertbackground=self.colors['primary'],
            font=(self.mono_font, 10), borderwidth=1, relief='solid',
            highlightthickness=0, padx=12, pady=10)
        # Not gridded yet — toggle_log() shows it on demand.

    def toggle_log(self):
        """Show or hide the activity log disclosure."""
        self.log_visible = not self.log_visible
        if self.log_visible:
            self.log_text.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
            self.log_toggle.config(text="Activity log  ‹")
        else:
            self.log_text.grid_forget()
            self.log_toggle.config(text="Activity log  ›")

    def setup_control_tab(self, parent):
        """Build-a-page screen: one clear input, one clear action."""
        parent.columnconfigure(0, weight=1)

        # Main card — describe the category to add.
        card, body = self._card(
            parent,
            heading="What would you like to add?",
            subtitle="Describe a category in plain words. We’ll create a page of "
                     "buttons for it and link to it from your chosen page.")
        card.grid(row=0, column=0, sticky=(tk.W, tk.E), pady=(0, 16))

        self.command_entry = ttk.Entry(body, style='Modern.TEntry',
                                       font=(self.ui_font, 14))
        self.command_entry.grid(row=0, column=0, sticky=(tk.W, tk.E))
        self.command_entry.bind('<Return>', lambda e: self.process_command())

        actions = tk.Frame(body, bg=self.colors['surface'])
        actions.grid(row=1, column=0, sticky=tk.W, pady=(16, 0))

        self.process_btn = ttk.Button(actions, text="Create Page",
                                      command=self.process_command,
                                      style='Primary.TButton')
        self.process_btn.grid(row=0, column=0, sticky=tk.W)

        # Stop is hidden until a build is actually running.
        self.stop_btn = ttk.Button(actions, text="Stop",
                                   command=self.stop_processing,
                                   state='disabled', style='Warning.TButton')
        self.stop_btn.grid(row=0, column=1, sticky=tk.W, padx=(10, 0))
        self.stop_btn.grid_remove()

        # Examples card — tappable suggestions to get started fast.
        ex_card, ex_body = self._card(parent, heading="Try an example")
        ex_card.grid(row=1, column=0, sticky=(tk.W, tk.E))
        ex_body.columnconfigure(0, weight=1)
        ex_body.columnconfigure(1, weight=1)

        examples = [
            "Add a drinks page",
            "Add animals with 15 items",
            "Create a colors page",
            "Add favorite foods",
        ]
        for i, example in enumerate(examples):
            btn = ttk.Button(
                ex_body, text=example, style='Secondary.TButton',
                command=lambda e=example: (self.command_entry.delete(0, tk.END),
                                           self.command_entry.insert(0, e)))
            left = 0 if i % 2 == 0 else 6
            right = 6 if i % 2 == 0 else 0
            btn.grid(row=i // 2, column=i % 2, padx=(left, right),
                     pady=6, sticky=(tk.W, tk.E))

    def setup_pageset_tab(self, parent):
        """Open-file screen: load an export, then pick where the link goes."""
        parent.columnconfigure(0, weight=1)

        # Load card — the one big action on this screen.
        card, body = self._card(
            parent,
            heading="Open your page set",
            subtitle="In TD Snap, export your page set to a .spb or .sps file, "
                     "then open it here. Your original file is never changed.")
        card.grid(row=0, column=0, sticky=(tk.W, tk.E), pady=(0, 16))

        ttk.Button(body, text="Choose File…", command=self.load_pageset,
                   style='Primary.TButton').grid(row=0, column=0, sticky=tk.W)

        self.pageset_path_var = tk.StringVar(value="No file open yet")
        ttk.Label(body, textvariable=self.pageset_path_var,
                  style='Value.TLabel').grid(row=1, column=0, sticky=tk.W,
                                             pady=(14, 0))

        # Destination card — which existing page should hold the new button.
        dest_card, dest_body = self._card(
            parent,
            heading="Where should the new button appear?",
            subtitle="Pick the existing page that will get a button linking to "
                     "your new category.")
        dest_card.grid(row=1, column=0, sticky=(tk.W, tk.E))

        self.parent_page_var = tk.StringVar()
        self.parent_page_combo = ttk.Combobox(
            dest_body, textvariable=self.parent_page_var, state='readonly',
            style='Modern.TCombobox', font=(self.ui_font, 12))
        self.parent_page_combo.grid(row=0, column=0, sticky=(tk.W, tk.E))

    def load_pageset(self):
        """Prompt for an exported .spb/.sps file and load its pages."""
        path = filedialog.askopenfilename(
            title="Select exported TD Snap page set",
            filetypes=[("TD Snap page set", "*.spb *.sps"), ("All files", "*.*")],
        )
        if not path:
            return

        # Close any previously opened working copy.
        if self.pageset_conn is not None:
            self.pageset_conn.close()
            self.pageset_conn = None

        try:
            self.pageset_conn = td_snap_pageset.open_pageset(path)
            self.pages = td_snap_pageset.list_pages(self.pageset_conn)
        except td_snap_pageset.PagesetError as e:
            self.log(f"❌ Could not load page set: {e}")
            messagebox.showerror("Invalid Page Set", str(e))
            return
        except Exception as e:
            self.log(f"❌ Error loading page set: {e}")
            messagebox.showerror("Error", str(e))
            return

        self.pageset_path = path
        name = os.path.basename(path)
        self.pageset_path_var.set(f"✓  {name}  ·  {len(self.pages)} pages")
        self.parent_page_combo['values'] = [name for _, name in self.pages]
        if self.pages:
            self.parent_page_combo.current(0)
        self.log(f"✓ Loaded page set '{name}' with {len(self.pages)} pages")
        self.update_status(
            "File open — go to “Build a Page” to add a category", "ready")

    def selected_parent_page_id(self) -> Optional[int]:
        """Return the Page Id chosen in the parent-page dropdown, if any."""
        idx = self.parent_page_combo.current()
        if idx is None or idx < 0 or idx >= len(self.pages):
            return None
        return self.pages[idx][0]

    def setup_settings_tab(self, parent):
        """Settings: AI connection and how new pages are generated."""
        parent.columnconfigure(0, weight=1)

        def field_row(body, label, hint, widget, r):
            top = 0 if r == 0 else 12
            ttk.Label(body, text=label, style='Modern.TLabel').grid(
                row=r, column=0, sticky=tk.W, pady=(top, 0))
            widget.grid(row=r, column=1, sticky=tk.E, pady=(top, 0))
            if hint:
                ttk.Label(body, text=hint, style='Muted.TLabel',
                          wraplength=520, justify=tk.LEFT).grid(
                    row=r + 1, column=0, columnspan=2, sticky=tk.W, pady=(2, 0))

        # AI connection card.
        ai_card, ai_body = self._card(
            parent,
            heading="AI connection",
            subtitle="Page Builder uses Ollama running locally on your computer. "
                     "Nothing leaves your machine.")
        ai_card.grid(row=0, column=0, sticky=(tk.W, tk.E), pady=(0, 16))
        ai_body.columnconfigure(0, weight=1)

        self.ollama_host_var = tk.StringVar(value="http://localhost:11434")
        host_entry = ttk.Entry(ai_body, textvariable=self.ollama_host_var,
                               width=26, style='Modern.TEntry',
                               font=(self.ui_font, 12))
        field_row(ai_body, "Server", "Where Ollama is running (default is fine "
                  "for most people).", host_entry, 0)

        self.ollama_model_var = tk.StringVar(value="llama3.2")
        model_combo = ttk.Combobox(ai_body, textvariable=self.ollama_model_var,
                                   width=24, style='Modern.TCombobox',
                                   font=(self.ui_font, 12))
        model_combo['values'] = ('llama3.2', 'llama3.1', 'llama2', 'mistral',
                                 'phi3', 'qwen2.5')
        field_row(ai_body, "Model", "Which AI model to use (e.g. llama3.2).",
                  model_combo, 2)

        ttk.Button(ai_body, text="Test Connection",
                   command=self.test_ollama_connection,
                   style='Success.TButton').grid(row=4, column=0, columnspan=2,
                                                  sticky=tk.W, pady=(18, 0))

        # Page generation card.
        gen_card, gen_body = self._card(
            parent,
            heading="New page options",
            subtitle="Defaults for the pages Page Builder creates.")
        gen_card.grid(row=1, column=0, sticky=(tk.W, tk.E))
        gen_body.columnconfigure(0, weight=1)

        self.items_count_var = tk.StringVar(value="10")
        items_entry = ttk.Entry(gen_body, textvariable=self.items_count_var,
                                width=8, style='Modern.TEntry',
                                font=(self.ui_font, 12))
        field_row(gen_body, "Buttons per page",
                  "How many words to add when you don’t say a number.",
                  items_entry, 0)

        self.grid_cols_var = tk.StringVar(value="4")
        cols_entry = ttk.Entry(gen_body, textvariable=self.grid_cols_var,
                               width=8, style='Modern.TEntry',
                               font=(self.ui_font, 12))
        field_row(gen_body, "Columns", "How wide the new grid of buttons is.",
                  cols_entry, 2)

    def _on_main_thread(self, func, *args, **kwargs):
        """Run *func* on the Tk main thread, scheduling it if we're off-thread.

        Tkinter is not thread-safe: every widget call must happen on the thread
        that owns the event loop. The build runs in a background thread, so any
        UI update it triggers is marshaled back here via ``root.after``.
        """
        if threading.current_thread() is threading.main_thread():
            func(*args, **kwargs)
        else:
            self.root.after(0, lambda: func(*args, **kwargs))

    def log(self, message):
        """Add a message to the log with timestamp (thread-safe)."""
        if threading.current_thread() is not threading.main_thread():
            self._on_main_thread(self.log, message)
            return
        timestamp = time.strftime("%H:%M:%S")
        self.log_text.insert(tk.END, f"[{timestamp}] {message}\n")
        self.log_text.see(tk.END)

    def update_status(self, message, state="busy"):
        """Update the status line and its colored dot (thread-safe).

        *state* drives the dot color: ``busy`` (blue), ``ready``/``success``
        (green), or ``error`` (red).
        """
        if threading.current_thread() is not threading.main_thread():
            self._on_main_thread(self.update_status, message, state)
            return
        dot_colors = {
            'busy': self.colors['primary'],
            'ready': self.colors['success'],
            'success': self.colors['success'],
            'error': self.colors['danger'],
        }
        self.status_var.set(message)
        if hasattr(self, 'status_dot'):
            self.status_dot.config(fg=dot_colors.get(state, self.colors['text_muted']))
        
    def stop_processing(self):
        """Stop the current processing"""
        self.is_processing = False
        self.log("Stop requested by user")
        
    def process_command(self):
        """Process the user's command"""
        command = self.command_entry.get().strip()
        if not command:
            messagebox.showwarning("Empty Command", "Please enter a command.")
            return
            
        if self.pageset_conn is None:
            messagebox.showwarning(
                "Open a file first",
                "Open the page set you exported from TD Snap on the "
                "“1 · Open File” tab, then try again.")
            return

        # Disable the process button and reveal the stop button.
        self.process_btn.config(state='disabled')
        self.stop_btn.grid()
        self.stop_btn.config(state='normal')
        self.is_processing = True
        
        # Run in a separate thread to keep UI responsive
        thread = threading.Thread(target=self._execute_command, args=(command,))
        thread.daemon = True
        thread.start()
        
    def _execute_command(self, command):
        """Execute the command in a separate thread"""
        try:
            self.log(f"\n{'━'*60}")
            self.log(f"🚀 Processing command: {command}")
            self.update_status("Reading your request…", "busy")

            # Parse the command using AI
            parsed_command = self.parse_command_with_ai(command)

            if not parsed_command:
                self.log("❌ ERROR: Could not understand the command")
                self._on_main_thread(
                    messagebox.showwarning,
                    "Didn’t catch that",
                    "Sorry, I couldn’t understand that request. Try something "
                    "like “Add a drinks page”.")
                self.update_status("Couldn’t understand that request", "error")
                self.finalize_processing()
                return

            self.log(f"✓ Understood: {parsed_command['action']} - {parsed_command['category']}")

            # Generate items for the category
            if parsed_command['action'] == 'add_category':
                self.update_status(
                    f"Choosing words for “{parsed_command['category']}”…", "busy")

                try:
                    items_count = int(self.items_count_var.get())
                except (ValueError, TypeError):
                    self.log("⚠️ 'Buttons per page' is not a number; using 10.")
                    items_count = 10
                if 'count' in parsed_command and parsed_command['count']:
                    items_count = parsed_command['count']

                items = self.generate_category_items(
                    parsed_command['category'],
                    items_count
                )

                if not items:
                    self.log("❌ ERROR: Could not generate items")
                    self._on_main_thread(
                        messagebox.showwarning,
                        "No words generated",
                        "I couldn’t come up with words for that category. "
                        "Check the AI connection on the Settings tab and try again.")
                    self.update_status("Couldn’t generate any words", "error")
                    self.finalize_processing()
                    return

                self.log(f"✓ Generated {len(items)} items")
                self.log(f"📝 Items: {', '.join(items)}")

                # Edit the page set file directly
                self.update_status("Adding the new page…", "busy")
                self.edit_pageset(parsed_command['category'], items)

            self.log("✅ Command completed successfully!")
            self.update_status(
                "Done — re-import the new file into TD Snap", "success")

        except Exception as e:
            self.log(f"❌ ERROR: {str(e)}")
            self._on_main_thread(
                messagebox.showerror, "Something went wrong", f"{str(e)}")
            self.update_status("Something went wrong — see the activity log", "error")
        finally:
            self._on_main_thread(self.process_btn.config, state='normal')
            self._on_main_thread(self.stop_btn.config, state='disabled')
            self.is_processing = False
            
    def finalize_processing(self):
        """Re-enable the action buttons after processing.

        The status line keeps its last meaningful message (done / error) so the
        result stays visible; only the controls are reset here.
        """
        self._on_main_thread(self.process_btn.config, state='normal')
        self._on_main_thread(self.stop_btn.config, state='disabled')
        self._on_main_thread(self.stop_btn.grid_remove)
        self.is_processing = False
        
    def parse_command_with_ai(self, command: str) -> Dict:
        """Use AI to parse the user's natural language command"""
        try:
            # Define JSON schema for structured output
            schema = {
                "type": "object",
                "properties": {
                    "action": {"type": "string"},
                    "category": {"type": "string"},
                    "count": {"type": "number"}
                },
                "required": ["action", "category"]
            }

            prompt = f"""Parse this command for a TD Snap AAC app automation tool.
The user wants to add categories and items to TD Snap.

User command: "{command}"

Extract the action (should be "add_category"), the category name, and optionally the count of items.

Examples:
"Add restaurants category" -> action: "add_category", category: "restaurants", count: null
"Add colors with 20 items" -> action: "add_category", category: "colors", count: 20
"Create an animals category" -> action: "add_category", category: "animals", count: null

Respond with JSON only."""

            response = self.call_ollama_api(prompt, json_schema=schema, max_tokens=200)

            if not response:
                self.log("ERROR: No response from Ollama")
                return None

            # Parse and validate the JSON
            parsed = json.loads(response.strip())

            # Ensure count is None if not specified
            if 'count' not in parsed or parsed['count'] is None:
                parsed['count'] = None
            else:
                parsed['count'] = int(parsed['count'])

            self.log(f"Parsed command: action={parsed.get('action')}, " +
                    f"category={parsed.get('category')}, count={parsed.get('count')}")

            return parsed

        except json.JSONDecodeError as e:
            self.log(f"Error: Could not parse JSON from Ollama: {str(e)}")
            return None
        except Exception as e:
            self.log(f"Error parsing command: {str(e)}")
            return None
            
    def generate_category_items(self, category: str, count: int = 10) -> List[str]:
        """Use AI to generate common items for a category"""
        try:
            # Define JSON schema for array of strings
            schema = {
                "type": "object",
                "properties": {
                    "items": {
                        "type": "array",
                        "items": {"type": "string"}
                    }
                },
                "required": ["items"]
            }

            prompt = f"""Generate exactly {count} common, practical items for the category "{category}"
for an AAC (Augmentative and Alternative Communication) app.

Requirements:
- Items should be commonly known and used
- Keep items simple and clear (1-3 words each)
- For places, use well-known brand names or common place types
- For food, use popular dishes or restaurants
- Make items practical for everyday communication
- Use simple, everyday language

Provide exactly {count} items in a JSON object with an "items" array.

Example format:
{{"items": ["item1", "item2", "item3"]}}"""

            response = self.call_ollama_api(prompt, json_schema=schema, max_tokens=800)

            if not response:
                self.log("ERROR: No response from Ollama")
                return []

            # Parse the JSON response
            parsed = json.loads(response.strip())
            items = parsed.get('items', [])

            # Ensure we got a list of strings
            if not isinstance(items, list):
                self.log("ERROR: Response was not a list")
                return []

            # Filter to ensure all items are strings
            items = [str(item) for item in items if item]

            # Limit to requested count
            items = items[:count]

            self.log(f"Generated {len(items)} items for '{category}'")

            return items

        except json.JSONDecodeError as e:
            self.log(f"Error: Could not parse JSON from Ollama: {str(e)}")
            return []
        except Exception as e:
            self.log(f"Error generating items: {str(e)}")
            return []
            
    def test_ollama_connection(self):
        """Test connection to Ollama server"""
        try:
            host = self.ollama_host_var.get()
            self.log(f"\nTesting connection to Ollama at {host}...")

            # Try to get list of models
            response = requests.get(f"{host}/api/tags", timeout=5)

            if response.status_code == 200:
                data = response.json()
                models = data.get('models', [])
                if models:
                    model_names = [m.get('name', 'unknown') for m in models]
                    self.log(f"Connection successful!")
                    self.log(f"Available models: {', '.join(model_names)}")
                    messagebox.showinfo("Success",
                        f"Connected to Ollama!\n\nAvailable models:\n" + "\n".join(model_names))
                else:
                    self.log("Connection successful but no models found.")
                    messagebox.showwarning("Warning",
                        "Connected to Ollama but no models are installed.\n\n" +
                        "Install a model with: ollama pull llama3.2")
            else:
                self.log(f"Connection failed: {response.status_code}")
                messagebox.showerror("Error",
                    f"Failed to connect to Ollama.\n\nStatus: {response.status_code}")

        except requests.exceptions.ConnectionError:
            self.log("ERROR: Could not connect to Ollama. Is it running?")
            messagebox.showerror("Connection Error",
                "Could not connect to Ollama.\n\n" +
                "Make sure Ollama is running:\n" +
                "1. Install Ollama from https://ollama.com\n" +
                "2. Start Ollama service\n" +
                "3. Pull a model: ollama pull llama3.2")
        except Exception as e:
            self.log(f"ERROR: {str(e)}")
            messagebox.showerror("Error", f"An error occurred:\n{str(e)}")

    def validate_json_schema(self, data: Dict, schema: Dict) -> bool:
        """Simple JSON schema validation"""
        try:
            if schema.get('type') == 'object':
                required = schema.get('required', [])
                properties = schema.get('properties', {})

                # Check all required fields exist
                for field in required:
                    if field not in data:
                        self.log(f"Validation error: Missing required field '{field}'")
                        return False

                # Check field types
                for field, field_schema in properties.items():
                    if field in data:
                        value = data[field]
                        expected_type = field_schema.get('type')

                        if expected_type == 'string' and not isinstance(value, str):
                            self.log(f"Validation error: Field '{field}' should be string")
                            return False
                        elif expected_type == 'number' and not isinstance(value, (int, float)):
                            # Allow null for optional number fields
                            if value is not None:
                                self.log(f"Validation error: Field '{field}' should be number")
                                return False
                        elif expected_type == 'array' and not isinstance(value, list):
                            self.log(f"Validation error: Field '{field}' should be array")
                            return False

            return True

        except Exception as e:
            self.log(f"Validation error: {str(e)}")
            return False

    def call_ollama_api(self, prompt: str, json_schema: Optional[Dict] = None,
                       max_tokens: int = 1000) -> Optional[str]:
        """Call Ollama API with optional structured JSON output"""
        try:
            host = self.ollama_host_var.get()
            model = self.ollama_model_var.get()

            # Prepare the request payload
            payload = {
                "model": model,
                "messages": [{"role": "user", "content": prompt}],
                "stream": False,
                "options": {
                    "num_predict": max_tokens,
                    "temperature": 0.7
                }
            }

            # Add JSON schema if provided (structured output)
            if json_schema:
                payload["format"] = json_schema

            # Make the API call
            response = requests.post(
                f"{host}/api/chat",
                headers={"Content-Type": "application/json"},
                json=payload,
                timeout=60  # Ollama can be slower than cloud APIs
            )

            if response.status_code == 200:
                data = response.json()
                message_content = data.get('message', {}).get('content', '')

                # If we requested structured output, validate it
                if json_schema and message_content:
                    try:
                        parsed_json = json.loads(message_content)
                        if self.validate_json_schema(parsed_json, json_schema):
                            return message_content
                        else:
                            self.log("JSON validation failed, retrying without schema...")
                            return None
                    except json.JSONDecodeError:
                        self.log("Failed to parse JSON response")
                        return None

                return message_content
            else:
                self.log(f"Ollama API Error: {response.status_code} - {response.text}")
                return None

        except requests.exceptions.ConnectionError:
            self.log("ERROR: Cannot connect to Ollama. Make sure it's running.")
            self._on_main_thread(messagebox.showerror, "Connection Error",
                "Cannot connect to Ollama.\n\nPlease start Ollama and try again.")
            return None
        except Exception as e:
            self.log(f"Ollama API call failed: {str(e)}")
            return None

    def edit_pageset(self, category: str, items: List[str]):
        """Add a category page (with item buttons) to the loaded page set file.

        Writes the result to a new ``*.edited.<ext>`` file alongside the original
        export, which the user then re-imports into TD Snap.
        """
        if self.pageset_conn is None:
            raise RuntimeError("No page set loaded. Load one in the 'Page Set' tab.")

        try:
            cols = int(self.grid_cols_var.get())
        except ValueError:
            cols = 4

        parent_page_id = self.selected_parent_page_id()

        self.log("\n━━━ Editing Page Set ━━━")
        self.log(f"📁 Adding page '{category}' with {len(items)} buttons "
                 f"(grid {cols} columns wide)")

        new_page_id = td_snap_pageset.add_category_page(
            self.pageset_conn, category, items, parent_page_id, cols=cols
        )

        if parent_page_id is not None:
            parent_name = next((n for i, n in self.pages if i == parent_page_id),
                               str(parent_page_id))
            self.log(f"🔗 Linked from '{parent_name}' via a new navigation button")

        # Write the edited file next to the original export.
        base, ext = os.path.splitext(self.pageset_path)
        dest = f"{base}.edited{ext}"
        td_snap_pageset.save_as(self.pageset_conn, dest)

        # Refresh the page list so subsequent commands see the new page.
        self.pages = td_snap_pageset.list_pages(self.pageset_conn)
        self._on_main_thread(
            self.parent_page_combo.configure,
            values=[name for _, name in self.pages])

        self.log("\n━━━ Edit Complete ━━━")
        self.log(f"💾 Saved edited page set to: {dest}")
        self.log("📥 Re-import this file into TD Snap to see your new page.")

def main():
    root = tk.Tk()
    app = TDSnapAIAssistantPro(root)
    root.mainloop()

if __name__ == "__main__":
    main()
