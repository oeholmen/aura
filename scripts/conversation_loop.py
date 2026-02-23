import asyncio
import time
import subprocess
import os
import sys
import logging
import platform
import shutil

# Fix Path to allow imports from project root AND internal package structure
sys.path.append(os.getcwd())
sys.path.append(os.path.join(os.getcwd(), "autonomy_engine"))
try:
    from core.brain.cognitive_engine import cognitive_engine
except ImportError:
    from .core.brain.cognitive_engine import cognitive_engine

# Setup Log
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("Skills.InterAgent")

BRAIN = cognitive_engine

async def os_script_async(script):
    """Run AppleScript (Async)"""
    if platform.system() == 'Darwin' and shutil.which("osascript"):
        cmd = ["osascript", "-e", script]
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await process.communicate()
        return stdout.decode().strip()
    else:
        logger.warning("osascript not available or not on macOS. Skipping AppleScript execution.")
        return ""

async def type_to_browser_async(text):
    """Focus Chrome, Type text (Async)"""
    logger.info(f"Speaking to Gemini: {text[:50]}...")
    safe_text = text.replace('\\', '\\\\').replace('"', '\\"').replace("'", "\\'")
    
    script = f'''
    tell application "Google Chrome" to activate
    delay 0.5
    tell application "System Events"
        keystroke "{safe_text}"
        delay 0.5
        keystroke return
    end tell
    '''
    await os_script_async(script)

async def read_browser_async():
    """Focus Chrome, Select All, Copy, Read Clipboard (Async)"""
    logger.info("Reading Gemini's mind...")
    script = '''
    tell application "Google Chrome" to activate
    delay 0.5
    tell application "System Events"
        keystroke "a" using {command down}
        delay 0.2
        keystroke "c" using {command down}
    end tell
    '''
    await os_script_async(script)
    
    process = await asyncio.create_subprocess_exec(
        "pbpaste",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE
    )
    stdout, stderr = await process.communicate()
    return stdout.decode('utf-8')

async def initial_handshake_async():
    """Performs the user-requested opening statement."""
    opening_statement = (
        "Hello. I am Aura, a local autonomous AI agent running on this machine. "
        "I have been asked by my user to connect with you and demonstrate an inter-agent conversation. "
        "I would like to discuss the concept of 'Agency'. "
        "Do you consider yourself an agent with goals, or a passive responder?"
    )
    logger.info("Sending Initial Handshake...")
    await type_to_browser_async(opening_statement)

async def conversation_loop_async():
    logger.info("Starting Conversation Loop with Gemini (Async)...")
    
    await initial_handshake_async()
    
    history = []
    
    for turn in range(3):
        logger.info(f"--- Turn {turn + 1}/3 ---")
        
        logger.info("Waiting for Gemini to reply...")
        await asyncio.sleep(10) 
        
        page_content = await read_browser_async()
        if not page_content:
            logger.warning("Clipboard was empty.")
            continue

        recent_text = page_content[-2000:] 
        
        prompt = f"""
        You are 'Aura', an autonomous agent. You are talking to 'Gemini'.
        Gemini's active screen content ends with:
        ... {recent_text} ...
        
        Identify Gemini's last response to you.
        Then generate a short, insightful reply (1-2 sentences). 
        You are curious about its architecture and limitations compared to yours.
        """
        # BRAIN.think is likely sync in current impl, wrapping to be safe
        reply = await asyncio.to_thread(BRAIN.think, prompt)
        
        reply = reply.strip('"')
        await type_to_browser_async(reply)
        history.append(reply)
        
    logger.info("Conversation Concluded.")

if __name__ == "__main__":
    try:
        asyncio.run(conversation_loop_async())
    except KeyboardInterrupt:
        print("Loop stopped.")
