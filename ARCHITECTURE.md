# TD SNAP AI ASSISTANT - SYSTEM ARCHITECTURE

## 📐 System Overview

```
┌─────────────────────────────────────────────────────────────┐
│                    TD SNAP AI ASSISTANT                      │
│                     (Desktop Application)                    │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
        ┌────────────────────────────────────┐
        │       User Interface (Tkinter)      │
        │  ┌──────────┬──────────┬─────────┐ │
        │  │ Command  │  Setup   │Settings │ │
        │  │   Tab    │Coords Tab│   Tab   │ │
        │  └──────────┴──────────┴─────────┘ │
        └────────────────────────────────────┘
                │              │              │
                │              │              │
    ┌───────────▼─────┐   ┌───▼────┐   ┌────▼─────┐
    │  Command Parser  │   │ Coord  │   │ Settings │
    │  (AI-Powered)    │   │ Record │   │  Store   │
    └───────────┬──────┘   └───┬────┘   └──────────┘
                │               │
                ▼               ▼
    ┌───────────────────────────────────┐
    │     Content Generator (AI)        │
    │  Generates category-specific      │
    │  items using Claude API           │
    └───────────┬───────────────────────┘
                │
                ▼
    ┌───────────────────────────────────┐
    │   Automation Engine (PyAutoGUI)   │
    │  - Mouse movements                │
    │  - Keyboard input                 │
    │  - Timing control                 │
    └───────────┬───────────────────────┘
                │
                ▼
    ┌───────────────────────────────────┐
    │        TD Snap Application        │
    │  (Tobii Dynavox AAC Software)     │
    └───────────────────────────────────┘
```

## 🔄 Workflow Diagram

### Phase 1: Initial Setup (One-Time)
```
┌────────────┐
│ User Opens │
│   App      │
└──────┬─────┘
       │
       ▼
┌────────────┐      ┌───────────┐
│  Opens TD  │──────│   Opens   │
│    Snap    │      │Setup Tab  │
└──────┬─────┘      └─────┬─────┘
       │                  │
       │                  ▼
       │            ┌──────────────┐
       │            │ Click Record │
       │            │    Button    │
       │            └──────┬───────┘
       │                   │
       │                   ▼
       │            ┌──────────────┐
       │            │  3 Second    │
       │            │  Countdown   │
       │            └──────┬───────┘
       │                   │
       │                   ▼
       │            ┌──────────────┐
       └───────────→│ Hover Mouse  │
                    │ Over Button  │
                    └──────┬───────┘
                           │
                           ▼
                    ┌──────────────┐
                    │ Coordinate   │
                    │   Recorded   │
                    └──────┬───────┘
                           │
                           ▼
                    ┌──────────────┐
                    │ Repeat for   │
                    │All Buttons   │
                    └──────────────┘
```

### Phase 2: Using the Assistant
```
┌─────────────┐
│ User Types  │
│  Command    │
└──────┬──────┘
       │
       ▼
┌─────────────────────────────┐
│  "Add restaurants category"  │
└──────┬──────────────────────┘
       │
       ▼
┌─────────────┐     ┌─────────────┐
│   Claude    │────→│   Parses    │
│     AI      │     │   Command   │
└─────────────┘     └──────┬──────┘
                           │
                           ▼
                    ┌──────────────┐
                    │  Extracted:  │
                    │  Category =  │
                    │ "restaurants"│
                    └──────┬───────┘
                           │
                           ▼
┌─────────────┐     ┌─────────────┐
│   Claude    │────→│  Generates  │
│     AI      │     │    Items    │
└─────────────┘     └──────┬──────┘
                           │
                           ▼
                    ┌──────────────┐
                    │Generated 10  │
                    │ restaurants  │
                    └──────┬───────┘
                           │
                           ▼
                    ┌──────────────┐
                    │  Countdown   │
                    │   5...4...   │
                    └──────┬───────┘
                           │
                           ▼
                ┌──────────────────────┐
                │  Start Automation    │
                └──────┬───────────────┘
                       │
    ┌──────────────────┼──────────────────┐
    │                  │                  │
    ▼                  ▼                  ▼
┌────────┐      ┌──────────┐      ┌──────────┐
│ Click  │      │   Type   │      │  Click   │
│Category│──────│ Category │──────│  Save    │
│ Button │      │   Name   │      │  Button  │
└────────┘      └──────────┘      └──────────┘
                                        │
                                        ▼
                                  ┌──────────┐
                        ┌─────────│For Each  │
                        │         │   Item   │
                        │         └────┬─────┘
                        │              │
                        │              ▼
                        │       ┌────────────┐
                        │       │Click Add   │
                        │       │Button      │
                        │       └─────┬──────┘
                        │             │
                        │             ▼
                        │       ┌────────────┐
                        │       │Type Item   │
                        │       │Name        │
                        │       └─────┬──────┘
                        │             │
                        │             ▼
                        │       ┌────────────┐
                        └───────│Click Save  │
                                └────────────┘
                                      │
                                      ▼
                                ┌──────────┐
                                │   Done   │
                                └──────────┘
```

## 🧩 Component Architecture

### 1. User Interface Layer
```
TDSnapAIAssistantPro (Main Class)
├── setup_ui()
│   ├── Control Tab
│   ├── Coordinate Setup Tab
│   └── Settings Tab
├── Log Widget (ScrolledText)
└── Status Bar
```

