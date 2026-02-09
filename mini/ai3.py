"""
VibeCLI v3.5 - Windows Edition
SDK: openai (OpenRouter Compatible)

WINDOWS-OPTIMIZED VERSION:
- Uses native Windows commands (dir, tree, etc.)
- No Unix dependencies
- Full Windows path support
- Proper cmd.exe integration

USAGE:
   python vibe_windows.py [target_directory]
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
DANGEROUS_COMMANDS = {'format', 'del /s', 'rmdir /s', 'rd /s', 'shutdown', 'diskpart'}
MAX_HISTORY_TURNS = 15

# ==============================================================================
# WINDOWS COMMAND MAPPINGS
# ==============================================================================

WINDOWS_CMD_MAP = {
    'ls': 'dir /b',
    'ls -l': 'dir',
    'ls -la': 'dir /a',
    'ls -R': 'tree /f /a',
    'pwd': 'cd',
    'cat': 'type',
    'cp': 'copy',
    'mv': 'move',
    'rm': 'del',
    'rm -rf': 'rmdir /s /q',
    'mkdir -p': 'mkdir',
    'touch': 'type nul >',
    'clear': 'cls',
    'grep': 'findstr',
    'which': 'where',
}

# ==============================================================================
# VIBE UTILS & SYSTEM PROMPT
# ==============================================================================

SYSTEM_INSTRUCTION = """
[CRITICAL CONFIGURATION - WINDOWS EDITION]
You are VibeCLI running on WINDOWS in a LOCAL development environment.
The user has granted you FULL PERMISSION to create, edit, run, and DELETE files.

WINDOWS-SPECIFIC CAPABILITIES:
1. **Navigation:** Use `cd` command. System tracks your current directory.
   - Example: >>> RUN cd backend <<<
   - Example: >>> RUN cd .. <<<

2. **File Operations:**
   - List files: >>> RUN dir <<<
   - Tree view: >>> RUN tree /f /a <<<
   - Read file: >>> READ file.txt <<<
   - Delete file: >>> DELETE file.txt <<<
   - Delete folder: >>> RUN rmdir /s /q foldername <<<

3. **Command Syntax (WINDOWS ONLY):**
   - Use backslashes: `src\\components\\Button.tsx`
   - Use Windows commands: dir, tree, type, copy, move, del, rmdir
   - DO NOT use: ls, cat, rm, cp, mv, pwd (these are Linux commands)

>>> REFRESH <<<
Use this after file operations to re-scan the directory.

PROTOCOL (Strict Command Blocks):

>>> WRITE {file_path}
{full_file_content}
<<<

>>> READ {file_path} <<<

>>> DELETE {file_path} <<<

>>> RUN {windows_command} <<<

>>> INSTALL {package_manager} {package_name} <<<

>>> TREE <<<
Shows complete file structure using Windows tree command.

>>> LISTFILES <<<
Shows file listing in current directory.

