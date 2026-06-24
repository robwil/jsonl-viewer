#!/usr/bin/env python3
"""TUI viewer for SillyTavern JSONL chat exports."""

import argparse
import curses
import json
import sys
import textwrap
from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class Swipe:
    text: str
    reasoning: str
    model: str = ""
    token_count: int = 0
    gen_seconds: float = 0.0


@dataclass
class Message:
    name: str
    is_user: bool
    is_system: bool
    timestamp: str
    swipes: list[Swipe] = field(default_factory=list)
    active_swipe: int = 0


@dataclass
class Chat:
    title: str
    date: str
    messages: list[Message]


def _parse_gen_seconds(obj: dict) -> float:
    started = obj.get("gen_started", "")
    finished = obj.get("gen_finished", "")
    if started and finished:
        try:
            fmt = "%Y-%m-%dT%H:%M:%S.%fZ"
            dt_s = datetime.strptime(started, fmt)
            dt_f = datetime.strptime(finished, fmt)
            return max(0.0, (dt_f - dt_s).total_seconds())
        except (ValueError, TypeError):
            pass
    return 0.0


def _format_time(ts: str) -> str:
    """'2026-06-24T03:12:02.044Z' -> '3:12am'"""
    if not ts:
        return ""
    try:
        raw = ts.rstrip("Z")
        if "." in raw:
            dt = datetime.strptime(raw, "%Y-%m-%dT%H:%M:%S.%f")
        else:
            dt = datetime.strptime(raw, "%Y-%m-%dT%H:%M:%S")
        return dt.strftime("%-I:%M%p").lower()
    except (ValueError, TypeError):
        return ts


def _format_date(ts: str) -> str:
    """'2026-06-24T03:12:02.044Z' -> '2026-06-24'"""
    if not ts:
        return ""
    try:
        return ts[:10]
    except (ValueError, TypeError):
        return ""


def parse_chat(path: str) -> Chat:
    messages = []
    title = ""
    chat_date = ""
    with open(path) as f:
        for i, line in enumerate(f):
            obj = json.loads(line)
            if i == 0 and "chat_metadata" in obj:
                continue
            name = obj.get("name", "???")
            is_user = obj.get("is_user", False)
            is_system = obj.get("is_system", False)
            timestamp = obj.get("send_date", "")
            swipe_texts = obj.get("swipes", [])
            swipe_infos = obj.get("swipe_info", [])
            active_swipe = obj.get("swipe_id", 0) or 0

            if not title and obj.get("title"):
                title = obj["title"]
            if not chat_date and timestamp:
                chat_date = _format_date(timestamp)

            main_text = obj.get("mes", "")
            main_extra = obj.get("extra", {})
            main_reasoning = main_extra.get("reasoning", "") or ""
            main_model = main_extra.get("model", "") or ""
            main_tokens = main_extra.get("token_count", 0) or 0
            main_gen = _parse_gen_seconds(obj)

            if swipe_texts:
                swipes = []
                for j, st in enumerate(swipe_texts):
                    reasoning = ""
                    model = ""
                    tokens = 0
                    gen_secs = 0.0
                    if j < len(swipe_infos):
                        si = swipe_infos[j]
                        si_extra = si.get("extra", {})
                        reasoning = si_extra.get("reasoning", "") or ""
                        model = si_extra.get("model", "") or ""
                        tokens = si_extra.get("token_count", 0) or 0
                        gen_secs = _parse_gen_seconds(si)
                    if j == active_swipe:
                        reasoning = reasoning or main_reasoning
                        model = model or main_model
                        tokens = tokens or main_tokens
                        gen_secs = gen_secs or main_gen
                    swipes.append(Swipe(text=st, reasoning=reasoning,
                                        model=model, token_count=tokens,
                                        gen_seconds=gen_secs))
            else:
                swipes = [Swipe(text=main_text, reasoning=main_reasoning,
                                model=main_model, token_count=main_tokens,
                                gen_seconds=main_gen)]

            messages.append(Message(
                name=name, is_user=is_user, is_system=is_system,
                timestamp=timestamp, swipes=swipes, active_swipe=active_swipe,
            ))

    if not title and messages:
        title = messages[0].name

    return Chat(title=title, date=chat_date, messages=messages)


