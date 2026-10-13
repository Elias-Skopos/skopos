"""Deterministic fictional data. No database, identity, secrets or external API."""
from datetime import date, timedelta
from calendar import monthrange

import pandas as pd


def build_demo(today: date | None = None) -> dict:
    today = today or date.today()
    first = today.replace(day=1)
    end = first - timedelta(days=1)
    months = []
    current = end.replace(day=1)
    for _ in range(3):
        months.insert(0, current)
        current = (current - timedelta(days=1)).replace(day=1)
    products = [("F001", "Jardins de papel", "Literatura", 59.9, 28.0),
                ("F002", "Pequenos exploradores", "Infantil", 39.9, 18.0),
                ("F003", "Rotas do conhecimento", "Educação", 89.9, 44.0),
                ("F004", "Uma viagem pelo tempo", "História", 72.0, 35.0),
                ("F005", "Entre versos", "Poesia", 45.0, 22.0)]
    sales, finance, stock = [], [], []
    for m, month in enumerate(months):
        for n in range(80 + m * 15):
            sku, title, category, price, cost = products[n % 5]
            day = date(month.year, month.month, 1 + n % monthrange(month.year, month.month)[1])
            sales.append({"order_id": f"FICT-{month:%Y%m}-{n:03}", "sale_date": day.isoformat(),
                          "customer": f"Cliente fictício {1+n%18:02}", "customer_id": f"C{n%18:02}",
                          "channel": "Loja física" if n%3 else "Online", "city": "Cidade exemplo", "state": "SP",
                          "sku": sku, "title": title, "category": category, "quantity": 1+n%3,
                          "returned_quantity": 0, "unit_price": price, "unit_cost": cost,
                          "discount": 0, "taxes": round(price * (1+n%3) * 0.04, 2),
                          "shipping_charged": 0, "shipping_cost": 0, "status": "Concluído"})
        for sku, title, category, price, cost in products:
            for day, quantity in ((1, 25 + m * 3), (monthrange(month.year, month.month)[1], 3 if sku == "F001" else 18 + m * 2)):
                stock.append({"snapshot_date": date(month.year, month.month, day).isoformat(), "sku": sku,
                              "title": title, "quantity": quantity, "unit_cost": cost, "minimum_quantity": 5})
        for category, amount, day in (("Fornecedores", 2400+m*250, 10), ("Aluguel", 1800, 5),
                                     ("Folha e encargos", 2400, 20), ("Marketing", 320+m*50, 15)):
            finance.append({"date": date(month.year, month.month, day).isoformat(), "kind": "Despesa",
                            "category": category, "description": f"{category} · exemplo", "amount": amount,
                            "status": "Pago", "due_date": None})
    frame = pd.DataFrame(sales)
    daily = frame.assign(amount=frame.quantity*frame.unit_price).groupby("sale_date", as_index=False)["amount"].sum()
    for row in daily.to_dict("records"):
        finance.append({"date": row["sale_date"], "kind": "Receita", "category": "Vendas de livros",
                        "description": "Recebimentos fictícios", "amount": round(row["amount"], 2), "status": "Pago", "due_date": None})
    # Pending amounts belong to the next month and are deliberately separate from sales/paid cash.
    for kind, category, amount, day in (("Despesa", "Aluguel", 1800, 5), ("Despesa", "Folha e encargos", 2400, 20),
                                      ("Receita", "Eventos", 650, 25)):
        due = date(first.year, first.month, min(day, monthrange(first.year, first.month)[1]))
        finance.append({"date": first.isoformat(), "kind": kind, "category": category,
                        "description": f"{category} · exemplo pendente", "amount": amount, "status": "Pendente", "due_date": due.isoformat()})
    return {"sales": frame, "finance": pd.DataFrame(finance), "stock": pd.DataFrame(stock),
            "daily": daily, "start": months[0], "end": end, "latest_month": months[-1], "company": "Livraria Horizonte · Demonstração"}
