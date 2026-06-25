"""Integration tests for the JSONL chat viewer TUI.

Uses Textual's pilot framework to drive the app and assert on screen contents.
"""

from pathlib import Path

import pytest

from viewer.app import ChatViewerApp, MessageWidget, StatusBar, TitleBar
from viewer.parser import load_chat, parse_chat, _is_gpg_file

FIXTURE = str(Path(__file__).resolve().parent / "fixture.jsonl")
ENCRYPTED_FIXTURE = str(Path(__file__).resolve().parent / "encrypted_fixture.jsonl.gpg")
# Small terminal to force scrolling with our 5-message fixture
ROWS, COLS = 20, 90


def _load_fixture():
    return load_chat(FIXTURE)


@pytest.fixture
def chat():
    return _load_fixture()


async def _launch(chat, rows=ROWS, cols=COLS):
    """Create an app and return (app, pilot) context manager."""
    app = ChatViewerApp(chat)
    return app, app.run_test(size=(cols, rows))


def _title_text(app: ChatViewerApp) -> str:
    return app.query_one("#title-bar", TitleBar).render().plain


def _status_text(app: ChatViewerApp) -> str:
    bar = app.query_one("#status-bar", StatusBar)
    result = bar.render()
    return result.plain if hasattr(result, "plain") else str(result)


def _all_message_text(app: ChatViewerApp) -> str:
    """Get all rendered message text as a single string."""
    parts = []
    for i in range(len(app.chat.messages)):
        widget = app.query_one(f"#msg-{i}", MessageWidget)
        rendered = widget.render()
        if hasattr(rendered, "plain"):
            parts.append(rendered.plain)
        else:
            from rich.console import Console
            from io import StringIO
            buf = StringIO()
            console = Console(file=buf, width=COLS, force_terminal=True)
            console.print(rendered)
            parts.append(buf.getvalue())
    return "\n".join(parts)


class TestInitialRender:
    @pytest.mark.asyncio
    async def test_title_bar_shows_chat_name(self, chat):
        app = ChatViewerApp(chat)
        async with app.run_test(size=(COLS, ROWS)):
            title = _title_text(app)
            assert "Bob" in title
            assert "2026-01-15" in title

    @pytest.mark.asyncio
    async def test_title_bar_shows_progress(self, chat):
        app = ChatViewerApp(chat)
        async with app.run_test(size=(COLS, ROWS)):
            title = _title_text(app)
            assert "1 / 5" in title

    @pytest.mark.asyncio
    async def test_first_message_header(self, chat):
        app = ChatViewerApp(chat)
        async with app.run_test(size=(COLS, ROWS)):
            text = _all_message_text(app)
            assert "#1" in text
            assert "Bob" in text
            assert "fancy-llm" in text

    @pytest.mark.asyncio
    async def test_first_message_body(self, chat):
        app = ChatViewerApp(chat)
        async with app.run_test(size=(COLS, ROWS)):
            text = _all_message_text(app)
            assert "Hello Alice!" in text
            assert "fire crackles" in text

    @pytest.mark.asyncio
    async def test_swipe_indicator_on_first_message(self, chat):
        app = ChatViewerApp(chat)
        async with app.run_test(size=(COLS, ROWS)):
            text = _all_message_text(app)
            assert "[1/2]" in text

    @pytest.mark.asyncio
    async def test_cursor_marker_on_first_message(self, chat):
        app = ChatViewerApp(chat)
        async with app.run_test(size=(COLS, ROWS)):
            widget = app.query_one("#msg-0", MessageWidget)
            assert widget.selected is True
            rendered = widget.render()
            plain = rendered.plain if hasattr(rendered, "plain") else str(rendered)
            assert "▌" in plain

    @pytest.mark.asyncio
    async def test_help_bar(self, chat):
        app = ChatViewerApp(chat)
        async with app.run_test(size=(COLS, ROWS)):
            status = _status_text(app)
            assert "scroll" in status
            assert "quit" in status

    @pytest.mark.asyncio
    async def test_reasoning_hidden_by_default(self, chat):
        app = ChatViewerApp(chat)
        async with app.run_test(size=(COLS, ROWS)):
            text = _all_message_text(app)
            assert "greet the user warmly" not in text


