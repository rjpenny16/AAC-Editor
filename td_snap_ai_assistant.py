import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox
import pyautogui
import time
import json
import requests
from typing import List, Dict
import threading
import keyboard
import os

class TDSnapAIAssistantPro:
    def __init__(self, root):
        self.root = root
        self.root.title("TD Snap AI Assistant Pro")
        self.root.geometry("900x700")
        
        # Store the current operation status
        self.is_processing = False
        self.recording_coordinates = False
        self.coordinates = {}
        self.load_coordinates()
        
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
        
    def setup_ui(self):
        # Main frame
        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        
        # Configure grid weights
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)
        main_frame.columnconfigure(0, weight=1)
        main_frame.rowconfigure(3, weight=1)
        
        # Title
        title_label = ttk.Label(main_frame, text="TD Snap AI Assistant Pro", 
                               font=('Arial', 16, 'bold'))
        title_label.grid(row=0, column=0, pady=10)
        
        # Notebook for tabs
        notebook = ttk.Notebook(main_frame)
        notebook.grid(row=1, column=0, sticky=(tk.W, tk.E, tk.N, tk.S), pady=10)
        
        # Tab 1: Main Control
        control_tab = ttk.Frame(notebook, padding="10")
        notebook.add(control_tab, text="Command")
        self.setup_control_tab(control_tab)
        
        # Tab 2: Coordinate Setup
        coord_tab = ttk.Frame(notebook, padding="10")
        notebook.add(coord_tab, text="Setup Coordinates")
        self.setup_coordinate_tab(coord_tab)
        
        # Tab 3: Settings
        settings_tab = ttk.Frame(notebook, padding="10")
        notebook.add(settings_tab, text="Settings")
        self.setup_settings_tab(settings_tab)
        
        # Output/Log section
        log_frame = ttk.LabelFrame(main_frame, text="Activity Log", padding="10")
        log_frame.grid(row=2, column=0, sticky=(tk.W, tk.E, tk.N, tk.S), pady=10)
        log_frame.columnconfigure(0, weight=1)
        log_frame.rowconfigure(0, weight=1)
        
        self.log_text = scrolledtext.ScrolledText(log_frame, height=12, width=70, 
                                                  wrap=tk.WORD)
        self.log_text.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        
        # Status bar
        self.status_var = tk.StringVar(value="Ready")
        status_bar = ttk.Label(main_frame, textvariable=self.status_var, 
                              relief=tk.SUNKEN, anchor=tk.W)
        status_bar.grid(row=3, column=0, sticky=(tk.W, tk.E))
        
        self.log("TD Snap AI Assistant Pro initialized.")
        self.log("Example commands: 'Add restaurants category', 'Add colors', etc.")
        if not self.coordinates:
            self.log("\n⚠️  IMPORTANT: Go to 'Setup Coordinates' tab to configure TD Snap button locations!")
        
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
                           command=lambda e=example: self.command_entry.delete(0, tk.END) or self.command_entry.insert(0, e))
            btn.grid(row=i//2, column=i%2, padx=5, pady=5, sticky=(tk.W, tk.E))
            
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
5. Repeat for all required positions"""
        
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
        for idx, (key, label) in enumerate(coord_points):
            ttk.Label(coords_frame, text=f"{label}:").grid(row=idx, column=0, sticky=tk.W, padx=5, pady=5)
            
            coord_text = self.coordinates.get(key, "Not set")
            self.coord_labels[key] = ttk.Label(coords_frame, text=str(coord_text), 
                                              foreground="blue")
            self.coord_labels[key].grid(row=idx, column=1, sticky=tk.W, padx=5, pady=5)
            
            ttk.Button(coords_frame, text="Record", 
                      command=lambda k=key: self.record_coordinate(k)).grid(
                          row=idx, column=2, padx=5, pady=5)
                          
        # Clear all button
        ttk.Button(coords_frame, text="Clear All Coordinates", 
                  command=self.clear_coordinates).grid(row=len(coord_points), column=0, 
                                                      columnspan=3, pady=10)
        
    def setup_settings_tab(self, parent):
        """Setup the settings tab"""
        parent.columnconfigure(0, weight=1)
        
        settings_frame = ttk.LabelFrame(parent, text="Automation Settings", padding="10")
        settings_frame.grid(row=0, column=0, sticky=(tk.W, tk.E), pady=10)
        
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
        
    def record_coordinate(self, key):
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
            self.log("All coordinates cleared")
        
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
        
    def parse_command_with_ai(self, command: str) -> Dict:
        """Use AI to parse the user's natural language command"""
        try:
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

            response = self.call_claude_api(prompt, max_tokens=200)
            
            if not response:
                return None
            
            # Clean up the response
            response_text = response.strip()
            if response_text.startswith('```'):
                lines = response_text.split('\n')
                response_text = '\n'.join(lines[1:-1])
            
            parsed = json.loads(response_text)
            return parsed
            
        except Exception as e:
            self.log(f"Error parsing command: {str(e)}")
            return None
            
    def generate_category_items(self, category: str, count: int = 10) -> List[str]:
        """Use AI to generate common items for a category"""
        try:
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

            response = self.call_claude_api(prompt, max_tokens=500)
            
            if not response:
                return []
            
            # Clean up the response
            response_text = response.strip()
            if response_text.startswith('```'):
                lines = response_text.split('\n')
                response_text = '\n'.join(lines[1:-1])
                
            items = json.loads(response_text)
            return items
            
        except Exception as e:
            self.log(f"Error generating items: {str(e)}")
            return []
            
    def call_claude_api(self, prompt: str, max_tokens: int = 1000) -> str:
        """Call the Claude API"""
        try:
            response = requests.post(
                "https://api.anthropic.com/v1/messages",
                headers={"Content-Type": "application/json"},
                json={
                    "model": "claude-sonnet-4-20250514",
                    "max_tokens": max_tokens,
                    "messages": [{"role": "user", "content": prompt}]
                },
                timeout=30
            )
            
            if response.status_code == 200:
                data = response.json()
                return data['content'][0]['text']
            else:
                self.log(f"API Error: {response.status_code} - {response.text}")
                return None
                
        except Exception as e:
            self.log(f"API call failed: {str(e)}")
            return None
            
    def automate_td_snap(self, category: str, items: List[str]):
        """Automate TD Snap to add a category and items"""
        try:
            delay = float(self.delay_var.get())
            countdown = int(self.countdown_var.get())
            typing_speed = float(self.typing_speed_var.get())
            
            self.log("\n--- Starting TD Snap Automation ---")
            self.log("IMPORTANT: Make sure TD Snap is open and visible!")
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
                pyautogui.click(coord['x'], coord['y'])
                time.sleep(delay)
                
                # Type category name if we have that field
                if 'category_name' in self.coordinates:
                    self.log(f"  -> Entering category name...")
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
            self.log(f"\nStep 2: Adding {len(items)} items to category")
            for idx, item in enumerate(items, 1):
                if not self.is_processing:
                    self.log("Automation stopped by user")
                    return
                    
                self.log(f"  [{idx}/{len(items)}] Adding '{item}'...")
                
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
                
            self.log("\n--- Automation Complete ---")
            self.log(f"Successfully processed category '{category}' with {len(items)} items!")
            
        except Exception as e:
            self.log(f"Automation error: {str(e)}")
            raise

def main():
    root = tk.Tk()
    app = TDSnapAIAssistantPro(root)
    root.mainloop()

if __name__ == "__main__":
    main()
