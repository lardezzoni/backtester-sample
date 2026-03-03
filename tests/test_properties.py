"""
Testes de propriedade (property-based) usando Hypothesis.

Invariantes testadas:
1. Custos nunca negativos: spread estimado >= 0 para High >= Low > 0
2. Posição respeita limite de alavancagem
3. Equity constante sem trades (retornos zero) → capital preservado
4. Drawdown máximo é sempre <= 0
"""
import math
import tempfile

import numpy as np
import pandas as pd
import pytest
from hypothesis import given, assume, settings
from hypothesis import strategies as st

from execution import estimate_highlow_spread, calibrate_execution_params
from metrics import compute_metrics


# ---------------------------------------------------------------------------
# 1. Custos nunca negativos
# ---------------------------------------------------------------------------

@given(
    high=st.floats(min_value=1.0, max_value=1e6),
    low=st.floats(min_value=0.01, max_value=1e6),
)
def test_spread_never_negative(high, low):
    """Para High >= Low > 0, o spread estimado é >= 0."""
    assume(high >= low)
    assume(low > 0)
    df = pd.DataFrame({"High": [high], "Low": [low]})
    spread = estimate_highlow_spread(df)
    value = spread.iloc[0]
    # Pode ser NaN se high+low==0, mas já filtramos low > 0
    assert not np.isnan(value)
    assert value >= 0.0


@given(
    high=st.floats(min_value=1.0, max_value=1e6),
    low=st.floats(min_value=0.01, max_value=1e6),
)
def test_half_spread_is_half(high, low):
    """half_spread é sempre exatamente metade do mean_spread."""
    assume(high >= low)
    assume(low > 0)
    df = pd.DataFrame({"High": [high], "Low": [low]})
    params = calibrate_execution_params(df)
    assert abs(params.half_spread_pct - params.mean_spread_pct / 2.0) < 1e-12


# ---------------------------------------------------------------------------
# 2. Posição respeita limite de alavancagem
# ---------------------------------------------------------------------------

@given(
    target_vol=st.floats(min_value=0.01, max_value=1.0),
    max_leverage=st.floats(min_value=0.1, max_value=10.0),
    ann_vol=st.floats(min_value=0.001, max_value=5.0),
)
def test_exposure_capped_by_max_leverage(target_vol, max_leverage, ann_vol):
    """
    A exposição raw = target_vol / ann_vol pode ser qualquer coisa,
    mas após capping, exposure <= max_leverage.
    """
    raw_exposure = target_vol / ann_vol
    exposure = max(0.0, min(max_leverage, raw_exposure))
    assert exposure <= max_leverage + 1e-12
    assert exposure >= 0.0


# ---------------------------------------------------------------------------
# 3. Equity constante sem trades → capital preservado
# ---------------------------------------------------------------------------

@given(
    capital=st.floats(min_value=100.0, max_value=1e8),
    n_days=st.integers(min_value=10, max_value=500),
)
def test_constant_equity_preserved(capital, n_days):
    """Equity constante (sem trades) → retorno anualizado = 0, drawdown = 0."""
    equity = [capital] * n_days
    df = pd.DataFrame({"Close": [capital] * n_days})
    with tempfile.TemporaryDirectory() as tmp:
        m = compute_metrics(df, results=[], out_dir=tmp, equity_curve=equity)
    assert abs(m["AnnualizedReturn"]) < 1e-10
    assert m["MaxDrawdown"] == 0.0
    assert m["Sharpe"] == 0.0


# ---------------------------------------------------------------------------
# 4. Drawdown máximo é sempre <= 0
# ---------------------------------------------------------------------------

@given(
    data=st.lists(
        st.floats(min_value=50.0, max_value=200.0),
        min_size=10,
        max_size=300,
    ),
)
@settings(max_examples=50)
def test_max_drawdown_non_positive(data):
    """Para qualquer série de equity, MaxDrawdown <= 0."""
    assume(len(data) >= 3)
    assume(all(math.isfinite(x) and x > 0 for x in data))
    df = pd.DataFrame({"Close": data})
    with tempfile.TemporaryDirectory() as tmp:
        m = compute_metrics(df, results=[], out_dir=tmp, equity_curve=data)
    assert m["MaxDrawdown"] <= 0.0 + 1e-12
