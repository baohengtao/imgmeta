from rich.console import Console
from rich.progress import Progress
from rich.theme import Theme
from rich import traceback
import typer, click
traceback.install(show_locals=True, suppress=[typer, click])
custom_theme = Theme({
    "info": "dim cyan",
    "warning": "magenta",
    "error": "bold red"
})
console = Console(theme=custom_theme)
progress = Progress(console=console)
