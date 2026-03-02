# src/reality_check.py
"""
Etapa 2 — Mitigação de data snooping (Reality Check - White)

O que faz:
- Lê results/calibration/calibration_table.csv (N variações testadas na calibração)
- Roda cada variação (robô aprimorado) e o benchmark (baseline SMA 10/20) no mesmo dataset
- Calcula retornos diários de portfólio (equity curve -> pct_change)
- Calcula excess return: f_{i,t} = r_{i,t} - r_{bench,t}
- Estatística observada: T_obs = sqrt(T) * max_i mean(f_i)
- Bootstrap em blocos (Moving Block Bootstrap) no f centrado para obter p-value (White Reality Check)

Saídas:
- results/reality_check/reality_check_summary.csv
- results/reality_check/model_means.csv
- E imprime um parágrafo pronto para colar no TCC
"""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any, Dict, Tuple

import numpy as np
import pandas as pd
import backtrader as bt

from utils import prepare_csv
from execution import calibrate_execution_params
from microstructure import MicrostructureStrategy, MicrostructureConfig
from risk import VolatilityTargetSizer


# -----------------------------
# Estratégias (baseline + enhanced)
# -----------------------------
class BaselineSmaCross(bt.Strategy):
    params = (("short_period", 10), ("long_period", 20))

    def __init__(self):
        self.sma_short = bt.indicators.SimpleMovingAverage(self.data.close, period=self.p.short_period)
        self.sma_long = bt.indicators.SimpleMovingAverage(self.data.close, period=self.p.long_period)
        self.crossover = bt.indicators.CrossOver(self.sma_short, self.sma_long)
        self.equity_curve = []

    def next(self):
        self.equity_curve.append(self.broker.getvalue())

        if not self.position:
            if self.crossover > 0:
                self.buy()
            elif self.crossover < 0:
                self.sell()
        else:
            if self.crossover > 0 and self.position.size < 0:
                self.close()
                self.buy()
            elif self.crossover < 0 and self.position.size > 0:
                self.close()
                self.sell()


class EnhancedSmaCross(MicrostructureStrategy):
    params = (
        ("fast_period", 10),
        ("slow_period", 20),
        ("micro_cfg", MicrostructureConfig()),
    )

    def __init__(self):
        super().__init__()
        self.sma_fast = bt.indicators.SimpleMovingAverage(self.data.close, period=self.p.fast_period)
        self.sma_slow = bt.indicators.SimpleMovingAverage(self.data.close, period=self.p.slow_period)
        self.crossover = bt.indicators.CrossOver(self.sma_fast, self.sma_slow)
        self.equity_curve = []

    def next(self):
        self.equity_curve.append(self.broker.getvalue())

        super().next()

        if not self.micro_ok():
            return

        if not self.position:
            if self.crossover > 0:
                self.buy()
            elif self.crossover < 0:
                self.sell()
        else:
            if self.crossover > 0 and self.position.size < 0:
                self.close()
                self.buy()
            elif self.crossover < 0 and self.position.size > 0:
                self.close()
                self.sell()


# -----------------------------
# Utilidades
# -----------------------------
def project_root_from_here() -> Path:
    here = Path(__file__).resolve()
    # se estiver em src/, root = parents[1]
    cand = here.parents[1]
    if (cand / "data").exists():
        return cand
    # fallback: cwd
    return Path.cwd()


def load_ohlcv_csv(clean_path: Path) -> pd.DataFrame:
    df = pd.read_csv(clean_path, parse_dates=["datetime"])
    df = df.sort_values("datetime").set_index("datetime")
    return df


def equity_to_returns(equity_curve, index: pd.Index) -> pd.Series:
    eq = np.asarray(equity_curve, dtype=float)
    if len(eq) < 3:
        raise ValueError("Equity curve muito curta para calcular retornos.")

    # alinha no final se houver mismatch de tamanho
    idx = index[-len(eq):]
    equity = pd.Series(eq, index=idx)
    rets = equity.pct_change().dropna()
    return rets


def run_baseline_returns(
    df: pd.DataFrame,
    cash: float,
    commission_perc: float = 0.0,
    slippage_perc: float = 0.0,
) -> pd.Series:
    data_feed = bt.feeds.PandasData(dataname=df)
    cerebro = bt.Cerebro()
    cerebro.adddata(data_feed)
    cerebro.broker.setcash(cash)
    cerebro.broker.setcommission(commission=commission_perc)
    cerebro.broker.set_slippage_perc(slippage_perc)
    cerebro.addstrategy(BaselineSmaCross, short_period=10, long_period=20)
    results = cerebro.run()
    strat = results[0]
    return equity_to_returns(strat.equity_curve, df.index)