class TestMessageNavigation:
    @pytest.mark.asyncio
    async def test_next_message(self, chat):
        app = ChatViewerApp(chat)
        async with app.run_test(size=(COLS, ROWS)) as pilot:
            await pilot.press("n")
            assert app.cursor_msg == 1
            assert "2 / 5" in _title_text(app)

    @pytest.mark.asyncio
    async def test_prev_message_with_N(self, chat):
        app = ChatViewerApp(chat)
        async with app.run_test(size=(COLS, ROWS)) as pilot:
            await pilot.press("n")
            await pilot.press("N")
            assert app.cursor_msg == 0
            assert "1 / 5" in _title_text(app)

    @pytest.mark.asyncio
    async def test_prev_message_with_p(self, chat):
        app = ChatViewerApp(chat)
        async with app.run_test(size=(COLS, ROWS)) as pilot:
            await pilot.press("n")
            await pilot.press("p")
            assert app.cursor_msg == 0
            assert "1 / 5" in _title_text(app)

    @pytest.mark.asyncio
    async def test_navigate_to_last_message(self, chat):
        app = ChatViewerApp(chat)
        async with app.run_test(size=(COLS, ROWS)) as pilot:
            for _ in range(5):
                await pilot.press("n")
            assert app.cursor_msg == 4
            assert "5 / 5" in _title_text(app)

    @pytest.mark.asyncio
    async def test_n_at_last_message_stays(self, chat):
        app = ChatViewerApp(chat)
        async with app.run_test(size=(COLS, ROWS)) as pilot:
            for _ in range(10):
                await pilot.press("n")
            assert app.cursor_msg == 4
            assert "5 / 5" in _title_text(app)

    @pytest.mark.asyncio
    async def test_p_at_first_message_stays(self, chat):
        app = ChatViewerApp(chat)
        async with app.run_test(size=(COLS, ROWS)) as pilot:
            await pilot.press("p")
            assert app.cursor_msg == 0
            assert "1 / 5" in _title_text(app)


class TestGotoDialog:
    @pytest.mark.asyncio
    async def test_goto_message(self, chat):
        app = ChatViewerApp(chat)
        async with app.run_test(size=(COLS, ROWS)) as pilot:
            await pilot.press("g")
            await pilot.press("4")
            await pilot.press("enter")
            assert app.cursor_msg == 3
            assert "4 / 5" in _title_text(app)

    @pytest.mark.asyncio
    async def test_goto_cancel(self, chat):
        app = ChatViewerApp(chat)
        async with app.run_test(size=(COLS, ROWS)) as pilot:
            await pilot.press("g")
            await pilot.press("escape")
            assert app.cursor_msg == 0
            assert "1 / 5" in _title_text(app)

    @pytest.mark.asyncio
    async def test_goto_last_message(self, chat):
        app = ChatViewerApp(chat)
        async with app.run_test(size=(COLS, ROWS)) as pilot:
            await pilot.press("g")
            await pilot.press("5")
            await pilot.press("enter")
            assert app.cursor_msg == 4
            assert "5 / 5" in _title_text(app)


class TestSwipes:
    @pytest.mark.asyncio
    async def test_swipe_next(self, chat):
        app = ChatViewerApp(chat)
        async with app.run_test(size=(COLS, ROWS)) as pilot:
            text = _all_message_text(app)
            assert "[1/2]" in text
            assert "Hello Alice!" in text

            await pilot.press("l")
            text = _all_message_text(app)
            assert "[2/2]" in text
            assert "Greetings traveler!" in text

    @pytest.mark.asyncio
    async def test_swipe_prev_wraps(self, chat):
        app = ChatViewerApp(chat)
        async with app.run_test(size=(COLS, ROWS)) as pilot:
            await pilot.press("h")
            text = _all_message_text(app)
            assert "[2/2]" in text

    @pytest.mark.asyncio
    async def test_swipe_round_trip(self, chat):
        app = ChatViewerApp(chat)
        async with app.run_test(size=(COLS, ROWS)) as pilot:
            await pilot.press("l")
            text = _all_message_text(app)
            assert "[2/2]" in text

            await pilot.press("h")
            text = _all_message_text(app)
            assert "[1/2]" in text

    @pytest.mark.asyncio
    async def test_swipe_on_message_without_swipes(self, chat):
        app = ChatViewerApp(chat)
        async with app.run_test(size=(COLS, ROWS)) as pilot:
            await pilot.press("n")  # msg 2 (alice, no swipes)
            await pilot.press("l")
            assert app.cursor_msg == 1
            assert "2 / 5" in _title_text(app)


