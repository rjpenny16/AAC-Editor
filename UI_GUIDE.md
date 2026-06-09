# TD SNAP AI ASSISTANT - USER INTERFACE GUIDE

## 🖥️ Main Window Overview

```
┌─────────────────────────────────────────────────────────────────┐
│  TD Snap AI Assistant Pro                                    [_][□][×]│
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│                   TD Snap AI Assistant Pro                       │
│                                                                  │
├─────────────────────────────────────────────────────────────────┤
│  [Command]  [Setup Coordinates]  [Settings]                     │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌─ Command Input ──────────────────────────────────────────┐  │
│  │                                                            │  │
│  │  Enter your request (e.g., 'Add restaurants category'):   │  │
│  │  ┌───────────────────────────────────────────────────┐   │  │
│  │  │ Add restaurants category                          │   │  │
│  │  └───────────────────────────────────────────────────┘   │  │
│  │                                                            │  │
│  │     [Process Command]  [Stop]                             │  │
│  │                                                            │  │
│  └────────────────────────────────────────────────────────────┘  │
│                                                                  │
│  ┌─ Quick Examples ──────────────────────────────────────────┐  │
│  │                                                            │  │
│  │  [Add restaurants category]  [Add animals with 15 items]  │  │
│  │  [Create a colors category]  [Add food category]          │  │
│  │                                                            │  │
│  └────────────────────────────────────────────────────────────┘  │
│                                                                  │
│  ┌─ Activity Log ────────────────────────────────────────────┐  │
│  │ [10:15:23] TD Snap AI Assistant Pro initialized.          │  │
│  │ [10:15:23] Example commands: 'Add restaurants', etc.      │  │
│  │ [10:16:45] Processing command: Add restaurants category   │  │
│  │ [10:16:45] Analyzing command with AI...                   │  │
│  │ [10:16:48] Understood: add_category - restaurants         │  │
│  │ [10:16:48] Generating items with AI...                    │  │
│  │ [10:16:52] Generated 10 items                             │  │
│  │ [10:16:52] Items: McDonald's, Burger King, Subway...      │  │
│  │ [10:16:52] Starting automation...                         │  │
│  │ [10:16:52] 5...                                           │  │
│  │ [10:16:53] 4...                                           │  │
│  │ [10:16:54] 3...                                           │  │
│  │ [10:16:55] 2...                                           │  │
│  │ [10:16:56] 1...                                           │  │
│  │ [10:16:57] Starting automation...                         │  │
│  │ [10:16:57] Step 1: Creating category 'restaurants'        │  │
│  │ [10:16:59] Step 2: Adding 10 items to category            │  │
│  │ [10:17:00]   [1/10] Adding 'McDonald's'...               │  │
│  │ [10:17:02]   [2/10] Adding 'Burger King'...              │  │
│  │                                                            │  │
│  └────────────────────────────────────────────────────────────┘  │
│                                                                  │
│  Status: Ready                                                   │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

## 📍 Setup Coordinates Tab

```
┌─────────────────────────────────────────────────────────────────┐
│  TD Snap AI Assistant Pro                                    [_][□][×]│
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│                   TD Snap AI Assistant Pro                       │
│                                                                  │
├─────────────────────────────────────────────────────────────────┤
│  [Command]  [Setup Coordinates]  [Settings]                     │
│              ^^^^^^^^^^^^^^^^^^                                  │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  Instructions:                                                   │
│  To automate TD Snap, the assistant needs to know where to      │
│  click. Press the buttons below and then click on the           │
│  corresponding location in TD Snap.                             │
│                                                                  │
│  1. Open TD Snap and enter edit mode                            │
│  2. Click a button below (e.g., 'Add Category Button')          │
│  3. You have 3 seconds to move your mouse over the target       │
│  4. The program will record that position                       │
│  5. Repeat for all required positions                           │
│                                                                  │
│  ┌─ Record Coordinates ─────────────────────────────────────┐  │
│  │                                                            │  │
│  │  Add Category Button:      x=150, y=200      [Record]     │  │
│  │  Add New Button/Word:      x=200, y=300      [Record]     │  │
│  │  Button Label Field:       x=300, y=350      [Record]     │  │
│  │  Category Name Field:      x=250, y=250      [Record]     │  │
│  │  Save Button:              x=400, y=500      [Record]     │  │
│  │                                                            │  │
│  │              [Clear All Coordinates]                       │  │
│  │                                                            │  │
│  └────────────────────────────────────────────────────────────┘  │
│                                                                  │
│  ┌─ Activity Log ────────────────────────────────────────────┐  │
│  │ [10:20:15] Recording coordinate for: add_category         │  │
│  │ [10:20:15] Move your mouse to target in TD Snap...        │  │
│  │ [10:20:16] Recording in 3...                              │  │
│  │ [10:20:17] Recording in 2...                              │  │
│  │ [10:20:18] Recording in 1...                              │  │
│  │ [10:20:19] ✓ Recorded add_category at (150, 200)          │  │
│  │                                                            │  │
│  └────────────────────────────────────────────────────────────┘  │
│                                                                  │
│  Status: Ready                                                   │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

