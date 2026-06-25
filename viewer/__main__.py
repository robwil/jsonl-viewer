"""Entry point for `python -m viewer`."""

import argparse
import sys

from .parser import load_chat


def main_cli():
    parser = argparse.ArgumentParser(description="SillyTavern JSONL chat viewer")
    parser.add_argument("file", help="Path to .jsonl chat export")
    args = parser.parse_args()

    try:
        chat = load_chat(args.file)
    except Exception as e:
        print(f"Error loading {args.file}: {e}", file=sys.stderr)
        sys.exit(1)

    if not chat.messages:
        print("No messages found.", file=sys.stderr)
        sys.exit(1)

    print(f"Loaded {len(chat.messages)} messages. Launching viewer...")

    from .app import main
    main(chat)


if __name__ == "__main__":
    main_cli()
