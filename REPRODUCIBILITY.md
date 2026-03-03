# Reprodutibilidade Operacional

Este documento descreve como reproduzir **exatamente** os resultados apresentados
neste TCC. Qualquer pessoa com Docker instalado pode verificar a integridade dos
dados e replicar todos os experimentos com um único comando.

---

## 1. Checksums dos Datasets (SHA-256)

| Arquivo | SHA-256 |
|---------|---------|
| `data/MES_2023.csv` (bruto) | `9f825a1bdde61bce60332019b7f4c7d180aee59be43097d92e56030def3cf68a` |
| `data/MES_2023_clean.csv` (limpo) | `d408ae34309d2a6aaaa0afb2901f413453d5c43cceecff620ba58448f240486f` |

Para verificar manualmente:

```bash
sha256sum data/MES_2023.csv data/MES_2023_clean.csv
```

---

## 2. Ambiente de Execução

### Imagem Docker

| Campo | Valor |
|-------|-------|
| Imagem base | `python:3.11-slim` |
| Python | 3.11.x (conforme imagem base) |
| SO | Debian (slim) |

O `Dockerfile` na raiz do repositório define o ambiente completo e determinístico.

### Dependências Principais (requirements.txt)

| Pacote | Versão |
|--------|--------|
| backtrader | 1.9.78.123 |
| pandas | 2.2.2 |
| numpy | 1.26.4 |
| matplotlib | 3.9.0 |
| yfinance | 0.2.41 |
| pytest | 8.2.0 |
| hypothesis | 6.105.0 |

Todas as versões estão fixadas com `==` no `requirements.txt` para garantir
reprodutibilidade bit-a-bit.

---

## 3. Como Reproduzir os Resultados

### Pré-requisitos

- [Docker](https://docs.docker.com/get-docker/) instalado (versão 20.10+)
- `make` instalado (opcional, mas recomendado)
- ~2 GB de espaço em disco

### Opção A: Via Makefile (recomendado)

```bash
git clone https://github.com/lardezzoni/tcc_usp_eng_2025.git
cd tcc_usp_eng_2025
make run
```

### Opção B: Via shell script

```bash
git clone https://github.com/lardezzoni/tcc_usp_eng_2025.git
cd tcc_usp_eng_2025
chmod +x run_experiment.sh
./run_experiment.sh
```

### Opção C: Passo a passo manual

```bash
# 1. Build da imagem Docker
docker build -t tcc-backtest .

# 2. Limpar resultados anteriores
rm -rf results/baseline/* results/enhanced/* results/equity_curve_comparison.png

# 3. Rodar baseline
docker run --rm -v "$(pwd)/results:/app/results" tcc-backtest \
    python src/baseline_bot.py

# 4. Rodar enhanced
docker run --rm -v "$(pwd)/results:/app/results" tcc-backtest \
    python src/enchanced_bot.py

# 5. Gerar comparação
docker run --rm -v "$(pwd)/results:/app/results" tcc-backtest \
    python src/compare.py

# 6. Verificar checksums
sha256sum results/baseline/metrics.csv results/enhanced/metrics.csv
```

---

## 4. Como Verificar que os Resultados são Idênticos

Após executar o experimento, compare os checksums gerados com os checksums de
referência salvos em `checksums.txt`:

### Verificação automática

```bash
make verify
```

### Verificação manual

```bash
sha256sum -c checksums.txt
```

Se todos os arquivos estiverem corretos, a saída será:

```
data/MES_2023.csv: OK
data/MES_2023_clean.csv: OK
results/baseline/metrics.csv: OK
results/enhanced/metrics.csv: OK
...
```

Se algum arquivo diferir, a saída indicará `FAILED` para esse arquivo.

### O que pode causar diferenças

- **Gráficos PNG**: Imagens podem apresentar diferenças de bytes entre execuções
  devido a metadados de renderização (timestamp, versão da lib). Os **dados numéricos**
  (metrics.csv) devem ser sempre idênticos.
- **Versão de dependências**: Certifique-se de que está usando as versões exatas
  do `requirements.txt`. O Docker garante isso automaticamente.
- **Sistema operacional**: Execute sempre via Docker para eliminar diferenças
  entre plataformas.

---

## 5. Estrutura dos Artefatos Gerados

```
results/
├── baseline/
│   ├── baseline_candlestick.png   # Gráfico de candles com sinais
│   └── metrics.csv                # Sharpe, Sortino, MaxDrawdown, RetornoAnual
├── enhanced/
│   ├── enhanced_candlestick.png   # Gráfico de candles com sinais
│   └── metrics.csv                # Sharpe, Sortino, MaxDrawdown, RetornoAnual
└── equity_curve_comparison.png    # Curva de capital comparativa
```

---

## 6. Checksums de Referência dos Resultados

Os checksums completos de todos os artefatos estão no arquivo `checksums.txt`
na raiz do repositório. Os valores de referência dos resultados principais são:

| Artefato | SHA-256 |
|----------|---------|
| `results/baseline/metrics.csv` | `fc5c9690fcf9789f0f8cc5f49b43dbdae04322c67f45f077379630e1f392e759` |
| `results/enhanced/metrics.csv` | `3a812903869e6d096525a3a47a4ae5d753b52cb57164c43fd2a8bc0c49105b66` |
