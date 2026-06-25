# JSONL Chat Viewer

A Python TUI for reading SillyTavern JSONL chat exports. Built with [Textual](https://textual.textualize.io/).

These chat files can get novel-length, so the viewer is designed around efficient scrolling and quick navigation.

## Features

- Color-coded speakers (green for user, cyan for characters)
- Collapsible LLM reasoning blocks
- Swipe variant support (SillyTavern's regeneration feature stores multiple responses per message)
- Message headers showing model name, token count, and generation time
- Sticky title bar with progress indicator
- Sticky message header when scrolled into a long message
- Case-insensitive text search with red highlights
- Goto-by-ID dialog for jumping to specific messages
- Mouse click to select messages, mouse scroll support
- Transparent GPG decryption (opens `.jsonl.gpg` or ASCII-armored files, prompts for passphrase)

## Usage

```
uv sync
uv run python viewer.py path/to/chat.jsonl
```

GPG-encrypted files are detected automatically (binary or ASCII-armored). Requires `gpg` on PATH:

```
uv run python viewer.py path/to/chat.jsonl.gpg
```

Requires Python 3.10+.

## Keybindings

| Key | Action |
|-----|--------|
| `j` / `k` / arrows | Scroll up/down |
| `PgUp` / `PgDn` / `Space` | Page scroll |
| `n` | Next message |
| `N` / `p` | Previous message |
| `h` / `l` / left/right arrows | Cycle swipe variants |
| `r` | Toggle reasoning |
| `/` | Search (then `n`/`N` to navigate matches, `Esc` to exit) |
| `g` / `G` | Go to message by ID |
| `?` | Help overlay |
| `q` / `Esc` | Quit |

## Running Tests

```
uv sync
uv run pytest
```

Tests use Textual's async pilot framework to drive the app and assert on widget state.
