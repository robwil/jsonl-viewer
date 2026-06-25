"""Textual TUI application for the chat viewer."""

from __future__ import annotations

import textwrap

from textual.app import App, ComposeResult
from textual.containers import Vertical, VerticalScroll
from textual.events import Key
from textual.message import Message as TMessage
from textual.reactive import reactive
from textual.screen import ModalScreen
from textual.widgets import Input, Label, Static
from rich.console import Group
from rich.rule import Rule
from rich.text import Text

from .models import Chat, Message, Swipe
from .parser import _format_time
from .state import find_search_matches


HELP_TEXT = """\
Keybindings

  ↑ / k          Scroll up one line
  ↓ / j          Scroll down one line
  PgUp            Scroll up one page
  PgDn / Space    Scroll down one page
  g / G           Go to message by ID

  n               Next message
  N / p           Previous message

  ← / h           Previous swipe
  → / l           Next swipe

  r               Toggle reasoning

  /               Search message text
                  n/N to navigate results

  q / Esc         Quit
  ?               This help"""


# ---------------------------------------------------------------------------
# Widgets
# ---------------------------------------------------------------------------

class TitleBar(Static):
    """Top bar with chat title, date, and progress."""

    def __init__(self, chat: Chat, **kwargs) -> None:
        super().__init__(**kwargs)
        self.chat = chat
        self._cursor_msg = 0

    def update_cursor(self, cursor_msg: int) -> None:
        self._cursor_msg = cursor_msg
        self.refresh()

    def render(self) -> Text:
        width = max(self.size.width, 20)
        total = len(self.chat.messages)
        msg_num = self._cursor_msg + 1
        pct = int(100 * msg_num / total) if total else 0

        left = f" {self.chat.title}"
        if self.chat.date:
            left += f"  {self.chat.date}"
        right = f" {msg_num} / {total} ({pct}%) "

        full = left.ljust(max(1, width - len(right))) + right
        full = full[:width].ljust(width)

        result = Text(full)
        filled = int(width * pct / 100) if total else 0
        if filled > 0:
            result.stylize("black on dark_cyan", 0, filled)
        if filled < width:
            result.stylize("white on rgb(40,40,40)", filled, width)
        return result


class StickyHeader(Static):
    """Shows the current message header when its real header scrolls off-screen."""

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._msg: Message | None = None
        self._idx = 0

    def set_message(self, msg: Message, idx: int) -> None:
        self._msg = msg
        self._idx = idx
        self.refresh()

    def render(self) -> Text:
        if self._msg is None:
            return Text("")
        msg = self._msg
        swipe = msg.swipes[msg.active_swipe] if msg.swipes else Swipe("", "")
        style = "bold green" if msg.is_user else ("bold yellow" if msg.is_system else "bold cyan")

        parts = [f"▌ #{self._idx + 1} {msg.name}"]
        if len(msg.swipes) > 1:
            parts.append(f"[{msg.active_swipe + 1}/{len(msg.swipes)}]")
        time_str = _format_time(msg.timestamp)
        if time_str:
            parts.append(time_str)
        if swipe.model:
            short = swipe.model.split("/")[-1] if "/" in swipe.model else swipe.model
            parts.append(short)
        if swipe.token_count:
            parts.append(f"{swipe.token_count}tok")
        if swipe.gen_seconds > 0:
            parts.append(f"{swipe.gen_seconds:.1f}s")

        width = max(self.size.width, 20)
        header = "  ".join(parts)
        result = Text(header.ljust(width)[:width], style=f"{style} reverse")
        result.stylize("bold yellow", 0, 1)
        return result


class StatusBar(Static):
    """Bottom bar showing keybinding hints or search info."""

    NORMAL_TEXT = " ↑↓:scroll  n/N:msg  ←→:swipe  r:reasoning  /:search  g:goto  q:quit  ?:help"

    def set_search(self, query: str, match_pos: int, total_matches: int) -> None:
        text = f' SEARCH "{query}"  {match_pos}/{total_matches}  n/N:next/prev  Esc:exit'
        self.update(Text(text, style="bold yellow"))

    def set_normal(self) -> None:
        self.update(Text(self.NORMAL_TEXT, style="black on white"))


