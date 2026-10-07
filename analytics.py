from __future__ import annotations

from datetime import date

import pandas as pd


SALES_COLUMNS = [
    "pedido_id", "data", "cliente", "cliente_id", "canal", "cidade", "uf", "sku", "titulo", "categoria",
    "quantidade", "quantidade_devolvida", "preco_unitario", "custo_unitario", "desconto",
    "impostos", "frete_cobrado", "frete_custo", "status",
]
SALES_REQUIRED = ["pedido_id", "data", "sku", "titulo", "quantidade", "preco_unitario", "custo_unitario"]
SALES_NUMERIC_DEFAULTS = {
    "quantidade_devolvida": 0.0,
    "desconto": 0.0,
    "impostos": 0.0,
    "frete_cobrado": 0.0,
    "frete_custo": 0.0,
}
INVENTORY_COLUMNS = ["data_ref", "sku", "titulo", "quantidade", "custo_unitario", "estoque_minimo"]
INVENTORY_REQUIRED = ["data_ref", "sku", "titulo", "quantidade", "custo_unitario"]


def _as_text(series: pd.Series) -> pd.Series:
    return series.fillna("").astype(str).str.strip()


def _as_number(series: pd.Series) -> pd.Series:
    text = series.fillna("").astype(str).str.strip()
    comma_values = text.str.contains(",", regex=False)
    text.loc[comma_values] = (
        text.loc[comma_values]
        .str.replace(".", "", regex=False)
        .str.replace(",", ".", regex=False)
    )
    return pd.to_numeric(text, errors="coerce")


def _parse_date(series: pd.Series) -> pd.Series:
    """Parse ISO dates and Brazilian dates without swapping ISO month/day."""
    text = _as_text(series)
    iso = text.str.fullmatch(r"\d{4}-\d{2}-\d{2}")
    parsed = pd.Series(pd.NaT, index=series.index, dtype="datetime64[ns]")
    parsed.loc[iso] = pd.to_datetime(text.loc[iso], format="%Y-%m-%d", errors="coerce")
    parsed.loc[~iso] = pd.to_datetime(text.loc[~iso], format="mixed", dayfirst=True, errors="coerce")
    return parsed


def normalize_sales_frame(frame: pd.DataFrame) -> tuple[list[dict], list[str]]:
    """Validate rows using the documented Skopos sales CSV/API contract."""
    data = frame.copy().dropna(how="all")
    data.columns = [str(column).strip().lower() for column in data.columns]
    missing = [name for name in SALES_REQUIRED if name not in data.columns]
    if missing:
        return [], [f"Colunas obrigatórias ausentes: {', '.join(missing)}."]
    if data.empty:
        return [], ["O arquivo não contém linhas de venda."]

    for name in SALES_COLUMNS:
        if name not in data:
            data[name] = SALES_NUMERIC_DEFAULTS.get(name, "Concluído" if name == "status" else "")

    for name in ["pedido_id", "sku", "titulo", "cliente", "cliente_id", "canal", "cidade", "uf", "categoria", "status"]:
        data[name] = _as_text(data[name])
    data["status"] = data["status"].replace("", "Concluído")
    data["data"] = _parse_date(data["data"]).dt.strftime("%Y-%m-%d")

    numeric_fields = ["quantidade", "quantidade_devolvida", "preco_unitario", "custo_unitario", "desconto", "impostos", "frete_cobrado", "frete_custo"]
    for name in numeric_fields:
        data[name] = _as_number(data[name])
    for name in SALES_NUMERIC_DEFAULTS:
        data[name] = data[name].fillna(0)

    errors: list[str] = []
    if (data["pedido_id"] == "").any() or (data["sku"] == "").any() or (data["titulo"] == "").any():
        errors.append("Pedido, SKU e título não podem ficar vazios.")
    if data["data"].isna().any():
        errors.append("Há datas inválidas. Use AAAA-MM-DD ou DD/MM/AAAA.")
    if data["quantidade"].isna().any() or data["preco_unitario"].isna().any() or data["custo_unitario"].isna().any():
        errors.append("Quantidade, preço unitário e custo unitário precisam ser números válidos.")
    if data[numeric_fields].isna().any().any():
        errors.append("Há valores numéricos inválidos nas colunas de venda.")
    if (data[numeric_fields] < 0).any().any():
        errors.append("Valores e quantidades não podem ser negativos.")
    if (data["quantidade_devolvida"] > data["quantidade"]).any():
        errors.append("A quantidade devolvida não pode exceder a quantidade vendida.")
    if data.duplicated(["pedido_id", "sku"]).any():
        errors.append("Há SKU repetido no mesmo pedido. Consolide em uma única linha por pedido e SKU.")
    for field in ("frete_cobrado", "frete_custo"):
        nonzero_freight = data[data[field] > 0].groupby("pedido_id").size()
        if (nonzero_freight > 1).any():
            errors.append(f"{field} é um valor do pedido e deve aparecer em apenas uma linha por pedido.")
    if errors:
        return [], errors

    return data[SALES_COLUMNS].to_dict(orient="records"), []


