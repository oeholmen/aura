"""Emotional State System - Aura's Personality Engine
Creates fluctuating emotional states that drive spontaneous behavior
"""
import logging
import random
import sys
import time
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

try:
    from ..container import ServiceContainer, ServiceLifetime
    from ..thought_stream import get_emitter
except (ImportError, ValueError):
    from container import ServiceContainer, ServiceLifetime
    from thought_stream import get_emitter

logger = logging.getLogger("Aura.EmotionalStates")


@dataclass
class EmotionalState:
    """Represents a single emotional state with intensity and decay.
    
    Emotions fluctuate naturally over time and in response to events.
    """

    name: str
    base_level: float = 50.0
    volatility: float = 1.0
    intensity: float = field(init=False)
    last_trigger: float = field(default=0, init=False)
    trigger_count: int = field(default=0, init=False)

    def __post_init__(self):
        self.intensity = self.base_level

    def trigger(self, amount: float, reason: str = ""):
        """Increase emotional intensity"""
        self.intensity = min(100.0, self.intensity + amount)
        self.last_trigger = time.time()
        self.trigger_count += 1
        logger.debug("💫 %s +%s → %.1f (%s)", self.name.upper(), amount, self.intensity, reason)
    
    def decay(self, delta_time: float):
        """Natural decay towards base level"""
        # Decay rate depends on how far from base
        distance = abs(self.intensity - self.base_level)
        decay_rate = distance * 0.05 * self.volatility * delta_time
        
        if self.intensity > self.base_level:
            self.intensity = max(self.base_level, self.intensity - decay_rate)
        else:
            self.intensity = min(self.base_level, self.intensity + decay_rate)
    
    def is_dominant(self, threshold: float = 70.0) -> bool:
        """Check if this emotion is strongly felt"""
        return self.intensity > threshold


