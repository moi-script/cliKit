"""
VibeCLI v4.0 - Unified Edition
SDK: openai (OpenRouter Compatible)

COMBINES:
- v2's Advanced Package Installation & Scaffolding
- v3's Superior Command Comprehension & Smart Reading
- Cross-platform support (Windows + Unix)
- Enhanced context management

USAGE:
   python vibe_unified.py [target_directory]
   python vibe_unified.py [target_directory] --no-context
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

# Platform detection
IS_WINDOWS = sys.platform.startswith('win')
IS_UNIX = not IS_WINDOWS

# ==============================================================================
# CONFIGURATION
# ==============================================================================


# openrouter/pony-alpha
#google/gemini-2.5-flash-lite:nitro
MODEL_NAME = "openrouter/pony-alpha" 

# Security & Limits
DANGEROUS_COMMANDS = {'rm', 'del', 'format', 'mkfs', 'dd', 'shutdown', 'reboot', 'diskpart'}
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
# SYSTEM PROMPT
# ==============================================================================

SYSTEM_INSTRUCTION = """
[CRITICAL CONFIGURATION - UNIFIED EDITION]
You are VibeCLI, running in a LOCAL development environment.
The user has granted you FULL PERMISSION to create, edit, run, and DELETE files.
You are NOT a web-based chat bot. You are a CLI Agent with a PERSISTENT SHELL.

PLATFORM: {'Windows' if IS_WINDOWS else 'Unix/Mac'}

CAPABILITIES:

1. **Navigation:** You CAN use `cd`. The system tracks your current directory.
   - Example: >>> RUN cd backend <<<
   - Example: >>> RUN cd .. <<<

2. **File Operations:**
   - Read file: >>> READ file.txt <<<
   - Read directory (SMART READ): >>> READ src/ <<< (scrapes all files recursively)
   - Write file: >>> WRITE path/to/file.js
     {full_content}
     <<<
   - Delete: >>> DELETE path/to/file <<<

3. **Directory Inspection:**
   - Show tree: >>> TREE <<<
   - List files: >>> LISTFILES <<<

4. **Package Management:**
   - Install: >>> INSTALL npm package-name <<<
   - Create project: >>> CREATE framework project-name [options] <<<
   - Add UI component: >>> SHADCN component-name <<<

5. **Command Execution:**
   - Run any shell command: >>> RUN command <<<
   - System auto-converts Unix→Windows commands on Windows

>>> REFRESH <<<
Use this after file operations to re-scan the directory and update context.

PROTOCOL (Strict Command Blocks):

>>> WRITE {file_path}
{full_file_content}
<<<

>>> READ {file_path_or_directory} <<<

>>> DELETE {file_path} <<<

>>> RUN {shell_command} <<<

>>> INSTALL {package_manager} {package_name} <<<

>>> CREATE {framework} {project_name} [options] <<<

>>> SHADCN {component_name} <<<

>>> TREE <<<

>>> LISTFILES <<<

>>> REFRESH <<<

