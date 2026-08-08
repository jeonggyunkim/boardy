"""Boardy: a home for AI companions that play board games with you online.

Each supported game lives under boardy.games.<slug> and registers a
GameSpec (see boardy.core.game_spec) so the shared CLI dispatcher and web
service can host it without knowing its rules. See docs/PLAN.md.
"""
