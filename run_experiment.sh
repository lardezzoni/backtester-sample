#!/usr/bin/env bash
# =============================================================================
# run_experiment.sh — Reproduz todos os experimentos do TCC de ponta a ponta
#
# Uso:
#   chmod +x run_experiment.sh
#   ./run_experiment.sh
#
# Pré-requisito: Docker instalado e rodando
# =============================================================================
set -euo pipefail

IMAGE_NAME="tcc-backtest"
PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"

echo "=============================================="
echo "  TCC USP — Reprodutibilidade Operacional"
echo "=============================================="
echo ""

# ----- 1. Verificar integridade dos dados de entrada -----
echo "[1/6] Verificando integridade dos dados de entrada..."
EXPECTED_RAW="9f825a1bdde61bce60332019b7f4c7d180aee59be43097d92e56030def3cf68a"
ACTUAL_RAW=$(sha256sum "${PROJECT_DIR}/data/MES_2023.csv" | awk '{print $1}')

if [ "$ACTUAL_RAW" != "$EXPECTED_RAW" ]; then
    echo "ERRO: Checksum do dataset bruto nao confere!"
    echo "  Esperado: ${EXPECTED_RAW}"
    echo "  Obtido:   ${ACTUAL_RAW}"
    exit 1
fi
echo "  data/MES_2023.csv: OK"
echo ""

# ----- 2. Limpar resultados anteriores -----
echo "[2/6] Limpando resultados anteriores..."
rm -rf "${PROJECT_DIR}/results/baseline/"*
rm -rf "${PROJECT_DIR}/results/enhanced/"*
rm -f  "${PROJECT_DIR}/results/equity_curve_comparison.png"
echo "  Pasta results/baseline/ limpa"
echo "  Pasta results/enhanced/ limpa"
echo "  results/equity_curve_comparison.png removido"
echo ""

# ----- 3. Build da imagem Docker -----
echo "[3/6] Construindo imagem Docker '${IMAGE_NAME}'..."
docker build -t "${IMAGE_NAME}" "${PROJECT_DIR}"
echo "  Build concluido."
echo ""

# ----- 4. Rodar baseline_bot.py -----
echo "[4/6] Executando baseline_bot.py..."
docker run --rm \
    -v "${PROJECT_DIR}/results:/app/results" \
    "${IMAGE_NAME}" \
    python src/baseline_bot.py
echo "  Baseline concluido. Resultados em results/baseline/"
echo ""

# ----- 5. Rodar enchanced_bot.py -----
echo "[5/6] Executando enchanced_bot.py (enhanced bot)..."
docker run --rm \
    -v "${PROJECT_DIR}/results:/app/results" \
    "${IMAGE_NAME}" \
    python src/enchanced_bot.py
echo "  Enhanced concluido. Resultados em results/enhanced/"
echo ""

# ----- 5b. Gerar comparacao (equity curve) -----
echo "[5b/6] Gerando comparacao de equity curves..."
docker run --rm \
    -v "${PROJECT_DIR}/results:/app/results" \
    -v "${PROJECT_DIR}/data:/app/data" \
    "${IMAGE_NAME}" \
    python src/compare.py
echo "  Comparacao concluida."
echo ""

# ----- 6. Calcular e exibir checksums dos outputs -----
echo "[6/6] Checksums SHA-256 dos artefatos gerados:"
echo "----------------------------------------------"
echo "--- Datasets ---"
sha256sum "${PROJECT_DIR}"/data/MES_2023.csv
sha256sum "${PROJECT_DIR}"/data/MES_2023_clean.csv
echo ""
echo "--- Resultados Baseline ---"
find "${PROJECT_DIR}/results/baseline" -type f | sort | xargs sha256sum
echo ""
echo "--- Resultados Enhanced ---"
find "${PROJECT_DIR}/results/enhanced" -type f | sort | xargs sha256sum
echo ""
echo "--- Comparacao ---"
if [ -f "${PROJECT_DIR}/results/equity_curve_comparison.png" ]; then
    sha256sum "${PROJECT_DIR}/results/equity_curve_comparison.png"
fi

echo ""
echo "=============================================="
echo "  Experimento concluido com sucesso!"
echo "  Para verificar reprodutibilidade, execute:"
echo "    make verify"
echo "  ou"
echo "    sha256sum -c checksums.txt"
echo "=============================================="
