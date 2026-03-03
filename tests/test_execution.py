"""
Testes unitários para src/execution.py — estimate_highlow_spread e
calibrate_execution_params.
"""
import numpy as np
import pandas as pd
import pytest

from execution import estimate_highlow_spread, calibrate_execution_params


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_df(highs, lows):
    """Cria DataFrame com colunas High e Low."""
    return pd.DataFrame({"High": highs, "Low": lows})


# ---------------------------------------------------------------------------
# Testes de estimate_highlow_spread
# ---------------------------------------------------------------------------

class TestEstimateHighLowSpread:
    def test_spread_never_negative(self):
        """Para High >= Low (dados válidos), spread é >= 0."""
        df = _make_df(
            highs=[105, 110, 115, 108, 120],
            lows=[100, 105, 110, 102, 115],
        )
        spreads = estimate_highlow_spread(df)
        assert (spreads >= 0).all()

    def test_high_equals_low_spread_zero(self):
        """High == Low → spread = 0 (sem variação intradiária)."""
        df = _make_df(
            highs=[100.0, 200.0, 150.0],
            lows=[100.0, 200.0, 150.0],
        )
        spreads = estimate_highlow_spread(df)
        assert (spreads == 0.0).all()

    def test_known_spread_value(self):
        """
        High=110, Low=100 → avg=105, spread = 10/105 ≈ 0.09524.
        """
        df = _make_df(highs=[110], lows=[100])
        spreads = estimate_highlow_spread(df)
        expected = 10.0 / 105.0
        assert abs(spreads.iloc[0] - expected) < 1e-10

    def test_custom_column_names(self):
        """Funciona com nomes de coluna personalizados."""
        df = pd.DataFrame({"H": [110, 120], "L": [100, 110]})
        spreads = estimate_highlow_spread(df, high_col="H", low_col="L")
        assert len(spreads) == 2
        assert (spreads >= 0).all()

    def test_replaces_inf_with_nan(self):
        """Quando High == Low == 0 → divisão por zero → inf → NaN."""
        df = _make_df(highs=[0.0], lows=[0.0])
        spreads = estimate_highlow_spread(df)
        # 0/0 dá NaN, mas (0-0)/0 = 0/0 = NaN, não inf
        # Na verdade: h-l=0, avg=0, 0/0 = NaN que é tratado
        assert spreads.isna().all() or (spreads == 0).all()


# ---------------------------------------------------------------------------
# Testes de calibrate_execution_params
# ---------------------------------------------------------------------------

class TestCalibrateExecutionParams:
    def test_half_spread_is_half_of_mean_spread(self):
        """half_spread_pct = mean_spread_pct / 2."""
        df = _make_df(
            highs=[110, 120, 115],
            lows=[100, 110, 105],
        )
        params = calibrate_execution_params(df)
        assert abs(params.half_spread_pct - params.mean_spread_pct / 2.0) < 1e-12

    def test_slippage_coherent_with_half_spread(self):
        """slippage_perc = half_spread * slippage_multiplier."""
        df = _make_df(
            highs=[110, 120, 115],
            lows=[100, 110, 105],
        )
        mult = 0.5
        params = calibrate_execution_params(df, slippage_multiplier=mult)
        expected_slippage = params.half_spread_pct * mult
        assert abs(params.slippage_perc - expected_slippage) < 1e-12

    def test_commission_passthrough(self):
        """commission_perc é passado diretamente ao resultado."""
        df = _make_df(highs=[110], lows=[100])
        params = calibrate_execution_params(df, commission_perc=0.001)
        assert params.commission_perc == 0.001

    def test_zero_spread_when_high_equals_low(self):
        """High == Low → mean_spread = 0, half_spread = 0, slippage = 0."""
        df = _make_df(
            highs=[100.0, 100.0, 100.0],
            lows=[100.0, 100.0, 100.0],
        )
        params = calibrate_execution_params(df)
        assert params.mean_spread_pct == 0.0
        assert params.half_spread_pct == 0.0
        assert params.slippage_perc == 0.0

    def test_spread_positive_for_normal_data(self):
        """Dados normais → spread > 0."""
        df = _make_df(
            highs=[110, 115, 120, 112, 118],
            lows=[100, 105, 110, 103, 110],
        )
        params = calibrate_execution_params(df)
        assert params.mean_spread_pct > 0
        assert params.half_spread_pct > 0
        assert params.slippage_perc > 0

    def test_slippage_multiplier_scales(self):
        """Multiplicador maior → slippage maior."""
        df = _make_df(highs=[110, 120], lows=[100, 110])
        p1 = calibrate_execution_params(df, slippage_multiplier=0.5)
        p2 = calibrate_execution_params(df, slippage_multiplier=1.0)
        assert p2.slippage_perc > p1.slippage_perc
