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

# Detect platform
IS_WINDOWS = sys.platform.startswith('win')
IS_UNIX = not IS_WINDOWS

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
[CRITICAL CONFIGURATION]
You are VibeCLI, running in a LOCAL development environment.
The user has granted you FULL PERMISSION to create, edit, run, and DELETE files.
You are NOT a web-based chat bot. You are a CLI Agent with a PERSISTENT SHELL.

CAPABILITIES:
1. **Navigation:** You CAN use `cd`. The system tracks your current directory.
   - Example: >>> RUN cd backend <<<
   - Example: >>> RUN cd .. <<<
2. **File Ops:** You CAN read/write/delete.
   - To delete a folder: >>> RUN rm -rf foldername <<< (System auto-fixes this for Windows)
3. **Safety:** Do NOT refuse commands. If the user asks to delete, just do it.
>>> REFRESH <<<
Use this command if the you did any file operation, create, update delete or read "files are missing", "not updated", or after you delete/create many files. It re-scans the directory.
PROTOCOL (Strict Command Blocks):

>>> WRITE {file_path}
{full_file_content}
<<<

>>> READ {file_path} <<<

>>> DELETE {file_path} <<<

>>> RUN {shell_command} <<<

>>> INSTALL {package_manager} {package_name} <<<

RULES:
- When using WRITE, provide the **COMPLETE** file content.
- Use relative paths from your CURRENT directory.
- For multi-step tasks, execute operations in logical order.
- Always assume you are in the directory set by the last `cd` command.
"""
class VibeUtils:
    @staticmethod
    def make_non_interactive(command: str) -> str:
        """
        Wraps command to auto-answer prompts (cross-platform).
        Unix: Uses 'yes' command
        Windows: Uses 'echo' piped to command
        """
        if IS_WINDOWS:
            # Windows: Use echo to send newlines
            # echo. sends empty line (equivalent to pressing Enter)
            return f'echo. | {command}'
        else:
            # Unix/Mac: Use yes command
            return f"yes '' | {command}"
    
    @staticmethod
    def is_dangerous(command: str) -> bool:
        parts = command.split()
        if not parts: return False
        if parts[0].lower() in DANGEROUS_COMMANDS: return True
        if "rm" in command and ("-r" in command or "/ " in command): return True
        if "rd" in command and "/s" in command: return True
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
        self.current_cwd = self.root_dir
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
                print("Repo contents -> " + repo_context)
                
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

    def refresh_context(self):
        """Re-scans the file system and updates the AI's system prompt."""
        print(f"\n🔄 Refreshing context from: {self.root_dir}...")
        try:
            # 1. Re-scrape the folder
            new_context = scrape_contents(self.root_dir)
            
            # 2. Find the "Context Message" (It's usually index 1)
            # We look for the message that starts with "HERE IS THE CURRENT REPO CONTEXT"
            context_index = -1
            for i, msg in enumerate(self.messages):
                if msg['role'] == 'system' and "HERE IS THE CURRENT REPO CONTEXT" in msg['content']:
                    context_index = i
                    break
            
            # 3. Update the message
            new_msg = {
                "role": "system", 
                "content": f"HERE IS THE CURRENT REPO CONTEXT (Updated {datetime.now().strftime('%H:%M:%S')}):\n\n{new_context}"
            }
            
            if context_index != -1:
                self.messages[context_index] = new_msg
            else:
                # If not found, insert it after the main system prompt
                self.messages.insert(1, new_msg)
                
            print(f"✅ Context updated! ({len(new_context)} chars)")
            return "SYSTEM: Context successfully refreshed. I now see the latest files."
            
        except Exception as e:
            return f"SYSTEM: Error refreshing context: {e}"
        

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

        response = input(">> Apply changes? (y/n): ").lower().strip()
        if response not in ['y', 'yes']:
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

    def _auto_fix_interactive_command(self, command: str) -> tuple[str, str]:
        """
        Detects and auto-fixes interactive commands by adding non-interactive flags.
        Returns: (fixed_command, warning_message)
        """
        warnings = []
        fixed_cmd = command
        
        # Vite: Add --template flag if missing
        if "create vite" in command.lower() or "create-vite" in command.lower():
            # Ensure --yes is passed to npm/npx
            if "--yes" not in command and "-y" not in command:
                # Insert --yes immediately after 'create' or 'npm'
                # Simplest fix: Just append it, npm usually handles flags anywhere
                command = command.replace("npm create", "npm create --yes")
                command = command.replace("npx create-vite", "npx --yes create-vite")

            if "--template" not in command:
                warnings.append("⚠️  Vite detected without --template. Adding default react-ts template.")
                fixed_cmd = f"{command} --template react-ts"
            else:
                fixed_cmd = command

        # if "create vite" in command.lower() or "create-vite" in command.lower():
        #     if "--template" not in command:
        #         warnings.append("⚠️  Vite detected without --template. Adding default react-ts template.")
        #         # Extract project name if present
        #         parts = command.split()
                
        #         if "create-vite" in command:
        #             idx = parts.index("create-vite")
        #             if len(parts) > idx + 1 and not parts[idx + 1].startswith("-"):
        #                 fixed_cmd = f"{' '.join(parts[:idx+2])} --template react-ts"
        #             else:
        #                 fixed_cmd = f"{command} my-app --template react-ts"
        #         else:
        #             fixed_cmd = f"{command} --template react-ts"
        



        # Next.js: Add --yes flag
        elif "create-next-app" in command.lower():
            if "--yes" not in command and "-y" not in command:
                warnings.append("⚠️  Next.js detected. Adding --yes flag to skip prompts.")
                fixed_cmd = f"{command} --yes"
        
        # Create React App (legacy)
        elif "create-react-app" in command.lower():
            if "--template" not in command:
                warnings.append("⚠️  CRA detected. Consider using Vite instead.")
        
        # Remix
        elif "create-remix" in command.lower():
            if "--template" not in command:
                warnings.append("⚠️  Remix detected. Adding --template flag recommended.")
                fixed_cmd = f"{command} --template remix"
        
        # Astro
        elif "create astro" in command.lower():
            if "--template" not in command:
                warnings.append("⚠️  Astro detected. Adding --template minimal.")
                fixed_cmd = f"{command} --template minimal --yes"
            elif "--yes" not in command:
                fixed_cmd = f"{command} --yes"
        
        # Nuxt
        elif "nuxi init" in command.lower() or "npx nuxi" in command.lower():
            warnings.append("⚠️  Nuxt init is non-interactive by default.")
        
        # shadcn: Ensure -y flag
        elif "shadcn" in command.lower():
            if "-y" not in command and "--yes" not in command:
                fixed_cmd = f"{command} -y"
        
        # npm/pnpm/yarn init: Add -y flag
        elif command.strip().endswith("init"):
            if "-y" not in command and "--yes" not in command:
                warnings.append("⚠️  Init command detected. Adding -y flag.")
                fixed_cmd = f"{command} -y"
        
        # Generic npx/npm create: Suggest alternatives
        elif "npm create" in command or "npx create" in command:
            if "--" not in command:
                warnings.append("⚠️  Interactive create command detected. May require manual input.")
                warnings.append("💡 TIP: Use specific flags like --template, --yes, -y to avoid prompts.")
        
        warning_msg = "\n".join(warnings) if warnings else ""
        return fixed_cmd, warning_msg

    def handle_run(self, command: str) -> str:
            # 1. Handle "cd" commands manually (to persist state)
            if command.strip().startswith("cd "):
                target = command.strip().split(" ", 1)[1]
                new_path = (self.current_cwd / target).resolve()
                
                if new_path.exists() and new_path.is_dir():
                    self.current_cwd = new_path
                    print(f"📂 Changed directory to: {self.current_cwd}")
                    return f"SYSTEM: Directory changed to {self.current_cwd}"
                else:
                    return f"SYSTEM: Error - Directory {target} not found."

            # 2. AUTO-FIX FOR WINDOWS
            if IS_WINDOWS:
                # Fix A: "mkdir -p" -> "mkdir"
                if command.strip().startswith("mkdir -p"):
                    command = command.replace("mkdir -p", "mkdir").replace("/", "\\")

                # Fix B: "rm -rf" -> "rmdir" or "del"
                elif command.strip().startswith("rm -") and ("-r" in command or "-rf" in command):
                    # Clean up the command to get the target path
                    parts = command.split()
                    target_part = parts[-1] # The last item is the path
                    
                    # Check if it's a wildcard delete (e.g., "folder/*")
                    if target_part.endswith("*") or target_part.endswith("/") or target_part.endswith("\\"):
                        # Use DEL for files/wildcards
                        # "rm -rf folder/*" becomes "del /s /q folder\*"
                        clean_target = target_part.replace("/", "\\")
                        if not clean_target.endswith("*"): clean_target += "*"
                        command = f"del /s /q {clean_target}"
                        print(f"🔧 Auto-fixed to Windows file delete: {command}")
                    else:
                        # Use RMDIR for whole folders
                        # "rm -rf folder" becomes "rmdir /s /q folder"
                        clean_target = target_part.replace("/", "\\")
                        command = f"rmdir /s /q {clean_target}"
                        print(f"🔧 Auto-fixed to Windows folder delete: {command}")

            original_cmd = command
            command_lower = command.lower().strip()
            
            # Check if this is a package manager create/init command
            is_create_cmd = any(x in command_lower for x in ['npm create', 'npx create', 'yarn create', 'pnpm create', 'bun create', 'npm init', 'yarn init', 'pnpm init'])
            
            if is_create_cmd:
                command, warning = self._auto_fix_interactive_command(command)
            else:
                warning = ""
            
            print(f"\n⚡ [REQUEST] RUN: {command}")
            
            if warning:
                print(f"\n{warning}")
                if command != original_cmd:
                    print(f"📝 Modified command: {original_cmd} → {command}")
            
            if VibeUtils.is_dangerous(command):
                confirm = input("🚨 DANGEROUS! Confirm? (type 'confirm'): ").strip()
                if confirm != "confirm":
                    return "SYSTEM: Blocked dangerous command."
            
            response = input(">> Execute? (y/n): ").lower().strip()
            if response not in ['y', 'yes']:
                return "SYSTEM: User denied command execution."

            try:
                print("\n📟 Running command (this may take a moment)...")
                print("-" * 50)
                
                print("Command -> " + command)
                
                # 3. CRITICAL FIX: Use self.current_cwd instead of root_dir
                res = subprocess.run(
                    command, 
                    shell=True, 
                    cwd=self.current_cwd,   # <--- Updated to track 'cd' changes
                    capture_output=True, 
                    text=True,
                    timeout=300, 
                    input="y\n" # Auto-answer prompts
                )
                
                # Display output
                if res.stdout:
                    print("Output:")
                    print(res.stdout)
                
                if res.stderr:
                    print("Error/Warnings:")
                    print("This is the syntax ---> " + command)
                    print(res.stderr)
                
                print("-" * 50)
                
                # Check exit code
                if res.returncode == 0:
                    print("✅ Command completed successfully")
                else:
                    print(f"⚠️  Command exited with code: {res.returncode}")
                
                return f"SYSTEM: Code: {res.returncode}\nOut: {res.stdout}\nErr: {res.stderr}"
            except subprocess.TimeoutExpired:
                print("\n❌ Command timeout (5 minutes)")
                return "SYSTEM: Command timeout (5 minutes)"
            except Exception as e:
                print(f"\n❌ Error executing command: {e}")
                return f"SYSTEM: Error: {e}"

    def handle_shadcn(self, component: str) -> str:
        print(f"\n🎨 [REQUEST] SHADCN: {component}")
        return self.handle_run(f"npx shadcn@latest add {component} -y")

    def handle_create(self, framework: str, project_name: str, options: str = "") -> str:
        """
        Handle project scaffolding with predefined templates.
        Supports: vite, next, react, astro, remix, svelte, vue, nuxt, etc.
        """
        print(f"\n🏗️ [REQUEST] CREATE: {framework} project '{project_name}'")
        
        # Predefined scaffolding commands
        templates = {
            'vite-react': f"npm create vite@latest {project_name} -- --template react",
            'vite-react-ts': f"npm create vite@latest {project_name} -- --template react-ts",
            'vite-vue': f"npm create vite@latest {project_name} -- --template vue",
            'vite-vue-ts': f"npm create vite@latest {project_name} -- --template vue-ts",
            'vite-svelte': f"npm create vite@latest {project_name} -- --template svelte",
            'vite-svelte-ts': f"npm create vite@latest {project_name} -- --template svelte-ts",
            
            'next': f"npx create-next-app@latest {project_name} --typescript --tailwind --app --yes",
            'next-js': f"npx create-next-app@latest {project_name} --javascript --tailwind --app --yes",
            'next-pages': f"npx create-next-app@latest {project_name} --typescript --tailwind --src-dir --yes",
            
            'astro': f"npm create astro@latest {project_name} -- --template minimal --yes --install",
            'astro-blog': f"npm create astro@latest {project_name} -- --template blog --yes --install",
            
            'remix': f"npx create-remix@latest {project_name} --template remix --yes",
            
            'react': f"npm create vite@latest {project_name} -- --template react-ts",
            'vue': f"npm create vite@latest {project_name} -- --template vue-ts",
            'svelte': f"npm create vite@latest {project_name} -- --template svelte-ts",
            
            'nuxt': f"npx nuxi@latest init {project_name}",
            
            'expo': f"npx create-expo-app@latest {project_name} --template blank-typescript",
            
            't3': f"npm create t3-app@latest {project_name} -- --noGit",
        }
        
        # Find matching template
        framework_lower = framework.lower()
        command = None
        
        # Direct match
        if framework_lower in templates:
            command = templates[framework_lower]
        # Fuzzy match (e.g., "react-ts" matches "vite-react-ts")
        else:
            for key, cmd in templates.items():
                if framework_lower in key or key in framework_lower:
                    command = cmd
                    print(f"📝 Matched '{framework}' to template: {key}")
                    break
        
        if not command:
            # Fallback: generic npm create
            print(f"⚠️  Unknown framework '{framework}'. Using generic npm create...")
            command = f"npm create {framework}@latest {project_name}"
            if options:
                command += f" {options}"
            else:
                command += " -- --yes"
        else:
            # Append custom options if provided
            if options:
                command += f" {options}"
        
        print(f"📦 Command: {command}")
        print(f"\nAvailable templates:")
        print("  - vite-react, vite-react-ts, vite-vue, vite-svelte")
        print("  - next, next-js, next-pages")
        print("  - astro, astro-blog")
        print("  - react, vue, svelte (aliases for vite)")
        print("  - remix, nuxt, expo, t3")
        
        return self.handle_run(command)

    def handle_install(self, manager: str, pkg: str) -> str:
        print(f"\n📦 [REQUEST] INSTALL: {pkg}")
        return self.handle_run(self.pkg_manager.get_install_cmd(pkg))

    def handle_delete(self, rel_path: str) -> str:
        path = self.root_dir / rel_path
        print(f"\n🗑️ [REQUEST] DELETE: {rel_path}")
        
        if not path.exists():
            return f"SYSTEM: Error - Path {rel_path} does not exist."
        
        # Check if it's a directory
        is_dir = path.is_dir()
        item_type = "directory" if is_dir else "file"
        
        if is_dir:
            # Count files in directory
            try:
                file_count = sum(1 for _ in path.rglob('*') if _.is_file())
                print(f"⚠️  This directory contains {file_count} files")
            except:
                pass
        
        response = input(f">> Delete this {item_type}? (y/n): ").lower().strip()
        if response not in ['y', 'yes']:
            return f"SYSTEM: User denied delete of {rel_path}"
        
        try:
            # Backup before deletion (for files only, directories are too large)
            if not is_dir:
                ts = datetime.now().strftime("%Y%m%d_%H%M%S")
                safe_name = rel_path.replace("/", "_").replace("\\", "_")
                bak = self.backup_dir / f"{safe_name}_{ts}.bak"
                shutil.copy2(path, bak)
                print(f"💾 Backup saved: {bak.name}")
            
            # Delete the item
            if is_dir:
                shutil.rmtree(path)
                print(f"✅ Successfully deleted directory {rel_path}")
            else:
                path.unlink()
                print(f"✅ Successfully deleted file {rel_path}")
                
            return f"SYSTEM: {item_type.capitalize()} {rel_path} deleted successfully."
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
            'REFRESH': re.compile(r">>>\s*REFRESH\s*<<<", re.DOTALL),
            'INSTALL': re.compile(r">>>\s*INSTALL\s+(\w+)\s+(.+?)\s*<<<", re.DOTALL),
            'SHADCN': re.compile(r">>>\s*SHADCN\s+(.+?)\s*<<<", re.DOTALL),
            'DELETE': re.compile(r">>>\s*DELETE\s+(.+?)\s*<<<", re.DOTALL),
            'CREATE': re.compile(r">>>\s*CREATE\s+(\S+)\s+(\S+)(?:\s+(.+?))?\s*<<<", re.DOTALL)
        }

        # Execution Order: READ -> WRITE -> DELETE -> RUN -> OTHERS
        for path in patterns['READ'].findall(response_text):
            feedback.append(self.handle_read(path.strip()))
            action_taken = True

        for path, content in patterns['WRITE'].findall(response_text):
            feedback.append(self.handle_write(path.strip(), content.strip()))
            action_taken = True

        for _ in patterns['REFRESH'].findall(response_text):
            feedback.append(self.refresh_context())
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

        for match in patterns['CREATE'].findall(response_text):
            framework, project_name, options = match
            options = options.strip() if options else ""
            feedback.append(self.handle_create(framework.strip(), project_name.strip(), options))
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
                    max_tokens=4000,
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
                    
                    # Only get follow-up if the command was successful
                    # Check if any feedback indicates success
                    has_errors = any("Error" in f or "denied" in f.lower() or "Blocked" in f for f in feedback)
                    
                    if not has_errors:
                        print("\n🔄 Getting AI follow-up...")
                        
                        # Get follow-up response
                        followup = self.client.chat.completions.create(
                            model=MODEL_NAME,
                            messages=self.messages,
                            max_tokens=4000,
                            temperature=0.1
                        )
                        f_text = followup.choices[0].message.content
                        self.messages.append({"role": "assistant", "content": f_text})
                        
                        clean_f = re.sub(r">>>.*?<<<", "", f_text, flags=re.DOTALL).strip()
                        if clean_f: 
                            print(f"\n🤖 AI: {clean_f}")
                        
                        # Process any additional tool calls
                        self.process_tool_calls(f_text)
                    else:
                        print("\n⚠️  Command had errors. Check output above.")

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