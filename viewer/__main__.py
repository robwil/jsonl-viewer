"""Entry point for `python -m viewer`."""

import argparse
import curses
import os
import sys

from .app import main
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

    if "TERM" not in os.environ:
        os.environ["TERM"] = "xterm-256color"

    print(f"Loaded {len(chat.messages)} messages. Launching viewer...")
    try:
        curses.wrapper(lambda stdscr: main(stdscr, chat))
    except curses.error:
        # Fallback if terminfo for the current TERM isn't available
        os.environ["TERM"] = "xterm"
        curses.wrapper(lambda stdscr: main(stdscr, chat))


if __name__ == "__main__":
    main_cli()