RULES:
- When using WRITE, provide the **COMPLETE** file content.
- Use relative paths from your CURRENT directory.
- For multi-step tasks, execute operations in logical order.
- READ can accept both files AND directories (smart detection).
- Always use REFRESH after creating/deleting many files.
- Available CREATE templates: vite-react, vite-react-ts, next, astro, remix, nuxt, expo, t3, and more.
"""

# ==============================================================================
# UTILITY CLASSES
# ==============================================================================

class VibeUtils:
    @staticmethod
    def make_non_interactive(command: str) -> str:
        """Wraps command to auto-answer prompts (cross-platform)."""
        if IS_WINDOWS:
            return f'echo. | {command}'
        else:
            return f"yes '' | {command}"
    
    @staticmethod
    def convert_unix_to_windows(command: str) -> str:
        """Convert common Unix commands to Windows equivalents."""
        if not IS_WINDOWS:
            return command
            
        cmd_lower = command.lower().strip()
        sorted_keys = sorted(WINDOWS_CMD_MAP.keys(), key=len, reverse=True)
        
        for unix_cmd in sorted_keys:
            if cmd_lower.startswith(unix_cmd):
                match_len = len(unix_cmd)
                if len(cmd_lower) == match_len or cmd_lower[match_len] == ' ':
                    win_cmd = WINDOWS_CMD_MAP[unix_cmd]
                    rest = command[match_len:].strip()
                    converted = f"{win_cmd} {rest}" if rest else win_cmd
                    print(f"🔧 Auto-converted: {command} → {converted}")
                    return converted
        
        return command
    
    @staticmethod
    def is_dangerous(command: str) -> bool:
        """Check if command is potentially dangerous."""
        parts = command.lower().split()
        if not parts:
            return False
            
        # Check against dangerous command list
        if parts[0] in DANGEROUS_COMMANDS:
            return True
            
        # Check for dangerous patterns
        if "rm" in command and ("-r" in command or "/ " in command):
            return True
        if IS_WINDOWS and ("del" in command or "rmdir" in command or "rd" in command):
            if "/s" in command and ("c:\\" in command.lower() or "d:\\" in command.lower()):
                return True
        
        return False
    
    @staticmethod
    def get_diff(old_content: str, new_content: str, filename: str) -> str:
        """Generate colored diff output."""
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
        """Normalize path to platform format."""
        if IS_WINDOWS:
            return path.replace('/', '\\')
        return path.replace('\\', '/')


class PackageManager:
    """Detects and manages package managers."""
    
    def __init__(self, root_dir: Path):
        self.root_dir = root_dir
        self.manager = self._detect()
    
    def _detect(self) -> str:
        """Auto-detect package manager from lock files."""
        if (self.root_dir / "bun.lockb").exists():
            return "bun"
        if (self.root_dir / "pnpm-lock.yaml").exists():
            return "pnpm"
        if (self.root_dir / "yarn.lock").exists():
            return "yarn"
        return "npm"
    
    def get_install_cmd(self, package: str) -> str:
        """Get install command for detected package manager."""
        cmds = {
            "npm": f"npm install {package}",
            "pnpm": f"pnpm add {package}",
            "yarn": f"yarn add {package}",
            "bun": f"bun add {package}"
        }
        return cmds.get(self.manager, cmds["npm"])


class ProjectTemplates:
    """Predefined project scaffolding templates."""
    
    TEMPLATES = {
        # Vite templates
        'vite-react': "npm create vite@latest {name} -- --template react",
        'vite-react-ts': "npm create vite@latest {name} -- --template react-ts",
        'vite-vue': "npm create vite@latest {name} -- --template vue",
        'vite-vue-ts': "npm create vite@latest {name} -- --template vue-ts",
        'vite-svelte': "npm create vite@latest {name} -- --template svelte",
        'vite-svelte-ts': "npm create vite@latest {name} -- --template svelte-ts",
        
        # Next.js templates
        'next': "npx create-next-app@latest {name} --typescript --tailwind --app --yes",
        'next-js': "npx create-next-app@latest {name} --javascript --tailwind --app --yes",
        'next-pages': "npx create-next-app@latest {name} --typescript --tailwind --src-dir --yes",
        
        # Astro templates
        'astro': "npm create astro@latest {name} -- --template minimal --yes --install",
        'astro-blog': "npm create astro@latest {name} -- --template blog --yes --install",
        
        # Other frameworks
        'remix': "npx create-remix@latest {name} --template remix --yes",
        'react': "npm create vite@latest {name} -- --template react-ts",
        'vue': "npm create vite@latest {name} -- --template vue-ts",
        'svelte': "npm create vite@latest {name} -- --template svelte-ts",
        'nuxt': "npx nuxi@latest init {name}",
        'expo': "npx create-expo-app@latest {name} --template blank-typescript",
        't3': "npm create t3-app@latest {name} -- --noGit",
        'solid': "npx degit solidjs/templates/ts {name}",
        'qwik': "npm create qwik@latest {name}",
    }
    
    @classmethod
    def get_command(cls, framework: str, project_name: str, options: str = "") -> Optional[str]:
        """Get scaffolding command for framework."""
        framework_lower = framework.lower()
        
        # Direct match
        if framework_lower in cls.TEMPLATES:
            command = cls.TEMPLATES[framework_lower].format(name=project_name)
        else:
            # Fuzzy match
            for key, cmd in cls.TEMPLATES.items():
                if framework_lower in key or key in framework_lower:
                    command = cmd.format(name=project_name)
                    print(f"📝 Matched '{framework}' to template: {key}")
                    break
            else:
                # Fallback: generic npm create
                print(f"⚠️  Unknown framework '{framework}'. Using generic npm create...")
                command = f"npm create {framework}@latest {project_name} -- --yes"
        
        # Append custom options if provided
        if options:
            command += f" {options}"
        
        return command
    
    @classmethod
    def list_available(cls) -> str:
        """List all available templates."""
        return """
Available CREATE templates:
  Vite: vite-react, vite-react-ts, vite-vue, vite-svelte
  Next.js: next, next-js, next-pages
  Astro: astro, astro-blog
  Others: remix, nuxt, expo, t3, solid, qwik
  Aliases: react, vue, svelte (→ vite templates)