## ⚙️ Settings Tab

```
┌─────────────────────────────────────────────────────────────────┐
│  TD Snap AI Assistant Pro                                    [_][□][×]│
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│                   TD Snap AI Assistant Pro                       │
│                                                                  │
├─────────────────────────────────────────────────────────────────┤
│  [Command]  [Setup Coordinates]  [Settings]                     │
│                                  ^^^^^^^^^^                      │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌─ Automation Settings ─────────────────────────────────────┐  │
│  │                                                            │  │
│  │  Delay between actions (seconds):    [1.0    ]           │  │
│  │                                                            │  │
│  │  Default items per category:         [10     ]           │  │
│  │                                                            │  │
│  │  Countdown before start (seconds):   [5      ]           │  │
│  │                                                            │  │
│  │  Typing speed (chars/sec):           [0.05   ]           │  │
│  │                                                            │  │
│  └────────────────────────────────────────────────────────────┘  │
│                                                                  │
│  Tips:                                                           │
│  • Increase delay if TD Snap is slow to respond                 │
│  • Decrease delay for faster automation                         │
│  • Lower typing speed = faster typing                           │
│  • Increase countdown if you need more time to position windows │
│                                                                  │
│                                                                  │
│  ┌─ Activity Log ────────────────────────────────────────────┐  │
│  │                                                            │  │
│  │                                                            │  │
│  └────────────────────────────────────────────────────────────┘  │
│                                                                  │
│  Status: Ready                                                   │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

## 🎨 Visual States

### 1. Processing State
```
┌─ Command Input ──────────────────────────────────────────┐
│  Enter your request:                                      │
│  ┌───────────────────────────────────────────────────┐   │
│  │ Add restaurants category                          │   │
│  └───────────────────────────────────────────────────┘   │
│                                                            │
│     [Process Command]  [Stop]                             │
│     (Button disabled)  (Button enabled)                   │
│                                                            │
└────────────────────────────────────────────────────────────┘

Status: Analyzing command with AI...
        ^^^^^^^^^^^^^^^^^^^^^^^^^^^
```

### 2. Recording Coordinate State
```
┌─ Record Coordinates ─────────────────────────────────────┐
│                                                            │
│  Add Category Button:      Recording...      [Record]     │
│                            ^^^^^^^^^^^^      (disabled)    │
│                                                            │
└────────────────────────────────────────────────────────────┘

Activity Log shows:
[10:20:16] Recording in 3...
[10:20:17] Recording in 2...
[10:20:18] Recording in 1...
```

### 3. Success State
```
Activity Log shows:
[10:17:15] --- Automation Complete ---
[10:17:15] Successfully processed category 'restaurants' with 10 items!
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
           Green text or highlighted
```

### 4. Error State
```
Activity Log shows:
[10:18:30] ERROR: Could not understand the command
           ^^^^^
           Red text

Or:
[10:18:45] ⚠️  IMPORTANT: Go to 'Setup Coordinates' tab to configure!
```

## 📱 Button States

### Primary Button (Process Command)
```
Normal:     [Process Command]  ← Blue/Primary color, clickable
Processing: [Process Command]  ← Grayed out, disabled
Hover:      [Process Command]  ← Slightly lighter, cursor changes
```

### Stop Button
```
Normal:     [Stop]  ← Grayed out, disabled
Active:     [Stop]  ← Red/Warning color, enabled
Hover:      [Stop]  ← Slightly darker red
```

### Record Buttons
```
Normal:     [Record]  ← Green, clickable
Recording:  [Record]  ← Grayed out, disabled
Hover:      [Record]  ← Slightly lighter green
```

## 🎯 Quick Examples Buttons

```
┌─ Quick Examples ──────────────────────────────────────────┐
│                                                            │
│  ┌──────────────────────────┐  ┌──────────────────────┐  │
│  │Add restaurants category  │  │Add animals with 15...│  │
│  └──────────────────────────┘  └──────────────────────┘  │
│  ┌──────────────────────────┐  ┌──────────────────────┐  │
│  │Create a colors category  │  │Add food category     │  │
│  └──────────────────────────┘  └──────────────────────┘  │
│                                                            │
└────────────────────────────────────────────────────────────┘