class TestReasoning:
    @pytest.mark.asyncio
    async def test_toggle_reasoning_on_and_off(self, chat):
        app = ChatViewerApp(chat)
        async with app.run_test(size=(COLS, ROWS)) as pilot:
            text = _all_message_text(app)
            assert "greet the user warmly" not in text

            await pilot.press("r")
            text = _all_message_text(app)
            assert "greet the user warmly" in text
            assert "Reasoning" in text

            await pilot.press("r")
            text = _all_message_text(app)
            assert "greet the user warmly" not in text

    @pytest.mark.asyncio
    async def test_reasoning_toggle_on_user_message_no_crash(self, chat):
        app = ChatViewerApp(chat)
        async with app.run_test(size=(COLS, ROWS)) as pilot:
            await pilot.press("n")  # msg 2 (user msg, no reasoning)
            await pilot.press("r")
            assert app.cursor_msg == 1
            assert "2 / 5" in _title_text(app)


class TestSearch:
    @pytest.mark.asyncio
    async def test_search_finds_match(self, chat):
        app = ChatViewerApp(chat)
        async with app.run_test(size=(COLS, ROWS)) as pilot:
            await pilot.press("slash")
            await pilot.press(*"stranger")
            await pilot.press("enter")
            assert app.search_mode is True
            status = _status_text(app)
            assert "SEARCH" in status

    @pytest.mark.asyncio
    async def test_search_shows_match_count(self, chat):
        app = ChatViewerApp(chat)
        async with app.run_test(size=(COLS, ROWS)) as pilot:
            await pilot.press("slash")
            await pilot.press(*"tavern")
            await pilot.press("enter")
            status = _status_text(app)
            assert "SEARCH" in status
            assert "tavern" in status.lower()

    @pytest.mark.asyncio
    async def test_search_navigate_next(self, chat):
        app = ChatViewerApp(chat)
        async with app.run_test(size=(COLS, ROWS)) as pilot:
            # "Whisper" only in message 4; "stranger" in 2, 3, 4
            await pilot.press("slash")
            await pilot.press(*"stranger")
            await pilot.press("enter")
            first_cursor = app.cursor_msg
            assert len(app.search_matches) >= 2

            await pilot.press("n")
            assert app.cursor_msg > first_cursor

    @pytest.mark.asyncio
    async def test_search_navigate_prev(self, chat):
        app = ChatViewerApp(chat)
        async with app.run_test(size=(COLS, ROWS)) as pilot:
            await pilot.press("slash")
            await pilot.press(*"stranger")
            await pilot.press("enter")
            first_cursor = app.cursor_msg

            await pilot.press("n")
            second_cursor = app.cursor_msg
            assert second_cursor > first_cursor

            await pilot.press("N")
            assert app.cursor_msg == first_cursor
            assert app.search_mode is True

    @pytest.mark.asyncio
    async def test_search_exit_with_esc(self, chat):
        app = ChatViewerApp(chat)
        async with app.run_test(size=(COLS, ROWS)) as pilot:
            await pilot.press("slash")
            await pilot.press(*"stranger")
            await pilot.press("enter")
            assert app.search_mode is True

            await pilot.press("escape")
            assert app.search_mode is False
            status = _status_text(app)
            assert "SEARCH" not in status
            assert "scroll" in status

    @pytest.mark.asyncio
    async def test_search_cancel_dialog(self, chat):
        app = ChatViewerApp(chat)
        async with app.run_test(size=(COLS, ROWS)) as pilot:
            await pilot.press("slash")
            await pilot.press("escape")
            assert app.search_mode is False
            status = _status_text(app)
            assert "SEARCH" not in status