class MessageWidget(Static):
    """Displays a single chat message with header, optional reasoning, and body."""

    selected: reactive[bool] = reactive(False)
    show_reasoning: reactive[bool] = reactive(False)
    search_query: reactive[str] = reactive("")

    class Clicked(TMessage):
        def __init__(self, idx: int) -> None:
            super().__init__()
            self.idx = idx

    def __init__(self, msg: Message, idx: int, **kwargs) -> None:
        super().__init__(**kwargs, id=f"msg-{idx}")
        self.msg = msg
        self.idx = idx
        self._cached_render: Text | Group | None = None
        self._cache_key: tuple | None = None

    def _invalidate_cache(self) -> None:
        self._cached_render = None
        self._cache_key = None

    def watch_selected(self, value: bool) -> None:
        if value:
            self.add_class("selected")
        else:
            self.remove_class("selected")
        self._invalidate_cache()

    def watch_show_reasoning(self, value: bool) -> None:
        self._invalidate_cache()

    def watch_search_query(self, value: str) -> None:
        self._invalidate_cache()

    def on_click(self) -> None:
        self.post_message(self.Clicked(self.idx))

    def invalidate_content(self) -> None:
        """Call after swipe changes to force re-render."""
        self._invalidate_cache()
        self.refresh()

    def render(self) -> Text | Group:
        cache_key = (
            self.selected, self.show_reasoning, self.search_query,
            self.msg.active_swipe, self.size.width,
        )
        if self._cached_render is not None and self._cache_key == cache_key:
            return self._cached_render

        result = self._build_content()
        self._cached_render = result
        self._cache_key = cache_key
        return result

    def _build_content(self) -> Text | Group:
        msg = self.msg
        swipe = msg.swipes[msg.active_swipe] if msg.swipes else Swipe("", "")
        content = Text()

        prefix = "▌ " if self.selected else "  "

        # Header
        style = "bold green" if msg.is_user else ("bold yellow" if msg.is_system else "bold cyan")
        parts = [f"{prefix}#{self.idx + 1} {msg.name}"]

        if len(msg.swipes) > 1:
            parts.append(f"[{msg.active_swipe + 1}/{len(msg.swipes)}]")

        time_str = _format_time(msg.timestamp)
        if time_str:
            parts.append(time_str)

        if swipe.model:
            short = swipe.model.split("/")[-1] if "/" in swipe.model else swipe.model
            parts.append(short)

        if swipe.token_count:
            parts.append(f"{swipe.token_count}tok")

        if swipe.gen_seconds > 0:
            parts.append(f"{swipe.gen_seconds:.1f}s")

        content.append("  ".join(parts), style=style)

        # Wrap width: widget width minus gutter, with a sane minimum
        gutter = 2
        wrap_width = max(self.size.width - gutter - 1, 20)

        # Reasoning (collapsible)
        reasoning_prefix = f"{prefix}  │ "
        reasoning_wrap = max(wrap_width - len(reasoning_prefix) + len(prefix), 20)
        if swipe.reasoning and self.show_reasoning:
            content.append(f"\n{prefix}▼ Reasoning:", style="bold magenta")
            for para in swipe.reasoning.split("\n"):
                if not para.strip():
                    content.append(f"\n{prefix}", style="magenta")
                    continue
                for wl in textwrap.wrap(para, reasoning_wrap):
                    content.append(f"\n{reasoning_prefix}{wl}", style="magenta")

        # Body — wrap each paragraph so every line gets the gutter prefix
        for para in swipe.text.split("\n"):
            if not para.strip():
                content.append(f"\n{prefix}")
                continue
            for wl in textwrap.wrap(para, wrap_width):
                content.append(f"\n{prefix}{wl}")

        # Search highlights
        if self.search_query:
            content.highlight_words(
                [self.search_query], style="bold red", case_sensitive=False
            )

        if self.idx > 0:
            return Group(Rule(style="dim"), content)
        return content