When clicked: Auto-fills the command input field
```

## 💬 Activity Log Features

### Color Coding (if implemented)
```
[10:15:23] Normal message          ← Black text
[10:15:23] ✓ Success message       ← Green text
[10:15:23] ⚠️  Warning message      ← Orange text
[10:15:23] ERROR: Error message    ← Red text
[10:15:23] Step 1: Process steps   ← Blue text
```

### Auto-Scroll
```
The log automatically scrolls to show the latest message
User can scroll up to see history
```

### Timestamps
```
All messages include [HH:MM:SS] timestamp for debugging
```

## 🖱️ Mouse Interactions

### Hover Effects
- Buttons: Slight color change + cursor pointer
- Input fields: Border highlight
- Text: No change (read-only log)

### Click Effects
- Buttons: Brief press animation
- Quick examples: Immediately updates input field
- Tabs: Tab switches, previous content preserved

### Drag & Drop
- Not implemented (future feature)
- Could allow dragging category templates

## ⌨️ Keyboard Shortcuts

### Current
- `Enter` in command field → Process Command
- `Esc` (future) → Stop current process

### Planned
- `Ctrl+R` → Record coordinate
- `Ctrl+S` → Save settings
- `Ctrl+Q` → Quit application

## 📐 Window Sizing

### Default Size
```
Width:  900 pixels
Height: 700 pixels
Minimum: 800x600
```

### Resizable
```
✓ Window can be resized
✓ Components scale with window
✓ Log area expands most
✓ Buttons stay at top
```

### Layout on Different Screens

#### Large Screen (1920x1080)
```
Plenty of space, everything visible
Log shows ~20 lines
```

#### Medium Screen (1366x768)
```
All elements visible
Log shows ~12 lines
Some scrolling needed
```

#### Small Screen (1024x768)
```
All elements still accessible
Log shows ~8 lines
More scrolling needed
```

## 🎭 Theme & Colors

### Current Theme (Default)
```
Background: Light gray (#F0F0F0)
Text: Black (#000000)
Buttons: System default (usually blue)
Input fields: White (#FFFFFF)
Status bar: Light gray with sunken border
```

### Future Themes
- Dark mode
- High contrast
- Custom colors

## 🔍 Visual Feedback

### Progress Indicators

#### Countdown
```
[10:16:52] Starting automation...
[10:16:52] 5...
[10:16:53] 4...
[10:16:54] 3...
[10:16:55] 2...
[10:16:56] 1...
[10:16:57] Starting automation...
```

#### Item Progress
```
[10:17:00]   [1/10] Adding 'McDonald's'...
[10:17:02]   [2/10] Adding 'Burger King'...
[10:17:04]   [3/10] Adding 'Subway'...
              ^^^^^^
              Shows progress
```

#### Status Bar
```
Status: Ready
Status: Analyzing command with AI...
Status: Generating items...
Status: Automating TD Snap...
Status: Ready
```

## 📱 Responsive Design

### Tab Content
```
Each tab preserves its state
Switching tabs doesn't lose your work
Settings persist between sessions
Coordinates saved to file
```

### Input Validation
```
Empty command    → Warning dialog
Invalid settings → Reverts to default
Bad coordinates  → Ignored until valid
```

## 🎬 Animation & Transitions

### Current
- Instant tab switching
- Immediate button state changes
- Real-time log updates

### Future Enhancements
- Fade transitions between tabs
- Progress bars for AI processing
- Animated success/error messages
- Smooth scroll in log

## 📊 Information Density

### High Information
- Activity log (dense text)
- Coordinate list (data table)

### Low Information
- Command input (single field)
- Settings (4 simple fields)

### Balanced
- Quick examples (visible shortcuts)
- Status bar (single line)

---

This UI is designed to be:
- **Simple** for beginners
- **Powerful** for advanced users
- **Clear** in all states
- **Responsive** to actions
- **Informative** about progress

The three-tab design keeps it organized while remaining accessible!
