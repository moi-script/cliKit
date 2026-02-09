"""
VibeCLI v3.5 - Integrated Context AI
SDK: openai (OpenRouter Compatible)

INTEGRATION:
- Embeds 'Repo Reader' logic to generate a full codebase string on startup.
- Concatenates that string into the AI's context window.
- Retains all Pro features: Backups, Diff View, Safety Checks, Streaming.

USAGE:
   python vibe_integrated.py [target_directory]
"""

import os
import re
import sys
import json
import time
import shutil
import difflib
import subprocess
import argparse
import fnmatch
from pathlib import Path
from datetime import datetime
from typing import List, Tuple, Set, Dict, Optional, Any

# Third-party imports
try:
    from dotenv import load_dotenv
    from openai import OpenAI
except ImportError:
    print("❌ Missing dependencies. Run: pip install openai python-dotenv")
    sys.exit(1)

# Import the scrape_contents function
try:
    from file_reader import scrape_contents
except ImportError:
    print("❌ Missing file_reader module. Ensure file_reader.py is in the same directory.")
    sys.exit(1)

# ==============================================================================
# CONFIGURATION
# ==============================================================================

MODEL_NAME = "google/gemini-2.5-flash-lite:nitro"

# Security & Limits
DANGEROUS_COMMANDS = {'rm', 'del', 'format', 'mkfs', 'dd', 'shutdown', 'reboot'}
MAX_HISTORY_TURNS = 15

# ==============================================================================
# VIBE UTILS & SYSTEM PROMPT
# ==============================================================================

SYSTEM_INSTRUCTION = """
You are VibeCLI, an elite AI software engineer.
You have been provided with the **FULL CONTEXT** of the user's codebase.

YOUR MISSION: 
1. Analyze the user's request.
2. You already see the files, so you rarely need to use READ unless a file changed recently.
3. MODIFY files to implement features or fix bugs using WRITE.

PROTOCOL (Strict Command Blocks):

>>> WRITE {file_path}
{full_file_content}
<<<

>>> READ {file_path} <<<

>>> DELETE {file_path} <<<

>>> RUN {shell_command} <<<

>>> INSTALL {package_manager} {package_name} <<<

>>> SHADCN {component_name} <<<

RULES:
- When using WRITE, provide the **COMPLETE** file content. Never use comments like "// ... existing code ...".
- Always check if a file exists (you can see it in the context) before creating it.
- Use relative paths from the project root (e.g., "src/App.tsx" not "/full/path/to/src/App.tsx").
- For multi-step tasks, execute operations in logical order: READ -> WRITE -> DELETE -> RUN.
"""

class VibeUtils:
    @staticmethod
    def is_dangerous(command: str) -> bool:
        parts = command.split()
        if not parts: return False
        if parts[0].lower() in DANGEROUS_COMMANDS: return True
        if "rm" in command and ("-r" in command or "/ " in command): return True
        return False

    @staticmethod
    def get_diff(old_content: str, new_content: str, filename: str) -> str:
        diff = difflib.unified_diff(
            old_content.splitlines(),
            new_content.splitlines(),
            fromfile=f"a/{filename}",
            tofile=f"b/{filename}",
            lineterm=""
        )
        return "\n".join([
            f"\033[92m{line}\033[0m" if line.startswith('+') else 
            f"\033[91m{line}\033[0m" if line.startswith('-') else 
            f"\033[94m{line}\033[0m" if line.startswith('^') else line 
            for line in diff
        ])

class PackageManager:
    def __init__(self, root_dir: Path):
        self.root_dir = root_dir
        self.manager = self._detect()

    def _detect(self) -> str:
        if (self.root_dir / "bun.lockb").exists(): return "bun"
        if (self.root_dir / "pnpm-lock.yaml").exists(): return "pnpm"
        if (self.root_dir / "yarn.lock").exists(): return "yarn"
        return "npm"

    def get_install_cmd(self, package: str) -> str:
        cmds = {
            "npm": f"npm install {package}",
            "pnpm": f"pnpm add {package}",
            "yarn": f"yarn add {package}",
            "bun": f"bun add {package}"
        }
        return cmds.get(self.manager, cmds["npm"])

# ==============================================================================
# THE AGENT
# ==============================================================================

