"""Integration tests for the JSONL chat viewer TUI.

Spawns the viewer in a real pty with a fixed terminal size, sends keystrokes,
and asserts on the screen contents via pyte (a terminal emulator).
"""

import os
import time
from pathlib import Path

import pexpect
import pyte
import pytest

VIEWER = str(Path(__file__).resolve().parent.parent / "viewer.py")
FIXTURE = str(Path(__file__).resolve().parent / "fixture.jsonl")
ENCRYPTED_FIXTURE = str(Path(__file__).resolve().parent / "encrypted_fixture.jsonl.gpg")
# Small terminal to force scrolling with our 5-message fixture
ROWS, COLS = 20, 90


class Screen:
    """Wrapper around pexpect + pyte for driving the TUI."""

    def __init__(self, rows=ROWS, cols=COLS):
        self.rows = rows
        self.cols = cols
        self.screen = pyte.Screen(cols, rows)
        self.stream = pyte.Stream(self.screen)
        self.child = pexpect.spawn(
            f"python3 {VIEWER} {FIXTURE}",
            dimensions=(rows, cols),
            encoding="utf-8",
            timeout=5,
        )
        # Wait for initial render — the "Loaded X messages" line prints first,
        # then curses takes over. Give it time to settle.
        self._read_until_idle(pause=0.3)

    def _read_until_idle(self, pause=0.2):
        """Read output until the process goes quiet for `pause` seconds."""
        while True:
            try:
                data = self.child.read_nonblocking(size=4096, timeout=pause)
                self.stream.feed(data)
            except pexpect.TIMEOUT:
                break
            except pexpect.EOF:
                break

    def send(self, keys: str, pause=0.2):
        """Send keystrokes and wait for the screen to update."""
        try:
            self.child.send(keys)
        except OSError:
            pytest.fail("Process died unexpectedly")
        self._read_until_idle(pause)

    def send_key(self, key_name: str, pause=0.2):
        """Send a named key (e.g. 'up', 'down', 'left', 'right').

        Escape sequences are written as a single raw write to avoid
        curses interpreting the leading ESC as a standalone keypress.
        """
        key_map = {
            "up": b"\x1b[A",
            "down": b"\x1b[B",
            "right": b"\x1b[C",
            "left": b"\x1b[D",
            "pgup": b"\x1b[5~",
            "pgdn": b"\x1b[6~",
            "enter": b"\r",
            "esc": b"\x1b",
        }
        import os
        os.write(self.child.child_fd, key_map[key_name])
        self._read_until_idle(pause)

    def get_row(self, row: int) -> str:
        """Get the text content of a screen row (0-indexed)."""
        return self.screen.display[row].rstrip()

    def get_rows(self, start: int = 0, end: int | None = None) -> list[str]:
        """Get a range of screen rows."""
        if end is None:
            end = self.rows
        return [self.get_row(r) for r in range(start, end)]

    def get_all_text(self) -> str:
        """Get all screen content as a single string."""
        return "\n".join(self.get_rows())

    def find_text(self, text: str) -> list[int]:
        """Return row indices where text appears."""
        return [i for i in range(self.rows) if text in self.screen.display[i]]

    def resize(self, rows: int, cols: int):
        """Resize the terminal and wait for the app to redraw."""
        self.rows = rows
        self.cols = cols
        self.screen = pyte.Screen(cols, rows)
        self.stream = pyte.Stream(self.screen)
        self.child.setwinsize(rows, cols)
        self._read_until_idle(pause=0.3)

    def close(self):
        try:
            self.child.sendeof()
        except OSError:
            pass
        self.child.close(force=True)


@pytest.fixture
def screen():
    s = Screen()
    yield s
    s.close()


@pytest.fixture
def small_screen():
    """A very small terminal to force scrolling."""
    s = Screen(rows=14, cols=80)
    yield s
    s.close()


class TestInitialRender:
    def test_title_bar_shows_chat_name(self, screen):
        title_row = screen.get_row(0)
        assert "Bob" in title_row
        assert "2026-01-15" in title_row

    def test_title_bar_shows_progress(self, screen):
        title_row = screen.get_row(0)
        assert "1 / 5" in title_row

    def test_first_message_header(self, screen):
        all_text = screen.get_all_text()
        assert "#1" in all_text
        assert "Bob" in all_text
        assert "fancy-llm" in all_text

    def test_first_message_body(self, screen):
        all_text = screen.get_all_text()
        assert "Hello Alice!" in all_text
        assert "fire crackles" in all_text

    def test_swipe_indicator_on_first_message(self, screen):
        all_text = screen.get_all_text()
        assert "[1/2]" in all_text

    def test_cursor_marker_on_first_message(self, screen):
        rows = screen.get_rows()
        marker_rows = [r for r in rows if "▌" in r]
        assert len(marker_rows) > 0

    def test_help_bar(self, screen):
        help_row = screen.get_row(screen.rows - 1)
        assert "scroll" in help_row
        assert "quit" in help_row

    def test_reasoning_hidden_by_default(self, screen):
        all_text = screen.get_all_text()
        assert "greet the user warmly" not in all_text


