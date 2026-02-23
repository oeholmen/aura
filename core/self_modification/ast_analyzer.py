"""ASTAnalyzer: Structural Self-Awareness for Aura
Provides deep analysis of Python source code via Abstract Syntax Trees.
"""
import ast
import logging
from pathlib import Path
import asyncio
from typing import Dict, List, Any, Optional, Set

logger = logging.getLogger("SelfEvolution.ASTAnalyzer")

class ASTAnalyzer:
    """Analyzes Python code to extract architectural patterns and smells."""

    def __init__(self, project_root: Optional[Path] = None):
        from core.config import config
        self.root = project_root or config.paths.project_root

    async def analyze_file(self, file_path: Path) -> Dict[str, Any]:
        """Performs a comprehensive structural audit of a file (Async)."""
        if not file_path.is_absolute():
            file_path = self.root / file_path

        try:
            source = await asyncio.to_thread(file_path.read_text, encoding='utf-8')
            tree = ast.parse(source)
        except Exception as e:
            logger.error("Failed to parse %s: %s", file_path, e)
            return {"error": str(e)}

        results = {
            "classes": self._get_classes(tree),
            "functions": self._get_functions(tree),
            "imports": self._get_imports(tree),
            "smells": self._detect_smells(tree, source),
            "complexity": self._calculate_complexity(tree)
        }
        return results

    def _get_classes(self, tree: ast.AST) -> List[Dict[str, Any]]:
        classes = []
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                classes.append({
                    "name": node.name,
                    "methods": [m.name for m in node.body if isinstance(m, ast.FunctionDef)],
                    "bases": [ast.unparse(b) if hasattr(ast, 'unparse') else "unknown" for b in node.bases],
                    "lineno": node.lineno
                })
        return classes

    def _get_functions(self, tree: ast.AST) -> List[Dict[str, Any]]:
        functions = []
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef):
                # Skip methods (already in classes)
                is_method = any(isinstance(p, ast.ClassDef) for p in self._get_parents(tree, node))
                if not is_method:
                    functions.append({
                        "name": node.name,
                        "args": [arg.arg for arg in node.args.args],
                        "is_async": isinstance(node, ast.AsyncFunctionDef),
                        "lineno": node.lineno
                    })
        return functions

    def _get_imports(self, tree: ast.AST) -> List[str]:
        imports = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    imports.append(alias.name)
            elif isinstance(node, ast.ImportFrom):
                imports.append(node.module or "")
        return list(set(imports))

    def _detect_smells(self, tree: ast.AST, source: str) -> List[Dict[str, Any]]:
        smells = []
        
        # 1. Monkey-Patching Sensor
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                if isinstance(node.func, ast.Name) and node.func.id == "setattr":
                    smells.append({
                        "type": "monkey_patch",
                        "severity": "high",
                        "message": "Dynamic attribute setting (setattr) detected. Architectural debt risk.",
                        "lineno": node.lineno
                    })
                elif isinstance(node.func, ast.Attribute) and node.func.attr == "update":
                    if isinstance(node.func.value, ast.Attribute) and node.func.value.attr == "__dict__":
                        smells.append({
                            "type": "monkey_patch",
                            "severity": "critical",
                            "message": "Manual __dict__ update detected. Dangerous architectural subversion.",
                            "lineno": node.lineno
                        })

        # 2. Async-Await & Stall Sensor
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                has_async = isinstance(node, ast.AsyncFunctionDef)
                has_await_or_sleep = False
                
                for subnode in ast.walk(node):
                    if not has_async and isinstance(subnode, ast.Await):
                        smells.append({
                            "type": "async_mismatch",
                            "severity": "high",
                            "message": f"'await' used in non-async function '{node.name}'",
                            "lineno": subnode.lineno
                        })
                    
                    if isinstance(subnode, ast.Await):
                        has_await_or_sleep = True
                    
                    # Detect common sync blockers in async def
                    if has_async and isinstance(subnode, ast.Call):
                        func_name = ast.unparse(subnode.func) if hasattr(ast, 'unparse') else ""
                        if any(blocker in func_name for blocker in ["time.sleep", "requests.get", "subprocess.run"]):
                            smells.append({
                                "type": "blocking_call",
                                "severity": "medium",
                                "message": f"Potential blocking call '{func_name}' in async function '{node.name}'",
                                "lineno": subnode.lineno
                            })
                        if "asyncio.sleep" in func_name:
                            has_await_or_sleep = True

                # 3. Deadlock Sensor (Nested Locks)
                # Check for nested 'with self._lock' blocks
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    lock_stack = []
                    for sub in ast.walk(node):
                        if isinstance(sub, ast.With):
                            for item in sub.items:
                                lock_name = ast.unparse(item.context_expr) if hasattr(ast, 'unparse') else ""
                                if "lock" in lock_name.lower():
                                    if lock_name in lock_stack:
                                        smells.append({
                                            "type": "deadlock_risk",
                                            "severity": "critical",
                                            "message": f"Recursive/Nested lock acquisition detected for '{lock_name}' in '{node.name}'.",
                                            "lineno": sub.lineno
                                        })
                                    lock_stack.append(lock_name)
                                    # We don't easily know when it ends in a walk, but nested 'with' in body is the trigger
                                    for child in ast.walk(sub):
                                        if child != sub and isinstance(child, ast.With):
                                             child_lock = ast.unparse(child.items[0].context_expr) if hasattr(ast, 'unparse') else ""
                                             if child_lock == lock_name:
                                                  smells.append({
                                                        "type": "deadlock_risk",
                                                        "severity": "critical",
                                                        "message": f"Nested acquisition of SAME lock '{lock_name}' in '{node.name}'.",
                                                        "lineno": child.lineno
                                                  })

        # 4. Resource Leak Sensor
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                if isinstance(node.func, ast.Name) and node.func.id == "open":
                    # Check if it's inside a 'with' statement
                    is_in_with = False
                    parent = self._get_parents(tree, node)
                    if any(isinstance(p, ast.With) for p in parent):
                        is_in_with = True
                    
                    if not is_in_with:
                        smells.append({
                            "type": "resource_leak",
                            "severity": "medium",
                            "message": "Unmanaged 'open()' call detected. Use 'with' statement for resource safety.",
                            "lineno": node.lineno
                        })

        return smells

    def _calculate_complexity(self, tree: ast.AST) -> Dict[str, int]:
        """Calculates basic cyclomatic complexity equivalents."""
        complexity = {}
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                score = 1
                for sub in ast.walk(node):
                    if isinstance(sub, (ast.If, ast.For, ast.While, ast.And, ast.Or, ast.ExceptHandler)):
                        score += 1
                complexity[node.name] = score
        return complexity

    def _get_parents(self, tree: ast.AST, target_node: ast.AST) -> List[ast.AST]:
        """Helper to find parent nodes for context."""
        parents = []
        for node in ast.walk(tree):
            for child in ast.iter_child_nodes(node):
                if child == target_node:
                    parents.append(node)
                    parents.extend(self._get_parents(tree, node))
        return parents

    async def map_repository(self) -> Dict[str, Any]:
        """Scans the entire core codebase to build an architectural map (Async)."""
        repo_map = {}
        core_dir = self.root / "core"
        if not core_dir.exists():
            return {"error": "Core directory not found"}

        for py_file in core_dir.rglob("*.py"):
            rel_path = py_file.relative_to(self.root)
            repo_map[str(rel_path)] = await self.analyze_file(py_file)
            
        return repo_map
