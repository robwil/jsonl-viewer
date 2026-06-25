"""Curses drawing functions for the viewer UI."""

import curses

from .colors import (
    CP_CURSOR_MARKER,
    CP_HELP_BAR,
    CP_PROGRESS_FILL,
    CP_SEARCH_MATCH,
    CP_SWIPE_INDICATOR,
    CP_TITLE_BAR,
)
from .models import Chat, Message, RenderedLine
from .render import _build_header_text, _name_color


def draw_title_bar(stdscr, row: int, width: int, chat: Chat,
                   cursor_msg: int, total_msgs: int):
    """Draw the top title bar with chat name, date, and progress."""
    left = f" {chat.title}"
    if chat.date:
        left += f"  {chat.date}"

    msg_num = cursor_msg + 1
    pct = int(100 * msg_num / total_msgs) if total_msgs else 0
    right = f" {msg_num} / {total_msgs} ({pct}%) "

    # Progress bar fills from the left based on percentage
    bar_width = width
    filled = int(bar_width * pct / 100) if total_msgs else 0

    full_text = left.ljust(width - len(right)) + right
    full_text = full_text[:width]

    try:
        if filled > 0:
            stdscr.addnstr(row, 0, full_text[:filled], filled,
                           curses.color_pair(CP_PROGRESS_FILL) | curses.A_BOLD)
        if filled < width:
            stdscr.addnstr(row, filled, full_text[filled:], width - filled,
                           curses.color_pair(CP_TITLE_BAR) | curses.A_BOLD)
    except curses.error:
        pass


def draw_sticky_header(stdscr, row: int, width: int, msg: Message, msg_id: int):
    """Draw the sticky current-message header."""
    header_text = _build_header_text(msg, "▌ ", msg_id=msg_id)
    name_cp = _name_color(msg)
    try:
        stdscr.addstr(row, 0, "▌", curses.color_pair(CP_CURSOR_MARKER) | curses.A_BOLD)
        stdscr.addnstr(row, 1, header_text[1:width].ljust(width - 1), width - 1,
                       curses.color_pair(name_cp) | curses.A_BOLD | curses.A_REVERSE)
    except curses.error:
        pass


def draw_help_bar(stdscr, height, width):
    bar = " ↑↓:scroll  n/N:msg  ←→:swipe  r:reasoning  /:search  g:goto  q:quit  ?:help"
    bar = bar[:width].ljust(width)
    try:
        stdscr.addnstr(height - 1, 0, bar, width, curses.color_pair(CP_HELP_BAR))
    except curses.error:
        pass


def draw_search_bar(stdscr, height: int, width: int, query: str,
                    match_pos: int, total_matches: int):
    """Draw the search mode status bar."""
    sbar = f" SEARCH \"{query}\"  {match_pos}/{total_matches}  n/N:next/prev  Esc:exit"
    sbar = sbar[:width].ljust(width)
    try:
        stdscr.addnstr(height - 1, 0, sbar, width,
                       curses.color_pair(CP_SWIPE_INDICATOR) | curses.A_BOLD)
    except curses.error:
        pass


def draw_content_line(stdscr, screen_row: int, width: int, rl: RenderedLine,
                      search_mode: bool, search_query: str):
    """Draw a single content line, handling cursor marker and search highlights."""
    attr = curses.color_pair(rl.color_pair)
    if rl.bold:
        attr |= curses.A_BOLD
    text = rl.text

    try:
        col = 0
        if text.startswith("▌"):
            stdscr.addstr(screen_row, 0, "▌",
                          curses.color_pair(CP_CURSOR_MARKER) | curses.A_BOLD)
            col = 1
            text = text[1:]

        if search_mode and search_query and not rl.is_header:
            highlight_attr = curses.color_pair(CP_SEARCH_MATCH) | curses.A_BOLD
            _draw_with_highlights(stdscr, screen_row, col, text,
                                  width - col, attr, highlight_attr,
                                  search_query)
        else:
            stdscr.addnstr(screen_row, col, text[:width - col],
                           width - col, attr)
    except curses.error:
        pass


def _draw_with_highlights(stdscr, row: int, col: int, text: str,
                          max_w: int, normal_attr: int, highlight_attr: int,
                          query: str):
    """Draw text with case-insensitive search matches highlighted."""
    text = text[:max_w]
    lower_text = text.lower()
    lower_query = query.lower()
    qlen = len(lower_query)
    pos = 0
    x = col
    while pos < len(text):
        match_pos = lower_text.find(lower_query, pos)
        if match_pos == -1:
            stdscr.addnstr(row, x, text[pos:], max_w - (x - col), normal_attr)
            break
        if match_pos > pos:
            chunk = text[pos:match_pos]
            stdscr.addnstr(row, x, chunk, max_w - (x - col), normal_attr)
            x += len(chunk)
        matched = text[match_pos:match_pos + qlen]
        stdscr.addnstr(row, x, matched, max_w - (x - col), highlight_attr)
        x += len(matched)
        pos = match_pos + qlen
