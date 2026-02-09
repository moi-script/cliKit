import os
import json
import sys
import requests
from dotenv import load_dotenv

# Optional: Color for Windows terminals
try:
    from colorama import init, Fore, Style
    init(autoreset=True)
    COLOR_USER = Fore.BLUE
    COLOR_AI = Fore.GREEN
    COLOR_THOUGHT = Fore.YELLOW
    COLOR_ERROR = Fore.RED
    RESET = Style.RESET_ALL
except ImportError:
    # Fallback if colorama isn't installed
    COLOR_USER = ""
    COLOR_AI = ""
    COLOR_THOUGHT = ""
    COLOR_ERROR = ""
    RESET = ""

# --- CONFIGURATION ---
load_dotenv()
API_KEY = os.getenv("OPENROUTER_API_KEY")
API_URL = "https://openrouter.ai/api/v1/chat/completions"
# Use a model that supports reasoning (or fallback to standard)
MODEL_NAME = "openrouter/pony-alpha" 

if not API_KEY:
    print(f"{COLOR_ERROR}❌ Error: OPENROUTER_API_KEY not found in .env{RESET}")
    sys.exit(1)

def chat_session():
    print(f"{COLOR_AI}🚀 OpenRouter Reasoning Terminal (Model: {MODEL_NAME})")
    print(f"Type 'exit' or 'quit' to stop.{RESET}\n")

    # Conversation history
    messages = []

    while True:
        try:
            user_input = input(f"{COLOR_USER}(You) > {RESET}").strip()
            
            if user_input.lower() in ['exit', 'quit']:
                print("👋 Goodbye!")
                break
            
            if not user_input:
                continue

            # Add user message to history
            messages.append({"role": "user", "content": user_input})

            print(f"{COLOR_THOUGHT}✨ Thinking...{RESET}", end="\r")

            # --- API CALL ---
            payload = {
                "model": MODEL_NAME,
                "messages": messages,
                "reasoning": {"enabled": True} # Enable reasoning logic
            }
            
            headers = {
                "Authorization": f"Bearer {API_KEY}",
                "Content-Type": "application/json",
                "HTTP-Referer": "http://localhost:8000", # OpenRouter requires referer
                "X-Title": "Reasoning-CLI"
            }

            response = requests.post(API_URL, headers=headers, data=json.dumps(payload))
            
            if response.status_code != 200:
                print(f"\n{COLOR_ERROR}❌ Error {response.status_code}: {response.text}{RESET}")
                continue

            data = response.json()
            choice = data['choices'][0]['message']
            
            # --- EXTRACT CONTENT & REASONING ---
            ai_content = choice.get('content', '')
            reasoning = choice.get('reasoning_details', None) # Capture reasoning if present

            print(" " * 20, end="\r") # Clear "Thinking..." line

            # 1. Print Reasoning (The "Thought Process") if available
            if reasoning:
                print(f"\n{COLOR_THOUGHT}💭 [Reasoning Process]:")
                print(f"{reasoning}{RESET}\n")
                print("-" * 40)

            # 2. Print Final Answer
            print(f"{COLOR_AI}🤖 {ai_content}{RESET}\n")

            # 3. Preserve History (Crucial for the "Turn 2" logic you showed)
            # We save the assistant's message back to history, INCLUDING reasoning details
            # so the model remembers its own train of thought.
            assistant_msg = {
                "role": "assistant",
                "content": ai_content
            }
            if reasoning:
                assistant_msg["reasoning_details"] = reasoning
            
            messages.append(assistant_msg)

        except KeyboardInterrupt:
            print("\n👋 Exiting...")
            break
        except Exception as e:
            print(f"\n{COLOR_ERROR}❌ System Error: {e}{RESET}")

if __name__ == "__main__":
    chat_session()