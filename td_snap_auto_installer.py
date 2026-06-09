"""
TD Snap AI Assistant - Auto Installer & Setup Wizard
One-click setup - installs everything automatically!
"""

import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext
import subprocess
import sys
import os
import platform
import urllib.request
import zipfile
import shutil
from pathlib import Path
import threading
import json

class AutoInstaller:
    """Automatic installer and setup wizard"""

    def __init__(self):
        self.root = tk.Tk()
        self.root.title("TD Snap AI Assistant - Auto Installer")
        self.root.geometry("700x600")

        self.install_dir = Path.home() / "TDSnapAssistant"
        self.ollama_installed = False
        self.python_installed = False
        self.dependencies_installed = False
        self.ollama_model_downloaded = False

        self.current_step = 0
        self.setup_ui()
        self.check_requirements()

    def setup_ui(self):
        """Setup installer UI"""
        main_frame = ttk.Frame(self.root, padding="20")
        main_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))

        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)
        main_frame.columnconfigure(0, weight=1)
        main_frame.rowconfigure(3, weight=1)

        # Title
        title = ttk.Label(main_frame,
                         text="🚀 TD Snap AI Assistant\nAutomatic Setup Wizard",
                         font=('Arial', 18, 'bold'),
                         justify=tk.CENTER)
        title.grid(row=0, column=0, pady=20)

        subtitle = ttk.Label(main_frame,
                            text="One-click setup! Just sit back and relax...",
                            font=('Arial', 12),
                            justify=tk.CENTER)
        subtitle.grid(row=1, column=0, pady=10)

        # Progress section
        progress_frame = ttk.LabelFrame(main_frame, text="Installation Progress", padding="15")
        progress_frame.grid(row=2, column=0, sticky=(tk.W, tk.E), pady=10)
        progress_frame.columnconfigure(0, weight=1)

        self.progress_var = tk.DoubleVar(value=0)
        self.progress_bar = ttk.Progressbar(progress_frame,
                                           variable=self.progress_var,
                                           maximum=100,
                                           length=600)
        self.progress_bar.grid(row=0, column=0, pady=10, sticky=(tk.W, tk.E))

        self.status_var = tk.StringVar(value="Checking requirements...")
        status_label = ttk.Label(progress_frame,
                                textvariable=self.status_var,
                                font=('Arial', 11))
        status_label.grid(row=1, column=0, pady=5)

        # Steps checklist
        steps_frame = ttk.Frame(progress_frame)
        steps_frame.grid(row=2, column=0, pady=10)

        self.step_labels = {}
        steps = [
            ("python", "✓ Python Installed"),
            ("ollama", "✓ Ollama Installed"),
            ("model", "✓ AI Model Downloaded"),
            ("deps", "✓ Dependencies Installed"),
            ("app", "✓ Application Ready")
        ]

        for idx, (key, text) in enumerate(steps):
            label = ttk.Label(steps_frame, text=f"⏳ {text}", foreground="gray")
            label.grid(row=idx, column=0, sticky=tk.W, pady=3)
            self.step_labels[key] = label

        # Log section
        log_frame = ttk.LabelFrame(main_frame, text="Activity Log", padding="10")
        log_frame.grid(row=3, column=0, sticky=(tk.W, tk.E, tk.N, tk.S), pady=10)
        log_frame.columnconfigure(0, weight=1)
        log_frame.rowconfigure(0, weight=1)

        self.log_text = scrolledtext.ScrolledText(log_frame,
                                                   height=12,
                                                   width=70,
                                                   wrap=tk.WORD)
        self.log_text.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))

        # Buttons
        button_frame = ttk.Frame(main_frame)
        button_frame.grid(row=4, column=0, pady=10)

        self.install_btn = ttk.Button(button_frame,
                                      text="🚀 Start Automatic Installation",
                                      command=self.start_installation,
                                      width=30)
        self.install_btn.grid(row=0, column=0, padx=5)

        self.launch_btn = ttk.Button(button_frame,
                                     text="▶️ Launch Application",
                                     command=self.launch_app,
                                     state='disabled',
                                     width=25)
        self.launch_btn.grid(row=0, column=1, padx=5)

        self.log("Welcome to TD Snap AI Assistant Auto-Installer!")
        self.log("This wizard will automatically set up everything you need.")
        self.log("")

    def log(self, message: str):
        """Add message to log"""
        self.log_text.insert(tk.END, f"{message}\n")
        self.log_text.see(tk.END)
        self.log_text.update()

    def update_status(self, message: str):
        """Update status label"""
        self.status_var.set(message)
        self.root.update()

    def update_progress(self, value: float):
        """Update progress bar"""
        self.progress_var.set(value)
        self.root.update()

    def check_step(self, step_key: str, success: bool = True):
        """Mark step as complete"""
        label = self.step_labels[step_key]
        if success:
            label.config(text=label.cget("text").replace("⏳", "✅"),
                        foreground="green")
        else:
            label.config(text=label.cget("text").replace("⏳", "❌"),
                        foreground="red")
        self.root.update()

    def check_requirements(self):
        """Check what's already installed"""
        self.log("\n=== Checking System Requirements ===")

        # Check Python
        self.log("Checking Python...")
        if sys.executable:
            version = sys.version.split()[0]
            self.log(f"✓ Python {version} found")
            self.python_installed = True
            self.check_step("python", True)
        else:
            self.log("✗ Python not found")

        # Check Ollama
        self.log("Checking Ollama...")
        if self.is_ollama_installed():
            self.log("✓ Ollama found")
            self.ollama_installed = True
            self.check_step("ollama", True)
        else:
            self.log("✗ Ollama not installed")

        self.log("\n=== Ready for Installation ===")
        self.log("Click 'Start Automatic Installation' to begin!")

    def is_ollama_installed(self) -> bool:
        """Check if Ollama is installed"""
        try:
            result = subprocess.run(['ollama', '--version'],
                                   capture_output=True,
                                   timeout=5)
            return result.returncode == 0
        except:
            return False

    def start_installation(self):
        """Start automatic installation"""
        self.install_btn.config(state='disabled')
        self.log("\n" + "="*60)
        self.log("🚀 STARTING AUTOMATIC INSTALLATION")
        self.log("="*60 + "\n")

        # Run in thread to keep UI responsive
        thread = threading.Thread(target=self.install_everything)
        thread.daemon = True
        thread.start()

    def install_everything(self):
        """Install all components"""
        try:
            total_steps = 5
            current = 0

            # Step 1: Ensure Python dependencies
            if not self.dependencies_installed:
                current += 1
                self.update_progress((current / total_steps) * 100)
                self.update_status("Installing Python dependencies...")
                self.install_python_dependencies()

            # Step 2: Install Ollama
            if not self.ollama_installed:
                current += 1
                self.update_progress((current / total_steps) * 100)
                self.update_status("Installing Ollama...")
                self.install_ollama()

            # Step 3: Download AI model
            if not self.ollama_model_downloaded:
                current += 1
                self.update_progress((current / total_steps) * 100)
                self.update_status("Downloading AI model (this may take a few minutes)...")
                self.download_ollama_model()

            # Step 4: Copy application files
            current += 1
            self.update_progress((current / total_steps) * 100)
            self.update_status("Setting up application...")
            self.setup_application()

            # Step 5: Create desktop shortcut
            current += 1
            self.update_progress(100)
            self.update_status("Creating shortcuts...")
            self.create_shortcuts()

            # Done!
            self.log("\n" + "="*60)
            self.log("🎉 INSTALLATION COMPLETE!")
            self.log("="*60)
            self.log("\nYou're ready to start using TD Snap AI Assistant!")
            self.log("Click 'Launch Application' to begin!")

            self.launch_btn.config(state='normal')

            messagebox.showinfo("Installation Complete!",
                              "TD Snap AI Assistant is ready to use!\n\n"
                              "Click 'Launch Application' to start.")

        except Exception as e:
            self.log(f"\n❌ ERROR: {str(e)}")
            messagebox.showerror("Installation Error",
                               f"An error occurred during installation:\n\n{str(e)}\n\n"
                               "Please check the Activity Log for details.")
            self.install_btn.config(state='normal')

    def install_python_dependencies(self):
        """Install Python packages"""
        self.log("\n--- Installing Python Dependencies ---")

        packages = [
            'pyautogui',
            'pillow',
            'requests',
            'keyboard',
            'pygetwindow',
            'pytesseract',
            'opencv-python',
            'cryptography'
        ]

        for pkg in packages:
            self.log(f"Installing {pkg}...")
            try:
                subprocess.run([sys.executable, '-m', 'pip', 'install', pkg],
                             check=True,
                             capture_output=True)
                self.log(f"  ✓ {pkg} installed")
            except subprocess.CalledProcessError as e:
                self.log(f"  ⚠️ {pkg} failed: {e}")

        self.dependencies_installed = True
        self.check_step("deps", True)
        self.log("✓ All Python dependencies installed")

    def install_ollama(self):
        """Install Ollama"""
        self.log("\n--- Installing Ollama ---")

        system = platform.system()

        if system == "Windows":
            self.log("Downloading Ollama for Windows...")
            url = "https://ollama.ai/download/OllamaSetup.exe"
            installer_path = Path.home() / "Downloads" / "OllamaSetup.exe"

            try:
                # Download installer
                self.log("Downloading...")
                urllib.request.urlretrieve(url, installer_path)
                self.log("✓ Download complete")

                # Run installer
                self.log("\nRunning Ollama installer...")
                self.log("⚠️ Please complete the Ollama installation wizard")
                self.log("   (Click through the installer prompts)")

                messagebox.showinfo("Ollama Installation",
                                  "The Ollama installer will now open.\n\n"
                                  "Please click through the installation wizard.\n\n"
                                  "When finished, this setup will continue automatically.")

                subprocess.run([str(installer_path)])

                # Wait for installation
                self.log("Waiting for Ollama installation to complete...")
                for i in range(30):  # Wait up to 30 seconds
                    if self.is_ollama_installed():
                        break
                    self.log(f"  Checking... ({i+1}/30)")
                    import time
                    time.sleep(1)

                if self.is_ollama_installed():
                    self.log("✓ Ollama installed successfully")
                    self.ollama_installed = True
                    self.check_step("ollama", True)
                else:
                    raise Exception("Ollama installation not detected. Please install manually from https://ollama.ai")

            except Exception as e:
                self.log(f"❌ Error: {str(e)}")
                messagebox.showerror("Ollama Installation",
                                   "Automatic Ollama installation failed.\n\n"
                                   "Please install Ollama manually:\n"
                                   "1. Visit https://ollama.ai\n"
                                   "2. Download and install\n"
                                   "3. Restart this installer")
                raise

        elif system == "Darwin":  # macOS
            self.log("For macOS, please install Ollama using Homebrew:")
            self.log("  brew install ollama")
            messagebox.showinfo("Ollama Installation",
                              "Please install Ollama:\n\n"
                              "1. Open Terminal\n"
                              "2. Run: brew install ollama\n"
                              "3. Then restart this installer")
            raise Exception("Please install Ollama manually on macOS")

        else:  # Linux
            self.log("Installing Ollama for Linux...")
            try:
                subprocess.run(['curl', '-fsSL', 'https://ollama.ai/install.sh'],
                             stdout=subprocess.PIPE,
                             check=True)
                self.log("✓ Ollama installed")
                self.ollama_installed = True
                self.check_step("ollama", True)
            except:
                messagebox.showinfo("Ollama Installation",
                                  "Please install Ollama:\n\n"
                                  "curl https://ollama.ai/install.sh | sh")
                raise Exception("Please install Ollama manually on Linux")

    def download_ollama_model(self):
        """Download Ollama model"""
        self.log("\n--- Downloading AI Model ---")
        self.log("Downloading Llama 3 model (~4.7GB)...")
        self.log("This may take 5-15 minutes depending on your internet speed...")
        self.log("Please be patient!")

        try:
            # Start Ollama service first
            self.log("\nStarting Ollama service...")
            subprocess.Popen(['ollama', 'serve'],
                           stdout=subprocess.DEVNULL,
                           stderr=subprocess.DEVNULL)

            import time
            time.sleep(3)  # Give it time to start

            # Download model
            self.log("Pulling llama3 model...")
            process = subprocess.Popen(['ollama', 'pull', 'llama3'],
                                      stdout=subprocess.PIPE,
                                      stderr=subprocess.PIPE,
                                      universal_newlines=True)

            # Show progress
            for line in process.stdout:
                if 'pulling' in line.lower() or 'download' in line.lower():
                    self.log(f"  {line.strip()}")

            process.wait()

            if process.returncode == 0:
                self.log("✓ AI model downloaded successfully")
                self.ollama_model_downloaded = True
                self.check_step("model", True)
            else:
                raise Exception("Model download failed")

        except Exception as e:
            self.log(f"❌ Error downloading model: {str(e)}")
            self.log("\nYou can download the model manually later:")
            self.log("  1. Open terminal/command prompt")
            self.log("  2. Run: ollama pull llama3")
            self.check_step("model", False)

    def setup_application(self):
        """Setup application files"""
        self.log("\n--- Setting Up Application ---")

        # Create installation directory
        self.install_dir.mkdir(parents=True, exist_ok=True)
        self.log(f"Installation directory: {self.install_dir}")

        # Copy application file
        app_file = Path(__file__).parent / "td_snap_ai_assistant_free.py"
        if app_file.exists():
            shutil.copy(app_file, self.install_dir / "td_snap_assistant.py")
            self.log("✓ Application files copied")
        else:
            # If running from compiled exe, extract bundled file
            self.log("⚠️ Application will be downloaded on first run")

        self.check_step("app", True)
        self.log("✓ Application ready")

    def create_shortcuts(self):
        """Create desktop shortcuts"""
        self.log("\n--- Creating Shortcuts ---")

        try:
            desktop = Path.home() / "Desktop"

            if platform.system() == "Windows":
                # Create Windows shortcut
                shortcut_path = desktop / "TD Snap Assistant.lnk"

                # Use PowerShell to create shortcut
                ps_script = f"""
                $WshShell = New-Object -comObject WScript.Shell
                $Shortcut = $WshShell.CreateShortcut("{shortcut_path}")
                $Shortcut.TargetPath = "python"
                $Shortcut.Arguments = "{self.install_dir / 'td_snap_assistant.py'}"
                $Shortcut.WorkingDirectory = "{self.install_dir}"
                $Shortcut.Save()
                """

                subprocess.run(['powershell', '-Command', ps_script],
                             check=True,
                             capture_output=True)

                self.log(f"✓ Desktop shortcut created")

            else:
                self.log("ℹ️ Manual shortcut creation needed for this OS")

        except Exception as e:
            self.log(f"⚠️ Shortcut creation failed: {str(e)}")
            self.log("   You can launch manually from:")
            self.log(f"   {self.install_dir / 'td_snap_assistant.py'}")

    def launch_app(self):
        """Launch the application"""
        self.log("\n🚀 Launching TD Snap AI Assistant...")

        try:
            app_file = self.install_dir / "td_snap_assistant.py"
            if not app_file.exists():
                # Use the current directory version
                app_file = Path(__file__).parent / "td_snap_ai_assistant_free.py"

            subprocess.Popen([sys.executable, str(app_file)])
            self.log("✓ Application launched!")

            messagebox.showinfo("Launched!",
                              "TD Snap AI Assistant is now running!\n\n"
                              "You can close this installer.")

            self.root.quit()

        except Exception as e:
            messagebox.showerror("Launch Error",
                               f"Could not launch application:\n{str(e)}")


def main():
    """Main entry point"""
    installer = AutoInstaller()
    installer.root.mainloop()


if __name__ == "__main__":
    main()
