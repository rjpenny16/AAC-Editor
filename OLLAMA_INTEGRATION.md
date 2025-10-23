# Ollama Integration Guide

## Overview

The TD Snap AI Assistant now uses **Ollama** for local LLM processing, replacing cloud-based API calls. This provides:

- **Privacy**: All data stays on your device
- **Offline Operation**: Works without internet connection
- **No API Costs**: Free local inference
- **Lower Latency**: Faster responses on good hardware

## Architecture

### How It Works

```
┌─────────────────────────────────────────────────────────────┐
│                    User Request                              │
│         "Add restaurants category with 15 items"             │
└─────────────────────────────────────────────────────────────┘
                             ↓
┌─────────────────────────────────────────────────────────────┐
│                  TD Snap AI Assistant                        │
│  ┌───────────────────────────────────────────────────────┐  │
│  │  1. Parse Command                                      │  │
│  │     → Send to Ollama API (localhost:11434)            │  │
│  │     → Request: Structured JSON output                 │  │
│  │     → Schema: {action, category, count}               │  │
│  └───────────────────────────────────────────────────────┘  │
│                             ↓                                │
│  ┌───────────────────────────────────────────────────────┐  │
│  │  2. Validate JSON Response                             │  │
│  │     → Check required fields exist                      │  │
│  │     → Verify data types match schema                   │  │
│  │     → Reject invalid/hallucinated outputs              │  │
│  └───────────────────────────────────────────────────────┘  │
│                             ↓                                │
│  ┌───────────────────────────────────────────────────────┐  │
│  │  3. Generate Category Items                            │  │
│  │     → Send to Ollama API                               │  │
│  │     → Request: Array of vocabulary words               │  │
│  │     → Schema: {items: [string, string, ...]}          │  │
│  └───────────────────────────────────────────────────────┘  │
│                             ↓                                │
│  ┌───────────────────────────────────────────────────────┐  │
│  │  4. Execute Automation                                 │  │
│  │     → PyAutoGUI clicks & keyboard input                │  │
│  │     → Based on recorded coordinates                    │  │
│  │     → Adds category and items to TD Snap               │  │
│  └───────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
                             ↓
┌─────────────────────────────────────────────────────────────┐
│                    TD Snap Application                       │
│         (Category and items added automatically)             │
└─────────────────────────────────────────────────────────────┘
```

## Installation & Setup

### 1. Install Ollama

**macOS / Linux:**
```bash
curl -fsSL https://ollama.com/install.sh | sh
```

**Windows:**
Download from https://ollama.com/download

**Verify Installation:**
```bash
ollama --version
```

### 2. Pull a Model

Choose a model based on your hardware:

**Recommended Models:**

| Model | Size | RAM Required | Best For |
|-------|------|--------------|----------|
| `llama3.2` | 2GB | 8GB RAM | Most users, fast & accurate |
| `llama3.1` | 4.7GB | 8GB RAM | Better quality, slower |
| `mistral` | 4.1GB | 8GB RAM | Good balance |
| `phi3` | 2.3GB | 6GB RAM | Low-end hardware |
| `qwen2.5` | 4.4GB | 8GB RAM | Alternative option |

**Pull a model:**
```bash
ollama pull llama3.2
```

### 3. Start Ollama

**Ollama runs as a service on most systems.**

To check if it's running:
```bash
ollama list
```

If not running, start it:
```bash
ollama serve
```

### 4. Configure in TD Snap AI Assistant

1. Open the app
2. Go to **Settings** tab
3. Configure:
   - **Ollama Host**: `http://localhost:11434` (default)
   - **Ollama Model**: Select from dropdown (e.g., `llama3.2`)
4. Click **Test Ollama Connection**
5. Verify you see available models

## Technical Details

### Structured JSON Output

The app uses Ollama's `format` parameter to enforce JSON schemas:

**Command Parsing Schema:**
```json
{
  "type": "object",
  "properties": {
    "action": {"type": "string"},
    "category": {"type": "string"},
    "count": {"type": "number"}
  },
  "required": ["action", "category"]
}
```

**Item Generation Schema:**
```json
{
  "type": "object",
  "properties": {
    "items": {
      "type": "array",
      "items": {"type": "string"}
    }
  },
  "required": ["items"]
}
```

### API Endpoints Used

**1. Test Connection:**
```
GET http://localhost:11434/api/tags
```
Returns list of available models.

