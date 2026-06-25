"""Unit tests for rendering functions."""

from viewer.models import Message, RenderedLine, Swipe
from viewer.render import _build_header_text, _name_color, render_messages
from viewer.colors import CP_CHAR_NAME, CP_REASONING, CP_SEPARATOR, CP_USER_NAME


def _msg(name="Bob", is_user=False, is_system=False, text="Hello",
         model="", tokens=0, gen_secs=0.0, reasoning="",
         n_swipes=1, timestamp="2026-06-24T03:12:00.000Z") -> Message:
    swipes = [Swipe(text=text, reasoning=reasoning, model=model,
                    token_count=tokens, gen_seconds=gen_secs)]
    for i in range(1, n_swipes):
        swipes.append(Swipe(text=f"Swipe {i}", reasoning="", model=model))
    return Message(name=name, is_user=is_user, is_system=is_system,
                   timestamp=timestamp, swipes=swipes, active_swipe=0)


class TestBuildHeaderText:
    def test_basic_header(self):
        msg = _msg(name="Bob")
        header = _build_header_text(msg, "  ", msg_id=1)
        assert "#1 Bob" in header

    def test_header_with_model(self):
        msg = _msg(name="Bob", model="openai/gpt-4")
        header = _build_header_text(msg, "  ", msg_id=1)
        assert "gpt-4" in header
        assert "openai/" not in header

    def test_header_with_tokens(self):
        msg = _msg(name="Bob", tokens=500)
        header = _build_header_text(msg, "  ", msg_id=1)
        assert "500tok" in header

    def test_header_with_gen_seconds(self):
        msg = _msg(name="Bob", gen_secs=3.5)
        header = _build_header_text(msg, "  ", msg_id=1)
        assert "3.5s" in header

    def test_header_with_swipe_indicator(self):
        msg = _msg(name="Bob", n_swipes=3)
        header = _build_header_text(msg, "  ", msg_id=1)
        assert "[1/3]" in header

    def test_header_with_time(self):
        msg = _msg(name="Bob")
        header = _build_header_text(msg, "  ", msg_id=1)
        assert "3:12am" in header

    def test_cursor_prefix(self):
        msg = _msg(name="Bob")
        header = _build_header_text(msg, "▌ ", msg_id=1)
        assert header.startswith("▌ #1 Bob")


class TestNameColor:
    def test_user_color(self):
        msg = _msg(is_user=True)
        assert _name_color(msg) == CP_USER_NAME

    def test_char_color(self):
        msg = _msg(is_user=False)
        assert _name_color(msg) == CP_CHAR_NAME


class TestRenderMessages:
    def test_single_message(self):
        msgs = [_msg(text="Hello world")]
        lines = render_messages(msgs, 80, set(), cursor_msg=0)
        assert any(rl.is_header for rl in lines)
        assert any("Hello world" in rl.text for rl in lines)

    def test_cursor_marker(self):
        msgs = [_msg(), _msg()]
        lines = render_messages(msgs, 80, set(), cursor_msg=0)
        header = next(rl for rl in lines if rl.is_header and rl.msg_idx == 0)
        assert header.text.startswith("▌")

    def test_non_cursor_no_marker(self):
        msgs = [_msg(), _msg()]
        lines = render_messages(msgs, 80, set(), cursor_msg=0)
        header = next(rl for rl in lines if rl.is_header and rl.msg_idx == 1)
        assert not header.text.startswith("▌")

    def test_separator_between_messages(self):
        msgs = [_msg(), _msg()]
        lines = render_messages(msgs, 80, set())
        separators = [rl for rl in lines if rl.color_pair == CP_SEPARATOR]
        assert len(separators) == 1
        assert "─" in separators[0].text

    def test_reasoning_hidden_by_default(self):
        msgs = [_msg(reasoning="Think think think")]
        lines = render_messages(msgs, 80, set())
        assert not any("Think think think" in rl.text for rl in lines)

    def test_reasoning_shown_when_expanded(self):
        msgs = [_msg(reasoning="Think think think")]
        lines = render_messages(msgs, 80, expanded_reasoning={0})
        assert any("Think think think" in rl.text for rl in lines)
        reasoning_lines = [rl for rl in lines if rl.color_pair == CP_REASONING]
        assert len(reasoning_lines) > 0

    def test_text_wrapping(self):
        long_text = "word " * 50
        msgs = [_msg(text=long_text)]
        lines = render_messages(msgs, 40, set())
        body_lines = [rl for rl in lines if not rl.is_header and rl.text.strip()]
        assert len(body_lines) > 1

    def test_msg_idx_assigned(self):
        msgs = [_msg(), _msg()]
        lines = render_messages(msgs, 80, set())
        for rl in lines:
            assert rl.msg_idx in (0, 1)
