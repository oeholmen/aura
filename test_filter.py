from core.synthesis import cure_personality_leak

test_cases = [
    "I found that the issue is simple.",
    "As an AI assistant, I can help with that.",
    "Objective: Test. Result: Success.",
    "Aura: \"Hello?\"",
    "Hello! How can I assist you today?",
    "I have processed your request. Here is the answer.",
]

for tc in test_cases:
    print(f"INPUT: '{tc}'")
    output = cure_personality_leak(tc)
    print(f"OUTPUT: '{output}'")
    print("-" * 20)