**2. Chat Completion:**
```
POST http://localhost:11434/api/chat
Content-Type: application/json

{
  "model": "llama3.2",
  "messages": [{"role": "user", "content": "..."}],
  "stream": false,
  "format": { /* JSON schema */ },
  "options": {
    "num_predict": 500,
    "temperature": 0.7
  }
}
```

### Safety & Validation

The app implements multiple safety layers:

1. **JSON Schema Validation**: Ensures output matches expected structure
2. **Type Checking**: Verifies all fields have correct data types
3. **Required Field Checking**: Rejects incomplete responses
4. **Error Handling**: Graceful fallback on invalid outputs
5. **No Execution of Arbitrary Code**: Only predefined automation actions
6. **Localhost Only**: Ollama API not exposed to public internet

### Security Considerations

**IMPORTANT:**

- Ollama API should ONLY be accessible on `localhost:11434`
- Never expose Ollama to public internet without authentication
- Known vulnerability: Open Ollama servers can be exploited
- Use firewall rules to block external access to port 11434
- For remote access, use SSH tunnel or VPN, not port forwarding

**Secure Remote Access (if needed):**
```bash
# SSH tunnel from remote machine
ssh -L 11434:localhost:11434 user@your-machine
```

## Troubleshooting

### Connection Errors

**Error: "Cannot connect to Ollama"**

Solutions:
1. Check if Ollama is running: `ollama list`
2. Verify port 11434 is open: `curl http://localhost:11434/api/tags`
3. Restart Ollama service
4. Check firewall settings

### Model Not Found

**Error: "Model not found"**

Solutions:
1. List installed models: `ollama list`
2. Pull the model: `ollama pull llama3.2`
3. Update model name in Settings tab

### Slow Performance

**LLM responses are slow**

Solutions:
1. Use a smaller model (e.g., `phi3` instead of `llama3.1`)
2. Ensure sufficient RAM available
3. Close other applications
4. Consider GPU acceleration (Ollama supports CUDA/Metal)

### Invalid JSON Responses

**Error: "Could not parse JSON"**

Solutions:
1. Update to latest Ollama version
2. Try a different model (some are better at structured output)
3. Check logs for actual response content
4. Ensure model supports structured outputs

## Performance Comparison

| Operation | Cloud API (Claude) | Local Ollama (llama3.2) |
|-----------|-------------------|-------------------------|
| Command Parse | 1-2 seconds | 2-5 seconds |
| Generate 10 items | 2-3 seconds | 5-10 seconds |
| Network required | Yes | No |
| Data leaves device | Yes | No |
| API cost | Paid | Free |

## Model Recommendations

**For most users:**
- `llama3.2` - Best balance of speed and quality

**For better quality (slower):**
- `llama3.1:8b` - More accurate, requires more RAM

**For low-end hardware:**
- `phi3` - Smaller, faster, less accurate
- `llama3.2:1b` - Smallest option

**To switch models:**
```bash
ollama pull <model-name>
```
Then update in Settings tab.

## API Reference

### Python Code Example

```python
import requests
import json

def call_ollama(prompt, schema=None):
    payload = {
        "model": "llama3.2",
        "messages": [{"role": "user", "content": prompt}],
        "stream": False,
        "options": {
            "num_predict": 500,
            "temperature": 0.7
        }
    }

    if schema:
        payload["format"] = schema

    response = requests.post(
        "http://localhost:11434/api/chat",
        json=payload,
        timeout=60
    )

    if response.status_code == 200:
        return response.json()['message']['content']
    else:
        raise Exception(f"Error: {response.status_code}")

# Example usage
schema = {
    "type": "object",
    "properties": {
        "category": {"type": "string"},
        "items": {
            "type": "array",
            "items": {"type": "string"}
        }
    },
    "required": ["category", "items"]
}

result = call_ollama("Generate 5 food items", schema)
print(json.loads(result))
```

## Additional Resources

- **Ollama Documentation**: https://github.com/ollama/ollama/blob/main/docs/api.md
- **Structured Outputs Guide**: https://ollama.com/blog/structured-outputs
- **Model Library**: https://ollama.com/library
- **TD Snap AAC Software**: https://www.tobiidynavox.com/

## Support

For issues with:
- **Ollama**: https://github.com/ollama/ollama/issues
- **TD Snap AI Assistant**: Check project repository
- **TD Snap Software**: Contact Tobii Dynavox support
