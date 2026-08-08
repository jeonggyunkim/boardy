"""Top-level CLI dispatcher: `python -m boardy.cli --game <slug> [game args...]`.

Each game owns its own CLI (its rules and interaction model are too
different to share one interactive loop), so this just picks the right
one by slug and hands off the remaining argv. Run with no --game to list
what's available.
"""

from __future__ import annotations

import io
import sys

from . import games  # noqa: F401  (import side effect: registers built-in games)
from .core import registry


def main() -> None:
    if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
    argv = sys.argv[1:]
    game_slug = None
    rest: list[str] = []
    i = 0
    while i < len(argv):
        if argv[i] == "--game" and i + 1 < len(argv):
            game_slug = argv[i + 1]
            i += 2
        else:
            rest.append(argv[i])
            i += 1

    specs = registry.all_specs()
    if game_slug is None:
        print("Usage: python -m boardy.cli --game <slug> [game-specific args]")
        print("\nAvailable games:")
        for spec in specs:
            print(f"  {spec.slug:<20} {spec.name} — {spec.description}")
        return

    spec = registry.get(game_slug)
    if spec is None or spec.cli_main is None:
        print(f"Unknown game or no CLI available: {game_slug!r}")
        print("Available: " + ", ".join(s.slug for s in specs if s.cli_main is not None))
        raise SystemExit(1)

    sys.argv = [f"boardy.cli --game {game_slug}", *rest]
    spec.cli_main()


if __name__ == "__main__":
    main()