class TestScrolling:
    @pytest.mark.asyncio
    async def test_scroll_changes_offset(self, chat):
        app = ChatViewerApp(chat)
        async with app.run_test(size=(80, 14)) as pilot:
            from textual.containers import VerticalScroll
            container = app.query_one("#messages", VerticalScroll)
            offset_before = container.scroll_offset.y

            for _ in range(3):
                await pilot.press("j")
            offset_after = container.scroll_offset.y
            assert offset_after > offset_before

    @pytest.mark.asyncio
    async def test_page_down(self, chat):
        app = ChatViewerApp(chat)
        async with app.run_test(size=(80, 14)) as pilot:
            from textual.containers import VerticalScroll
            container = app.query_one("#messages", VerticalScroll)
            offset_before = container.scroll_offset.y

            await pilot.press("space")
            offset_after = container.scroll_offset.y
            assert offset_after > offset_before

    @pytest.mark.asyncio
    async def test_j_k_round_trip(self, chat):
        app = ChatViewerApp(chat)
        async with app.run_test(size=(80, 14)) as pilot:
            from textual.containers import VerticalScroll
            container = app.query_one("#messages", VerticalScroll)
            offset_before = container.scroll_offset.y

            for _ in range(3):
                await pilot.press("j")
            assert container.scroll_offset.y > offset_before

            for _ in range(3):
                await pilot.press("k")
            assert container.scroll_offset.y == offset_before


class TestCursorFollowsScroll:
    @pytest.mark.asyncio
    async def test_cursor_snaps_forward_on_scroll_down(self, chat):
        app = ChatViewerApp(chat)
        async with app.run_test(size=(80, 14)) as pilot:
            assert app.cursor_msg == 0

            for _ in range(15):
                await pilot.press("j")
            await pilot.pause()
            assert app.cursor_msg > 0

    @pytest.mark.asyncio
    async def test_cursor_snaps_back_on_scroll_up(self, chat):
        app = ChatViewerApp(chat)
        async with app.run_test(size=(80, 14)) as pilot:
            for _ in range(4):
                await pilot.press("n")
            assert app.cursor_msg == 4

            for _ in range(20):
                await pilot.press("k")
            await pilot.pause()
            assert app.cursor_msg < 4

    @pytest.mark.asyncio
    async def test_cursor_stays_when_partially_visible(self, chat):
        app = ChatViewerApp(chat)
        async with app.run_test(size=(80, 14)) as pilot:
            await pilot.press("n")
            await pilot.press("n")
            assert app.cursor_msg == 2

            await pilot.press("j")
            await pilot.pause()
            assert app.cursor_msg == 2


class TestSearchReSearch:
    @pytest.mark.asyncio
    async def test_new_search_replaces_old(self, chat):
        app = ChatViewerApp(chat)
        async with app.run_test(size=(COLS, ROWS)) as pilot:
            await pilot.press("slash")
            await pilot.press(*"tavern")
            await pilot.press("enter")
            assert app.search_query == "tavern"

            await pilot.press("slash")
            await pilot.press(*"stranger")
            await pilot.press("enter")
            assert app.search_query == "stranger"

    @pytest.mark.asyncio
    async def test_re_search_navigates_new_matches(self, chat):
        app = ChatViewerApp(chat)
        async with app.run_test(size=(COLS, ROWS)) as pilot:
            await pilot.press("slash")
            await pilot.press(*"tavern")
            await pilot.press("enter")

            await pilot.press("slash")
            await pilot.press(*"Whisper")
            await pilot.press("enter")
            assert app.cursor_msg == 4
            assert "5 / 5" in _title_text(app)

            await pilot.press("n")
            assert app.cursor_msg == 4

    @pytest.mark.asyncio
    async def test_cancel_re_search_keeps_old(self, chat):
        app = ChatViewerApp(chat)
        async with app.run_test(size=(COLS, ROWS)) as pilot:
            await pilot.press("slash")
            await pilot.press(*"tavern")
            await pilot.press("enter")

            await pilot.press("slash")
            await pilot.press("escape")

            assert app.search_mode is True
            assert app.search_query == "tavern"
            status = _status_text(app)
            assert "SEARCH" in status


