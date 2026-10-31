from datetime import date

import kb_data
from tools import get_order_status, get_store_policy, run_tool, search_products


def names(result):
    return [p["name"] for p in result["products"]]


def test_exact_model_lookup_returns_only_that_product():
    result = search_products(query="Takamine GD20")
    assert names(result) == ["Takamine GD20 Dreadnought Natural"]
    assert result["products"][0]["price"] == 2199
    assert result["products"][0]["pix_price"] == 2089.05


def test_browse_by_category_and_price_lists_only_available():
    result = search_products(category="Violões", max_price=1000)
    assert result["count"] > 0
    for p in result["products"]:
        assert p["category"] == "Violões"
        assert p["availability"] == "disponível"
        assert p.get("price", p.get("promo_price")) <= 1000


def test_active_promotion_shows_original_price_and_no_pix_stacking():
    # promotion 12: product 127, 10%, active
    product = search_products(query="KAL-700T")["products"][0]
    assert product["original_price"] == 359
    assert product["discount_percent"] == 10
    assert product["promo_price"] == 323.1
    assert product["pix_extra_discount"] is False
    assert "pix_price" not in product


def test_inactive_promotion_is_ignored():
    # promotion 1 (product 102, Black Friday) is inactive
    product = search_products(query="Crafter CE-15")["products"][0]
    assert "promotion" not in product
    assert product["price"] == 3899


def test_named_product_is_returned_even_when_unavailable():
    discontinued = search_products(query="Shelby SN-7C")["products"][0]
    assert discontinued["availability"].startswith("descontinuado")
    sold_out = search_products(query="Giannini GF-3D")["products"][0]
    assert sold_out["availability"] == "esgotado no momento"


def test_category_without_products_returns_note():
    result = search_products(category="Ukuleles", min_price=50000)
    assert result["count"] == 0
    assert "no matching product" in result["note"]


def test_unknown_category_is_rejected():
    assert "error" in search_products(category="Pedais")


def test_mismatched_descriptions_were_dropped():
    bass = next(p for p in kb_data.PRODUCTS if p["id"] == 135)  # name Music Man, description Fender
    assert bass["description"] is None


def test_order_requires_matching_contact():
    ok = get_order_status(8, "anacarol.ferreira@coldmail.com")
    assert ok["status"] == "enviado, em trânsito"
    assert ok["tracking_code"] == "BRJL5544332BR"
    by_phone = get_order_status(8, "(67) 99654-7821")
    assert by_phone["order_id"] == 8


def test_order_with_wrong_contact_looks_like_missing_order():
    wrong = get_order_status(8, "someone@else.com")
    missing = get_order_status(999, "anacarol.ferreira@coldmail.com")
    assert wrong == missing
    assert "error" in wrong


def test_phone_check_rejects_short_or_padded_suffixes():
    # customer of order 8 has phone (67) 99654-7821
    for attempt in ("00000001", "0000007821", "7821", "1", "+55 67 0000-7821"):
        assert "error" in get_order_status(8, attempt), attempt
    assert get_order_status(8, "+55 67 99654-7821")["order_id"] == 8


def test_delivered_order_reports_days_since_delivery():
    order = get_order_status(4, "lucas.mendes@jmail.com", today=date(2026, 1, 1))
    assert order["delivered_on_or_before"] == "2025-12-22"
    assert order["days_since_delivery"] == 10


def test_every_policy_topic_has_text():
    for topic in kb_data.POLICIES:
        assert get_store_policy(topic)["text"].strip()
    assert "09:00" in get_store_policy("opening_hours")["text"]
    assert "error" in get_store_policy("refunds")


def test_side_effect_tools_return_events_hidden_from_model():
    result, event = run_tool("register_lead", {"name": "Ana", "contact": "67999990000", "interest": "Taylor 214ce"})
    assert result["ok"] and "_event" not in result
    assert event["type"] == "lead"
    _, event = run_tool("handoff_to_human", {"reason": "complaint", "summary": "produto chegou riscado"})
    assert event["type"] == "handoff"


def test_run_tool_handles_bad_input():
    assert "error" in run_tool("nope", {})[0]
    assert "error" in run_tool("search_products", None)[0]
    assert "error" in run_tool("get_store_policy", {"wrong": 1})[0]
