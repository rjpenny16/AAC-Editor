"""
TD Snap AI Assistant - Free Edition
100% Free with Local AI Support (Ollama, LM Studio, GPT4All)
Also supports Claude API if you have a key
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


class AIProvider:
    """Base class for AI providers"""

    def __init__(self, name: str):
        self.name = name
        self.available = False

    def test_connection(self) -> Tuple[bool, str]:
        """Test if provider is available"""
        raise NotImplementedError

    def generate(self, prompt: str, max_tokens: int = 1000) -> Optional[str]:
        """Generate text from prompt"""
        raise NotImplementedError


class OllamaProvider(AIProvider):
    """Ollama - Free local AI"""

    def __init__(self, base_url: str = "http://localhost:11434", model: str = "llama3"):
        super().__init__("Ollama (Local)")
        self.base_url = base_url
        self.model = model
        self.available = self.test_connection()[0]

    def test_connection(self) -> Tuple[bool, str]:
        """Test Ollama connection"""
        try:
            response = requests.get(f"{self.base_url}/api/tags", timeout=2)
            if response.status_code == 200:
                models = response.json().get('models', [])
                if models:
                    return True, f"Connected! Available models: {len(models)}"
                else:
                    return False, "Ollama running but no models installed. Run: ollama pull llama3"
            return False, "Ollama not responding"
        except:
            return False, "Ollama not running. Install from: https://ollama.ai"

    def generate(self, prompt: str, max_tokens: int = 1000) -> Optional[str]:
        """Generate with Ollama"""
        try:
            response = requests.post(
                f"{self.base_url}/api/generate",
                json={
                    "model": self.model,
                    "prompt": prompt,
                    "stream": False
                },
                timeout=30
            )

            if response.status_code == 200:
                return response.json().get('response', '')
            return None
        except Exception as e:
            print(f"Ollama error: {e}")
            return None


class LMStudioProvider(AIProvider):
    """LM Studio - Local AI with OpenAI-compatible API"""

    def __init__(self, base_url: str = "http://localhost:1234"):
        super().__init__("LM Studio (Local)")
        self.base_url = base_url
        self.available = self.test_connection()[0]

    def test_connection(self) -> Tuple[bool, str]:
        """Test LM Studio connection"""
        try:
            response = requests.get(f"{self.base_url}/v1/models", timeout=2)
            if response.status_code == 200:
                models = response.json().get('data', [])
                return True, f"Connected! {len(models)} model(s) loaded"
            return False, "LM Studio not responding"
        except:
            return False, "LM Studio not running. Download from: https://lmstudio.ai"

    def generate(self, prompt: str, max_tokens: int = 1000) -> Optional[str]:
        """Generate with LM Studio"""
        try:
            response = requests.post(
                f"{self.base_url}/v1/chat/completions",
                json={
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0.7,
                    "max_tokens": max_tokens
                },
                timeout=30
            )

            if response.status_code == 200:
                return response.json()['choices'][0]['message']['content']
            return None
        except Exception as e:
            print(f"LM Studio error: {e}")
            return None


class GPT4AllProvider(AIProvider):
    """GPT4All - Local AI"""

    def __init__(self, base_url: str = "http://localhost:4891"):
        super().__init__("GPT4All (Local)")
        self.base_url = base_url
        self.available = self.test_connection()[0]

    def test_connection(self) -> Tuple[bool, str]:
        """Test GPT4All connection"""
        try:
            # GPT4All uses OpenAI-compatible API
            response = requests.get(f"{self.base_url}/v1/models", timeout=2)
            if response.status_code == 200:
                return True, "Connected!"
            return False, "GPT4All not responding"
        except:
            return False, "GPT4All not running. Download from: https://gpt4all.io"

    def generate(self, prompt: str, max_tokens: int = 1000) -> Optional[str]:
        """Generate with GPT4All"""
        try:
            response = requests.post(
                f"{self.base_url}/v1/chat/completions",
                json={
                    "messages": [{"role": "user", "content": prompt}],
                    "max_tokens": max_tokens
                },
                timeout=30
            )

            if response.status_code == 200:
                return response.json()['choices'][0]['message']['content']
            return None
        except Exception as e:
            print(f"GPT4All error: {e}")
            return None


class ClaudeProvider(AIProvider):
    """Claude API (requires API key)"""

    def __init__(self, api_key: str = ""):
        super().__init__("Claude API (Paid)")
        self.api_key = api_key
        self.client = None
        if api_key:
            try:
                import anthropic
                self.client = anthropic.Anthropic(api_key=api_key)
                self.available = True
            except:
                self.available = False

    def test_connection(self) -> Tuple[bool, str]:
        """Test Claude API"""
        if not self.api_key:
            return False, "No API key provided"

        try:
            message = self.client.messages.create(
                model="claude-3-5-sonnet-20241022",
                max_tokens=50,
                messages=[{"role": "user", "content": "Say 'OK'"}]
            )
            return True, "API key valid!"
        except Exception as e:
            return False, f"API error: {str(e)}"

    def generate(self, prompt: str, max_tokens: int = 1000) -> Optional[str]:
        """Generate with Claude"""
        try:
            message = self.client.messages.create(
                model="claude-3-5-sonnet-20241022",
                max_tokens=max_tokens,
                messages=[{"role": "user", "content": prompt}]
            )
            return message.content[0].text
        except Exception as e:
            print(f"Claude error: {e}")
            return None


class SecureStorage:
    """Secure storage for API keys"""

    def __init__(self, config_dir: str = ".config"):
        self.config_dir = Path(config_dir)
        self.config_dir.mkdir(exist_ok=True)
        self.key_file = self.config_dir / "key.enc"
        self.data_file = self.config_dir / "data.enc"
        self._ensure_key()

    def _ensure_key(self):
        if not self.key_file.exists():
            key = Fernet.generate_key()
            self.key_file.write_bytes(key)

    def _get_cipher(self) -> Fernet:
        key = self.key_file.read_bytes()
        return Fernet(key)

    def save(self, data: dict):
        cipher = self._get_cipher()
        json_data = json.dumps(data).encode()
        encrypted = cipher.encrypt(json_data)
        self.data_file.write_bytes(encrypted)

    def load(self) -> dict:
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
    """Track changes for undo/redo"""

    def __init__(self, max_history: int = 50):
        self.max_history = max_history
        self.history = []
        self.current_index = -1

    def add_change(self, change: dict):
        if self.current_index < len(self.history) - 1:
            self.history = self.history[:self.current_index + 1]

        self.history.append(change)
        if len(self.history) > self.max_history:
            self.history.pop(0)
        else:
            self.current_index += 1

    def can_undo(self) -> bool:
        return self.current_index >= 0

    def can_redo(self) -> bool:
        return self.current_index < len(self.history) - 1

    def undo(self) -> Optional[dict]:
        if self.can_undo():
            change = self.history[self.current_index]
            self.current_index -= 1
            return change
        return None

    def redo(self) -> Optional[dict]:
        if self.can_redo():
            self.current_index += 1
            return self.history[self.current_index]
        return None


class WindowManager:
    """Manage TD Snap window detection"""

    @staticmethod
    def find_td_snap_window():
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
        window = WindowManager.find_td_snap_window()
        if window:
            return (window.left, window.top, window.width, window.height)
        return None


class VisualVerifier:
    """Visual verification using screenshots"""

    @staticmethod
    def capture_region(x: int, y: int, width: int, height: int) -> np.ndarray:
        screenshot = ImageGrab.grab(bbox=(x, y, x + width, y + height))
        return cv2.cvtColor(np.array(screenshot), cv2.COLOR_RGB2BGR)

    @staticmethod
    def verify_button_exists(x: int, y: int, width: int = 100, height: int = 40) -> bool:
        try:
            img = VisualVerifier.capture_region(x - 10, y - 10, width, height)
            return img is not None and img.size > 0
        except:
            return False


class TDSnapAIAssistantFree:
    """Free TD Snap AI Assistant with local AI support"""

    def __init__(self, root):
        self.root = root
        self.root.title("TD Snap AI Assistant - Free Edition")
        self.root.geometry("1000x800")

        # Core state
        self.is_processing = False
        self.coordinates = {}
        self.current_profile = "default"

        # AI Providers
        self.providers = {}
        self.current_provider = None

        # Advanced features
        self.secure_storage = SecureStorage()
        self.change_history = ChangeHistory()
        self.batch_queue = []

        # Load data
        self.load_coordinates()
        self.load_config()
        self.init_ai_providers()

        # Setup UI
        self.setup_ui()
        self.setup_shortcuts()

        # Check for available providers
        self.check_available_providers()

    def init_ai_providers(self):
        """Initialize all AI providers"""
        config = self.secure_storage.load()

        # Local providers (always available if running)
        self.providers['ollama'] = OllamaProvider()
        self.providers['lmstudio'] = LMStudioProvider()
        self.providers['gpt4all'] = GPT4AllProvider()

        # Cloud provider (needs API key)
        claude_key = config.get('claude_api_key', '')
        self.providers['claude'] = ClaudeProvider(claude_key)

        # Set default provider (first available)
        for name, provider in self.providers.items():
            if provider.available:
                self.current_provider = name
                break

    def check_available_providers(self):
        """Check and log available providers"""
        available = []
        for name, provider in self.providers.items():
            is_avail, msg = provider.test_connection()
            if is_avail:
                available.append(f"✓ {provider.name}")
            else:
                self.log(f"⚠️  {provider.name}: {msg}")

        if available:
            self.log(f"\n✓ Available AI providers:")
            for prov in available:
                self.log(f"  {prov}")
            self.log(f"\nUsing: {self.providers[self.current_provider].name}")
        else:
            self.log("\n⚠️  No AI providers available!")
            self.log("Install Ollama (easiest): https://ollama.ai")
            self.log("Then run: ollama pull llama3")

    def load_coordinates(self):
        if os.path.exists('td_snap_coordinates.json'):
            try:
                with open('td_snap_coordinates.json', 'r') as f:
                    self.coordinates = json.load(f)
            except:
                self.coordinates = {}
        else:
            self.coordinates = {}

    def save_coordinates(self):
        with open('td_snap_coordinates.json', 'w') as f:
            json.dump(self.coordinates, f, indent=2)

    def load_config(self):
        config = self.secure_storage.load()
        self.current_provider = config.get('ai_provider', 'ollama')

    def save_config(self):
        config = {
            'ai_provider': self.current_provider,
            'claude_api_key': self.providers['claude'].api_key if 'claude' in self.providers else ''
        }
        self.secure_storage.save(config)

    def setup_shortcuts(self):
        self.root.bind('<Control-z>', lambda e: self.undo_last_change())
        self.root.bind('<Control-y>', lambda e: self.redo_change())
        self.root.bind('<Control-s>', lambda e: self.save_coordinates())
        self.root.bind('<Escape>', lambda e: self.stop_processing())

    def setup_ui(self):
        """Setup the user interface"""
        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))

        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)
        main_frame.columnconfigure(0, weight=1)
        main_frame.rowconfigure(1, weight=1)

        # Title
        title_label = ttk.Label(main_frame, text="TD Snap AI Assistant - Free Edition (100% Local AI)",
                               font=('Arial', 16, 'bold'))
        title_label.grid(row=0, column=0, pady=10)

        # Notebook for tabs
        notebook = ttk.Notebook(main_frame)
        notebook.grid(row=1, column=0, sticky=(tk.W, tk.E, tk.N, tk.S), pady=10)

        # Tabs
        control_tab = ttk.Frame(notebook, padding="10")
        notebook.add(control_tab, text="Command")
        self.setup_control_tab(control_tab)

        batch_tab = ttk.Frame(notebook, padding="10")
        notebook.add(batch_tab, text="Batch Operations")
        self.setup_batch_tab(batch_tab)

        coord_tab = ttk.Frame(notebook, padding="10")
        notebook.add(coord_tab, text="Setup Coordinates")
        self.setup_coordinate_tab(coord_tab)

        settings_tab = ttk.Frame(notebook, padding="10")
        notebook.add(settings_tab, text="Settings")
        self.setup_settings_tab(settings_tab)

        # Activity Log
        log_frame = ttk.LabelFrame(main_frame, text="Activity Log", padding="10")
        log_frame.grid(row=2, column=0, sticky=(tk.W, tk.E, tk.N, tk.S), pady=10)
        log_frame.columnconfigure(0, weight=1)
        log_frame.rowconfigure(0, weight=1)

        self.log_text = scrolledtext.ScrolledText(log_frame, height=10, width=70, wrap=tk.WORD)
        self.log_text.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))

        # Status bar
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

        self.log("🆓 TD Snap AI Assistant Free Edition - 100% Free Local AI!")
        self.log("Using completely free local AI models - no API costs!")

    def setup_control_tab(self, parent):
        """Setup main control tab"""
        parent.columnconfigure(0, weight=1)

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
            "Add animals with 15 items",
            "Create colors category",
            "Add food category"
        ]

        for i, example in enumerate(examples):
            btn = ttk.Button(examples_frame, text=example,
                           command=lambda e=example: self.set_command(e))
            btn.grid(row=i//2, column=i%2, padx=5, pady=5, sticky=(tk.W, tk.E))

    def setup_batch_tab(self, parent):
        """Setup batch operations tab"""
        parent.columnconfigure(0, weight=1)
        parent.rowconfigure(1, weight=1)

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

        queue_frame = ttk.LabelFrame(parent, text="Batch Queue", padding="10")
        queue_frame.grid(row=1, column=0, sticky=(tk.W, tk.E, tk.N, tk.S), pady=10)
        queue_frame.columnconfigure(0, weight=1)
        queue_frame.rowconfigure(0, weight=1)

        self.batch_queue_text = scrolledtext.ScrolledText(queue_frame, height=15,
                                                          width=70, wrap=tk.WORD)
        self.batch_queue_text.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))

    def setup_coordinate_tab(self, parent):
        """Setup coordinate recording tab"""
        parent.columnconfigure(0, weight=1)

        info_frame = ttk.Frame(parent)
        info_frame.grid(row=0, column=0, sticky=(tk.W, tk.E), pady=10)

        info_text = """Setup TD Snap automation by recording button positions.