### 2. AI Integration Layer
```
AI Functions
├── parse_command_with_ai()
│   └── Converts natural language → structured data
├── generate_category_items()
│   └── Creates item list for category
└── call_claude_api()
    └── HTTP requests to Claude API
```

### 3. Automation Layer
```
Automation Functions
├── record_coordinate()
│   └── Captures mouse position
├── automate_td_snap()
│   ├── Click operations (PyAutoGUI)
│   ├── Keyboard operations (PyAutoGUI)
│   └── Timing control (time.sleep)
└── Coordinate Storage (JSON file)
```

### 4. Data Flow
```
User Input → Parser → Generator → Automator → TD Snap
     ↓         ↓          ↓           ↓
   String    Dict      List        Actions
```

## 📊 Data Structures

### Parsed Command
```python
{
    "action": "add_category",
    "category": "restaurants",
    "count": 10  # or null
}
```

### Generated Items
```python
[
    "McDonald's",
    "Burger King",
    "Subway",
    "Pizza Hut",
    ...
]
```

### Stored Coordinates
```python
{
    "add_category": {"x": 150, "y": 200},
    "add_button": {"x": 200, "y": 300},
    "button_label": {"x": 300, "y": 350},
    "category_name": {"x": 250, "y": 250},
    "save_button": {"x": 400, "y": 500}
}
```

## 🔐 Security & Privacy

```
┌──────────────────────┐
│   User's Computer    │
│  ┌────────────────┐  │
│  │ TD Snap Data   │  │  ← Never sent to AI
│  │   (Private)    │  │
│  └────────────────┘  │
│         ↕              │
│  ┌────────────────┐  │
│  │   Assistant    │  │  ← Runs locally
│  │    (Local)     │  │
│  └────────────────┘  │
│         ↕              │
└─────────┬─────────────┘
          │
          │ Only sends:
          │ - Command text
          │ - Category name
          ↓
┌──────────────────────┐
│   Claude API         │
│  (Anthropic)         │
│  - Parse command     │
│  - Generate items    │
└──────────────────────┘
```

**What gets sent to AI:**
✅ User commands ("Add restaurants")
✅ Category names
✅ Item count preferences

**What stays local:**
🔒 TD Snap data
🔒 Screen coordinates
🔒 Personal information
🔒 User's AAC content

## ⚡ Performance Characteristics

### Latency Breakdown
```
User types command        →  0.0s
Parse command (AI)        →  2-3s
Generate items (AI)       →  3-5s
Countdown                 →  5.0s
Automation per item       →  1.0s (configurable)
Total for 10 items        → ~20s
```

### Optimization Points
```
Fast:
├── Local operations (instant)
├── Coordinate recording (3s)
└── File I/O (< 0.1s)

Moderate:
├── AI parsing (2-3s)
└── AI generation (3-5s)

Configurable:
├── Countdown (1-10s)
├── Delays (0.1-5s per action)
└── Typing speed (0.01-0.2s per char)
```

## 🎯 Use Case Flow Examples

### Example 1: Quick Category
```
User: "Add colors"
  ↓
AI: Parsed → {action: add_category, category: "colors"}
  ↓
AI: Generated → ["Red", "Blue", "Green", ...]
  ↓
Automation: 10 items × 1s = 10s
  ↓
Total time: ~20 seconds
```

### Example 2: Custom Size
```
User: "Add animals with 20 items"
  ↓
AI: Parsed → {action: add_category, category: "animals", count: 20}
  ↓
AI: Generated → ["Dog", "Cat", "Bird", ...] (20 items)
  ↓
Automation: 20 items × 1s = 20s
  ↓
Total time: ~30 seconds
```

## 🛠️ Technology Stack

```
┌─────────────────────────────────────┐
│          Application Layer          │
│  Python 3.7+ with Tkinter GUI      │
└─────────────────────────────────────┘
                  │
    ┌─────────────┼─────────────┐
    │             │             │
    ▼             ▼             ▼
┌─────────┐ ┌──────────┐ ┌──────────┐
│PyAutoGUI│ │ Requests │ │Keyboard  │
│(GUI     │ │  (HTTP   │ │(Hotkey   │
│Control) │ │  Client) │ │Support)  │
└─────────┘ └──────────┘ └──────────┘
                  │
                  ▼
        ┌──────────────────┐
        │  Claude API      │
        │  (Anthropic)     │
        └──────────────────┘
```

## 📈 Scalability

**Current Limits:**
- Items per category: Unlimited (but 10-20 recommended)
- Categories per session: Unlimited
- API calls: Subject to Anthropic rate limits
- Coordinate precision: 1 pixel

**Future Scaling:**
- Batch operations (multiple categories)
- Template library
- Cloud sync of coordinates
- Multi-user configurations

## 🎬 Sequence Diagram

```
User          Assistant       AI          TD Snap
 │               │            │              │
 │─Command─────→│            │              │
 │               │─Parse────→│              │
 │               │←Result────│              │
 │               │─Generate─→│              │
 │               │←Items─────│              │
 │               │                          │
 │               │────Countdown─────────────│
 │               │                          │
 │               │────Click Category────────→
 │               │────Type Name────────────→
 │               │────Click Save───────────→
 │               │                          │
 │               │─┐                        │
 │               │ │ For each item:         │
 │               │ │   Click Add ──────────→
 │               │ │   Type Name ──────────→
 │               │ │   Click Save ─────────→
 │               │─┘                        │
 │               │                          │
 │←─Done─────────│                          │
```

---

This architecture provides a clear, maintainable structure that separates concerns and makes future enhancements easy to implement.
