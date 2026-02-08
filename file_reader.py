from pathlib import Path

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


def is_ignored(path: Path) -> bool:
    if path.name in SKIPPED_NAMES:
        return True
    if path.is_file() and path.suffix.lower() in SKIPPED_EXTENSIONS:
        return True
    if path.is_dir() and path.name.startswith('.'):
        return True
    return False


def generate_structure(root_dir: Path, indent: str = "") -> str:
    tree = ""
    try:
        items = sorted(p for p in root_dir.iterdir() if not is_ignored(p))
    except PermissionError:
        return f"{indent}├── [ACCESS DENIED]\n"

    for i, item in enumerate(items):
        last = i == len(items) - 1
        connector = "└── " if last else "├── "
        tree += f"{indent}{connector}{item.name}\n"

        if item.is_dir():
            extension = "    " if last else "│   "
            tree += generate_structure(item, indent + extension)

    return tree


def scrape_contents(root_dir: Path) -> str:
    if not root_dir.exists() or not root_dir.is_dir():
        raise ValueError(f"Invalid directory: {root_dir}")

    output = ""
    output += f"# Project Content: {root_dir.name}\n\n"
    output += "## Folder Structure\n"
    output += "```\n"
    output += f"{root_dir.name}/\n"
    output += generate_structure(root_dir)
    output += "```\n\n---\n\n"
    output += "## File Contents\n\n"

    for path in root_dir.rglob('*'):
        if is_ignored(path) or not path.is_file():
            continue

        ext = path.suffix[1:] if path.suffix else "text"
        content = path.read_text(encoding="utf-8", errors="replace")

        output += f"### File: `{path.relative_to(root_dir)}`\n"
        output += f"```{ext}\n{content}\n```\n\n"

    return output
