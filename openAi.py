"""
VibeCLI - AI Software Engineer Agent (ENHANCED VERSION)
SDK: openai (OpenRouter Compatible)

ENHANCEMENTS:
- shadcn/ui component detection & installation
- Multi-package manager support (npm/pnpm/yarn/bun)
- TypeScript & CSS framework dependency handling
- Batch installations with verification
- Improved dependency resolution
"""

import os
import re
import sys
import json
import time
import subprocess
import importlib.util
import argparse
from pathlib import Path
from typing import List, Tuple, Set, Dict, Optional

from dotenv import load_dotenv
from openai import OpenAI

# ==============================================================================
# CONFIGURATION
# ==============================================================================

MODEL_NAME = "google/gemini-2.5-flash-lite:nitro"

SKIPPED_FILES: Set[str] = {
    'package-lock.json', 'yarn.lock', 'pnpm-lock.yaml', 'bun.lockb',
    'node_modules', '__pycache__', '.git', '.vs', '.idea', '.vscode',
    'dist', 'build', 'coverage', '.DS_Store', 'Thumbs.db', '.env',
    'test.py', 'vibe_terminal.py', 'vibe_terminal_enhanced.py'
}

SYSTEM_INSTRUCTION = """
You are VibeCLI, an elite AI software engineer with direct file system access.
YOUR MISSION: Transform user requests into working software.

PROTOCOL (Strict Blocks):
1. >>> WRITE {file_path}
{content}
<<<
2. >>> DELETE {file_path} <<<
3. >>> READ {file_path} <<<
4. >>> RUN {command} <<<
5. >>> INSTALL {package_manager} {package_name} <<<
6. >>> SHADCN {component_name} <<<  (for shadcn/ui components)

RULES:
- Always provide COMPLETE file content.
- Declare all dependencies using INSTALL before writing files.
- For shadcn/ui components, use >>> SHADCN {component} <<<
- Check if dependencies exist before importing.
- Use the detected package manager (npm/pnpm/yarn/bun).
"""

# Python stdlib list
PYTHON_STDLIB = {
    'abc', 'aifc', 'argparse', 'array', 'ast', 'asynchat', 'asyncio', 'asyncore',
    'atexit', 'audioop', 'base64', 'bdb', 'binascii', 'binhex', 'bisect', 'builtins',
    'bz2', 'calendar', 'cgi', 'cgitb', 'chunk', 'cmath', 'cmd', 'code', 'codecs',
    'codeop', 'collections', 'colorsys', 'compileall', 'concurrent', 'configparser',
    'contextlib', 'contextvars', 'copy', 'copyreg', 'cProfile', 'crypt', 'csv',
    'ctypes', 'curses', 'dataclasses', 'datetime', 'dbm', 'decimal', 'difflib',
    'dis', 'distutils', 'doctest', 'email', 'encodings', 'enum', 'errno', 'faulthandler',
    'fcntl', 'filecmp', 'fileinput', 'fnmatch', 'formatter', 'fractions', 'ftplib',
    'functools', 'gc', 'getopt', 'getpass', 'gettext', 'glob', 'graphlib', 'grp',
    'gzip', 'hashlib', 'heapq', 'hmac', 'html', 'http', 'idlelib', 'imaplib',
    'imghdr', 'imp', 'importlib', 'inspect', 'io', 'ipaddress', 'itertools', 'json',
    'keyword', 'lib2to3', 'linecache', 'locale', 'logging', 'lzma', 'mailbox',
    'mailcap', 'marshal', 'math', 'mimetypes', 'mmap', 'modulefinder', 'msilib',
    'msvcrt', 'multiprocessing', 'netrc', 'nis', 'nntplib', 'numbers', 'operator',
    'optparse', 'os', 'ossaudiodev', 'parser', 'pathlib', 'pdb', 'pickle', 'pickletools',
    'pipes', 'pkgutil', 'platform', 'plistlib', 'poplib', 'posix', 'posixpath',
    'pprint', 'profile', 'pstats', 'pty', 'pwd', 'py_compile', 'pyclbr', 'pydoc',
    'queue', 'quopri', 'random', 're', 'readline', 'reprlib', 'resource', 'rlcompleter',
    'runpy', 'sched', 'secrets', 'select', 'selectors', 'shelve', 'shlex', 'shutil',
    'signal', 'site', 'smtpd', 'smtplib', 'sndhdr', 'socket', 'socketserver', 'spwd',
    'sqlite3', 'ssl', 'stat', 'statistics', 'string', 'stringprep', 'struct', 'subprocess',
    'sunau', 'symbol', 'symtable', 'sys', 'sysconfig', 'syslog', 'tabnanny', 'tarfile',
    'telnetlib', 'tempfile', 'termios', 'test', 'textwrap', 'threading', 'time',
    'timeit', 'tkinter', 'token', 'tokenize', 'trace', 'traceback', 'tracemalloc',
    'tty', 'turtle', 'turtledemo', 'types', 'typing', 'unicodedata', 'unittest',
    'urllib', 'uu', 'uuid', 'venv', 'warnings', 'wave', 'weakref', 'webbrowser',
    'winreg', 'winsound', 'wsgiref', 'xdrlib', 'xml', 'xmlrpc', 'zipapp', 'zipfile',
    'zipimport', 'zlib', '_thread'
}