# Color pair IDs
CP_USER_NAME = 1
CP_CHAR_NAME = 2
CP_SYSTEM_NAME = 3
CP_REASONING = 4
CP_SWIPE_INDICATOR = 5
CP_HELP_BAR = 6
CP_SEPARATOR = 7
CP_TIMESTAMP = 8
CP_CURSOR_MARKER = 9
CP_TITLE_BAR = 10
CP_PROGRESS_FILL = 11
CP_META = 12
CP_SEARCH_MATCH = 13


def init_colors():
    curses.start_color()
    curses.use_default_colors()
    curses.init_pair(CP_USER_NAME, curses.COLOR_GREEN, -1)
    curses.init_pair(CP_CHAR_NAME, curses.COLOR_CYAN, -1)
    curses.init_pair(CP_SYSTEM_NAME, curses.COLOR_YELLOW, -1)
    curses.init_pair(CP_REASONING, curses.COLOR_MAGENTA, -1)
    curses.init_pair(CP_SWIPE_INDICATOR, curses.COLOR_YELLOW, -1)
    curses.init_pair(CP_HELP_BAR, curses.COLOR_BLACK, curses.COLOR_WHITE)
    curses.init_pair(CP_SEPARATOR, curses.COLOR_WHITE, -1)
    curses.init_pair(CP_TIMESTAMP, curses.COLOR_WHITE, -1)
    curses.init_pair(CP_CURSOR_MARKER, curses.COLOR_YELLOW, -1)
    curses.init_pair(CP_TITLE_BAR, curses.COLOR_WHITE, curses.COLOR_BLACK)
    curses.init_pair(CP_PROGRESS_FILL, curses.COLOR_BLACK, curses.COLOR_CYAN)
    curses.init_pair(CP_META, curses.COLOR_WHITE, -1)
    curses.init_pair(CP_SEARCH_MATCH, curses.COLOR_RED, -1)


@dataclass
class RenderedLine:
    """A single screen line with its color pair."""
    text: str
    color_pair: int = 0
    bold: bool = False
    msg_idx: int = -1
    is_header: bool = False


def _build_header_text(msg: Message, prefix: str, msg_id: int = 0) -> str:
    """Build the header line text for a message. msg_id is 1-based."""
    swipe = msg.swipes[msg.active_swipe] if msg.swipes else Swipe("", "")
    id_str = f"#{msg_id} " if msg_id else ""
    parts = [f"{prefix}{id_str}{msg.name}"]

    if len(msg.swipes) > 1:
        parts.append(f"[{msg.active_swipe + 1}/{len(msg.swipes)}]")

    time_str = _format_time(msg.timestamp)
    if time_str:
        parts.append(time_str)

    if swipe.model:
        short_model = swipe.model.split("/")[-1] if "/" in swipe.model else swipe.model
        parts.append(short_model)

    if swipe.token_count:
        parts.append(f"{swipe.token_count}tok")

    if swipe.gen_seconds > 0:
        parts.append(f"{swipe.gen_seconds:.1f}s")

    return "  ".join(parts)


def _name_color(msg: Message) -> int:
    if msg.is_system:
        return CP_SYSTEM_NAME
    elif msg.is_user:
        return CP_USER_NAME
    return CP_CHAR_NAME


