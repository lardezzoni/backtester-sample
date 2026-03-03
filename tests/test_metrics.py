"""
Testes unitários para src/metrics.py — compute_metrics.

A função compute_metrics recebe (df, results, out_dir, equity_curve) e
retorna um dict com Sharpe, Sortino, MaxDrawdown e AnnualizedReturn.
Os testes exercitam a lógica via equity_curve (branch principal).
"""
import math
import os
import tempfile

import numpy as np
import pandas as pd
import pytest

from metrics import compute_metrics


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_dummy_df(n: int = 100) -> pd.DataFrame:
    """DataFrame mínimo aceito por compute_metrics (precisa de col Close)."""
    return pd.DataFrame({"Close": np.linspace(100, 110, n)})


def _call_metrics(equity_curve, out_dir=None):
    """Wrapper para chamar compute_metrics com o mínimo necessário."""
    if out_dir is None:
        out_dir = tempfile.mkdtemp()
    df = _make_dummy_df(len(equity_curve))
    # results não é usado quando equity_curve é passado; lista vazia basta
    return compute_metrics(df, results=[], out_dir=out_dir, equity_curve=equity_curve)


# ---------------------------------------------------------------------------
# Testes de Sharpe
# ---------------------------------------------------------------------------

class TestSharpe:
    def test_constant_positive_returns_high_sharpe(self):
        """Retornos constantes positivos → desvio ~0, Sharpe muito alto."""
        # Equity sobe 1 unidade por dia, de 100 a 200
        equity = list(np.linspace(100, 200, 252))
        m = _call_metrics(equity)
        # Com retornos praticamente constantes, Sharpe deve ser alto
        assert m["Sharpe"] > 5.0

    def test_zero_returns_sharpe_zero(self):
        """Equity flat (retornos zero) → Sharpe = 0."""
        equity = [100_000.0] * 100
        m = _call_metrics(equity)
        assert m["Sharpe"] == 0.0

    def test_negative_returns_negative_sharpe(self):
        """Equity que só cai → Sharpe negativo."""
        equity = list(np.linspace(100_000, 80_000, 100))
        m = _call_metrics(equity)
        assert m["Sharpe"] < 0.0


# ---------------------------------------------------------------------------
# Testes de Sortino
# ---------------------------------------------------------------------------

class TestSortino:
    def test_only_positive_returns_high_sortino(self):
        """Sem retornos negativos → downside_std ≈ 0, Sortino alto ou 0 (sem downside)."""
        equity = list(np.linspace(100, 200, 252))
        m = _call_metrics(equity)
        # Sem retornos negativos: downside_returns é vazio,
        # código usa std_ret como fallback → Sortino = Sharpe
        assert m["Sortino"] > 5.0

    def test_zero_returns_sortino_zero(self):
        """Retornos zero → Sortino = 0."""
        equity = [100_000.0] * 100
        m = _call_metrics(equity)
        assert m["Sortino"] == 0.0


# ---------------------------------------------------------------------------
# Testes de Max Drawdown
# ---------------------------------------------------------------------------

class TestMaxDrawdown:
    def test_monotonically_increasing_drawdown_zero(self):
        """Série que só sobe → drawdown = 0."""
        equity = list(range(100, 201))
        m = _call_metrics(equity)
        assert m["MaxDrawdown"] == 0.0

    def test_drawdown_always_non_positive(self):
        """Drawdown é sempre <= 0 por definição."""
        equity = [100, 110, 105, 115, 90, 120]
        m = _call_metrics(equity)
        assert m["MaxDrawdown"] <= 0.0

    def test_known_drawdown(self):
        """Equity 100 → 200 → 100: drawdown = -50%."""
        equity = [100, 150, 200, 150, 100]
        m = _call_metrics(equity)
        assert abs(m["MaxDrawdown"] - (-0.5)) < 1e-6


# ---------------------------------------------------------------------------
# Testes de Retorno Anualizado
# ---------------------------------------------------------------------------

class TestAnnualizedReturn:
    def test_flat_equity_zero_return(self):
        """Equity flat → retorno anualizado ≈ 0."""
        equity = [100_000.0] * 100
        m = _call_metrics(equity)
        assert abs(m["AnnualizedReturn"]) < 1e-10

    def test_positive_equity_positive_return(self):
        """Equity crescente → retorno anualizado > 0."""
        equity = list(np.linspace(100_000, 120_000, 252))
        m = _call_metrics(equity)
        assert m["AnnualizedReturn"] > 0.0

    def test_annualization_uses_252_trading_days(self):
        """Verifica que o fator de anualização é 252 (dias úteis), não 365.

        Retorno diário de 0.1% × 252 = 25.2% anualizado.
        Se fosse 365: 36.5%. Teste verifica proximidade a 25.2%.
        """
        daily_ret = 0.001  # 0.1% ao dia
        n = 252
        # equity com retorno diário constante de 0.1%
        equity = [100_000.0]
        for _ in range(n):
            equity.append(equity[-1] * (1 + daily_ret))
        m = _call_metrics(equity)
        expected = daily_ret * 252
        assert abs(m["AnnualizedReturn"] - expected) < 0.01


class TestSortinoDownside:
    def test_sortino_uses_downside_only(self):
        """Sortino com retornos mistos deve ser diferente de Sharpe (usa apenas downside)."""
        # Série com mix de subidas e descidas assimétricas
        equity = [100, 110, 105, 115, 108, 120, 112, 125, 118, 130]
        m = _call_metrics(equity)
        # Se downside_returns não é vazio, Sortino != Sharpe
        if m["Sharpe"] != 0 and m["Sortino"] != 0:
            assert m["Sortino"] != m["Sharpe"]


# ---------------------------------------------------------------------------
# Testes de salvamento em disco
# ---------------------------------------------------------------------------

class TestMetricsIO:
    def test_csv_created(self):
        """compute_metrics gera metrics.csv no diretório informado."""
        with tempfile.TemporaryDirectory() as tmp:
            _call_metrics([100, 110, 120], out_dir=tmp)
            assert os.path.isfile(os.path.join(tmp, "metrics.csv"))

    def test_csv_has_expected_columns(self):
        """metrics.csv deve ter as 4 colunas de métricas."""
        with tempfile.TemporaryDirectory() as tmp:
            _call_metrics([100, 110, 120], out_dir=tmp)
            df = pd.read_csv(os.path.join(tmp, "metrics.csv"))
            expected = {"Sharpe", "Sortino", "MaxDrawdown", "AnnualizedReturn"}
            assert set(df.columns) == expected