# ---------------------------------------------------------------------------
# Modal screens
# ---------------------------------------------------------------------------

class SearchScreen(ModalScreen[str | None]):
    CSS = """
    SearchScreen { align: center middle; }
    #search-dialog {
        width: 60;
        height: auto;
        border: solid $accent;
        background: $surface;
        padding: 1 2;
    }
    """

    def compose(self) -> ComposeResult:
        with Vertical(id="search-dialog"):
            yield Label("Search:")
            yield Input(placeholder="Enter search query...")

    def on_input_submitted(self, event: Input.Submitted) -> None:
        self.dismiss(event.value if event.value else None)

    def on_key(self, event: Key) -> None:
        if event.key == "escape":
            self.dismiss(None)
            event.stop()


class GotoScreen(ModalScreen[int | None]):
    CSS = """
    GotoScreen { align: center middle; }
    #goto-dialog {
        width: 50;
        height: auto;
        border: solid $accent;
        background: $surface;
        padding: 1 2;
    }
    """

    def __init__(self, total: int) -> None:
        super().__init__()
        self.total = total

    def compose(self) -> ComposeResult:
        with Vertical(id="goto-dialog"):
            yield Label(f"Go to message (1-{self.total}):")
            yield Input(restrict=r"\d*", placeholder="Message number...")

    def on_input_submitted(self, event: Input.Submitted) -> None:
        try:
            num = int(event.value)
            if 1 <= num <= self.total:
                self.dismiss(num - 1)
                return
        except (ValueError, TypeError):
            pass
        self.dismiss(None)

    def on_key(self, event: Key) -> None:
        if event.key == "escape":
            self.dismiss(None)
            event.stop()


class HelpScreen(ModalScreen):
    CSS = """
    HelpScreen { align: center middle; }
    #help-dialog {
        width: 52;
        height: auto;
        max-height: 90%;
        border: solid $accent;
        background: $surface;
        padding: 1 2;
    }
    """

    def compose(self) -> ComposeResult:
        with Vertical(id="help-dialog"):
            yield Static(HELP_TEXT)

    def on_key(self, event: Key) -> None:
        self.dismiss()
        event.stop()


# ---------------------------------------------------------------------------
# Main application
# ---------------------------------------------------------------------------

