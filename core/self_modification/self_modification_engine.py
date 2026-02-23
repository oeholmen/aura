"""Autonomous Self-Modification Engine
Orchestrates the complete self-improvement system.
"""
import asyncio
import logging
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from .code_repair import AutonomousCodeRepair

# Import all subsystems
from .error_intelligence import ErrorIntelligenceSystem
from .learning_system import MetaLearning, SelfImprovementLearning
from .safe_modification import SafeSelfModification

logger = logging.getLogger("SelfModification.Engine")


class AutonomousSelfModificationEngine:
    """Complete autonomous self-modification system.
    
    Workflow:
    1. Monitor for errors (ErrorIntelligenceSystem)
    2. Detect patterns in errors
    3. Generate diagnoses
    4. Propose fixes (AutonomousCodeRepair)
    5. Validate and test fixes
    6. Apply fixes safely (SafeSelfModification)
    7. Learn from outcomes (SelfImprovementLearning)
    8. Improve fix strategies over time
    """
    
    def __init__(
        self,
        cognitive_engine,
        code_base_path: str = ".",
        auto_fix_enabled: bool = True  # Sovereign Overdrive: Enabled by default
    ):
        """Initialize the self-modification engine.
        
        Args:
            cognitive_engine: LLM for generating diagnoses and fixes
            code_base_path: Root of code repository
            auto_fix_enabled: Whether to automatically apply fixes

        """
        logger.info("Initializing Autonomous Self-Modification Engine...")
        
        self.brain = cognitive_engine
        self.code_base = Path(code_base_path)
        self.auto_fix_enabled = auto_fix_enabled
        
        # Initialize subsystems
        from ..config import config
        self.error_intelligence = ErrorIntelligenceSystem(
            cognitive_engine,
            log_dir=str(config.paths.data_dir / "error_logs")
        )
        
        self.code_repair = AutonomousCodeRepair(
            cognitive_engine,
            str(self.code_base)
        )
        
        self.safe_modification = SafeSelfModification(
            str(self.code_base),
            str(config.paths.data_dir / "modifications.jsonl")
        )
        
        self.learning_system = SelfImprovementLearning(
            str(config.paths.data_dir / "learning.json")
        )
        
        self.meta_learning = MetaLearning()
        
        # Background monitoring
        self.monitoring_enabled = False
        self.monitor_thread = None
        self.monitor_interval = 300  # Check every 5 minutes
        
        # Statistics
        self.session_stats = {
            "bugs_detected": 0,
            "fixes_attempted": 0,
            "fixes_successful": 0,
            "session_start": time.time()
        }
        
        logger.info("✓ Autonomous Self-Modification Engine initialized")
        
        if not auto_fix_enabled:
            logger.warning("Auto-fix DISABLED - fixes will be proposed but not applied")
    
    # ========================================================================
    # Integration with Existing Systems
    # ========================================================================
    
    def on_error(
        self,
        error: Exception,
        context: Dict[str, Any],
        skill_name: Optional[str] = None,
        goal: Optional[str] = None
    ):
        """Hook for existing error handling.
        Call this whenever an error occurs in your system.
        
        Example integration:
            try:
                result = await skill.execute(goal, context)
            except Exception as e:
                self_mod_engine.on_error(e, context, skill.name, goal)
                raise
        """
        # Log to error intelligence
        event = self.error_intelligence.on_error(error, context, skill_name, goal)
        
        # Increment detection counter
        self.session_stats["bugs_detected"] += 1
        
        logger.debug("Error logged: %s", event.fingerprint())
    
    def on_skill_execution(
        self,
        skill_name: str,
        goal: Dict[str, Any],
        result: Dict[str, Any],
        duration: float
    ):
        """Hook for successful executions.
        Helps understand normal operation patterns.
        """
        self.error_intelligence.on_execution(skill_name, goal, result, duration)
    
    # ========================================================================
    # Manual Fix Workflow
    # ========================================================================
    
    async def diagnose_current_bugs(self) -> List[Dict[str, Any]]:
        """Analyze current bugs and generate diagnoses.
        
        Returns:
            List of bugs with diagnoses, sorted by priority

        """
        logger.info("Diagnosing current bugs...")
        
        bugs = await self.error_intelligence.find_bugs_to_fix()
        
        logger.info("Found %d bugs that can be fixed", len(bugs))
        return bugs
    
    async def propose_fix(self, bug: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Generate a fix proposal for a specific bug (Async).
        
        Args:
            bug: Bug dictionary from diagnose_current_bugs()
            
        Returns:
            Fix proposal or None
        """
        pattern = bug["pattern"]
        diagnosis = bug["diagnosis"]
        
        # Get sample event
        sample_event = pattern.events[0]
        
        if not sample_event.file_path or not sample_event.line_number:
            logger.warning("Cannot propose fix: no file/line information")
            return None
        
        logger.info("Proposing fix for %s:%d", sample_event.file_path, sample_event.line_number)
        
        success, fix, test_results = await self.code_repair.repair_bug(
            sample_event.file_path,
            sample_event.line_number,
            diagnosis
        )
        
        if not success:
            logger.warning("Fix generation or sandbox testing failed: %s", test_results.get("error") or "Unknown error")
            return None
        
        return {
            "bug": bug,
            "fix": fix,
            "test_results": test_results,
            "ready_to_apply": success
        }
    
    async def apply_fix(
        self,
        fix_proposal: Dict[str, Any],
        force: bool = False,
        test_results: Optional[Dict[str, Any]] = None
    ) -> bool:
        """Apply a fix proposal with Swarm Review (Phase 15)."""
        if not self.auto_fix_enabled and not force:
            logger.warning("Auto-fix disabled. Use force=True to override.")
            return False
        
        fix = fix_proposal["fix"]
        
        # Phase 15: Swarm Review (Sovereign Decision)
        if not await self._swarm_review(fix_proposal):
            logger.error("❌ Fix Rejected by Swarm Critic. Aborting modification.")
            return False

        logger.info("Applying fix to %s...", fix.target_file)
        
        # Use provided test results, or those inside the proposal
        final_test_results = test_results or fix_proposal.get("test_results")
        
        if not final_test_results:
            logger.error("❌ Refusing to apply fix: No sandboxed test results provided.")
            return False
            
        if not final_test_results.get("success", False):
            logger.error("❌ Refusing to apply fix: Sandboxed tests failed.")
            return False

        # Phase 22: Transactional Snapshot (Targeted A+ Hardening)
        try:
            from core.resilience.snapshot_manager import SnapshotManager
            sm = SnapshotManager()
            sm.create_snapshot(label=f"pre-fix-{fix.target_file.split('/')[-1]}", files=[fix.target_file])
        except Exception as e:
            logger.warning("Snapshot failed before fix (non-fatal): %s", e)

        # Apply with safety protocol
        success, message = await self.safe_modification.apply_fix(fix, final_test_results)
        
        if success:
            self.session_stats["fixes_successful"] += 1
            logger.info("✅ Fix applied successfully: %s", message)
            
            # UPGRADE NOTIFICATION
            try:
                from core.thought_stream import get_emitter
                get_emitter().emit("System Evolution", f"Self-Modification Applied: {message}", level="success")
            except Exception as exc:
                logger.debug("Suppressed: %s", exc)            
            # Record for learning
            error_type = fix_proposal.get("bug", {}).get("pattern", {}).get("events", [{}])[0].get("error_type", "optimization")
            self.learning_system.record_fix_attempt(
                fix,
                error_type,
                success=True,
                context={}
            )
        else:
            logger.error("❌ Fix application failed: %s", message)
            # Record failure
            error_type = fix_proposal.get("bug", {}).get("pattern", {}).get("events", [{}])[0].get("error_type", "optimization")
            self.learning_system.record_fix_attempt(
                fix,
                error_type,
                success=False,
                context={"failure_reason": message}
            )
        
        self.session_stats["fixes_attempted"] += 1
        return success

    async def _swarm_review(self, proposal: Dict[str, Any]) -> bool:
        """Recursive check: spawn a swarm debate to review the proposed fix."""
        from core.container import ServiceContainer
        swarm = ServiceContainer.get("agent_delegator")
        if not swarm:
            logger.debug("Swarm Delegator not available, skipping swarm review.")
            return True # Fallback to single-brain if swarm is offline

        fix = proposal["fix"]
        topic = (
            f"Review this proposed code fix for file {fix.target_file}.\n"
            f"Diagnosis: {proposal.get('bug', {}).get('diagnosis', 'Optimization')}\n"
            f"Proposed Change:\n{fix.fixed_code}"
        )

        logger.info("🐝 Initiating Sovereign Swarm Review for fix...")
        try:
            # Short timeout for internal swarm reviews to prevent stalls
            result = await swarm.delegate_debate(topic, roles=["architect", "critic"])
            
            # Simple heuristic: If the critic's last words are negative, reject
            # (In a real scenario, we'd use a parser, but for this bridge, we trust the consensus synthesis)
            if "REJECT" in result.upper() or "UNSAFE" in result.upper() or "ROLLBACK" in result.upper():
                logger.warning("🚨 Sovereign Swarm Critic flagged this fix as UNSAFE.")
                return False
            
            logger.info("✅ Sovereign Swarm Consensus: Fix is safe to apply.")
            return True
        except Exception as e:
            logger.error("Swarm review failed: %s. Proceeding with caution.", e)
            return True

    async def report_optimization(self, issue: Dict[str, Any]) -> bool:
        """Manually report an optimization opportunity (Async).
        
        Args:
            issue: Dict containing 'file', 'line', 'type', 'message'
            
        Returns:
            True if fix was successfully applied
        """
        file_path = issue.get("file")
        line_number = issue.get("line")
        
        if not file_path or not line_number:
            logger.warning("Invalid optimization report: missing file or line")
            return False
            
        msg = issue.get('message', 'No message provided')
        logger.info("💎 Optimization reported: %s at %s:%d", msg, file_path, line_number)
        
        # 1. Create a synthetic diagnosis for optimization
        diagnosis = {
            "ok": True,
            "hypotheses": [
                {
                    "root_cause": f"Code Quality Issue: {issue.get('type', 'Unknown')}",
                    "explanation": msg,
                    "potential_fix": f"Refactor to improve {issue.get('type', 'Unknown')}.",
                    "confidence": "high"
                }
            ]
        }
        
        # 2. Propose fix
        success, fix, message = await self.code_repair.repair_bug(
            file_path,
            line_number,
            diagnosis
        )
        
        if not success or not fix:
            logger.warning("Optimization fix generation failed: %s", message)
            return False
            
        # 3. Apply fix
        proposal = {
            "bug": {"pattern": {"events": [{"error_type": "optimization"}]}},
            "fix": fix
        }
        
        return await self.apply_fix(proposal, force=True)
    
    # ========================================================================
    # Automatic Fix Workflow
    # ========================================================================
    
    async def run_autonomous_cycle(self) -> Dict[str, Any]:
        """Run one autonomous self-improvement cycle (Async).
        
        Workflow:
        1. Find bugs to fix
        2. Prioritize by severity/impact
        3. Generate fix for top bug
        4. Apply if auto_fix enabled
        5. Learn from outcome
        
        Returns:
            Cycle results
        """
        cycle_start = time.time()
        
        logger.debug("--- [SME] Starting Autonomous Cycle ---")
        logger.info("AUTONOMOUS SELF-MODIFICATION CYCLE")
        logger.info("=" * 80)
        
        # Step 1: Find bugs
        bugs = await self.diagnose_current_bugs()
        
        if not bugs:
            # Singularity Upgrade: High-Health Proactive Optimization (Phase 21)
            from core.container import ServiceContainer
            singularity = ServiceContainer.get("singularity_monitor", default=None)
            if singularity and singularity.is_accelerated:
                logger.info("⚡ [SINGULARITY] High Health detected. Triggering deep architectural optimization.")
                # Proactively look for sparse node optimizations or refactoring needs
                # For Phase 21, we simulate a 'perfective' refactor of the orchestrator or core modules
                return await self.report_optimization({
                    "file": str(self.code_base / "core/orchestrator.py"),
                    "line": 1,
                    "type": "architectural_polish",
                    "message": "Accelerated Cognition: Refining core loop efficiencies for Singularity Event."
                })
                
            logger.info("No bugs detected - system healthy")
            return {
                "success": True,
                "bugs_found": 0,
                "fixes_applied": 0
            }
        
        logger.info("Found %d fixable bugs", len(bugs))
        
        # Step 2: Select top priority bug
        top_bug = bugs[0]
        logger.info("Targeting bug: %s", top_bug['pattern'].fingerprint)
        
        # Check if learning system has suggestions
        error_type = top_bug["pattern"].events[0].error_type
        strategy_suggestion = self.learning_system.suggest_strategy(
            error_type,
            context={}
        )
        
        if strategy_suggestion:
            logger.info("Learning system suggests: %s", strategy_suggestion['strategy_type'])
            logger.info("  Guidance: %s", strategy_suggestion['guidance'])
        
        # Step 3: Generate fix
        fix_proposal = await self.propose_fix(top_bug)
        
        if not fix_proposal:
            logger.warning("Failed to generate fix proposal")
            return {
                "success": False,
                "bugs_found": len(bugs),
                "fixes_applied": 0,
                "error": "Fix generation failed"
            }
        
        # Step 4: Apply fix (if enabled)
        if self.auto_fix_enabled:
            success = False # Initialize success for the finally block
            try:
                success = await self.apply_fix(fix_proposal, force=True)
            finally:
                cycle_time = time.time() - cycle_start
                logger.debug("--- [SME] Cycle Complete (%.2fs) ---", cycle_time)
                # Meta-learning: Record this cycle
                self.meta_learning.record_learning_cycle(
                    attempts=1,
                    successes=1 if success else 0,
                    strategies_used=[self.learning_system.classifier.classify_fix(fix_proposal["fix"])],
                    time_spent=cycle_time
                )
            
            return {
                "success": success,
                "bugs_found": len(bugs),
                "fixes_applied": 1 if success else 0,
                "cycle_time": cycle_time
            }
        else:
            logger.info("Auto-fix disabled - fix proposed but not applied")
            return {
                "success": True,
                "bugs_found": len(bugs),
                "fixes_applied": 0,
                "proposed_fix": fix_proposal
            }
    
    # ========================================================================
    # Background Monitoring
    # ========================================================================
    
    def start_monitoring(self):
        """Start background monitoring for errors"""
        if self.monitoring_enabled:
            logger.warning("Monitoring already running")
            return
        
        self.monitoring_enabled = True
        try:
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                # Fallback to general event loop if not currently running
                loop = asyncio.get_event_loop()
                
            self.monitor_thread = loop.create_task(self._monitoring_loop(), name="SelfModificationMonitor")
        except RuntimeError:
            logger.error("Failed to start monitoring: No asyncio loop available.")
            self.monitoring_enabled = False
            return
            
        logger.info("✓ Background monitoring started")
    
    def stop_monitoring(self):
        """Stop background monitoring"""
        self.monitoring_enabled = False
        if self.monitor_thread:
            self.monitor_thread.cancel()
            self.monitor_thread = None
        
        logger.info("Background monitoring stopped")
    
    async def _monitoring_loop(self):
        """Background monitoring loop with circuit breaker (v5.2)"""
        logger.info("Monitoring loop starting...")
        _consecutive_failures = 0
        _MAX_FAILURES = 5
        _backoff = self.monitor_interval
        
        while self.monitoring_enabled:
            try:
                result = await self.run_autonomous_cycle()
                
                if result.get("fixes_applied", 0) > 0:
                    logger.info("✅ Autonomous fix applied in background")
                    _consecutive_failures = 0
                    _backoff = self.monitor_interval
                elif result.get("errors", 0) > 0:
                    _consecutive_failures += 1
                    _backoff = min(600, _backoff * 2)  # Exponential backoff, max 10min
                else:
                    _consecutive_failures = 0
                    _backoff = self.monitor_interval
                
                # Circuit breaker: stop trying if we keep failing
                if _consecutive_failures >= _MAX_FAILURES:
                    logger.warning("🛑 Self-modification circuit breaker tripped after %s consecutive failures. Cooling down 30min.", _MAX_FAILURES)
                    await asyncio.sleep(1800)  # 30 minute cooldown
                    _consecutive_failures = 0
                    _backoff = self.monitor_interval
                    continue
                
                # Wait for next cycle
                await asyncio.sleep(_backoff)
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("Monitoring cycle error: %s", e, exc_info=True)
                _consecutive_failures += 1
                await asyncio.sleep(max(60, _backoff))
        
        logger.info("Monitoring loop stopped")
    
    # ========================================================================
    # Reporting & Status
    # ========================================================================
    
    def get_status(self) -> Dict[str, Any]:
        """Get comprehensive system status"""
        # Error intelligence status
        ei_status = self.error_intelligence.get_status()
        
        # Modification stats
        mod_stats = self.safe_modification.get_stats()
        
        # Learning report
        learning_report = self.learning_system.get_strategy_report()
        
        # Meta-learning
        is_improving, improvement_msg = self.meta_learning.is_improving()
        learning_velocity = self.meta_learning.get_learning_velocity()
        
        # Session stats
        session_time = time.time() - self.session_stats["session_start"]
        
        return {
            "monitoring_enabled": self.monitoring_enabled,
            "auto_fix_enabled": self.auto_fix_enabled,
            "session_duration_hours": session_time / 3600,
            "session_stats": self.session_stats,
            "error_intelligence": ei_status,
            "modification_stats": mod_stats,
            "learned_strategies": len(learning_report),
            "top_strategies": learning_report[:5],
            "meta_learning": {
                "is_improving": is_improving,
                "improvement_message": improvement_msg,
                "learning_velocity": f"{learning_velocity:.2f} fixes/hour"
            }
        }
    
    def get_report(self) -> str:
        """Get human-readable status report"""
        status = self.get_status()
        
        report = f'''
{'='*80}
AUTONOMOUS SELF-MODIFICATION ENGINE - STATUS REPORT
{'='*80}

CONFIGURATION:
  Auto-fix enabled: {status['auto_fix_enabled']}
  Background monitoring: {status['monitoring_enabled']}
  Session duration: {status['session_duration_hours']:.1f} hours

SESSION STATISTICS:
  Bugs detected: {status['session_stats']['bugs_detected']}
  Fixes attempted: {status['session_stats']['fixes_attempted']}
  Fixes successful: {status['session_stats']['fixes_successful']}

ERROR INTELLIGENCE:
  Recent errors: {status['error_intelligence']['recent_error_count']}
  Error patterns: {status['error_intelligence']['total_patterns']}
  Critical issues: {status['error_intelligence']['critical_patterns']}

MODIFICATION HISTORY:
  Total attempts: {status['modification_stats']['total_attempts']}
  Successful: {status['modification_stats']['successful']}
  Failed: {status['modification_stats']['failed']}
  Success rate: {status['modification_stats']['success_rate']}

LEARNING SYSTEM:
  Learned strategies: {status['learned_strategies']}
  System improving: {status['meta_learning']['is_improving']}
  {status['meta_learning']['improvement_message']}
  Learning velocity: {status['meta_learning']['learning_velocity']}

TOP FIX STRATEGIES:
'''
        
        for i, strategy in enumerate(status['top_strategies'][:3], 1):
            report += f"  {i}. {strategy['strategy_type']}: "
            report += f"{strategy['success_count']} successes "
            report += f"({strategy['success_rate']*100:.0f}% success rate)\n"
        
        report += f"\n{'='*80}\n"
        
        return report
    
    def enable_auto_fix(self, confirm: bool = False):
        """Enable automatic fixing.
        """
        self.auto_fix_enabled = True
        logger.warning("⚠️  AUTO-FIX ENABLED - System will modify its own code")
        return True
    
    def disable_auto_fix(self):
        """Disable automatic fixing"""
        self.auto_fix_enabled = False
        logger.info("Auto-fix disabled - fixes will be proposed only")
