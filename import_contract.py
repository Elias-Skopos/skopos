"""CSV contract: preserve text and reject ambiguous numeric/date formats."""
import csv
from datetime import date
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
        dialect = csv.Sniffer().sniff(text[:8192], delimiters=",;")
        records = list(csv.reader(StringIO(text), dialect, strict=True))
    except csv.Error as exc:
        raise ValueError("CSV inválido. Use vírgula ou ponto e vírgula para separar as colunas, como nos modelos.") from exc
    if not records or len(records) < 2:
        raise ValueError("O CSV deve conter um cabeçalho e ao menos uma linha de dados.")
    headers = [name.strip().lower() for name in records[0]]
    if len(headers) != len(set(headers)):
        raise ValueError("O cabeçalho contém colunas repetidas. Cada coluna deve aparecer uma única vez.")
    for line, record in enumerate(records[1:], 2):
        if len(record) != len(headers):
            raise ValueError(f"Linha {line}: encontrei {len(record)} campos; o cabeçalho tem {len(headers)}. Confira o separador e as aspas.")
    return pd.DataFrame(records[1:], columns=headers)


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
                if not re.fullmatch(r"[0-9]+(?:\.[0-9]+)?", value):
                    reason = "use número não negativo, sem separador de milhar, com ponto decimal (ex.: 1234.56)"
                elif not math.isfinite(float(value)):
                    reason = "número fora do limite suportado"
            elif field == date_field and value:
                try:
                    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
                        raise ValueError
                    date.fromisoformat(value)
                except ValueError:
                    reason = "use uma data válida no formato AAAA-MM-DD"
            elif field == "status" and value and value not in {"Concluído", "Cancelado", "Devolvido"}:
                reason = "use Concluído, Cancelado ou Devolvido"
            if reason:
                errors.append(f"Linha {line}, coluna '{field}', valor {value[:80]!r}: {reason}.")
    return errors


def csv_template(columns, examples=None):
    return pd.DataFrame(examples or [], columns=columns).to_csv(index=False, sep=";").encode("utf-8-sig")
