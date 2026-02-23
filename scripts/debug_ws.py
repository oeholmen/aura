import asyncio
import websockets
import json
import os

async def test_chat():
    uri = "ws://localhost:8000/ws/chat"
    # We might need authentication if enabled
    # But usually localhost is allowed if AURA_ALLOW_LOCALHOST_ONLY=1
    
    print(f"Connecting to {uri}...")
    try:
        async with websockets.connect(uri) as websocket:
            print("Connected!")
            
            msg = {"type": "message", "message": "Hello Aura"}
            await websocket.send(json.dumps(msg))
            print(f"Sent: {msg}")
            
            while True:
                try:
                    response = await asyncio.wait_for(websocket.recv(), timeout=10.0)
                    data = json.loads(response)
                    print(f"Received: {data}")
                    if data.get("type") == "done":
                        print("Stream finished (done received).")
                        break
                    
                    if data.get("type") == "done":
                        break
                    if data.get("type") == "error":
                        print("Error received!")
                        break
                except asyncio.TimeoutError:
                    print("Timeout waiting for response.")
                    break
                except websockets.exceptions.ConnectionClosed as e:
                    print(f"Connection closed by server: {e.code} {e.reason}")
                    break
                except Exception as e:
                    print(f"Error in loop: {type(e)} {e}")
                    break
                    
    except Exception as e:
        print(f"Connection failed: {type(e)} {e}")

if __name__ == "__main__":
    asyncio.run(test_chat())
