"""Tools the agent can call. Pure Python over kb_data, no Workers APIs.

Each tool returns a JSON-serializable dict that goes back to the model.
Tools with side effects (lead, handoff) return an "_event" entry that the
caller persists; the model never sees it.
"""

import re
import unicodedata
from datetime import date

import kb_data

PIX_DISCOUNT = 0.05  # policy 3: 5% off list price, not on promotional prices (6.2)
MAX_RESULTS = 8

AVAILABILITY_PT = {
    "in_stock": "disponível",
    "out_of_stock": "esgotado no momento",
    "discontinued": "descontinuado (fora do catálogo)",
    "coming_soon": "em breve (ainda não disponível para venda)",
}

ORDER_STATUS_PT = {
    "pending": "aguardando confirmação de pagamento",
    "confirmed": "pagamento confirmado, em separação",
    "shipped": "enviado, em trânsito",
    "delivered": "entregue",
    "cancelled": "cancelado",
}


def normalize(text):
    text = unicodedata.normalize("NFKD", str(text).lower())
    return "".join(c for c in text if not unicodedata.combining(c))


def tokens(text):
    return [t for t in re.split(r"[^a-z0-9]+", normalize(text)) if len(t) > 1]


def availability(product):
    if product["status"] == "discontinued":
        return "discontinued"
    if product["status"] == "coming_soon":
        return "coming_soon"
    return "in_stock" if product["stock"] > 0 else "out_of_stock"


def price_view(product):
    price = product["price"]
    promo = product["promotion"]
    if promo:
        # Policy 6.2: show promo price with original price and percent.
        return {
            "original_price": price,
            "promotion": promo["label"],
            "discount_percent": promo["percent"],
            "promo_price": round(price * (1 - promo["percent"] / 100), 2),
            "pix_extra_discount": False,
        }
    return {"price": price, "pix_price": round(price * (1 - PIX_DISCOUNT), 2)}


def product_view(product):
    view = {
        "id": product["id"],
        "name": product["name"],
        "category": product["category"],
        "availability": AVAILABILITY_PT[availability(product)],
        **price_view(product),
        "specs": product["specs"],
    }
    if availability(product) == "in_stock" and product["stock"] <= 3:
        view["low_stock"] = f"últimas {product['stock']} unidades"
    if product["description"]:
        view["description"] = product["description"]
    return view


def _haystack(product):
    specs = " ".join(str(v) for v in product["specs"].values())
    return set(tokens(f"{product['name']} {product['category']} {product['description'] or ''} {specs}"))


def _token_matches(token, haystack):
    if token in haystack:
        return True
    # crude plural/singular tolerance: "violoes" ~ "violao" is handled by the
    # category filter; here only strip a trailing "s"
    return token.endswith("s") and token[:-1] in haystack


def search_products(query=None, category=None, min_price=None, max_price=None, include_unavailable=False):
    if category and category not in kb_data.CATEGORIES:
        return {"error": f"unknown category {category!r}", "valid_categories": kb_data.CATEGORIES}

    products = kb_data.PRODUCTS
    if category:
        products = [p for p in products if p["category"] == category]

    def effective_price(p):
        view = price_view(p)
        return view.get("promo_price", view.get("price"))

    if min_price is not None:
        products = [p for p in products if effective_price(p) >= float(min_price)]
    if max_price is not None:
        products = [p for p in products if effective_price(p) <= float(max_price)]

    query_tokens = tokens(query) if query else []
    if query_tokens:
        scored = []
        for p in products:
            hay = _haystack(p)
            score = sum(_token_matches(t, hay) for t in query_tokens)
            if score:
                scored.append((score, p))
        best = max((s for s, _ in scored), default=0)
        # If some products match every word, keep only those (exact model lookup).
        products = [p for s, p in scored if s == best] if best == len(query_tokens) else [p for _, p in scored]

    if not include_unavailable:
        # Browsing ("violão até R$ 1000") lists only what can be bought today. A product the
        # customer names ("Giannini GF-3D") is kept whatever its status, so the agent can say
        # it is sold out and suggest alternatives.
        def named(p):
            name = set(tokens(p["name"]))
            return bool(query_tokens) and all(_token_matches(t, name) for t in query_tokens)

        products = [p for p in products if availability(p) == "in_stock" or named(p)]

    products = sorted(products, key=lambda p: (availability(p) != "in_stock", effective_price(p)))
    result = {
        "count": len(products),
        "products": [product_view(p) for p in products[:MAX_RESULTS]],
    }
    if len(products) > MAX_RESULTS:
        # Give the model the arithmetic instead of letting it count (it miscounted in testing).
        result["not_shown"] = len(products) - MAX_RESULTS
        result["note"] = (f"showing {MAX_RESULTS} of {len(products)} matching products; "
                          f"{result['not_shown']} more not shown. Say these exact numbers; ask the customer to narrow down")
    if not products:
        result["note"] = "no matching product in the catalog"
    return result


def _identity_matches(customer, email_or_phone):
    given = str(email_or_phone).strip().lower()
    if "@" in given:
        return given == customer["email"]
    given_digits = re.sub(r"\D", "", given)
    # Accept with or without area/country code, but always compare the full
    # 8-digit subscriber number, never a shorter suffix.
    if len(given_digits) < 8:
        return False
    return given_digits[-8:] == customer["phone_digits"][-8:]


