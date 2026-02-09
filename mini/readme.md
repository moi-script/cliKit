# VibeCLI v3.5 - Integrated Context AI

An elite AI-powered code assistant that loads your entire codebase into context and executes file operations, shell commands, and package management through natural language.

## 🚀 Features

- **Full Codebase Context**: Automatically scans and loads your entire project into the AI's context
- **Smart File Operations**: Read, Write, Delete files with diff preview and automatic backups
- **Shell Command Execution**: Run any shell command with safety checks
- **Package Management**: Auto-detects npm/yarn/pnpm/bun and installs dependencies
- **Shadcn/UI Integration**: Quick component installation for React projects
- **Streaming Responses**: Real-time AI output
- **Automatic Backups**: All modified files are backed up to `.vibe/backups/`
- **Nested Directory Support**: Recursively scans all subdirectories (excluding node_modules, .git, etc.)
- **Interactive Command Handling**: Auto-detects and fixes commands that require user input (Vite, Next.js, etc.)
- **Project Scaffolding**: CREATE command for bootstrapping new projects with proper templates

## 📋 Prerequisites

- Python 3.8+
- OpenRouter API Key ([Get one here](https://openrouter.ai/))

## 🔧 Installation

### 1. Clone or Download Files

You need two files:
- `vibe_integrated.py` - Main application
- `file_reader.py` - Repository scanner module

### 2. Install Dependencies

```bash
pip install openai python-dotenv
```

### 3. Configure API Key

Create a `.env` file in the same directory as the scripts:

```bash
OPENROUTER_API_KEY=your_openrouter_api_key_here
```

**Important**: Never commit your `.env` file to version control!

## 📖 Usage

### Basic Usage

Navigate to your project directory and run:

```bash
python vibe_integrated.py
```

This will:
1. Scan the current directory
2. Load all code files into context
3. Start an interactive chat session

### Specify a Different Directory

```bash
python vibe_integrated.py /path/to/your/project
```

### Skip Initial Context Loading

For large projects or quick commands:

```bash
python vibe_integrated.py --no-context
```

## 💬 Example Commands

Once running, you can interact naturally:

### File Operations

```
(You) > Create a new React component called Button in src/components/Button.tsx
(You) > Add error handling to the login function in auth.js
(You) > Delete the old test file tests/legacy.test.js
(You) > Show me the contents of package.json
```

### Package Management

```
(You) > Install react-query
(You) > Add tailwindcss to the project
(You) > Install shadcn button component
```

### Project Scaffolding

```
(You) > Create a new React TypeScript project called my-app
(You) > Bootstrap a Next.js app with Tailwind
(You) > Set up a new Astro blog project
```

VibeCLI will use the `CREATE` command with proper templates:
```
>>> CREATE vite-react-ts my-app <<<
>>> CREATE next my-store <<<
>>> CREATE astro-blog my-blog <<<
```

### Shell Commands

```
(You) > Run the test suite
(You) > Build the project
(You) > Start the development server
```

### Complex Tasks

```
(You) > Refactor the authentication system to use JWT tokens instead of sessions
(You) > Add TypeScript to this JavaScript project
(You) > Create a new API endpoint for user registration with validation
```

## 🎯 How It Works

### 1. Context Loading
When you start VibeCLI, it uses `file_reader.py` to:
- Recursively scan your project directory
- Skip binary files, dependencies, and system folders
- Concatenate all source code into a single string
- Inject this context into the AI's system prompt

### 2. AI Commands
The AI uses special command blocks to interact with your system:

```
>>> WRITE src/app.js
console.log("Hello World");
<<<

>>> RUN npm test <<<

>>> DELETE old-file.js <<<
```

### 3. Safety Features
- **Diff Preview**: Shows exactly what will change before writing
- **User Confirmation**: You approve all file modifications and shell commands
- **Automatic Backups**: Original files saved to `.vibe/backups/` with timestamps
- **Dangerous Command Detection**: Warns about destructive operations (rm, format, etc.)

## 📁 Project Structure

```
your-project/
├── vibe_integrated.py     # Main VibeCLI application
├── file_reader.py         # Repository scanner module
├── .env                   # API keys (create this)
└── .vibe/                 # Created automatically
    └── backups/           # File backups with timestamps
```

## 🔍 What Gets Scanned?

### ✅ Included
- Source code files (.js, .ts, .py, .jsx, .tsx, etc.)
- Configuration files (.json, .yaml, .toml, etc.)
- Documentation (.md, .txt)
- Stylesheets (.css, .scss)

### ❌ Excluded
- Dependencies (`node_modules`, `__pycache__`, etc.)
- Version control (`.git`)
- Build outputs (`dist`, `build`, `.next`)
- Binary files (images, fonts, executables)
- Lock files (`package-lock.json`, `yarn.lock`)
- System files (`.DS_Store`, `Thumbs.db`)

## ⚙️ Configuration

### Change AI Model

Edit `MODEL_NAME` in `vibe_integrated.py`:

```python
MODEL_NAME = "google/gemini-2.5-flash-lite:nitro"  # Default
# MODEL_NAME = "anthropic/claude-3.5-sonnet"
# MODEL_NAME = "openai/gpt-4"
```

See [OpenRouter Models](https://openrouter.ai/models) for options.

### Adjust Context History

```python
MAX_HISTORY_TURNS = 15  # Number of conversation turns to keep
```

### Customize File Skipping

Edit `file_reader.py`:

```python
SKIPPED_NAMES = {
    'node_modules', '__pycache__', '.git',
    # Add more here
}

SKIPPED_EXTENSIONS = {
    '.png', '.jpg', '.pdf',
    # Add more here
}
```

## 🛡️ Security Best Practices

1. **Never share your API key**: Keep `.env` in `.gitignore`
2. **Review diffs carefully**: Always check what will be changed before approving
3. **Use version control**: Commit your code before major changes
4. **Backup important files**: VibeCLI creates backups, but Git is your safety net
5. **Be cautious with RUN commands**: Review shell commands before execution

## 🐛 Troubleshooting

### "Missing file_reader module"
Make sure `file_reader.py` is in the same directory as `vibe_integrated.py`.

### "OPENROUTER_API_KEY not found"
Create a `.env` file with your API key in the same directory.

### Context too large
For huge projects (>100k lines), use `--no-context` and manually READ files as needed.

### Commands not executing
Ensure you're using the exact command format from the examples above.

### Interactive command hangs
If a command gets stuck (like `npm create vite`), press Ctrl+C and use the CREATE command or add proper flags:
```
(You) > Create a Vite React app with npm create vite@latest my-app -- --template react-ts
```

See `INTERACTIVE_COMMANDS.md` for detailed solutions.

## 📊 Standalone Scraper Usage

You can also use `file_reader.py` independently to dump your codebase:

```bash
python file_reader.py /path/to/project -o output.txt
```

This creates a text file with all your code for manual inspection or other tools.

## 🎓 Tips & Tricks

1. **Be Specific**: "Add error handling to the login function" works better than "improve the code"
2. **Start Small**: Test with simple tasks before complex refactoring
3. **Use Git**: Commit before big changes so you can easily revert
4. **Review Everything**: Always read the diff before approving writes
5. **Iterative Development**: Break large tasks into smaller steps

## 📝 Example Session

```
🚀 VibeCLI Integrated | google/gemini-2.5-flash-lite:nitro
📂 Root: /Users/dev/my-app
📦 Package Manager: npm
--------------------------------------------------
🔍 Scanning repo: /Users/dev/my-app...
✅ Context Loaded. (45,832 characters)

(You) > Create a new utility function to format dates in src/utils/date.ts

🤖 AI: I'll create a date formatting utility for you.

📝 [REQUEST] WRITE: src/utils/date.ts

--- DIFF CHECK ---
[Shows the new file content]
------------------

>> Apply changes? (y/n): y
✅ Successfully wrote src/utils/date.ts

🤖 AI: I've created src/utils/date.ts with a formatDate function that handles common date formatting patterns.

(You) > Now use this function in the dashboard component

🤖 AI: I'll update the dashboard to use the new date utility.

[Process continues...]
```

## 🤝 Contributing

Feel free to modify and extend VibeCLI for your needs. Some ideas:
- Add support for more package managers
- Integrate with other AI providers
- Add custom command types
- Improve context management for huge codebases

## 📄 License

Free to use and modify. No warranties provided.

## 🙏 Credits

Built with:
- [OpenRouter](https://openrouter.ai/) - Unified AI API
- [OpenAI Python SDK](https://github.com/openai/openai-python) - API client
- Google Gemini 2.5 Flash Lite (default model)

---

**Happy Coding!** 🎉