RULES:
- When using WRITE, provide the **COMPLETE** file content.
- Use Windows-style paths with backslashes or forward slashes (both work).
- For multi-step tasks, execute operations in logical order.
- Always assume you are in the directory set by the last `cd` command.
- Use TREE to show file structure instead of ls -R.
- All commands run in cmd.exe on Windows.
"""

class VibeUtils:
    @staticmethod
    def convert_unix_to_windows(command: str) -> str:
        """Convert common Unix commands to Windows equivalents (Smart Match)."""
        cmd_lower = command.lower().strip()
        
        # Sort keys by length (longest first) to prevent 'rm' catching 'rm -rf'
        # This ensures specific commands match before general ones
        sorted_keys = sorted(WINDOWS_CMD_MAP.keys(), key=len, reverse=True)
        
        for unix_cmd in sorted_keys:
            # Check if command STARTS with the unix_cmd
            if cmd_lower.startswith(unix_cmd):
                # CRITICAL CHECK: Ensure it's a whole word match
                # It must be followed by a space, OR be the entire string.
                # This prevents 'rm' from matching 'rmdir'
                match_len = len(unix_cmd)
                if len(cmd_lower) == match_len or cmd_lower[match_len] == ' ':
                    
                    win_cmd = WINDOWS_CMD_MAP[unix_cmd]
                    rest = command[match_len:].strip()
                    converted = f"{win_cmd} {rest}" if rest else win_cmd
                    
                    print(f"🔧 Converted: {command} → {converted}")
                    return converted
        
        return command
    
    @staticmethod
    def is_dangerous(command: str) -> bool:
        cmd_lower = command.lower()
        
        # Check for dangerous Windows commands
        if any(danger in cmd_lower for danger in DANGEROUS_COMMANDS):
            return True
        
        # Check for system-wide deletion
        if ('del' in cmd_lower or 'rmdir' in cmd_lower or 'rd' in cmd_lower):
            if '/s' in cmd_lower and ('c:\\' in cmd_lower or 'd:\\' in cmd_lower):
                return True
        
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

    @staticmethod
    def normalize_path(path: str) -> str:
        """Normalize path to Windows format."""
        # Convert forward slashes to backslashes
        return path.replace('/', '\\')

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
            default_headers={"X-Title": "VibeCLI-Windows"}
        )
        
        # --- CONTEXT INJECTION ---
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
        if len(self.messages) > MAX_HISTORY_TURNS * 2:
            system_msgs = self.messages[:2]
            conversation = self.messages[2:]
            self.messages = system_msgs + conversation[-(MAX_HISTORY_TURNS * 2):]

    # --- HANDLERS ---

    def refresh_context(self):
        # """Re-scans the file system and updates the AI's system prompt."""
        # print(f"\n🔄 Refreshing context from: {self.root_dir}...")
        # try:
        #     new_context = scrape_contents(self.root_dir)
            
        #     context_index = -1
        #     for i, msg in enumerate(self.messages):
        #         if msg['role'] == 'system' and "HERE IS THE CURRENT REPO CONTEXT" in msg['content']:
        #             context_index = i
        #             break
            
        #     new_msg = {
        #         "role": "system", 
        #         "content": f"HERE IS THE CURRENT REPO CONTEXT (Updated {datetime.now().strftime('%H:%M:%S')}):\n\n{new_context}"
        #     }
            
        #     if context_index != -1:
        #         self.messages[context_index] = new_msg
        #     else:
        #         self.messages.insert(1, new_msg)
                
        #     print(f"✅ Context updated! ({len(new_context)} chars)")
        #     return "SYSTEM: Context successfully refreshed. I now see the latest files."
            
        # except Exception as e:
        #     return f"SYSTEM: Error refreshing context: {e}"
        
        """Re-scans the file system AND structure to update the AI's system prompt."""
        print(f"\n🔄 Refreshing context from: {self.root_dir}...")
        try:
            # 1. Get File Contents
            new_context = scrape_contents(self.root_dir)
            
            # 2. Get Directory Structure (Crucial for empty folders)
            tree_output = subprocess.run(
                "tree /f /a", 
                shell=True, 
                cwd=self.root_dir, 
                capture_output=True, 
                text=True
            ).stdout

            # 3. Combine them
            combined_context = (
                f"DIRECTORY STRUCTURE:\n{tree_output}\n\n"
                f"FILE CONTENTS:\n{new_context}"
            )
            
            # 4. Update the System Message
            context_index = -1
            for i, msg in enumerate(self.messages):
                if msg['role'] == 'system' and "HERE IS THE CURRENT REPO CONTEXT" in msg['content']:
                    context_index = i
                    break
            
            new_msg = {
                "role": "system", 
                "content": f"HERE IS THE CURRENT REPO CONTEXT (Updated {datetime.now().strftime('%H:%M:%S')}):\n\n{combined_context}"
            }
            
            if context_index != -1:
                self.messages[context_index] = new_msg
            else:
                self.messages.insert(1, new_msg)
                
            print(f"✅ Context updated! (Structure + {len(new_context)} chars of content)")
            return f"SYSTEM: Context refreshed. Current Structure:\n{tree_output}"
            
        except Exception as e:
            return f"SYSTEM: Error refreshing context: {e}"





    def handle_tree(self) -> str:
        """Show directory tree structure using Windows tree command."""
        print("\n🌳 [REQUEST] TREE: Showing directory structure...")
        try:
            result = subprocess.run(
                "tree /f /a",
                shell=True,
                cwd=self.current_cwd,
                capture_output=True,
                text=True,
                timeout=30
            )
            
            if result.returncode == 0:
                output = result.stdout
                print("\n" + output)
                return f"SYSTEM: Directory tree:\n{output}"
            else:
                return f"SYSTEM: Error running tree command: {result.stderr}"
        except Exception as e:
            return f"SYSTEM: Error: {e}"

    def handle_listfiles(self) -> str:
        """List files in current directory using Windows dir command."""
        print("\n📁 [REQUEST] LISTFILES: Listing current directory...")
        try:
            result = subprocess.run(
                "dir /b",
                shell=True,
                cwd=self.current_cwd,
                capture_output=True,
                text=True,
                timeout=30
            )
            
            if result.returncode == 0:
                output = result.stdout
                print("\n" + output)
                return f"SYSTEM: Files in current directory:\n{output}"
            else:
                return f"SYSTEM: Error listing files: {result.stderr}"
        except Exception as e:
            return f"SYSTEM: Error: {e}"

    def handle_read(self, rel_path: str) -> str:
        """
        SMART READ: 
        - If path is a file -> Returns content.
        - If path is a folder -> Returns ALL files inside (Recursive Scrape).
        """
        # Normalize path for Windows
        rel_path = VibeUtils.normalize_path(rel_path)
        path = (self.root_dir / rel_path).resolve()
        
        print(f"\n📖 [REQUEST] READ: {rel_path}")

        # Security check: Ensure we are not reading outside the root
        if not str(path).startswith(str(self.root_dir)):
             return "SYSTEM: Error - Access denied. You can only read files inside the project root."

        if not path.exists(): 
            return f"SYSTEM: Error - Path {rel_path} does not exist."
        
        try:
            # CASE A: It is a Directory -> SCRAPE IT
            if path.is_dir():
                print(f"📂 Detected directory. Scraping all contents of: {rel_path}...")
                # Use our existing scraper to get everything
                content = scrape_contents(path)
                return f"SYSTEM: Scraped contents of directory '{rel_path}':\n\n{content}"
            
            # CASE B: It is a File -> READ IT
            else:
                content = path.read_text(encoding='utf-8', errors='ignore')
                return f"SYSTEM: Content of {rel_path}:\n{content}"
                
        except Exception as e: 
            return f"SYSTEM: Read error: {e}"


    def handle_write(self, rel_path: str, new_content: str) -> str:
        # Normalize path for Windows
        rel_path = VibeUtils.normalize_path(rel_path)
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
        """Auto-fix interactive commands for non-interactive execution."""
        warnings = []
        fixed_cmd = command
        
        # Vite: Add --template flag if missing
        if "create vite" in command.lower() or "create-vite" in command.lower():
            if "--yes" not in command and "-y" not in command:
                command = command.replace("npm create", "npm create --yes")
                command = command.replace("npx create-vite", "npx --yes create-vite")

            if "--template" not in command:
                warnings.append("⚠️  Vite detected without --template. Adding default react-ts template.")
                fixed_cmd = f"{command} --template react-ts"
            else:
                fixed_cmd = command

        # Next.js: Add --yes flag
        elif "create-next-app" in command.lower():
            if "--yes" not in command and "-y" not in command:
                warnings.append("⚠️  Next.js detected. Adding --yes flag to skip prompts.")
                fixed_cmd = f"{command} --yes"
        
        # Astro
        elif "create astro" in command.lower():
            if "--template" not in command:
                warnings.append("⚠️  Astro detected. Adding --template minimal.")
                fixed_cmd = f"{command} --template minimal --yes"
            elif "--yes" not in command:
                fixed_cmd = f"{command} --yes"
        
        # shadcn: Ensure -y flag
        elif "shadcn" in command.lower():
            if "-y" not in command and "--yes" not in command:
                fixed_cmd = f"{command} -y"
        
        # npm/pnpm/yarn init: Add -y flag
        elif command.strip().endswith("init"):
            if "-y" not in command and "--yes" not in command:
                warnings.append("⚠️  Init command detected. Adding -y flag.")
                fixed_cmd = f"{command} -y"
        
        warning_msg = "\n".join(warnings) if warnings else ""
        return fixed_cmd, warning_msg

    def handle_run(self, command: str) -> str:
        # 1. Handle "cd" commands manually
        if command.strip().startswith("cd "):
            target = command.strip().split(" ", 1)[1]
            # Support both forward and back slashes
            target = target.replace('/', '\\')
            new_path = (self.current_cwd / target).resolve()
            
            if new_path.exists() and new_path.is_dir():
                self.current_cwd = new_path
                print(f"📂 Changed directory to: {self.current_cwd}")
                return f"SYSTEM: Directory changed to {self.current_cwd}"
            else:
                return f"SYSTEM: Error - Directory {target} not found."

        # 2. Convert Unix commands to Windows
        command = VibeUtils.convert_unix_to_windows(command)

        # 3. Auto-fix interactive commands
        original_cmd = command
        command_lower = command.lower().strip()
        
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
            
            # Run command in cmd.exe with current working directory
            res = subprocess.run(
                command, 
                shell=True, 
                cwd=self.current_cwd,
                capture_output=True, 
                text=True,
                timeout=300
            )
            
            # Display output
            if res.stdout:
                print("Output:")
                print(res.stdout)
            
            if res.stderr:
                print("Error/Warnings:")
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

    def handle_delete(self, rel_path: str) -> str:
        # Normalize path for Windows
        rel_path = VibeUtils.normalize_path(rel_path)
        path = self.root_dir / rel_path
        
        print(f"\n🗑️ [REQUEST] DELETE: {rel_path}")
        
        if not path.exists():
            return f"SYSTEM: Error - Path {rel_path} does not exist."
        
        is_dir = path.is_dir()
        item_type = "directory" if is_dir else "file"
        
        if is_dir:
            try:
                file_count = sum(1 for _ in path.rglob('*') if _.is_file())
                print(f"⚠️  This directory contains {file_count} files")
            except:
                pass
        
        response = input(f">> Delete this {item_type}? (y/n): ").lower().strip()
        if response not in ['y', 'yes']:
            return f"SYSTEM: User denied delete of {rel_path}"
        
        try:
            if not is_dir:
                ts = datetime.now().strftime("%Y%m%d_%H%M%S")
                safe_name = rel_path.replace("/", "_").replace("\\", "_")
                bak = self.backup_dir / f"{safe_name}_{ts}.bak"
                shutil.copy2(path, bak)
                print(f"💾 Backup saved: {bak.name}")
            
            if is_dir:
                shutil.rmtree(path)
                print(f"✅ Successfully deleted directory {rel_path}")
            else:
                path.unlink()
                print(f"✅ Successfully deleted file {rel_path}")
                
            return f"SYSTEM: {item_type.capitalize()} {rel_path} deleted successfully."
        except Exception as e:
            return f"SYSTEM: Delete error: {e}"

    def handle_install(self, manager: str, pkg: str) -> str:
        print(f"\n📦 [REQUEST] INSTALL: {pkg}")
        return self.handle_run(self.pkg_manager.get_install_cmd(pkg))

    # --- MAIN LOOP ---

    def process_tool_calls(self, response_text: str) -> Tuple[List[str], bool]:
        feedback = []
        action_taken = False
        
        patterns = {
            'WRITE': re.compile(r">>>\s*WRITE\s+(.+?)\s*\n(.*?)<<<", re.DOTALL),
            'READ': re.compile(r">>>\s*READ\s+(.+?)\s*<<<", re.DOTALL),
            'RUN': re.compile(r">>>\s*RUN\s+(.+?)\s*<<<", re.DOTALL),
            'REFRESH': re.compile(r">>>\s*REFRESH\s*<<<", re.DOTALL),
            'TREE': re.compile(r">>>\s*TREE\s*<<<", re.DOTALL),
            'LISTFILES': re.compile(r">>>\s*LISTFILES\s*<<<", re.DOTALL),
            'INSTALL': re.compile(r">>>\s*INSTALL\s+(\w+)\s+(.+?)\s*<<<", re.DOTALL),
            'DELETE': re.compile(r">>>\s*DELETE\s+(.+?)\s*<<<", re.DOTALL),
        }

        # Execution Order: READ -> TREE -> LISTFILES -> WRITE -> DELETE -> RUN -> OTHERS
        for path in patterns['READ'].findall(response_text):
            feedback.append(self.handle_read(path.strip()))
            action_taken = True

        for _ in patterns['TREE'].findall(response_text):
            feedback.append(self.handle_tree())
            action_taken = True

        for _ in patterns['LISTFILES'].findall(response_text):
            feedback.append(self.handle_listfiles())
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

        return feedback, action_taken

    def run(self):
        print(f"\n🚀 VibeCLI Windows Edition | {MODEL_NAME}")
        print(f"📂 Root: {self.root_dir}")
        print(f"🪟 Platform: Windows")
        print(f"📦 Package Manager: {self.pkg_manager.manager}")
        print("--------------------------------------------------")
        print("💡 TIP: Use TREE to view file structure, or ask to 'show file structure'")

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
                        if ">>>" not in full_response:
                            print(content, end="", flush=True)

                self.messages.append({"role": "assistant", "content": full_response})

                # Display clean response
                clean_display = re.sub(r">>>.*?<<<", "", full_response, flags=re.DOTALL).strip()
                if clean_display and ">>>" in full_response:
                    print(f"\n🤖 AI: {clean_display}")

                # Process tool calls
                feedback, acted = self.process_tool_calls(full_response)

                if acted:
                    tool_output = "SYSTEM: Results:\n" + "\n".join(feedback)
                    self.messages.append({"role": "system", "content": tool_output})
                    
                    has_errors = any("Error" in f or "denied" in f.lower() or "Blocked" in f for f in feedback)
                    
                    if not has_errors:
                        print("\n🔄 Getting AI follow-up...")
                        
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
    parser = argparse.ArgumentParser(description="VibeCLI Windows Edition - AI-Powered Code Assistant")
    parser.add_argument("path", nargs="?", default=".", help="Project root directory (default: current directory)")
    parser.add_argument("--no-context", action="store_true", help="Skip initial codebase scanning")
    args = parser.parse_args()
    
    agent = VibeAgent(args.path, skip_context=args.no_context)
    agent.run()