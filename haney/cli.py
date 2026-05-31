"""Typer CLI entry point for Haney.

Provides the main CLI application with startup banner,
first-run setup, and the interactive chat loop.
"""

from __future__ import annotations

import typer
from rich.console import Console

from haney.banner import render_banner
from haney.chat import start_chat
from haney.setup import is_setup_complete, run_setup

app = typer.Typer(
    name="haney",
    help="Haney — A terminal-based AI coding assistant.",
    no_args_is_help=False,
)


@app.command()
def main() -> None:
    """Launch the Haney interactive assistant."""
    console = Console()

    # Show startup banner
    render_banner(console)

    # First-run setup if .haney does not exist
    if not is_setup_complete():
        console.print()
        run_setup(console)

    # Enter the interactive chat loop
    start_chat(console)


if __name__ == "__main__":
    app()
