#!/usr/bin/env python3
"""TUI viewer for SillyTavern JSONL chat exports."""

import argparse
import curses
import json
import sys
import textwrap
from dataclasses import dataclass, field


@dataclass
class Swipe:
    text: str
    reasoning: str


@dataclass
class Message:
    name: str
    is_user: bool
    is_system: bool
    timestamp: str
    swipes: list[Swipe] = field(default_factory=list)
    active_swipe: int = 0


def parse_chat(path: str) -> list[Message]:
    messages = []
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

            # The main message text / reasoning
            main_text = obj.get("mes", "")
            main_reasoning = obj.get("extra", {}).get("reasoning", "") or ""

            if swipe_texts:
                swipes = []
                for j, st in enumerate(swipe_texts):
                    reasoning = ""
                    if j < len(swipe_infos):
                        reasoning = swipe_infos[j].get("extra", {}).get("reasoning", "") or ""
                    elif j == active_swipe:
                        reasoning = main_reasoning
                    swipes.append(Swipe(text=st, reasoning=reasoning))
            else:
                swipes = [Swipe(text=main_text, reasoning=main_reasoning)]

            messages.append(Message(
                name=name,
                is_user=is_user,
                is_system=is_system,
                timestamp=timestamp,
                swipes=swipes,
                active_swipe=active_swipe,
            ))
    return messages


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


@dataclass
class RenderedLine:
    """A single screen line with its color pair."""
    text: str
    color_pair: int = 0
    bold: bool = False


def render_messages(messages: list[Message], width: int, expanded_reasoning: set[int],
                    cursor_msg: int = -1) -> list[RenderedLine]:
    """Pre-render all messages into wrapped lines for the given terminal width."""
    lines: list[RenderedLine] = []
    # Reserve 2 columns for the cursor gutter ("▌ " for active, "  " otherwise)
    gutter = 2
    content_width = max(width - gutter - 1, 20)

    for idx, msg in enumerate(messages):
        is_active = idx == cursor_msg
        prefix = "▌ " if is_active else "  "

        if idx > 0:
            lines.append(RenderedLine("─" * width, CP_SEPARATOR))

        # Name header
        if msg.is_system:
            name_cp = CP_SYSTEM_NAME
        elif msg.is_user:
            name_cp = CP_USER_NAME
        else:
            name_cp = CP_CHAR_NAME

        swipe = msg.swipes[msg.active_swipe] if msg.swipes else Swipe("", "")
        header = f"{prefix}{msg.name}"
        if len(msg.swipes) > 1:
            header += f"  [{msg.active_swipe + 1}/{len(msg.swipes)}]"
        if msg.timestamp:
            ts = msg.timestamp
            if ts.endswith("Z"):
                ts = ts[:-1]
            header += f"  {ts}"

        lines.append(RenderedLine(header, name_cp, bold=True))

        # Reasoning (collapsible) — only shown when expanded
        if swipe.reasoning and idx in expanded_reasoning:
            lines.append(RenderedLine(f"{prefix}▼ Reasoning:", CP_REASONING, bold=True))
            for para in swipe.reasoning.split("\n"):
                if not para.strip():
                    lines.append(RenderedLine(prefix, CP_REASONING))
                    continue
                for wl in textwrap.wrap(para, content_width - 4):
                    lines.append(RenderedLine(f"{prefix}  │ {wl}", CP_REASONING))
            lines.append(RenderedLine(prefix, 0))

        # Message body
        for para in swipe.text.split("\n"):
            if not para.strip():
                lines.append(RenderedLine(prefix, 0))
                continue
            for wl in textwrap.wrap(para, content_width):
                lines.append(RenderedLine(f"{prefix}{wl}", 0))

        lines.append(RenderedLine(prefix, 0))

    return lines


def draw_help_bar(stdscr, height, width, scroll_pos, total_lines, viewable):
    pct = 0 if total_lines <= viewable else int(100 * scroll_pos / (total_lines - viewable))
    bar = f" ↑↓/PgUp/PgDn:scroll  r:toggle reasoning  </> or h/l:swipe  g/G:top/bottom  q:quit  [{pct}%]"
    bar = bar[:width].ljust(width)
    try:
        stdscr.addnstr(height - 1, 0, bar, width, curses.color_pair(CP_HELP_BAR))
    except curses.error:
        pass


