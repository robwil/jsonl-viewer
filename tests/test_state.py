"""Unit tests for ViewerState and scroll/search helpers."""

from viewer.models import Chat, Message, Swipe
from viewer.state import (
    ViewerState,
    cursor_after_scroll,
    find_search_matches,
    is_header_visible,
    scroll_to_msg,
)


def _make_chat(n_messages: int = 5, swipes_per: int = 1) -> Chat:
    """Create a simple chat with n messages."""
    messages = []
    for i in range(n_messages):
        swipes = [Swipe(text=f"Message {i} swipe {j}", reasoning="")
                  for j in range(swipes_per)]
        messages.append(Message(
            name="Alice" if i % 2 == 0 else "Bob",
            is_user=(i % 2 == 0),
            is_system=False,
            timestamp=f"2026-06-24T0{i}:00:00.000Z",
            swipes=swipes,
            active_swipe=0,
        ))
    return Chat(title="Test Chat", date="2026-06-24", messages=messages)


def _make_state(n_messages: int = 5, **kwargs) -> ViewerState:
    chat = _make_chat(n_messages, **kwargs)
    return ViewerState(chat=chat, messages=chat.messages)


class TestMoveCursor:
    def test_move_forward(self):
        state = _make_state()
        state.move_cursor(2)
        assert state.cursor_msg == 2
        assert state.needs_rerender
        assert state.scroll_to_cursor

    def test_move_clamps_to_last(self):
        state = _make_state(5)
        state.move_cursor(10)
        assert state.cursor_msg == 4

    def test_move_clamps_to_first(self):
        state = _make_state(5)
        state.move_cursor(-1)
        assert state.cursor_msg == 0


class TestToggleSwipe:
    def test_cycle_forward(self):
        state = _make_state(3, swipes_per=3)
        state.toggle_swipe(1)
        assert state.messages[0].active_swipe == 1
        assert state.needs_rerender

    def test_cycle_wraps(self):
        state = _make_state(3, swipes_per=3)
        state.messages[0].active_swipe = 2
        state.toggle_swipe(1)
        assert state.messages[0].active_swipe == 0

    def test_cycle_backward(self):
        state = _make_state(3, swipes_per=3)
        state.toggle_swipe(-1)
        assert state.messages[0].active_swipe == 2

    def test_single_swipe_no_change(self):
        state = _make_state(3, swipes_per=1)
        state.needs_rerender = False
        state.toggle_swipe(1)
        assert state.messages[0].active_swipe == 0
        assert not state.needs_rerender


class TestToggleReasoning:
    def test_expand(self):
        state = _make_state()
        state.toggle_reasoning()
        assert 0 in state.expanded_reasoning
        assert state.needs_rerender

    def test_collapse(self):
        state = _make_state()
        state.expanded_reasoning.add(0)
        state.needs_rerender = False
        state.toggle_reasoning()
        assert 0 not in state.expanded_reasoning
        assert state.needs_rerender


class TestSearch:
    def test_find_matches(self):
        chat = _make_chat(5)
        matches = find_search_matches(chat.messages, "Message 2")
        assert matches == [2]

    def test_find_matches_case_insensitive(self):
        chat = _make_chat(5)
        matches = find_search_matches(chat.messages, "message 2")
        assert matches == [2]

    def test_find_no_matches(self):
        chat = _make_chat(5)
        matches = find_search_matches(chat.messages, "nonexistent")
        assert matches == []

    def test_start_search(self):
        state = _make_state(5)
        state.needs_rerender = False
        state.start_search("Message 3")
        assert state.search_mode
        assert state.search_query == "Message 3"
        assert state.search_matches == [3]
        assert state.cursor_msg == 3
        assert state.needs_rerender

    def test_next_search_match(self):
        state = _make_state(5)
        state.start_search("Message")
        assert state.cursor_msg == 0
        state.next_search_match(1)
        assert state.cursor_msg == 1
        state.next_search_match(1)
        assert state.cursor_msg == 2

    def test_prev_search_match_wraps(self):
        state = _make_state(5)
        state.start_search("Message")
        assert state.cursor_msg == 0
        state.next_search_match(-1)
        assert state.cursor_msg == 4

    def test_exit_search(self):
        state = _make_state()
        state.start_search("Message")
        state.exit_search()
        assert not state.search_mode


class TestCursorAfterScroll:
    def test_cursor_stays_when_visible(self):
        line_to_msg = [0, 0, 0, 1, 1, 1, 2, 2, 2]
        result = cursor_after_scroll(1, 2, 5, line_to_msg, 9)
        assert result == 1

    def test_cursor_snaps_forward(self):
        line_to_msg = [0, 0, 0, 1, 1, 1, 2, 2, 2]
        result = cursor_after_scroll(0, 3, 5, line_to_msg, 9)
        assert result == 1

    def test_cursor_snaps_to_first_at_top(self):
        line_to_msg = [0, 0, 0, 1, 1, 1, 2, 2, 2]
        result = cursor_after_scroll(2, 0, 5, line_to_msg, 9)
        assert result == 0


class TestIsHeaderVisible:
    def test_header_visible(self):
        from viewer.models import RenderedLine
        rendered = [
            RenderedLine("header", msg_idx=0, is_header=True),
            RenderedLine("body", msg_idx=0),
            RenderedLine("header", msg_idx=1, is_header=True),
            RenderedLine("body", msg_idx=1),
        ]
        assert is_header_visible(0, 0, 4, rendered)

    def test_header_not_visible(self):
        from viewer.models import RenderedLine
        rendered = [
            RenderedLine("header", msg_idx=0, is_header=True),
            RenderedLine("body", msg_idx=0),
            RenderedLine("header", msg_idx=1, is_header=True),
            RenderedLine("body", msg_idx=1),
        ]
        assert not is_header_visible(0, 2, 2, rendered)
