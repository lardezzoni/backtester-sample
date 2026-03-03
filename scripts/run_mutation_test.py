#!/usr/bin/env python3
"""
Teste de mutação simplificado para os módulos críticos do TCC.

Aplica mutações pontuais no código-fonte, roda pytest e verifica se
os testes detectam (matam) o mutante. Restaura o arquivo original
após cada mutação.

Foca nos módulos: metrics.py, execution.py, risk.py, microstructure.py
"""
import subprocess
import sys
import shutil
import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SRC_DIR = PROJECT_ROOT / "src"
TESTS_DIR = PROJECT_ROOT / "tests"

# Cada mutação: (arquivo, string_original, string_mutada, descrição)
MUTATIONS = [
    # --- metrics.py ---
    (
        "metrics.py",
        "(mean_ret / std_ret) * np.sqrt(252)",
        "(mean_ret / std_ret) * np.sqrt(365)",
        "metrics: troca fator de anualização Sharpe 252 → 365",
    ),
    (
        "metrics.py",
        "sharpe = (mean_ret / std_ret) * np.sqrt(252) if std_ret > 0 else 0",
        "sharpe = (mean_ret / std_ret) * np.sqrt(252) if std_ret > 0 else 1",
        "metrics: Sharpe default quando std=0: 0 → 1",
    ),
    (
        "metrics.py",
        "returns[returns < 0]",
        "returns[returns > 0]",
        "metrics: inverte filtro downside > 0 (deveria ser < 0)",
    ),
    (
        "metrics.py",
        "drawdown = (equity - rolling_max) / rolling_max",
        "drawdown = (equity + rolling_max) / rolling_max",
        "metrics: troca - por + no cálculo do drawdown",
    ),
    (
        "metrics.py",
        "annualized_return = mean_ret * 252",
        "annualized_return = mean_ret * 365",
        "metrics: troca fator de anualização do retorno 252 → 365",
    ),
    (
        "metrics.py",
        "max_dd = drawdown.min()",
        "max_dd = drawdown.max()",
        "metrics: troca .min() por .max() no drawdown",
    ),
    (
        "metrics.py",
        "sortino = (mean_ret / downside_std) * np.sqrt(252) if downside_std > 0 else 0",
        "sortino = (mean_ret / downside_std) * np.sqrt(252) if downside_std > 0 else 1",
        "metrics: Sortino default quando downside_std=0: 0 → 1",
    ),

    # --- execution.py ---
    (
        "execution.py",
        "spread = (h - l) / avg",
        "spread = (h + l) / avg",
        "execution: troca h-l por h+l no cálculo do spread",
    ),
    (
        "execution.py",
        "half_spread = mean_spread / 2.0",
        "half_spread = mean_spread / 3.0",
        "execution: troca divisor do half_spread: 2.0 → 3.0",
    ),
    (
        "execution.py",
        "slippage_perc = half_spread * slippage_multiplier",
        "slippage_perc = half_spread + slippage_multiplier",
        "execution: troca * por + no slippage",
    ),
    (
        "execution.py",
        "avg = (h + l) / 2.0",
        "avg = (h + l) / 3.0",
        "execution: troca divisor da média: 2.0 → 3.0",
    ),

    # --- risk.py ---
    (
        "risk.py",
        "if price <= 0:",
        "if price <= -1:",
        "risk: altera guarda de preço: <= 0 → <= -1",
    ),
    (
        "risk.py",
        "exposure = max(0.0, min(self.p.max_leverage, raw_exposure))",
        "exposure = max(0.0, min(self.p.max_leverage + 1, raw_exposure))",
        "risk: soma 1 ao max_leverage no capping",
    ),
    (
        "risk.py",
        "if size < self.p.min_size:",
        "if size < self.p.min_size + 100:",
        "risk: soma 100 ao min_size check",
    ),
    (
        "risk.py",
        "raw_exposure = self.p.target_vol / ann_vol",
        "raw_exposure = self.p.target_vol * ann_vol",
        "risk: troca / por * na exposição raw",
    ),
    (
        "risk.py",
        "daily_vol = np.nanstd(rets, ddof=1)",
        "daily_vol = np.nanstd(rets, ddof=0)",
        "risk: troca ddof de 1 para 0 no cálculo de vol",
    ),

    # --- microstructure.py ---
    (
        "microstructure.py",
        "return vol_ratio >= self.p.micro_cfg.min_volume_pct_avg",
        "return vol_ratio <= self.p.micro_cfg.min_volume_pct_avg",
        "micro: inverte comparação de liquidez >= → <=",
    ),
    (
        "microstructure.py",
        "return self._bars_since_trade >= self.p.micro_cfg.min_holding_period",
        "return self._bars_since_trade <= self.p.micro_cfg.min_holding_period",
        "micro: inverte comparação do holding period >= → <=",
    ),
    (
        "microstructure.py",
        "self._bars_since_trade += 1",
        "self._bars_since_trade += 2",
        "micro: incremento do contador de barras: 1 → 2",
    ),
    (
        "microstructure.py",
        "return self._liquidity_ok() and self._holding_period_ok() and self._spread_ok()",
        "return self._liquidity_ok() or self._holding_period_ok() and self._spread_ok()",
        "micro: troca 'and' por 'or' no micro_ok",
    ),
]