def render_messages(messages: list[Message], width: int, expanded_reasoning: set[int],
                    cursor_msg: int = -1) -> list[RenderedLine]:
    """Pre-render all messages into wrapped lines for the given terminal width."""
    lines: list[RenderedLine] = []
    gutter = 2
    content_width = max(width - gutter - 1, 20)

    for idx, msg in enumerate(messages):
        is_active = idx == cursor_msg
        prefix = "▌ " if is_active else "  "

        if idx > 0:
            lines.append(RenderedLine("─" * width, CP_SEPARATOR, msg_idx=idx))

        name_cp = _name_color(msg)
        header = _build_header_text(msg, prefix, msg_id=idx + 1)
        lines.append(RenderedLine(header, name_cp, bold=True, msg_idx=idx, is_header=True))

        swipe = msg.swipes[msg.active_swipe] if msg.swipes else Swipe("", "")

        # Reasoning (collapsible) — only shown when expanded
        if swipe.reasoning and idx in expanded_reasoning:
            lines.append(RenderedLine(f"{prefix}▼ Reasoning:", CP_REASONING, bold=True, msg_idx=idx))
            for para in swipe.reasoning.split("\n"):
                if not para.strip():
                    lines.append(RenderedLine(prefix, CP_REASONING, msg_idx=idx))
                    continue
                for wl in textwrap.wrap(para, content_width - 4):
                    lines.append(RenderedLine(f"{prefix}  │ {wl}", CP_REASONING, msg_idx=idx))
            lines.append(RenderedLine(prefix, 0, msg_idx=idx))

        # Message body
        for para in swipe.text.split("\n"):
            if not para.strip():
                lines.append(RenderedLine(prefix, 0, msg_idx=idx))
                continue
            for wl in textwrap.wrap(para, content_width):
                lines.append(RenderedLine(f"{prefix}{wl}", 0, msg_idx=idx))

        lines.append(RenderedLine(prefix, 0, msg_idx=idx))

    return lines


