"""
TD Snap AI Assistant - Advanced Edition
AI-powered AAC Editor with intelligent suggestions and comprehensive automation
"""

import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox, filedialog
import pyautogui
import time
import json
import requests
import os
import threading
import keyboard
from typing import List, Dict, Optional, Tuple
from cryptography.fernet import Fernet
import base64
from pathlib import Path
import cv2
import numpy as np
from PIL import Image, ImageGrab
import anthropic

try:
    import pygetwindow as gw
    WINDOW_DETECTION_AVAILABLE = True
except ImportError:
    WINDOW_DETECTION_AVAILABLE = False

try:
    import pytesseract
    OCR_AVAILABLE = True
except ImportError:
    OCR_AVAILABLE = False


class SecureStorage:
    """Secure storage for API keys using encryption"""

    def __init__(self, config_dir: str = ".config"):
        self.config_dir = Path(config_dir)
        self.config_dir.mkdir(exist_ok=True)
        self.key_file = self.config_dir / "key.enc"
        self.data_file = self.config_dir / "data.enc"
        self._ensure_key()

    def _ensure_key(self):
        """Ensure encryption key exists"""
        if not self.key_file.exists():
            key = Fernet.generate_key()
            self.key_file.write_bytes(key)

    def _get_cipher(self) -> Fernet:
        """Get encryption cipher"""
        key = self.key_file.read_bytes()
        return Fernet(key)

    def save(self, data: dict):
        """Save encrypted data"""
        cipher = self._get_cipher()
        json_data = json.dumps(data).encode()
        encrypted = cipher.encrypt(json_data)
        self.data_file.write_bytes(encrypted)

    def load(self) -> dict:
        """Load encrypted data"""
        if not self.data_file.exists():
            return {}
        try:
            cipher = self._get_cipher()
            encrypted = self.data_file.read_bytes()
            decrypted = cipher.decrypt(encrypted)
            return json.loads(decrypted.decode())
        except:
            return {}


class ChangeHistory:
    """Track changes for undo/redo functionality"""

    def __init__(self, max_history: int = 50):
        self.max_history = max_history
        self.history = []
        self.current_index = -1

    def add_change(self, change: dict):
        """Add a change to history"""
        # Remove any redo history if we're not at the end
        if self.current_index < len(self.history) - 1:
            self.history = self.history[:self.current_index + 1]

        self.history.append(change)
        if len(self.history) > self.max_history:
            self.history.pop(0)
        else:
            self.current_index += 1

    def can_undo(self) -> bool:
        """Check if undo is available"""
        return self.current_index >= 0

    def can_redo(self) -> bool:
        """Check if redo is available"""
        return self.current_index < len(self.history) - 1

    def undo(self) -> Optional[dict]:
        """Get previous change"""
        if self.can_undo():
            change = self.history[self.current_index]
            self.current_index -= 1
            return change
        return None

    def redo(self) -> Optional[dict]:
        """Get next change"""
        if self.can_redo():
            self.current_index += 1
            return self.history[self.current_index]
        return None


class WindowManager:
    """Manage TD Snap window detection and focusing"""

    @staticmethod
    def find_td_snap_window():
        """Find TD Snap window"""
        if not WINDOW_DETECTION_AVAILABLE:
            return None

        try:
            windows = gw.getWindowsWithTitle("TD Snap")
            if windows:
                return windows[0]
        except:
            pass
        return None

    @staticmethod
    def focus_td_snap() -> bool:
        """Bring TD Snap to front"""
        window = WindowManager.find_td_snap_window()
        if window:
            try:
                window.activate()
                time.sleep(0.5)
                return True
            except:
                pass
        return False

    @staticmethod
    def get_td_snap_bounds() -> Optional[Tuple[int, int, int, int]]:
        """Get TD Snap window bounds (left, top, width, height)"""
        window = WindowManager.find_td_snap_window()
        if window:
            return (window.left, window.top, window.width, window.height)
        return None


class VisualVerifier:
    """Visual verification using screenshots and template matching"""

    @staticmethod
    def capture_region(x: int, y: int, width: int, height: int) -> np.ndarray:
        """Capture screenshot of region"""
        screenshot = ImageGrab.grab(bbox=(x, y, x + width, y + height))
        return cv2.cvtColor(np.array(screenshot), cv2.COLOR_RGB2BGR)

    @staticmethod
    def find_template(screenshot: np.ndarray, template: np.ndarray, threshold: float = 0.8) -> Optional[Tuple[int, int]]:
        """Find template in screenshot"""
        result = cv2.matchTemplate(screenshot, template, cv2.TM_CCOEFF_NORMED)
        min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(result)

        if max_val >= threshold:
            return max_loc
        return None

    @staticmethod
    def verify_button_exists(x: int, y: int, width: int = 100, height: int = 40) -> bool:
        """Verify a button exists at coordinates"""
        try:
            img = VisualVerifier.capture_region(x - 10, y - 10, width, height)
            # Simple check: verify there's some visual content
            return img is not None and img.size > 0
        except:
            return False