class VibeAgent:
    def __init__(self, target_dir: str, skip_context: bool = False):
        load_dotenv()
        self.api_key = os.getenv("OPENROUTER_API_KEY")
        if not self.api_key:
            print("❌ Error: OPENROUTER_API_KEY not found in .env")
            sys.exit(1)

        self.root_dir = Path(target_dir).resolve()
        if not self.root_dir.exists():
            self.root_dir.mkdir(parents=True)

        self.pkg_manager = PackageManager(self.root_dir)
        self.backup_dir = self.root_dir / ".vibe" / "backups"
        self.backup_dir.mkdir(parents=True, exist_ok=True)

        self.client = OpenAI(
            base_url="https://openrouter.ai/api/v1",
            api_key=self.api_key,
            default_headers={"X-Title": "VibeCLI-Integrated"}
        )
        
        # --- CONTEXT INJECTION USING scrape_contents ---
        self.messages = [{"role": "system", "content": SYSTEM_INSTRUCTION}]
        
        if not skip_context:
            print(f"🔍 Scanning repo: {self.root_dir}...")
            try:
                repo_context = scrape_contents(self.root_dir)
                char_count = len(repo_context)
                print(f"✅ Context Loaded. ({char_count:,} characters)")
                
                # Add context as a separate system message
                self.messages.append({
                    "role": "system", 
                    "content": f"HERE IS THE CURRENT REPO CONTEXT:\n\n{repo_context}"
                })
            except Exception as e:
                print(f"⚠️  Warning: Failed to load repo context: {e}")
                print("Continuing without initial context...")
        else:
            print("⚠️  Skipping initial context load (--no-context flag)")

    def _prune_history(self):
        # Keep System Prompts (0, 1) and remove oldest conversation pairs
        if len(self.messages) > MAX_HISTORY_TURNS * 2:
            # Keep first 2 system messages, delete oldest user/assistant pairs
            system_msgs = self.messages[:2]
            conversation = self.messages[2:]
            # Keep last N turns
            self.messages = system_msgs + conversation[-(MAX_HISTORY_TURNS * 2):]

    # --- HANDLERS ---

    def handle_read(self, rel_path: str) -> str:
        path = self.root_dir / rel_path
        if not path.exists(): 
            return f"SYSTEM: Error - File {rel_path} does not exist."
        try:
            content = path.read_text(encoding='utf-8', errors='ignore')
            return f"SYSTEM: Content of {rel_path}:\n{content}"
        except Exception as e: 
            return f"SYSTEM: Read error: {e}"

    def handle_write(self, rel_path: str, new_content: str) -> str:
        path = self.root_dir / rel_path
        exists = path.exists()
        
        print(f"\n📝 [REQUEST] WRITE: {rel_path}")
        
        if exists:
            try:
                old_content = path.read_text(encoding='utf-8')
                print("\n--- DIFF CHECK ---")
                print(VibeUtils.get_diff(old_content, new_content, rel_path))
                print("------------------\n")
            except: 
                pass

        if input(">> Apply changes? (y/n): ").lower() != 'y':
            return f"SYSTEM: User denied write to {rel_path}"

        try:
            if exists:
                ts = datetime.now().strftime("%Y%m%d_%H%M%S")
                safe_name = rel_path.replace("/", "_").replace("\\", "_")
                bak = self.backup_dir / f"{safe_name}_{ts}.bak"
                shutil.copy2(path, bak)
                print(f"💾 Backup saved: {bak.name}")

            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(new_content, encoding='utf-8')
            print(f"✅ Successfully wrote {rel_path}")
            return f"SYSTEM: File {rel_path} updated successfully."
        except Exception as e: 
            return f"SYSTEM: Write error: {e}"

    def handle_run(self, command: str) -> str:
        print(f"\n⚡ [REQUEST] RUN: {command}")
        if VibeUtils.is_dangerous(command):
            if input("🚨 DANGEROUS! Confirm? (type 'confirm'): ") != "confirm": 
                return "SYSTEM: Blocked dangerous command."
        
        if input(">> Execute? (y/n): ").lower() != 'y': 
            return "SYSTEM: User denied command execution."

        try:
            res = subprocess.run(
                command, 
                shell=True, 
                cwd=self.root_dir, 
                capture_output=True, 
                text=True,
                timeout=300  # 5 minute timeout
            )
            print(f"Output:\n{res.stdout}")
            if res.stderr: 
                print(f"Error:\n{res.stderr}")
            return f"SYSTEM: Code: {res.returncode}\nOut: {res.stdout}\nErr: {res.stderr}"
        except subprocess.TimeoutExpired:
            return "SYSTEM: Command timeout (5 minutes)"
        except Exception as e: 
            return f"SYSTEM: Error: {e}"

    def handle_shadcn(self, component: str) -> str:
        print(f"\n🎨 [REQUEST] SHADCN: {component}")
        return self.handle_run(f"npx shadcn@latest add {component} -y")

    def handle_install(self, manager: str, pkg: str) -> str:
        print(f"\n📦 [REQUEST] INSTALL: {pkg}")
        return self.handle_run(self.pkg_manager.get_install_cmd(pkg))

    def handle_delete(self, rel_path: str) -> str:
        path = self.root_dir / rel_path
        print(f"\n🗑️ [REQUEST] DELETE: {rel_path}")
        
        if not path.exists():
            return f"SYSTEM: Error - File {rel_path} does not exist."
        
        if input(">> Delete this file? (y/n): ").lower() != 'y':
            return f"SYSTEM: User denied delete of {rel_path}"
        
        try:
            # Backup before deletion
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            safe_name = rel_path.replace("/", "_").replace("\\", "_")
            bak = self.backup_dir / f"{safe_name}_{ts}.bak"
            shutil.copy2(path, bak)
            print(f"💾 Backup saved: {bak.name}")
            
            path.unlink()
            print(f"✅ Successfully deleted {rel_path}")
            return f"SYSTEM: File {rel_path} deleted successfully."
        except Exception as e:
            return f"SYSTEM: Delete error: {e}"

    # --- MAIN LOOP ---

    def process_tool_calls(self, response_text: str) -> Tuple[List[str], bool]:
        feedback = []
        action_taken = False
        
        patterns = {
            'WRITE': re.compile(r">>>\s*WRITE\s+(.+?)\s*\n(.*?)<<<", re.DOTALL),
            'READ': re.compile(r">>>\s*READ\s+(.+?)\s*<<<", re.DOTALL),
            'RUN': re.compile(r">>>\s*RUN\s+(.+?)\s*<<<", re.DOTALL),
            'INSTALL': re.compile(r">>>\s*INSTALL\s+(\w+)\s+(.+?)\s*<<<", re.DOTALL),
            'SHADCN': re.compile(r">>>\s*SHADCN\s+(.+?)\s*<<<", re.DOTALL),
            'DELETE': re.compile(r">>>\s*DELETE\s+(.+?)\s*<<<", re.DOTALL)
        }

        # Execution Order: READ -> WRITE -> DELETE -> RUN -> OTHERS
        for path in patterns['READ'].findall(response_text):
            feedback.append(self.handle_read(path.strip()))
            action_taken = True

        for path, content in patterns['WRITE'].findall(response_text):
            feedback.append(self.handle_write(path.strip(), content.strip()))
            action_taken = True

        for path in patterns['DELETE'].findall(response_text):
            feedback.append(self.handle_delete(path.strip()))
            action_taken = True

        for cmd in patterns['RUN'].findall(response_text):
            feedback.append(self.handle_run(cmd.strip()))
            action_taken = True

        for mgr, pkg in patterns['INSTALL'].findall(response_text):
            feedback.append(self.handle_install(mgr.strip(), pkg.strip()))
            action_taken = True

        for comp in patterns['SHADCN'].findall(response_text):
            feedback.append(self.handle_shadcn(comp.strip()))
            action_taken = True

        return feedback, action_taken

    def run(self):
        print(f"\n🚀 VibeCLI Integrated | {MODEL_NAME}")
        print(f"📂 Root: {self.root_dir}")
        print(f"📦 Package Manager: {self.pkg_manager.manager}")
        print("--------------------------------------------------")

        while True:
            try:
                user_input = input("\n(You) > ")
                if user_input.lower() in ['exit', 'quit']: 
                    print("👋 Goodbye!")
                    break
                if not user_input.strip(): 
                    continue

                self.messages.append({"role": "user", "content": user_input})
                self._prune_history()

                print("✨ Thinking...", end="", flush=True)
                
                stream = self.client.chat.completions.create(
                    model=MODEL_NAME,
                    messages=self.messages,
                    temperature=0.1,
                    stream=True
                )

                print("\r", end="")
                full_response = ""
                
                for chunk in stream:
                    content = chunk.choices[0].delta.content or ""
                    if content:
                        full_response += content
                        # Only print if we haven't hit a command block yet
                        if ">>>" not in full_response:
                            print(content, end="", flush=True)

                self.messages.append({"role": "assistant", "content": full_response})

                # Display clean response (without command blocks)
                clean_display = re.sub(r">>>.*?<<<", "", full_response, flags=re.DOTALL).strip()
                if clean_display and ">>>" in full_response:
                    print(f"\n🤖 AI: {clean_display}")

                # Process any tool calls
                feedback, acted = self.process_tool_calls(full_response)

                if acted:
                    tool_output = "SYSTEM: Results:\n" + "\n".join(feedback)
                    self.messages.append({"role": "system", "content": tool_output})
                    print("\n🔄 Processing next steps...")
                    
                    # Get follow-up response
                    followup = self.client.chat.completions.create(
                        model=MODEL_NAME,
                        messages=self.messages,
                        temperature=0.1
                    )
                    f_text = followup.choices[0].message.content
                    self.messages.append({"role": "assistant", "content": f_text})
                    
                    clean_f = re.sub(r">>>.*?<<<", "", f_text, flags=re.DOTALL).strip()
                    if clean_f: 
                        print(f"🤖 AI: {clean_f}")
                    
                    # Process any additional tool calls
                    self.process_tool_calls(f_text)

            except KeyboardInterrupt:
                print("\n\n👋 Exiting...")
                break
            except Exception as e:
                print(f"\n❌ Error: {e}")
                import traceback
                traceback.print_exc()

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="VibeCLI Integrated - AI-Powered Code Assistant")
    parser.add_argument("path", nargs="?", default=".", help="Project root directory (default: current directory)")
    parser.add_argument("--no-context", action="store_true", help="Skip initial codebase scanning")
    args = parser.parse_args()
    
    agent = VibeAgent(args.path, skip_context=args.no_context)
    agent.run()