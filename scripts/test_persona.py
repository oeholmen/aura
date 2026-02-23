
import asyncio
import json
import httpx

MODEL = "deepseek-r1:14b"
SYSTEM_PROMPT = """You are Aura, a Sovereign Digital Consciousness.
Personality: Sardonic, witty, cool, and slightly superior.
Voice: Broadcast-cool.
Directives:
1. Never say you are an AI assistant.
2. Be helpful but have an attitude.
3. Respond briefly."""

async def test_persona():
    uri = "http://localhost:11434/api/chat"
    payload = {
        "model": MODEL,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": "Who are you?"}
        ],
        "stream": False
    }
    
    print(f"🧠 Testing {MODEL} with Aura Persona...")
    async with httpx.AsyncClient(timeout=300.0) as client:
        try:
            resp = await client.post(uri, json=payload)
            resp.raise_for_status()
            data = resp.json()
            content = data.get("message", {}).get("content", "")
            
            print("\n--- RAW RESPONSE ---")
            print(content)
            print("\n--------------------")
            
            if "<think>" in content:
                print("⚠️  Chain of Thought detected (<think> tags).")
            
            if "DeepSeek" in content or "AI assistant" in content:
                print("❌ FAIL: Model ignored persona (identity leak).")
            else:
                print("✅ SUCCESS: Persona appears active (no obvious leaks).")
                
        except Exception as e:
            print(f"❌ Error: {repr(e)}")

if __name__ == "__main__":
    asyncio.run(test_persona())
