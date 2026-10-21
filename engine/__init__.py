"""AI Arena engine: pure-Python Connect Four rules, heuristics and agents.

app.py should only import :mod:`engine.api`.
"""

from .api import (  # noqa: F401
    AGENT_PRESETS, game_state, choose_move, run_match, compare_depth,
    validate_board, normalize_config, apply_move,
)