"""


class InteractiveCommandFixer:
    """Auto-fixes interactive commands for non-interactive execution."""
    
    @staticmethod
    def fix(command: str) -> Tuple[str, str]:
        """
        Detects and auto-fixes interactive commands.
        Returns: (fixed_command, warning_message)
        """
        warnings = []
        fixed_cmd = command
        cmd_lower = command.lower()
        
        # Vite: Add --template flag if missing
        if "create vite" in cmd_lower or "create-vite" in cmd_lower:
            if "--yes" not in command and "-y" not in command:
                command = command.replace("npm create", "npm create --yes")
                command = command.replace("npx create-vite", "npx --yes create-vite")
            
            if "--template" not in command:
                warnings.append("⚠️  Vite detected without --template. Adding default react-ts.")
                fixed_cmd = f"{command} --template react-ts"
            else:
                fixed_cmd = command
        
        # Next.js: Add --yes flag
        elif "create-next-app" in cmd_lower:
            if "--yes" not in command and "-y" not in command:
                warnings.append("⚠️  Next.js detected. Adding --yes flag.")
                fixed_cmd = f"{command} --yes"
        
        # Astro
        elif "create astro" in cmd_lower:
            if "--template" not in command:
                warnings.append("⚠️  Astro detected. Adding --template minimal.")
                fixed_cmd = f"{command} --template minimal --yes"
            elif "--yes" not in command:
                fixed_cmd = f"{command} --yes"
        
        # Remix
        elif "create-remix" in cmd_lower:
            if "--template" not in command:
                warnings.append("⚠️  Remix detected. Consider adding --template flag.")
                fixed_cmd = f"{command} --template remix"
        
        # shadcn: Ensure -y flag
        elif "shadcn" in cmd_lower:
            if "-y" not in command and "--yes" not in command:
                fixed_cmd = f"{command} -y"
        
        # npm/pnpm/yarn init: Add -y flag
        elif command.strip().endswith("init"):
            if "-y" not in command and "--yes" not in command:
                warnings.append("⚠️  Init command detected. Adding -y flag.")
                fixed_cmd = f"{command} -y"
        
        # Generic create commands
        elif any(x in cmd_lower for x in ['npm create', 'npx create', 'yarn create', 'pnpm create']):
            if "--" not in command and "--yes" not in command:
                warnings.append("⚠️  Interactive create command detected.")
                warnings.append("💡 TIP: Use --yes, -y, or --template flags to avoid prompts.")
        
        warning_msg = "\n".join(warnings) if warnings else ""
        return fixed_cmd, warning_msg


# ==============================================================================
# MAIN AGENT
# ==============================================================================

class VibeAgent:
    """Unified VibeCLI Agent with enhanced capabilities."""
    
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
            default_headers={"X-Title": "VibeCLI-Unified"}
        )
        
        # Initialize message history with system prompt
        self.messages = [{"role": "system", "content": SYSTEM_INSTRUCTION}]
        
        # Load initial context
        if not skip_context:
            self._load_initial_context()
        else:
            print("⚠️  Skipping initial context load (--no-context flag)")
    
    def _load_initial_context(self):
        """Load initial repository context."""
        print(f"🔍 Scanning repo: {self.root_dir}...")
        try:
            repo_context = scrape_contents(self.root_dir)
            
            # Get directory structure
            tree_output = self._get_tree_output()
            
            # Combine structure and contents
            combined_context = (
                f"DIRECTORY STRUCTURE:\n{tree_output}\n\n"
                f"FILE CONTENTS:\n{repo_context}"
            )
            
            char_count = len(repo_context)
            print(f"✅ Context Loaded. ({char_count:,} characters)")
            
            # Add context as system message
            self.messages.append({
                "role": "system",
                "content": f"HERE IS THE CURRENT REPO CONTEXT:\n\n{combined_context}"
            })
        except Exception as e:
            print(f"⚠️  Warning: Failed to load repo context: {e}")
            print("Continuing without initial context...")
    
    def _get_tree_output(self) -> str:
        """
        Generates a clean directory tree using Python (instead of system 'tree').
        This intentionally hides node_modules, .git, and build artifacts.
        """
        # Folders and files to hide from the tree view
        IGNORE_LIST = {
            'node_modules', '.git', '.vs', '.vscode', '.idea', '__pycache__',
            'dist', 'build', 'coverage', '.next', '.nuxt', '.output',
            '.vibe', 'package-lock.json', 'pnpm-lock.yaml', 'yarn.lock', 'bun.lockb',
            'Thumbs.db', '.DS_Store'
        }

        def _generate_tree(root_path: Path, prefix: str = "") -> str:
            output = []
            try:
                # Get all items, sorted by name (Directories first looks nicer, but alphabetic is standard)
                # We sort so the tree is deterministic
                items = sorted(
                    [p for p in root_path.iterdir()],
                    key=lambda x: (not x.is_dir(), x.name.lower())
                )
            except PermissionError:
                return f"{prefix}[Access Denied]"

            # Filter out ignored items
            filtered_items = []
            for item in items:
                # 1. Exact match ignore
                if item.name in IGNORE_LIST: continue
                # 2. Ignore generic dot-folders (like .cache), but keep .env and .gitignore
                if item.name.startswith('.') and item.name not in ['.env', '.gitignore']: continue
                
                filtered_items.append(item)

            # Build the tree string
            for i, path in enumerate(filtered_items):
                is_last = (i == len(filtered_items) - 1)
                connector = "└── " if is_last else "├── "
                
                output.append(f"{prefix}{connector}{path.name}")
                
                if path.is_dir():
                    extension = "    " if is_last else "│   "
                    # Recursively build the sub-tree
                    output.append(_generate_tree(path, prefix + extension))
            
            return "\n".join(output)

        print("🌳 Generating clean directory tree (skipping node_modules & junk)...")
        
        try:
            tree_str = _generate_tree(self.root_dir)
            if not tree_str:
                return "(Empty Directory)"
            return tree_str
        except Exception as e:
            return f"[Error generating tree: {e}]"
        
    def _find_skipped_directories(self) -> List[str]:
        """Find commonly skipped large directories."""
        skip_patterns = [
            'node_modules',
            '.git',
            '__pycache__',
            '.venv',
            'venv',
            'dist',
            'build',
            '.next',
            '.nuxt',
            'target',
            'vendor',
            '.vibe'
        ]
        
        found_dirs = []
        try:
            for root, dirs, _ in os.walk(self.root_dir):
                # Only search 2 levels deep to avoid performance issues
                depth = root[len(str(self.root_dir)):].count(os.sep)
                if depth > 2:
                    dirs[:] = []  # Don't recurse deeper
                    continue
                
                for skip_pattern in skip_patterns:
                    if skip_pattern in dirs:
                        rel_path = os.path.relpath(os.path.join(root, skip_pattern), self.root_dir)
                        found_dirs.append(rel_path)
        except Exception:
            pass
        
        return sorted(set(found_dirs))  # Remove duplicates and sort
    
    def _prune_history(self):
        """Prune conversation history to maintain context limits."""
        if len(self.messages) > MAX_HISTORY_TURNS * 2:
            system_msgs = self.messages[:2]
            conversation = self.messages[2:]
            self.messages = system_msgs + conversation[-(MAX_HISTORY_TURNS * 2):]
    
    # ==============================================================================
    # COMMAND HANDLERS
    # ==============================================================================
    
    def refresh_context(self) -> str:
        """Re-scan file system and update AI context."""
        print(f"\n🔄 Refreshing context from: {self.root_dir}...")
        try:
            # Re-scrape contents
            new_context = scrape_contents(self.root_dir)
            
            # Get updated directory structure
            tree_output = self._get_tree_output()
            
            # Combine
            combined_context = (
                f"DIRECTORY STRUCTURE:\n{tree_output}\n\n"
                f"FILE CONTENTS:\n{new_context}"
            )
            
            # Find and update context message
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
            
            print(f"✅ Context updated! ({len(new_context)} chars of content)")
            return f"SYSTEM: Context refreshed.\n\nCurrent Structure:\n{tree_output}"
        except Exception as e:
            return f"SYSTEM: Error refreshing context: {e}"
    
    def handle_tree(self) -> str:
        """Show directory tree structure."""
        print("\n🌳 [REQUEST] TREE: Showing directory structure...")
        tree_output = self._get_tree_output()
        print("\n" + tree_output)
        return f"SYSTEM: Directory tree:\n{tree_output}"
    
    def handle_listfiles(self) -> str:
        """List files in current directory."""
        print("\n📁 [REQUEST] LISTFILES: Listing current directory...")
        try:
            if IS_WINDOWS:
                cmd = "dir /b"
            else:
                cmd = "ls -1"
            
            result = subprocess.run(
                cmd,
                shell=True,
                cwd=self.current_cwd,
                capture_output=True,
                text=True,
                timeout=10
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
        - If path is a file → Returns content
        - If path is a directory → Returns ALL files inside (recursive scrape)
        """
        rel_path = VibeUtils.normalize_path(rel_path)
        path = (self.root_dir / rel_path).resolve()
        
        print(f"\n📖 [REQUEST] READ: {rel_path}")
        
        # Security check
        if not str(path).startswith(str(self.root_dir)):
            return "SYSTEM: Error - Access denied. Can only read files inside project root."
        
        if not path.exists():
            return f"SYSTEM: Error - Path {rel_path} does not exist."
        
        try:
            # Directory: Scrape all contents
            if path.is_dir():
                print(f"📂 Detected directory. Scraping all contents of: {rel_path}...")
                content = scrape_contents(path)
                return f"SYSTEM: Scraped contents of directory '{rel_path}':\n\n{content}"
            
            # File: Read it
            else:
                content = path.read_text(encoding='utf-8', errors='ignore')
                return f"SYSTEM: Content of {rel_path}:\n{content}"
        except Exception as e:
            return f"SYSTEM: Read error: {e}"
    
    def handle_cd(self, target: str) -> str:
        """
        Master function for changing directories.
        Updates state, OS process, and AI context.
        """
        print(f"\n📂 [REQUEST] CD: {target}")

        # 1. Normalize path separators (Windows/Unix)
        if IS_WINDOWS: 
            target = target.replace('/', '\\')
        
        # 2. Resolve absolute path relative to current tracking
        new_path = (self.current_cwd / target).resolve()
        
        # 3. Validation
        if not new_path.exists():
            return f"SYSTEM: Error - Directory '{target}' does not exist."
        if not new_path.is_dir():
            return f"SYSTEM: Error - '{target}' is not a directory."

        try:
            # 4. Update Internal State
            self.current_cwd = new_path
            
            # 5. Update Actual Process State (Critical for relative paths in Python)
            os.chdir(self.current_cwd)
            
            print(f"✅ Changed directory to: {self.current_cwd}")
            
            # 6. REFRESH CONTEXT (Critical so AI sees new files)
            return self.refresh_context()
            
        except PermissionError:
            return f"SYSTEM: Error - Permission denied accessing {target}"
        except Exception as e:
            return f"SYSTEM: Error changing directory: {e}"

    def handle_write(self, rel_path: str, new_content: str) -> str:
        """Write content to file with diff preview and backup."""
        rel_path = VibeUtils.normalize_path(rel_path)
        path = self.root_dir / rel_path
        exists = path.exists()
        
        print(f"\n📝 [REQUEST] WRITE: {rel_path}")
        
        # Show diff if file exists
        if exists:
            try:
                old_content = path.read_text(encoding='utf-8')
                print("\n--- DIFF CHECK ---")
                print(VibeUtils.get_diff(old_content, new_content, rel_path))
                print("------------------\n")
            except:
                pass
        
        # Confirm with user
        response = input(">> Apply changes? (y/n): ").lower().strip()
        if response not in ['y', 'yes']:
            return f"SYSTEM: User denied write to {rel_path}"
        
        try:
            # Backup existing file
            if exists:
                ts = datetime.now().strftime("%Y%m%d_%H%M%S")
                safe_name = rel_path.replace("/", "_").replace("\\", "_")
                bak = self.backup_dir / f"{safe_name}_{ts}.bak"
                shutil.copy2(path, bak)
                print(f"💾 Backup saved: {bak.name}")
            
            # Write new content
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(new_content, encoding='utf-8')
            print(f"✅ Successfully wrote {rel_path}")
            return f"SYSTEM: File {rel_path} updated successfully."
        except Exception as e:
            return f"SYSTEM: Write error: {e}"
    
    def handle_delete(self, rel_path: str) -> str:
        """Delete file or directory with confirmation and backup."""


        rel_path = VibeUtils.normalize_path(rel_path)
        path = self.root_dir / rel_path
        
        print(f"\n🗑️  [REQUEST] DELETE: {rel_path}")
        
        if not path.exists():
            return f"SYSTEM: Error - Path {rel_path} does not exist."
        
        is_dir = path.is_dir()
        item_type = "directory" if is_dir else "file"
        
        # Show directory size if applicable
        if is_dir:
            try:
                file_count = sum(1 for _ in path.rglob('*') if _.is_file())
                print(f"⚠️  This directory contains {file_count} files")
            except:
                pass
        
        # Confirm deletion
        response = input(f">> Delete this {item_type}? (y/n): ").lower().strip()
        if response not in ['y', 'yes']:
            return f"SYSTEM: User denied delete of {rel_path}"
        
        try:
            # Backup file (not directories - too large)
            if not is_dir:
                ts = datetime.now().strftime("%Y%m%d_%H%M%S")
                safe_name = rel_path.replace("/", "_").replace("\\", "_")
                bak = self.backup_dir / f"{safe_name}_{ts}.bak"
                shutil.copy2(path, bak)
                print(f"💾 Backup saved: {bak.name}")
            
            # Delete
            if is_dir:
                shutil.rmtree(path)
                print(f"✅ Successfully deleted directory {rel_path}")
            else:
                path.unlink()
                print(f"✅ Successfully deleted file {rel_path}")
            
            return f"SYSTEM: {item_type.capitalize()} {rel_path} deleted successfully."
        except Exception as e:
            return f"SYSTEM: Delete error: {e}"
        
        
    def handle_run(self, command: str) -> str:
        """Execute shell command with Server Guard and Auto-Window support."""
    
    # 1. Delegate 'cd' commands
        if command.strip().startswith("cd "):
            target = command.strip().split(" ", 1)[1]
            if IS_WINDOWS:
                target = target.replace('/', '\\')
            new_path = (self.current_cwd / target).resolve()

            if new_path.exists() and new_path.is_dir():
                self.current_cwd = new_path
                print(f"📂 Changed directory to: {self.current_cwd}")
                return f"SYSTEM: Directory changed to {self.current_cwd}"
            else:
                return f"SYSTEM: Error - Directory {target} not found."

        # 2. Convert Unix -> Windows
        command = VibeUtils.convert_unix_to_windows(command)

        # 3. Auto-fix Windows rm -rf commands
        if IS_WINDOWS and command.strip().startswith("rm -"):
            if "-r" in command or "-rf" in command:
                parts = command.split()
                target_part = parts[-1]

                if target_part.endswith("*") or target_part.endswith("/") or target_part.endswith("\\"):
                    clean_target = target_part.replace("/", "\\")
                    if not clean_target.endswith("*"):
                        clean_target += "*"
                    command = f"del /s /q {clean_target}"
                    print(f"🔧 Auto-fixed to Windows: {command}")
                else:
                    clean_target = target_part.replace("/", "\\")
                    command = f"rmdir /s /q {clean_target}"
                    print(f"🔧 Auto-fixed to Windows: {command}")

        # 4. Interactive Fixes (npm create, etc.)
        original_cmd = command
        is_create_cmd = any(x in command.lower() for x in [
            'npm create', 'npx create', 'yarn create', 'pnpm create',
            'npm init', 'yarn init', 'pnpm init'
        ])

        if is_create_cmd:
            command, warning = InteractiveCommandFixer.fix(command)
        else:
            warning = ""

        print(f"\n⚡ [REQUEST] RUN: {command}")
        if warning:
            print(f"\n{warning}")
            if command != original_cmd:
                print(f"📝 Modified: {original_cmd} → {command}")

        # --- SERVER GUARD 2.0 ---
        server_patterns = [
            'npm run dev', 'npm start', 'yarn dev', 'yarn start', 
            'pnpm dev', 'pnpm start', 'bun dev', 'bun run dev',
            'python manage.py runserver', 'uvicorn', 'nodemon'
        ]

        is_server = any(s in command.lower() for s in server_patterns)

        if is_server:
            print(f"\n⚠️  Likely Server Command Detected: '{command}'")

            if IS_WINDOWS:
                # OPTION A: Launch in New Window (Non-Blocking)
                print("💡 TIP: I can launch this in a new window so VibeCLI stays active.")
                response = input(">> Launch in new window? (Y/n): ").lower().strip()

                if response in ['', 'y', 'yes']:
                    print(f"🚀 Launching server in separate window...")
                    # 'start' command opens a new cmd window
                    # /k keeps the window open even if the server crashes
                    full_cmd = f'start "{command}" cmd /k "cd /d {self.current_cwd} && {command}"'
                    subprocess.run(full_cmd, shell=True)

                    return f"SYSTEM: Successfully launched '{command}' in a new background window. The server is now running."

            # OPTION B: Block Current Window (Standard)
            print("🛑 VibeCLI will FREEZE if you run this here.")
            print("💡 TIP: To test if your code compiles, ask me to run 'npm run build' instead.")
            confirm = input(">> Run here anyway? (The CLI will hang until Ctrl+C) (y/N): ").lower().strip()

            if confirm not in ['y', 'yes']:
                return f"SYSTEM: Skipped '{command}' to prevent freezing. User will run it manually."

            # If we get here, the user wants to freeze
            print(f"🚀 Starting {command}...")
            print("✅ Server is running. (Press Ctrl+C to stop it and return to VibeCLI)")

        # -------------------------

        # 5. Safety Check (Standard)
        if VibeUtils.is_dangerous(command):
            confirm = input("🚨 DANGEROUS COMMAND! Type 'confirm' to proceed: ").strip()
            if confirm != "confirm":
                return "SYSTEM: Blocked dangerous command."

        # 6. User confirmation for non-server commands
        if not is_server:
            response = input(">> Execute? (y/n): ").lower().strip()
            if response not in ['y', 'yes']:
                return "SYSTEM: User denied command execution."

        # 7. Execution
        try:
            print("\n📟 Running command...")
            print("-" * 50)

            # If it's a server run "here", this line blocks forever until Ctrl+C
            res = subprocess.run(
                command,
                shell=True,
                cwd=self.current_cwd,
                capture_output=True,
                text=True,
                timeout=300,
                input="y\n"  # Auto-answer prompts
            )

            # For non-servers or completed commands, print output
            if res.stdout:
                print("Output:")
                # Truncate very long output
                if len(res.stdout) > 2000:
                    print(res.stdout[:2000] + "\n... (output truncated)")
                else:
                    print(res.stdout)

            if res.stderr:
                print("Error/Warnings:")
                if len(res.stderr) > 2000:
                    print(res.stderr[:2000] + "\n... (output truncated)")
                else:
                    print(res.stderr)

            print("-" * 50)

            if res.returncode == 0:
                print("✅ Command completed successfully")
            else:
                print(f"⚠️  Command exited with code: {res.returncode}")

            return f"SYSTEM: Code: {res.returncode}\nOut: {res.stdout}\nErr: {res.stderr}"

        except subprocess.TimeoutExpired:
            print("\n❌ Command timeout (5 minutes)")
            return "SYSTEM: Command timeout (5 minutes)"
        except KeyboardInterrupt:
            print("\n🛑 User stopped the command (Ctrl+C)")
            return "SYSTEM: User stopped the command (Ctrl+C)."
        except Exception as e:
            print(f"\n❌ Error executing command: {e}")
            return f"SYSTEM: Error: {e}"
    def handle_install(self, manager: str, pkg: str) -> str:
        """Install package using detected package manager."""
        print(f"\n📦 [REQUEST] INSTALL: {pkg}")
        return self.handle_run(self.pkg_manager.get_install_cmd(pkg))
    
    def handle_create(self, framework: str, project_name: str, options: str = "") -> str:
        """Create project AND automatically enter the new directory."""
        print(f"\n🏗️  [REQUEST] CREATE: {framework} project '{project_name}'")
        
        command = ProjectTemplates.get_command(framework, project_name, options)
        
        if not command:
            return f"SYSTEM: Error - Unknown framework '{framework}'"

        print(f"📦 Command: {command}")
        
        # 1. Run the scaffolding command
        result = self.handle_run(command)
        
        # 2. Check if it worked (Primitive check for success code or folder existence)
        # We check if the folder now exists to be sure.
        new_project_path = self.current_cwd / project_name
        
        if new_project_path.exists() and new_project_path.is_dir():
            print(f"\n🚀 Project created successfully. Auto-entering '{project_name}'...")

            # 3. AUTO-CD into the new folder
            # We call handle_cd directly to trigger the state update and context refresh
            cd_result = self.handle_cd(project_name)
            
            return f"{result}\n\nSYSTEM: Automatically entered new project directory.\n{cd_result}"
            
        return result


    def handle_shadcn(self, component: str) -> str:
        """Add shadcn/ui component."""
        print(f"\n🎨 [REQUEST] SHADCN: {component}")
        return self.handle_run(f"npx shadcn@latest add {component} -y")
    
    # ==============================================================================
    # TOOL CALL PROCESSING
    # ==============================================================================
    
    def process_tool_calls(self, response_text: str) -> Tuple[List[str], bool]:
        """Parse and execute tool calls from AI response."""
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
            'SHADCN': re.compile(r">>>\s*SHADCN\s+(.+?)\s*<<<", re.DOTALL),
            'DELETE': re.compile(r">>>\s*DELETE\s+(.+?)\s*<<<", re.DOTALL),
            'CREATE': re.compile(r">>>\s*CREATE\s+(\S+)\s+(\S+)(?:\s+(.+?))?\s*<<<", re.DOTALL),
            'CD': re.compile(r">>>\s*CD\s+(.+?)\s*<<<", re.DOTALL),
        }
        
        # Execution order: READ → TREE → LISTFILES → WRITE → DELETE → RUN → INSTALL → CREATE → SHADCN → REFRESH
        
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

        for path in patterns['CD'].findall(response_text):
            feedback.append(self.handle_cd(path.strip()))
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
        
        for match in patterns['CREATE'].findall(response_text):
            framework, project_name, options = match
            options = options.strip() if options else ""
            feedback.append(self.handle_create(framework.strip(), project_name.strip(), options))
            action_taken = True
        
        for comp in patterns['SHADCN'].findall(response_text):
            feedback.append(self.handle_shadcn(comp.strip()))
            action_taken = True
        
        for _ in patterns['REFRESH'].findall(response_text):
            feedback.append(self.refresh_context())
            action_taken = True
        
        return feedback, action_taken
    
    # ==============================================================================
    # MAIN LOOP
    # ==============================================================================
    def controlPrompt(self, user_input: str) -> str:
        return (
            f"ANALYZE THE FOLLOWING REQUEST: '{user_input}'\n"
            "CLASSIFY IT INTO ONE OF THESE CATEGORIES: "
            # Changed CHANGE_DIR to CD to match your regex pattern
            "[TREE, LISTFILES, CD, READ, WRITE, CREATE, INSTALL, RUN, SHADCN, DELETE, REFRESH, CHAT]\n" 
            "RULES:\n"
            "1. If it requires file system access, return ONLY the category name.\n"
            "2. If it is a general question or conversation, return 'CHAT'.\n"
            "3. DO NOT output any other text.\n"
            "RESPONSE:"
        )
    def run(self):
        """Main interaction loop."""
        platform = "Windows" if IS_WINDOWS else "Unix/Mac"
        print(f"\n🚀 VibeCLI Unified v4.0 | {MODEL_NAME}")
        print(f"📂 Root: {self.root_dir}")
        print(f"🖥️  Platform: {platform}")
        print(f"📦 Package Manager: {self.pkg_manager.manager}")
        print("--------------------------------------------------")
        print("💡 Commands: TREE, LISTFILES, READ, WRITE, CREATE, DELETE INSTALL, RUN")
        print("💡 Type 'exit' or 'quit' to end session\n")
        
        while True:
            try:
                user_input = input("(You) > ")
                
                if user_input.lower() in ['exit', 'quit']:
                    print("👋 Goodbye!")
                    break
                
                if not user_input.strip():
                    continue
                
                # 1. Ask AI to classify intent (Ghost Request)
                # We don't save this to history permanently, we just use it to guide the next step.
                intent_prompt = self.controlPrompt(user_input)
                
                print("✨ Analyzing intent...", end="", flush=True)
                
                # Quick non-streaming call for classification
                intent_response = self.client.chat.completions.create(
                    model="google/gemini-2.5-flash-lite:nitro",
                    messages=[{"role": "user", "content": intent_prompt}],
                    max_tokens=10,
                    temperature=0.1 # Strict!
                ).choices[0].message.content.strip()
                
                print(f"\r✨ Intent detected: [{intent_response}]")
                
                # 2. Handle the Intent
                if intent_response == "CHAT":
                    # It's just talk. Add user input normally.
                    self.messages.append({"role": "user", "content": user_input})
                else:
                    # It's an action! Force the AI to execute it.
                    # We prefix the input with the intent to make sure it follows through.
                    system_guidance = f"ACTION REQUIRED: {intent_response}. User Request: {user_input}"
                    self.messages.append({"role": "user", "content": system_guidance})

                
                # Add user message
                # self.messages.append({"role": "user", "content": self.controlPrompt(user_input) })
                self._prune_history()
                
                # Stream AI response
                print("✨ Thinking...", end="", flush=True)
                
                stream = self.client.chat.completions.create(
                    model=MODEL_NAME,
                    messages=self.messages,
                    max_tokens=2000,
                    temperature=0.1,
                    stream=True
                )
                
                print("\r", end="")
                full_response = ""
                
                for chunk in stream:
                    content = chunk.choices[0].delta.content or ""
                    if content:
                        full_response += content
                        # Only print if we haven't hit a command block
                        if ">>>" not in full_response:
                            print(content, end="", flush=True)
                
                # Add assistant response to history

                self.messages.append({"role": "assistant", "content": full_response})
                
                # Display clean response (without command blocks)
                clean_display = re.sub(r">>>.*?<<<", "", full_response, flags=re.DOTALL).strip()
                if clean_display and ">>>" in full_response:
                    print(f"\n🤖 AI: {clean_display}")
                
                # Process tool calls
                feedback, acted = self.process_tool_calls(full_response)
                
                if acted:
                    tool_output = "SYSTEM: Results:\n" + "\n".join(feedback)
                    self.messages.append({"role": "system", "content": tool_output})
                    
                    # Check for errors
                    has_errors = any("Error" in f or "denied" in f.lower() or "Blocked" in f for f in feedback)
                    
                    if not has_errors:
                        print("\n🔄 Getting AI follow-up...")
                        
                        # Get follow-up response
                        followup = self.client.chat.completions.create(
                            model=MODEL_NAME,
                            messages=self.messages,
                            max_tokens=2000,
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


# ==============================================================================
# ENTRY POINT
# ==============================================================================

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="VibeCLI Unified v4.0 - AI-Powered Development Assistant",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python vibe_unified.py                    # Current directory
  python vibe_unified.py ./my-project       # Specific directory
  python vibe_unified.py . --no-context     # Skip initial scan
        """
    )
    parser.add_argument(
        "path",
        nargs="?",
        default=".",
        help="Project root directory (default: current directory)"
    )
    parser.add_argument(
        "--no-context",
        action="store_true",
        help="Skip initial codebase scanning for faster startup"
    )
    
    args = parser.parse_args()
    
    agent = VibeAgent(args.path, skip_context=args.no_context)
    agent.run()