class ChatViewerApp(App):
    CSS = """
    Screen { background: $surface; }
    #title-bar { dock: top; width: 100%; height: 1; }
    #sticky-header { width: 100%; height: 0; }
    #sticky-header.visible { height: 1; }
    #status-bar { dock: bottom; width: 100%; height: 1; }
    #messages { width: 100%; }
    """

    def __init__(self, chat: Chat, **kwargs) -> None:
        super().__init__(**kwargs)
        self.chat = chat
        self.cursor_msg = 0
        self.expanded_reasoning: set[int] = set()
        self.search_mode = False
        self.search_query = ""
        self.search_matches: list[int] = []
        self.search_idx = 0

    def compose(self) -> ComposeResult:
        yield TitleBar(self.chat, id="title-bar")
        yield StickyHeader(id="sticky-header")
        yield VerticalScroll(id="messages")
        yield StatusBar(id="status-bar")

    def on_mount(self) -> None:
        container = self.query_one("#messages", VerticalScroll)
        for i, msg in enumerate(self.chat.messages):
            container.mount(MessageWidget(msg, i))
        self._select_message(0)
        self.query_one("#status-bar", StatusBar).set_normal()

    # --- Event handlers ---

    def on_key(self, event: Key) -> None:
        if self.search_mode:
            handled = self._handle_search_key(event)
        else:
            handled = self._handle_normal_key(event)
        if handled:
            event.prevent_default()
            event.stop()

    def on_message_widget_clicked(self, event: MessageWidget.Clicked) -> None:
        self._select_message(event.idx)

    # --- Key dispatch ---

    def _handle_scroll_key(self, event: Key) -> bool:
        char = event.character or ""
        key = event.key
        container = self.query_one("#messages", VerticalScroll)

        if char == "j" or key == "down":
            container.scroll_down(animate=False)
        elif char == "k" or key == "up":
            container.scroll_up(animate=False)
        elif key == "pagedown" or char == " ":
            container.scroll_page_down(animate=False)
        elif key == "pageup":
            container.scroll_page_up(animate=False)
        else:
            return False

        self._update_sticky_header()
        self.set_timer(0.05, self._snap_cursor_to_viewport)
        return True

    def _handle_normal_key(self, event: Key) -> bool:
        char = event.character or ""
        key = event.key

        if char == "q" or key == "escape":
            self.exit()
            return True

        if self._handle_scroll_key(event):
            return True

        if char == "n":
            self._select_message(min(self.cursor_msg + 1, len(self.chat.messages) - 1))
            return True
        if char in ("N", "p"):
            self._select_message(max(self.cursor_msg - 1, 0))
            return True
        if char == "h" or key == "left":
            self._toggle_swipe(-1)
            return True
        if char == "l" or key == "right":
            self._toggle_swipe(1)
            return True
        if char == "r":
            self._toggle_reasoning()
            return True
        if char == "/":
            self.push_screen(SearchScreen(), callback=self._on_search_result)
            return True
        if char in ("g", "G"):
            self.push_screen(
                GotoScreen(len(self.chat.messages)), callback=self._on_goto_result
            )
            return True
        if char == "?":
            self.push_screen(HelpScreen())
            return True
        return False

    def _handle_search_key(self, event: Key) -> bool:
        char = event.character or ""
        key = event.key

        if key == "escape":
            self.search_mode = False
            self._clear_search_highlights()
            self._update_status_bar()
            return True
        if char == "n" and self.search_matches:
            self.search_idx = (self.search_idx + 1) % len(self.search_matches)
            self._select_message(self.search_matches[self.search_idx])
            self._update_status_bar()
            return True
        if char in ("N", "p") and self.search_matches:
            self.search_idx = (self.search_idx - 1) % len(self.search_matches)
            self._select_message(self.search_matches[self.search_idx])
            self._update_status_bar()
            return True
        if char == "/":
            self.push_screen(SearchScreen(), callback=self._on_search_result)
            return True
        if char == "q":
            self.exit()
            return True
        return self._handle_scroll_key(event)

    # --- Actions ---

    def _is_widget_in_viewport(self, widget: MessageWidget, container: VerticalScroll) -> bool:
        """Check if any part of a message widget is visible in the scroll viewport."""
        scroll_y = container.scroll_offset.y
        vp_height = container.size.height
        # widget.virtual_region gives position in the scrollable content space
        wy = widget.virtual_region.y
        wh = widget.virtual_region.height
        return wy + wh > scroll_y and wy < scroll_y + vp_height

    def _update_sticky_header(self) -> None:
        """Show/hide the sticky header based on whether the current message's header is off-screen."""
        container = self.query_one("#messages", VerticalScroll)
        sticky = self.query_one("#sticky-header", StickyHeader)
        widget = self.query_one(f"#msg-{self.cursor_msg}", MessageWidget)

        scroll_y = container.scroll_offset.y
        header_y = widget.virtual_region.y
        # The separator Rule above non-first messages takes 1 row before the header
        header_y_effective = header_y + (1 if self.cursor_msg > 0 else 0)

        if header_y_effective < scroll_y:
            sticky.set_message(self.chat.messages[self.cursor_msg], self.cursor_msg)
            sticky.add_class("visible")
        else:
            sticky.remove_class("visible")

    def _snap_cursor_to_viewport(self) -> None:
        """If the selected message is off-screen, snap cursor to the nearest visible one."""
        container = self.query_one("#messages", VerticalScroll)

        current = self.query_one(f"#msg-{self.cursor_msg}", MessageWidget)
        if self._is_widget_in_viewport(current, container):
            self._update_sticky_header()
            return

        # Search outward from cursor to find the nearest visible message
        n = len(self.chat.messages)
        lo = self.cursor_msg - 1
        hi = self.cursor_msg + 1
        while lo >= 0 or hi < n:
            if hi < n:
                w = self.query_one(f"#msg-{hi}", MessageWidget)
                if self._is_widget_in_viewport(w, container):
                    self._move_cursor(hi)
                    return
                hi += 1
            if lo >= 0:
                w = self.query_one(f"#msg-{lo}", MessageWidget)
                if self._is_widget_in_viewport(w, container):
                    self._move_cursor(lo)
                    return
                lo -= 1

    def _move_cursor(self, idx: int) -> None:
        """Move the cursor marker without scrolling the viewport."""
        if idx == self.cursor_msg:
            return
        old_widget = self.query_one(f"#msg-{self.cursor_msg}", MessageWidget)
        old_widget.selected = False
        self.cursor_msg = idx
        new_widget = self.query_one(f"#msg-{idx}", MessageWidget)
        new_widget.selected = True
        self.query_one("#title-bar", TitleBar).update_cursor(idx)
        self._update_sticky_header()

    def _select_message(self, idx: int) -> None:
        old = self.cursor_msg
        self.cursor_msg = idx

        if old != idx:
            try:
                old_widget = self.query_one(f"#msg-{old}", MessageWidget)
                old_widget.selected = False
            except Exception:
                pass

        widget = self.query_one(f"#msg-{idx}", MessageWidget)
        widget.selected = True
        widget.scroll_visible(animate=False)
        self.query_one("#title-bar", TitleBar).update_cursor(idx)
        self._update_sticky_header()

    def _toggle_swipe(self, direction: int) -> None:
        msg = self.chat.messages[self.cursor_msg]
        if len(msg.swipes) > 1:
            msg.active_swipe = (msg.active_swipe + direction) % len(msg.swipes)
            widget = self.query_one(f"#msg-{self.cursor_msg}", MessageWidget)
            widget.invalidate_content()
            self.query_one("#title-bar", TitleBar).update_cursor(self.cursor_msg)

    def _toggle_reasoning(self) -> None:
        widget = self.query_one(f"#msg-{self.cursor_msg}", MessageWidget)
        if self.cursor_msg in self.expanded_reasoning:
            self.expanded_reasoning.discard(self.cursor_msg)
            widget.show_reasoning = False
        else:
            self.expanded_reasoning.add(self.cursor_msg)
            widget.show_reasoning = True

    def _start_search(self, query: str) -> None:
        self.search_query = query
        self.search_matches = find_search_matches(self.chat.messages, query)
        self.search_idx = 0
        self.search_mode = True

        for i in range(len(self.chat.messages)):
            self.query_one(f"#msg-{i}", MessageWidget).search_query = query

        if self.search_matches:
            self._select_message(self.search_matches[0])
        self._update_status_bar()

    def _clear_search_highlights(self) -> None:
        for i in range(len(self.chat.messages)):
            self.query_one(f"#msg-{i}", MessageWidget).search_query = ""

    def _update_status_bar(self) -> None:
        bar = self.query_one("#status-bar", StatusBar)
        if self.search_mode:
            match_pos = (
                self.search_matches.index(self.cursor_msg) + 1
                if self.cursor_msg in self.search_matches
                else 0
            )
            bar.set_search(self.search_query, match_pos, len(self.search_matches))
        else:
            bar.set_normal()

    # --- Callbacks ---

    def _on_search_result(self, query: str | None) -> None:
        if query:
            self._start_search(query)

    def _on_goto_result(self, idx: int | None) -> None:
        if idx is not None:
            self._select_message(idx)


def main(chat: Chat) -> None:
    app = ChatViewerApp(chat)
    app.run()
