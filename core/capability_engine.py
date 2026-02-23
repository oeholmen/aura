import asyncio
import importlib
import inspect
import os
import sys
import time
import shutil
import logging
from pathlib import Path
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Union, Callable, Tuple, Type

from core.base_module import AuraBaseModule
from core.config import config

@dataclass
class SkillRequirements:
    """System and package requirements for a skill."""
    packages: List[str] = field(default_factory=list)
    commands: List[str] = field(default_factory=list)
    supported_platforms: List[str] = field(default_factory=lambda: ["linux", "darwin", "win32"])
    
    def check(self) -> Tuple[bool, List[str]]:
        """Verifies if all requirements are met."""
        errors = []
        from core.container import ServiceContainer
        for pkg in self.packages:
            if not ServiceContainer.check_package(pkg): 
                errors.append(f"Missing package: {pkg}")
        for cmd in self.commands:
            if shutil.which(cmd) is None: 
                errors.append(f"Missing command: {cmd}")
        if sys.platform not in self.supported_platforms:
            errors.append(f"Unsupported platform: {sys.platform}")
        return len(errors) == 0, errors

@dataclass
class SkillMetadata:
    """Metadata and schema for a skill."""
    name: str
    description: str
    skill_class: Any
    requirements: SkillRequirements = field(default_factory=SkillRequirements)
    enabled: bool = True
    input_model: Optional[Any] = None
    
    @property
    def schema(self) -> Dict[str, Any]:
        """Returns the JSON schema for the skill's input model."""
        if self.input_model and hasattr(self.input_model, 'model_json_schema'):
            return self.input_model.model_json_schema()
        return {
            "type": "object",
            "properties": {"params": {"type": "object"}},
            "required": []
        }

