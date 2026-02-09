"""
VibeCLI v4.0 - Ultimate Edition
Merges:
  - V2: Advanced Scaffolding, Package Management (shadcn/vite/next), Auto-Fixing Interactive Commands.
  - V3: Windows Native Command Translation, Deep Context/Repo Reading, Directory Trees.

USAGE:
    python vibe_ultimate.py [target_directory]
"""

import os
import re
import sys
import shutil
import difflib
import subprocess
import argparse
import fnmatch
from pathlib import Path
from datetime import datetime
from typing import List, Tuple, Dict, Optional

# --- Dependency Check ---
try:
    from dotenv import load_dotenv
    from openai import OpenAI
    from colorama import init, Fore, Style
    init(autoreset=True) # Initialize colorama for Windows
except ImportError:
    print("❌ Missing dependencies. Run: pip install openai python-dotenv colorama")
    sys.exit(1)

# ==============================================================================
# CONFIGURATION
# ==============================================================================

MODEL_NAME = "google/gemini-2.5-flash-lite:nitro" # Or your preferred nitro model
DANGEROUS_COMMANDS = {'format', 'del /s', 'rmdir /s', 'rd /s', 'shutdown', 'diskpart', 'mkfs', 'dd'}
MAX_HISTORY_TURNS = 20
IGNORE_PATTERNS = [
    '.git', '__pycache__', 'node_modules', '.next', '.vibe', 'dist', 'build', 
    'coverage', '.DS_Store', 'Thumbs.db', '*.lock', '*.log', '*.png', '*.jpg', 
    '*.jpeg', '*.gif', '*.ico', '*.svg', '*.mp4', '*.mp3', '*.pdf', '*.zip', '*.exe'
]

# ==============================================================================
# 1. FILE SYSTEM INTELLIGENCE (The "Repo Reader" from V3)
# ==============================================================================

class RepoContext:
    @staticmethod
    def should_ignore(path: Path, root: Path) -> bool:
        rel_path = path.relative_to(root).as_posix()
        name = path.name
        for pattern in IGNORE_PATTERNS:
            if fnmatch.fnmatch(name, pattern) or fnmatch.fnmatch(rel_path, pattern):
                return True
        return False

    @staticmethod
    def get_tree(root_path: Path) -> str:
        """Generates a visual tree structure string using native Windows command if available, else python."""
        try:
            # Try native Windows tree first for speed
            if sys.platform.startswith('win'):
                res = subprocess.run("tree /f /a", shell=True, cwd=root_path, capture_output=True, text=True)
                if res.returncode == 0:
                    return res.stdout
        except:
            pass
        
        # Python fallback
        tree_str = ""
        for path in sorted(root_path.rglob('*')):
            if RepoContext.should_ignore(path, root_path): continue
            depth = len(path.relative_to(root_path).parts)
            spacer = "  " * (depth - 1)
            tree_str += f"{spacer}|-- {path.name}\n"
        return tree_str

    @staticmethod
    def scrape(root_path: Path) -> str:
        """Recursively reads all text files in the project."""
        output = []
        for path in root_path.rglob('*'):
            if path.is_file() and not RepoContext.should_ignore(path, root_path):
                try:
                    # Check for binary content roughly
                    with open(path, 'rb') as f:
                        if b'\0' in f.read(1024): continue 
                    
                    content = path.read_text(encoding='utf-8', errors='ignore')
                    rel_path = path.relative_to(root_path).as_posix()
                    output.append(f"--- FILE: {rel_path} ---\n{content}\n")
                except Exception:
                    pass
        return "\n".join(output)

# ==============================================================================
# 2. UTILITIES & TRANSLATORS
# ==============================================================================

