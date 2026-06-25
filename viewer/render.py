"""Pre-render messages into flat line lists for display."""

import textwrap

from .colors import CP_CHAR_NAME, CP_REASONING, CP_SEPARATOR, CP_SYSTEM_NAME, CP_USER_NAME
from .models import Message, RenderedLine, Swipe
from .parser import _format_time


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
