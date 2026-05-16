from __future__ import annotations


def clean_player_handle(display_name: str) -> str:
    return display_name.split("#", maxsplit=1)[0]