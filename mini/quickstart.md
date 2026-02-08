# Quick Start Guide - VibeCLI

## 5-Minute Setup

### Step 1: Install Dependencies
```bash
pip install openai python-dotenv
```

### Step 2: Create .env File
Create a file named `.env` in the same folder as the scripts:
```
OPENROUTER_API_KEY=sk-or-v1-your-actual-key-here
```

Get your key from: https://openrouter.ai/

### Step 3: Run VibeCLI
```bash
# In your project directory
python vibe_integrated.py

# Or specify a path
python vibe_integrated.py /path/to/your/project
```

## First Commands to Try

```
(You) > Show me the project structure

(You) > Read the package.json file

(You) > Create a new file called test.js with a hello world function

(You) > Install lodash

(You) > Run npm test
```

## File Structure
Make sure you have:
```
your-folder/
├── vibe_integrated.py
├── file_reader.py
└── .env
```

## Common Issues

**"Missing dependencies"**
→ Run: `pip install openai python-dotenv`

**"Missing file_reader module"**
→ Download both `vibe_integrated.py` AND `file_reader.py` to the same folder

**"API key not found"**
→ Create `.env` file with: `OPENROUTER_API_KEY=your-key-here`

## What Happens When You Start?

1. ✅ VibeCLI scans your project
2. ✅ Loads all source code into AI context
3. ✅ Starts interactive session
4. ✅ You give natural language commands
5. ✅ AI suggests changes, you approve them

## Safety Features

- ✅ Shows diffs before writing files
- ✅ Requires confirmation for all changes
- ✅ Auto-backups files to `.vibe/backups/`
- ✅ Warns about dangerous commands
- ✅ Detects package manager automatically

## Pro Tips

1. **Always use Git**: Commit before big changes
2. **Review diffs**: Read what will change before approving
3. **Start small**: Test with simple tasks first
4. **Be specific**: Clear instructions = better results
5. **Skip context for speed**: Use `--no-context` for large projects

---

That's it! You're ready to code with AI. 🚀