Instructions:
1. Open TD Snap and enter edit mode
2. Click a 'Record' button below
3. You have 3 seconds to position your mouse over the target in TD Snap
4. The position will be recorded automatically
5. Click 'Verify' to confirm the position is correct"""

        ttk.Label(info_frame, text=info_text, justify=tk.LEFT).grid(row=0, column=0, sticky=tk.W)

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

        ttk.Button(coords_frame, text="Clear All Coordinates",
                  command=self.clear_coordinates).grid(row=len(coord_points), column=0,
                                                      columnspan=5, pady=10)

    def setup_settings_tab(self, parent):
        """Setup settings tab"""
        parent.columnconfigure(0, weight=1)

        # AI Provider Selection
        ai_frame = ttk.LabelFrame(parent, text="AI Provider (100% FREE OPTIONS!)", padding="10")
        ai_frame.grid(row=0, column=0, sticky=(tk.W, tk.E), pady=10)
        ai_frame.columnconfigure(1, weight=1)

        ttk.Label(ai_frame, text="Select AI Provider:", font=('Arial', 10, 'bold')).grid(
            row=0, column=0, columnspan=3, sticky=tk.W, padx=5, pady=5)

        self.provider_var = tk.StringVar(value=self.current_provider)

        providers_info = [
            ("ollama", "Ollama (FREE, Local) ⭐ RECOMMENDED", "https://ollama.ai"),
            ("lmstudio", "LM Studio (FREE, Local)", "https://lmstudio.ai"),
            ("gpt4all", "GPT4All (FREE, Local)", "https://gpt4all.io"),
            ("claude", "Claude API (Paid, requires API key)", "https://console.anthropic.com")
        ]

        for idx, (key, name, url) in enumerate(providers_info, start=1):
            provider = self.providers.get(key)
            is_available = provider.available if provider else False
            status = "✓ Available" if is_available else "Not running"
            color = "green" if is_available else "red"

            ttk.Radiobutton(ai_frame, text=name, variable=self.provider_var,
                          value=key, command=self.switch_provider).grid(
                row=idx, column=0, sticky=tk.W, padx=5, pady=2)

            ttk.Label(ai_frame, text=status, foreground=color).grid(
                row=idx, column=1, sticky=tk.W, padx=5, pady=2)

            ttk.Button(ai_frame, text="Setup Guide",
                      command=lambda u=url: self.open_setup_guide(u)).grid(
                row=idx, column=2, padx=5, pady=2)

        # Test connection button
        ttk.Button(ai_frame, text="Test Current Provider",
                  command=self.test_current_provider).grid(
            row=len(providers_info)+1, column=0, columnspan=3, pady=10)

        # Claude API Key (optional)
        claude_frame = ttk.LabelFrame(parent, text="Claude API Key (Optional)", padding="10")
        claude_frame.grid(row=1, column=0, sticky=(tk.W, tk.E), pady=10)
        claude_frame.columnconfigure(1, weight=1)

        ttk.Label(claude_frame, text="Only needed if using Claude:").grid(
            row=0, column=0, sticky=tk.W, padx=5, pady=5)

        self.api_key_var = tk.StringVar(value="")
        api_key_entry = ttk.Entry(claude_frame, textvariable=self.api_key_var,
                                  width=50, show="*")
        api_key_entry.grid(row=1, column=0, columnspan=2, sticky=(tk.W, tk.E), padx=5, pady=5)

        ttk.Button(claude_frame, text="Save Claude API Key",
                  command=self.save_claude_key).grid(row=2, column=0, padx=5, pady=5)

        # Automation Settings
        settings_frame = ttk.LabelFrame(parent, text="Automation Settings", padding="10")
        settings_frame.grid(row=2, column=0, sticky=(tk.W, tk.E), pady=10)

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

        self.visual_verify_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(settings_frame, text="Enable visual verification",
                       variable=self.visual_verify_var).grid(
            row=4, column=0, columnspan=2, sticky=tk.W, padx=5, pady=5)

        self.error_recovery_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(settings_frame, text="Enable error recovery & retry",
                       variable=self.error_recovery_var).grid(
            row=5, column=0, columnspan=2, sticky=tk.W, padx=5, pady=5)

    def open_setup_guide(self, url: str):
        """Open setup guide in browser"""
        import webbrowser
        webbrowser.open(url)
        self.log(f"Opening setup guide: {url}")

    def switch_provider(self):
        """Switch AI provider"""
        new_provider = self.provider_var.get()
        if new_provider in self.providers and self.providers[new_provider].available:
            self.current_provider = new_provider
            self.save_config()
            self.log(f"Switched to: {self.providers[new_provider].name}")
        else:
            messagebox.showwarning("Provider Not Available",
                                 f"{self.providers[new_provider].name} is not running. "
                                 f"Please start it first and click 'Test Current Provider'")
            # Revert selection
            self.provider_var.set(self.current_provider)

    def test_current_provider(self):
        """Test current AI provider"""
        provider = self.providers[self.current_provider]
        self.log(f"\nTesting {provider.name}...")

        is_available, message = provider.test_connection()
        if is_available:
            self.log(f"✓ {message}")
            messagebox.showinfo("Success", f"{provider.name} is working!")
        else:
            self.log(f"✗ {message}")
            messagebox.showerror("Connection Failed", message)

        # Refresh available providers
        self.check_available_providers()

    def save_claude_key(self):
        """Save Claude API key"""
        api_key = self.api_key_var.get().strip()
        if api_key:
            self.providers['claude'] = ClaudeProvider(api_key)
            self.save_config()
            self.log("✓ Claude API key saved")
            messagebox.showinfo("Success", "Claude API key saved!")
        else:
            messagebox.showwarning("Empty Key", "Please enter an API key")

    def log(self, message: str):
        """Add message to log"""
        timestamp = time.strftime("%H:%M:%S")
        self.log_text.insert(tk.END, f"[{timestamp}] {message}\n")
        self.log_text.see(tk.END)
        self.log_text.update()

    def update_status(self, message: str):
        """Update status bar"""
        self.status_var.set(message)
        self.root.update()

    def update_undo_redo_status(self):
        """Update undo/redo display"""
        status = []
        if self.change_history.can_undo():
            status.append("Ctrl+Z: Undo")
        if self.change_history.can_redo():
            status.append("Ctrl+Y: Redo")
        self.undo_redo_var.set(" | ".join(status) if status else "")

    def set_command(self, command: str):
        """Set command in entry"""
        self.command_entry.delete(0, tk.END)
        self.command_entry.insert(0, command)

    def focus_td_snap_window(self):
        """Focus TD Snap window"""
        self.log("Attempting to focus TD Snap window...")
        if WindowManager.focus_td_snap():
            self.log("✓ TD Snap window focused")
        else:
            self.log("⚠️  Could not find TD Snap window")
            messagebox.showwarning("Window Not Found", "Could not find TD Snap window")

    def record_coordinate(self, key: str):
        """Record coordinate position"""
        self.log(f"\nRecording coordinate for: {key}")
        self.log("Move your mouse to the target position...")

        def capture():
            for i in range(3, 0, -1):
                self.log(f"Recording in {i}...")
                time.sleep(1)

            pos = pyautogui.position()
            self.coordinates[key] = {"x": pos.x, "y": pos.y}
            self.save_coordinates()

            self.coord_labels[key].config(text=f"x={pos.x}, y={pos.y}")
            self.log(f"✓ Recorded {key} at ({pos.x}, {pos.y})")

            if self.visual_verify_var.get():
                self.verify_coordinate(key)

        thread = threading.Thread(target=capture)
        thread.daemon = True
        thread.start()

    def verify_coordinate(self, key: str):
        """Verify coordinate"""
        if key not in self.coordinates:
            return

        coord = self.coordinates[key]
        if VisualVerifier.verify_button_exists(coord['x'], coord['y']):
            self.coord_verify_labels[key].config(text="✓ Verified", foreground="green")
            self.log(f"✓ {key} verified")
        else:
            self.coord_verify_labels[key].config(text="✗ Failed", foreground="red")
            self.log(f"⚠️  {key} verification failed")

    def clear_coordinates(self):
        """Clear all coordinates"""
        if messagebox.askyesno("Clear", "Clear all coordinates?"):
            self.coordinates = {}
            self.save_coordinates()
            for label in self.coord_labels.values():
                label.config(text="Not set")
            for label in self.coord_verify_labels.values():
                label.config(text="")
            self.log("Coordinates cleared")

    def stop_processing(self):
        """Stop processing"""
        self.is_processing = False
        self.log("Stop requested")

    def process_command(self):
        """Process command"""
        command = self.command_entry.get().strip()
        if not command:
            messagebox.showwarning("Empty Command", "Please enter a command")
            return

        provider = self.providers.get(self.current_provider)
        if not provider or not provider.available:
            messagebox.showwarning("No AI Available",
                                 "No AI provider available. Please install Ollama:\n"
                                 "1. Visit https://ollama.ai\n"
                                 "2. Download and install\n"
                                 "3. Run: ollama pull llama3")
            return

        if not self.coordinates:
            messagebox.showwarning("Setup Required",
                                 "Please configure coordinates first")
            return

        self.process_btn.config(state='disabled')
        self.stop_btn.config(state='normal')
        self.is_processing = True

        thread = threading.Thread(target=self._execute_command, args=(command,))
        thread.daemon = True
        thread.start()

    def _execute_command(self, command: str):
        """Execute command"""
        try:
            self.log(f"\n{'='*60}")
            self.log(f"Processing: {command}")
            self.update_status("Analyzing with AI...")

            parsed = self.parse_command_with_ai(command)
            if not parsed:
                self.log("ERROR: Could not understand command")
                self.finalize_processing()
                return

            self.log(f"Understood: {parsed['category']}")

            self.update_status("Generating items...")
            items_count = int(self.items_count_var.get())
            if 'count' in parsed and parsed['count']:
                items_count = parsed['count']

            items = self.generate_category_items(parsed['category'], items_count)
            if not items:
                self.log("ERROR: Could not generate items")
                self.finalize_processing()
                return

            self.log(f"Generated {len(items)} items")
            self.log(f"Items: {', '.join(items)}")

            # Record change
            change = {
                'type': 'add_category',
                'category': parsed['category'],
                'items': items,
                'timestamp': time.time()
            }
            self.change_history.add_change(change)
            self.update_undo_redo_status()

            # Automate
            self.update_status("Automating TD Snap...")
            self.automate_td_snap(parsed['category'], items)

            self.log("✓ Command completed!")

        except Exception as e:
            self.log(f"ERROR: {str(e)}")
            messagebox.showerror("Error", str(e))
        finally:
            self.finalize_processing()

    def finalize_processing(self):
        """Re-enable UI"""
        self.process_btn.config(state='normal')
        self.stop_btn.config(state='disabled')
        self.is_processing = False
        self.update_status("Ready")

    def parse_command_with_ai(self, command: str) -> Optional[Dict]:
        """Parse command with AI"""
        provider = self.providers[self.current_provider]

        prompt = f"""Parse this command for adding items to TD Snap AAC app.