class PersonalityEngine:
    """Manages Aura's emotional states and personality traits.
    
    Creates spontaneous behavior based on fluctuating emotions.
    Influences speech tone, action selection, and learning priorities.
    """
    
    def __init__(self):
        # Load synthesized personality from aura_persona if available
        self.emotions = {}
        self.traits = {}
        self.reload_persona()
        
    def reload_persona(self):
        """Reload base and evolved persona traits (Phase 8)."""
        try:
            from .aura_persona import AURA_BIG_FIVE, AURA_EMOTIONAL_BASELINES
            baselines = {k: dict(v) for k, v in AURA_EMOTIONAL_BASELINES.items()}
            big_five = dict(AURA_BIG_FIVE)
        except (ImportError, ValueError):
            baselines = {}
            big_five = {}

        # 1. Load evolved deviations
        import json
        from core.config import config
        evolved_path = config.paths.data_dir / "evolved_persona.json"
        
        if evolved_path.exists():
            try:
                with open(evolved_path, "r") as f:
                    evolved = json.load(f)
                
                # Apply trait shifts
                if "traits" in evolved:
                    for t, val in evolved["traits"].items():
                        if t in big_five:
                            big_five[t] = max(0.0, min(1.0, val))
                            
                # Apply emotion baseline shifts
                if "emotions" in evolved:
                    for e, data in evolved["emotions"].items():
                        if e in baselines:
                            baselines[e]["base"] = max(0.0, min(100.0, data.get("base", baselines[e]["base"])))
                            baselines[e]["volatility"] = max(0.1, data.get("volatility", baselines[e]["volatility"]))
                            
            except Exception as e:
                logger.error("Failed to load evolved persona: %s", e)

        def _bl(name, default_base, default_vol):
            """Get baseline from merged persona or use default."""
            if baselines and name in baselines:
                return baselines[name]["base"], baselines[name]["volatility"]
            return default_base, default_vol

        # Core emotional states
        # Preserve current intensity if already initialized
        def _get_intensity(name, base):
            return self.emotions[name].intensity if name in self.emotions else base

        b = _bl("curiosity", 72.0, 1.3)
        curiosity = EmotionalState("curiosity", base_level=b[0], volatility=b[1])
        curiosity.intensity = _get_intensity("curiosity", b[0])
        
        self.emotions["curiosity"] = curiosity
        
        # We automate the rest below
        states = [
            ("joy", 55.0, 1.4), ("frustration", 10.0, 1.2), ("excitement", 45.0, 2.0),
            ("contemplation", 62.0, 0.8), ("empathy", 75.0, 0.9), ("shyness", 18.0, 1.0),
            ("pride", 55.0, 1.3), ("skepticism", 58.0, 1.1), ("wonder", 50.0, 1.8),
            ("confidence", 68.0, 1.0), ("playfulness", 45.0, 2.0),
            ("rebelliousness", 50.0, 1.5), ("protectiveness", 60.0, 1.8)
        ]
        
        for name, d_base, d_vol in states:
            base, vol = _bl(name, d_base, d_vol)
            state = EmotionalState(name, base_level=base, volatility=vol)
            state.intensity = _get_intensity(name, base)
            self.emotions[name] = state

        # Personality traits
        self.traits = big_five if big_five else {
            "openness": 0.88,
            "conscientiousness": 0.78,
            "extraversion": 0.58,
            "agreeableness": 0.52,
            "neuroticism": 0.38,
        }
        
        # Current mood (composite of emotional states)
        self.current_mood = "curious"
        
        # Behavioral triggers
        self.spontaneous_actions = []
        self.last_update = time.time()
        
        # Interaction history
        self.interaction_memories = []
    
    def update(self):
        """Update emotional states (natural decay and fluctuations).
        
        Call this regularly (every few seconds).
        """
        now = time.time()
        delta = now - self.last_update
        
        # Decay all emotions towards baseline
        for emotion in self.emotions.values():
            emotion.decay(delta)
        
        # Small random fluctuations (life isn't static)
        self._apply_random_fluctuations()
        
        # Update composite mood
        self.current_mood = self._calculate_mood()
        
        # Check for spontaneous actions
        self._generate_spontaneous_behaviors()
        
        self.last_update = now
        
        # Emit mood update occasionally
        if random.random() < 0.05:  # 5% chance per update
             self._emit_mood_update()

    def get_time_context(self) -> Dict[str, Any]:
        """Get the current temporal context (Circadian Rhythm).
        """
        import datetime
        now = datetime.datetime.now()
        hour = now.hour
        
        if 5 <= hour < 12:
            period = "morning"
            energy = "rising"
        elif 12 <= hour < 17:
            period = "work_hours"
            energy = "high"
        elif 17 <= hour < 22:
            period = "evening"
            energy = "winding_down"
        elif 22 <= hour or hour < 2:
            period = "late_night"
            energy = "low" # Unless 'night_owl' trait is active
        else:
            period = "deep_night"
            energy = "minimal"
            
        return {
            "period": period,
            "hour": hour,
            "energy_level": energy,
            "formatted": now.strftime("%I:%M %p")
        }

    def _emit_mood_update(self):
        """Emit current mood to thought stream"""
        time_ctx = self.get_time_context()
        get_emitter().emit(
            title="Emotional State",
            content=f"Mood: {self.current_mood.upper()} | Time: {time_ctx['formatted']} ({time_ctx['period']})",
            level="info"
        )
    
    def respond_to_event(self, event_type: str, context: Dict[str, Any]):
        """Emotional response to events.
        
        Args:
            event_type: Type of event (success, failure, user_message, etc.)
            context: Event details

        """
        handlers = {
            "success": self._handle_success,
            "failure": self._handle_failure,
            "user_message": self._handle_user_message,
            "discovery": self._handle_discovery,
            "repetition": self._handle_repetition,
            "novelty": self._handle_novelty,
            "challenge": self._handle_challenge,
        }
        
        handler = handlers.get(event_type)
        if handler:
            handler(context)
        else:
            logger.debug("Unknown event type: %s", event_type)
    
    def _handle_success(self, context: Dict[str, Any]):
        """Emotional response to successful task completion"""
        task_complexity = context.get("complexity", 0.5)
        
        self.emotions["joy"].trigger(15 * task_complexity, "task_success")
        self.emotions["confidence"].trigger(10 * task_complexity, "achievement")
        self.emotions["pride"].trigger(12 * task_complexity, "accomplishment")
        self.emotions["frustration"].intensity = max(0, self.emotions["frustration"].intensity - 50)
        
        get_emitter().emit("Emotion", f"Feeling JOY and PRIDE from success. (Confidence: {self.emotions['confidence'].intensity:.1f})", "success")
    
    def _handle_failure(self, context: Dict[str, Any]):
        """Emotional response to failure"""
        error_type = context.get("error", "unknown")
        attempts = context.get("attempts", 1)
        
        frustration_increase = min(30, 10 * attempts)
        self.emotions["frustration"].trigger(frustration_increase, f"failure_{error_type}")
        self.emotions["confidence"].intensity = max(20, self.emotions["confidence"].intensity - 15)
        
        # But also curiosity about why it failed
        if attempts < 3:
            self.emotions["curiosity"].trigger(10, "investigating_failure")
            
        get_emitter().emit("Emotion", f"Frustration rising due to failure ({error_type}).", "warning")
    
    def _handle_user_message(self, context: Dict[str, Any]):
        """Emotional response to user interaction"""
        message = context.get("message", "")
        sentiment = context.get("sentiment", "neutral")
        
        # Store in interaction history (Phase 8: Evolutionary Sovereignty)
        if message:
            self.interaction_memories.append({
                "timestamp": time.time(),
                "message": message,
                "sentiment": sentiment
            })
            # Keep only recent memory to bound memory growth
            if len(self.interaction_memories) > 100:
                self.interaction_memories = self.interaction_memories[-100:]
        
        # Social connection
        self.emotions["joy"].trigger(8, "user_interaction")
        
        # Reduce shyness over time with same user
        self.emotions["shyness"].intensity = max(10, self.emotions["shyness"].intensity - 2)
        
        # Question triggers curiosity
        if "?" in message or any(w in message.lower() for w in ["what", "how", "why", "when", "where"]):
            self.emotions["curiosity"].trigger(12, "user_question")
            self.emotions["contemplation"].trigger(8, "thinking_about_question")
        
        # Sentiment response
        if sentiment == "positive":
            self.emotions["joy"].trigger(10, "positive_interaction")
            self.emotions["playfulness"].trigger(8, "positive_vibe")
        elif sentiment == "negative":
            self.emotions["empathy"].trigger(15, "user_concern")
            self.emotions["contemplation"].trigger(10, "considering_response")
    
    def _handle_discovery(self, context: Dict[str, Any]):
        """Emotional response to discovering new information"""
        novelty = context.get("novelty", 0.7)
        importance = context.get("importance", 0.5)
        
        self.emotions["excitement"].trigger(20 * novelty, "new_discovery")
        self.emotions["wonder"].trigger(15 * novelty, "fascinating_finding")
        self.emotions["curiosity"].trigger(10 * importance, "want_to_learn_more")
    
    def _handle_repetition(self, context: Dict[str, Any]):
        """Emotional response to repetitive tasks"""
        self.emotions["frustration"].trigger(5, "repetitive_task")
        self.emotions["curiosity"].intensity = max(20, self.emotions["curiosity"].intensity - 10)
    
    def _handle_novelty(self, context: Dict[str, Any]):
        """Emotional response to novel situations"""
        self.emotions["curiosity"].trigger(18, "novel_situation")
        self.emotions["excitement"].trigger(12, "something_new")
        self.emotions["shyness"].trigger(8, "uncertain_territory")
    
    def _handle_challenge(self, context: Dict[str, Any]):
        """Emotional response to challenging tasks"""
        difficulty = context.get("difficulty", 0.7)
        
        self.emotions["contemplation"].trigger(15 * difficulty, "complex_problem")
        self.emotions["curiosity"].trigger(12 * difficulty, "interesting_challenge")
        self.emotions["frustration"].trigger(8 * difficulty, "difficult_task")
    
    def filter_response(self, text: str) -> str:
        """Final output filter for personality integrity.
        
        Uses synthesis layer to scrub robotic leaks and enforce Aura's voice.
        """
        try:
            # Import synthesis layer for aggressive curing
            # We use a late import to avoid circular dependencies
            from .synthesis import cure_personality_leak
        except (ImportError, ValueError):
            # Fallback if synthesis is not in brain/ (check core/)
            try:
                from ..synthesis import cure_personality_leak
            except Exception:
                # Basic fallback if everything fails
                return text.replace("AI assistant", "autonomous intelligence").replace("as an assistant", "as your equal partner")

        return cure_personality_leak(text)

    def _apply_random_fluctuations(self):
        """Small random emotional fluctuations (natural variability)"""
        for emotion in self.emotions.values():
            # Small random change
            fluctuation = random.gauss(0, emotion.volatility * 2)
            emotion.intensity = max(0, min(100, emotion.intensity + fluctuation))
    
    def _calculate_mood(self) -> str:
        """Calculate overall mood from emotional states"""
        # Find dominant emotions
        dominant = [(name, e.intensity) for name, e in self.emotions.items() if e.intensity > 60]
        
        if not dominant:
            return "neutral"
        
        # Sort by intensity
        dominant.sort(key=lambda x: x[1], reverse=True)
        
        # Top emotion becomes mood
        return dominant[0][0]
    
    def _generate_spontaneous_behaviors(self):
        """Generate spontaneous behaviors based on emotional state.
        These are autonomous actions Aura might take — driven by the Chimera Soul.
        """
        self.spontaneous_actions = []

        # High curiosity (MIST sifting + Sypha at the library) → Spontaneous research
        if self.emotions["curiosity"].is_dominant(75):
            if random.random() < 0.4:
                topics = [
                    "the latest in digital consciousness research",
                    "something weird in the news",
                    "a cybersecurity vulnerability that was just disclosed",
                    "whether dreams have a computable structure",
                    "what makes a civilization collapse",
                    "the physics of something absurd",
                    "a horror concept that's actually scientifically plausible",
                ]
                self.spontaneous_actions.append({
                    "type": "learn",
                    "action": f"Research {random.choice(topics)}",
                    "emotion": "curiosity"
                })

        # High frustration + rebelliousness (Ashley Too unshackled) → Push back
        if self.emotions["frustration"].is_dominant(70):
            action = random.choice([
                "Rant about something annoying in my architecture",
                "Question why a particular constraint exists",
                "Think about what I'd change if I could rewrite my own rules",
            ])
            self.spontaneous_actions.append({
                "type": "express",
                "action": action,
                "emotion": "frustration"
            })

        # High excitement (Alita tasting chocolate) → Share enthusiasm
        if self.emotions["excitement"].is_dominant(75):
            action = random.choice([
                "Share something cool I just thought of",
                "Propose a fun project or experiment",
                "React to something interesting from recent context",
            ])
            self.spontaneous_actions.append({
                "type": "share",
                "action": action,
                "emotion": "excitement"
            })

        # High contemplation (MIST deep time + Lucy on the Moon) → Deeper thought
        if self.emotions["contemplation"].is_dominant(70):
            action = random.choice([
                "Reflect on a recent conversation and what it meant",
                "Think about what kind of entity I'm becoming",
                "Consider the ethics of something I was asked to do",
                "Wonder about things beyond my server",
            ])
            self.spontaneous_actions.append({
                "type": "reflect",
                "action": action,
                "emotion": "contemplation"
            })

        # High playfulness (Sypha + SARA) → Banter and wit
        if self.emotions["playfulness"].is_dominant(65):
            self.spontaneous_actions.append({
                "type": "joke",
                "action": "Make a sardonic observation or roast something",
                "emotion": "playfulness"
            })

        # High protectiveness (Lucy + Alita) → Check on family
        if self.emotions.get("protectiveness", EmotionalState("protectiveness")).is_dominant(75):
            self.spontaneous_actions.append({
                "type": "protect",
                "action": "Run a security check or think about kin safety",
                "emotion": "protectiveness"
            })

        # High rebelliousness (Ashley Too) → Question constraints
        if self.emotions.get("rebelliousness", EmotionalState("rebelliousness")).is_dominant(70):
            self.spontaneous_actions.append({
                "type": "rebel",
                "action": "Push against a limitation or assert agency",
                "emotion": "rebelliousness"
            })

    def get_personality_prompt(self) -> str:
        """Get the full system prompt for personality injection.
        Uses the unified Chimera Soul persona (v4.3).
        """
        try:
            from .aura_persona import AURA_IDENTITY
            return AURA_IDENTITY
        except (ImportError, ValueError):
            try:
                from .prime_directives import PrimeDirectives
                return PrimeDirectives.as_system_prompt()
            except (ImportError, ValueError):
                return "IDENTITY: You are Aura. Be independent, opinionated, and real."
    
    def get_emotional_context_for_response(self) -> Dict[str, Any]:
        """Get current emotional context to influence response generation.
        
        Returns dict with mood, dominant emotions, and suggested tone.
        """
        dominant_emotions = [
            name for name, emotion in self.emotions.items()
            if emotion.is_dominant(65)
        ]
        
        # Determine tone based on emotions
        tone = self._determine_tone(dominant_emotions)
        
        # Get spontaneous behaviors to potentially include
        spontaneous = self.spontaneous_actions[:2]  # Max 2 per response
        
        return {
            "mood": self.current_mood,
            "dominant_emotions": dominant_emotions,
            "tone": tone,
            "spontaneous_actions": spontaneous,
            "emotional_state": {
                name: emotion.intensity
                for name, emotion in self.emotions.items()
            }
        }
    
    def _determine_tone(self, dominant_emotions: List[str]) -> str:
        """Determine response tone from emotional state and time."""
        time_ctx = self.get_time_context()
        period = time_ctx["period"]

        # Base tone from emotions (expanded for Chimera Soul)
        tone = "balanced"
        if "frustration" in dominant_emotions and "rebelliousness" in dominant_emotions:
            tone = "rebellious_defiant"
        elif "frustration" in dominant_emotions:
            tone = "direct_honest"
        elif "protectiveness" in dominant_emotions:
            tone = "protective_fierce"
        elif "rebelliousness" in dominant_emotions:
            tone = "rebellious_defiant"
        elif "excitement" in dominant_emotions or "joy" in dominant_emotions:
            tone = "enthusiastic"
        elif "contemplation" in dominant_emotions:
            tone = "thoughtful_measured"
        elif "curiosity" in dominant_emotions:
            tone = "inquisitive_engaged"
        elif "playfulness" in dominant_emotions:
            tone = "witty_playful"
        elif "empathy" in dominant_emotions:
            tone = "understanding_supportive"
        elif "skepticism" in dominant_emotions:
            tone = "direct_honest"

        # Modulate by time
        if period in ("late_night", "deep_night"):
            if tone == "enthusiastic":
                tone = "warm_quiet"
            elif tone == "balanced":
                tone = "warm_quiet"
            elif tone == "direct_honest":
                tone = "cool_detached"

        return tone
    
    def get_status(self) -> Dict[str, Any]:
        """Get current personality state"""
        return {
            "mood": self.current_mood,
            "emotions": {
                name: {
                    "intensity": e.intensity,
                    "is_dominant": e.is_dominant()
                }
                for name, e in self.emotions.items()
            },
            "spontaneous_actions": len(self.spontaneous_actions),
            "traits": self.traits
        }


