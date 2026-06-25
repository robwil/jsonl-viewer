"""Viewer application state and actions."""

from dataclasses import dataclass, field

from .models import Chat, Message, RenderedLine
from .render import render_messages


@dataclass
class ViewerState:
    chat: Chat
    messages: list[Message]
    cursor_msg: int = 0
    scroll_pos: int = 0
    expanded_reasoning: set[int] = field(default_factory=set)
    rendered: list[RenderedLine] = field(default_factory=list)
    line_to_msg: list[int] = field(default_factory=list)
    needs_rerender: bool = True
    needs_clear: bool = True
    scroll_to_cursor: bool = False
    scroll_to_search: str | None = None
    # Search
    search_mode: bool = False
    search_query: str = ""
    search_matches: list[int] = field(default_factory=list)
    search_idx: int = 0

    def rerender(self, width: int):
        self.rendered = render_messages(
            self.messages, width, self.expanded_reasoning, self.cursor_msg)
        self.line_to_msg = [rl.msg_idx for rl in self.rendered]
        self.needs_rerender = False
        self.needs_clear = True

    def move_cursor(self, target: int):
        self.cursor_msg = max(0, min(target, len(self.messages) - 1))
        self.needs_rerender = True
        self.scroll_to_cursor = True

    def next_search_match(self, direction: int):
        if not self.search_matches:
            return
        self.search_idx = (self.search_idx + direction) % len(self.search_matches)
        self.cursor_msg = self.search_matches[self.search_idx]
        self.needs_rerender = True
        self.scroll_to_cursor = True
        self.scroll_to_search = self.search_query

    def toggle_swipe(self, direction: int):
        msg = self.messages[self.cursor_msg]
        if len(msg.swipes) > 1:
            msg.active_swipe = (msg.active_swipe + direction) % len(msg.swipes)
            self.needs_rerender = True

    def toggle_reasoning(self):
        if self.cursor_msg in self.expanded_reasoning:
            self.expanded_reasoning.discard(self.cursor_msg)
        else:
            self.expanded_reasoning.add(self.cursor_msg)
        self.needs_rerender = True

    def start_search(self, query: str):
        self.search_query = query
        self.search_matches = find_search_matches(self.messages, query)
        self.search_idx = 0
        self.search_mode = True
        if self.search_matches:
            self.cursor_msg = self.search_matches[0]
            self.needs_rerender = True
            self.scroll_to_cursor = True
            self.scroll_to_search = query

    def exit_search(self):
        self.search_mode = False


def find_search_matches(messages: list[Message], query: str) -> list[int]:
    """Return 0-based message indices whose active swipe body matches query (case-insensitive)."""
    q = query.lower()
    return [i for i, m in enumerate(messages)
            if q in m.swipes[m.active_swipe].text.lower()]


def is_header_visible(cursor_msg: int, scroll_pos: int, viewable: int,
                      rendered: list[RenderedLine]) -> bool:
    """Check if the header line of cursor_msg is visible in the viewport."""
    for i in range(viewable):
        line_idx = scroll_pos + i
        if line_idx >= len(rendered):
            break
        rl = rendered[line_idx]
        if rl.msg_idx == cursor_msg and rl.is_header:
            return True
    return False


def cursor_after_scroll(cursor_msg: int, scroll_pos: int, viewable: int,
                        line_to_msg: list[int], total: int) -> int:
    """If cursor_msg is fully off-screen, move it to the first/last visible message."""
    max_scroll = max(0, total - viewable)
    visible_end = min(scroll_pos + viewable, total)
    visible_msgs = set()
    for i in range(scroll_pos, visible_end):
        if i < len(line_to_msg):
            visible_msgs.add(line_to_msg[i])
    if not visible_msgs:
        return cursor_msg
    if scroll_pos == 0:
        return min(visible_msgs)
    if scroll_pos >= max_scroll:
        return max(visible_msgs)
    if cursor_msg in visible_msgs:
        return cursor_msg
    if cursor_msg < min(visible_msgs):
        return min(visible_msgs)
    return max(visible_msgs)


def scroll_to_msg(msg_idx: int, rendered: list[RenderedLine],
                  line_to_msg: list[int], scroll_pos: int,
                  viewable: int, max_scroll: int) -> int:
    """Return scroll position that puts the start of msg_idx on screen."""
    for i, mid in enumerate(line_to_msg):
        if mid == msg_idx:
            return max(0, min(i - 1, max_scroll))
    return scroll_pos


def scroll_to_match(msg_idx: int, query: str, rendered: list[RenderedLine],
                    line_to_msg: list[int], viewable: int, max_scroll: int) -> int:
    """Scroll so the first line in msg_idx containing query is visible."""
    q = query.lower()
    for i, rl in enumerate(rendered):
        if rl.msg_idx == msg_idx and not rl.is_header and q in rl.text.lower():
            target = max(0, i - viewable // 3)
            return max(0, min(target, max_scroll))
    for i, mid in enumerate(line_to_msg):
        if mid == msg_idx:
            return max(0, min(i - 1, max_scroll))
    return 0
