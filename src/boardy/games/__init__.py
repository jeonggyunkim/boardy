"""Namespace package: one subpackage per supported board game.

Importing this package registers every built-in game with
boardy.core.registry (see each game's __init__.py). Add a new game by
creating boardy/games/<slug>/ with its own spec.py, then importing it
here.
"""

from . import deep_sea_crew  # noqa: F401  (import side effect: registers this game)
from . import gomoku  # noqa: F401  (import side effect: registers this game)