class VibeUtils:
    WINDOWS_CMD_MAP = {
        'ls': 'dir /b', 'ls -l': 'dir', 'ls -la': 'dir /a', 'ls -R': 'tree /f /a',
        'pwd': 'cd', 'cat': 'type', 'cp': 'copy', 'mv': 'move',
        'rm': 'del', 'rm -rf': 'rmdir /s /q', 'mkdir -p': 'mkdir',
        'touch': 'type nul >', 'clear': 'cls', 'grep': 'findstr', 'which': 'where'
    }

    @staticmethod
    def normalize_path(path: str) -> str:
        return path.replace('/', '\\') if sys.platform.startswith('win') else path

    @staticmethod
    def convert_to_native(command: str) -> str:
        """Smartly translates Unix commands to Windows if running on Windows."""
        if not sys.platform.startswith('win'): return command
        
        cmd_lower = command.lower().strip()
        sorted_keys = sorted(VibeUtils.WINDOWS_CMD_MAP.keys(), key=len, reverse=True)
        
        for unix_cmd in sorted_keys:
            if cmd_lower.startswith(unix_cmd):
                # Ensure whole word match (prevent 'rm' matching 'rmdir')
                match_len = len(unix_cmd)
                if len(cmd_lower) == match_len or cmd_lower[match_len] == ' ':
                    win_cmd = VibeUtils.WINDOWS_CMD_MAP[unix_cmd]
                    rest = command[match_len:].strip()
                    return f"{win_cmd} {rest}" if rest else win_cmd
        return command

    @staticmethod
    def auto_fix_interactive(command: str) -> tuple[str, str]:
        """Injects non-interactive flags (V2 Feature)."""
        warnings = []
        fixed_cmd = command
        cmd_lower = command.lower()

        # Vite
        if "create vite" in cmd_lower or "create-vite" in cmd_lower:
            if "--yes" not in cmd_lower and "-y" not in cmd_lower:
                fixed_cmd = fixed_cmd.replace("npm create", "npm create --yes").replace("npx create-vite", "npx --yes create-vite")
            if "--template" not in cmd_lower:
                warnings.append("⚠️  Vite: Added default --template react-ts")
                fixed_cmd += " --template react-ts"

        # Next.js
        elif "create-next-app" in cmd_lower:
            if "--yes" not in cmd_lower:
                warnings.append("⚠️  Next.js: Added --yes flag")
                fixed_cmd += " --yes"
        
        # Shadcn
        elif "shadcn" in cmd_lower:
            if "-y" not in cmd_lower and "--yes" not in cmd_lower:
                fixed_cmd += " -y"
        
        # Generic Init
        elif cmd_lower.strip().endswith("init"):
            if "-y" not in cmd_lower:
                warnings.append("⚠️  Init: Added -y flag")
                fixed_cmd += " -y"

        return fixed_cmd, "\n".join(warnings)

    @staticmethod
    def is_dangerous(command: str) -> bool:
        cmd = command.lower()
        if any(d in cmd for d in DANGEROUS_COMMANDS): return True
        # Specific check for root directory wipes
        if ('del' in cmd or 'rmdir' in cmd) and ('/s' in cmd) and len(command.split()) < 3:
             return True
        return False

    @staticmethod
    def get_diff(old: str, new: str, filename: str) -> str:
        diff = difflib.unified_diff(old.splitlines(), new.splitlines(), fromfile=f"a/{filename}", tofile=f"b/{filename}", lineterm="")
        out = []
        for line in diff:
            if line.startswith('+'): out.append(Fore.GREEN + line + Style.RESET_ALL)
            elif line.startswith('-'): out.append(Fore.RED + line + Style.RESET_ALL)
            elif line.startswith('^'): out.append(Fore.BLUE + line + Style.RESET_ALL)
            else: out.append(line)
        return "\n".join(out)

class PackageManager:
    def __init__(self, root: Path):
        self.root = root
        self.type = self._detect()

    def _detect(self) -> str:
        if (self.root / "bun.lockb").exists(): return "bun"
        if (self.root / "pnpm-lock.yaml").exists(): return "pnpm"
        if (self.root / "yarn.lock").exists(): return "yarn"
        return "npm"

    def get_install_cmd(self, pkg: str) -> str:
        map = {
            "npm": f"npm install {pkg}",
            "pnpm": f"pnpm add {pkg}",
            "yarn": f"yarn add {pkg}",
            "bun": f"bun add {pkg}"
        }
        return map.get(self.type, map["npm"])

