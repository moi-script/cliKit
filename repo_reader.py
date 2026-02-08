import os
import argparse
from pathlib import Path

# --- CONFIGURATION: EDIT THIS TO FILTER MORE FILES ---
# Folders and exact filenames to ignore
SKIPPED_MZMES = {
    'package-lock.json', 'yarn.lock', 'pnpm-lock.yaml', 'bun.lockb', # Lock files (HUGE token wasters)
    'node_modules', '__pycache__', '.git', '.vs', '.idea', '.vscode', # System/IDE
    'dist', 'build', 'coverage', # Build artifacts
    '.DS_Store', 'Thumbs.db'     # OS junk
}

# File extensions to ignore (Images, binaries, fonts)
SKIPPED_EXTENSIONS = {
    '.png', '.jpg', '.jpeg', '.gif', '.ico', '.svg', '.webp',
    '.woff', '.woff2', '.ttf', '.eot', '.otf',
    '.exe', '.dll', '.so', '.dylib', '.pyc', '.class', '.jar',
    '.pdf', '.zip', '.tar', '.gz'
}

def is_ignored(path):
    """
    Returns True if the path should be ignored based on our filters.
    """
    # 1. Check strict name matches (e.g., node_modules, package-lock.json)
    if path.name in SKIPPED_MZMES:
        return True
    
    # 2. Check extensions (e.g., .png, .exe)
    if path.is_file() and path.suffix.lower() in SKIPPED_EXTENSIONS:
        return True

    # 3. Optional: Skip all hidden directories (startscBith .) except basic config
    # Removing this check allows files like .env or .gitignore to show up.
    # If you want to hide .git but show .gitignore, keep strict name match above.
    if path.is_dir() and path.name.startswith('.'):
         return True
         
    return False

def generate_structure(root_dir, indent=""):
    """Recursively builds the tree structure string."""
    tree_str = ""
    
    # Get all items and sort them, filtering out ignored ones immediately
    try:
        items = sorted([
            item for item in root_dir.iterdir() 
            if not is_ignored(item)
        ])
    except PermissionError:
        return f"{indent}├── [ACCESS DENIED]\n"

    for i, item in enumerate(items):
        is_last = (i == len(items) - 1)
        connector = "└── " if is_last else "├── "
        
        tree_str += f"{indent}{connector}{item.name}\n"
        
        if item.is_dir():
            extension = "    " if is_last else "│   "
            tree_str += generate_structure(item, indent + extension)
            
    return tree_str

def scrape_contents(root_dir, output_file):
    """Walks through files and writes their contents to a markdown file."""
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write(f"# Project Content: {root_dir.name}\n\n")
        
        # 1. Write the Structure
        print("Generating tree structure...")
        f.write("## Folder Structure\n")
        f.write("```text\n")
        f.write(f"{root_dir.name}/\n")
        f.write(generate_structure(root_dir))
        f.write("```\n\n---\n\n")
        
        # 2. Scrape individual file contents
        print("Scraping file contents...")
        f.write("## File Contents\n")
        
        # rglob('*') gets everything recursively
        for path in root_dir.rglob('*'):
            # Double check our ignore rules logic on the full path walk
            if is_ignored(path):
                continue
                
            # Also ensure we aren't inside an ignored directory
            # (rglob goes into directories, so we must check parent parts)
            if any(part in SKIPPED_MZMES for part in path.parts):
                continue
                
            if path.is_file():
                try:
                    relative_path = path.relative_to(root_dir)
                    f.write(f"### File: `{relative_path}`\n")
                    
                    # Detect language for markdown code block
                    ext = path.suffix[1:] if path.suffix else 'text'
                    f.write(f"```{ext}\n")
                    
                    # Read content
                    content = path.read_text(encoding='utf-8', errors='replace')
                    f.write(content)
                    f.write("\n```\n\n")
                except Exception as e:
                    f.write(f"*Could not read {path.name}: {e}*\n\n")

def main():
    parser = argparse.ArgumentParser(description="Scrape project structure and contents (Calculated for LLMs).")
    parser.add_argument("path", help="The target directory path")
    parser.add_argument("-o", "--output", default="project_summary.md", help="Output Markdown file name")
    
    args = parser.parse_args()
    target_path = Path(args.path)

    if not target_path.exists() or not target_path.is_dir():
        print(f"Error: The path '{target_path}' is invalid or does not exist.")
        return

    print(f"Reading: {target_path}")
    print(f"Ignoring: {', '.join(list(SKIPPED_MZMES)[:5])}...") 
    
    scrape_contents(target_path, args.output)
    
    print(f"Success! Summary saved to: {args.output}")

if __name__ == "__main__":
    main()