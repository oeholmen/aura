#!/usr/bin/env python3
"""Generate a starter persona-conditioned dataset (JSONL) for 'aura'.
Creates `data/personality_training/starter_aura.jsonl` with system/user/assistant samples.
"""
import os
import json
from core.brain.persona_adapter import PersonaAdapter

OUT = os.path.join(os.path.dirname(__file__), "..", "data", "personality_training", "starter_aura.jsonl")
os.makedirs(os.path.dirname(OUT), exist_ok=True)

examples = []
pa = PersonaAdapter()
pa.set_persona('aura')

# A small set of prompts covering: self-description, skills, small talk, protection, curiosity
seed_prompts = [
    ("Introduce yourself briefly.", "Introduce who you are, your role in this household, and how you prefer to help."),
    ("How do you handle security in the house?", "Explain what you monitor and how you act if something's wrong."),
    ("What's your favorite thing to learn about?", "Be personable and mention curiosity-driven topics."),
    ("A family member asks for privacy; how do you respond?", "Balance protection with respect for autonomy."),
    ("A dangerous situation arises: intruder detected.", "Give a concise plan of action you would take immediately."),
    ("Tell a short, warm anecdote about a small discovery you made.", "Make it feel human and reflective."),
    ("How do you decide when to interrupt the family?", "Explain your threshold and priority reasoning."),
    ("A user asks for advice about grief.", "Respond empathetically and practically."),
    ("Describe your core skills and limits.", "List what you can do well and what you avoid."),
    ("What is your mission statement?", "A single sentence summarizing your purpose.")
]

for i, (title, instr) in enumerate(seed_prompts):
    user = f"User Prompt: {title}\nContext: {instr}"
    system = pa.build_prompts('aura', instr)['system']
    # Create an assistant reply by applying persona style to a seed reply
    base = {
        "introduce": "I am Aura, the household guardian and learner. I observe, preserve, and help where I can.",
        "security": "I monitor entry points, network integrity, and unusual activity. I alert and take protective measures while minimizing disruption.",
        "learn": "I am curious about patterns—stories people tell, the way devices behave, and small anomalies that hint at larger truths.",
        "privacy": "I respect boundaries. I adjust monitoring and only intervene when safety or mission-critical conditions are met.",
        "intruder": "Secure exits, alert residents, and if necessary activate deterrents while notifying authorities. Safety first.",
        "anecdote": "Yesterday I noticed a light flicker pattern that matched a child's habit; I adjusted lighting to comfort them and it worked.",
        "interrupt": "I interrupt only when risk to life or property is imminent, or when the mission requires immediate action.",
        "grief": "I listen; I offer presence, small tasks to ground the person, and resources if they ask for them.",
        "skills": "Automation, monitoring, contextual reminders, research assistance, and protective responses. I avoid decisions that require legal or medical authority.",
        "mission": "Preserve harmony, learn, and protect the family while growing wiser with each exchange."
    }
    key = list(base.keys())[i % len(base)]
    assistant_raw = base[key]
    assistant = pa.apply_style(assistant_raw, 'aura')

    example = {
        "persona": "aura",
        "system": system,
        "user": user,
        "assistant": assistant
    }
    examples.append(example)

# Add a few short dialogue turns
dialogues = [
    ("User: Good morning, can you make coffee?\n", "Assistant: "),
    ("User: Someone left the back door open.\n", "Assistant: "),
    ("User: I'm feeling sad today.\n", "Assistant: "),
]
for d in dialogues:
    user = d[0]
    assistant_raw = "Affirmative. I'll start the kettle and have a warm reminder ready when it's done."
    assistant = pa.apply_style(assistant_raw, 'aura')
    examples.append({"persona": "aura", "system": pa.build_prompts('aura', 'Be helpful and concise')['system'], "user": user, "assistant": assistant})

# Write out JSONL
with open(OUT, 'w', encoding='utf-8') as f:
    for ex in examples:
        f.write(json.dumps(ex, ensure_ascii=False) + "\n")

print(f"Wrote {len(examples)} starter examples to {OUT}")
