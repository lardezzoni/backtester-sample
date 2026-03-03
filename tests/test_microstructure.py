"""
Testes unitários para src/microstructure.py — MicrostructureConfig,
MicrostructureStrategy (filtros de liquidez, holding period).

Como MicrostructureStrategy é um bt.Strategy, precisa de um Cerebro
para instanciar. Usamos um Cerebro mínimo com dados sintéticos.
"""
import backtrader as bt
import numpy as np
import pandas as pd
import pytest

from microstructure import MicrostructureConfig, MicrostructureStrategy


# ---------------------------------------------------------------------------
# Helpers — criar dados sintéticos e rodar Cerebro
# ---------------------------------------------------------------------------

def _make_synthetic_df(n=50, base_volume=1000):
    """DataFrame com OHLCV sintético."""
    dates = pd.date_range("2023-01-01", periods=n, freq="B")
    close = 100 + np.cumsum(np.random.RandomState(42).randn(n) * 0.5)
    return pd.DataFrame({
        "Open": close + 0.1,
        "High": close + 1.0,
        "Low": close - 1.0,
        "Close": close,
        "Volume": [base_volume] * n,
    }, index=dates)


class CaptureMicroStrategy(MicrostructureStrategy):
    """Estratégia que captura resultados dos filtros a cada barra."""
    params = (
        ("micro_cfg", MicrostructureConfig()),
    )

    def __init__(self):
        super().__init__()
        self.liquidity_results = []
        self.holding_results = []
        self.micro_ok_results = []

    def next(self):
        super().next()
        self.liquidity_results.append(self._liquidity_ok())
        self.holding_results.append(self._holding_period_ok())
        self.micro_ok_results.append(self.micro_ok())


def _run_strategy(df, micro_cfg=None):
    """Roda CaptureMicroStrategy e retorna a instância."""
    if micro_cfg is None:
        micro_cfg = MicrostructureConfig()

    data = bt.feeds.PandasData(dataname=df)
    cerebro = bt.Cerebro()
    cerebro.adddata(data)
    cerebro.addstrategy(CaptureMicroStrategy, micro_cfg=micro_cfg)
    results = cerebro.run()
    return results[0]


# ---------------------------------------------------------------------------
# Testes de liquidez (_liquidity_ok)
# ---------------------------------------------------------------------------

class TestLiquidityFilter:
    def test_blocks_when_volume_below_threshold(self):
        """
        Com volume constante, a SMA(20) de volume == volume,
        portanto vol_ratio = 1.0. Com min_volume_pct_avg=2.0
        (exige 200% da média), deve bloquear.
        """
        df = _make_synthetic_df(n=50, base_volume=1000)
        cfg = MicrostructureConfig(min_volume_pct_avg=2.0)
        strat = _run_strategy(df, micro_cfg=cfg)
        # Após warmup (20 barras SMA), os resultados devem bloquear
        # porque vol_ratio = 1.0 < 2.0
        results_after_warmup = strat.liquidity_results[20:]
        assert all(r is False for r in results_after_warmup)

    def test_allows_when_volume_above_threshold(self):
        """
        Com volume constante e min_volume_pct_avg=0.5,
        vol_ratio = 1.0 >= 0.5, deve permitir.
        """
        df = _make_synthetic_df(n=50, base_volume=1000)
        cfg = MicrostructureConfig(min_volume_pct_avg=0.5)
        strat = _run_strategy(df, micro_cfg=cfg)
        results_after_warmup = strat.liquidity_results[20:]
        assert all(r is True for r in results_after_warmup)


# ---------------------------------------------------------------------------
# Testes de holding period (_holding_period_ok)
# ---------------------------------------------------------------------------

class TestHoldingPeriodFilter:
    def test_holding_period_one_allows_immediate(self):
        """min_holding_period=1: após 1 barra, _holding_period_ok é True."""
        df = _make_synthetic_df(n=50)
        cfg = MicrostructureConfig(min_holding_period=1)
        strat = _run_strategy(df, micro_cfg=cfg)
        # _bars_since_trade começa em 0 e incrementa por 1 a cada next()
        # Com min_holding=1 e sem trades, após a 1ª barra já é True
        assert strat.holding_results[-1] is True

    def test_high_holding_period_blocks_initially(self):
        """
        min_holding_period=100: sem nenhum trade, _bars_since_trade
        incrementa do 0 a cada barra. Com 50 barras e min=100,
        nunca atinge o mínimo.
        """
        df = _make_synthetic_df(n=50)
        cfg = MicrostructureConfig(min_holding_period=100)
        strat = _run_strategy(df, micro_cfg=cfg)
        # _bars_since_trade vai de 1 até 50, nunca chega a 100
        assert all(r is False for r in strat.holding_results)


# ---------------------------------------------------------------------------
# Testes de micro_ok (combinação de filtros)
# ---------------------------------------------------------------------------

class TestMicroOk:
    def test_all_filters_pass(self):
        """Configuração permissiva → micro_ok() = True (após warmup)."""
        df = _make_synthetic_df(n=50, base_volume=1000)
        cfg = MicrostructureConfig(
            min_volume_pct_avg=0.5,
            min_holding_period=1,
            max_spread_pct=None,
        )
        strat = _run_strategy(df, micro_cfg=cfg)
        results_after_warmup = strat.micro_ok_results[20:]
        assert all(r is True for r in results_after_warmup)

    def test_liquidity_blocks_micro_ok(self):
        """Se liquidez falha, micro_ok = False mesmo que holding passe."""
        df = _make_synthetic_df(n=50, base_volume=1000)
        cfg = MicrostructureConfig(
            min_volume_pct_avg=10.0,  # impossível de atingir
            min_holding_period=1,
        )
        strat = _run_strategy(df, micro_cfg=cfg)
        results_after_warmup = strat.micro_ok_results[20:]
        assert all(r is False for r in results_after_warmup)


# ---------------------------------------------------------------------------
# Testes de MicrostructureConfig (dataclass)
# ---------------------------------------------------------------------------

class TestMicrostructureConfig:
    def test_default_values(self):
        cfg = MicrostructureConfig()
        assert cfg.min_volume_pct_avg == 0.3
        assert cfg.max_spread_pct is None
        assert cfg.min_holding_period == 1

    def test_custom_values(self):
        cfg = MicrostructureConfig(
            min_volume_pct_avg=0.5,
            max_spread_pct=0.02,
            min_holding_period=5,
        )
        assert cfg.min_volume_pct_avg == 0.5
        assert cfg.max_spread_pct == 0.02
        assert cfg.min_holding_period == 5
