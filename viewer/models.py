"""Data models for chat messages."""

from dataclasses import dataclass, field


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


@dataclass
class RenderedLine:
    """A single screen line with its color pair."""
    text: str
    color_pair: int = 0
    bold: bool = False
    msg_idx: int = -1
    is_header: bool = False
