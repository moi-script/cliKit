import os
import re
import sys
import time
import requests
from pathlib import Path
from typing import List, Tuple, Dict
from dotenv import load_dotenv
from openai import OpenAI

# ==============================================================================
# DYNAMIC MODEL SCOUTER
# ==============================================================================

class OpenRouterScouter:
    @staticmethod
    def fetch_fastest_model(api_key: str) -> str:
        print("🔍 Scouting OpenRouter for the fastest available engines...")
        try:
            url = "https://openrouter.ai/api/v1/models"
            headers = {"Authorization": f"Bearer {api_key}"}
            response = requests.get(url, headers=headers, timeout=10)
            
            if response.status_code != 200:
                return "google/gemini-2.0-flash-lite:nitro"

            models = response.json().get('data', [])
            candidates = []
            
            for m in models:
                perf = m.get('top_provider', {})
                throughput = perf.get('throughput', 0)
                
                # Filter for "Flash", "Lite", or "Fast" variants
                is_fast = any(x in m['id'].lower() for x in ['flash', 'lite', 'fast', 'speed'])
                
                if is_fast:
                    candidates.append({
                        'id': m['id'],
                        'throughput': throughput,
                        'latency': perf.get('latency', 999)
                    })

            # Sort by Throughput (High to Low), then Latency (Low to High)
            candidates.sort(key=lambda x: (-x['throughput'], x['latency']))

            if candidates:
                best = candidates[0]['id']
                # :nitro forces OpenRouter to ignore cost and pick the fastest provider
                return f"{best}:nitro"
            
            return "google/gemini-2.0-flash-lite:nitro"
        except Exception as e:
            print(f"⚠️ Scouting failed: {e}")
            return "google/gemini-2.0-flash-lite:nitro"

# ==============================================================================
# AGENT CORE
# ==============================================================================

class VibeTerminal:
    def __init__(self):
        load_dotenv()
        # Using the key name you specified: OPEN_ROUTER_KEY
        self.api_key = os.getenv("OPENROUTER_API_KEY")
        if not self.api_key:
            print("❌ Error: OPEN_ROUTER_KEY not found in .env")
            sys.exit(1)

        self.model_name = OpenRouterScouter.fetch_fastest_model(self.api_key)
        self.client = OpenAI(
            base_url="https://openrouter.ai/api/v1",
            api_key=self.api_key,
            default_headers={"X-Title": "VibeCLI-Scouter"}
        )
        self.history = []

    def send_message(self, message: str):
        self.history.append({"role": "user", "content": message})
        try:
            # FIX: Removed 'quantizations' to prevent 404 "No endpoints found"
            response = self.client.chat.completions.create(
                model=self.model_name,
                messages=self.history,
                extra_body={
                    "provider": {
                        "sort": "throughput" 
                    }
                }
            )
            res_text = response.choices[0].message.content
            # Filter Reasoning/Thinking if the scouted model is a reasoning model
            res_text = re.sub(r"<think>.*?</think>", "", res_text, flags=re.DOTALL)
            self.history.append({"role": "assistant", "content": res_text})
            return res_text
        except Exception as e:
            print(f"❌ API Error: {e}")
            return None

    def run(self):
        print(f"\n🚀 VibeCLI: [SCOUTER ACTIVE]")
        print(f"📡 Current Fastest Target: {self.model_name}")
        print("-" * 50)
        
        while True:
            prompt = input("\n(You) > ")
            if prompt.lower() in ['exit', 'quit']: break
            if not prompt.strip(): continue
            
            print("✨ Thinking...")
            start = time.time()
            res = self.send_message(prompt)
            if res:
                print(f"🤖 AI [{time.time()-start:.2f}s]: {res.strip()}")

if __name__ == "__main__":
    VibeTerminal().run()