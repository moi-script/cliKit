import argparse
from pathlib import Path
from file_reader import scrape_contents

def main():
    parser = argparse.ArgumentParser(
        description="Scrape project structure and contents"
    )
    parser.add_argument("path", help="Target directory")
    args = parser.parse_args()

    result = scrape_contents(Path(args.path))
    print(result)

if __name__ == "__main__":
    main()
