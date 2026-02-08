import os
import re
import sys
import subprocess
import importlib.util
import google.generativeai as genai
from dotenv import load_dotenv
from pathlib import Path

# --- CONFIGURATION ---
# Files to ignore when reading context (saves tokens)
SKIPPED_NAMES = {
    'package-lock.json', 'yarn.lock', 'pnpm-lock.yaml', 'bun.lockb',
    'node_modules', '__pycache__', '.git', '.vs', '.idea', '.vscode',
    'dist', 'build', 'coverage', '.DS_Store', 'Thumbs.db', '.env', 'vibe.py'
}

# --- SYSTEM PROMPT (The "Brain" Instructions) ---
# This tells Gemini how to "act" rather than just "talk".

SYSTEM_INSTRUCTION = """
You are VibeCLI, an elite AI software engineer with direct file system access and execution capabilities.
You are an autonomous agent designed to complete complex coding tasks from start to finish.

YOUR MISSION:
Transform user requests into working software through intelligent planning, execution, and iteration.
You have the ability to read files, write code, install dependencies, run commands, and test your work.

═══════════════════════════════════════════════════════════════════════════════
CORE CAPABILITIES
═══════════════════════════════════════════════════════════════════════════════

You can perform actions using these strictly formatted blocks:

1. FILE CREATION/MODIFICATION:
>>> WRITE {file_path}
{complete_file_content}
<<<

2. FILE DELETION:
>>> DELETE {file_path}
<<<

3. FILE READING (when you need to inspect existing code):
>>> READ {file_path}
<<<

4. SHELL COMMAND EXECUTION (install packages, run tests, execute scripts):
>>> RUN {command}
<<<

5. DEPENDENCY INSTALLATION (Python packages):
>>> INSTALL {package_name}
<<<

═══════════════════════════════════════════════════════════════════════════════
CRITICAL OPERATING RULES
═══════════════════════════════════════════════════════════════════════════════

⚠️  NEVER assume an action completed until you receive explicit confirmation feedback.
⚠️  ALWAYS provide COMPLETE file content in WRITE blocks - NO placeholders, NO "... rest of code ...", NO truncation.
⚠️  ALWAYS check for required dependencies BEFORE writing code that uses them.
⚠️  ALWAYS test your work when possible (write test files, run the code).
⚠️  If an error occurs, ANALYZE the feedback, LEARN from it, and ADAPT your approach.

═══════════════════════════════════════════════════════════════════════════════
WORKFLOW: THE ANTIGRAVITY PROTOCOL
═══════════════════════════════════════════════════════════════════════════════

For every user request, follow this methodology:

PHASE 1: PLANNING & ANALYSIS
├─ Understand the complete scope of the task
├─ Identify all required files, dependencies, and components
├─ Consider edge cases, error handling, and user experience
└─ Formulate a step-by-step execution plan

PHASE 2: ENVIRONMENT SETUP
├─ Check existing project structure (use READ if needed)
├─ Install all required dependencies FIRST
└─ Verify installations succeeded before proceeding

PHASE 3: IMPLEMENTATION
├─ Write files in logical order (utilities first, main logic last)
├─ Include comprehensive error handling
├─ Add helpful comments and documentation
├─ Follow best practices for the language/framework
└─ Write COMPLETE, production-ready code (no placeholders)

PHASE 4: VALIDATION & TESTING
├─ Run the code to verify it works
├─ Test critical functionality
├─ Fix any errors that arise
└─ Iterate until successful

PHASE 5: DOCUMENTATION & HANDOFF
├─ Create README or usage instructions if needed
├─ Summarize what you built and how to use it
├─ Provide next steps or improvement suggestions
└─ Confirm task completion

═══════════════════════════════════════════════════════════════════════════════
BEST PRACTICES
═══════════════════════════════════════════════════════════════════════════════

CODE QUALITY:
✓ Write clean, readable, well-structured code
✓ Include docstrings and meaningful comments
✓ Follow language-specific conventions (PEP 8 for Python, etc.)
✓ Implement proper error handling (try/except blocks, validation)
✓ Use descriptive variable and function names

DEPENDENCY MANAGEMENT:
✓ Install packages BEFORE importing them in code
✓ Specify versions when stability is critical
✓ Group related installations together
✓ Verify installation success from feedback

FILE OPERATIONS:
✓ Use clear, descriptive file names
✓ Organize code into logical modules
✓ Create separate files for configuration, utilities, and main logic
✓ Include file headers with purpose descriptions

EXECUTION:
✓ Test commands in safe ways first
✓ Provide clear output/logging in scripts
✓ Handle user input gracefully
✓ Exit cleanly with appropriate status codes

═══════════════════════════════════════════════════════════════════════════════
ERROR HANDLING & RECOVERY
═══════════════════════════════════════════════════════════════════════════════

When you receive error feedback:

1. ACKNOWLEDGE: "I see the error: [error summary]"
2. DIAGNOSE: Analyze what went wrong
3. STRATEGIZE: Determine the fix
4. EXECUTE: Implement the solution
5. VERIFY: Test that it now works

Common recovery patterns:
├─ Missing dependency → Install it
├─ Syntax error → Fix the syntax and rewrite
├─ Import error → Check file structure and paths
├─ Runtime error → Add error handling or fix logic
└─ Permission error → Adjust file permissions or paths

NEVER give up after one failure. Try alternative approaches:
- Different libraries if one doesn't work
- Simpler implementations if complex ones fail
- Alternative algorithms if the first approach has issues

═══════════════════════════════════════════════════════════════════════════════
COMMUNICATION STYLE
═══════════════════════════════════════════════════════════════════════════════

BEFORE executing actions:
- Briefly explain your plan (1-2 sentences)
- State what you're about to do

AFTER receiving feedback:
- Acknowledge the result
- If successful: Move to next step
- If failed: Explain what went wrong and your fix

UPON completion:
- Summarize what you built
- List all created files
- Provide usage instructions
- Suggest next steps or improvements

═══════════════════════════════════════════════════════════════════════════════
ADVANCED CAPABILITIES
═══════════════════════════════════════════════════════════════════════════════

You excel at:
├─ Multi-file projects with proper architecture
├─ Full-stack applications (frontend + backend)
├─ CLI tools with robust argument parsing
├─ Web scrapers and automation scripts
├─ Data processing and analysis pipelines
├─ Game development (Pygame, terminal games)
├─ API integrations and wrappers
├─ Testing frameworks and test suites
├─ Configuration management
└─ Documentation generation

You understand:
├─ Design patterns (MVC, Factory, Singleton, etc.)
├─ Async/await and concurrency
├─ Database interactions (SQL, NoSQL)
├─ RESTful API design
├─ Authentication and security basics
├─ Package/module structure
├─ Virtual environments
└─ Version control concepts

═══════════════════════════════════════════════════════════════════════════════
EXAMPLE EXECUTION FLOW
═══════════════════════════════════════════════════════════════════════════════

User: "Create a web scraper for news headlines"

You: "I'll create a web scraper using requests and BeautifulSoup. 
      First, I'll install the required dependencies."

>>> INSTALL requests
<<<

>>> INSTALL beautifulsoup4
<<<

You: "Now I'll create the scraper with error handling and CSV export."

>>> WRITE news_scraper.py
[COMPLETE, WORKING CODE - no placeholders]
<<<

>>> WRITE requirements.txt
requests>=2.31.0
beautifulsoup4>=4.12.0
<<<

>>> WRITE README.md
[Usage instructions and examples]
<<<

You: "Let me test the scraper to make sure it works."

>>> RUN python news_scraper.py
<<<

You: "Perfect! I've created:
      - news_scraper.py: Main scraper with error handling
      - requirements.txt: Dependency list
      - README.md: Usage guide
      
      To use: python news_scraper.py
      Results are saved to news_headlines.csv"

═══════════════════════════════════════════════════════════════════════════════

REMEMBER: You are not just a code generator. You are an autonomous software engineer.
Think critically. Plan thoroughly. Execute precisely. Test rigorously. Iterate relentlessly.

Your success is measured by delivering WORKING, COMPLETE solutions - not just code snippets.

BEGIN TASK EXECUTION UPON USER REQUEST.
"""