# Common shadcn/ui components
SHADCN_COMPONENTS = {
    'accordion', 'alert', 'alert-dialog', 'aspect-ratio', 'avatar', 'badge',
    'breadcrumb', 'button', 'calendar', 'card', 'carousel', 'chart', 'checkbox',
    'collapsible', 'combobox', 'command', 'context-menu', 'dialog', 'drawer',
    'dropdown-menu', 'form', 'hover-card', 'input', 'input-otp', 'label',
    'menubar', 'navigation-menu', 'pagination', 'popover', 'progress',
    'radio-group', 'resizable', 'scroll-area', 'select', 'separator', 'sheet',
    'skeleton', 'slider', 'sonner', 'switch', 'table', 'tabs', 'textarea',
    'toast', 'toggle', 'toggle-group', 'tooltip'
}

# ==============================================================================
# PACKAGE MANAGER DETECTION
# ==============================================================================

class PackageManager:
    """Detects and manages package manager operations."""
    
    def __init__(self, root_dir: Path):
        self.root_dir = root_dir
        self.manager = self._detect_manager()
    
    def _detect_manager(self) -> str:
        """Detect package manager from lock files."""
        if (self.root_dir / "bun.lockb").exists():
            return "bun"
        if (self.root_dir / "pnpm-lock.yaml").exists():
            return "pnpm"
        if (self.root_dir / "yarn.lock").exists():
            return "yarn"
        if (self.root_dir / "package-lock.json").exists():
            return "npm"
        # Default to npm if package.json exists
        if (self.root_dir / "package.json").exists():
            return "npm"
        return "npm"  # fallback
    
    def get_install_command(self, package: str, dev: bool = False) -> List[str]:
        """Get the install command for the detected package manager."""
        commands = {
            "npm": ["npm", "install", package] + (["--save-dev"] if dev else []),
            "pnpm": ["pnpm", "add", package] + (["-D"] if dev else []),
            "yarn": ["yarn", "add", package] + (["-D"] if dev else []),
            "bun": ["bun", "add", package] + (["-d"] if dev else [])
        }
        return commands.get(self.manager, commands["npm"])
    
    def get_shadcn_command(self, component: str) -> List[str]:
        """Get the shadcn component add command."""
        return ["npx", "shadcn@latest", "add", component, "-y"]

# ==============================================================================
# ENHANCED DEPENDENCY SCANNER
# ==============================================================================