def run_tests():
    """Roda pytest e retorna True se todos passam, False se algum falha."""
    result = subprocess.run(
        [sys.executable, "-m", "pytest", str(TESTS_DIR), "-x", "-q",
         "--tb=no", "--no-header"],
        capture_output=True,
        text=True,
        cwd=str(PROJECT_ROOT),
    )
    return result.returncode == 0


def apply_mutation(filepath, original, mutated):
    """Aplica mutação no arquivo. Retorna True se conseguiu."""
    content = filepath.read_text()
    if original not in content:
        return False
    filepath.write_text(content.replace(original, mutated, 1))
    return True


def restore_file(filepath, backup_path):
    """Restaura arquivo a partir do backup."""
    shutil.copy2(backup_path, filepath)


def main():
    killed = 0
    survived = 0
    skipped = 0
    results = []

    print("=" * 70)
    print("TESTE DE MUTAÇÃO — TCC USP Eng 2025")
    print("=" * 70)
    print(f"Total de mutações definidas: {len(MUTATIONS)}")
    print()

    for i, (filename, original, mutated, desc) in enumerate(MUTATIONS, 1):
        filepath = SRC_DIR / filename
        backup = filepath.with_suffix(".py.bak")

        # Backup
        shutil.copy2(filepath, backup)

        print(f"[{i:02d}/{len(MUTATIONS)}] {desc}")

        if not apply_mutation(filepath, original, mutated):
            restore_file(filepath, backup)
            backup.unlink()
            print(f"  → PULADO (string não encontrada)")
            skipped += 1
            results.append((desc, "PULADO"))
            continue

        tests_pass = run_tests()

        if tests_pass:
            print(f"  → SOBREVIVEU (testes não detectaram)")
            survived += 1
            results.append((desc, "SOBREVIVEU"))
        else:
            print(f"  → MORTO (testes detectaram)")
            killed += 1
            results.append((desc, "MORTO"))

        # Restaura original
        restore_file(filepath, backup)
        backup.unlink()

    total_valid = killed + survived
    score = (killed / total_valid * 100) if total_valid > 0 else 0

    print()
    print("=" * 70)
    print("RESUMO")
    print("=" * 70)
    print(f"Total de mutações:    {len(MUTATIONS)}")
    print(f"Mutações válidas:     {total_valid}")
    print(f"Mutantes mortos:      {killed}")
    print(f"Mutantes sobreviventes: {survived}")
    print(f"Mutações puladas:     {skipped}")
    print(f"Mutation Score:       {score:.1f}%")
    print()
    print("Detalhamento:")
    print("-" * 70)
    for desc, status in results:
        marker = "✓" if status == "MORTO" else ("⊘" if status == "PULADO" else "✗")
        print(f"  {marker} [{status:>11s}] {desc}")

    # Salva resultado em arquivo
    out_dir = PROJECT_ROOT / "results" / "quality"
    out_dir.mkdir(parents=True, exist_ok=True)
    with open(out_dir / "mutmut_results.txt", "w") as f:
        f.write("TESTE DE MUTAÇÃO — TCC USP Eng 2025\n")
        f.write("=" * 70 + "\n\n")
        f.write(f"Total de mutações:    {len(MUTATIONS)}\n")
        f.write(f"Mutações válidas:     {total_valid}\n")
        f.write(f"Mutantes mortos:      {killed}\n")
        f.write(f"Mutantes sobreviventes: {survived}\n")
        f.write(f"Mutações puladas:     {skipped}\n")
        f.write(f"Mutation Score:       {score:.1f}%\n\n")
        f.write("Detalhamento:\n")
        f.write("-" * 70 + "\n")
        for desc, status in results:
            f.write(f"  [{status:>11s}] {desc}\n")

    print(f"\nRelatório salvo em: {out_dir / 'mutmut_results.txt'}")
    return 0 if score >= 50 else 1


if __name__ == "__main__":
    sys.exit(main())