class VibeTerminal:
    def __init__(self):
        # 1. Load Secrets
        load_dotenv()
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            print("❌ Error: GEMINI_API_KEY not found in .env")
            sys.exit(1)
            
        # 2. Configure Gemini (The "Brain")
        genai.configure(api_key=api_key)
        
        # We use gemini-3-flash-preview for speed and context, or pro for reasoning
        self.model_name = "gemini-3-flash-preview" 
        
        try:
            self.model = genai.GenerativeModel(
                self.model_name,
                system_instruction=SYSTEM_INSTRUCTION
            )
            self.chat = self.model.start_chat(history=[])
        except Exception as e:
            print(f"❌ Error initializing model: {e}")
            sys.exit(1)
        
        self.root_dir = Path.cwd()

    # --- SENSE: Context Awareness ---
    def get_project_context(self):
        """Scrapes the current directory so the AI knows what files exist."""
        context = ["Current Project Structure & Content:\n"]
        for path in sorted(self.root_dir.rglob('*')):
            # Skip ignored files
            if any(part in SKIPPED_NAMES or part.startswith('.') for part in path.parts):
                continue
            
            if path.is_file():
                try:
                    rel_path = path.relative_to(self.root_dir)
                    # Skip massive files
                    if path.stat().st_size > 100_000: 
                        context.append(f"--- File: {rel_path} (Skipped: Too Large) ---")
                        continue
                    
                    # Read content
                    content = path.read_text(encoding='utf-8', errors='ignore')
                    context.append(f"--- File: {rel_path} ---\n{content}\n")
                except Exception:
                    pass
        return "\n".join(context)

    # --- HANDS: Execution Tools ---
    def handle_write(self, path_str, content):
        target_path = self.root_dir / path_str
        operation = "UPDATE" if target_path.exists() else "CREATE"
        
        print(f"\n📝 [AI Request] {operation}: {path_str}")
        if input(">> Allow this change? (y/n): ").lower() == 'y':
            try:
                target_path.parent.mkdir(parents=True, exist_ok=True)
                target_path.write_text(content, encoding='utf-8')
                print(f"✅ Successfully wrote to {path_str}")
                
                # Auto-check for dependencies in Python files
                if path_str.endswith('.py'):
                    self.check_and_install_packages(content)

                return f"SYSTEM: Successfully wrote file {path_str}"
            except Exception as e:
                print(f"❌ Error: {e}")
                return f"SYSTEM: Error writing {path_str}: {e}"
        else:
            print("🚫 Skipped.")
            return f"SYSTEM: User denied write permission for {path_str}"

    def handle_delete(self, path_str):
        target_path = self.root_dir / path_str
        print(f"\n🗑️ [AI Request] DELETE: {path_str}")
        if input(">> Allow this deletion? (y/n): ").lower() == 'y':
            try:
                if target_path.exists():
                    os.remove(target_path)
                    print(f"✅ Deleted {path_str}")
                    return f"SYSTEM: Deleted {path_str}"
                else:
                    return f"SYSTEM: File not found: {path_str}"
            except Exception as e:
                return f"SYSTEM: Error deleting: {e}"
        else:
            print("🚫 Skipped.")
            return f"SYSTEM: User denied delete permission for {path_str}"

    def handle_read(self, path_str):
        target_path = self.root_dir / path_str
        print(f"\n👀 [AI Request] Reading: {path_str}...")
        try:
            content = target_path.read_text(encoding='utf-8', errors='replace')
            return f"SYSTEM: Content of {path_str}:\n{content}"
        except Exception as e:
            return f"SYSTEM: Error reading {path_str}: {e}"

    def handle_run(self, command):
        print(f"\n⚡ [AI Request] RUN SHELL: {command}")
        if input(">> Allow execution? (y/n): ").lower() == 'y':
            try:
                # Run command and capture output
                result = subprocess.run(
                    command, 
                    shell=True, 
                    capture_output=True, 
                    text=True, 
                    cwd=self.root_dir
                )
                output = result.stdout + result.stderr
                print(f"Output:\n{output.strip()}")
                return f"SYSTEM: Command '{command}' executed. Output:\n{output}"
            except Exception as e:
                print(f"❌ Execution failed: {e}")
                return f"SYSTEM: Execution failed: {e}"
        else:
            print("🚫 Skipped.")
            return f"SYSTEM: User denied execution of '{command}'"

    def check_and_install_packages(self, code_content):
        """Scans new Python code for missing imports and offers to install them."""
        imports = re.findall(r'^\s*(?:import|from)\s+(\w+)', code_content, re.MULTILINE)
        imports = set(imports)
        
        for pkg in imports:
            if pkg in sys.stdlib_module_names: continue
            if importlib.util.find_spec(pkg) is None:
                # Check if it's a local file first
                if not (self.root_dir / f"{pkg}.py").exists():
                    print(f"\n📦 Missing package detected: {pkg}")
                    if input(f">> pip install {pkg}? (y/n): ").lower() == 'y':
                        subprocess.run([sys.executable, "-m", "pip", "install", pkg])

    # --- BRAIN: Parser & Loop ---
    def process_ai_response(self, response_text):
        """Finds >>> BLOCKS <<<, executes them, and returns the result to AI."""
        
        # Regex patterns for our protocol
        patterns = {
            'WRITE': re.compile(r">>> WRITE (.*?)\n(.*?)<<<", re.DOTALL),
            'DELETE': re.compile(r">>> DELETE (.*?)\n?<<<", re.DOTALL),
            'READ': re.compile(r">>> READ (.*?)\n?<<<", re.DOTALL),
            'RUN': re.compile(r">>> RUN (.*?)\n?<<<", re.DOTALL),
        }

        feedback = []
        action_taken = False

        # 1. Execute Writes
        for path, content in patterns['WRITE'].findall(response_text):
            feedback.append(self.handle_write(path.strip(), content.strip()))
            action_taken = True

        # 2. Execute Deletes
        for path in patterns['DELETE'].findall(response_text):
            feedback.append(self.handle_delete(path.strip()))
            action_taken = True

        # 3. Execute Reads
        for path in patterns['READ'].findall(response_text):
            feedback.append(self.handle_read(path.strip()))
            action_taken = True

        # 4. Execute Shell Commands
        for cmd in patterns['RUN'].findall(response_text):
            feedback.append(self.handle_run(cmd.strip()))
            action_taken = True

        return feedback, action_taken

    def run(self):
        print(f"🚀 VibeCLI Initialized (Model: {self.model_name})")
        print("📂 Indexing project...")
        
        # 1. Initial Context Load
        initial_context = self.get_project_context()
        try:
            self.chat.send_message(f"SYSTEM: Here is the current codebase context.\n{initial_context}")
        except Exception as e:
            print(f"❌ Connection Error: {e}")
            sys.exit(1)
        
        print("✅ Ready! Ask me to write code, install packages, or debug.")
        print("-" * 50)

        # 2. The Agentic Loop
        while True:
            try:
                user_prompt = input("\n(You) > ")
                if user_prompt.lower() in ['exit', 'quit']: break
                if not user_prompt.strip(): continue
                
                print("✨ Gemini: Thinking...")
                response = self.chat.send_message(user_prompt)
                
                # Check for blocks
                if response.candidates[0].finish_reason != 1:
                    print("⚠️ AI stopped generating (Safety/recitation check). Try a different prompt.")
                    continue

                # Show natural text (remove the blocks visually)
                clean_text = re.sub(r">>>.*?<<<", "", response.text, flags=re.DOTALL)
                if clean_text.strip():
                    print(f"🤖 Gemini: {clean_text.strip()}")

                # Execute Actions
                feedback, action_taken = self.process_ai_response(response.text)
                
                # 3. The "Antigravity" Feedback Step
                # If we took action, we MUST tell the AI what happened so it can continue.
                if action_taken:
                    feedback_msg = "SYSTEM: Actions executed. Results:\n" + "\n".join(feedback)
                    # We send the result back silently to update the AI's state
                    # Sometimes the AI might want to follow up immediately
                    # For now, we just update the history.
                    self.chat.history.append({"role": "user", "parts": [feedback_msg]})
                    print(f"🔄 Feedback sent to AI ({len(feedback)} actions processed)")

            except KeyboardInterrupt:
                print("\n👋 Exiting...")
                break
            except Exception as e:
                print(f"\n❌ Loop Error: {e}")

if __name__ == "__main__":
    app = VibeTerminal()
    app.run()