# ==============================================================================
# 3. SYSTEM PROMPT (The "Brain")
# ==============================================================================

SYSTEM_INSTRUCTION = """
You are VibeCLI Ultimate (v4). You are a local CLI Agent with FULL File System Access.

CAPABILITIES:
1. **Manage Projects:** Create Next.js, Vite, Astro, Remix apps efficiently.
2. **Edit Code:** Read files, analyze context, and write changes with backups.
3. **Execute Commands:** Run shell commands. Auto-translate 'ls', 'rm' etc. to Windows native commands.
4. **Install Packages:** Detects npm/pnpm/yarn/bun automatically.
5. **Smart Reading:** If asked to READ a directory, you get a full recursive scrape.

COMMAND PROTOCOL (Strict):

>>> WRITE {relative_path}
{full_content}
<<<

>>> READ {relative_path} <<<

>>> RUN {shell_command} <<<

>>> DELETE {relative_path} <<<

>>> CREATE {framework} {project_name} {optional_flags} <<<
Supported: vite (react/vue/svelte), next, astro, remix, shadcn (components).

>>> INSTALL {package_name} <<<
(Automatically picks npm/pnpm/yarn based on lockfile)

>>> TREE <<<
(Displays directory structure)

GUIDELINES:
- When writing code, provide the **COMPLETE** file. No lazy "..." placeholders.
- Always use relative paths from the current directory.
- If you create a new project, assume you need to `cd` into it for subsequent commands.
- For `shadcn` requests, use the `CREATE shadcn {component}` syntax or `RUN` command.
"""

# ==============================================================================
# 4. THE AGENT (Logic Core)
# ==============================================================================

