"""
Write Image Meta
"""
import click
import typer
from rich import traceback
from rich.console import Console
from rich.progress import (BarColumn, Progress, TaskProgressColumn, TextColumn,
                           TimeRemainingColumn)
from rich.theme import Theme

__version__ = '0.3.0'

traceback.install(show_locals=True, suppress=[typer, click])
custom_theme = Theme({
    "info": "dim cyan",
    "warning": "magenta",
    "error": "bold red"
})
console = Console(theme=custom_theme, log_time=False, highlight=False)


def get_progress(disable=False):
    columns = [
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TaskProgressColumn(
            "[progress.percentage]{task.completed} of "
            "{task.total:>2.0f}({task.percentage:>02.1f}%)"),
        TimeRemainingColumn()
    ]
    return Progress(*columns, console=console,
                    disable=disable)
