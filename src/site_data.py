"""Data for the public website: featured products, categories, store status
and the policy manual as structured blocks. Pure Python over kb_data."""

import re

import kb_data
from prompt import is_open, store_now
from tools import availability, product_view

# Order and public titles of the manual sections on the website.
POLICY_PAGES = [
    ("about_and_contact", "sobre"),
    ("opening_hours", "horario"),
    ("payment", "pagamento"),
    ("returns_and_exchanges", "trocas-e-devolucoes"),
    ("shipping_and_delivery", "frete-e-entregas"),
    ("promotions", "promocoes"),
    ("customer_service_guidelines", "atendimento"),
    ("warranty", "garantia"),
    ("privacy", "privacidade"),
    ("final_provisions", "disposicoes-finais"),
]

FEATURED_LIMIT = 6

TABLE_GAP = re.compile(r"\S {3,}\S")
SUBHEADING = re.compile(r"^(\d+\.\d+)\s+(.+)$")
BULLET = re.compile(r"^-\s+(.+)$")
NUMBERED = re.compile(r"^(\d+)\.\s+(.+)$")


def policy_blocks(text):
    """Turn the layout-mode text of one manual section into blocks.

    The PDF text keeps the page's line wraps and table columns, so this
    rejoins wrapped lines and splits table rows on wide gaps.
    Block types: h3, p, ul, ol, table.
    """
    blocks = []
    lines = [raw.strip() for raw in text.splitlines()]
    # A line that reaches (almost) the full text width was wrapped by the PDF,
    # so the next line continues the same paragraph even after a period.
    wrap_width = 0.8 * max((len(l) for l in lines if not TABLE_GAP.search(l)), default=0)
    previous = ""

    def last(kind):
        return blocks[-1] if blocks and blocks[-1]["type"] == kind else None

    for line in lines:
        was_wrapped = len(previous) >= wrap_width
        previous = line
        if not line:
            blocks.append({"type": "break"})
            continue
        numbered = NUMBERED.match(line)
        if numbered:  # before the table check: "1.   Saudação" has a wide gap too
            ol = last("ol")
            if ol:
                ol["items"].append(numbered.group(2))
            else:
                blocks.append({"type": "ol", "items": [numbered.group(2)]})
            continue
        bullet = BULLET.match(line)
        if bullet:  # before the table check: "-    text" has a wide gap after the dash
            ul = last("ul")
            if ul:
                ul["items"].append(bullet.group(1))
            else:
                blocks.append({"type": "ul", "items": [bullet.group(1)]})
            continue
        if TABLE_GAP.search(line):
            cells = re.split(r" {3,}", line)
            table = last("table")
            if table:
                table["rows"].append(cells)
            else:
                blocks.append({"type": "table", "header": cells, "rows": []})
            continue
        table = last("table")
        if table and line[0].islower():
            # wrapped cell: "5% de desconto sobre o preço de" + "tabela"
            target = table["rows"][-1] if table["rows"] else table["header"]
            target[-1] = f"{target[-1]} {line}"
            continue
        heading = SUBHEADING.match(line)
        if heading:
            blocks.append({"type": "h3", "text": line})
            continue
        for kind in ("ul", "ol"):
            listing = last(kind)
            if listing:
                listing["items"][-1] += " " + line
                break
        else:
            paragraph = last("p")
            if paragraph and (was_wrapped or not paragraph["text"].endswith((".", ":", "!", "?"))):
                paragraph["text"] += " " + line
            else:
                blocks.append({"type": "p", "text": line})
    return [b for b in blocks if b["type"] != "break"]


def policies():
    sections = []
    for topic, slug in POLICY_PAGES:
        policy = kb_data.POLICIES[topic]
        text = policy["text"]
        if topic == "about_and_contact":
            # The manual's cover is internal ("uso restrito da equipe"); the site starts at §1.
            text = text.split("\n\n", 1)[-1]
        sections.append({"slug": slug, "title": policy["title"], "blocks": policy_blocks(text)})
    return sections


def _featured_products():
    in_stock = [p for p in kb_data.PRODUCTS if availability(p) == "in_stock"]
    picks = [p for p in in_stock if p["promotion"]]
    chosen = {p["id"] for p in picks}
    # Then one well-stocked instrument per category not yet shown.
    shown = {p["category"] for p in picks}
    for p in sorted(in_stock, key=lambda p: (-p["stock"], p["price"])):
        if len(picks) >= FEATURED_LIMIT:
            break
        if p["category"] not in shown and p["id"] not in chosen:
            picks.append(p)
            shown.add(p["category"])
            chosen.add(p["id"])
    return [product_view(p) for p in picks[:FEATURED_LIMIT]]


def home(now=None):
    now = store_now(now)
    counts = {c: 0 for c in kb_data.CATEGORIES}
    for p in kb_data.PRODUCTS:
        if availability(p) == "in_stock":
            counts[p["category"]] += 1
    return {
        "open_now": is_open(now),
        "categories": [{"name": c, "available": n} for c, n in counts.items()],
        "featured": _featured_products(),
    }