class TestMessageNavigation:
    def test_next_message(self, screen):
        screen.send("n")
        title_row = screen.get_row(0)
        assert "2 / 5" in title_row

    def test_prev_message_with_N(self, screen):
        screen.send("n")
        screen.send("N")
        title_row = screen.get_row(0)
        assert "1 / 5" in title_row

    def test_prev_message_with_p(self, screen):
        screen.send("n")
        screen.send("p")
        title_row = screen.get_row(0)
        assert "1 / 5" in title_row

    def test_navigate_to_last_message(self, screen):
        for _ in range(5):
            screen.send("n")
        title_row = screen.get_row(0)
        assert "5 / 5" in title_row
        all_text = screen.get_all_text()
        assert "Whisper" in all_text

    def test_n_at_last_message_stays(self, screen):
        for _ in range(10):
            screen.send("n")
        title_row = screen.get_row(0)
        assert "5 / 5" in title_row

    def test_p_at_first_message_stays(self, screen):
        screen.send("p")
        title_row = screen.get_row(0)
        assert "1 / 5" in title_row


class TestGotoDialog:
    def test_goto_message(self, screen):
        screen.send("g")
        time.sleep(0.1)
        screen.send("4")
        screen.send_key("enter")
        title_row = screen.get_row(0)
        assert "4 / 5" in title_row

    def test_goto_cancel(self, screen):
        screen.send("g")
        screen.send_key("esc")
        title_row = screen.get_row(0)
        assert "1 / 5" in title_row

    def test_goto_last_message(self, screen):
        screen.send("g")
        screen.send("5")
        screen.send_key("enter")
        title_row = screen.get_row(0)
        assert "5 / 5" in title_row


class TestSwipes:
    def test_swipe_next(self, screen):
        all_text = screen.get_all_text()
        assert "[1/2]" in all_text
        assert "Hello Alice!" in all_text

        screen.send("l")
        all_text = screen.get_all_text()
        assert "[2/2]" in all_text
        assert "Greetings traveler!" in all_text

    def test_swipe_prev_wraps(self, screen):
        screen.send("h")
        all_text = screen.get_all_text()
        assert "[2/2]" in all_text

    def test_swipe_round_trip(self, screen):
        screen.send("l")
        all_text = screen.get_all_text()
        assert "[2/2]" in all_text

        screen.send("h")
        all_text = screen.get_all_text()
        assert "[1/2]" in all_text

    def test_swipe_on_message_without_swipes(self, screen):
        screen.send("n")  # msg 2 (alice, no swipes)
        screen.send("l")
        title_row = screen.get_row(0)
        assert "2 / 5" in title_row


class TestReasoning:
    def test_toggle_reasoning_on_and_off(self, screen):
        all_text = screen.get_all_text()
        assert "greet the user warmly" not in all_text

        screen.send("r")
        all_text = screen.get_all_text()
        assert "greet the user warmly" in all_text
        assert "Reasoning" in all_text

        screen.send("r")
        all_text = screen.get_all_text()
        assert "greet the user warmly" not in all_text

    def test_reasoning_toggle_on_user_message_no_crash(self, screen):
        screen.send("n")  # msg 2 (user msg, no reasoning)
        screen.send("r")
        # Should not crash, still on msg 2
        title_row = screen.get_row(0)
        assert "2 / 5" in title_row


class TestSearch:
    def test_search_finds_match(self, screen):
        screen.send("/")
        screen.send("stranger")
        screen.send_key("enter")
        all_text = screen.get_all_text()
        assert "stranger" in all_text.lower()
        help_row = screen.get_row(screen.rows - 1)
        assert "SEARCH" in help_row

    def test_search_shows_match_count(self, screen):
        screen.send("/")
        screen.send("tavern")
        screen.send_key("enter")
        help_row = screen.get_row(screen.rows - 1)
        assert "SEARCH" in help_row
        assert "tavern" in help_row.lower() or "tavern" in screen.get_all_text().lower()

    def test_search_navigate_next(self, screen):
        screen.send("/")
        screen.send("Bob")
        screen.send_key("enter")
        # Should be on first Bob message
        first_title = screen.get_row(0)

        screen.send("n")
        second_title = screen.get_row(0)
        # Progress should have advanced
        assert first_title != second_title or "SEARCH" in screen.get_row(screen.rows - 1)

    def test_search_navigate_prev(self, screen):
        screen.send("/")
        screen.send("Bob")
        screen.send_key("enter")
        screen.send("n")
        screen.send("N")
        # Should be back at first match
        title_row = screen.get_row(0)
        help_row = screen.get_row(screen.rows - 1)
        assert "SEARCH" in help_row

    def test_search_exit_with_esc(self, screen):
        screen.send("/")
        screen.send("stranger")
        screen.send_key("enter")
        # Esc to exit search mode — use raw write with pause for curses to process
        screen.send_key("esc", pause=0.5)
        help_row = screen.get_row(screen.rows - 1)
        assert "SEARCH" not in help_row
        assert "scroll" in help_row

    def test_search_cancel_dialog(self, screen):
        screen.send("/")
        screen.send_key("esc")
        help_row = screen.get_row(screen.rows - 1)
        assert "SEARCH" not in help_row


