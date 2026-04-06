"""core/voice — Substrate-Driven Voice System

The voice system sits between Aura's consciousness substrate and the LLM.
The substrate is the mind. The LLM is the voicebox. This package ensures
the mind controls what the voicebox says.

Key components:
  - speech_profile.py        — Compiles substrate state → hard linguistic constraints
  - response_shaper.py       — Post-LLM enforcement of speech constraints
  - natural_followup.py      — Organic follow-up behavior (curiosity, topic shifts)
  - substrate_voice_engine.py — The executive controller that orchestrates all of the above
  - stable_voice_pipeline.py — TTS/STT pipeline (audio I/O)
  - voice_bridge.py          — Conversation bridge for voice mode
"""