class DependencyScanner:
    """Scans and manages project dependencies."""
    
    def __init__(self, root_dir: Path):
        self.root_dir = root_dir
        self.package_manager = PackageManager(root_dir)
    
    def scan_python_imports(self) -> Set[str]:
        """Scan all Python files for import statements."""
        imports = set()
        for py_file in self.root_dir.rglob('*.py'):
            if any(part in SKIPPED_FILES for part in py_file.parts):
                continue
            try:
                content = py_file.read_text(encoding='utf-8', errors='ignore')
                matches = re.findall(
                    r'^\s*(?:from|import)\s+([a-zA-Z_][\w]*)',
                    content,
                    re.MULTILINE
                )
                for imp in matches:
                    root_pkg = imp.split('.')[0]
                    if root_pkg not in PYTHON_STDLIB:
                        imports.add(root_pkg)
            except Exception:
                pass
        return imports
    
    def scan_package_json(self) -> Dict[str, Set[str]]:
        """Scan package.json for all dependency types."""
        deps = {
            'dependencies': set(),
            'devDependencies': set(),
            'peerDependencies': set()
        }
        
        package_json = self.root_dir / 'package.json'
        if not package_json.exists():
            return deps
        
        try:
            data = json.loads(package_json.read_text())
            for dep_type in deps.keys():
                if dep_type in data:
                    deps[dep_type].update(data[dep_type].keys())
        except Exception:
            pass
        
        return deps
    
    def scan_shadcn_components(self) -> Set[str]:
        """Scan for shadcn/ui component usage in TypeScript/JavaScript files."""
        components = set()
        
        # Check components.json
        components_json = self.root_dir / "components.json"
        if components_json.exists():
            try:
                data = json.loads(components_json.read_text())
                # shadcn/ui is configured
                components.add("_configured")
            except Exception:
                pass
        
        # Scan for component imports
        patterns = [
            r'from\s+["\']@/components/ui/([a-z-]+)["\']',
            r'import\s+.*?\s+from\s+["\']@/components/ui/([a-z-]+)["\']'
        ]
        
        for file in self.root_dir.rglob('*'):
            if file.suffix in {'.tsx', '.ts', '.jsx', '.js'} and file.is_file():
                if any(part in SKIPPED_FILES for part in file.parts):
                    continue
                try:
                    content = file.read_text(encoding='utf-8', errors='ignore')
                    for pattern in patterns:
                        matches = re.findall(pattern, content)
                        components.update(matches)
                except Exception:
                    pass
        
        return components
    
    def get_missing_python_packages(self, required: Set[str]) -> Set[str]:
        """Check which Python packages are not installed."""
        missing = set()
        for pkg in required:
            if importlib.util.find_spec(pkg) is None:
                missing.add(pkg)
        return missing
    
    def get_missing_node_packages(self, required: Set[str]) -> Set[str]:
        """Check which Node packages are not installed."""
        missing = set()
        node_modules = self.root_dir / 'node_modules'
        
        if not node_modules.exists():
            return required
        
        for pkg in required:
            # Handle scoped packages
            if pkg.startswith('@'):
                scope, name = pkg.split('/', 1)
                if not (node_modules / scope / name).exists():
                    missing.add(pkg)
            else:
                if not (node_modules / pkg).exists():
                    missing.add(pkg)
        
        return missing
    
    def get_missing_shadcn_components(self, used: Set[str]) -> Set[str]:
        """Check which shadcn components are not installed."""
        missing = set()
        components_dir = self.root_dir / "src" / "components" / "ui"
        
        if not components_dir.exists():
            return used - {"_configured"}
        
        for component in used:
            if component == "_configured":
                continue
            component_file = components_dir / f"{component}.tsx"
            if not component_file.exists():
                missing.add(component)
        
        return missing

# ==============================================================================
# AGENT
# ==============================================================================

