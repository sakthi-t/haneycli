"""Haney startup banner module."""

from rich.console import Console
from rich.panel import Panel
from rich.text import Text


BANNER_ASCII = r"""/\_/\ 
( o.o )
 > ^ <"""

BANNER_MESSAGE = """Haney Meow!

I am Haney,
an apartment cat.

Fed by Sakthivel T.

Please feed stray cats and dogs whenever possible.

Small acts of kindness save lives."""


def render_banner(console: Console) -> None:
    """Render the Haney startup banner.

    Args:
        console: Rich Console instance for output.
    """
    ascii_text = Text(BANNER_ASCII, style="bold yellow")
    message_text = Text(BANNER_MESSAGE, style="italic cyan")

    combined = Text.assemble(ascii_text, "\n\n", message_text)

    panel = Panel(
        combined,
        border_style="yellow",
        padding=(1, 2),
        title="Haney",
        title_align="left",
    )
    console.print(panel)
