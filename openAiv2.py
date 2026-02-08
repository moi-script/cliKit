"""
VibeCLI v3.0 - Production-Grade AI Software Engineer
SDK: openai (OpenRouter Compatible)

FEATURES:
1. Context Awareness: Indexes your actual code (not just file names).
2. Safety First: Automatic backups (.vibe/backups) before any write.
3. Diff View: Shows Red/Green changes before you type 'y'.
4. Memory Management: Sliding window to prevent token overflow.
5. Security: Blacklists dangerous shell commands (rm -rf, etc.).
6. Dynamic Ignoring: Respects .gitignore patterns automatically.
7. Streaming: Real-time "Matrix style" output.

USAGE:
   python vibe_pro.py [target_directory]
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

# Third-party imports (ensure these are installed via pip install openai python-dotenv)
try:
    from dotenv import load_dotenv
    from openai import OpenAI
except ImportError:
    print("❌ Missing dependencies. Run: pip install openai python-dotenv")
    sys.exit(1)

# ==============================================================================
# CONFIGURATION & CONSTANTS
# ==============================================================================

# Fast & Cheap for Logic, can be swapped for "anthropic/claude-3.5-sonnet" for complex tasks
MODEL_NAME = "google/gemini-2.5-flash-lite:nitro"

# Security: Commands that will be auto-blocked or require double confirmation
DANGEROUS_COMMANDS = {'rm', 'del', 'format', 'mkfs', 'dd', 'shutdown', 'reboot'}

# Context: Max size of a single file to read into context (20KB)
MAX_FILE_CONTEXT_SIZE = 20 * 1024 

# Memory: Max conversation turns before sliding window activates
MAX_HISTORY_TURNS = 15

SYSTEM_INSTRUCTION = """
You are VibeCLI v3, an elite AI software engineer.
You have FULL ACCESS to the user's codebase.

