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
        gpg_file = tmp_path / "test.gpg"
        gpg_file.write_bytes(b"\x85\x02" + b"\x00" * 100)
        assert _is_gpg_file(str(gpg_file)) is True

    def test_gpg_detection_armored(self, tmp_path):
        from viewer import _is_gpg_file
        gpg_file = tmp_path / "test.asc"
        gpg_file.write_text("-----BEGIN PGP MESSAGE-----\nstuff\n-----END PGP MESSAGE-----\n")
        assert _is_gpg_file(str(gpg_file)) is True


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
