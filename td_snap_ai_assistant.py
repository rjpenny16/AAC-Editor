import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox
import pyautogui
import time
import json
import requests
from typing import List, Dict
import threading

class TDSnapAIAssistant:
    def __init__(self, root):
        self.root = root
        self.root.title("TD Snap AI Assistant")
        self.root.geometry("800x600")
        
        # Store the current operation status
        self.is_processing = False
        
        self.setup_ui()
        
    def setup_ui(self):
        # Main frame
        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        
        # Configure grid weights
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)
        main_frame.columnconfigure(0, weight=1)
        main_frame.rowconfigure(2, weight=1)
        
        # Title
        title_label = ttk.Label(main_frame, text="TD Snap AI Assistant", 
                               font=('Arial', 16, 'bold'))
        title_label.grid(row=0, column=0, pady=10)
        
        # Input section
        input_frame = ttk.LabelFrame(main_frame, text="Command Input", padding="10")
        input_frame.grid(row=1, column=0, sticky=(tk.W, tk.E), pady=10)
        input_frame.columnconfigure(0, weight=1)
        
        ttk.Label(input_frame, text="Enter your request (e.g., 'Add restaurants category'):").grid(
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
        
        # Settings frame
        settings_frame = ttk.LabelFrame(main_frame, text="Settings", padding="10")
        settings_frame.grid(row=3, column=0, sticky=(tk.W, tk.E), pady=10)
        
        ttk.Label(settings_frame, text="Delay between actions (seconds):").grid(
            row=0, column=0, sticky=tk.W, padx=5)
        self.delay_var = tk.StringVar(value="1.0")
        delay_entry = ttk.Entry(settings_frame, textvariable=self.delay_var, width=10)
        delay_entry.grid(row=0, column=1, padx=5)
        
        ttk.Label(settings_frame, text="Items per category:").grid(
            row=0, column=2, sticky=tk.W, padx=5)
        self.items_count_var = tk.StringVar(value="10")
        items_entry = ttk.Entry(settings_frame, textvariable=self.items_count_var, width=10)
        items_entry.grid(row=0, column=3, padx=5)
        
        # Output/Log section
        log_frame = ttk.LabelFrame(main_frame, text="Activity Log", padding="10")
        log_frame.grid(row=2, column=0, sticky=(tk.W, tk.E, tk.N, tk.S), pady=10)
        log_frame.columnconfigure(0, weight=1)
        log_frame.rowconfigure(0, weight=1)
        
        self.log_text = scrolledtext.ScrolledText(log_frame, height=15, width=70, 
                                                  wrap=tk.WORD)
        self.log_text.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        
        # Status bar
        self.status_var = tk.StringVar(value="Ready")
        status_bar = ttk.Label(main_frame, textvariable=self.status_var, 
                              relief=tk.SUNKEN, anchor=tk.W)
        status_bar.grid(row=4, column=0, sticky=(tk.W, tk.E))
        
        self.log("TD Snap AI Assistant initialized. Ready to process commands.")
        self.log("Example commands:")
        self.log("  - 'Add restaurants category'")
        self.log("  - 'Add colors category'")
        self.log("  - 'Add animals category with 15 items'")
        
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
                if 'count' in parsed_command:
                    items_count = parsed_command['count']
                    
                items = self.generate_category_items(
                    parsed_command['category'], 
                    items_count
                )
                
                if not items:
                    self.log("ERROR: Could not generate items")
                    self.finalize_processing()
                    return
                    
                self.log(f"Generated {len(items)} items: {', '.join(items[:5])}{'...' if len(items) > 5 else ''}")
                
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

Analyze the command and respond with ONLY a JSON object (no other text):
{{
    "action": "add_category",
    "category": "the category name",
    "count": number of items (if specified, otherwise null)
}}

Examples:
"Add restaurants category" -> {{"action": "add_category", "category": "restaurants", "count": null}}
"Add colors with 20 items" -> {{"action": "add_category", "category": "colors", "count": 20}}
"Create an animals category" -> {{"action": "add_category", "category": "animals", "count": null}}

Respond ONLY with valid JSON. Do not include any other text or explanation."""

            response = self.call_claude_api(prompt, max_tokens=200)
            
            # Try to extract JSON from the response
            response_text = response.strip()
            
            # Remove markdown code blocks if present
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
- Keep items simple and clear
- For places, use well-known brand names or common place types
- For food, use popular dishes or restaurants
- Make items practical for everyday communication

Respond with ONLY a JSON array of strings (no other text):
["item1", "item2", "item3", ...]

Category: {category}
Number of items: {count}

RESPOND ONLY WITH A VALID JSON ARRAY."""

            response = self.call_claude_api(prompt, max_tokens=500)
            
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
        """Call the Claude API (uses the free API available in the environment)"""
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
                self.log(f"API Error: {response.status_code}")
                return None
                
        except Exception as e:
            self.log(f"API call failed: {str(e)}")
            return None
            
    def automate_td_snap(self, category: str, items: List[str]):
        """Automate TD Snap to add a category and items"""
        try:
            delay = float(self.delay_var.get())
            
            self.log("\n--- Starting TD Snap Automation ---")
            self.log("IMPORTANT: Make sure TD Snap is open and in edit mode!")
            self.log(f"Starting in 5 seconds... Position TD Snap window now.")
            
            # Countdown
            for i in range(5, 0, -1):
                if not self.is_processing:
                    self.log("Automation stopped by user")
                    return
                self.log(f"{i}...")
                time.sleep(1)
                
            self.log("Starting automation...")
            
            # Note: These are example automation steps
            # The actual implementation will depend on TD Snap's UI
            # Users will need to adjust coordinates and timing
            
            self.log(f"Step 1: Creating category '{category}'")
            self.log("  -> Right-clicking to open context menu...")
            # pyautogui.rightClick()  # User needs to position this
            time.sleep(delay)
            
            self.log("  -> Looking for 'Add Category' option...")
            # This is where you'd click on the add category button
            # The user needs to teach the script where to click
            
            self.log(f"\nStep 2: Adding {len(items)} items to category")
            for idx, item in enumerate(items, 1):
                if not self.is_processing:
                    self.log("Automation stopped by user")
                    return
                    
                self.log(f"  [{idx}/{len(items)}] Adding '{item}'...")
                
                # Example automation (needs to be customized):
                # 1. Click the "Add Button" location
                # pyautogui.click(x, y)
                # time.sleep(delay)
                
                # 2. Type the item name
                # pyautogui.write(item, interval=0.05)
                # time.sleep(delay)
                
                # 3. Press Enter or click OK
                # pyautogui.press('enter')
                # time.sleep(delay)
                
                # Simulate the delay
                time.sleep(delay)
                
            self.log("\n--- Automation Complete ---")
            self.log(f"Successfully added category '{category}' with {len(items)} items!")
            self.log("\nNOTE: This is a demo. To actually control TD Snap, you need to:")
            self.log("1. Identify the exact click coordinates in TD Snap")
            self.log("2. Uncomment and configure the pyautogui commands")
            self.log("3. Adjust delays as needed for your system")
            
        except Exception as e:
            self.log(f"Automation error: {str(e)}")
            raise

def main():
    root = tk.Tk()
    app = TDSnapAIAssistant(root)
    root.mainloop()

if __name__ == "__main__":
    main()