def run_enhanced_returns(
    df: pd.DataFrame,
    cash: float,
    cfg: Dict[str, Any],
) -> pd.Series:
    # execução (com slippage_multiplier do próprio cfg)
    exec_params = calibrate_execution_params(
        df,
        high_col="High",
        low_col="Low",
        commission_perc=float(cfg.get("commission_perc", 0.0)),
        slippage_multiplier=float(cfg.get("slippage_multiplier", 0.5)),
    )

    data_feed = bt.feeds.PandasData(dataname=df)
    cerebro = bt.Cerebro()
    cerebro.adddata(data_feed)
    cerebro.broker.setcash(cash)
    cerebro.broker.setcommission(commission=exec_params.commission_perc)
    cerebro.broker.set_slippage_perc(exec_params.slippage_perc)

    # risco
    cerebro.addsizer(
        VolatilityTargetSizer,
        target_vol=float(cfg["target_vol"]),
        lookback=int(cfg["vol_lookback"]),
        max_leverage=float(cfg["max_leverage"]),
        contract_size=5.0,
    )

    # microestrutura
    micro_cfg = MicrostructureConfig(
        min_volume_pct_avg=float(cfg["min_volume_pct_avg"]),
        max_spread_pct=None,  # no seu projeto está desligado (NaN/None)
        min_holding_period=int(cfg["min_holding_period"]),
    )

    cerebro.addstrategy(
        EnhancedSmaCross,
        fast_period=int(cfg["fast_period"]),
        slow_period=int(cfg["slow_period"]),
        micro_cfg=micro_cfg,
    )

    results = cerebro.run()
    strat = results[0]
    return equity_to_returns(strat.equity_curve, df.index)