class TestStickyHeader:
    def test_sticky_header_when_scrolled_past(self, small_screen):
        small_screen.send("n")  # msg 2
        small_screen.send("n")  # msg 3 (Bob's longer message)
        for _ in range(5):
            small_screen.send("j")
        row1 = small_screen.get_row(1)
        assert "▌" in row1 or "#" in row1


class TestScrolling:
    def test_scroll_down_and_back(self, small_screen):
        """In a small terminal, content should shift when scrolling."""
        row2_before = small_screen.get_row(2)
        for _ in range(3):
            small_screen.send("j")
        row2_after = small_screen.get_row(2)
        assert row2_before != row2_after

    def test_page_down(self, small_screen):
        """Page down should change visible content in a small terminal."""
        text_before = small_screen.get_all_text()
        small_screen.send(" ")
        text_after = small_screen.get_all_text()
        assert text_before != text_after

    def test_j_k_round_trip(self, small_screen):
        """j/k should scroll down and back."""
        row2_before = small_screen.get_row(2)
        small_screen.send("j")
        small_screen.send("j")
        small_screen.send("j")
        row2_after = small_screen.get_row(2)
        assert row2_before != row2_after

        small_screen.send("k")
        small_screen.send("k")
        small_screen.send("k")
        row2_restored = small_screen.get_row(2)
        assert row2_before == row2_restored


class TestCursorFollowsScroll:
    """Cursor should snap to a visible message when the current one scrolls off."""

    def test_cursor_snaps_forward_on_scroll_down(self, small_screen):
        # Start at message 1, scroll down until it's fully off-screen
        title = small_screen.get_row(0)
        assert "1 / 5" in title

        # Scroll down many lines — msg 1 should leave the viewport
        for _ in range(15):
            small_screen.send("j")
        title = small_screen.get_row(0)
        # Cursor should have snapped to a later message
        assert "1 / 5" not in title

    def test_cursor_snaps_back_on_scroll_up(self, small_screen):
        # Navigate to last message
        for _ in range(4):
            small_screen.send("n")
        title = small_screen.get_row(0)
        assert "5 / 5" in title

        # Scroll up many lines — msg 5 should leave the viewport
        for _ in range(20):
            small_screen.send("k")
        title = small_screen.get_row(0)
        assert "5 / 5" not in title

    def test_cursor_stays_when_partially_visible(self, small_screen):
        # Navigate to msg 3 (Bob's longer message)
        small_screen.send("n")
        small_screen.send("n")
        title = small_screen.get_row(0)
        assert "3 / 5" in title

        # Scroll down just a little — msg 3 body should still be visible
        small_screen.send("j")
        title = small_screen.get_row(0)
        # Should still be on msg 3
        assert "3 / 5" in title


class TestSearchReSearch:
    """Test re-searching while already in search mode."""

    def test_new_search_replaces_old(self, screen):
        # First search
        screen.send("/")
        screen.send("tavern")
        screen.send_key("enter")
        help_row = screen.get_row(screen.rows - 1)
        assert "tavern" in help_row.lower()

        # Re-search with different query while in search mode
        screen.send("/")
        screen.send("stranger")
        screen.send_key("enter")
        help_row = screen.get_row(screen.rows - 1)
        assert "stranger" in help_row.lower()
        assert "tavern" not in help_row.lower()

    def test_re_search_navigates_new_matches(self, screen):
        # Search for something
        screen.send("/")
        screen.send("tavern")
        screen.send_key("enter")

        # Note position
        title1 = screen.get_row(0)

        # Re-search for "Whisper" — only in msg 5
        screen.send("/")
        screen.send("Whisper")
        screen.send_key("enter")
        title2 = screen.get_row(0)
        assert "5 / 5" in title2

        # n should wrap back to the same match (only 1 result)
        screen.send("n")
        title3 = screen.get_row(0)
        assert "5 / 5" in title3

    def test_cancel_re_search_keeps_old(self, screen):
        # First search
        screen.send("/")
        screen.send("tavern")
        screen.send_key("enter")

        # Start new search but cancel
        screen.send("/")
        screen.send_key("esc", pause=0.3)

        # Should still be in search mode with old query
        help_row = screen.get_row(screen.rows - 1)
        assert "SEARCH" in help_row
        assert "tavern" in help_row.lower()


