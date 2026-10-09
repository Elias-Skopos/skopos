from __future__ import annotations

from datetime import date
import ipaddress
import math
import os
import socket
from urllib.parse import urljoin, urlparse

import requests


class HorusAPIError(Exception):
    """A safe, user-facing error from a Horus API request."""


def _base_url(value: str) -> str:
    value = value.strip()
    parsed = urlparse(value)
    if (
        parsed.scheme.lower() not in {"http", "https"}
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
    ):
        raise HorusAPIError("Informe a URL base do Horus, iniciando com http:// ou https://.")

    hostname = parsed.hostname.rstrip(".").lower()
    allowed_hosts = {
        host.strip().rstrip(".").lower()
        for host in os.environ.get("HORUS_ALLOWED_HOSTS", "").split(",")
        if host.strip()
    }
    if allowed_hosts and hostname not in allowed_hosts:
        raise HorusAPIError("Este host não está na lista HORUS_ALLOWED_HOSTS autorizada pelo servidor.")

    allow_private = os.environ.get("HORUS_ALLOW_PRIVATE_NETWORK", "").lower() in {"1", "true", "yes"}
    try:
        try:
            address = ipaddress.ip_address(hostname)
            addresses = [address]
        except ValueError:
            port = parsed.port or (443 if parsed.scheme.lower() == "https" else 80)
            address_rows = socket.getaddrinfo(hostname, port, type=socket.SOCK_STREAM)
            addresses = [ipaddress.ip_address(row[4][0].split("%")[0]) for row in address_rows]
    except (OSError, ValueError) as exc:
        raise HorusAPIError("Não foi possível validar o host da URL do Horus.") from exc

    if not addresses:
        raise HorusAPIError("O host da URL do Horus não resolveu para um endereço válido.")
    private_addresses = [address for address in addresses if not address.is_global]
    public_addresses = [address for address in addresses if address.is_global]
    if private_addresses and public_addresses:
        raise HorusAPIError("O host do Horus resolve para endereços públicos e privados ao mesmo tempo.")
    if not allow_private and private_addresses:
        raise HorusAPIError(
            "A URL do Horus aponta para uma rede privada ou local. Para uma instalação local confiável, "
            "o administrador deve definir HORUS_ALLOW_PRIVATE_NETWORK=true no servidor."
        )
    if parsed.scheme.lower() == "http" and public_addresses:
        raise HorusAPIError(
            "A conexão Horus para hosts públicos exige HTTPS. HTTP só pode ser usado em rede privada "
            "com HORUS_ALLOW_PRIVATE_NETWORK=true."
        )
    return value.rstrip("/") + "/"


def _get_json(
    base_url: str,
    method: str,
    username: str,
    password: str,
    params: dict[str, str | int],
) -> list[dict] | dict:
    url = urljoin(_base_url(base_url), method.lstrip("/"))
    try:
        response = requests.get(
            url,
            params=params,
            auth=(username, password),
            headers={"Accept": "application/json"},
            timeout=(5, 30),
            allow_redirects=False,
        )
        if 300 <= response.status_code < 400:
            raise HorusAPIError("O Horus tentou redirecionar a chamada. Confira a URL base configurada.")
        if response.status_code in {401, 403}:
            raise HorusAPIError("A autenticação foi recusada. Confira usuário, senha e permissões de leitura.")
        response.raise_for_status()
        if len(response.content) > 25_000_000:
            raise HorusAPIError("A resposta ultrapassou o limite de 25 MB. Reduza o período consultado.")
        payload = response.json()
    except HorusAPIError:
        raise
    except requests.exceptions.JSONDecodeError as exc:
        raise HorusAPIError("O Horus respondeu com conteúdo que não é JSON válido.") from exc
    except requests.RequestException as exc:
        raise HorusAPIError(f"Não foi possível acessar o Horus ({exc.__class__.__name__}).") from exc

    if not isinstance(payload, (list, dict)):
        raise HorusAPIError("A resposta do Horus precisa ser uma lista ou um objeto JSON.")
    return payload


def _records(payload: list[dict] | dict) -> list[dict]:
    if isinstance(payload, list):
        records = payload
    else:
        records = next(
            (payload[key] for key in ("data", "items", "records", "result") if isinstance(payload.get(key), list)),
            None,
        )
        if records is None:
            raise HorusAPIError("O Horus não retornou uma lista de registros no formato esperado.")
    if not all(isinstance(row, dict) for row in records):
        raise HorusAPIError("A resposta contém registros em formato inesperado.")
    return records


def fetch_pages(
    base_url: str,
    method: str,
    username: str,
    password: str,
    filters: dict[str, str],
    *,
    page_size: int = 200,
    max_pages: int = 50,
) -> list[dict]:
    records: list[dict] = []
    for page in range(max_pages):
        params: dict[str, str | int] = {**filters, "OFFSET": page * page_size, "LIMIT": page_size}
        payload = _get_json(base_url, method, username, password, params)
        batch = _records(payload)
        records.extend(batch)
        if len(batch) < page_size:
            return records
    raise HorusAPIError(
        f"A consulta excedeu {max_pages * page_size:,} registros. Reduza o período e tente novamente."
    )


def test_connection(base_url: str, username: str, password: str) -> tuple[int, int | None]:
    payload = _get_json(base_url, "Busca_Acervo", username, password, {"LIMIT": 1})
    return len(_records(payload)), 200


