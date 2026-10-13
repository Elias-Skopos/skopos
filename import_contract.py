"""CSV contract: preserve text and reject ambiguous numeric/date formats."""
import csv
from datetime import date, datetime
from decimal import Decimal
from numbers import Number
from io import StringIO
import re
import math

import pandas as pd


def read_csv(raw: bytes) -> pd.DataFrame:
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = raw.decode("latin-1")
    try:
        records = list(csv.reader(StringIO(text), delimiter=";", strict=True))
    except csv.Error as exc:
        raise ValueError("CSV inválido. Use ponto e vírgula (;) para separar as colunas, como nos modelos.") from exc
    if not records or len(records) < 2:
        raise ValueError("O CSV deve conter um cabeçalho e ao menos uma linha de dados.")
    if len(records[0]) < 2:
        raise ValueError("Use ponto e vírgula (;) para separar as colunas do CSV. A vírgula é usada somente nos números.")
    headers = [name.strip().lower() for name in records[0]]
    if len(headers) != len(set(headers)):
        raise ValueError("O cabeçalho contém colunas repetidas. Cada coluna deve aparecer uma única vez.")
    for line, record in enumerate(records[1:], 2):
        if len(record) != len(headers):
            raise ValueError(f"Linha {line}: encontrei {len(record)} campos; o cabeçalho tem {len(headers)}. Confira o separador e as aspas.")
    return pd.DataFrame(records[1:], columns=headers)


def brazilian_date(value):
    text = str(value).strip()
    if not re.fullmatch(r"\d{2}-\d{2}-\d{4}", text):
        raise ValueError("use uma data válida no formato DD-MM-AAAA (ex.: 12-10-2026)")
    return datetime.strptime(text, "%d-%m-%Y").date().isoformat()


def brazilian_number(value, decimal_places=None):
    text = str(value).strip()
    decimals = r"[0-9]+" if decimal_places is None else r"[0-9]{1," + str(decimal_places) + "}"
    if not re.fullmatch(r"[0-9]+(?:," + decimals + r")?", text):
        raise ValueError("use vírgula decimal, sem moeda ou separador de milhar (ex.: 1234,56)")
    normalized = text.replace(",", ".")
    if not math.isfinite(float(normalized)):
        raise ValueError("número fora do limite suportado")
    return normalized


def validate_format(data, columns, required, numeric, date_field):
    errors = []
    unknown = [str(name) for name in data.columns if name not in columns]
    if unknown:
        errors.append(f"Colunas não reconhecidas: {', '.join(unknown)}. Use os nomes do modelo.")
    if data.columns.duplicated().any():
        return ["O cabeçalho contém colunas repetidas."]
    for line, (_, row) in enumerate(data.iterrows(), 2):
        for field in columns:
            if field not in data:
                continue
            value = "" if pd.isna(row[field]) else str(row[field]).strip()
            reason = None
            if field in required and not value:
                reason = "campo obrigatório vazio"
            elif field in numeric and value:
                try:
                    brazilian_number(value)
                except ValueError as exc:
                    reason = str(exc)
            elif field == date_field and value:
                try:
                    brazilian_date(value)
                except ValueError:
                    reason = "use uma data válida no formato DD-MM-AAAA (ex.: 12-10-2026)"
            elif field == "status" and value and value not in {"Concluído", "Cancelado", "Devolvido"}:
                reason = "use Concluído, Cancelado ou Devolvido"
            if reason:
                errors.append(f"Linha {line}, coluna '{field}', valor {value[:80]!r}: {reason}.")
    return errors


DATE_COLUMNS = {"data", "data_ref", "data_pagamento", "vencimento"}
NUMBER_COLUMNS = {"quantidade", "quantidade_devolvida", "preco_unitario", "custo_unitario", "desconto",
                  "impostos", "frete_cobrado", "frete_custo", "estoque_minimo", "valor", "total_vendas"}


def brazilian_frame(frame):
    """Format importable fields only; keep identifiers and free text untouched."""
    data = frame.copy()
    for column in data:
        if column in DATE_COLUMNS:
            def format_date(value):
                if pd.isna(value) or value == "":
                    return ""
                if isinstance(value, (date, datetime, pd.Timestamp)):
                    return value.strftime("%d-%m-%Y")
                if re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(value)):
                    return date.fromisoformat(str(value)).strftime("%d-%m-%Y")
                if re.fullmatch(r"\d{2}/\d{2}/\d{4}", str(value)):
                    return datetime.strptime(str(value), "%d/%m/%Y").strftime("%d-%m-%Y")
                return str(value)
            data[column] = data[column].map(format_date)
        elif column in NUMBER_COLUMNS:
            def format_number(value):
                if pd.isna(value) or value == "":
                    return ""
                text = str(value)
                if isinstance(value, (Number, Decimal)) or re.fullmatch(r"[0-9]+(?:\.[0-9]+)?", text):
                    return text.replace(".", ",")
                return text
            data[column] = data[column].map(format_number)
    return data


def csv_template(columns, examples=None):
    data = pd.DataFrame(examples or [], columns=columns)
    return brazilian_frame(data).to_csv(index=False, sep=";", decimal=",").encode("utf-8-sig")