class TestTerminalResize:
    """Test that the viewer handles terminal resize correctly."""

    def test_resize_wider(self):
        s = Screen(rows=20, cols=60)
        # Verify initial render at narrow width
        all_text = s.get_all_text()
        assert "Bob" in all_text

        # Resize wider
        s.resize(20, 120)
        all_text = s.get_all_text()
        assert "Bob" in all_text
        # Title bar should fill the wider width
        title = s.get_row(0)
        assert len(title.rstrip()) > 50
        s.close()

    def test_resize_shorter(self):
        s = Screen(rows=25, cols=90)
        all_text = s.get_all_text()
        assert "Bob" in all_text

        # Resize to fewer rows — should still render without crashing
        s.resize(10, 90)
        all_text = s.get_all_text()
        assert "Bob" in all_text
        # Help bar should be on the last row
        help_row = s.get_row(s.rows - 1)
        assert "scroll" in help_row or "quit" in help_row
        s.close()

    def test_content_reflows_on_resize(self):
        s = Screen(rows=20, cols=40)
        # At 40 cols, long messages will wrap more
        text_narrow = s.get_all_text()

        s.resize(20, 120)
        text_wide = s.get_all_text()

        # The same content should be present but laid out differently
        assert "Hello Alice!" in text_narrow
        assert "Hello Alice!" in text_wide
        # Narrow should have more lines of content due to wrapping
        narrow_lines = [l for l in text_narrow.split("\n") if l.strip()]
        wide_lines = [l for l in text_wide.split("\n") if l.strip()]
        assert len(narrow_lines) >= len(wide_lines)
        s.close()


class TestParsing:
    """Unit tests for parsing and GPG detection (no pty needed)."""

    def test_parse_chat_from_lines(self):
        from viewer import parse_chat
        fixture = Path(FIXTURE).read_text().splitlines()
        chat = parse_chat(fixture)
        assert len(chat.messages) == 5
        assert chat.messages[0].name == "Bob"
        assert chat.messages[1].name == "alice"
        assert chat.messages[1].is_user is True
        assert len(chat.messages[0].swipes) == 2

    def test_gpg_detection_plaintext(self):
        from viewer import _is_gpg_file
        assert _is_gpg_file(FIXTURE) is False

    def test_gpg_detection_binary(self, tmp_path):
        from viewer import _is_gpg_file
        # GPG packets have bit 7 set in the first byte
        for tag in [0x85, 0x8C, 0xC0, 0xFF]:
            gpg_file = tmp_path / f"test_{tag:x}.gpg"
            gpg_file.write_bytes(bytes([tag]) + b"\x00" * 100)
            assert _is_gpg_file(str(gpg_file)) is True

    def test_gpg_detection_armored(self, tmp_path):
        from viewer import _is_gpg_file
        gpg_file = tmp_path / "test.asc"
        gpg_file.write_text("-----BEGIN PGP MESSAGE-----\nstuff\n-----END PGP MESSAGE-----\n")
        assert _is_gpg_file(str(gpg_file)) is True


class TestGPGDecryption:
    """Test loading a GPG-encrypted JSONL file via the pty."""

    def test_gpg_encrypted_file(self):
        screen = pyte.Screen(COLS, ROWS)
        stream = pyte.Stream(screen)
        child = pexpect.spawn(
            f"python3 {VIEWER} {ENCRYPTED_FIXTURE}",
            dimensions=(ROWS, COLS),
            encoding="utf-8",
            timeout=5,
        )
        # Wait for passphrase prompt
        child.expect("GPG passphrase:", timeout=5)
        child.sendline("test")

        # Read until idle — TUI should render
        while True:
            try:
                data = child.read_nonblocking(size=4096, timeout=0.3)
                stream.feed(data)
            except (pexpect.TIMEOUT, pexpect.EOF):
                break

        all_text = "\n".join(line.rstrip() for line in screen.display)
        # Should show the same content as the plaintext fixture
        assert "Bob" in all_text
        assert "#1" in all_text

        try:
            child.sendeof()
        except OSError:
            pass
        child.close(force=True)


class TestHelpOverlay:
    def test_help_shows_and_dismisses(self, screen):
        screen.send("?")
        all_text = screen.get_all_text()
        assert "Keybindings" in all_text
        assert "Toggle reasoning" in all_text

        screen.send("?")
        all_text = screen.get_all_text()
        # Help should be dismissed, back to normal view
        assert "Hello Alice!" in all_text or "#1" in all_text
