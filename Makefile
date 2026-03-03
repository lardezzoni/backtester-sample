# =============================================================================
# Makefile — TCC USP Engenharia 2025
# Robôs de Negociação Algorítmica — Reprodutibilidade Operacional
# =============================================================================

.PHONY: run clean checksums verify help

IMAGE_NAME := tcc-backtest

help: ## Exibe esta mensagem de ajuda
	@echo "Targets disponíveis:"
	@echo ""
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  make %-12s %s\n", $$1, $$2}'
	@echo ""

run: ## Executa o experimento completo (build + baseline + enhanced + comparação)
	@./run_experiment.sh

clean: ## Apaga todos os resultados gerados (results/baseline, results/enhanced, comparação)
	@echo "Limpando resultados..."
	rm -rf results/baseline/*
	rm -rf results/enhanced/*
	rm -f  results/equity_curve_comparison.png
	@echo "Resultados limpos."

checksums: ## Calcula e exibe checksums SHA-256 de todos os artefatos (data + results)
	@echo "=== Checksums SHA-256 ==="
	@echo ""
	@echo "--- Datasets ---"
	@sha256sum data/MES_2023.csv
	@sha256sum data/MES_2023_clean.csv
	@echo ""
	@echo "--- Resultados Baseline ---"
	@find results/baseline -type f 2>/dev/null | sort | xargs sha256sum 2>/dev/null || echo "  (sem arquivos)"
	@echo ""
	@echo "--- Resultados Enhanced ---"
	@find results/enhanced -type f 2>/dev/null | sort | xargs sha256sum 2>/dev/null || echo "  (sem arquivos)"
	@echo ""
	@echo "--- Comparação ---"
	@sha256sum results/equity_curve_comparison.png 2>/dev/null || echo "  (sem arquivo)"

verify: ## Compara checksums gerados com os checksums de referência (checksums.txt)
	@echo "Verificando checksums contra referência (checksums.txt)..."
	@echo ""
	@sha256sum -c checksums.txt && echo "" && echo "TODOS OS CHECKSUMS CONFEREM." || \
		(echo "" && echo "ATENCAO: Alguns checksums NAO conferem!" && exit 1)
