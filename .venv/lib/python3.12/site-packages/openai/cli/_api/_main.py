from __future__ import annotations

from argparse import ArgumentParser

from . import audio, chat, completions, files, fine_tuning, image, models


def register_commands(parser: ArgumentParser) -> None:
    subparsers = parser.add_subparsers(help="All API subcommands")

    chat.register(subparsers)
    image.register(subparsers)
    audio.register(subparsers)
    files.register(subparsers)
    models.register(subparsers)
    completions.register(subparsers)
    fine_tuning.register(subparsers)