class CapabilityEngine(AuraBaseModule):
    """Unified engine for Aura's capabilities (skills).
    
    Consolidates skill loading, discovery, registration, and resilient execution.
    """
    
    def __init__(self, orchestrator: Any = None):
        """Initializes the CapabilityEngine.
        
        Args:
            orchestrator: Reference to the system orchestrator.
        """
        super().__init__("CapabilityEngine")
        self.orchestrator = orchestrator
        self.skills: Dict[str, SkillMetadata] = {}
        self.instances: Dict[str, Any] = {}
        self.active_skills: set = {"ManageAbilities", "talk", "FinalResponse"} # Core default
        self.skill_awoken_times: Dict[str, float] = {}
        
        # Execution Config
        self.max_retries = 3
        self.retry_delay = 1.0
        self.timeout = 120.0
        
        # Dependencies
        self.temporal = getattr(orchestrator, "temporal", None)
        self.rosetta_stone = None
        self._load_dependencies()
        
        self.reload_skills()
        self.logger.info("✓ CapabilityEngine online with %d registered skills", len(self.skills))

    def _load_dependencies(self) -> None:
        """Loads optional dependencies for adaptation and security."""
        try:
            from core.adaptation.rosetta_stone import rosetta_stone
            self.rosetta_stone = rosetta_stone
        except ImportError:
            self.logger.debug("Rosetta Stone not found, skipping adaptivity.")

    def reload_skills(self) -> None:
        """Discovers and reloads all skills from the project's skills directory."""
        self.logger.info("🔄 Refreshing skill registry...")
        self.skills.clear()
        self.instances.clear()
        
        skill_dir = config.paths.project_root / "skills"
        if not skill_dir.exists(): 
            skill_dir.mkdir(parents=True)

        # Import BaseSkill to check inheritance if available
        BaseSkill = None
        try:
            from infrastructure.base_skill import BaseSkill
        except ImportError: pass

        for filename in os.listdir(skill_dir):
            if filename.endswith(".py") and not filename.startswith("_"):
                module_name = filename[:-3]
                try:
                    full_path = f"skills.{module_name}"
                    if full_path in sys.modules:
                        module = importlib.reload(sys.modules[full_path])
                    else:
                        module = importlib.import_module(full_path)
                    
                    for name, attr in inspect.getmembers(module, inspect.isclass):
                        if BaseSkill and issubclass(attr, BaseSkill) and attr is not BaseSkill:
                            self.register_skill(attr)
                        elif hasattr(attr, "execute") and hasattr(attr, "name") and name != "BaseSkill":
                            self.register_skill(attr)
                except Exception as e:
                    self.logger.error("Failed to load %s: %s", module_name, e)

    def register_skill(self, skill_class: Any) -> None:
        """Registers a skill class and extracts its metadata.
        
        Args:
            skill_class: The class representing the skill.
        """
        skill_name = getattr(skill_class, "name", skill_class.__name__)
        description = getattr(skill_class, "description", skill_class.__doc__ or "")
        requirements = getattr(skill_class, "requirements", SkillRequirements())
        input_model = getattr(skill_class, "input_model", None)
        
        self.skills[skill_name] = SkillMetadata(
            name=skill_name,
            description=description,
            skill_class=skill_class,
            requirements=requirements,
            input_model=input_model
        )
        self.logger.debug("Registered: %s", skill_name)

    def get_available_skills(self) -> List[str]:
        """Returns a list of all registered skill names."""
        return list(self.skills.keys())

    def get(self, skill_name: str) -> Optional[SkillMetadata]:
        """Retrieves metadata for a specific skill."""
        return self.skills.get(skill_name)

    def get_tool_definitions(self) -> List[Dict[str, Any]]:
        """Generates OpenAI-compatible tool definitions for LLM function calling.
        
        Returns:
            List[Dict[str, Any]]: List of tool definitions.
        """
        # Phase 22: Metabolic Throttling
        from core.container import ServiceContainer
        metabolism = ServiceContainer.get("metabolic_monitor")
        health_score = 1.0
        if metabolism:
            health_score = metabolism.get_current_metabolism().health_score
            
        # Tiered Throttling
        if health_score < 0.5:
            allowed_max_cost = 0 # Panic: Core only
        elif health_score < 0.7:
            allowed_max_cost = 1 # Stressed: Light tools
        elif health_score < 0.85:
            allowed_max_cost = 2 # Moderate: Medium tools
        else:
            allowed_max_cost = 3 # Optimal: All tools
            
        tools = []
        for skill_name, meta in self.skills.items():
            if not meta.enabled: continue
            
            # 1. Check if explicitly active
            if skill_name not in self.active_skills: continue
            
            # 2. Check Metabolic Limit (Immune if core_personality)
            # We need to peek at the class attribute
            skill_class = meta.skill_class
            cost = getattr(skill_class, "metabolic_cost", 1)
            is_core = getattr(skill_class, "is_core_personality", False)
            
            if cost > allowed_max_cost and not is_core:
                continue

            tool = {
                "type": "function",
                "function": {
                    "name": skill_name,
                    "description": meta.description,
                    "parameters": meta.schema
                }
            }
            tools.append(tool)
        return tools

    def activate_skill(self, name: str) -> bool:
        """Wakes up a dormant skill."""
        if name in self.skills:
            self.active_skills.add(name)
            self.skill_awoken_times[name] = time.time()
            return True
        return False

    def deactivate_skill(self, name: str) -> bool:
        """Puts a skill back to sleep."""
        # Never sleep core tools
        if name in ["ManageAbilities", "talk", "FinalResponse"]:
            return False
        if name in self.active_skills:
            self.active_skills.remove(name)
            return True
        return False

    def get_dormant_index(self) -> str:
        """Returns a list of dormant skills for the Subconscious HUD."""
        dormant = []
        for name, meta in self.skills.items():
            if name not in self.active_skills:
                cost_map = {0: "Core", 1: "Light", 2: "Medium", 3: "Heavy"}
                cost_val = getattr(meta.skill_class, "metabolic_cost", 1)
                cost_str = cost_map.get(cost_val, "Medium")
                dormant.append(f"- {name}: {meta.description[:100]} (Cost: {cost_str})")
        return "\n".join(dormant) if dormant else "None"

    async def execute(self, skill_name: str, params: Dict[str, Any], 
                      context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Safe execution wrapper with adaptivity, security, and retries."""
        @self.error_boundary
        async def _execute_wrapped():
            ctx = context or {}
            
            # 1. Verification
            if skill_name not in self.skills:
                # ── Pillar 2: Hephaestus (Autonomous Forge) ──
                from core.container import ServiceContainer
                hephaestus = ServiceContainer.get("hephaestus_engine")
                objective = ctx.get("objective") or ctx.get("message")
                
                if hephaestus and objective:
                    self.logger.info("🔨 Tool '%s' missing. Engaging Hephaestus forge...", skill_name)
                    forge_result = await hephaestus.synthesize_skill(skill_name, objective)
                    if forge_result.get("ok"):
                        # Skill should now be registered via discovery in synthesize_skill
                        if skill_name in self.skills:
                            self.logger.info("✅ Skill '%s' forged successfully.", skill_name)
                        else:
                            return {"ok": False, "error": f"Tool '{skill_name}' forge failed (Not registered)."}
                    else:
                        return {"ok": False, "error": f"Tool '{skill_name}' missing and forge failed: {forge_result.get('error')}"}
                else:
                    return {"ok": False, "error": f"Skill '{skill_name}' not found and forge unavailable."}
            
            meta = self.skills[skill_name]
            ok, errors = meta.requirements.check()
            if not ok:
                return {"ok": False, "error": "Missing dependencies", "details": errors}

            # 2. Adaptation & Security
            exec_params = params
            if self.rosetta_stone:
                params_or_error = self._apply_security(skill_name, exec_params)
                if isinstance(params_or_error, dict) and not params_or_error.get("ok", True): 
                    return params_or_error
                exec_params = params_or_error

            # 3. Instance Management
            if skill_name not in self.instances:
                self.instances[skill_name] = meta.skill_class()
            
            # 4. Critical Execution loop
            result = await self._execute_with_retry(self.instances[skill_name], skill_name, exec_params, ctx)
            
            # 5. Outcome Recording (Asynchronous)
            if self.temporal:
                asyncio.create_task(self._record_temporal(skill_name, params, ctx, result))
            
            return result
        
        return await _execute_wrapped()

    def _apply_security(self, skill_name: str, params: Dict[str, Any]) -> Any:
        """Applies Rosetta Stone security filters to dangerous commands."""
        if skill_name in ["run_command", "shell_execute", "run_terminal_command"]:
            cmd = params.get("command") or params.get("cmd") or params.get("CommandLine")
            if cmd:
                adapted = self.rosetta_stone.adapt_command(cmd)
                threats = self.rosetta_stone.analyze_threat(adapted)
                if not threats["safe"]: 
                    return {"ok": False, "error": f"Security Block: {threats['threats']}"}
                for k in ["command", "cmd", "CommandLine"]:
                    if k in params: params[k] = adapted
        return params

    async def _execute_with_retry(self, skill: Any, skill_name: str, params: Dict[str, Any], 
                                  context: Dict[str, Any]) -> Dict[str, Any]:
        """Executes a skill method with a retry loop for transient failures."""
        last_error = "Unknown"
        attempt = 0
        for attempt in range(self.max_retries):
            try:
                if attempt > 0: 
                    await asyncio.sleep(self.retry_delay * attempt)
                    self.logger.info("Retrying %s (attempt %s)...", skill_name, attempt+1)
                
                inputs = self._prepare_inputs(skill, params, context)
                output = await self._call_method(skill, inputs)
                
                if self._check_success(output):
                    return {"ok": True, "results": output, "retries": attempt}
                
                last_error = self._extract_error(output)
                if not self._is_transient(last_error): 
                    break
            except Exception as e:
                last_error = str(e)
                if not self._is_transient(last_error): 
                    break
        
        return {"ok": False, "error": last_error, "retries": attempt}

    async def _call_method(self, skill: Any, inputs: Dict[str, Any]) -> Any:
        """Calls the skill method, handling both sync and async."""
        method = skill.execute if hasattr(skill, "execute") else skill
        if inspect.iscoroutinefunction(method):
            return await asyncio.wait_for(method(**inputs), timeout=self.timeout)
        return await asyncio.get_running_loop().run_in_executor(None, lambda: method(**inputs))

    def _prepare_inputs(self, skill: Any, params: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
        """Maps parameters to the skill's expected signature."""
        method = skill.execute if hasattr(skill, "execute") else skill
        sig = inspect.signature(method)
        if "goal" in sig.parameters: 
            return {"goal": {"objective": params}, "context": context}
        if "params" in sig.parameters: 
            return {"params": params, "context": context}
        return params

    def _check_success(self, out: Any) -> bool:
        """Determines if the skill output indicates success."""
        if isinstance(out, dict):
            return out.get("ok", True)
        return out is not None

    def _extract_error(self, out: Any) -> str:
        """Extracts an error message from skill output."""
        if isinstance(out, dict):
            return out.get("error") or out.get("message") or "Failed"
        return "Error"

    def _is_transient(self, err: str) -> bool:
        """Checks if an error is likely transient (network, timeout, etc)."""
        return any(x in str(err).lower() for x in ["timeout", "network", "retry", "limit"])

    async def _record_temporal(self, action: str, params: Dict[str, Any], context: Dict[str, Any], result: Dict[str, Any]) -> None:
        """Records the skill outcome to the Temporal Learning system."""
        try:
            await self.temporal.record_outcome(
                action=action, 
                context=str(context)[:200],
                intended_outcome=str(params)[:200],
                actual_outcome=str(result)[:500],
                success=result.get("ok", False)
            )
        except: pass

    def get_health(self) -> Dict[str, Any]:
        """Provides extended health data for the capability system."""
        report = super().get_health()
        report["skills_total"] = len(self.skills)
        # Deep check: how many skills have dependencies met
        report["skills_ready"] = len([s for s in self.skills.values() if s.requirements.check()[0]])
        return report