User command: "{command}"

Respond with ONLY valid JSON (no markdown, no explanation):
{{"action": "add_category", "category": "category name", "count": number or null}}

Examples:
"Add restaurants" -> {{"action": "add_category", "category": "restaurants", "count": null}}
"Add colors with 15 items" -> {{"action": "add_category", "category": "colors", "count": 15}}

ONLY JSON OUTPUT:"""

        try:
            response = provider.generate(prompt, max_tokens=200)
            if not response:
                return None

            # Clean response
            response = response.strip()
            if response.startswith('```'):
                lines = response.split('\n')
                response = '\n'.join(lines[1:-1]) if len(lines) > 2 else response

            # Try to extract JSON
            start = response.find('{')
            end = response.rfind('}') + 1
            if start >= 0 and end > start:
                response = response[start:end]

            return json.loads(response)
        except Exception as e:
            self.log(f"Parse error: {str(e)}")
            return None

    def generate_category_items(self, category: str, count: int = 10) -> List[str]:
        """Generate items with AI"""
        provider = self.providers[self.current_provider]

        prompt = f"""Generate {count} common items for AAC category "{category}".

Requirements:
- Practical everyday words
- Simple (1-3 words each)
- Common and useful
- For AAC communication device

Respond with ONLY a JSON array (no markdown, no explanation):
["item1", "item2", "item3", ...]

