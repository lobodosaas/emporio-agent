from datetime import datetime, timezone

import kb_data
from site_data import home, policies, policy_blocks


def test_payment_table_rejoins_wrapped_cell():
    blocks = policy_blocks(kb_data.POLICIES["payment"]["text"])
    table = next(b for b in blocks if b["type"] == "table")
    assert len(table["header"]) == 3
    pix = next(r for r in table["rows"] if r[0] == "PIX")
    assert pix[2] == "5% de desconto sobre o preço de tabela"
    assert all(len(r) == 3 for r in table["rows"])


def test_bullets_rejoin_wrapped_lines():
    blocks = policy_blocks(kb_data.POLICIES["returns_and_exchanges"]["text"])
    first_list = next(b for b in blocks if b["type"] == "ul")
    assert first_list["items"][0].endswith("após o recebimento do produto, sem necessidade de justificativa.")
    assert [b["text"] for b in blocks if b["type"] == "h3"][0].startswith("4.1")


def test_paragraph_wraps_are_joined():
    blocks = policy_blocks(kb_data.POLICIES["returns_and_exchanges"]["text"])
    assert blocks[0]["type"] == "p"
    assert blocks[0]["text"].endswith("claras para trocas e devoluções.")


def test_numbered_list_and_wrapped_paragraphs():
    blocks = policy_blocks(kb_data.POLICIES["customer_service_guidelines"]["text"])
    steps = next(b for b in blocks if b["type"] == "ol")
    assert len(steps["items"]) == 5 and steps["items"][0].startswith("Saudação")
    assert not any(b["type"] == "table" for b in blocks)
    tracking = policy_blocks(kb_data.POLICIES["shipping_and_delivery"]["text"])
    assert any("(exemplo: BR4K7M2X9P1BR)" in b.get("text", "") for b in tracking)
    hours = policy_blocks(kb_data.POLICIES["opening_hours"]["text"])
    assert any("estendido. Alterações serão" in b.get("text", "") for b in hours)


def test_every_section_published_and_cover_left_out():
    sections = policies()
    assert len(sections) == len(kb_data.POLICIES)
    about = sections[0]
    text = " ".join(b.get("text", "") for b in about["blocks"])
    assert "Uso restrito" not in text
    assert "fundada em 2008" in text


def test_word_coverage_of_published_policies():
    """Every word of the manual sections (cover excepted) reaches the site."""
    import re

    def words(s):
        return set(re.findall(r"\w+", s.lower()))

    published = ""
    for s in policies():
        published += " " + s["title"]
        for b in s["blocks"]:
            published += " " + " ".join([b.get("text", "")] + b.get("items", []) + b.get("header", [])
                                        + [c for row in b.get("rows", []) for c in row])
    source = " ".join(p["title"] + " " + p["text"].split("\n\n", 1)[-1] for p in kb_data.POLICIES.values())
    assert words(source) - words(published) == set()


def test_home_has_real_featured_data():
    data = home(datetime(2026, 11, 2, 14, 0, tzinfo=timezone.utc))  # Monday 10:00 local
    assert data["open_now"] is True
    assert 1 <= len(data["featured"]) <= 6
    promos = [p for p in data["featured"] if "promo_price" in p]
    assert len(promos) == 4  # all active promotions with stock
    for p in data["featured"]:
        assert p["availability"] == "disponível"
    names = {c["name"] for c in data["categories"]}
    assert names == set(kb_data.CATEGORIES)