def _draw_title_bar(stdscr, row: int, width: int, chat: Chat,
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

    # Pad both parts
    full_text = left.ljust(width - len(right)) + right
    full_text = full_text[:width]

    try:
        # Draw filled portion
        if filled > 0:
            stdscr.addnstr(row, 0, full_text[:filled], filled,
                           curses.color_pair(CP_PROGRESS_FILL) | curses.A_BOLD)
        # Draw unfilled portion
        if filled < width:
            stdscr.addnstr(row, filled, full_text[filled:], width - filled,
                           curses.color_pair(CP_TITLE_BAR) | curses.A_BOLD)
    except curses.error:
        pass


def _draw_sticky_header(stdscr, row: int, width: int, msg: Message, msg_id: int):
    """Draw the sticky current-message header."""
    header_text = _build_header_text(msg, "▌ ", msg_id=msg_id)
    name_cp = _name_color(msg)
    try:
        stdscr.addstr(row, 0, "▌", curses.color_pair(CP_CURSOR_MARKER) | curses.A_BOLD)
        stdscr.addnstr(row, 1, header_text[1:width].ljust(width - 1), width - 1,
                       curses.color_pair(name_cp) | curses.A_BOLD | curses.A_REVERSE)
    except curses.error:
        pass


def _is_header_visible(cursor_msg: int, scroll_pos: int, viewable: int,
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


def draw_help_bar(stdscr, height, width):
    bar = " ↑↓:scroll  n/N:msg  ←→:swipe  r:reasoning  /:search  g:goto  q:quit  ?:help"
    bar = bar[:width].ljust(width)
    try:
        stdscr.addnstr(height - 1, 0, bar, width, curses.color_pair(CP_HELP_BAR))
    except curses.error:
        pass


HELP_LINES = [
    "Keybindings",
    "",
    "  ↑ / k          Scroll up one line",
    "  ↓ / j          Scroll down one line",
    "  PgUp            Scroll up one page",
    "  PgDn / Space    Scroll down one page",
    "  g / G           Go to message by ID",
    "",
    "  n               Next message",
    "  N / p           Previous message",
    "",
    "  ← / h           Previous swipe",
    "  → / l           Next swipe",
    "",
    "  r               Toggle reasoning",
    "",
    "  /               Search message text",
    "                  n/N to navigate results",
    "",
    "  q / Esc         Quit",
    "  ?               This help",
]


def _draw_help_overlay(stdscr, height, width):
    box_w = min(max(len(l) for l in HELP_LINES) + 6, width - 4)
    box_h = min(len(HELP_LINES) + 4, height - 2)
    start_y = (height - box_h) // 2
    start_x = (width - box_w) // 2

    for row in range(box_h):
        y = start_y + row
        if y < 0 or y >= height:
            continue
        if row == 0:
            line = "┌" + "─" * (box_w - 2) + "┐"
        elif row == box_h - 1:
            line = "└" + "─" * (box_w - 2) + "┘"
        else:
            content_idx = row - 2
            if 0 <= content_idx < len(HELP_LINES):
                inner = HELP_LINES[content_idx]
            else:
                inner = ""
            inner = inner[:box_w - 4]
            line = "│ " + inner.ljust(box_w - 4) + " │"
        try:
            stdscr.addnstr(y, start_x, line, box_w,
                           curses.color_pair(CP_HELP_BAR) | curses.A_BOLD)
        except curses.error:
            pass

    stdscr.refresh()
    while True:
        k = stdscr.getch()
        if k in (ord("?"), ord("q"), 27, ord("\n")):
            break


def _goto_dialog(stdscr, height: int, width: int, total_msgs: int) -> int | None:
    """Show a goto dialog, return 0-based message index or None if cancelled."""
    prompt = f"Go to message (1-{total_msgs}): "
    box_w = min(len(prompt) + 12, width - 4)
    box_h = 5
    start_y = (height - box_h) // 2
    start_x = (width - box_w) // 2
    input_buf = ""

    while True:
        for row in range(box_h):
            y = start_y + row
            if row == 0:
                line = "┌" + "─" * (box_w - 2) + "┐"
            elif row == box_h - 1:
                line = "└" + "─" * (box_w - 2) + "┘"
            elif row == 2:
                inner = f"{prompt}{input_buf}"
                inner = inner[:box_w - 4]
                line = "│ " + inner.ljust(box_w - 4) + " │"
            else:
                line = "│" + " " * (box_w - 2) + "│"
            try:
                stdscr.addnstr(y, start_x, line, box_w,
                               curses.color_pair(CP_HELP_BAR) | curses.A_BOLD)
            except curses.error:
                pass

        # Show cursor at input position
        cursor_x = start_x + 2 + len(prompt) + len(input_buf)
        if cursor_x < start_x + box_w - 2:
            try:
                curses.curs_set(1)
                stdscr.move(start_y + 2, cursor_x)
            except curses.error:
                pass

        stdscr.refresh()
        k = stdscr.getch()

        if k == 27:  # Esc
            curses.curs_set(0)
            return None
        elif k in (ord("\n"), curses.KEY_ENTER):
            curses.curs_set(0)
            try:
                num = int(input_buf)
                if 1 <= num <= total_msgs:
                    return num - 1
            except ValueError:
                pass
            return None
        elif k in (curses.KEY_BACKSPACE, 127, 8):
            input_buf = input_buf[:-1]
        elif 0 <= k <= 255 and chr(k).isdigit():
            input_buf += chr(k)


def _search_dialog(stdscr, height: int, width: int) -> str | None:
    """Show a search input dialog, return query or None if cancelled."""
    prompt = "Search: "
    box_w = min(60, width - 4)
    box_h = 5
    start_y = (height - box_h) // 2
    start_x = (width - box_w) // 2
    input_buf = ""

    while True:
        for row in range(box_h):
            y = start_y + row
            if row == 0:
                line = "┌" + "─" * (box_w - 2) + "┐"
            elif row == box_h - 1:
                line = "└" + "─" * (box_w - 2) + "┘"
            elif row == 2:
                inner = f"{prompt}{input_buf}"
                inner = inner[:box_w - 4]
                line = "│ " + inner.ljust(box_w - 4) + " │"
            else:
                line = "│" + " " * (box_w - 2) + "│"
            try:
                stdscr.addnstr(y, start_x, line, box_w,
                               curses.color_pair(CP_HELP_BAR) | curses.A_BOLD)
            except curses.error:
                pass

        cursor_x = start_x + 2 + len(prompt) + len(input_buf)
        if cursor_x < start_x + box_w - 2:
            try:
                curses.curs_set(1)
                stdscr.move(start_y + 2, cursor_x)
            except curses.error:
                pass

        stdscr.refresh()
        k = stdscr.getch()

        if k == 27:
            curses.curs_set(0)
            return None
        elif k in (ord("\n"), curses.KEY_ENTER):
            curses.curs_set(0)
            return input_buf if input_buf else None
        elif k in (curses.KEY_BACKSPACE, 127, 8):
            input_buf = input_buf[:-1]
        elif 32 <= k <= 126:
            input_buf += chr(k)


def _find_search_matches(messages: list[Message], query: str) -> list[int]:
    """Return 0-based message indices whose active swipe body matches query (case-insensitive)."""
    q = query.lower()
    return [i for i, m in enumerate(messages)
            if q in m.swipes[m.active_swipe].text.lower()]


def main(stdscr, chat: Chat):
    curses.curs_set(0)
    init_colors()
    curses.mousemask(curses.ALL_MOUSE_EVENTS | curses.REPORT_MOUSE_POSITION)
    stdscr.timeout(-1)
    stdscr.keypad(True)
    messages = chat.messages

    expanded_reasoning: set[int] = set()
    scroll_pos = 0
    cursor_msg = 0

    rendered: list[RenderedLine] = []
    line_to_msg: list[int] = []
    needs_rerender = True
    needs_clear = True
    scroll_to_cursor = False
    scroll_to_search: str | None = None  # if set, scroll to first line matching this query

    # Search state
    search_mode = False
    search_query = ""
    search_matches: list[int] = []
    search_idx = 0

    while True:
        height, width = stdscr.getmaxyx()

        if needs_rerender:
            rendered = render_messages(messages, width, expanded_reasoning, cursor_msg)
            line_to_msg = [rl.msg_idx for rl in rendered]
            needs_rerender = False
            needs_clear = True

        # Determine if we need a sticky header (1 row for title, maybe 1 for sticky)
        show_sticky = not _is_header_visible(cursor_msg, scroll_pos,
                                              height - 2, rendered)  # rough check before final layout
        header_rows = 2 if show_sticky else 1  # title bar + optional sticky
        viewable = height - 1 - header_rows  # minus help bar and header rows

        total = len(rendered)
        max_scroll = max(0, total - viewable)

        if scroll_to_cursor:
            if scroll_to_search:
                scroll_pos = _scroll_to_match(cursor_msg, scroll_to_search,
                                              rendered, line_to_msg, viewable, max_scroll)
                scroll_to_search = None
            else:
                scroll_pos = _scroll_to_msg(cursor_msg, rendered, line_to_msg,
                                            scroll_pos, viewable, max_scroll)
            scroll_to_cursor = False
            # Recheck sticky after scroll adjustment
            show_sticky = not _is_header_visible(cursor_msg, scroll_pos,
                                                  viewable, rendered)
            header_rows = 2 if show_sticky else 1
            viewable = height - 1 - header_rows
            max_scroll = max(0, total - viewable)

        scroll_pos = max(0, min(scroll_pos, max_scroll))

        if needs_clear:
            stdscr.clear()
            needs_clear = False
        else:
            stdscr.erase()

        # Row 0: title bar
        _draw_title_bar(stdscr, 0, width, chat, cursor_msg, len(messages))

        # Row 1: sticky header (if needed)
        if show_sticky and 0 <= cursor_msg < len(messages):
            _draw_sticky_header(stdscr, 1, width, messages[cursor_msg], cursor_msg + 1)

        # Content area
        content_start_row = header_rows
        highlight_attr = curses.color_pair(CP_SEARCH_MATCH) | curses.A_BOLD
        for i in range(viewable):
            line_idx = scroll_pos + i
            if line_idx >= total:
                break
            rl = rendered[line_idx]
            attr = curses.color_pair(rl.color_pair)
            if rl.bold:
                attr |= curses.A_BOLD
            text = rl.text
            screen_row = content_start_row + i
            try:
                # Draw gutter marker
                col = 0
                if text.startswith("▌"):
                    stdscr.addstr(screen_row, 0, "▌",
                                  curses.color_pair(CP_CURSOR_MARKER) | curses.A_BOLD)
                    col = 1
                    text = text[1:]

                if search_mode and search_query and not rl.is_header:
                    _draw_with_highlights(stdscr, screen_row, col, text,
                                          width - col, attr, highlight_attr,
                                          search_query)
                else:
                    stdscr.addnstr(screen_row, col, text[:width - col],
                                   width - col, attr)
            except curses.error:
                pass

        if search_mode:
            match_pos = search_matches.index(cursor_msg) + 1 if cursor_msg in search_matches else 0
            sbar = f" SEARCH \"{search_query}\"  {match_pos}/{len(search_matches)}  n/N:next/prev  Esc:exit"
            sbar = sbar[:width].ljust(width)
            try:
                stdscr.addnstr(height - 1, 0, sbar, width,
                               curses.color_pair(CP_SWIPE_INDICATOR) | curses.A_BOLD)
            except curses.error:
                pass
        else:
            draw_help_bar(stdscr, height, width)
        stdscr.refresh()

        key = stdscr.getch()

        if search_mode:
            if key == 27:
                search_mode = False
            elif key == ord("n") and search_matches:
                search_idx = (search_idx + 1) % len(search_matches)
                cursor_msg = search_matches[search_idx]
                needs_rerender = True
                scroll_to_cursor = True
                scroll_to_search = search_query
            elif key in (ord("N"), ord("p")) and search_matches:
                search_idx = (search_idx - 1) % len(search_matches)
                cursor_msg = search_matches[search_idx]
                needs_rerender = True
                scroll_to_cursor = True
                scroll_to_search = search_query
            elif key == ord("/"):
                query = _search_dialog(stdscr, height, width)
                needs_clear = True
                if query:
                    search_query = query
                    search_matches = _find_search_matches(messages, search_query)
                    search_idx = 0
                    if search_matches:
                        cursor_msg = search_matches[0]
                        needs_rerender = True
                        scroll_to_cursor = True
                        scroll_to_search = search_query
            elif key in (curses.KEY_DOWN, ord("j")):
                scroll_pos = min(scroll_pos + 1, max_scroll)
            elif key in (curses.KEY_UP, ord("k")):
                scroll_pos = max(scroll_pos - 1, 0)
            elif key in (curses.KEY_NPAGE, ord(" ")):
                scroll_pos = min(scroll_pos + viewable, max_scroll)
            elif key == curses.KEY_PPAGE:
                scroll_pos = max(scroll_pos - viewable, 0)
            elif key == ord("q"):
                break
            continue

        if key == ord("q") or key == 27:
            break
        elif key in (curses.KEY_DOWN, ord("j"), curses.KEY_UP, ord("k"),
                     curses.KEY_NPAGE, ord(" "), curses.KEY_PPAGE):
            if key == curses.KEY_DOWN or key == ord("j"):
                scroll_pos = min(scroll_pos + 1, max_scroll)
            elif key == curses.KEY_UP or key == ord("k"):
                scroll_pos = max(scroll_pos - 1, 0)
            elif key == curses.KEY_NPAGE or key == ord(" "):
                scroll_pos = min(scroll_pos + viewable, max_scroll)
            elif key == curses.KEY_PPAGE:
                scroll_pos = max(scroll_pos - viewable, 0)

            new_cursor = _cursor_after_scroll(
                cursor_msg, scroll_pos, viewable, line_to_msg, total)
            if new_cursor != cursor_msg:
                cursor_msg = new_cursor
                needs_rerender = True
        elif key in (ord("g"), ord("G")):
            target = _goto_dialog(stdscr, height, width, len(messages))
            needs_clear = True
            if target is not None:
                cursor_msg = target
                needs_rerender = True
                scroll_to_cursor = True
        elif key == ord("n"):
            cursor_msg = min(cursor_msg + 1, len(messages) - 1)
            needs_rerender = True
            scroll_to_cursor = True
        elif key in (ord("p"), ord("N")):
            cursor_msg = max(cursor_msg - 1, 0)
            needs_rerender = True
            scroll_to_cursor = True
        elif key == ord("r"):
            if cursor_msg in expanded_reasoning:
                expanded_reasoning.discard(cursor_msg)
            else:
                expanded_reasoning.add(cursor_msg)
            needs_rerender = True
        elif key in (curses.KEY_LEFT, ord("h")):
            msg = messages[cursor_msg]
            if len(msg.swipes) > 1:
                msg.active_swipe = (msg.active_swipe - 1) % len(msg.swipes)
                needs_rerender = True
        elif key in (curses.KEY_RIGHT, ord("l")):
            msg = messages[cursor_msg]
            if len(msg.swipes) > 1:
                msg.active_swipe = (msg.active_swipe + 1) % len(msg.swipes)
                needs_rerender = True
        elif key == ord("?"):
            _draw_help_overlay(stdscr, height, width)
            needs_clear = True
        elif key == ord("/"):
            query = _search_dialog(stdscr, height, width)
            needs_clear = True
            if query:
                search_query = query
                search_matches = _find_search_matches(messages, search_query)
                search_idx = 0
                search_mode = True
                if search_matches:
                    cursor_msg = search_matches[0]
                    needs_rerender = True
                    scroll_to_cursor = True
                    scroll_to_search = search_query
        elif key == curses.KEY_MOUSE:
            try:
                _, mx, my, _, bstate = curses.getmouse()
                scroll_lines = 3
                # macOS reports scroll-down as REPORT_MOUSE_POSITION (0x8000000)
                SCROLL_DOWN = getattr(curses, "BUTTON5_PRESSED", 0) | curses.REPORT_MOUSE_POSITION
                if bstate & curses.BUTTON4_PRESSED:
                    scroll_pos = max(scroll_pos - scroll_lines, 0)
                    new_cursor = _cursor_after_scroll(
                        cursor_msg, scroll_pos, viewable, line_to_msg, total)
                    if new_cursor != cursor_msg:
                        cursor_msg = new_cursor
                        needs_rerender = True
                elif bstate & SCROLL_DOWN:
                    scroll_pos = min(scroll_pos + scroll_lines, max_scroll)
                    new_cursor = _cursor_after_scroll(
                        cursor_msg, scroll_pos, viewable, line_to_msg, total)
                    if new_cursor != cursor_msg:
                        cursor_msg = new_cursor
                        needs_rerender = True
                elif bstate & (curses.BUTTON1_CLICKED | curses.BUTTON1_PRESSED):
                    content_row = my - header_rows
                    line_idx = scroll_pos + content_row
                    if 0 <= content_row < viewable and 0 <= line_idx < len(line_to_msg):
                        clicked_msg = line_to_msg[line_idx]
                        if clicked_msg != cursor_msg:
                            cursor_msg = clicked_msg
                            needs_rerender = True
            except curses.error:
                pass
        elif key == curses.KEY_RESIZE:
            needs_rerender = True


def _cursor_after_scroll(cursor_msg: int, scroll_pos: int, viewable: int,
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
    # At extremes, snap to first/last message
    if scroll_pos == 0:
        return min(visible_msgs)
    if scroll_pos >= max_scroll:
        return max(visible_msgs)
    if cursor_msg in visible_msgs:
        return cursor_msg
    if cursor_msg < min(visible_msgs):
        return min(visible_msgs)
    return max(visible_msgs)


def _scroll_to_msg(msg_idx: int, rendered: list[RenderedLine],
                   line_to_msg: list[int], scroll_pos: int,
                   viewable: int, max_scroll: int) -> int:
    """Return scroll position that puts the start of msg_idx on screen."""
    for i, mid in enumerate(line_to_msg):
        if mid == msg_idx:
            return max(0, min(i - 1, max_scroll))
    return scroll_pos


def _scroll_to_match(msg_idx: int, query: str, rendered: list[RenderedLine],
                     line_to_msg: list[int], viewable: int, max_scroll: int) -> int:
    """Scroll so the first line in msg_idx containing query is visible."""
    q = query.lower()
    for i, rl in enumerate(rendered):
        if rl.msg_idx == msg_idx and not rl.is_header and q in rl.text.lower():
            target = max(0, i - viewable // 3)
            return max(0, min(target, max_scroll))
    # Fallback: scroll to message start
    for i, mid in enumerate(line_to_msg):
        if mid == msg_idx:
            return max(0, min(i - 1, max_scroll))
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="SillyTavern JSONL chat viewer")
    parser.add_argument("file", help="Path to .jsonl chat export")
    args = parser.parse_args()

    try:
        chat = parse_chat(args.file)
    except Exception as e:
        print(f"Error loading {args.file}: {e}", file=sys.stderr)
        sys.exit(1)

    if not chat.messages:
        print("No messages found.", file=sys.stderr)
        sys.exit(1)

    print(f"Loaded {len(chat.messages)} messages. Launching viewer...")
    curses.wrapper(lambda stdscr: main(stdscr, chat))