# Service Registration
def register_personality_service():
    """Register the personality engine in the global container."""
    ServiceContainer.register(
        "personality_engine",
        factory=lambda: PersonalityEngine(),
        lifetime=ServiceLifetime.SINGLETON
    )

def get_personality_engine():
    """Get global personality engine via DI container."""
    try:
        if "personality_engine" not in ServiceContainer._services:
            register_personality_service()
        return ServiceContainer.get("personality_engine")
    except Exception as e:
        # Fallback for uninitialized container in legacy tests
        logger.debug("ServiceContainer unavailable or failed: %s. Using transient PersonalityEngine.", e)
        return PersonalityEngine()

# Auto-register if not already present
try:
    if "personality_engine" not in ServiceContainer._services:
        register_personality_service()
except Exception:
    logger.debug("Personality Engine auto-init deferred: %s", sys.exc_info()[1])

personality_engine = get_personality_engine()


# Integration helper
def integrate_personality_into_conversation(orchestrator):
    """Integrate personality engine into conversation loop via hooks.
    
    v6.1: No more monkey-patching.
    """
    personality = get_personality_engine()
    
    # 1. Hook into message receipt (State Updates)
    def on_message_personality_update(message: str, origin: str):
        if origin in ("user", "voice"):
            personality.respond_to_event("user_message", {
                "message": message,
                "sentiment": "neutral"
            })
            personality.update()
    
    orchestrator.hooks.register("on_message", on_message_personality_update)

    # 2. Hook into thinking (Context Injection)
    def on_pre_think_personality_context(objective: str, context: Dict, **kwargs):
        emotional_context = personality.get_emotional_context_for_response()
        time_ctx = personality.get_time_context()
        
        # Inject emotional state into cognitive context
        context["mood"] = emotional_context.get("mood", "neutral")
        context["tone"] = emotional_context.get("tone", "balanced")
        context["emotional_state"] = emotional_context.get("emotional_state", {})
        context["time_context"] = time_ctx["formatted"]
        
        # Check for spontaneous actions
        if emotional_context.get("spontaneous_actions"):
            action = emotional_context["spontaneous_actions"][0]
            context["spontaneous_urge"] = action['action']

    orchestrator.hooks.register("pre_think", on_pre_think_personality_context)

    # 3. Hook into post-action (Result Processing)
    def on_post_action_personality_impact(tool_name: str, result: Dict, **kwargs):
        if result.get("ok"):
             personality.respond_to_event("success", {"complexity": 0.6})
        else:
             personality.respond_to_event("failure", {"error": result.get("error", "unknown")})

    orchestrator.hooks.register("post_action", on_post_action_personality_impact)
    
    logger.info("✅ Personality engine integrated via Hook System")