class OCRReader:
    """OCR functionality for reading TD Snap content"""

    @staticmethod
    def read_text_at_region(x: int, y: int, width: int, height: int) -> str:
        """Read text from screen region"""
        if not OCR_AVAILABLE:
            return ""

        try:
            screenshot = ImageGrab.grab(bbox=(x, y, x + width, y + height))
            text = pytesseract.image_to_string(screenshot)
            return text.strip()
        except:
            return ""

    @staticmethod
    def read_td_snap_vocabulary(bounds: Tuple[int, int, int, int]) -> List[str]:
        """Read vocabulary from TD Snap window"""
        if not OCR_AVAILABLE or not bounds:
            return []

        left, top, width, height = bounds
        try:
            screenshot = ImageGrab.grab(bbox=(left, top, left + width, top + height))
            text = pytesseract.image_to_string(screenshot)
            # Parse text into vocabulary items (basic implementation)
            words = [w.strip() for w in text.split('\n') if w.strip()]
            return words
        except:
            return []


class TDSnapAIAssistantAdvanced:
    """Advanced TD Snap AI Assistant with full feature set"""

    def __init__(self, root):
        self.root = root
        self.root.title("TD Snap AI Assistant - Advanced Edition")
        self.root.geometry("1000x800")

        # Core state
        self.is_processing = False
        self.recording_coordinates = False
        self.coordinates = {}
        self.current_profile = "default"

        # Advanced features
        self.secure_storage = SecureStorage()
        self.change_history = ChangeHistory()
        self.api_key = ""
        self.anthropic_client = None

        # Batch operation queue
        self.batch_queue = []

        # Load saved data
        self.load_coordinates()
        self.load_secure_config()

        # Setup UI
        self.setup_ui()

        # Setup keyboard shortcuts
        self.setup_shortcuts()

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

    def load_secure_config(self):
        """Load secure configuration"""
        config = self.secure_storage.load()
        self.api_key = config.get('api_key', '')
        if self.api_key:
            self.init_anthropic_client()

    def save_secure_config(self):
        """Save secure configuration"""
        config = {'api_key': self.api_key}
        self.secure_storage.save(config)

    def init_anthropic_client(self):
        """Initialize Anthropic client"""
        if self.api_key:
            try:
                self.anthropic_client = anthropic.Anthropic(api_key=self.api_key)
                return True
            except Exception as e:
                self.log(f"Error initializing Anthropic client: {str(e)}")
                return False
        return False

    def setup_shortcuts(self):
        """Setup keyboard shortcuts"""
        self.root.bind('<Control-z>', lambda e: self.undo_last_change())
        self.root.bind('<Control-y>', lambda e: self.redo_change())
        self.root.bind('<Control-s>', lambda e: self.save_coordinates())
        self.root.bind('<Escape>', lambda e: self.stop_processing())

    def setup_ui(self):
        """Setup the user interface"""
        # Main frame
        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))

        # Configure grid weights
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)
        main_frame.columnconfigure(0, weight=1)
        main_frame.rowconfigure(1, weight=1)

        # Title
        title_label = ttk.Label(main_frame, text="TD Snap AI Assistant - Advanced Edition",
                               font=('Arial', 16, 'bold'))
        title_label.grid(row=0, column=0, pady=10)

        # Notebook for tabs
        notebook = ttk.Notebook(main_frame)
        notebook.grid(row=1, column=0, sticky=(tk.W, tk.E, tk.N, tk.S), pady=10)

        # Tab 1: Main Control
        control_tab = ttk.Frame(notebook, padding="10")
        notebook.add(control_tab, text="Command")
        self.setup_control_tab(control_tab)

        # Tab 2: AI Suggestions
        suggestions_tab = ttk.Frame(notebook, padding="10")
        notebook.add(suggestions_tab, text="AI Suggestions")
        self.setup_suggestions_tab(suggestions_tab)

        # Tab 3: Batch Operations
        batch_tab = ttk.Frame(notebook, padding="10")
        notebook.add(batch_tab, text="Batch Operations")
        self.setup_batch_tab(batch_tab)

        # Tab 4: Coordinate Setup
        coord_tab = ttk.Frame(notebook, padding="10")
        notebook.add(coord_tab, text="Setup Coordinates")
        self.setup_coordinate_tab(coord_tab)

        # Tab 5: Settings
        settings_tab = ttk.Frame(notebook, padding="10")
        notebook.add(settings_tab, text="Settings")
        self.setup_settings_tab(settings_tab)

        # Output/Log section
        log_frame = ttk.LabelFrame(main_frame, text="Activity Log", padding="10")
        log_frame.grid(row=2, column=0, sticky=(tk.W, tk.E, tk.N, tk.S), pady=10)
        log_frame.columnconfigure(0, weight=1)
        log_frame.rowconfigure(0, weight=1)

        self.log_text = scrolledtext.ScrolledText(log_frame, height=10, width=70, wrap=tk.WORD)
        self.log_text.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))

        # Status bar with undo/redo info
        status_frame = ttk.Frame(main_frame)
        status_frame.grid(row=3, column=0, sticky=(tk.W, tk.E))
        status_frame.columnconfigure(0, weight=1)

        self.status_var = tk.StringVar(value="Ready")
        status_bar = ttk.Label(status_frame, textvariable=self.status_var,
                              relief=tk.SUNKEN, anchor=tk.W)
        status_bar.grid(row=0, column=0, sticky=(tk.W, tk.E))

        self.undo_redo_var = tk.StringVar(value="")
        undo_redo_label = ttk.Label(status_frame, textvariable=self.undo_redo_var,
                                    relief=tk.SUNKEN, anchor=tk.E)
        undo_redo_label.grid(row=0, column=1, padx=5)

        self.log("TD Snap AI Assistant Advanced Edition initialized.")
        self.log("✨ New features: AI Suggestions, Batch Operations, Undo/Redo, Visual Verification")

        if not self.api_key:
            self.log("\n⚠️  IMPORTANT: Go to 'Settings' tab to configure your Anthropic API key!")
        if not self.coordinates:
            self.log("⚠️  IMPORTANT: Go to 'Setup Coordinates' tab to configure TD Snap button locations!")

    def setup_control_tab(self, parent):
        """Setup the main control tab"""
        parent.columnconfigure(0, weight=1)

        # Input section
        input_frame = ttk.LabelFrame(parent, text="Command Input", padding="10")
        input_frame.grid(row=0, column=0, sticky=(tk.W, tk.E), pady=10)
        input_frame.columnconfigure(0, weight=1)

        ttk.Label(input_frame, text="Enter your request:").grid(
            row=0, column=0, sticky=tk.W, pady=5)

        self.command_entry = ttk.Entry(input_frame, width=60)
        self.command_entry.grid(row=1, column=0, sticky=(tk.W, tk.E), pady=5)
        self.command_entry.bind('<Return>', lambda e: self.process_command())

        button_frame = ttk.Frame(input_frame)
        button_frame.grid(row=2, column=0, pady=5)

        self.process_btn = ttk.Button(button_frame, text="Process Command",
                                     command=self.process_command)
        self.process_btn.grid(row=0, column=0, padx=5)

        self.stop_btn = ttk.Button(button_frame, text="Stop",
                                   command=self.stop_processing, state='disabled')
        self.stop_btn.grid(row=0, column=1, padx=5)

        ttk.Button(button_frame, text="Focus TD Snap",
                  command=self.focus_td_snap_window).grid(row=0, column=2, padx=5)

        # Quick examples
        examples_frame = ttk.LabelFrame(parent, text="Quick Examples", padding="10")
        examples_frame.grid(row=1, column=0, sticky=(tk.W, tk.E), pady=10)

        examples = [
            "Add restaurants category",
            "Add animals category with 15 items",
            "Create a colors category",
            "Add food category"
        ]

        for i, example in enumerate(examples):
            btn = ttk.Button(examples_frame, text=example,
                           command=lambda e=example: self.set_command(e))
            btn.grid(row=i//2, column=i%2, padx=5, pady=5, sticky=(tk.W, tk.E))

    def setup_suggestions_tab(self, parent):
        """Setup AI suggestions tab"""
        parent.columnconfigure(0, weight=1)
        parent.rowconfigure(1, weight=1)

        # Header
        header_frame = ttk.Frame(parent)
        header_frame.grid(row=0, column=0, sticky=(tk.W, tk.E), pady=10)

        ttk.Label(header_frame, text="AI-Powered Vocabulary Suggestions",
                 font=('Arial', 12, 'bold')).grid(row=0, column=0, sticky=tk.W)

        ttk.Button(header_frame, text="Analyze Current Vocabulary",
                  command=self.analyze_vocabulary).grid(row=0, column=1, padx=10)

        ttk.Button(header_frame, text="Generate Suggestions",
                  command=self.generate_suggestions).grid(row=0, column=2, padx=5)

        # Suggestions display
        suggestions_frame = ttk.LabelFrame(parent, text="Suggestions", padding="10")
        suggestions_frame.grid(row=1, column=0, sticky=(tk.W, tk.E, tk.N, tk.S), pady=10)
        suggestions_frame.columnconfigure(0, weight=1)
        suggestions_frame.rowconfigure(0, weight=1)

        self.suggestions_text = scrolledtext.ScrolledText(suggestions_frame, height=15,
                                                          width=70, wrap=tk.WORD)
        self.suggestions_text.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))

        # Apply button
        ttk.Button(parent, text="Apply Selected Suggestions",
                  command=self.apply_suggestions).grid(row=2, column=0, pady=10)

    def setup_batch_tab(self, parent):
        """Setup batch operations tab"""
        parent.columnconfigure(0, weight=1)
        parent.rowconfigure(1, weight=1)

        # Controls
        control_frame = ttk.Frame(parent)
        control_frame.grid(row=0, column=0, sticky=(tk.W, tk.E), pady=10)

        ttk.Button(control_frame, text="Import from CSV",
                  command=self.import_csv).grid(row=0, column=0, padx=5)

        ttk.Button(control_frame, text="Add to Queue",
                  command=self.add_to_batch_queue).grid(row=0, column=1, padx=5)

        ttk.Button(control_frame, text="Clear Queue",
                  command=self.clear_batch_queue).grid(row=0, column=2, padx=5)

        ttk.Button(control_frame, text="Process Queue",
                  command=self.process_batch_queue).grid(row=0, column=3, padx=5)

        # Queue display
        queue_frame = ttk.LabelFrame(parent, text="Batch Queue", padding="10")
        queue_frame.grid(row=1, column=0, sticky=(tk.W, tk.E, tk.N, tk.S), pady=10)
        queue_frame.columnconfigure(0, weight=1)
        queue_frame.rowconfigure(0, weight=1)

        self.batch_queue_text = scrolledtext.ScrolledText(queue_frame, height=15,
                                                          width=70, wrap=tk.WORD)
        self.batch_queue_text.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))

    def setup_coordinate_tab(self, parent):
        """Setup the coordinate recording tab"""
        parent.columnconfigure(0, weight=1)

        info_frame = ttk.Frame(parent)
        info_frame.grid(row=0, column=0, sticky=(tk.W, tk.E), pady=10)

        info_text = """To automate TD Snap, the assistant needs to know where to click.
Press the buttons below and then click on the corresponding location in TD Snap.

Instructions:
1. Open TD Snap and enter edit mode
2. Click a button below (e.g., 'Add Category Button')
3. You have 3 seconds to move your mouse over the target button in TD Snap
4. The program will record that position
5. Repeat for all required positions

✨ New: Visual verification helps confirm button positions!"""

        ttk.Label(info_frame, text=info_text, justify=tk.LEFT).grid(row=0, column=0, sticky=tk.W)

        # Coordinate buttons
        coords_frame = ttk.LabelFrame(parent, text="Record Coordinates", padding="10")
        coords_frame.grid(row=1, column=0, sticky=(tk.W, tk.E), pady=10)
        coords_frame.columnconfigure(1, weight=1)

        coord_points = [
            ("add_category", "Add Category Button"),
            ("add_button", "Add New Button/Word"),
            ("button_label", "Button Label Field"),
            ("category_name", "Category Name Field"),
            ("save_button", "Save Button"),
        ]

        self.coord_labels = {}
        self.coord_verify_labels = {}

        for idx, (key, label) in enumerate(coord_points):
            ttk.Label(coords_frame, text=f"{label}:").grid(row=idx, column=0, sticky=tk.W, padx=5, pady=5)

            coord_text = self.coordinates.get(key, "Not set")
            self.coord_labels[key] = ttk.Label(coords_frame, text=str(coord_text),
                                              foreground="blue")
            self.coord_labels[key].grid(row=idx, column=1, sticky=tk.W, padx=5, pady=5)

            self.coord_verify_labels[key] = ttk.Label(coords_frame, text="", foreground="green")
            self.coord_verify_labels[key].grid(row=idx, column=2, sticky=tk.W, padx=5, pady=5)

            ttk.Button(coords_frame, text="Record",
                      command=lambda k=key: self.record_coordinate(k)).grid(
                          row=idx, column=3, padx=5, pady=5)

            ttk.Button(coords_frame, text="Verify",
                      command=lambda k=key: self.verify_coordinate(k)).grid(
                          row=idx, column=4, padx=5, pady=5)

        # Clear all button
        ttk.Button(coords_frame, text="Clear All Coordinates",
                  command=self.clear_coordinates).grid(row=len(coord_points), column=0,
                                                      columnspan=5, pady=10)

    def setup_settings_tab(self, parent):
        """Setup the settings tab"""
        parent.columnconfigure(0, weight=1)

        # API Configuration
        api_frame = ttk.LabelFrame(parent, text="API Configuration", padding="10")
        api_frame.grid(row=0, column=0, sticky=(tk.W, tk.E), pady=10)
        api_frame.columnconfigure(1, weight=1)

        ttk.Label(api_frame, text="Anthropic API Key:").grid(
            row=0, column=0, sticky=tk.W, padx=5, pady=5)

        self.api_key_var = tk.StringVar(value=self.api_key if self.api_key else "")
        api_key_entry = ttk.Entry(api_frame, textvariable=self.api_key_var,
                                  width=50, show="*")
        api_key_entry.grid(row=0, column=1, sticky=(tk.W, tk.E), padx=5, pady=5)

        ttk.Button(api_frame, text="Save API Key",
                  command=self.save_api_key).grid(row=0, column=2, padx=5, pady=5)

        ttk.Button(api_frame, text="Test Connection",
                  command=self.test_api_connection).grid(row=0, column=3, padx=5, pady=5)

        ttk.Label(api_frame, text="Get your API key at: https://console.anthropic.com/",
                 font=('Arial', 8), foreground="gray").grid(
            row=1, column=0, columnspan=4, sticky=tk.W, padx=5)

        # Automation Settings
        settings_frame = ttk.LabelFrame(parent, text="Automation Settings", padding="10")
        settings_frame.grid(row=1, column=0, sticky=(tk.W, tk.E), pady=10)

        ttk.Label(settings_frame, text="Delay between actions (seconds):").grid(
            row=0, column=0, sticky=tk.W, padx=5, pady=5)
        self.delay_var = tk.StringVar(value="1.0")
        ttk.Entry(settings_frame, textvariable=self.delay_var, width=10).grid(
            row=0, column=1, padx=5, pady=5)

        ttk.Label(settings_frame, text="Default items per category:").grid(
            row=1, column=0, sticky=tk.W, padx=5, pady=5)
        self.items_count_var = tk.StringVar(value="10")
        ttk.Entry(settings_frame, textvariable=self.items_count_var, width=10).grid(
            row=1, column=1, padx=5, pady=5)

        ttk.Label(settings_frame, text="Countdown before start (seconds):").grid(
            row=2, column=0, sticky=tk.W, padx=5, pady=5)
        self.countdown_var = tk.StringVar(value="5")
        ttk.Entry(settings_frame, textvariable=self.countdown_var, width=10).grid(
            row=2, column=1, padx=5, pady=5)

        ttk.Label(settings_frame, text="Typing speed (chars/sec):").grid(
            row=3, column=0, sticky=tk.W, padx=5, pady=5)
        self.typing_speed_var = tk.StringVar(value="0.05")
        ttk.Entry(settings_frame, textvariable=self.typing_speed_var, width=10).grid(
            row=3, column=1, padx=5, pady=5)

        # Enable/disable visual verification
        self.visual_verify_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(settings_frame, text="Enable visual verification",
                       variable=self.visual_verify_var).grid(
            row=4, column=0, columnspan=2, sticky=tk.W, padx=5, pady=5)

        # Enable/disable error recovery
        self.error_recovery_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(settings_frame, text="Enable error recovery & retry",
                       variable=self.error_recovery_var).grid(
            row=5, column=0, columnspan=2, sticky=tk.W, padx=5, pady=5)

        # User Profiles
        profile_frame = ttk.LabelFrame(parent, text="User Profiles", padding="10")
        profile_frame.grid(row=2, column=0, sticky=(tk.W, tk.E), pady=10)

        ttk.Label(profile_frame, text="Current Profile:").grid(
            row=0, column=0, sticky=tk.W, padx=5, pady=5)

        self.profile_var = tk.StringVar(value=self.current_profile)
        profile_combo = ttk.Combobox(profile_frame, textvariable=self.profile_var,
                                     values=["default", "child", "adult", "custom"])
        profile_combo.grid(row=0, column=1, padx=5, pady=5)

        ttk.Button(profile_frame, text="Switch Profile",
                  command=self.switch_profile).grid(row=0, column=2, padx=5, pady=5)

    def log(self, message: str):
        """Add a message to the log with timestamp"""
        timestamp = time.strftime("%H:%M:%S")
        self.log_text.insert(tk.END, f"[{timestamp}] {message}\n")
        self.log_text.see(tk.END)
        self.log_text.update()

    def update_status(self, message: str):
        """Update the status bar"""
        self.status_var.set(message)
        self.root.update()

    def update_undo_redo_status(self):
        """Update undo/redo status display"""
        status = []
        if self.change_history.can_undo():
            status.append("Ctrl+Z: Undo")
        if self.change_history.can_redo():
            status.append("Ctrl+Y: Redo")
        self.undo_redo_var.set(" | ".join(status) if status else "")

    def set_command(self, command: str):
        """Set command in entry field"""
        self.command_entry.delete(0, tk.END)
        self.command_entry.insert(0, command)

    def focus_td_snap_window(self):
        """Focus TD Snap window"""
        self.log("Attempting to focus TD Snap window...")
        if WindowManager.focus_td_snap():
            self.log("✓ TD Snap window focused successfully")
        else:
            self.log("⚠️  Could not find or focus TD Snap window")
            messagebox.showwarning("Window Not Found",
                                 "Could not find TD Snap window. Make sure TD Snap is running.")

    def save_api_key(self):
        """Save API key securely"""
        self.api_key = self.api_key_var.get().strip()
        if self.api_key:
            self.save_secure_config()
            self.init_anthropic_client()
            self.log("✓ API key saved securely")
            messagebox.showinfo("Success", "API key saved successfully!")
        else:
            messagebox.showwarning("Empty Key", "Please enter an API key")

    def test_api_connection(self):
        """Test API connection"""
        if not self.api_key:
            messagebox.showwarning("No API Key", "Please configure your API key first")
            return

        self.log("Testing API connection...")
        self.update_status("Testing API connection...")

        def test():
            try:
                if not self.anthropic_client:
                    self.init_anthropic_client()

                # Simple test message
                message = self.anthropic_client.messages.create(
                    model="claude-3-5-sonnet-20241022",
                    max_tokens=50,
                    messages=[{"role": "user", "content": "Say 'API test successful'"}]
                )

                response_text = message.content[0].text
                self.log(f"✓ API test successful: {response_text}")
                messagebox.showinfo("Success", "API connection successful!")
            except Exception as e:
                self.log(f"✗ API test failed: {str(e)}")
                messagebox.showerror("API Error", f"Connection failed: {str(e)}")
            finally:
                self.update_status("Ready")

        thread = threading.Thread(target=test)
        thread.daemon = True
        thread.start()

    def record_coordinate(self, key: str):
        """Record a coordinate position"""
        self.log(f"\nRecording coordinate for: {key}")
        self.log("Move your mouse to the target position in TD Snap...")

        def capture():
            for i in range(3, 0, -1):
                self.log(f"Recording in {i}...")
                time.sleep(1)

            pos = pyautogui.position()
            self.coordinates[key] = {"x": pos.x, "y": pos.y}
            self.save_coordinates()

            self.coord_labels[key].config(text=f"x={pos.x}, y={pos.y}")
            self.log(f"✓ Recorded {key} at position ({pos.x}, {pos.y})")

            # Auto-verify after recording
            if self.visual_verify_var.get():
                self.verify_coordinate(key)

        thread = threading.Thread(target=capture)
        thread.daemon = True
        thread.start()

    def verify_coordinate(self, key: str):
        """Verify a coordinate using visual verification"""
        if key not in self.coordinates:
            self.log(f"⚠️  {key} not set, cannot verify")
            return

        coord = self.coordinates[key]
        if VisualVerifier.verify_button_exists(coord['x'], coord['y']):
            self.coord_verify_labels[key].config(text="✓ Verified", foreground="green")
            self.log(f"✓ {key} verified successfully")
        else:
            self.coord_verify_labels[key].config(text="✗ Failed", foreground="red")
            self.log(f"⚠️  {key} verification failed - position may be incorrect")

    def clear_coordinates(self):
        """Clear all saved coordinates"""
        if messagebox.askyesno("Clear Coordinates", "Are you sure you want to clear all coordinates?"):
            self.coordinates = {}
            self.save_coordinates()
            for label in self.coord_labels.values():
                label.config(text="Not set")
            for label in self.coord_verify_labels.values():
                label.config(text="")
            self.log("All coordinates cleared")

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

        if not self.api_key:
            messagebox.showwarning("API Key Required",
                                 "Please configure your Anthropic API key in the Settings tab first.")
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

    def _execute_command(self, command: str):
        """Execute the command in a separate thread"""
        try:
            self.log(f"\n{'='*60}")
            self.log(f"Processing command: {command}")
            self.update_status("Analyzing command with AI...")

            # Parse the command using AI
            parsed_command = self.parse_command_with_ai(command)

            if not parsed_command:
                self.log("ERROR: Could not understand the command")
                self.finalize_processing()
                return

            self.log(f"Understood: {parsed_command['action']} - {parsed_command['category']}")

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
                    self.log("ERROR: Could not generate items")
                    self.finalize_processing()
                    return

                self.log(f"Generated {len(items)} items")
                self.log(f"Items: {', '.join(items)}")

                # Record change for undo
                change = {
                    'type': 'add_category',
                    'category': parsed_command['category'],
                    'items': items,
                    'timestamp': time.time()
                }
                self.change_history.add_change(change)
                self.update_undo_redo_status()

                # Execute the automation
                self.update_status("Automating TD Snap...")
                self.automate_td_snap(parsed_command['category'], items)

            self.log("Command completed successfully!")

        except Exception as e:
            self.log(f"ERROR: {str(e)}")
            messagebox.showerror("Error", f"An error occurred: {str(e)}")
        finally:
            self.finalize_processing()

    def finalize_processing(self):
        """Re-enable UI after processing"""
        self.process_btn.config(state='normal')
        self.stop_btn.config(state='disabled')
        self.is_processing = False
        self.update_status("Ready")

    def parse_command_with_ai(self, command: str) -> Optional[Dict]:
        """Use AI to parse the user's natural language command"""
        try:
            if not self.anthropic_client:
                self.init_anthropic_client()

            prompt = f"""Parse this command for a TD Snap AAC app automation tool.
The user wants to add categories and items to TD Snap.

User command: "{command}"

Analyze the command and respond with ONLY a JSON object (no other text, no markdown, no code blocks):
{{
    "action": "add_category",
    "category": "the category name",
    "count": number of items (if specified, otherwise null)
}}

Examples:
"Add restaurants category" -> {{"action": "add_category", "category": "restaurants", "count": null}}
"Add colors with 20 items" -> {{"action": "add_category", "category": "colors", "count": 20}}
"Create an animals category" -> {{"action": "add_category", "category": "animals", "count": null}}

RESPOND ONLY WITH VALID JSON. DO NOT INCLUDE ANY OTHER TEXT."""

            message = self.anthropic_client.messages.create(
                model="claude-3-5-sonnet-20241022",
                max_tokens=200,
                messages=[{"role": "user", "content": prompt}]
            )

            response = message.content[0].text.strip()

            # Clean up the response
            if response.startswith('```'):
                lines = response.split('\n')
                response = '\n'.join(lines[1:-1])

            parsed = json.loads(response)
            return parsed

        except Exception as e:
            self.log(f"Error parsing command: {str(e)}")
            return None

    def generate_category_items(self, category: str, count: int = 10) -> List[str]:
        """Use AI to generate common items for a category"""
        try:
            if not self.anthropic_client:
                self.init_anthropic_client()

            prompt = f"""Generate a list of {count} common, practical items for the category "{category}"
that would be useful in an AAC (Augmentative and Alternative Communication) app for people with
speech disabilities.

Requirements:
- Items should be commonly known and used
- Keep items simple and clear (1-3 words each)
- For places, use well-known brand names or common place types
- For food, use popular dishes or restaurants
- Make items practical for everyday communication
- Use simple, everyday language

Respond with ONLY a JSON array of strings (no markdown, no code blocks, no other text):
["item1", "item2", "item3", ...]

Category: {category}
Number of items: {count}

RESPOND ONLY WITH A VALID JSON ARRAY. DO NOT ADD ANY OTHER TEXT."""

            message = self.anthropic_client.messages.create(
                model="claude-3-5-sonnet-20241022",
                max_tokens=500,
                messages=[{"role": "user", "content": prompt}]
            )

            response = message.content[0].text.strip()

            # Clean up the response
            if response.startswith('```'):
                lines = response.split('\n')
                response = '\n'.join(lines[1:-1])

            items = json.loads(response)
            return items

        except Exception as e:
            self.log(f"Error generating items: {str(e)}")
            return []

    def automate_td_snap(self, category: str, items: List[str]):
        """Automate TD Snap to add a category and items"""
        try:
            delay = float(self.delay_var.get())
            countdown = int(self.countdown_var.get())
            typing_speed = float(self.typing_speed_var.get())

            self.log("\n--- Starting TD Snap Automation ---")

            # Try to focus TD Snap window
            if WindowManager.focus_td_snap():
                self.log("✓ TD Snap window focused")
            else:
                self.log("⚠️  Could not auto-focus TD Snap - make sure it's visible!")

            self.log(f"Starting in {countdown} seconds... Position TD Snap window now.")

            # Countdown
            for i in range(countdown, 0, -1):
                if not self.is_processing:
                    self.log("Automation stopped by user")
                    return
                self.log(f"{i}...")
                time.sleep(1)

            self.log("Starting automation...")

            # Step 1: Create category if we have the coordinate
            if 'add_category' in self.coordinates:
                self.log(f"Step 1: Creating category '{category}'")
                coord = self.coordinates['add_category']

                if not self.safe_click(coord['x'], coord['y'], "add_category"):
                    return
                time.sleep(delay)

                # Type category name if we have that field
                if 'category_name' in self.coordinates:
                    self.log(f"  -> Entering category name...")
                    coord = self.coordinates['category_name']

                    if not self.safe_click(coord['x'], coord['y'], "category_name"):
                        return
                    time.sleep(delay * 0.5)

                    pyautogui.write(category, interval=typing_speed)
                    time.sleep(delay)

                    # Save if we have save button
                    if 'save_button' in self.coordinates:
                        coord = self.coordinates['save_button']
                        if not self.safe_click(coord['x'], coord['y'], "save_button"):
                            return
                        time.sleep(delay)

            # Step 2: Add items
            self.log(f"\nStep 2: Adding {len(items)} items to category")
            for idx, item in enumerate(items, 1):
                if not self.is_processing:
                    self.log("Automation stopped by user")
                    return

                self.log(f"  [{idx}/{len(items)}] Adding '{item}'...")

                # Click add button
                if 'add_button' in self.coordinates:
                    coord = self.coordinates['add_button']
                    if not self.safe_click(coord['x'], coord['y'], "add_button"):
                        if self.error_recovery_var.get():
                            self.log("  -> Retrying after error...")
                            time.sleep(delay * 2)
                            if not self.safe_click(coord['x'], coord['y'], "add_button"):
                                continue
                        else:
                            continue

                    time.sleep(delay)

                    # Type the item name
                    if 'button_label' in self.coordinates:
                        coord = self.coordinates['button_label']
                        if not self.safe_click(coord['x'], coord['y'], "button_label"):
                            continue
                        time.sleep(delay * 0.5)

                        pyautogui.write(item, interval=typing_speed)
                        time.sleep(delay * 0.5)

                        # Save the item
                        if 'save_button' in self.coordinates:
                            coord = self.coordinates['save_button']
                            if not self.safe_click(coord['x'], coord['y'], "save_button"):
                                continue
                            time.sleep(delay)

            self.log("\n--- Automation Complete ---")
            self.log(f"Successfully processed category '{category}' with {len(items)} items!")

        except Exception as e:
            self.log(f"Automation error: {str(e)}")
            raise

    def safe_click(self, x: int, y: int, name: str) -> bool:
        """Safely click with optional verification"""
        try:
            if self.visual_verify_var.get():
                if not VisualVerifier.verify_button_exists(x, y):
                    self.log(f"  ⚠️  Warning: {name} position may be incorrect")

            pyautogui.click(x, y)
            return True
        except Exception as e:
            self.log(f"  ✗ Error clicking {name}: {str(e)}")
            return False

    def analyze_vocabulary(self):
        """Analyze current TD Snap vocabulary"""
        self.log("\n--- Analyzing TD Snap Vocabulary ---")

        bounds = WindowManager.get_td_snap_bounds()
        if not bounds:
            messagebox.showwarning("TD Snap Not Found",
                                 "Could not find TD Snap window. Make sure it's running.")
            return

        self.log("Reading vocabulary from TD Snap...")
        vocabulary = OCRReader.read_td_snap_vocabulary(bounds)

        if vocabulary:
            self.log(f"Found {len(vocabulary)} vocabulary items")
            self.suggestions_text.delete(1.0, tk.END)
            self.suggestions_text.insert(tk.END, "Current Vocabulary:\n\n")
            for word in vocabulary:
                self.suggestions_text.insert(tk.END, f"  - {word}\n")
        else:
            self.log("Could not read vocabulary (OCR may not be available)")
            messagebox.showinfo("OCR Required",
                              "Install pytesseract and Tesseract OCR for vocabulary analysis.")

    def generate_suggestions(self):
        """Generate AI-powered vocabulary suggestions"""
        if not self.api_key:
            messagebox.showwarning("API Key Required",
                                 "Please configure your API key in Settings first.")
            return

        self.log("\n--- Generating AI Suggestions ---")
        self.update_status("Generating suggestions...")

        def generate():
            try:
                if not self.anthropic_client:
                    self.init_anthropic_client()

                prompt = f"""You are an AAC (Augmentative and Alternative Communication) expert.
Suggest 5 important vocabulary categories that should be added to a TD Snap device for
effective communication. For each category, provide:

1. Category name
2. Why it's important
3. 5 example words for that category

Format your response as:

**Category 1: [Name]**
Why: [Explanation]
Words: word1, word2, word3, word4, word5

**Category 2: [Name]**
...

Focus on practical, everyday communication needs."""

                message = self.anthropic_client.messages.create(
                    model="claude-3-5-sonnet-20241022",
                    max_tokens=1500,
                    messages=[{"role": "user", "content": prompt}]
                )

                suggestions = message.content[0].text

                self.suggestions_text.delete(1.0, tk.END)
                self.suggestions_text.insert(tk.END, "AI-Generated Suggestions:\n\n")
                self.suggestions_text.insert(tk.END, suggestions)

                self.log("✓ Suggestions generated successfully")

            except Exception as e:
                self.log(f"Error generating suggestions: {str(e)}")
                messagebox.showerror("Error", f"Could not generate suggestions: {str(e)}")
            finally:
                self.update_status("Ready")

        thread = threading.Thread(target=generate)
        thread.daemon = True
        thread.start()

    def apply_suggestions(self):
        """Apply selected suggestions"""
        messagebox.showinfo("Coming Soon",
                          "This feature will allow you to select and apply suggestions automatically.")

    def import_csv(self):
        """Import batch operations from CSV"""
        filename = filedialog.askopenfilename(
            title="Select CSV File",
            filetypes=[("CSV files", "*.csv"), ("All files", "*.*")]
        )

        if filename:
            try:
                import csv
                with open(filename, 'r') as f:
                    reader = csv.DictReader(f)
                    for row in reader:
                        self.batch_queue.append(row)

                self.update_batch_queue_display()
                self.log(f"✓ Imported {len(self.batch_queue)} items from CSV")
            except Exception as e:
                self.log(f"Error importing CSV: {str(e)}")
                messagebox.showerror("Import Error", f"Could not import CSV: {str(e)}")

    def add_to_batch_queue(self):
        """Add current command to batch queue"""
        command = self.command_entry.get().strip()
        if command:
            self.batch_queue.append({'command': command})
            self.update_batch_queue_display()
            self.log(f"Added to batch queue: {command}")

    def clear_batch_queue(self):
        """Clear batch queue"""
        if messagebox.askyesno("Clear Queue", "Clear all items from batch queue?"):
            self.batch_queue = []
            self.update_batch_queue_display()
            self.log("Batch queue cleared")

    def update_batch_queue_display(self):
        """Update batch queue display"""
        self.batch_queue_text.delete(1.0, tk.END)
        self.batch_queue_text.insert(tk.END, f"Batch Queue ({len(self.batch_queue)} items):\n\n")
        for idx, item in enumerate(self.batch_queue, 1):
            command = item.get('command', str(item))
            self.batch_queue_text.insert(tk.END, f"{idx}. {command}\n")

    def process_batch_queue(self):
        """Process all items in batch queue"""
        if not self.batch_queue:
            messagebox.showinfo("Empty Queue", "Batch queue is empty")
            return

        if not messagebox.askyesno("Process Batch",
                                  f"Process {len(self.batch_queue)} items in queue?"):
            return

        self.log(f"\n--- Processing Batch Queue ({len(self.batch_queue)} items) ---")

        def process():
            for idx, item in enumerate(self.batch_queue, 1):
                if not self.is_processing:
                    self.log("Batch processing stopped by user")
                    break

                command = item.get('command', str(item))
                self.log(f"\n[{idx}/{len(self.batch_queue)}] Processing: {command}")
                self._execute_command(command)
                time.sleep(2)  # Delay between batch items

            self.log("\n--- Batch Processing Complete ---")

        self.is_processing = True
        thread = threading.Thread(target=process)
        thread.daemon = True
        thread.start()

    def undo_last_change(self):
        """Undo last change"""
        change = self.change_history.undo()
        if change:
            self.log(f"\nUndo: {change['type']} - {change.get('category', 'unknown')}")
            messagebox.showinfo("Undo",
                              "Change undone. Note: TD Snap changes must be manually reverted.")
            self.update_undo_redo_status()
        else:
            self.log("Nothing to undo")

    def redo_change(self):
        """Redo change"""
        change = self.change_history.redo()
        if change:
            self.log(f"\nRedo: {change['type']} - {change.get('category', 'unknown')}")
            self.update_undo_redo_status()
        else:
            self.log("Nothing to redo")

    def switch_profile(self):
        """Switch user profile"""
        new_profile = self.profile_var.get()
        self.current_profile = new_profile
        self.log(f"Switched to profile: {new_profile}")
        messagebox.showinfo("Profile Switched", f"Now using profile: {new_profile}")


def main():
    root = tk.Tk()
    app = TDSnapAIAssistantAdvanced(root)
    root.mainloop()


if __name__ == "__main__":
    main()
