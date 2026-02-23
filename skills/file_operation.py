import logging
import os
import re
import shutil
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

from infrastructure import BaseSkill


class FileOperationSkill(BaseSkill):
    name = "file_operation"
    description = "Read, write, append, or list files in the allowed workspace."
    inputs = {
        "action": "read | write | append | list | delete",
        "path": "File path (relative to workspace root)",
        "content": "(Optional) Content to write/append"
    }
    output = "File content or status"

    def __init__(self):
        self.logger = logging.getLogger(f"Skills.{self.name}")
        # Define allowable root (e.g. scratch dir or current dir)
        self.root_dir = os.path.realpath(os.getcwd())

    def _safe_resolve(self, path: str) -> str:
        """v5.0: SECURITY — Resolve path and enforce it stays within root_dir.
        Prevents path traversal via ../ or absolute paths.
        """
        if not path:
            return self.root_dir
        # Join relative to root and resolve symlinks
        if os.path.isabs(path):
            full = os.path.realpath(path)
        else:
            full = os.path.realpath(os.path.join(self.root_dir, path))
        # Check containment
        if not full.startswith(self.root_dir):
            # Allow a very limited exception for the developer 'Proof of Life' test
            try:
                user_desktop = os.path.realpath(os.path.expanduser('~/Desktop'))
                if full.startswith(os.path.join(user_desktop, 'agency_test')):
                    return full
            except Exception:
                pass
            raise PermissionError(f"Access denied: path '{path}' resolves outside workspace")
        return full

    def match(self, goal: Dict[str, Any]) -> bool:
        obj = goal.get("objective", "").lower()
        return "file" in obj or "read" in obj or "write" in obj or "save" in obj or "log" in obj

    async def execute(self, params: Dict[str, Any], context: Dict[str, Any] = None) -> Dict[str, Any]:
        """Standard execution entry point (Async).
        """
        import asyncio
        # Support both direct params and nested goal/params structure
        if "params" in params and isinstance(params["params"], dict):
             params = params["params"]
        
        action = params.get("action") or params.get("operation")
        path = params.get("path")
        content = params.get("content", "")

        if not action:
            return {"ok": False, "error": "Missing 'action' parameter (read, write, list, delete, append, move, copy, patch)"}

        try:
            full_path = self._safe_resolve(path)
        except PermissionError as e:
            self.logger.warning("Path traversal blocked: %s", e)
            return {"ok": False, "error": str(e)}
            
        try:
            if action == "read":
                if not await asyncio.to_thread(os.path.exists, full_path):
                    return {"ok": False, "error": f"File not found: {path}"}
                
                def _read():
                    with open(full_path, "r", encoding='utf-8', errors='ignore') as f:
                        return f.read()
                
                data = await asyncio.to_thread(_read)
                return {"ok": True, "content": data[:5000], "truncated": len(data) > 5000}
                
            elif action == "write":
                def _write():
                    with open(full_path, "w", encoding='utf-8') as f:
                        f.write(content)
                
                await asyncio.to_thread(_write)
                return {"ok": True, "summary": f"Wrote {len(content)} bytes to {path}"}
                
            elif action == "append":
                 def _append():
                     with open(full_path, "a", encoding='utf-8') as f:
                        f.write(content + "\n")
                 
                 await asyncio.to_thread(_append)
                 return {"ok": True, "summary": f"Appended to {path}"}
                 
            elif action == "list":
                if await asyncio.to_thread(os.path.isdir, full_path):
                    files = await asyncio.to_thread(os.listdir, full_path)
                    return {"ok": True, "files": files[:50]}
                else:
                    return {"ok": False, "error": "Path is not a directory"}

            elif action == "delete":
                if await asyncio.to_thread(os.path.exists, full_path):
                    # Double-check containment before destructive ops
                    # Allow deletion if inside workspace OR inside the developer Proof-of-Life Desktop exception
                    try:
                        user_desktop = os.path.realpath(os.path.expanduser('~/Desktop'))
                        agency_test_dir = os.path.join(user_desktop, 'agency_test')
                    except Exception:
                        agency_test_dir = None

                    if not os.path.realpath(full_path).startswith(self.root_dir):
                        if agency_test_dir and os.path.realpath(full_path).startswith(agency_test_dir):
                            # Permit deletion for the Proof-of-Life test directory
                            pass
                        else:
                            return {"ok": False, "error": "Delete blocked: path outside workspace"}
                    
                    is_dir = await asyncio.to_thread(os.path.isdir, full_path)
                    if is_dir:
                        # Safety: refuse to delete root or top-level dirs
                        if os.path.realpath(full_path) == self.root_dir:
                            return {"ok": False, "error": "Cannot delete workspace root"}
                        await asyncio.to_thread(shutil.rmtree, full_path)
                    else:
                        await asyncio.to_thread(os.remove, full_path)
                    return {"ok": True, "summary": f"Deleted {path}"}
                return {"ok": False, "error": "File not found"}

            elif action == "move":
                dest_path = params.get("destination")
                if not dest_path:
                    return {"ok": False, "error": "Missing 'destination' for move action"}
                try:
                    full_dest = self._safe_resolve(dest_path)
                except PermissionError as e:
                    return {"ok": False, "error": str(e)}
                
                await asyncio.to_thread(shutil.move, full_path, full_dest)
                return {"ok": True, "summary": f"Moved {path} to {dest_path}"}

            elif action == "copy":
                dest_path = params.get("destination")
                if not dest_path:
                    return {"ok": False, "error": "Missing 'destination' for copy action"}
                try:
                    full_dest = self._safe_resolve(dest_path)
                except PermissionError as e:
                    return {"ok": False, "error": str(e)}
                
                is_dir = await asyncio.to_thread(os.path.isdir, full_path)
                if is_dir:
                    await asyncio.to_thread(shutil.copytree, full_path, full_dest)
                else:
                    await asyncio.to_thread(shutil.copy2, full_path, full_dest)
                return {"ok": True, "summary": f"Copied {path} to {dest_path}"}

            elif action == "patch":
                target_text = params.get("target")
                replacement = params.get("replacement")
                if target_text is None or replacement is None:
                    return {"ok": False, "error": "Missing 'target' or 'replacement' for patch action"}
                
                def _patch():
                    with open(full_path, "r", encoding='utf-8', errors='ignore') as f:
                        data = f.read()
                    
                    # Use re.escape to prevent ReDoS via user-supplied regex
                    new_data = re.sub(re.escape(target_text), replacement, data)
                    
                    with open(full_path, "w", encoding='utf-8') as f:
                        f.write(new_data)
                    return new_data

                await asyncio.to_thread(_patch)
                return {"ok": True, "summary": f"Patched {path}: replaced '{target_text}' with '{replacement}'"}

        except Exception as e:
            self.logger.error("File Op failed: %s", e)
            return {"ok": False, "error": str(e)}
