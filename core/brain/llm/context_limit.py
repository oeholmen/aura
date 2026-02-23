"""Context Limit Manager.
Prevents the 'Titan' from choking on too much text.
"""
import logging

logger = logging.getLogger("Core.Context")

class ContextManager:
    def __init__(self, max_tokens: int = 8000):
        # Rough estimate: 1 token ~= 4 characters
        self.char_limit = max_tokens * 3.5 
        
    def prune(self, history: str, system_prompt: str) -> str:
        """Trims the history to fit within the model's context window,
        ALWAYS preserving the System Prompt (Identity).
        """
        total_len = len(history) + len(system_prompt)
        
        if total_len < self.char_limit:
            return history
            
        # We need to cut. Calculate how much to remove.
        excess = total_len - self.char_limit
        # Add a safety buffer (500 chars)
        cut_amount = int(excess + 500)
        
        # We cut from the BEGINNING of history (oldest stuff), 
        # but we must never touch the System Prompt.
        
        # Simple heuristic: Find the first newline after the cut point 
        # to avoid cutting words in half.
        pruned_history = history[cut_amount:]
        first_newline = pruned_history.find('\n')
        if first_newline != -1:
            pruned_history = pruned_history[first_newline+1:]
            
        logger.warning("Context Overflow detected. Pruned %s chars from short-term memory.", cut_amount)
        return f"[...Earlier conversation forgotten...]\n{pruned_history}"

# Usage helper
context_guard = ContextManager()