def get_order_status(order_id, email_or_phone, today=None):
    try:
        order = kb_data.ORDERS.get(int(order_id))
    except (TypeError, ValueError):
        order = None
    customer = kb_data.CUSTOMERS.get(order["customer_id"]) if order else None
    # Same answer for "no such order" and "wrong contact": do not leak which orders exist (LGPD, policy 9).
    if not order or not customer or not _identity_matches(customer, email_or_phone):
        return {"error": "order not found for this order number and contact; ask the customer to double-check both"}

    view = {
        "order_id": order["id"],
        "customer_first_name": customer["name"].split()[0],
        "order_date": order["date"],
        "status": ORDER_STATUS_PT[order["status"]],
        "items": order["items"],
        "total": order["total"],
        "payment_method": order["payment_method"],
    }
    if order["tracking_code"]:
        view["tracking_code"] = order["tracking_code"]
    if order["estimated_delivery"]:
        key = "delivered_on_or_before" if order["status"] == "delivered" else "estimated_delivery"
        view[key] = order["estimated_delivery"]
    if order["notes"]:
        view["notes"] = order["notes"]
    if today and order["status"] == "delivered" and order["estimated_delivery"]:
        delivered = date.fromisoformat(order["estimated_delivery"])
        view["days_since_delivery"] = (today - delivered).days
        view["days_since_purchase"] = (today - date.fromisoformat(order["date"])).days
    return view


def get_store_policy(topic):
    policy = kb_data.POLICIES.get(topic)
    if not policy:
        return {"error": f"unknown topic {topic!r}", "valid_topics": list(kb_data.POLICIES)}
    return {"topic": topic, "title": policy["title"], "text": policy["text"]}


def register_lead(name, contact, interest):
    lead = {"name": str(name)[:100], "contact": str(contact)[:100], "interest": str(interest)[:300]}
    return {"ok": True, "message": "lead registered; a salesperson will reach out", "_event": {"type": "lead", **lead}}


def handoff_to_human(reason, summary, contact=None):
    ticket = {"reason": str(reason)[:100], "summary": str(summary)[:500], "contact": str(contact or "")[:100]}
    return {
        "ok": True,
        "message": "conversation flagged for a human attendant; reply time up to 24 business hours (policy 7.3)",
        "_event": {"type": "handoff", **ticket},
    }


TOOLS = {
    "search_products": search_products,
    "get_order_status": get_order_status,
    "get_store_policy": get_store_policy,
    "register_lead": register_lead,
    "handoff_to_human": handoff_to_human,
}

SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "search_products",
            "description": (
                "Search the store catalog for instruments: price, promotions, PIX price, availability and specs. "
                "Use for any question about products, prices or stock. Never state a price or stock without calling this."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Brand, model or keywords, e.g. 'Takamine GD20', 'nylon', 'elétrico'"},
                    "category": {"type": "string", "enum": kb_data.CATEGORIES},
                    "min_price": {"type": "number", "description": "Minimum price in BRL"},
                    "max_price": {"type": "number", "description": "Maximum price in BRL"},
                    "include_unavailable": {"type": "boolean", "description": "Also list out-of-stock/discontinued items when browsing"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_order_status",
            "description": (
                "Look up an order. Requires the order number AND the e-mail or phone used in the purchase, "
                "to protect customer data. Ask the customer for both before calling."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "order_id": {"type": "integer"},
                    "email_or_phone": {"type": "string"},
                },
                "required": ["order_id", "email_or_phone"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_store_policy",
            "description": "Read the official store policy on a topic: contact/address, hours, payment and installments, returns and exchanges, shipping, promotions rules, warranty, privacy.",
            "parameters": {
                "type": "object",
                "properties": {"topic": {"type": "string", "enum": list(kb_data.POLICIES)}},
                "required": ["topic"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "register_lead",
            "description": "Save a sales lead when the customer shows buying intent and agrees to be contacted by a salesperson.",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "contact": {"type": "string", "description": "Phone or e-mail given by the customer"},
                    "interest": {"type": "string", "description": "Product(s) and context"},
                },
                "required": ["name", "contact", "interest"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "handoff_to_human",
            "description": (
                "Escalate to a human attendant: complaints, damaged/defective products, return or exchange requests "
                "that need processing, doubts about how a policy applies, or when the customer asks for a person."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "reason": {"type": "string", "enum": ["complaint", "return_or_exchange", "defect", "policy_doubt", "customer_request", "other"]},
                    "summary": {"type": "string", "description": "Short summary for the attendant"},
                    "contact": {"type": "string", "description": "Customer phone or e-mail, if given"},
                },
                "required": ["reason", "summary"],
            },
        },
    },
]


def run_tool(name, arguments, today=None):
    """Execute a tool by name. Returns (result_for_model, event_or_None)."""
    func = TOOLS.get(name)
    if func is None:
        return {"error": f"unknown tool {name!r}"}, None
    if not isinstance(arguments, dict):
        return {"error": "arguments must be a JSON object"}, None
    if name == "get_order_status":
        arguments = {**arguments, "today": today}
    try:
        result = func(**arguments)
    except TypeError as exc:
        return {"error": f"bad arguments: {exc}"}, None
    event = result.pop("_event", None)
    return result, event
