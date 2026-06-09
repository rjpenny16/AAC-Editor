"""
TD Snap AI Assistant - Demo Mode
This script demonstrates the AI capabilities without requiring TD Snap
"""

import json
import requests

def call_claude_api(prompt: str, max_tokens: int = 1000) -> str:
    """Call the Claude API"""
    try:
        print("🤖 Calling AI...")
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
            print(f"❌ API Error: {response.status_code}")
            return None
            
    except Exception as e:
        print(f"❌ API call failed: {str(e)}")
        return None

def parse_command(command: str):
    """Parse a natural language command"""
    print(f"\n{'='*60}")
    print(f"📝 Your command: '{command}'")
    print(f"{'='*60}")
    
    prompt = f"""Parse this command for a TD Snap AAC app automation tool. 
The user wants to add categories and items to TD Snap.

User command: "{command}"

Analyze the command and respond with ONLY a JSON object (no other text, no markdown, no code blocks):
{{
    "action": "add_category",
    "category": "the category name",
    "count": number of items (if specified, otherwise null)
}}

RESPOND ONLY WITH VALID JSON."""

    response = call_claude_api(prompt, max_tokens=200)
    
    if not response:
        return None
    
    # Clean up the response
    response_text = response.strip()
    if response_text.startswith('```'):
        lines = response_text.split('\n')
        response_text = '\n'.join(lines[1:-1])
    
    try:
        parsed = json.loads(response_text)
        print("\n✅ AI understood your command!")
        print(f"   Action: {parsed['action']}")
        print(f"   Category: {parsed['category']}")
        if parsed.get('count'):
            print(f"   Item count: {parsed['count']}")
        return parsed
    except:
        print("❌ Could not parse AI response")
        return None

def generate_items(category: str, count: int = 10):
    """Generate items for a category"""
    print(f"\n🎨 Generating {count} items for '{category}'...")
    
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

RESPOND ONLY WITH A VALID JSON ARRAY."""

    response = call_claude_api(prompt, max_tokens=500)
    
    if not response:
        return []
    
    # Clean up the response
    response_text = response.strip()
    if response_text.startswith('```'):
        lines = response_text.split('\n')
        response_text = '\n'.join(lines[1:-1])
        
    try:
        items = json.loads(response_text)
        print(f"\n✅ Generated {len(items)} items:")
        for i, item in enumerate(items, 1):
            print(f"   {i:2d}. {item}")
        return items
    except:
        print("❌ Could not parse AI response")
        return []

def demo():
    """Run a demonstration"""
    print("\n" + "="*60)
    print("   TD SNAP AI ASSISTANT - DEMO MODE")
    print("="*60)
    print("\nThis demo shows what the AI can do WITHOUT TD Snap")
    print("It will parse your commands and generate category items")
    print("\nExamples to try:")
    print("  - Add restaurants category")
    print("  - Add colors")
    print("  - Create animals with 15 items")
    print("  - Add family members")
    print("\nType 'quit' to exit")
    print("="*60)
    
    while True:
        print("\n")
        command = input("💬 Enter a command (or 'quit'): ").strip()
        
        if command.lower() in ['quit', 'exit', 'q']:
            print("\n👋 Thanks for trying the demo!")
            break
            
        if not command:
            continue
        
        # Parse the command
        parsed = parse_command(command)
        
        if not parsed:
            print("\n⚠️  Try rephrasing your command")
            continue
        
        # Generate items
        count = parsed.get('count', 10)
        items = generate_items(parsed['category'], count)
        
        if items:
            print(f"\n🎯 SUCCESS!")
            print(f"In the full app, these {len(items)} items would be")
            print(f"automatically added to TD Snap in the '{parsed['category']}' category")

if __name__ == "__main__":
    demo()