def main(stdscr, messages: list[Message]):
    curses.curs_set(0)
    init_colors()
    stdscr.timeout(-1)

    expanded_reasoning: set[int] = set()
    scroll_pos = 0
    # Which message index the cursor is on (for toggling reasoning / swipes)
    cursor_msg = 0

    rendered: list[RenderedLine] = []
    # Map from rendered line index -> message index
    line_to_msg: list[int] = []
    needs_rerender = True
    scroll_to_cursor = False

    while True:
        height, width = stdscr.getmaxyx()
        viewable = height - 1  # bottom row is help bar

        if needs_rerender:
            rendered = render_messages(messages, width, expanded_reasoning, cursor_msg)
            # Build line->message mapping
            line_to_msg = []
            msg_idx = -1
            for rl in rendered:
                # Detect message boundaries by separator lines
                if rl.color_pair == CP_SEPARATOR:
                    msg_idx += 1
                elif msg_idx == -1:
                    msg_idx = 0
                line_to_msg.append(msg_idx)
            needs_rerender = False

        total = len(rendered)
        max_scroll = max(0, total - viewable)

        if scroll_to_cursor:
            scroll_pos = _scroll_to_msg(cursor_msg, messages, rendered, line_to_msg, scroll_pos, viewable, max_scroll)
            scroll_to_cursor = False
        scroll_pos = max(0, min(scroll_pos, max_scroll))

        stdscr.erase()

        for i in range(viewable):
            line_idx = scroll_pos + i
            if line_idx >= total:
                break
            rl = rendered[line_idx]
            attr = curses.color_pair(rl.color_pair)
            if rl.bold:
                attr |= curses.A_BOLD
            text = rl.text
            try:
                # Draw the gutter marker ("▌") in yellow if present
                if text.startswith("▌"):
                    stdscr.addstr(i, 0, "▌", curses.color_pair(CP_CURSOR_MARKER) | curses.A_BOLD)
                    stdscr.addnstr(i, 1, text[1:width], width - 1, attr)
                else:
                    stdscr.addnstr(i, 0, text[:width], width, attr)
            except curses.error:
                pass

        draw_help_bar(stdscr, height, width, scroll_pos, total, viewable)
        stdscr.refresh()

        key = stdscr.getch()
        if key == ord("q") or key == 27:  # q or Esc
            break
        elif key in (curses.KEY_DOWN, ord("j"), curses.KEY_UP, ord("k"),
                     curses.KEY_NPAGE, ord(" "), curses.KEY_PPAGE,
                     ord("g"), ord("G")):
            if key == curses.KEY_DOWN or key == ord("j"):
                scroll_pos = min(scroll_pos + 1, max_scroll)
            elif key == curses.KEY_UP or key == ord("k"):
                scroll_pos = max(scroll_pos - 1, 0)
            elif key == curses.KEY_NPAGE or key == ord(" "):
                scroll_pos = min(scroll_pos + viewable, max_scroll)
            elif key == curses.KEY_PPAGE:
                scroll_pos = max(scroll_pos - viewable, 0)
            elif key == ord("g"):
                scroll_pos = 0
            elif key == ord("G"):
                scroll_pos = max_scroll

            new_cursor = _cursor_after_scroll(
                cursor_msg, scroll_pos, viewable, line_to_msg, total)
            if new_cursor != cursor_msg:
                cursor_msg = new_cursor
                needs_rerender = True
        elif key == ord("n"):
            # Next message
            cursor_msg = min(cursor_msg + 1, len(messages) - 1)
            needs_rerender = True
            scroll_to_cursor = True
        elif key == ord("p"):
            # Previous message
            cursor_msg = max(cursor_msg - 1, 0)
            needs_rerender = True
            scroll_to_cursor = True
        elif key == ord("r"):
            if cursor_msg in expanded_reasoning:
                expanded_reasoning.discard(cursor_msg)
            else:
                expanded_reasoning.add(cursor_msg)
            needs_rerender = True
        elif key in (ord("<"), ord(","), ord("h")):
            msg = messages[cursor_msg]
            if len(msg.swipes) > 1:
                msg.active_swipe = (msg.active_swipe - 1) % len(msg.swipes)
                needs_rerender = True
        elif key in (ord(">"), ord("."), ord("l")):
            msg = messages[cursor_msg]
            if len(msg.swipes) > 1:
                msg.active_swipe = (msg.active_swipe + 1) % len(msg.swipes)
                needs_rerender = True
        elif key == curses.KEY_RESIZE:
            needs_rerender = True


def _cursor_after_scroll(cursor_msg: int, scroll_pos: int, viewable: int,
                         line_to_msg: list[int], total: int) -> int:
    """If cursor_msg is fully off-screen, move it to the first/last visible message."""
    visible_end = min(scroll_pos + viewable, total)
    visible_msgs = set()
    for i in range(scroll_pos, visible_end):
        if i < len(line_to_msg):
            visible_msgs.add(line_to_msg[i])
    if cursor_msg in visible_msgs:
        return cursor_msg
    # Fully off-screen — snap to the nearest visible message
    if not visible_msgs:
        return cursor_msg
    if cursor_msg < min(visible_msgs):
        return min(visible_msgs)
    return max(visible_msgs)


def _scroll_to_msg(msg_idx: int, messages: list[Message], rendered: list[RenderedLine],
                   line_to_msg: list[int], scroll_pos: int, viewable: int, max_scroll: int) -> int:
    """Return scroll position that puts the start of msg_idx on screen."""
    for i, mid in enumerate(line_to_msg):
        if mid == msg_idx:
            return max(0, min(i - 1, max_scroll))
    return scroll_pos


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="SillyTavern JSONL chat viewer")
    parser.add_argument("file", help="Path to .jsonl chat export")
    args = parser.parse_args()

    try:
        messages = parse_chat(args.file)
    except Exception as e:
        print(f"Error loading {args.file}: {e}", file=sys.stderr)
        sys.exit(1)

    if not messages:
        print("No messages found.", file=sys.stderr)
        sys.exit(1)

    print(f"Loaded {len(messages)} messages. Launching viewer...")
    curses.wrapper(lambda stdscr: main(stdscr, messages))