def fetch_orders_and_items(
    base_url: str,
    username: str,
    password: str,
    company: str,
    branch: str,
    start: date,
    end: date,
    status: str,
) -> tuple[list[dict], list[dict]]:
    order_filters = {
        "COD_EMPRESA": company,
        "COD_FILIAL": branch,
        "DAT_PEDIDO_INI": start.strftime("%d/%m/%Y"),
        "DAT_PEDIDO_FIM": end.strftime("%d/%m/%Y"),
    }
    if status:
        order_filters["STA_PEDIDO"] = status

    orders = fetch_pages(base_url, "Busca_PedidosVenda", username, password, order_filters)
    item_filters = {
        "COD_EMPRESA": company,
        "COD_FILIAL": branch,
        "DAT_PEDIDO_INI": start.strftime("%d/%m/%Y 00:00:00"),
        "DAT_PEDIDO_FIM": end.strftime("%d/%m/%Y 23:59:59"),
    }
    items = fetch_pages(base_url, "Busca_ItensPedidosVenda", username, password, item_filters)
    return orders, items


def _number(value: object) -> float:
    if value is None or value == "":
        return 0.0
    if isinstance(value, str):
        value = value.strip()
        if not value:
            return 0.0
        if "," in value:
            value = value.replace(".", "").replace(",", ".")
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise HorusAPIError("O Horus retornou um valor numérico inválido. Confira os dados da consulta.") from exc
    if not math.isfinite(number):
        raise HorusAPIError("O Horus retornou um valor numérico não finito. Confira os dados da consulta.")
    return number


def sales_preview(orders: list[dict], items: list[dict], selected_status: str) -> list[dict]:
    accepted_orders = {
        (str(order.get("COD_EMPRESA", "")), str(order.get("COD_FILIAL", "")), str(order.get("COD_PED_VENDA", ""))): order
        for order in orders
        if not selected_status or str(order.get("STATUS_PEDIDO_VENDA", order.get("STA_PEDIDO", ""))) == selected_status
    }
    result: list[dict] = []
    seen_orders: set[str] = set()
    for item in items:
        key = (str(item.get("COD_EMPRESA", "")), str(item.get("COD_FILIAL", "")), str(item.get("COD_PED_VENDA", "")))
        order = accepted_orders.get(key)
        if order is None:
            continue
        quantity = _number(item.get("QTD_ATENDIDA"))
        if quantity <= 0:
            quantity = _number(item.get("QT_PEDIDA"))
        unit_price = _number(item.get("VLR_PRECO"))
        line_net = _number(item.get("VLR_LIQUIDO"))
        discount = _number(item.get("VLR_DESCONTO"))
        if line_net <= 0 and discount <= 0:
            line_net = unit_price * quantity
        elif line_net <= 0:
            line_net = max(unit_price * quantity - discount, 0.0)
        # Use the net line total to derive a total line discount, avoiding assumptions
        # about whether the API's discount is represented as an amount or percentage.
        discount = max(unit_price * quantity - line_net, 0.0)
        order_id = "-".join(key)
        first_item_in_order = order_id not in seen_orders
        seen_orders.add(order_id)
        cost_value = item.get("VLR_CUSTO", item.get("CUSTO_UNITARIO", ""))
        result.append(
            {
                "pedido_id": order_id,
                "data": order.get("DAT_PEDIDO", ""),
                "cliente": order.get("NOM_CLI", ""),
                "cliente_id": order.get("COD_CLI", ""),
                "canal": order.get("COD_METODO", ""),
                "cidade": "",
                "uf": "",
                "sku": item.get("COD_ITEM", ""),
                "titulo": item.get("NOM_ITEM", ""),
                "categoria": "",
                "quantidade": quantity,
                "quantidade_devolvida": 0,
                "preco_unitario": unit_price,
                "custo_unitario": _number(cost_value) if cost_value not in (None, "") else "",
                "desconto": discount,
                "impostos": 0,
                "frete_cobrado": _number(order.get("VLR_FRETE")) if first_item_in_order else 0,
                "frete_custo": 0,
                "status": "Cancelado" if str(order.get("STATUS_PEDIDO_VENDA", "")) == "CAN" else "Concluído",
                "valor_liquido_horus": line_net,
            }
        )
    grouped: dict[tuple[str, str], list[dict]] = {}
    for row in result:
        grouped.setdefault((row["pedido_id"], str(row["sku"])), []).append(row)

    consolidated: list[dict] = []
    for matching_rows in grouped.values():
        row = matching_rows[0].copy()
        quantity_total = sum(_number(item["quantidade"]) for item in matching_rows)
        gross_total = sum(_number(item["preco_unitario"]) * _number(item["quantidade"]) for item in matching_rows)
        net_total = sum(_number(item["valor_liquido_horus"]) for item in matching_rows)
        row["quantidade"] = quantity_total
        row["preco_unitario"] = gross_total / quantity_total if quantity_total else 0
        row["desconto"] = max(gross_total - net_total, 0.0)
        costs = [_number(item["custo_unitario"]) for item in matching_rows]
        row["custo_unitario"] = sum(cost * _number(item["quantidade"]) for cost, item in zip(costs, matching_rows)) / quantity_total if quantity_total and all(item["custo_unitario"] not in (None, "") for item in matching_rows) else ""
        row["valor_liquido_horus"] = net_total
        consolidated.append(row)
    return consolidated
