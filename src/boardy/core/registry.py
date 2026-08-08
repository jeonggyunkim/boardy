"""Registry of games hosted by the shared CLI/web layers.

Games register themselves as a side effect of being imported (see
boardy/games/__init__.py, which imports every game subpackage). This is
deliberately simple explicit-import discovery rather than plugin scanning
— fine for a handful of built-in games; revisit if/when third-party game
plugins become a real need.
"""

from __future__ import annotations

from .game_spec import GameSpec

_registry: dict[str, GameSpec] = {}


def register(spec: GameSpec) -> None:
    if spec.slug in _registry:
        raise ValueError(f"Game slug already registered: {spec.slug}")
    _registry[spec.slug] = spec


def get(slug: str) -> GameSpec | None:
    return _registry.get(slug)


def all_specs() -> list[GameSpec]:
    return list(_registry.values())
