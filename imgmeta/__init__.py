"""
Write Image Meta
"""
import click
import typer
from rich import traceback
from rich.console import Console
from rich.progress import Progress, BarColumn, TimeRemainingColumn
from rich.theme import Theme
__version__ = '0.3.0'

traceback.install(show_locals=True, suppress=[typer, click])
custom_theme = Theme({
    "info": "dim cyan",
    "warning": "magenta",
    "error": "bold red"
})
console = Console(theme=custom_theme, log_time=False, highlight=False)


def get_progress():
    return Progress("[progress.description]{task.description}", BarColumn(),
                    "[progress.percentage]{task.completed} of "
                    "{task.total:>2.0f}({task.percentage:>02.1f}%)",
                    TimeRemainingColumn(), console=console)


def track(sequence, **kwargs):
    with get_progress() as progress:
        yield from progress.track(sequence, **kwargs)
