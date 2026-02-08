import argparse
from pathlib import Path
from file_reader import scrape_contents

def main():
    parser = argparse.ArgumentParser(
        description="Scrape project structure and contents and save to a file"
    )
    parser.add_argument("path", help="Target directory")
    parser.add_argument(
        "-o", "--output", 
        default="project_summary.md", 
        help="Output file name (default: project_summary.md)"
    )
    
    args = parser.parse_args()
    target_path = Path(args.path)

    # Scrape the contents
    result = scrape_contents(target_path)

    # Write the result to the specified file
    try:
        output_file = Path(args.output)
        output_file.write_text(result, encoding="utf-8")
        print(f"Successfully saved scrape results to: {output_file.absolute()}")
    except Exception as e:
        print(f"Error saving file: {e}")

if __name__ == "__main__":
    main()