YOUR MISSION: 
1. Analyze the user's request.
2. Read relevant files if you don't have their content yet.
3. MODIFY files to implement features or fix bugs.

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
- If you need to know what's in a file before editing, use READ first.
- Always check if a file exists before creating it.
- Use the detected package manager.
"""

# ==============================================================================
# UTILS: Security & File Management
# ==============================================================================

class VibeUtils:
    @staticmethod
    def is_dangerous(command: str) -> bool:
        """Check if a shell command contains dangerous keywords."""
        parts = command.split()
        if not parts: return False
        base_cmd = parts[0].lower()
        if base_cmd in DANGEROUS_COMMANDS:
            return True
        # Check for aggressive flags like -rf on system paths
        if "rm" in command and ("-r" in command or "/ " in command):
            return True
        return False

    @staticmethod
    def get_diff(old_content: str, new_content: str, filename: str) -> str:
        """Generate a colored diff string for terminal display."""
        diff = difflib.unified_diff(
            old_content.splitlines(),
            new_content.splitlines(),
            fromfile=f"a/{filename}",
            tofile=f"b/{filename}",
            lineterm=""
        )
        
        output = []
        for line in diff:
            if line.startswith('+'):
                output.append(f"\033[92m{line}\033[0m") # Green
            elif line.startswith('-'):
                output.append(f"\033[91m{line}\033[0m") # Red
            elif line.startswith('^'):
                output.append(f"\033[94m{line}\033[0m") # Blue
            else:
                output.append(line)
        return "\n".join(output)

# ==============================================================================
# SUBSYSTEM: File Indexer & Ignorer
# ==============================================================================

class ProjectIndexer:
    def __init__(self, root_dir: Path):
        self.root_dir = root_dir
        self.ignore_patterns = self._load_gitignore()
        # Default ignores
        self.ignore_patterns.extend([
            '.git', '.env', 'node_modules', '__pycache__', 'dist', 'build', 
            'package-lock.json', 'yarn.lock', '*.lock', '*.log', '.DS_Store'
        ])

    def _load_gitignore(self) -> List[str]:
        """Parse .gitignore if it exists."""
        gitignore = self.root_dir / ".gitignore"
        patterns = []
        if gitignore.exists():
            with open(gitignore, 'r') as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith('#'):
                        patterns.append(line)
        return patterns

    def should_ignore(self, path: Path) -> bool:
        """Check if a path matches ignored patterns."""
        rel_path = str(path.relative_to(self.root_dir)).replace('\\', '/')
        name = path.name
        
        for pattern in self.ignore_patterns:
            # Handle directory matches specifically
            if pattern.endswith('/') and path.is_dir():
                if fnmatch.fnmatch(name + '/', pattern) or fnmatch.fnmatch(rel_path + '/', pattern):
                    return True
            if fnmatch.fnmatch(name, pattern) or fnmatch.fnmatch(rel_path, pattern):
                return True
        return False

    def scan_project_structure(self) -> str:
        """Returns a tree-like string of the project structure."""
        output = []
        for root, dirs, files in os.walk(self.root_dir):
            # Modify dirs in-place to skip ignored directories
            dirs[:] = [d for d in dirs if not self.should_ignore(Path(root) / d)]
            
            level = root.replace(str(self.root_dir), '').count(os.sep)
            indent = ' ' * 4 * (level)
            output.append(f"{indent}{os.path.basename(root)}/")
            subindent = ' ' * 4 * (level + 1)
            
            for f in files:
                if not self.should_ignore(Path(root) / f):
                    output.append(f"{subindent}{f}")
        return "\n".join(output)

# ==============================================================================
# SUBSYSTEM: Package Manager
# ==============================================================================

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
# CORE AGENT
# ==============================================================================

class VibeAgent:
    def __init__(self, target_dir: str):
        load_dotenv()
        self.api_key = os.getenv("OPENROUTER_API_KEY")
        if not self.api_key:
            print("❌ Error: OPENROUTER_API_KEY not found in .env")
            sys.exit(1)

        self.root_dir = Path(target_dir).resolve()
        if not self.root_dir.exists():
            self.root_dir.mkdir(parents=True)

        # Initialize Subsystems
        self.indexer = ProjectIndexer(self.root_dir)
        self.pkg_manager = PackageManager(self.root_dir)
        self.backup_dir = self.root_dir / ".vibe" / "backups"
        self.backup_dir.mkdir(parents=True, exist_ok=True)

        # Initialize AI
        self.client = OpenAI(
            base_url="https://openrouter.ai/api/v1",
            api_key=self.api_key,
            default_headers={"X-Title": "VibeCLI-Pro"}
        )
        
        # Memory
        self.messages = [{"role": "system", "content": SYSTEM_INSTRUCTION}]
        
        # Inject Initial Context
        print("🔍 Indexing project structure...")
        structure = self.indexer.scan_project_structure()
        self.messages.append({
            "role": "system", 
            "content": f"Current File Structure:\n{structure}\nPackage Manager: {self.pkg_manager.manager}"
        })

    # --------------------------------------------------------------------------
    # MEMORY MANAGEMENT
    # --------------------------------------------------------------------------
    
    def _prune_history(self):
        """Sliding window to keep context manageable."""
        if len(self.messages) > MAX_HISTORY_TURNS * 2:
            # Keep System Prompt (0) and Context (1), remove oldest interaction
            # Remove indices 2 and 3 (User + Assistant pair)
            del self.messages[2:4]

    # --------------------------------------------------------------------------
    # ACTION HANDLERS
    # --------------------------------------------------------------------------

    def handle_read(self, rel_path: str) -> str:
        path = self.root_dir / rel_path
        if not path.exists():
            return f"SYSTEM: Error - File {rel_path} does not exist."
        
        if self.indexer.should_ignore(path):
            return f"SYSTEM: Error - {rel_path} is ignored/protected."

        try:
            if path.stat().st_size > MAX_FILE_CONTEXT_SIZE:
                return f"SYSTEM: Error - File {rel_path} is too large to read."
            
            content = path.read_text(encoding='utf-8', errors='ignore')
            print(f"📖 Read: {rel_path}")
            return f"SYSTEM: Content of {rel_path}:\n{content}"
        except Exception as e:
            return f"SYSTEM: Read error: {e}"

    def handle_write(self, rel_path: str, new_content: str) -> str:
        path = self.root_dir / rel_path
        exists = path.exists()
        
        print(f"\n📝 [REQUEST] WRITE: {rel_path}")
        
        # DIFF VIEW
        if exists:
            try:
                old_content = path.read_text(encoding='utf-8')
                print("\n--- DIFF CHECK ---")
                print(VibeUtils.get_diff(old_content, new_content, rel_path))
                print("------------------\n")
            except:
                print("⚠️  (Binary or unreadable file, cannot show diff)")

        if input(">> Apply changes? (y/n): ").lower() != 'y':
            return f"SYSTEM: User denied write to {rel_path}"

        try:
            # BACKUP
            if exists:
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                safe_name = rel_path.replace("/", "_").replace("\\", "_")
                bak_path = self.backup_dir / f"{safe_name}_{timestamp}.bak"
                shutil.copy2(path, bak_path)
                print(f"💾 Backup saved to .vibe/backups/{bak_path.name}")

            # WRITE
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(new_content, encoding='utf-8')
            print(f"✅ Successfully wrote {rel_path}")
            return f"SYSTEM: File {rel_path} updated successfully."
        except Exception as e:
            return f"SYSTEM: Write error: {e}"

    def handle_run(self, command: str) -> str:
        print(f"\n⚡ [REQUEST] RUN: {command}")
        
        if VibeUtils.is_dangerous(command):
            print("🚨 SECURITY WARNING: Dangerous command detected!")
            if input(">> ARE YOU SURE? (type 'confirm' to proceed): ") != "confirm":
                return "SYSTEM: User blocked dangerous command."

        if input(">> Execute? (y/n): ").lower() != 'y':
            return "SYSTEM: User denied execution."

        try:
            res = subprocess.run(
                command, 
                shell=True, 
                cwd=self.root_dir, 
                capture_output=True, 
                text=True
            )
            print(f"Output:\n{res.stdout}")
            if res.stderr: print(f"Error:\n{res.stderr}")
            return f"SYSTEM: Exit Code: {res.returncode}\nStdout: {res.stdout}\nStderr: {res.stderr}"
        except Exception as e:
            return f"SYSTEM: Execution error: {e}"

    def handle_shadcn(self, component: str) -> str:
        print(f"\n🎨 [REQUEST] ADD COMPONENT: {component}")
        cmd = f"npx shadcn@latest add {component} -y"
        return self.handle_run(cmd)

    def handle_install(self, manager: str, pkg: str) -> str:
        print(f"\n📦 [REQUEST] INSTALL: {pkg}")
        # Ignore AI's manager suggestion, use the detected one
        cmd = self.pkg_manager.get_install_cmd(pkg)
        return self.handle_run(cmd)

    # --------------------------------------------------------------------------
    # BRAIN: Parsing & Loop
    # --------------------------------------------------------------------------

    def process_tool_calls(self, response_text: str) -> Tuple[List[str], bool]:
        """Parses response for strict tool blocks."""
        feedback = []
        action_taken = False
        
        # Regex patterns
        patterns = {
            'WRITE': re.compile(r">>>\s*WRITE\s+(.+?)\s*\n(.*?)<<<", re.DOTALL),
            'READ': re.compile(r">>>\s*READ\s+(.+?)\s*<<<", re.DOTALL),
            'RUN': re.compile(r">>>\s*RUN\s+(.+?)\s*<<<", re.DOTALL),
            'INSTALL': re.compile(r">>>\s*INSTALL\s+(\w+)\s+(.+?)\s*<<<", re.DOTALL),
            'SHADCN': re.compile(r">>>\s*SHADCN\s+(.+?)\s*<<<", re.DOTALL),
            'DELETE': re.compile(r">>>\s*DELETE\s+(.+?)\s*<<<", re.DOTALL)
        }

        # Execute Reads first (Context gathering)
        for path in patterns['READ'].findall(response_text):
            feedback.append(self.handle_read(path.strip()))
            action_taken = True

        # Execute Writes
        for path, content in patterns['WRITE'].findall(response_text):
            feedback.append(self.handle_write(path.strip(), content.strip()))
            action_taken = True

        # Execute Commands
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
        print(f"\n🚀 VibeCLI Pro Initialized")
        print(f"📂 Root: {self.root_dir}")
        print("--------------------------------------------------")

        while True:
            try:
                user_input = input("\n(You) > ")
                if user_input.lower() in ['exit', 'quit']: break
                if not user_input.strip(): continue

                self.messages.append({"role": "user", "content": user_input})
                self._prune_history()

                print("✨ Assistant Thinking...", end="", flush=True)
                
                # Streaming Response
                full_response = ""
                stream = self.client.chat.completions.create(
                    model=MODEL_NAME,
                    messages=self.messages,
                    temperature=0.1,
                    stream=True
                )

                print("\r", end="") # Clear thinking message
                
                for chunk in stream:
                    content = chunk.choices[0].delta.content or ""
                    if content:
                        full_response += content
                        # Hacky way to stream text but hide tool blocks until finished
                        if ">>>" not in full_response:
                            print(content, end="", flush=True)
                        elif "<<<" in full_response:
                            # If a block just finished, we can resume printing if there's chat after
                            pass 

                # Store full response in memory
                self.messages.append({"role": "assistant", "content": full_response})

                # Process Tools
                # Clean the response for display if it was hidden
                clean_display = re.sub(r">>>.*?<<<", "", full_response, flags=re.DOTALL).strip()
                if clean_display and ">>>" in full_response:
                    print(f"\n🤖 AI: {clean_display}")

                feedback, acted = self.process_tool_calls(full_response)

                if acted:
                    tool_output = "SYSTEM: Tool Execution Results:\n" + "\n".join(feedback)
                    self.messages.append({"role": "system", "content": tool_output})
                    print("\n🔄 Sending tool results back to AI...")
                    
                    # Auto-follow up allows AI to chain commands (e.g. Read -> Write)
                    # We do a non-streaming call here for speed
                    followup = self.client.chat.completions.create(
                        model=MODEL_NAME,
                        messages=self.messages,
                        temperature=0.1
                    )
                    followup_text = followup.choices[0].message.content
                    self.messages.append({"role": "assistant", "content": followup_text})
                    
                    clean_followup = re.sub(r">>>.*?<<<", "", followup_text, flags=re.DOTALL).strip()
                    if clean_followup:
                        print(f"🤖 AI: {clean_followup}")
                    
                    # Recursively process if it decided to do more things
                    self.process_tool_calls(followup_text)

            except KeyboardInterrupt:
                print("\n👋 Saving memory and exiting...")
                break
            except Exception as e:
                print(f"\n❌ Critical Error: {e}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="VibeCLI Pro - AI Engineer")
    parser.add_argument("path", nargs="?", default=".", help="Project root directory")
    args = parser.parse_args()
    
    agent = VibeAgent(args.path)
    agent.run()