# -----------------------------
# Moving Block Bootstrap
# -----------------------------
def mbb_sample_indices(T: int, L: int, rng: np.random.Generator) -> np.ndarray:
    """Gera índices (0..T-1) via Moving Block Bootstrap."""
    if L < 1:
        L = 1
    if L > T:
        L = max(1, T // 2)

    n_blocks = int(np.ceil(T / L))
    starts = rng.integers(0, T - L + 1, size=n_blocks)
    idx = np.concatenate([np.arange(s, s + L) for s in starts])[:T]
    return idx


def reality_check_white(
    F: np.ndarray,  # shape (T, N) excess returns
    B: int = 2000,
    block_len: int = 10,
    seed: int = 123,
) -> Tuple[float, float]:
    """
    White Reality Check:
    T_obs = sqrt(T) * max_i mean(F[:, i])

    Bootstrap sob H0:
    - centra cada coluna: F0 = F - mean(F, axis=0)
    - reamostra em blocos (MBB) no tempo
    - T* = sqrt(T) * max_i mean(F0[idx, i])
    p-value = (1 + #{T* >= T_obs}) / (B + 1)
    """
    T, N = F.shape
    means = F.mean(axis=0)
    T_obs = np.sqrt(T) * np.max(means)

    F0 = F - means  # impõe H0: mean=0 por modelo
    rng = np.random.default_rng(seed)

    exceed = 0
    for _ in range(B):
        idx = mbb_sample_indices(T, block_len, rng)
        m_star = F0[idx, :].mean(axis=0)
        T_star = np.sqrt(T) * np.max(m_star)
        if T_star >= T_obs:
            exceed += 1

    p_value = (1 + exceed) / (B + 1)
    return float(T_obs), float(p_value)


# -----------------------------
# Main
# -----------------------------
def main():
    parser = argparse.ArgumentParser(description="Etapa 2 — Reality Check (White) contra benchmark baseline")
    parser.add_argument("--data", type=str, default="data/MES_2023.csv", help="CSV bruto (default: data/MES_2023.csv)")
    parser.add_argument("--calibration-table", type=str, default="results/calibration/calibration_table.csv",
                        help="Tabela da calibração (default: results/calibration/calibration_table.csv)")
    parser.add_argument("--cash", type=float, default=100_000.0, help="Capital inicial (default 100000)")
    parser.add_argument("--bootstraps", type=int, default=2000, help="Número de reamostragens bootstrap (default 2000)")
    parser.add_argument("--block-len", type=int, default=10, help="Tamanho do bloco no MBB (default 10)")
    parser.add_argument("--alpha", type=float, default=0.05, help="Nível de significância (default 0.05)")
    parser.add_argument("--seed", type=int, default=123, help="Seed RNG (default 123)")
    args = parser.parse_args()

    root = project_root_from_here()
    data_path = Path(args.data)
    calib_path = Path(args.calibration_table)

    if not data_path.is_absolute():
        data_path = (root / data_path).resolve()
    if not calib_path.is_absolute():
        calib_path = (root / calib_path).resolve()

    if not data_path.exists():
        raise FileNotFoundError(f"Não encontrei o arquivo de dados: {data_path}")
    if not calib_path.exists():
        raise FileNotFoundError(f"Não encontrei a calibration_table: {calib_path}")

    # prepara CSV limpo
    clean_path = Path(prepare_csv(str(data_path), str(root / "data" / "MES_2023_clean.csv")))
    df = load_ohlcv_csv(clean_path)

    calib = pd.read_csv(calib_path)

    # pega N variações (dedup por tag)
    calib = calib.drop_duplicates(subset=["tag"]).reset_index(drop=True)
    N = len(calib)

    # benchmark baseline (fixo): sem custos (padrão), mas você pode mudar aqui se quiser
    r_bench = run_baseline_returns(df, cash=float(args.cash), commission_perc=0.0, slippage_perc=0.0)

    # roda todas as variações enhanced e calcula excess returns
    excess = {}
    for _, row in calib.iterrows():
        tag = str(row["tag"])
        cfg = row.to_dict()

        # NaN -> None
        if "max_spread_pct" in cfg and (pd.isna(cfg["max_spread_pct"])):
            cfg["max_spread_pct"] = None

        r_i = run_enhanced_returns(df, cash=float(args.cash), cfg=cfg)

        # alinha por interseção de datas
        joined = pd.concat([r_i.rename("ri"), r_bench.rename("rb")], axis=1).dropna()
        excess[tag] = (joined["ri"] - joined["rb"])

    F_df = pd.DataFrame(excess).dropna()
    T = F_df.shape[0]

    # estatística + p-value
    T_obs, pval = reality_check_white(
        F=F_df.values,
        B=int(args.bootstraps),
        block_len=int(args.block_len),
        seed=int(args.seed),
    )

    decision = "REJEITA H0 (há evidência de superioridade após ajuste)" if pval < float(args.alpha) else \
               "NÃO rejeita H0 (evidência insuficiente após ajuste)"

    out_dir = (root / "results" / "reality_check")
    out_dir.mkdir(parents=True, exist_ok=True)

    # tabela de médias (para diagnóstico)
    means = F_df.mean(axis=0).sort_values(ascending=False)
    means_df = pd.DataFrame({
        "tag": means.index,
        "mean_excess_daily": means.values,
        "annualized_excess": means.values * 252,
    })
    means_df.to_csv(out_dir / "model_means.csv", index=False)

    # summary (entregável)
    summary = pd.DataFrame([{
        "N_variations": N,
        "T_days": T,
        "benchmark": "Baseline SMA(10/20)",
        "bootstrap_B": int(args.bootstraps),
        "block_len": int(args.block_len),
        "T_obs": T_obs,
        "p_value": pval,
        "alpha": float(args.alpha),
        "decision": decision,
    }])
    summary.to_csv(out_dir / "reality_check_summary.csv", index=False)

    # imprime parágrafo pronto pro TCC
    paragraph = (
        f"Para mitigar o risco de data snooping decorrente da seleção da melhor configuração "
        f"entre múltiplas variações (N={N}), aplicamos o White Reality Check com bootstrap em blocos "
        f"(moving block bootstrap, L={int(args.block_len)}; B={int(args.bootstraps)}) comparando cada variação "
        f"ao benchmark Baseline SMA(10/20). A estatística observada foi T={T_obs:.3f} com p-value={pval:.4f}. "
        f"Adotando α={float(args.alpha):.2f}, {('rejeitamos' if pval < float(args.alpha) else 'não rejeitamos')} "
        f"a hipótese nula de ausência de desempenho superior após ajuste para múltiplos testes; "
        f"portanto, {('há evidência' if pval < float(args.alpha) else 'a evidência é insuficiente')} "
        f"de que a configuração escolhida não se deve apenas à escolha oportunista entre várias tentativas."
    )

    print("\n" + "=" * 70)
    print("REALITY CHECK (WHITE) — OK")
    print(f"Summary: {out_dir / 'reality_check_summary.csv'}")
    print(f"Means:   {out_dir / 'model_means.csv'}")
    print("-" * 70)
    print(paragraph)
    print("=" * 70 + "\n")


if __name__ == "__main__":
    main()