ONLY JSON ARRAY OUTPUT:"""

        try:
            response = provider.generate(prompt, max_tokens=500)
            if not response:
                return []

            # Clean response
            response = response.strip()
            if response.startswith('```'):
                lines = response.split('\n')
                response = '\n'.join(lines[1:-1]) if len(lines) > 2 else response

            # Try to extract JSON array
            start = response.find('[')
            end = response.rfind(']') + 1
            if start >= 0 and end > start:
                response = response[start:end]

            items = json.loads(response)
            return items if isinstance(items, list) else []
        except Exception as e:
            self.log(f"Generate error: {str(e)}")
            return []

    def automate_td_snap(self, category: str, items: List[str]):
        """Automate TD Snap"""
        try:
            delay = float(self.delay_var.get())
            countdown = int(self.countdown_var.get())
            typing_speed = float(self.typing_speed_var.get())

            self.log("\n--- Starting Automation ---")

            if WindowManager.focus_td_snap():
                self.log("✓ TD Snap focused")
            else:
                self.log("⚠️  Ensure TD Snap is visible")

            self.log(f"Starting in {countdown} seconds...")

            for i in range(countdown, 0, -1):
                if not self.is_processing:
                    return
                self.log(f"{i}...")
                time.sleep(1)

            self.log("Starting automation...")

            # Create category
            if 'add_category' in self.coordinates:
                self.log(f"Creating category '{category}'")
                coord = self.coordinates['add_category']
                self.safe_click(coord['x'], coord['y'], "add_category")
                time.sleep(delay)

                if 'category_name' in self.coordinates:
                    coord = self.coordinates['category_name']
                    self.safe_click(coord['x'], coord['y'], "category_name")
                    time.sleep(delay * 0.5)
                    pyautogui.write(category, interval=typing_speed)
                    time.sleep(delay)

                    if 'save_button' in self.coordinates:
                        coord = self.coordinates['save_button']
                        self.safe_click(coord['x'], coord['y'], "save")
                        time.sleep(delay)

            # Add items
            self.log(f"\nAdding {len(items)} items")
            for idx, item in enumerate(items, 1):
                if not self.is_processing:
                    return

                self.log(f"  [{idx}/{len(items)}] {item}")

                if 'add_button' in self.coordinates:
                    coord = self.coordinates['add_button']
                    if not self.safe_click(coord['x'], coord['y'], "add_button"):
                        if self.error_recovery_var.get():
                            time.sleep(delay * 2)
                            if not self.safe_click(coord['x'], coord['y'], "add_button"):
                                continue
                        else:
                            continue
                    time.sleep(delay)

                    if 'button_label' in self.coordinates:
                        coord = self.coordinates['button_label']
                        self.safe_click(coord['x'], coord['y'], "label")
                        time.sleep(delay * 0.5)
                        pyautogui.write(item, interval=typing_speed)
                        time.sleep(delay * 0.5)

                        if 'save_button' in self.coordinates:
                            coord = self.coordinates['save_button']
                            self.safe_click(coord['x'], coord['y'], "save")
                            time.sleep(delay)

            self.log("\n--- Automation Complete ---")
            self.log(f"✓ Added category '{category}' with {len(items)} items!")

        except Exception as e:
            self.log(f"Automation error: {str(e)}")
            raise

    def safe_click(self, x: int, y: int, name: str) -> bool:
        """Safe click with verification"""
        try:
            if self.visual_verify_var.get():
                if not VisualVerifier.verify_button_exists(x, y):
                    self.log(f"  ⚠️  {name} position uncertain")
            pyautogui.click(x, y)
            return True
        except Exception as e:
            self.log(f"  ✗ Click error: {str(e)}")
            return False

    def import_csv(self):
        """Import CSV"""
        filename = filedialog.askopenfilename(
            title="Select CSV",
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
                self.log(f"✓ Imported {len(self.batch_queue)} items")
            except Exception as e:
                messagebox.showerror("Import Error", str(e))

    def add_to_batch_queue(self):
        """Add to queue"""
        command = self.command_entry.get().strip()
        if command:
            self.batch_queue.append({'command': command})
            self.update_batch_queue_display()
            self.log(f"Added to queue: {command}")

    def clear_batch_queue(self):
        """Clear queue"""
        if messagebox.askyesno("Clear", "Clear queue?"):
            self.batch_queue = []
            self.update_batch_queue_display()
            self.log("Queue cleared")

    def update_batch_queue_display(self):
        """Update queue display"""
        self.batch_queue_text.delete(1.0, tk.END)
        self.batch_queue_text.insert(tk.END, f"Queue ({len(self.batch_queue)}):\n\n")
        for idx, item in enumerate(self.batch_queue, 1):
            self.batch_queue_text.insert(tk.END, f"{idx}. {item.get('command', str(item))}\n")

    def process_batch_queue(self):
        """Process queue"""
        if not self.batch_queue:
            messagebox.showinfo("Empty", "Queue is empty")
            return

        if not messagebox.askyesno("Process", f"Process {len(self.batch_queue)} items?"):
            return

        self.log(f"\n--- Processing Batch ({len(self.batch_queue)}) ---")

        def process():
            for idx, item in enumerate(self.batch_queue, 1):
                if not self.is_processing:
                    break
                command = item.get('command', str(item))
                self.log(f"\n[{idx}/{len(self.batch_queue)}] {command}")
                self._execute_command(command)
                time.sleep(2)
            self.log("\n--- Batch Complete ---")

        self.is_processing = True
        thread = threading.Thread(target=process)
        thread.daemon = True
        thread.start()

    def undo_last_change(self):
        """Undo"""
        change = self.change_history.undo()
        if change:
            self.log(f"\nUndo: {change.get('category')}")
            self.update_undo_redo_status()
        else:
            self.log("Nothing to undo")

    def redo_change(self):
        """Redo"""
        change = self.change_history.redo()
        if change:
            self.log(f"\nRedo: {change.get('category')}")
            self.update_undo_redo_status()
        else:
            self.log("Nothing to redo")


def main():
    root = tk.Tk()
    app = TDSnapAIAssistantFree(root)
    root.mainloop()


if __name__ == "__main__":
    main()
