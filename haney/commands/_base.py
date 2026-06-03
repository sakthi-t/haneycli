"""Command dataclass for Haney slash-commands."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, TYPE_CHECKING

from rich.console import Console

if TYPE_CHECKING:
    from haney.llm import ChatSession


@dataclass
class Command:
    """Represents a slash-command with its handler and description."""

    name: str
    description: str
    handler: Callable[[Console, list[str]], None]