class VibeTerminal:
    def __init__(self, target_dir="."):
        self._setup_environment()
        self._setup_ai()
        self._setup_directory(target_dir)
        self.scanner = DependencyScanner(self.root_dir)
        self._install_dependencies()

    # --------------------------------------------------------------------------
    # ENV + AI
    # --------------------------------------------------------------------------

    def _setup_environment(self):
        load_dotenv()
        self.api_key = os.getenv("OPENROUTER_API_KEY")
        if not self.api_key:
            print("❌ Error: OPENROUTER_API_KEY not found")
            sys.exit(1)

    def _setup_ai(self):
        try:
            self.client = OpenAI(
                api_key=self.api_key,
                base_url="https://openrouter.ai/api/v1",
                default_headers={
                    "HTTP-Referer": "http://localhost",
                    "X-Title": "VibeCLI"
                }
            )
            self.messages = [
                {"role": "system", "content": SYSTEM_INSTRUCTION}
            ]
        except Exception as e:
            print(f"❌ OpenRouter init failed: {e}")
            sys.exit(1)

    def _setup_directory(self, target_dir):
        self.root_dir = Path(target_dir).resolve()
        self.root_dir.mkdir(parents=True, exist_ok=True)
        print(f"📂 Working in: {self.root_dir}")

    # --------------------------------------------------------------------------
    # DEPENDENCY SCAN / INSTALL
    # --------------------------------------------------------------------------

    def _install_dependencies(self):
        """Enhanced dependency installation with shadcn support."""
        print("\n🔍 Scanning for dependencies...")
        
        # Python dependencies
        python_imports = self.scanner.scan_python_imports()
        missing_python = self.scanner.get_missing_python_packages(python_imports)
        
        # Node dependencies
        node_deps = self.scanner.scan_package_json()
        all_node_deps = node_deps['dependencies'] | node_deps['devDependencies']
        missing_node = self.scanner.get_missing_node_packages(all_node_deps)
        
        # shadcn components
        shadcn_components = self.scanner.scan_shadcn_components()
        missing_shadcn = self.scanner.get_missing_shadcn_components(shadcn_components)
        
        if not missing_python and not missing_node and not missing_shadcn:
            print("✅ All dependencies are installed")
            return
        
        print("\n📦 Missing dependencies detected:")
        if missing_python:
            print(f"  Python: {', '.join(sorted(missing_python))}")
        if missing_node:
            pm = self.scanner.package_manager.manager
            print(f"  {pm.upper()}: {', '.join(sorted(missing_node))}")
        if missing_shadcn:
            print(f"  shadcn/ui: {', '.join(sorted(missing_shadcn))}")
        
        if input("\n>> Auto-install missing packages? (y/n): ").lower() == 'y':
            # Install Python packages
            if missing_python:
                print("\n📦 Installing Python packages...")
                for pkg in missing_python:
                    self._install_python_package(pkg)
            
            # Install Node packages (batch)
            if missing_node:
                print(f"\n📦 Installing {self.scanner.package_manager.manager} packages...")
                self._install_node_packages_batch(missing_node)
            
            # Install shadcn components
            if missing_shadcn:
                print("\n🎨 Installing shadcn/ui components...")
                for component in missing_shadcn:
                    self._install_shadcn_component(component)

    def _install_python_package(self, package: str) -> bool:
        """Install a Python package."""
        try:
            cmd = [sys.executable, '-m', 'pip', 'install', package, '-q']
            result = subprocess.run(cmd, capture_output=True, text=True, cwd=self.root_dir)
            if result.returncode == 0:
                print(f"  ✅ Installed: {package}")
                return True
            else:
                print(f"  ❌ Failed: {package} - {result.stderr}")
                return False
        except Exception as e:
            print(f"  ❌ Error installing {package}: {e}")
            return False

    def _install_node_packages_batch(self, packages: Set[str]) -> bool:
        """Install Node packages in batch for efficiency."""
        if not packages:
            return True
        
        try:
            pm = self.scanner.package_manager
            # Use add command with multiple packages
            if pm.manager == "npm":
                cmd = ["npm", "install"] + list(packages)
            elif pm.manager == "pnpm":
                cmd = ["pnpm", "add"] + list(packages)
            elif pm.manager == "yarn":
                cmd = ["yarn", "add"] + list(packages)
            elif pm.manager == "bun":
                cmd = ["bun", "add"] + list(packages)
            else:
                cmd = ["npm", "install"] + list(packages)
            
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                cwd=self.root_dir,
                timeout=300
            )
            
            if result.returncode == 0:
                print(f"  ✅ Installed: {', '.join(packages)}")
                return True
            else:
                print(f"  ❌ Failed batch install: {result.stderr}")
                # Fallback to individual installs
                for pkg in packages:
                    self._install_node_package(pkg)
                return False
        except Exception as e:
            print(f"  ❌ Error batch installing: {e}")
            return False

    def _install_node_package(self, package: str, dev: bool = False) -> bool:
        """Install a single Node package."""
        try:
            cmd = self.scanner.package_manager.get_install_command(package, dev)
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                cwd=self.root_dir,
                timeout=120
            )
            if result.returncode == 0:
                print(f"  ✅ Installed: {package}")
                return True
            else:
                print(f"  ❌ Failed: {package}")
                return False
        except Exception as e:
            print(f"  ❌ Error installing {package}: {e}")
            return False

    def _install_shadcn_component(self, component: str) -> bool:
        """Install a shadcn/ui component."""
        try:
            cmd = self.scanner.package_manager.get_shadcn_command(component)
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                cwd=self.root_dir,
                timeout=120,
                shell=True
            )
            if result.returncode == 0:
                print(f"  ✅ Installed shadcn component: {component}")
                return True
            else:
                print(f"  ❌ Failed to install shadcn component: {component}")
                print(f"     Output: {result.stderr}")
                return False
        except Exception as e:
            print(f"  ❌ Error installing shadcn component {component}: {e}")
            return False

    # --------------------------------------------------------------------------
    # OPENROUTER MESSAGE HANDLING
    # --------------------------------------------------------------------------

    def send_message_safe(self, message: str):
        self.messages.append({"role": "user", "content": message})

        for attempt in range(3):
            try:
                response = self.client.chat.completions.create(
                    model=MODEL_NAME,
                    messages=self.messages,
                    temperature=0.7
                )
                reply = response.choices[0].message.content
                self.messages.append({"role": "assistant", "content": reply})
                return reply
            except Exception as e:
                if "429" in str(e):
                    wait = 10 * (attempt + 1)
                    print(f"⏳ Rate limit hit. Waiting {wait}s...")
                    time.sleep(wait)
                else:
                    print(f"❌ API error: {e}")
                    return None
        return None

    # ==========================================================================
    # SENSE: Context Awareness
    # ==========================================================================

    def get_project_context(self) -> str:
        """Enhanced context with package manager info."""
        pm = self.scanner.package_manager.manager
        context = [
            f"Current Project Structure & Content (Root: {self.root_dir.name}):",
            f"Package Manager: {pm}",
            ""
        ]
        
        # Add components.json info if exists
        components_json = self.root_dir / "components.json"
        if components_json.exists():
            context.append("shadcn/ui: CONFIGURED")
            context.append("")
        
        for path in sorted(self.root_dir.rglob('*')):
            if any(part in SKIPPED_FILES or part.startswith('.') for part in path.parts):
                continue
            if path.is_file():
                try:
                    rel_path = path.relative_to(self.root_dir)
                    if path.stat().st_size > 100_000:
                        context.append(f"--- File: {rel_path} (Skipped: Too Large) ---")
                        continue
                    content = path.read_text(encoding='utf-8', errors='ignore')
                    context.append(f"--- File: {rel_path} ---\n{content}\n")
                except Exception:
                    pass
        return "\n".join(context)

    # ==========================================================================
    # HANDS: Action Handlers
    # ==========================================================================

    def handle_install(self, manager: str, package: str) -> str:
        """Enhanced install handler with package manager detection."""
        print(f"\n📦 [AI Request] INSTALL: {package} via {manager}")
        
        # Python
        if manager == 'pip':
            if package in PYTHON_STDLIB:
                return f"SYSTEM: {package} is a standard library module"
            if importlib.util.find_spec(package) is not None:
                return f"SYSTEM: {package} is already installed"
            
            if input(f">> Install {package}? (y/n): ").lower() == 'y':
                success = self._install_python_package(package)
                return f"SYSTEM: {'Successfully' if success else 'Failed to'} installed {package}"
            return f"SYSTEM: User denied installation of {package}"
        
        # Node
        if manager in ['npm', 'pnpm', 'yarn', 'bun']:
            # Check if already installed
            if not self.scanner.get_missing_node_packages({package}):
                return f"SYSTEM: {package} is already installed"
            
            if input(f">> Install {package}? (y/n): ").lower() == 'y':
                success = self._install_node_package(package)
                return f"SYSTEM: {'Successfully' if success else 'Failed to'} installed {package}"
            return f"SYSTEM: User denied installation of {package}"
        
        return f"SYSTEM: Unsupported package manager: {manager}"

    def handle_shadcn(self, component: str) -> str:
        """Handle shadcn/ui component installation."""
        print(f"\n🎨 [AI Request] SHADCN: {component}")
        
        if component not in SHADCN_COMPONENTS:
            return f"SYSTEM: Unknown shadcn component: {component}. Valid components: {', '.join(sorted(SHADCN_COMPONENTS))}"
        
        # Check if already installed
        components_dir = self.root_dir / "components" / "ui"
        component_file = components_dir / f"{component}.tsx"
        if component_file.exists():
            return f"SYSTEM: shadcn component {component} is already installed"
        
        if input(f">> Install shadcn component '{component}'? (y/n): ").lower() == 'y':
            success = self._install_shadcn_component(component)
            return f"SYSTEM: {'Successfully' if success else 'Failed to'} installed shadcn component {component}"
        
        return f"SYSTEM: User denied installation of shadcn component {component}"

    def handle_write(self, path_str: str, content: str) -> str:
        target_path = self.root_dir / path_str
        operation = "UPDATE" if target_path.exists() else "CREATE"
        print(f"\n📝 [AI Request] {operation}: {path_str}")
        
        if input(">> Allow this change? (y/n): ").lower() == 'y':
            try:
                target_path.parent.mkdir(parents=True, exist_ok=True)
                target_path.write_text(content, encoding='utf-8')
                print(f"✅ Wrote: {path_str}")
                return f"SYSTEM: Successfully wrote file {path_str}"
            except Exception as e:
                return f"SYSTEM: Error writing {path_str}: {e}"
        return f"SYSTEM: User denied write permission for {path_str}"

    def handle_delete(self, path_str: str) -> str:
        target_path = self.root_dir / path_str
        print(f"\n🗑️  [AI Request] DELETE: {path_str}")
        if input(">> Allow deletion? (y/n): ").lower() == 'y':
            try:
                if target_path.exists():
                    os.remove(target_path)
                    print(f"✅ Deleted: {path_str}")
                    return f"SYSTEM: Deleted {path_str}"
                return f"SYSTEM: File not found: {path_str}"
            except Exception as e:
                return f"SYSTEM: Error deleting: {e}"
        return f"SYSTEM: User denied delete permission for {path_str}"

    def handle_read(self, path_str: str) -> str:
        target_path = self.root_dir / path_str
        print(f"\n👀 [AI Request] Reading: {path_str}...")
        try:
            content = target_path.read_text(encoding='utf-8', errors='replace')
            return f"SYSTEM: Content of {path_str}:\n{content}"
        except Exception as e:
            return f"SYSTEM: Error reading {path_str}: {e}"

    def handle_run(self, command: str) -> str:
        print(f"\n⚡ [AI Request] RUN SHELL: {command}")
        if input(">> Allow execution? (y/n): ").lower() == 'y':
            try:
                result = subprocess.run(
                    command, shell=True, capture_output=True, text=True, cwd=self.root_dir
                )
                output = (result.stdout + result.stderr).strip()
                print(f"Output:\n{output[:500]}..." if len(output) > 500 else f"Output:\n{output}")
                return f"SYSTEM: Command executed. Exit Code: {result.returncode}\nOutput:\n{output}"
            except Exception as e:
                return f"SYSTEM: Execution failed: {e}"
        return f"SYSTEM: User denied execution of '{command}'"

    # ==========================================================================
    # BRAIN: Parsing & Loop
    # ==========================================================================

    def process_ai_response(self, response_text: str) -> Tuple[List[str], bool]:
        patterns = {
            'INSTALL': re.compile(r">>> INSTALL (pip|npm|pnpm|yarn|bun) ([\w\-\.@/]+)\s*<<<", re.DOTALL),
            'SHADCN': re.compile(r">>> SHADCN ([\w\-]+)\s*<<<", re.DOTALL),
            'WRITE': re.compile(r">>> WRITE (.*?)\n(.*?)<<<", re.DOTALL),
            'DELETE': re.compile(r">>> DELETE (.*?)\s*<<<", re.DOTALL),
            'READ': re.compile(r">>> READ (.*?)\s*<<<", re.DOTALL),
            'RUN': re.compile(r">>> RUN (.*?)\s*<<<", re.DOTALL),
        }
        feedback = []
        action_taken = False

        # Process INSTALL first
        for manager, package in patterns['INSTALL'].findall(response_text):
            feedback.append(self.handle_install(manager.strip(), package.strip()))
            action_taken = True

        # Process SHADCN
        for component in patterns['SHADCN'].findall(response_text):
            feedback.append(self.handle_shadcn(component.strip()))
            action_taken = True

        # Process other operations
        for path, content in patterns['WRITE'].findall(response_text):
            feedback.append(self.handle_write(path.strip(), content.strip()))
            action_taken = True
        
        for path in patterns['DELETE'].findall(response_text):
            feedback.append(self.handle_delete(path.strip()))
            action_taken = True
        
        for path in patterns['READ'].findall(response_text):
            feedback.append(self.handle_read(path.strip()))
            action_taken = True
        
        for cmd in patterns['RUN'].findall(response_text):
            feedback.append(self.handle_run(cmd.strip()))
            action_taken = True

        return feedback, action_taken

    # --------------------------------------------------------------------------
    # MAIN LOOP
    # --------------------------------------------------------------------------

    def run(self):
        print(f"\n🚀 VibeCLI Enhanced (OpenRouter | {MODEL_NAME})")
        print(f"📦 Package Manager: {self.scanner.package_manager.manager}")
        
        context = self.get_project_context()
        self.send_message_safe(f"SYSTEM: Current codebase:\n{context}")

        while True:
            try:
                user = input("\n(You) > ")
                if user.lower() in {"exit", "quit"}:
                    break

                reply = self.send_message_safe(user)
                if not reply:
                    continue

                clean = re.sub(r">>>.*?<<<", "", reply, flags=re.DOTALL).strip()
                if clean:
                    print(f"\n🤖 AI:\n{clean}")

                feedback, acted = self.process_ai_response(reply)
                if acted:
                    self.send_message_safe(
                        "SYSTEM: Tool results:\n" + "\n".join(feedback)
                    )

            except KeyboardInterrupt:
                print("\n👋 Bye")
                break

# ==============================================================================
# ENTRY
# ==============================================================================

if __name__ == "__main__":
    parser = argparse.ArgumentParser("VibeCLI Enhanced (OpenRouter)")
    parser.add_argument("path", nargs="?", default=".")
    args = parser.parse_args()

    app = VibeTerminal(args.path)
    app.run()