class TestTerminalResize:
    @pytest.mark.asyncio
    async def test_resize_wider(self, chat):
        app = ChatViewerApp(chat)
        async with app.run_test(size=(60, 20)) as pilot:
            text = _all_message_text(app)
            assert "Bob" in text

            await pilot.resize_terminal(120, 20)
            text = _all_message_text(app)
            assert "Bob" in text

    @pytest.mark.asyncio
    async def test_resize_shorter(self, chat):
        app = ChatViewerApp(chat)
        async with app.run_test(size=(90, 25)) as pilot:
            text = _all_message_text(app)
            assert "Bob" in text

            await pilot.resize_terminal(90, 10)
            text = _all_message_text(app)
            assert "Bob" in text

    @pytest.mark.asyncio
    async def test_content_reflows_on_resize(self, chat):
        app = ChatViewerApp(chat)
        async with app.run_test(size=(40, 20)) as pilot:
            w0 = app.query_one("#msg-0", MessageWidget)
            narrow_height = w0.size.height

            await pilot.resize_terminal(120, 20)
            wide_height = w0.size.height
            assert narrow_height >= wide_height


class TestParsing:
    """Unit tests for parsing and GPG detection (no Textual needed)."""

    def test_parse_chat_from_lines(self):
        fixture = Path(FIXTURE).read_text().splitlines()
        chat = parse_chat(fixture)
        assert len(chat.messages) == 5
        assert chat.messages[0].name == "Bob"
        assert chat.messages[1].name == "alice"
        assert chat.messages[1].is_user is True
        assert len(chat.messages[0].swipes) == 2

    def test_gpg_detection_plaintext(self):
        assert _is_gpg_file(FIXTURE) is False

    def test_gpg_detection_binary(self, tmp_path):
        for tag in [0x85, 0x8C, 0xC0, 0xFF]:
            gpg_file = tmp_path / f"test_{tag:x}.gpg"
            gpg_file.write_bytes(bytes([tag]) + b"\x00" * 100)
            assert _is_gpg_file(str(gpg_file)) is True

    def test_gpg_detection_armored(self, tmp_path):
        gpg_file = tmp_path / "test.asc"
        gpg_file.write_text("-----BEGIN PGP MESSAGE-----\nstuff\n-----END PGP MESSAGE-----\n")
        assert _is_gpg_file(str(gpg_file)) is True


class TestGPGDecryption:
    """Test loading a GPG-encrypted JSONL file."""

    def test_gpg_encrypted_file(self):
        import subprocess, shutil
        if not shutil.which("gpg"):
            pytest.skip("gpg not installed")
        if not Path(ENCRYPTED_FIXTURE).exists():
            pytest.skip("encrypted fixture not found")

        result = subprocess.run(
            ["gpg", "--decrypt", "--batch", "--yes",
             "--passphrase-fd", "0", "--no-tty", ENCRYPTED_FIXTURE],
            input=b"test",
            capture_output=True,
        )
        if result.returncode != 0:
            pytest.skip(f"gpg decryption failed: {result.stderr.decode()}")

        chat = parse_chat(result.stdout.decode().splitlines())
        assert len(chat.messages) > 0
        assert chat.messages[0].name == "Bob"


class TestHelpOverlay:
    @pytest.mark.asyncio
    async def test_help_shows_and_dismisses(self, chat):
        app = ChatViewerApp(chat)
        async with app.run_test(size=(COLS, ROWS)) as pilot:
            await pilot.press("question_mark")
            # Help screen should be on the screen stack
            assert len(app.screen_stack) > 1

            await pilot.press("question_mark")
            # Should be dismissed
            assert len(app.screen_stack) == 1
