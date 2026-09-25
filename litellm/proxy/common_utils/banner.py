from typing import Final

# RAW ASCII banner
LITELLM_BANNER: Final = """   ██████╗  █████╗ ██╗    ██╗
   ██╔══██╗██╔══██╗██║    ██║
   ██████╔╝███████║██║ █╗ ██║
   ██╔══██╗██╔══██║██║███╗██║
   ██║  ██║██║  ██║╚███╔███╔╝
   ╚═╝  ╚═╝╚═╝  ╚═╝ ╚══╝╚══╝  by Rabbitt"""


def show_banner():
    """Display the RAW CLI banner."""
    try:
        import click

        click.echo(f"\n{LITELLM_BANNER}\n")
    except ImportError:
        print("\n")  # noqa: T201