def normalize_inventory_frame(frame: pd.DataFrame) -> tuple[list[dict], list[str]]:
    data = frame.copy().dropna(how="all")
    data.columns = [str(column).strip().lower() for column in data.columns]
    missing = [name for name in INVENTORY_REQUIRED if name not in data.columns]
    if missing:
        return [], [f"Colunas obrigatórias ausentes: {', '.join(missing)}."]
    if data.empty:
        return [], ["O arquivo não contém linhas de estoque."]
    if "estoque_minimo" not in data:
        data["estoque_minimo"] = 0
    for name in ["sku", "titulo"]:
        data[name] = _as_text(data[name])
    data["data_ref"] = _parse_date(data["data_ref"]).dt.strftime("%Y-%m-%d")
    numeric_fields = ["quantidade", "custo_unitario", "estoque_minimo"]
    for name in numeric_fields:
        data[name] = _as_number(data[name])
    data["estoque_minimo"] = data["estoque_minimo"].fillna(0)
    errors: list[str] = []
    if (data["sku"] == "").any() or (data["titulo"] == "").any():
        errors.append("SKU e título não podem ficar vazios.")
    if data["data_ref"].isna().any():
        errors.append("Há datas de inventário inválidas. Use AAAA-MM-DD ou DD/MM/AAAA.")
    if data[numeric_fields].isna().any().any():
        errors.append("Quantidade, custo e estoque mínimo precisam ser números válidos.")
    if (data[numeric_fields] < 0).any().any():
        errors.append("Valores de estoque não podem ser negativos.")
    if data.duplicated(["data_ref", "sku"]).any():
        errors.append("Há SKU repetido na mesma data de inventário.")
    if errors:
        return [], errors
    return data[INVENTORY_COLUMNS].to_dict(orient="records"), []


