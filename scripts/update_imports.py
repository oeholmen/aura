import os
import re

MAPPING = {
    "core.brain.cognitive_engine": "core.brain.cognitive_engine",
    "core.brain.cognitive_amplification": "core.brain.cognitive_amplification",
    "core.brain.cognitive_patch": "core.brain.cognitive_patch",
    "core.brain.cognition_models": "core.brain.cognition_models",
    "core.brain.aura_persona": "core.brain.aura_persona",
    "core.brain.personality_engine": "core.brain.personality_engine",
    "core.brain.personality_integration": "core.brain.personality_integration",
    "core.brain.personality_kernel": "core.brain.personality_kernel",
    "core.brain.persona_adapter": "core.brain.persona_adapter",
    "core.brain.persona_integration": "core.brain.persona_integration",
    "core.brain.cognition": "core.brain.cognition",
    "core.brain.cognitive": "core.brain.cognitive",
    "core.brain.consciousness": "core.brain.consciousness",
    "core.memory.knowledge_graph": "core.memory.knowledge_graph",
    "core.memory.knowledge_ledger": "core.memory.knowledge_ledger",
    "core.memory.learning": "core.memory.learning",
    "core.memory.data_engine": "core.memory.data_engine",
    "core.memory.knowledge": "core.memory.knowledge",
    "core.resilience.resilience.resilience.circuit_breaker": "core.resilience.resilience.resilience.circuit_breaker",
    "core.resilience.resilience.resilience.immune_system": "core.resilience.resilience.resilience.immune_system",
    "core.resilience.resilience.resilience.antibody": "core.resilience.resilience.resilience.antibody",
    "core.resilience.resilience.resilience.code_validation": "core.resilience.resilience.resilience.code_validation",
    "core.resilience.resilience.resilience.code_verifier": "core.resilience.resilience.resilience.code_verifier",
    "core.resilience.resilience.resilience.degradation": "core.resilience.resilience.resilience.degradation",
    "core.resilience.resilience.resilience.graceful_degradation": "core.resilience.resilience.resilience.graceful_degradation",
    "core.resilience.resilience.resilience.fail_controller": "core.resilience.resilience.resilience.fail_controller",
    "core.resilience.resilience.resilience.system_integrity": "core.resilience.resilience.resilience.system_integrity",
    "core.resilience.resilience.resilience.safety_net": "core.resilience.resilience.resilience.safety_net",
    "core.resilience.resilience.resilience.silent_failover": "core.resilience.resilience.resilience.silent_failover",
    "core.resilience.resilience.resilience": "core.resilience.resilience.resilience.resilience",
    "core.brain.llm": "core.brain.llm"
}

# Special case for "from core import ..."
FROM_CORE_MAPPINGS = {
    m.split('.')[-1]: m for m in MAPPING.keys()
}

def update_file(filepath):
    with open(filepath, 'r') as f:
        content = f.read()
    
    original_content = content
    
    # 1. Replace explicit core.module
    for old, new in MAPPING.items():
        # Match core.module but not core.module_something
        pattern = r'\b' + re.escape(old) + r'\b'
        content = re.sub(pattern, new, content)
    
    # 2. Replace from core import module
    # Matches: from core import module1, module2
    def replace_from_core(match):
        imports = match.group(1).split(',')
        new_lines = []
        for imp in imports:
            imp_name = imp.strip().split(' as ')[0].strip()
            if imp_name in FROM_CORE_MAPPINGS:
                full_old = FROM_CORE_MAPPINGS[imp_name]
                full_new = MAPPING[full_old]
                # If there are other imports in the same line, we might need to split them
                # But for simplicity, we replace the whole line if it's just this one
                if len(imports) == 1:
                    return f"from {full_new.rsplit('.', 1)[0]} import {imp.strip()}"
                else:
                    # Collect them for later splitting if needed, but let's try a simpler approach first
                    pass 
        return match.group(0) # Fallback

    # Simple approach for 'from core import ...'
    for mod_name, full_old in FROM_CORE_MAPPINGS.items():
        full_new = MAPPING[full_old]
        new_base = full_new.rsplit('.', 1)[0]
        # Match: from core import module
        content = re.sub(r'from core import ([^#\n]*)' + re.escape(mod_name) + r'\b', 
                         r'from ' + new_base + r' import \1' + mod_name, content)
        # Note: This regex is a bit simplistic for multi-import lines.
    
    if content != original_content:
        with open(filepath, 'w') as f:
            f.write(content)
        print(f"Updated {filepath}")

def main():
    for root, dirs, files in os.walk('.'):
        for file in files:
            if file.endswith('.py'):
                update_file(os.path.join(root, file))

if __name__ == "__main__":
    main()
