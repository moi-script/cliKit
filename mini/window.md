# Windows-Specific Guide for VibeCLI

## The Windows Challenge

Many Node.js CLI tools use interactive prompts that don't work well on Windows with non-interactive execution. VibeCLI solves this with **platform-specific handling**.

## How VibeCLI Handles Windows

### Automatic Detection
VibeCLI automatically detects if you're on Windows and adjusts its behavior:

```python
# Automatically detects platform
IS_WINDOWS = sys.platform.startswith('win')
```

### Input Redirection Strategy

For interactive commands (like Vite, Next.js), VibeCLI uses **temporary file input redirection**:

```python
# Creates temp file with newlines
temp_file = create_input_file('\n' * 10)

# Redirects input from file
npm create vite@latest frontend -- --template react-ts < temp_file
```

This simulates pressing Enter multiple times to skip prompts.

## Tested Commands on Windows

### ✅ Working Commands

```bash
# Vite (all variants)
npm create vite@latest my-app -- --template react-ts
npm create vite@latest my-app -- --template vue
npm create vite@latest my-app -- --template svelte-ts

# Next.js
npx create-next-app@latest my-app --yes --typescript --tailwind

# Package initialization
npm init -y
yarn init -y
pnpm init

# Shadcn UI
npx shadcn@latest add button -y
npx shadcn@latest init -y

# Package installation
npm install <package>
pnpm add <package>
```

### ⚠️ Commands That May Still Prompt

Some tools are stubborn on Windows:

```bash
# If these still prompt, use the CREATE command instead:
(You) > Create a Vite React app
# VibeCLI will handle it properly
```

## Windows-Specific Tips

### 1. Use PowerShell or CMD
VibeCLI works in both PowerShell and CMD. Git Bash may have issues.

```bash
# ✅ Good
python vibe_integrated.py

# ⚠️ May have issues in Git Bash
```

### 2. Install Node.js Properly
Make sure Node.js is in your PATH:

```powershell
# Check Node is accessible
node --version
npm --version
```

### 3. Run as Administrator (If Needed)
Some commands may need elevated privileges:

```powershell
# Right-click PowerShell → "Run as Administrator"
python vibe_integrated.py
```

### 4. Use Forward Slashes in Paths
Even on Windows, use forward slashes in file paths:

```
# ✅ Good
src/components/Button.tsx

# ❌ Avoid
src\components\Button.tsx
```

## Troubleshooting Windows Issues

### Issue: "npm not recognized"

**Solution:** Add Node.js to PATH

```powershell
# Check current PATH
$env:PATH

# Add Node.js (replace with your path)
$env:PATH += ";C:\Program Files\nodejs\"
```

### Issue: "'yes' is not recognized"

**Solution:** This is expected! VibeCLI auto-fixed this. If you see this error, it means the auto-fix didn't work. Report the command that failed.

### Issue: Commands still hanging

**Solution 1:** Use the CREATE command instead
```
(You) > Create a new Vite React TypeScript project called my-app
```

**Solution 2:** Set environment variable
```powershell
$env:CI = "true"
npm create vite@latest my-app -- --template react-ts
```

**Solution 3:** Use manual flags
```
(You) > Run npm create vite@latest my-app -- --template react-ts --yes
```

### Issue: Permission denied errors

**Solution:** Run PowerShell as Administrator or adjust execution policy

```powershell
# Check current policy
Get-ExecutionPolicy

# Allow scripts (run as Admin)
Set-ExecutionPolicy RemoteSigned -Scope CurrentUser
```

### Issue: Long path errors

**Solution:** Enable long paths in Windows

```powershell
# Run as Admin
New-ItemProperty -Path "HKLM:\SYSTEM\CurrentControlSet\Control\FileSystem" `
  -Name "LongPathsEnabled" -Value 1 -PropertyType DWORD -Force
```

## Windows-Specific CREATE Commands

All these work perfectly on Windows:

```
(You) > Create a Vite React TypeScript app called my-app
>>> CREATE vite-react-ts my-app <<<

(You) > Set up a Next.js project
>>> CREATE next my-store <<<

(You) > Make an Astro blog
>>> CREATE astro-blog my-blog <<<
```

VibeCLI automatically uses the right Windows-compatible command.

## Differences from Unix/Mac

| Feature | Unix/Mac | Windows |
|---------|----------|---------|
| Auto-answer prompts | `yes '' \| command` | `command < temp_file` |
| Path separators | `/` (native) | `/` or `\` (both work) |
| Shell | bash/zsh | cmd/PowerShell |
| Line endings | LF (`\n`) | CRLF (`\r\n`) |

VibeCLI handles all these differences automatically!

## Best Practices for Windows

1. **Use the CREATE command** for new projects - it's most reliable
2. **Always add `--yes`/`-y` flags** when manually using RUN
3. **Use forward slashes** in file paths
4. **Run in PowerShell** (not Git Bash)
5. **Keep Node.js updated** - newer versions have better Windows support
6. **Use Windows Terminal** - better than legacy CMD

## Example Session on Windows

```powershell
PS C:\Users\Dev\Projects> python vibe_integrated.py

🚀 VibeCLI Integrated | google/gemini-2.5-flash-lite:nitro
📂 Root: C:\Users\Dev\Projects
📦 Package Manager: npm
--------------------------------------------------
🔍 Scanning repo: C:\Users\Dev\Projects...
✅ Context Loaded. (1,234 characters)

(You) > Create a new Vite React TypeScript app in the frontend folder

🤖 AI: I'll create a Vite + React + TypeScript project in the frontend folder.

🏗️ [REQUEST] CREATE: vite-react-ts project 'frontend'
📦 Command: echo. | npm create vite@latest frontend -- --template react-ts

>> Execute? (y/n): y

📟 Running command (this may take a moment)...
--------------------------------------------------
[Windows uses input redirection automatically]

Output:
Scaffolding project in C:\Users\Dev\Projects\frontend...
Done. Now run:
  cd frontend
  npm install
  npm run dev

--------------------------------------------------
✅ Command completed successfully

🔄 Getting AI follow-up...
🤖 AI: Successfully created the frontend folder with Vite + React + TypeScript!
```

## Need Help?

If you encounter Windows-specific issues:

1. Check this guide first
2. Try the CREATE command instead of manual RUN
3. Ensure Node.js is properly installed
4. Run PowerShell as Administrator
5. Update to latest Node.js LTS

---

**Windows is fully supported!** 🎉