def calculate_sales(frame: pd.DataFrame, start: date, end: date) -> dict | None:
    if frame.empty:
        return None
    sales = frame.copy()
    sales["sale_date"] = pd.to_datetime(sales["sale_date"], errors="coerce")
    sales = sales[sales["sale_date"].dt.date.between(start, end)].copy()
    if sales.empty:
        return None

    sales["cancelled"] = sales["status"].astype(str).str.lower().str.contains("cancel|estorn", regex=True, na=False)
    sales["gross"] = sales["quantity"] * sales["unit_price"]
    sales["returns"] = sales["returned_quantity"] * sales["unit_price"]
    sales["net_revenue"] = sales["gross"] - sales["returns"] - sales["discount"] - sales["taxes"]
    sales["net_units"] = sales["quantity"] - sales["returned_quantity"]
    sales["cogs"] = sales["net_units"] * sales["unit_cost"]

    attempts = sales.drop_duplicates("order_id")
    valid = sales[~sales["cancelled"]].copy()
    orders = valid.drop_duplicates("order_id")
    order_count = int(orders["order_id"].nunique())
    valid["customer_key"] = valid["customer_id"].where(valid["customer_id"].astype(str).str.strip() != "", valid["customer"])
    customer_count = int(valid.loc[valid["customer_key"].astype(str).str.strip() != "", "customer_key"].nunique())

    if not valid.empty:
        # Shipping fields are order-level values. max() avoids depending on row
        # order and tolerates legacy imports that repeated the same amount.
        order_shipping = valid.groupby("order_id")[["shipping_charged", "shipping_cost"]].max()
        shipping_charged = float(order_shipping["shipping_charged"].sum())
        shipping_cost = float(order_shipping["shipping_cost"].sum())
        revenue = float(valid["net_revenue"].sum())
        gross_sales = float(valid["gross"].sum())
        discounts = float(valid["discount"].sum())
        cogs = float(valid["cogs"].sum())
        units = float(valid["net_units"].sum())
    else:
        shipping_charged = shipping_cost = revenue = gross_sales = discounts = cogs = units = 0.0

    contribution = revenue + shipping_charged - cogs - shipping_cost
    day_count = max((end - start).days + 1, 1)
    monthly = valid.assign(month=valid["sale_date"].dt.to_period("M").dt.to_timestamp())
    monthly = monthly.groupby("month", as_index=False).agg(net_revenue=("net_revenue", "sum"), cogs=("cogs", "sum"))
    product_rank = valid.groupby(["sku", "title"], as_index=False).agg(net_revenue=("net_revenue", "sum"), units=("net_units", "sum"))
    product_rank = product_rank.sort_values("net_revenue", ascending=False)
    product_rank["share"] = product_rank["net_revenue"] / revenue * 100 if revenue else 0.0
    product_rank["share_cumulative"] = product_rank["share"].cumsum()
    product_rank["share_before"] = product_rank["share_cumulative"] - product_rank["share"]
    product_rank["class"] = product_rank["share_before"].apply(lambda x: "A" if x < 80 else ("B" if x < 95 else "C"))
    customer_rank = valid[valid["customer_key"].astype(str).str.strip() != ""].groupby(["customer_key", "customer"], as_index=False).agg(net_revenue=("net_revenue", "sum"), orders=("order_id", "nunique"))
    customer_rank = customer_rank.sort_values("net_revenue", ascending=False)
    state_rank = valid[valid["state"].astype(str).str.strip() != ""].groupby("state", as_index=False)["net_revenue"].sum().sort_values("net_revenue", ascending=False)
    channels = valid[valid["channel"].astype(str).str.strip() != ""].groupby("channel", as_index=False)["net_revenue"].sum().sort_values("net_revenue", ascending=False)

    return {
        "rows": valid,
        "monthly": monthly,
        "product_rank": product_rank,
        "customer_rank": customer_rank,
        "state_rank": state_rank,
        "channels": channels,
        "orders": order_count,
        "customers": customer_count,
        "attempted_orders": int(attempts["order_id"].nunique()),
        "cancelled_orders": int(attempts.loc[attempts["cancelled"], "order_id"].nunique()),
        "gross_sales": gross_sales,
        "discounts": discounts,
        "revenue": revenue,
        "cogs": cogs,
        "contribution": contribution,
        "margin_pct": contribution / revenue * 100 if revenue else 0.0,
        "gross_margin": revenue - cogs,
        "gross_margin_pct": (revenue - cogs) / revenue * 100 if revenue else 0.0,
        "units": units,
        "shipping_charged": shipping_charged,
        "shipping_cost": shipping_cost,
        "days": day_count,
        "ticket": revenue / order_count if order_count else 0.0,
        "average_daily_orders": order_count / day_count,
        "average_daily_revenue": revenue / day_count,
        "average_unit_price": (gross_sales - discounts - float(valid["returns"].sum())) / units if units else 0.0,
        "average_unit_cost": cogs / units if units else 0.0,
        "unit_profit": (contribution / units) if units else 0.0,
        "customer_period_revenue": revenue / customer_count if customer_count else 0.0,
        "order_frequency": order_count / customer_count if customer_count else 0.0,
        "average_freight_per_order": shipping_cost / order_count if order_count else 0.0,
        "freight_share_pct": shipping_cost / revenue * 100 if revenue else 0.0,
        "discount_pct": discounts / gross_sales * 100 if gross_sales else 0.0,
        "annualized_run_rate": revenue / day_count * 365,
        "physical_run_rate": units / day_count * 365,
        "cancellation_pct": (int(attempts["cancelled"].sum()) / len(attempts) * 100) if len(attempts) else 0.0,
    }


def calculate_inventory(frame: pd.DataFrame, start: date, end: date) -> dict | None:
    if frame.empty:
        return None
    data = frame.copy()
    data["snapshot_date"] = pd.to_datetime(data["snapshot_date"], errors="coerce")
    period = data[data["snapshot_date"].dt.date.between(start, end)].copy()
    latest = data.sort_values("snapshot_date").groupby("sku", as_index=False).tail(1).copy()
    latest["stock_value"] = latest["quantity"] * latest["unit_cost"]
    latest["low_stock"] = latest["quantity"] <= latest["minimum_quantity"]
    snapshots = period.assign(stock_value=period["quantity"] * period["unit_cost"])
    snapshot_count = int(snapshots["snapshot_date"].dt.date.nunique())
    average_stock_value = float(snapshots.groupby("snapshot_date")["stock_value"].sum().mean()) if snapshot_count >= 2 else None
    return {
        "latest": latest,
        "current_value": float(latest["stock_value"].sum()),
        "low_stock_count": int(latest["low_stock"].sum()),
        "average_stock_value": average_stock_value,
        "snapshot_count": snapshot_count,
    }
