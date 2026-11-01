import numpy as np
import pandas as pd
import pytest


@pytest.fixture
def price_frame():
    """Crea un DataFrame de precios tranquilos cuya última rueda varía last_move."""

    def build(last_move: float = 0.0, days: int = 60, seed: int = 0) -> pd.DataFrame:
        rng = np.random.default_rng(seed)
        moves = rng.normal(0, 0.002, days)
        moves[-1] = last_move
        index = pd.bdate_range(end="2026-10-30", periods=days)
        return pd.DataFrame({"Close": 100 * np.cumprod(1 + moves), "Volume": [1_000] * days}, index=index)

    return build
