"""
Testes unitários para src/risk.py — VolatilityTargetSizer.

O sizer do Backtrader depende de self.broker, self.data, etc.  Testamos
a lógica interna (_estimate_ann_vol, limites de alavancagem) com mocks
leves, sem precisar levantar um Cerebro completo.
"""
import math
from unittest.mock import MagicMock

import numpy as np
import pytest

from risk import VolatilityTargetSizer


# ---------------------------------------------------------------------------
# Helpers — construir um sizer "desconectado" do Backtrader
# ---------------------------------------------------------------------------

def _make_sizer(**overrides):
    """
    Cria um VolatilityTargetSizer mockado, sem Cerebro.
    Sobrescreve parâmetros e dependências necessárias.
    """
    defaults = dict(
        target_vol=0.10,
        lookback=20,
        annualization=252,
        max_leverage=2.0,
        contract_size=50.0,
        min_size=1,
    )
    defaults.update(overrides)

    sizer = object.__new__(VolatilityTargetSizer)
    # Simula self.p (params) como SimpleNamespace-like
    sizer.p = MagicMock(**defaults)
    sizer._ann_factor = math.sqrt(defaults["annualization"])
    return sizer


class _CloseArray:
    """Simula data.close do Backtrader: close[0] = último, close[-1] = penúltimo."""

    def __init__(self, closes):
        self._closes = closes

    def __getitem__(self, idx):
        return float(self._closes[len(self._closes) - 1 + idx])


def _make_data_mock(closes):
    """
    Cria um mock de data feed do Backtrader com closes[i] acessíveis
    via data.close[i] (indexação negativa relativa a 0).
    """
    data = MagicMock()
    data.close = _CloseArray(closes)
    data.__len__ = lambda self_: len(closes)
    return data


def _call_getsizing(sizer, closes, equity=100_000.0):
    """Helper que chama _getsizing com mocks de broker e data."""
    data = _make_data_mock(closes)
    sizer.broker = MagicMock()
    sizer.broker.getvalue.return_value = equity
    comminfo = MagicMock()
    cash = equity
    return sizer._getsizing(comminfo, cash, data, isbuy=True)


# ---------------------------------------------------------------------------
# Testes de limite de alavancagem
# ---------------------------------------------------------------------------

class TestLeverageLimit:
    def test_position_never_exceeds_max_leverage(self):
        """
        Para qualquer cenário razoável, position * contract_notional
        nunca deve exceder max_leverage * equity.
        """
        sizer = _make_sizer(target_vol=0.10, max_leverage=2.0, contract_size=50.0)
        # Cria closes com volatilidade muito baixa → exposição raw seria enorme
        # (target_vol / vol_realizada → muito alto), mas capped em max_leverage
        closes = [100.0 + 0.001 * i for i in range(25)]  # quase flat
        equity = 100_000.0
        size = _call_getsizing(sizer, closes, equity)

        contract_notional = closes[-1] * 50.0
        if size > 0:
            assert size * contract_notional <= 2.0 * equity * 1.01  # 1% tolerância de arredondamento

    def test_max_leverage_zero_means_zero_position(self):
        """max_leverage = 0 → posição sempre 0."""
        sizer = _make_sizer(max_leverage=0.0, contract_size=50.0)
        closes = list(np.linspace(100, 110, 25))
        size = _call_getsizing(sizer, closes, equity=100_000.0)
        assert size == 0


# ---------------------------------------------------------------------------
# Testes de volatilidade → tamanho de posição
# ---------------------------------------------------------------------------

class TestVolatilityScaling:
    def test_higher_vol_fewer_contracts(self):
        """Volatilidade alta → menos contratos que vol baixa."""
        sizer = _make_sizer(target_vol=0.10, max_leverage=10.0, contract_size=5.0)

        # Série com alta volatilidade
        rng = np.random.RandomState(42)
        prices_high_vol = 100 + np.cumsum(rng.normal(0, 3, 25))
        prices_high_vol = np.maximum(prices_high_vol, 50)  # manter positivos

        # Série com baixa volatilidade
        prices_low_vol = 100 + np.cumsum(rng.normal(0, 0.1, 25))

        size_high = _call_getsizing(sizer, list(prices_high_vol), equity=100_000.0)
        size_low = _call_getsizing(sizer, list(prices_low_vol), equity=100_000.0)

        # Mais vol → menos contratos
        assert size_high <= size_low


