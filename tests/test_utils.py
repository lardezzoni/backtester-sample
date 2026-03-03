"""
Testes unitários para src/utils.py — prepare_csv.
"""
import os
import tempfile

import pandas as pd
import pytest

from utils import prepare_csv


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _write_csv(path, content):
    """Escreve conteúdo CSV no caminho dado."""
    with open(path, "w") as f:
        f.write(content)


# ---------------------------------------------------------------------------
# Testes de prepare_csv
# ---------------------------------------------------------------------------

class TestPrepareCsv:
    def test_output_has_expected_columns(self):
        """CSV limpo deve ter colunas: datetime, Open, High, Low, Close, Volume."""
        with tempfile.TemporaryDirectory() as tmp:
            input_path = os.path.join(tmp, "raw.csv")
            output_path = os.path.join(tmp, "clean.csv")
            _write_csv(input_path, (
                "Date,Open,High,Low,Close,Volume\n"
                "2023-01-03,100,110,90,105,1000\n"
                "2023-01-04,105,115,95,110,1200\n"
            ))
            prepare_csv(input_path, output_path)
            df = pd.read_csv(output_path)
            expected = {"datetime", "Open", "High", "Low", "Close", "Volume"}
            assert set(df.columns) == expected

    def test_dates_are_datetime(self):
        """Coluna datetime deve ser conversível para datetime."""
        with tempfile.TemporaryDirectory() as tmp:
            input_path = os.path.join(tmp, "raw.csv")
            output_path = os.path.join(tmp, "clean.csv")
            _write_csv(input_path, (
                "Date,Open,High,Low,Close,Volume\n"
                "2023-01-03,100,110,90,105,1000\n"
                "2023-06-15,105,115,95,110,1200\n"
            ))
            prepare_csv(input_path, output_path)
            df = pd.read_csv(output_path, parse_dates=["datetime"])
            assert pd.api.types.is_datetime64_any_dtype(df["datetime"])

    def test_drops_ticker_column(self):
        """Se houver coluna Ticker, ela deve ser removida."""
        with tempfile.TemporaryDirectory() as tmp:
            input_path = os.path.join(tmp, "raw.csv")
            output_path = os.path.join(tmp, "clean.csv")
            _write_csv(input_path, (
                "Ticker,Date,Open,High,Low,Close,Volume\n"
                "ES,2023-01-03,100,110,90,105,1000\n"
            ))
            prepare_csv(input_path, output_path)
            df = pd.read_csv(output_path)
            assert "Ticker" not in df.columns

    def test_drops_na_rows(self):
        """Linhas com NaN devem ser removidas."""
        with tempfile.TemporaryDirectory() as tmp:
            input_path = os.path.join(tmp, "raw.csv")
            output_path = os.path.join(tmp, "clean.csv")
            _write_csv(input_path, (
                "Date,Open,High,Low,Close,Volume\n"
                "2023-01-03,100,110,90,105,1000\n"
                "2023-01-04,,,,,\n"
                "2023-01-05,105,115,95,110,1200\n"
            ))
            prepare_csv(input_path, output_path)
            df = pd.read_csv(output_path)
            assert len(df) == 2

    def test_sorts_by_datetime(self):
        """O CSV deve estar ordenado por datetime."""
        with tempfile.TemporaryDirectory() as tmp:
            input_path = os.path.join(tmp, "raw.csv")
            output_path = os.path.join(tmp, "clean.csv")
            _write_csv(input_path, (
                "Date,Open,High,Low,Close,Volume\n"
                "2023-06-01,105,115,95,110,1200\n"
                "2023-01-01,100,110,90,105,1000\n"
            ))
            prepare_csv(input_path, output_path)
            df = pd.read_csv(output_path, parse_dates=["datetime"])
            assert df["datetime"].iloc[0] < df["datetime"].iloc[1]

    def test_returns_output_path(self):
        """prepare_csv retorna o caminho do output."""
        with tempfile.TemporaryDirectory() as tmp:
            input_path = os.path.join(tmp, "raw.csv")
            output_path = os.path.join(tmp, "out", "clean.csv")
            _write_csv(input_path, (
                "Date,Open,High,Low,Close,Volume\n"
                "2023-01-03,100,110,90,105,1000\n"
            ))
            result = prepare_csv(input_path, output_path)
            assert result == output_path
            assert os.path.isfile(output_path)

    def test_raises_on_missing_date_column(self):
        """Sem coluna de data → ValueError."""
        with tempfile.TemporaryDirectory() as tmp:
            input_path = os.path.join(tmp, "raw.csv")
            output_path = os.path.join(tmp, "clean.csv")
            _write_csv(input_path, (
                "Open,High,Low,Close,Volume\n"
                "100,110,90,105,1000\n"
            ))
            with pytest.raises((ValueError, KeyError)):
                prepare_csv(input_path, output_path)
