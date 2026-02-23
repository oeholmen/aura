import asyncio
import websockets
import json
import logging

logging.basicConfig(level=logging.INFO)

async def test():
    try:
        async with websockets.connect("ws://localhost:8000/ws", ping_interval=None, ping_timeout=None) as ws:
            # Auth
            await ws.send(json.dumps({"type": "auth", "token": ""}))
            auth_resp = await ws.recv()
            print("Auth:", auth_resp)
            
            # Send action request
            msg = {"type": "user_message", "content": "evaluate this python code: print(2+2)"}
            await ws.send(json.dumps(msg))
            
            print("Waiting for response...")
            while True:
                resp = await ws.recv()
                print("Received:", resp)
                data = json.loads(resp)
                if data.get("type") == "chat_response":
                    break
    except Exception as e:
        print("Error:", e)

asyncio.run(test())