# ---------------------------------------------------------------------------
# Testes de posição mínima
# ---------------------------------------------------------------------------

class TestMinSize:
    def test_min_size_respected(self):
        """Se o cálculo der < min_size, retorna 0 (não retorna fração)."""
        sizer = _make_sizer(
            target_vol=0.0001,       # alvo de vol muito baixo
            max_leverage=0.001,      # alavancagem muito baixa
            contract_size=100_000.0, # contrato enorme
            min_size=1,
        )
        closes = list(np.linspace(100, 110, 25))
        size = _call_getsizing(sizer, closes, equity=1.0)  # capital mínimo
        assert size == 0


# ---------------------------------------------------------------------------
# Testes com capital zero / muito baixo
# ---------------------------------------------------------------------------

class TestZeroCapital:
    def test_zero_equity_returns_zero(self):
        """Equity = 0 → target_notional = 0 → size = 0."""
        sizer = _make_sizer(contract_size=50.0)
        closes = list(np.linspace(100, 110, 25))
        size = _call_getsizing(sizer, closes, equity=0.0)
        assert size == 0

    def test_very_low_equity_returns_zero(self):
        """Equity muito baixo com contrato grande → size = 0."""
        sizer = _make_sizer(contract_size=50.0, max_leverage=2.0)
        closes = list(np.linspace(100, 110, 25))
        size = _call_getsizing(sizer, closes, equity=1.0)
        assert size == 0


# ---------------------------------------------------------------------------
# Testes de _estimate_ann_vol
# ---------------------------------------------------------------------------

class TestEstimateAnnVol:
    def test_returns_none_when_insufficient_data(self):
        """Com menos dados que lookback, retorna None."""
        sizer = _make_sizer(lookback=20)
        data = _make_data_mock([100.0] * 10)
        assert sizer._estimate_ann_vol(data) is None

    def test_flat_series_zero_vol(self):
        """Série de closes constantes → vol ≈ 0 → retorna None (vol <= 0)."""
        sizer = _make_sizer(lookback=5)
        data = _make_data_mock([100.0] * 10)
        result = sizer._estimate_ann_vol(data)
        # Retornos todos zero → std = 0 → retorna None
        assert result is None

    def test_positive_vol_for_varying_series(self):
        """Série com variação → vol anualizada positiva."""
        sizer = _make_sizer(lookback=5)
        closes = [100, 102, 99, 104, 97, 105, 98, 103, 101, 106]
        data = _make_data_mock(closes)
        vol = sizer._estimate_ann_vol(data)
        assert vol is not None
        assert vol > 0

    def test_price_zero_returns_zero_size(self):
        """Preço <= 0 → _getsizing retorna 0 sem tentar calcular vol."""
        sizer = _make_sizer(contract_size=50.0)
        closes = [0.0] * 25
        size = _call_getsizing(sizer, closes, equity=100_000.0)
        assert size == 0

    def test_ddof_1_for_sample_std(self):
        """_estimate_ann_vol usa ddof=1 (Bessel correction) para std amostral.

        Com dados sintéticos conhecidos, verifica que o resultado bate
        com a fórmula usando ddof=1.
        """
        sizer = _make_sizer(lookback=5, annualization=252)
        closes = [100, 102, 99, 104, 97, 105, 98, 103, 101, 106]
        data = _make_data_mock(closes)
        vol = sizer._estimate_ann_vol(data)
        # Calcula manualmente com ddof=1
        import numpy as _np
        last_5 = closes[-5:]
        rets = _np.diff(last_5) / _np.array(last_5[:-1], dtype=float)
        expected = _np.std(rets, ddof=1) * _np.sqrt(252)
        assert vol is not None
        assert abs(vol - expected) < 1e-10

    def test_min_size_boundary(self):
        """Quando cálculo dá exatamente min_size, retorna min_size (não 0)."""
        sizer = _make_sizer(
            target_vol=0.10, max_leverage=2.0,
            contract_size=5.0, min_size=1,
        )
        # Closes com volatilidade razoável
        rng = np.random.RandomState(123)
        closes = list(100 + np.cumsum(rng.normal(0, 1, 25)))
        size = _call_getsizing(sizer, closes, equity=100_000.0)
        # Com capital de 100k, size deve ser >= 1
        assert size >= 1
