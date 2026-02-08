import argparse
import os
from pathlib import Path

# --- Configuration ---
SKIPPED_NAMES = {
    'package-lock.json', 'yarn.lock', 'pnpm-lock.yaml', 'bun.lockb',
    'node_modules', '__pycache__', '.git', '.vs', '.idea', '.vscode',
    'dist', 'build', 'coverage',
    '.DS_Store', 'Thumbs.db'
}

SKIPPED_EXTENSIONS = {
    '.png', '.jpg', '.jpeg', '.gif', '.ico', '.svg', '.webp',
    '.woff', '.woff2', '.ttf', '.eot', '.otf',
    '.exe', '.dll', '.so', '.dylib', '.pyc', '.class', '.jar',
    '.pdf', '.zip', '.tar', '.gz'
}

def is_skipped(path: Path) -> bool:
    """Check if a file should be skipped based on name or extension."""
    if path.name in SKIPPED_NAMES:
        return True
    if path.suffix.lower() in SKIPPED_EXTENSIONS:
        return True
    return False

def scrape_contents(root_path: Path) -> str:
    """Scrapes file contents into a single formatted string."""
    output_lines = []
    
    # os.walk is used here because it allows us to modify 'dirs' in-place
    # to prevent recursing into skipped directories (like node_modules).
    for root, dirs, files in os.walk(root_path):
        # 1. Filter directories to prevent recursion into skipped folders
        # We modify dirs[:] in place to prune the walk
        dirs[:] = [d for d in dirs if d not in SKIPPED_NAMES]
        
        for file in files:
            file_path = Path(root) / file
            
            # 2. Skip specific files or extensions
            if is_skipped(file_path):
                continue
                
            # 3. Read and format content
            try:
                # Calculate relative path for cleaner output
                rel_path = file_path.relative_to(root_path)
                
                output_lines.append(f"\n{'='*50}")
                output_lines.append(f"FILE: {rel_path}")
                output_lines.append(f"{'='*50}\n")
                
                # Force utf-8 and ignore errors (in case of unexpected binary files)
                content = file_path.read_text(encoding='utf-8', errors='ignore')
                output_lines.append(content)
                output_lines.append("\n")
                
            except Exception as e:
                output_lines.append(f"[Error reading file: {e}]")

    return "\n".join(output_lines)

def main():
    parser = argparse.ArgumentParser(
        description="Scrape project structure and contents excluding binary/system files."
    )
    parser.add_argument("path", help="Target directory to scrape")
    parser.add_argument(
        "-o", "--output", 
        default="project_dump.txt", 
        help="Output file name (default: project_dump.txt)"
    )

    args = parser.parse_args()
    target_path = Path(args.path).resolve()

    if not target_path.exists():
        print(f"Error: Target path '{target_path}' does not exist.")
        return

    print(f"Scraping: {target_path}")
    print("Ignoring binaries and system folders...")

    result = scrape_contents(target_path)
    
    # Save to file
    try:
        output_file = Path(args.output)
        output_file.write_text(result, encoding="utf-8")
        print(f"Done! Saved to: {output_file.absolute()}")
    except Exception as e:
        print(f"Error writing output: {e}")

if __name__ == "__main__":
    main()