import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox
import pyautogui
import time
import json
import requests
from typing import List, Dict, Optional
import threading
import os

class TDSnapAIAssistantPro:
    def __init__(self, root):
        self.root = root
        self.root.title("TD Snap AI Assistant Pro - Ollama Edition")
        self.root.geometry("1000x750")

        # Modern color scheme
        self.colors = {
            'bg': '#0f172a',           # Dark slate background
            'surface': '#1e293b',      # Lighter surface
            'surface_light': '#334155', # Even lighter surface
            'primary': '#3b82f6',      # Bright blue
            'primary_dark': '#2563eb', # Darker blue
            'secondary': '#8b5cf6',    # Purple accent
            'success': '#10b981',      # Green
            'warning': '#f59e0b',      # Amber
            'text': '#f1f5f9',         # Light text
            'text_muted': '#94a3b8',   # Muted text
            'border': '#475569',       # Border color
            'hover': '#60a5fa',        # Hover blue
        }

        # Configure window background
        self.root.configure(bg=self.colors['bg'])

        # Store the current operation status
        self.is_processing = False
        self.recording_coordinates = False
        self.coordinates = {}
        self.load_coordinates()

        # Ollama configuration
        self.ollama_host = "http://localhost:11434"
        self.ollama_model = "llama3.2"  # Default model
        self.use_ollama = True  # Use Ollama by default

        # Setup modern styles before UI
        self.setup_modern_styles()
        self.setup_ui()
        
    def load_coordinates(self):
        """Load saved coordinates from file"""
        if os.path.exists('td_snap_coordinates.json'):
            try:
                with open('td_snap_coordinates.json', 'r') as f:
                    self.coordinates = json.load(f)
            except:
                self.coordinates = {}
        else:
            self.coordinates = {}
            
    def save_coordinates(self):
        """Save coordinates to file"""
        with open('td_snap_coordinates.json', 'w') as f:
            json.dump(self.coordinates, f, indent=2)

    def setup_modern_styles(self):
        """Configure modern ttk styles"""
        style = ttk.Style()
        style.theme_use('clam')

        # Configure main frame
        style.configure('Modern.TFrame',
                       background=self.colors['bg'])

        # Configure surface frames
        style.configure('Surface.TFrame',
                       background=self.colors['surface'],
                       borderwidth=0)

        # Configure label frames
        style.configure('Modern.TLabelframe',
                       background=self.colors['surface'],
                       foreground=self.colors['text'],
                       borderwidth=2,
                       relief='flat',
                       bordercolor=self.colors['border'])
        style.configure('Modern.TLabelframe.Label',
                       background=self.colors['surface'],
                       foreground=self.colors['primary'],
                       font=('Segoe UI', 10, 'bold'))

        # Configure labels
        style.configure('Modern.TLabel',
                       background=self.colors['surface'],
                       foreground=self.colors['text'],
                       font=('Segoe UI', 10))
        style.configure('Title.TLabel',
                       background=self.colors['bg'],
                       foreground=self.colors['text'],
                       font=('Segoe UI', 24, 'bold'))
        style.configure('Muted.TLabel',
                       background=self.colors['surface'],
                       foreground=self.colors['text_muted'],
                       font=('Segoe UI', 9))
        style.configure('Coord.TLabel',
                       background=self.colors['surface'],
                       foreground=self.colors['secondary'],
                       font=('Segoe UI', 9, 'bold'))

        # Configure buttons - Primary
        style.configure('Primary.TButton',
                       background=self.colors['primary'],
                       foreground='white',
                       borderwidth=0,
                       focuscolor='none',
                       font=('Segoe UI', 10, 'bold'),
                       padding=(20, 12))
        style.map('Primary.TButton',
                 background=[('active', self.colors['hover']),
                           ('pressed', self.colors['primary_dark'])],
                 relief=[('pressed', 'flat'), ('!pressed', 'flat')])

        # Configure buttons - Secondary
        style.configure('Secondary.TButton',
                       background=self.colors['surface_light'],
                       foreground=self.colors['text'],
                       borderwidth=1,
                       focuscolor='none',
                       font=('Segoe UI', 9),
                       padding=(15, 10))
        style.map('Secondary.TButton',
                 background=[('active', self.colors['border']),
                           ('pressed', self.colors['surface'])],
                 bordercolor=[('active', self.colors['primary'])],
                 relief=[('pressed', 'flat'), ('!pressed', 'flat')])

        # Configure buttons - Success
        style.configure('Success.TButton',
                       background=self.colors['success'],
                       foreground='white',
                       borderwidth=0,
                       focuscolor='none',
                       font=('Segoe UI', 10, 'bold'),
                       padding=(20, 12))
        style.map('Success.TButton',
                 background=[('active', '#059669'), ('pressed', '#047857')],
                 relief=[('pressed', 'flat'), ('!pressed', 'flat')])

        # Configure buttons - Warning (Stop)
        style.configure('Warning.TButton',
                       background=self.colors['warning'],
                       foreground='white',
                       borderwidth=0,
                       focuscolor='none',
                       font=('Segoe UI', 10, 'bold'),
                       padding=(20, 12))
        style.map('Warning.TButton',
                 background=[('active', '#d97706'), ('pressed', '#b45309')],
                 relief=[('pressed', 'flat'), ('!pressed', 'flat')])

        # Configure entry fields
        style.configure('Modern.TEntry',
                       fieldbackground=self.colors['surface_light'],
                       foreground=self.colors['text'],
                       borderwidth=2,
                       insertcolor=self.colors['text'],
                       relief='flat',
                       padding=12)
        style.map('Modern.TEntry',
                 fieldbackground=[('focus', self.colors['surface'])],
                 bordercolor=[('focus', self.colors['primary'])])

        # Configure notebook (tabs)
        style.configure('Modern.TNotebook',
                       background=self.colors['bg'],
                       borderwidth=0)
        style.configure('Modern.TNotebook.Tab',
                       background=self.colors['surface'],
                       foreground=self.colors['text_muted'],
                       padding=(20, 12),
                       borderwidth=0,
                       font=('Segoe UI', 10, 'bold'))
        style.map('Modern.TNotebook.Tab',
                 background=[('selected', self.colors['surface_light'])],
                 foreground=[('selected', self.colors['primary'])],
                 expand=[('selected', (2, 2, 2, 0))])


    def setup_ui(self):
        # Main frame with modern style
        main_frame = ttk.Frame(self.root, padding="20", style='Modern.TFrame')
        main_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))

        # Configure grid weights
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)
        main_frame.columnconfigure(0, weight=1)
        main_frame.rowconfigure(2, weight=1)

        # Title with gradient effect (using styled label)
        title_label = ttk.Label(main_frame, text="TD Snap AI Assistant Pro",
                               style='Title.TLabel')
        title_label.grid(row=0, column=0, pady=(0, 20))

        # Notebook for tabs with modern style
        notebook = ttk.Notebook(main_frame, style='Modern.TNotebook')
        notebook.grid(row=1, column=0, sticky=(tk.W, tk.E, tk.N, tk.S), pady=(0, 15))

        # Tab 1: Main Control
        control_tab = ttk.Frame(notebook, padding="20", style='Surface.TFrame')
        notebook.add(control_tab, text="  Command  ")
        self.setup_control_tab(control_tab)

        # Tab 2: Coordinate Setup
        coord_tab = ttk.Frame(notebook, padding="20", style='Surface.TFrame')
        notebook.add(coord_tab, text="  Setup Coordinates  ")
        self.setup_coordinate_tab(coord_tab)

        # Tab 3: Settings
        settings_tab = ttk.Frame(notebook, padding="20", style='Surface.TFrame')
        notebook.add(settings_tab, text="  Settings  ")
        self.setup_settings_tab(settings_tab)

        # Output/Log section with modern styling
        log_frame = ttk.LabelFrame(main_frame, text="Activity Log", padding="15",
                                  style='Modern.TLabelframe')
        log_frame.grid(row=2, column=0, sticky=(tk.W, tk.E, tk.N, tk.S), pady=(0, 10))
        log_frame.columnconfigure(0, weight=1)
        log_frame.rowconfigure(0, weight=1)

        # Modern log text area
        self.log_text = scrolledtext.ScrolledText(
            log_frame,
            height=12,
            width=80,
            wrap=tk.WORD,
            bg=self.colors['surface_light'],
            fg=self.colors['text'],
            insertbackground=self.colors['primary'],
            font=('Consolas', 9),
            borderwidth=0,
            relief='flat',
            padx=10,
            pady=10
        )
        self.log_text.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))

        # Status bar with modern styling
        self.status_var = tk.StringVar(value="Ready")
        status_bar = tk.Label(
            main_frame,
            textvariable=self.status_var,
            bg=self.colors['surface'],
            fg=self.colors['text_muted'],
            anchor=tk.W,
            font=('Segoe UI', 9),
            padx=15,
            pady=8
        )
        status_bar.grid(row=3, column=0, sticky=(tk.W, tk.E))

        self.log("✓ TD Snap AI Assistant Pro - Ollama Edition initialized.")
        self.log("🔒 This version uses local Ollama LLM for privacy and offline operation.")
        self.log("💡 Example commands: 'Add restaurants category', 'Add colors', etc.")
        self.log("\n⚠️  SETUP STEPS:")
        if not self.coordinates:
            self.log("1. Go to 'Setup Coordinates' tab to configure TD Snap button locations")
        self.log("2. Go to 'Settings' tab and test Ollama connection")
        self.log("3. Make sure Ollama is running with a model (e.g., llama3.2)")
        self.log("\n📚 For help installing Ollama, visit: https://ollama.com")
        
    def setup_control_tab(self, parent):
        """Setup the main control tab"""
        parent.columnconfigure(0, weight=1)

        # Input section with modern styling
        input_frame = ttk.LabelFrame(parent, text="Command Input", padding="20",
                                    style='Modern.TLabelframe')
        input_frame.grid(row=0, column=0, sticky=(tk.W, tk.E), pady=(0, 15))
        input_frame.columnconfigure(0, weight=1)

        ttk.Label(input_frame, text="Enter your request:",
                 style='Modern.TLabel').grid(row=0, column=0, sticky=tk.W, pady=(0, 8))

        self.command_entry = ttk.Entry(input_frame, width=60, style='Modern.TEntry',
                                      font=('Segoe UI', 11))
        self.command_entry.grid(row=1, column=0, sticky=(tk.W, tk.E), pady=(0, 15))
        self.command_entry.bind('<Return>', lambda e: self.process_command())

        button_frame = ttk.Frame(input_frame, style='Surface.TFrame')
        button_frame.grid(row=2, column=0, pady=5)

        self.process_btn = ttk.Button(button_frame, text="▶ Process Command",
                                     command=self.process_command,
                                     style='Primary.TButton')
        self.process_btn.grid(row=0, column=0, padx=8)

        self.stop_btn = ttk.Button(button_frame, text="■ Stop",
                                   command=self.stop_processing,
                                   state='disabled',
                                   style='Warning.TButton')
        self.stop_btn.grid(row=0, column=1, padx=8)

        # Quick examples with modern styling
        examples_frame = ttk.LabelFrame(parent, text="Quick Examples", padding="20",
                                       style='Modern.TLabelframe')
        examples_frame.grid(row=1, column=0, sticky=(tk.W, tk.E), pady=(0, 15))
        examples_frame.columnconfigure(0, weight=1)
        examples_frame.columnconfigure(1, weight=1)

        examples = [
            "Add restaurants category",
            "Add animals category with 15 items",
            "Create a colors category",
            "Add food category"
        ]

        for i, example in enumerate(examples):
            btn = ttk.Button(examples_frame, text=example,
                           command=lambda e=example: self.command_entry.delete(0, tk.END) or self.command_entry.insert(0, e),
                           style='Secondary.TButton')
            btn.grid(row=i//2, column=i%2, padx=8, pady=8, sticky=(tk.W, tk.E))
            
    def setup_coordinate_tab(self, parent):
        """Setup the coordinate recording tab"""
        parent.columnconfigure(0, weight=1)

        # Info section with modern styling
        info_frame = ttk.LabelFrame(parent, text="Instructions", padding="20",
                                   style='Modern.TLabelframe')
        info_frame.grid(row=0, column=0, sticky=(tk.W, tk.E), pady=(0, 15))

        info_text = """To automate TD Snap, the assistant needs to know where to click.
Press the buttons below and then click on the corresponding location in TD Snap.

Steps:
1. Open TD Snap and enter edit mode
2. Click a 'Record' button below (e.g., for 'Add Category Button')
3. You have 3 seconds to move your mouse over the target button in TD Snap
4. The program will record that position
5. Repeat for all required positions"""

        info_label = ttk.Label(info_frame, text=info_text, justify=tk.LEFT,
                              style='Muted.TLabel')
        info_label.grid(row=0, column=0, sticky=tk.W)

        # Coordinate buttons with modern styling
        coords_frame = ttk.LabelFrame(parent, text="Record Coordinates", padding="20",
                                     style='Modern.TLabelframe')
        coords_frame.grid(row=1, column=0, sticky=(tk.W, tk.E), pady=(0, 15))
        coords_frame.columnconfigure(1, weight=1)

        coord_points = [
            ("add_category", "Add Category Button"),
            ("add_button", "Add New Button/Word"),
            ("button_label", "Button Label Field"),
            ("category_name", "Category Name Field"),
            ("save_button", "Save Button"),
        ]

        self.coord_labels = {}
        for idx, (key, label) in enumerate(coord_points):
            # Label
            ttk.Label(coords_frame, text=f"{label}:",
                     style='Modern.TLabel').grid(row=idx, column=0, sticky=tk.W,
                                                padx=(0, 15), pady=8)

            # Coordinate display
            coord_text = self.coordinates.get(key, "Not set")
            self.coord_labels[key] = ttk.Label(coords_frame, text=str(coord_text),
                                              style='Coord.TLabel')
            self.coord_labels[key].grid(row=idx, column=1, sticky=tk.W, padx=10, pady=8)

            # Record button
            ttk.Button(coords_frame, text="● Record",
                      command=lambda k=key: self.record_coordinate(k),
                      style='Secondary.TButton').grid(row=idx, column=2, padx=10, pady=8)

        # Clear all button
        ttk.Button(coords_frame, text="Clear All Coordinates",
                  command=self.clear_coordinates,
                  style='Warning.TButton').grid(row=len(coord_points), column=0,
                                               columnspan=3, pady=(15, 0))
        
    def setup_settings_tab(self, parent):
        """Setup the settings tab"""
        parent.columnconfigure(0, weight=1)

        # Ollama Settings Frame with modern styling
        ollama_frame = ttk.LabelFrame(parent, text="🤖 Ollama AI Settings", padding="20",
                                     style='Modern.TLabelframe')
        ollama_frame.grid(row=0, column=0, sticky=(tk.W, tk.E), pady=(0, 15))
        ollama_frame.columnconfigure(1, weight=1)

        ttk.Label(ollama_frame, text="Ollama Host:",
                 style='Modern.TLabel').grid(row=0, column=0, sticky=tk.W,
                                            padx=(0, 15), pady=12)
        self.ollama_host_var = tk.StringVar(value="http://localhost:11434")
        ttk.Entry(ollama_frame, textvariable=self.ollama_host_var, width=30,
                 style='Modern.TEntry').grid(row=0, column=1, sticky=(tk.W, tk.E), pady=12)

        ttk.Label(ollama_frame, text="Ollama Model:",
                 style='Modern.TLabel').grid(row=1, column=0, sticky=tk.W,
                                            padx=(0, 15), pady=12)
        self.ollama_model_var = tk.StringVar(value="llama3.2")
        model_combo = ttk.Combobox(ollama_frame, textvariable=self.ollama_model_var, width=27)
        model_combo['values'] = ('llama3.2', 'llama3.1', 'llama2', 'mistral', 'phi3', 'qwen2.5')
        model_combo.grid(row=1, column=1, sticky=(tk.W, tk.E), pady=12, padx=(0, 0))

        # Test connection button
        ttk.Button(ollama_frame, text="🔌 Test Ollama Connection",
                  command=self.test_ollama_connection,
                  style='Success.TButton').grid(row=2, column=0, columnspan=2, pady=(5, 0))

        # Automation Settings Frame with modern styling
        settings_frame = ttk.LabelFrame(parent, text="⚙️  Automation Settings", padding="20",
                                       style='Modern.TLabelframe')
        settings_frame.grid(row=1, column=0, sticky=(tk.W, tk.E), pady=(0, 15))
        settings_frame.columnconfigure(1, weight=1)

        # Delay setting
        ttk.Label(settings_frame, text="Delay between actions (seconds):",
                 style='Modern.TLabel').grid(row=0, column=0, sticky=tk.W,
                                            padx=(0, 15), pady=12)
        self.delay_var = tk.StringVar(value="1.0")
        ttk.Entry(settings_frame, textvariable=self.delay_var, width=15,
                 style='Modern.TEntry').grid(row=0, column=1, sticky=tk.W, pady=12)

        # Items count setting
        ttk.Label(settings_frame, text="Default items per category:",
                 style='Modern.TLabel').grid(row=1, column=0, sticky=tk.W,
                                            padx=(0, 15), pady=12)
        self.items_count_var = tk.StringVar(value="10")
        ttk.Entry(settings_frame, textvariable=self.items_count_var, width=15,
                 style='Modern.TEntry').grid(row=1, column=1, sticky=tk.W, pady=12)

        # Countdown setting
        ttk.Label(settings_frame, text="Countdown before start (seconds):",
                 style='Modern.TLabel').grid(row=2, column=0, sticky=tk.W,
                                            padx=(0, 15), pady=12)
        self.countdown_var = tk.StringVar(value="5")
        ttk.Entry(settings_frame, textvariable=self.countdown_var, width=15,
                 style='Modern.TEntry').grid(row=2, column=1, sticky=tk.W, pady=12)

        # Typing speed setting
        ttk.Label(settings_frame, text="Typing speed (chars/sec):",
                 style='Modern.TLabel').grid(row=3, column=0, sticky=tk.W,
                                            padx=(0, 15), pady=12)
        self.typing_speed_var = tk.StringVar(value="0.05")
        ttk.Entry(settings_frame, textvariable=self.typing_speed_var, width=15,
                 style='Modern.TEntry').grid(row=3, column=1, sticky=tk.W, pady=12)
        
    def record_coordinate(self, key):
        """Record a coordinate position"""
        self.log(f"\n🎯 Recording coordinate for: {key}")
        self.log("Move your mouse to the target position in TD Snap...")

        def capture():
            for i in range(3, 0, -1):
                self.log(f"⏱️  Recording in {i}...")
                time.sleep(1)

            pos = pyautogui.position()
            self.coordinates[key] = {"x": pos.x, "y": pos.y}
            self.save_coordinates()

            # Update label with coordinate info (using config instead of style)
            self.coord_labels[key].config(text=f"x={pos.x}, y={pos.y}")
            self.log(f"✓ Recorded {key} at position ({pos.x}, {pos.y})")

        thread = threading.Thread(target=capture)
        thread.daemon = True
        thread.start()

    def clear_coordinates(self):
        """Clear all saved coordinates"""
        if messagebox.askyesno("Clear Coordinates", "Are you sure you want to clear all coordinates?"):
            self.coordinates = {}
            self.save_coordinates()
            for label in self.coord_labels.values():
                label.config(text="Not set")
            self.log("✓ All coordinates cleared")
        
    def log(self, message):
        """Add a message to the log with timestamp"""
        timestamp = time.strftime("%H:%M:%S")
        self.log_text.insert(tk.END, f"[{timestamp}] {message}\n")
        self.log_text.see(tk.END)
        self.log_text.update()
        
    def update_status(self, message):
        """Update the status bar"""
        self.status_var.set(message)
        self.root.update()
        
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
            
        if not self.coordinates:
            messagebox.showwarning("Setup Required", 
                                 "Please configure coordinates in the 'Setup Coordinates' tab first.")
            return
        
        # Disable the process button and enable stop button
        self.process_btn.config(state='disabled')
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
            self.update_status("Analyzing command with AI...")

            # Parse the command using AI
            parsed_command = self.parse_command_with_ai(command)

            if not parsed_command:
                self.log("❌ ERROR: Could not understand the command")
                self.finalize_processing()
                return

            self.log(f"✓ Understood: {parsed_command['action']} - {parsed_command['category']}")

            # Generate items for the category
            if parsed_command['action'] == 'add_category':
                self.update_status("Generating items with AI...")

                items_count = int(self.items_count_var.get())
                if 'count' in parsed_command and parsed_command['count']:
                    items_count = parsed_command['count']

                items = self.generate_category_items(
                    parsed_command['category'],
                    items_count
                )

                if not items:
                    self.log("❌ ERROR: Could not generate items")
                    self.finalize_processing()
                    return

                self.log(f"✓ Generated {len(items)} items")
                self.log(f"📝 Items: {', '.join(items)}")

                # Execute the automation
                self.update_status("Automating TD Snap...")
                self.automate_td_snap(parsed_command['category'], items)

            self.log("✅ Command completed successfully!")

        except Exception as e:
            self.log(f"❌ ERROR: {str(e)}")
            messagebox.showerror("Error", f"An error occurred: {str(e)}")
        finally:
            self.finalize_processing()
            
    def finalize_processing(self):
        """Re-enable UI after processing"""
        self.process_btn.config(state='normal')
        self.stop_btn.config(state='disabled')
        self.is_processing = False
        self.update_status("Ready")
        
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
            messagebox.showerror("Connection Error",
                "Cannot connect to Ollama.\n\nPlease start Ollama and try again.")
            return None
        except Exception as e:
            self.log(f"Ollama API call failed: {str(e)}")
            return None

    def automate_td_snap(self, category: str, items: List[str]):
        """Automate TD Snap to add a category and items"""
        try:
            delay = float(self.delay_var.get())
            countdown = int(self.countdown_var.get())
            typing_speed = float(self.typing_speed_var.get())

            self.log("\n━━━ Starting TD Snap Automation ━━━")
            self.log("⚠️  IMPORTANT: Make sure TD Snap is open and visible!")
            self.log(f"⏰ Starting in {countdown} seconds... Position TD Snap window now.")

            # Countdown
            for i in range(countdown, 0, -1):
                if not self.is_processing:
                    self.log("⏹️  Automation stopped by user")
                    return
                self.log(f"⏱️  {i}...")
                time.sleep(1)

            self.log("▶️  Starting automation...")

            # Step 1: Create category if we have the coordinate
            if 'add_category' in self.coordinates:
                self.log(f"📁 Step 1: Creating category '{category}'")
                coord = self.coordinates['add_category']
                pyautogui.click(coord['x'], coord['y'])
                time.sleep(delay)

                # Type category name if we have that field
                if 'category_name' in self.coordinates:
                    self.log(f"  ➜ Entering category name...")
                    coord = self.coordinates['category_name']
                    pyautogui.click(coord['x'], coord['y'])
                    time.sleep(delay * 0.5)
                    pyautogui.write(category, interval=typing_speed)
                    time.sleep(delay)

                    # Save if we have save button
                    if 'save_button' in self.coordinates:
                        coord = self.coordinates['save_button']
                        pyautogui.click(coord['x'], coord['y'])
                        time.sleep(delay)

            # Step 2: Add items
            self.log(f"\n📝 Step 2: Adding {len(items)} items to category")
            for idx, item in enumerate(items, 1):
                if not self.is_processing:
                    self.log("⏹️  Automation stopped by user")
                    return

                self.log(f"  ➜ [{idx}/{len(items)}] Adding '{item}'...")

                # Click add button
                if 'add_button' in self.coordinates:
                    coord = self.coordinates['add_button']
                    pyautogui.click(coord['x'], coord['y'])
                    time.sleep(delay)

                    # Type the item name
                    if 'button_label' in self.coordinates:
                        coord = self.coordinates['button_label']
                        pyautogui.click(coord['x'], coord['y'])
                        time.sleep(delay * 0.5)
                        pyautogui.write(item, interval=typing_speed)
                        time.sleep(delay * 0.5)

                        # Save the item
                        if 'save_button' in self.coordinates:
                            coord = self.coordinates['save_button']
                            pyautogui.click(coord['x'], coord['y'])
                            time.sleep(delay)

            self.log("\n━━━ Automation Complete ━━━")
            self.log(f"✅ Successfully processed category '{category}' with {len(items)} items!")

        except Exception as e:
            self.log(f"❌ Automation error: {str(e)}")
            raise

def main():
    root = tk.Tk()
    app = TDSnapAIAssistantPro(root)
    root.mainloop()

if __name__ == "__main__":
    main()