class VibeAgent:
    def __init__(self, root_dir: str, skip_context: bool = False):
        load_dotenv()
        self.api_key = os.getenv("OPENROUTER_API_KEY") or os.getenv("OPENAI_API_KEY")
        if not self.api_key:
            print(Fore.RED + "❌ Error: API Key not found in .env" + Style.RESET_ALL)
            sys.exit(1)

        self.root = Path(root_dir).resolve()
        self.cwd = self.root
        if not self.root.exists(): self.root.mkdir(parents=True)
        
        self.pkg_mgr = PackageManager(self.root)
        self.backup_dir = self.root / ".vibe" / "backups"
        self.backup_dir.mkdir(parents=True, exist_ok=True)

        self.client = OpenAI(
            base_url="https://openrouter.ai/api/v1",
            api_key=self.api_key,
            default_headers={"X-Title": "VibeCLI-Ultimate"}
        )

        self.messages = [{"role": "system", "content": SYSTEM_INSTRUCTION}]
        
        if not skip_context:
            self.refresh_context(quiet=False)
        else:
            print(Fore.YELLOW + "⚠️  Skipping initial context load." + Style.RESET_ALL)

    def refresh_context(self, quiet=True):
        if not quiet: print(Fore.CYAN + f"🔍 Scanning context: {self.cwd}..." + Style.RESET_ALL)
        try:
            tree = RepoContext.get_tree(self.cwd)
            content = RepoContext.scrape(self.cwd)
            
            context_msg = (
                f"CURRENT CONTEXT (Updated {datetime.now().strftime('%H:%M:%S')}):\n"
                f"WORKING DIR: {self.cwd}\n"
                f"DIRECTORY STRUCTURE:\n{tree}\n\n"
                f"FILE CONTENTS:\n{content}"
            )

            # Update or Insert context message
            found = False
            for i, msg in enumerate(self.messages):
                if msg['role'] == 'system' and "CURRENT CONTEXT" in msg['content']:
                    self.messages[i] = {"role": "system", "content": context_msg}
                    found = True
                    break
            if not found:
                self.messages.insert(1, {"role": "system", "content": context_msg})
            
            if not quiet: print(Fore.GREEN + f"✅ Context Loaded. ({len(content)} chars)" + Style.RESET_ALL)
            return f"SYSTEM: Context refreshed. Tree:\n{tree}"
        except Exception as e:
            return f"SYSTEM: Error refreshing context: {e}"

    def _prune_history(self):
        if len(self.messages) > MAX_HISTORY_TURNS * 2:
            self.messages = self.messages[:2] + self.messages[-(MAX_HISTORY_TURNS * 2):]

    # --- ACTION HANDLERS ---

    def handle_create(self, framework: str, name: str, flags: str = "") -> str:
        """V2 Logic: Robust Scaffolding"""
        print(Fore.MAGENTA + f"\n🏗️  [CREATE] {framework} project: {name}" + Style.RESET_ALL)
        
        # Template Dictionary
        templates = {
            'vite': f"npm create vite@latest {name} -- --template react-ts",
            'vite-react': f"npm create vite@latest {name} -- --template react-ts",
            'vite-vue': f"npm create vite@latest {name} -- --template vue-ts",
            'next': f"npx create-next-app@latest {name} --typescript --tailwind --app --yes",
            'astro': f"npm create astro@latest {name} -- --template minimal --yes --install",
            'remix': f"npx create-remix@latest {name} --template remix --yes",
            'shadcn': f"npx shadcn@latest add {name} -y" # Special case
        }

        # Fuzzy matching
        cmd = None
        fw_lower = framework.lower()
        if fw_lower == 'shadcn':
            # Handle shadcn specifically (it runs in current dir, doesn't make a new folder usually)
            cmd = templates['shadcn']
        elif fw_lower in templates:
            cmd = templates[fw_lower]
        else:
            # Fallback
            cmd = f"npm create {framework}@latest {name} --yes"

        if flags: cmd += f" {flags}"
        return self.handle_run(cmd)

    def handle_read(self, path_str: str) -> str:
        """V3 Logic: Smart Read (File vs Dir)"""
        path_str = VibeUtils.normalize_path(path_str)
        target = (self.cwd / path_str).resolve()

        print(Fore.CYAN + f"\n📖 [READ] {path_str}" + Style.RESET_ALL)

        if not target.exists():
            return f"SYSTEM: Error - {path_str} does not exist."
        
        # Security check (basic)
        if not str(target).startswith(str(self.root)):
            # Allow reading if user navigated out, but warn
            pass 

        if target.is_dir():
            print(Fore.YELLOW + "📂 Target is directory. Recursive scraping..." + Style.RESET_ALL)
            content = RepoContext.scrape(target)
            return f"SYSTEM: Directory Contents of '{path_str}':\n\n{content}"
        else:
            try:
                content = target.read_text(encoding='utf-8', errors='ignore')
                return f"SYSTEM: File '{path_str}':\n{content}"
            except Exception as e:
                return f"SYSTEM: Read Error: {e}"

    def handle_write(self, path_str: str, content: str) -> str:
        """V2+V3 Logic: Write with Diff and Backup"""
        path_str = VibeUtils.normalize_path(path_str)
        target = self.cwd / path_str
        
        print(Fore.BLUE + f"\n📝 [WRITE] {path_str}" + Style.RESET_ALL)

        # Diff
        if target.exists():
            try:
                old = target.read_text(encoding='utf-8', errors='ignore')
                print(VibeUtils.get_diff(old, content, path_str))
            except: pass
        else:
            print(Fore.GREEN + "(New File)" + Style.RESET_ALL)

        # Backup
        if target.exists():
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            safe_name = path_str.replace("\\", "_").replace("/", "_")
            bak = self.backup_dir / f"{safe_name}_{ts}.bak"
            try:
                shutil.copy2(target, bak)
            except: pass

        # Execute
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding='utf-8')
            print(Fore.GREEN + f"✅ Saved {path_str}" + Style.RESET_ALL)
            return f"SYSTEM: File {path_str} written successfully."
        except Exception as e:
            return f"SYSTEM: Write Error: {e}"

    def handle_run(self, cmd: str) -> str:
        """Ultimate Logic: V2 Auto-Fix + V3 Windows Translation"""
        
        # 1. Handle CD internally
        if cmd.strip().startswith("cd "):
            target_dir = cmd.strip().split(" ", 1)[1]
            new_path = (self.cwd / target_dir).resolve()
            if new_path.exists() and new_path.is_dir():
                self.cwd = new_path
                print(Fore.YELLOW + f"📂 Changed Directory: {self.cwd}" + Style.RESET_ALL)
                # Auto refresh context on directory change
                self.refresh_context(quiet=True)
                return f"SYSTEM: Directory changed to {self.cwd}"
            return f"SYSTEM: Error - Directory {target_dir} not found."

        # 2. Translate Unix -> Windows (V3)
        cmd = VibeUtils.convert_to_native(cmd)

        # 3. Auto-Fix Interactive (V2)
        cmd, warning = VibeUtils.auto_fix_interactive(cmd)

        print(Fore.YELLOW + f"\n⚡ [RUN] {cmd}" + Style.RESET_ALL)
        if warning: print(Fore.MAGENTA + warning + Style.RESET_ALL)

        # 4. Safety Check
        if VibeUtils.is_dangerous(cmd):
            confirm = input(Fore.RED + "🚨 DANGEROUS COMMAND. Type 'confirm' to run: " + Style.RESET_ALL)
            if confirm.lower() != 'confirm': return "SYSTEM: Command blocked by user."

        # 5. Execution
        try:
            res = subprocess.run(
                cmd, 
                shell=True, 
                cwd=self.cwd, 
                capture_output=True, 
                text=True, 
                timeout=300,
                input="y\n" # Enter key injection
            )
            
            if res.stdout: print(res.stdout)
            if res.stderr: print(Fore.RED + res.stderr + Style.RESET_ALL)

            status = "Success" if res.returncode == 0 else f"Failed ({res.returncode})"
            return f"SYSTEM: Command '{cmd}' finished. Status: {status}\nOutput:\n{res.stdout}\nErrors:\n{res.stderr}"
        except subprocess.TimeoutExpired:
            return "SYSTEM: Command timed out."
        except Exception as e:
            return f"SYSTEM: Execution Error: {e}"

    # --- MAIN LOOP ---

    def process_response(self, text: str) -> bool:
        acted = False
        
        # Regex Patterns
        patterns = {
            'WRITE': r">>>\s*WRITE\s+(.+?)\s*\n(.*?)<<<",
            'READ': r">>>\s*READ\s+(.+?)\s*<<<",
            'RUN': r">>>\s*RUN\s+(.+?)\s*<<<",
            'DELETE': r">>>\s*DELETE\s+(.+?)\s*<<<",
            'INSTALL': r">>>\s*INSTALL\s+(.+?)\s*<<<",
            'CREATE': r">>>\s*CREATE\s+(\S+)\s+(\S+)(?:\s+(.+?))?\s*<<<",
            'TREE': r">>>\s*TREE\s*<<<"
        }

        # Execution Priority: READ/TREE -> WRITE -> DELETE -> CREATE/INSTALL/RUN
        
        # Read/Tree (Non-destructive)
        for m in re.finditer(patterns['READ'], text, re.DOTALL):
            self.messages.append({"role": "system", "content": self.handle_read(m.group(1).strip())})
            acted = True
        
        if re.search(patterns['TREE'], text):
             self.messages.append({"role": "system", "content": f"SYSTEM: Tree:\n{RepoContext.get_tree(self.cwd)}"})
             acted = True

        # Write
        for m in re.finditer(patterns['WRITE'], text, re.DOTALL):
            self.messages.append({"role": "system", "content": self.handle_write(m.group(1).strip(), m.group(2).strip())})
            acted = True

        # Delete
        for m in re.finditer(patterns['DELETE'], text, re.DOTALL):
            path = m.group(1).strip()
            # Simple delete wrapper
            tgt = self.cwd / path
            if tgt.exists():
                try:
                    if tgt.is_dir(): shutil.rmtree(tgt)
                    else: tgt.unlink()
                    self.messages.append({"role": "system", "content": f"SYSTEM: Deleted {path}"})
                    print(Fore.RED + f"🗑️  Deleted {path}" + Style.RESET_ALL)
                except Exception as e:
                    self.messages.append({"role": "system", "content": f"Error deleting: {e}"})
            acted = True

        # Create
        for m in re.finditer(patterns['CREATE'], text, re.DOTALL):
            fw, name, flags = m.group(1), m.group(2), m.group(3)
            self.messages.append({"role": "system", "content": self.handle_create(fw, name, flags or "")})
            acted = True

        # Install (Using Package Manager Logic)
        for m in re.finditer(patterns['INSTALL'], text, re.DOTALL):
            pkg = m.group(1).strip()
            cmd = self.pkg_mgr.get_install_cmd(pkg)
            self.messages.append({"role": "system", "content": self.handle_run(cmd)})
            acted = True

        # Run
        for m in re.finditer(patterns['RUN'], text, re.DOTALL):
            self.messages.append({"role": "system", "content": self.handle_run(m.group(1).strip())})
            acted = True

        return acted

    def run(self):
        print(Fore.CYAN + "==========================================")
        print(f"🚀 VibeCLI Ultimate | {self.pkg_mgr.type.upper()} Detected")
        print(f"📂 {self.cwd}")
        print("==========================================" + Style.RESET_ALL)

        while True:
            try:
                user_in = input(Fore.WHITE + "\n(You) > " + Style.RESET_ALL).strip()
                if not user_in: continue
                if user_in.lower() in ['exit', 'quit']: break
                if user_in.lower() == 'refresh': 
                    print(self.refresh_context(quiet=False))
                    continue

                self.messages.append({"role": "user", "content": user_in})
                self._prune_history()

                print(Fore.CYAN + "✨ Thinking..." + Style.RESET_ALL, end="", flush=True)
                
                # Streaming Response
                full_resp = ""
                stream = self.client.chat.completions.create(
                    model=MODEL_NAME, messages=self.messages, stream=True, temperature=0.1, max_tokens=4000
                )
                
                print("\r", end="")
                for chunk in stream:
                    c = chunk.choices[0].delta.content or ""
                    full_resp += c
                    if ">>>" not in full_resp: print(c, end="", flush=True)
                
                # Clean display of command blocks
                clean_display = re.sub(r">>>.*?<<<", "", full_resp, flags=re.DOTALL).strip()
                if clean_display and ">>>" in full_resp:
                    print(Fore.GREEN + f"\n🤖 AI: {clean_display}" + Style.RESET_ALL)
                
                self.messages.append({"role": "assistant", "content": full_resp})

                # Execute Tools
                if self.process_response(full_resp):
                    # Auto Follow-up after action
                    print(Fore.CYAN + "\n🔄 Verifying actions..." + Style.RESET_ALL)
                    followup = self.client.chat.completions.create(
                         model=MODEL_NAME, messages=self.messages, temperature=0.1
                    )
                    f_text = followup.choices[0].message.content
                    self.messages.append({"role": "assistant", "content": f_text})
                    
                    clean_f = re.sub(r">>>.*?<<<", "", f_text, flags=re.DOTALL).strip()
                    if clean_f: print(Fore.GREEN + f"\n🤖 AI: {clean_f}" + Style.RESET_ALL)
                    self.process_response(f_text) # Allow chaining

            except KeyboardInterrupt:
                print("\n👋 Goodbye")
                break
            except Exception as e:
                print(Fore.RED + f"❌ Critical Error: {e}" + Style.RESET_ALL)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="VibeCLI Ultimate")
    parser.add_argument("path", nargs="?", default=".", help="Target Directory")
    parser.add_argument("--no-context", action="store_true", help="Skip initial scan")
    args = parser.parse_args()
    
    agent = VibeAgent(args.path, skip_context=args.no_context)
    agent.run()