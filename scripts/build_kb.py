"""Build the agent knowledge base from the raw case files.

Reads case/data/*.csv and the store policy PDF, cleans them, and writes
src/kb_data.py as plain Python literals. The Worker imports that module,
so the runtime needs no file I/O, no CSV parsing and no PDF library.

Run: uv run python scripts/build_kb.py
"""

import csv
import json
import re
from pathlib import Path

from pypdf import PdfReader

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "case" / "data"
OUT = ROOT / "src" / "kb_data.py"
PREFIX = "desafio_tecnico_ai_eng - "

# Brands that appear in product names or descriptions. Used to catch rows
# whose description talks about a different instrument than the name.
BRANDS = [
    "Music Man", "Crafter", "Fender", "Giannini", "Gibson", "Ibanez", "Kalani",
    "Kala", "Korg", "Martin", "Nord", "Ohana", "PRS", "Pearl", "Roland",
    "Rozini", "Shelby", "Tagima", "Takamine", "Tama", "Taylor", "Yamaha",
]

# Every top-level section of the policy PDF, exposed as a lookup topic.
# Nothing is dropped: the cover page is kept as its own topic too.
# Sections 7 and 10 are also copied into the system prompt, since they are
# instructions for the attendant rather than answers for the customer.
POLICY_TOPICS = {
    "about_and_contact": 1,
    "opening_hours": 2,
    "payment": 3,
    "returns_and_exchanges": 4,
    "shipping_and_delivery": 5,
    "promotions": 6,
    "customer_service_guidelines": 7,
    "warranty": 8,
    "privacy": 9,
    "final_provisions": 10,
}


def read_csv(name):
    with open(DATA / f"{PREFIX}{name}.csv", encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def brands_in(text):
    found = []
    rest = text
    for brand in BRANDS:  # "Kalani" before "Kala" so the longer name wins
        if re.search(rf"\b{re.escape(brand)}\b", rest):
            found.append(brand)
            rest = re.sub(rf"\b{re.escape(brand)}\b", " ", rest)
    return found


def description_matches_name(name, description):
    in_name = brands_in(name)
    in_desc = brands_in(description)
    if not in_name or not in_desc:
        return True
    return in_name[0] in in_desc


def build_products(categories, promotions):
    products = []
    for row in read_csv("products"):
        pid = int(row["product_id"])
        description = row["description"].strip()
        if not description_matches_name(row["name"], description):
            description = None
        promo = promotions.get(pid)
        products.append({
            "id": pid,
            "name": row["name"].strip(),
            "category": categories[int(row["category_id"])],
            "price": round(float(row["price_brl"]), 2),
            "stock": int(row["stock_quantity"]),
            "status": row["status"].strip(),
            "description": description,
            "specs": json.loads(row["specs"]) if row["specs"] else {},
            "promotion": promo,
        })
    return products


def build_promotions():
    active = {}
    for row in read_csv("promotions"):
        if row["is_active"].strip() != "1":
            continue
        pid = int(row["product_id"])
        promo = {"label": row["description"].strip(), "percent": int(row["discount_percent"])}
        # Promotions are not cumulative (policy 6.2): keep the best one.
        if pid not in active or promo["percent"] > active[pid]["percent"]:
            active[pid] = promo
    return active


def digits(text):
    return re.sub(r"\D", "", text)


def build_customers():
    return {
        int(r["customer_id"]): {
            "name": r["name"].strip(),
            "email": r["email"].strip().lower(),
            "phone_digits": digits(r["phone"]),
            "city": r["city"].strip(),
        }
        for r in read_csv("customers")
    }


def build_orders(products_by_id):
    items = {}
    for r in read_csv("order_items"):
        oid = int(r["order_id"])
        pid = int(r["product_id"])
        items.setdefault(oid, []).append({
            "product_id": pid,
            "name": products_by_id[pid]["name"],
            "quantity": int(r["quantity"]),
        })
    orders = {}
    for r in read_csv("orders"):
        oid = int(r["order_id"])
        orders[oid] = {
            "id": oid,
            "customer_id": int(r["customer_id"]),
            "date": r["order_date"],
            "status": r["status"].strip(),
            "total": round(float(r["total_brl"]), 2),
            "payment_method": r["payment_method"].strip(),
            "tracking_code": r["tracking_code"].strip() or None,
            "estimated_delivery": r["estimated_delivery"].strip() or None,
            "notes": r["notes"].strip() or None,
            "items": items.get(oid, []),
        }
    return orders


def build_policies():
    reader = PdfReader(DATA / "políticas_da_loja.pdf")
    cover = "\n".join(
        line.strip() for line in reader.pages[0].extract_text(extraction_mode="layout").splitlines() if line.strip()
    )
    lines = []
    for page in reader.pages[1:]:
        for line in page.extract_text(extraction_mode="layout").splitlines():
            text = line.strip()
            if not text or text.startswith("Empório da Música Manual") or re.fullmatch(r"Página \d+", text):
                continue
            lines.append(text.replace("•", "-"))
    sections = {}
    current = None
    for text in lines:
        heading = re.fullmatch(r"(\d+)\.\s+(.+)", text)
        # Numbered list items ("1. Saudação: ...") look like headings too;
        # real sections are numbered in sequence, so only accept the next one.
        if heading and int(heading.group(1)) == (current or 0) + 1:
            current = int(heading.group(1))
            sections[current] = {"title": heading.group(2), "lines": []}
        elif current is not None:
            sections[current]["lines"].append(text)
    policies = {num: {"title": s["title"], "text": "\n".join(s["lines"])} for num, s in sections.items()}
    policies[0] = {"title": "Capa do manual", "text": cover}
    return policies


def main():
    categories = {int(r["category_id"]): r["name"].strip() for r in read_csv("categories")}
    promotions = build_promotions()
    products = build_products(categories, promotions)
    products_by_id = {p["id"]: p for p in products}
    policies = build_policies()
    missing = [n for n in POLICY_TOPICS.values() if n not in policies]
    unmapped = [n for n in policies if n and n not in POLICY_TOPICS.values()]
    if missing or unmapped:
        raise SystemExit(f"policy sections missing: {missing}, unmapped: {unmapped}")

    topics = {topic: policies[num] for topic, num in POLICY_TOPICS.items()}
    # Cover holds the slogan and version; contact data repeats §1.2. Keep it with "about".
    topics["about_and_contact"] = {
        "title": topics["about_and_contact"]["title"],
        "text": policies[0]["text"] + "\n\n" + topics["about_and_contact"]["text"],
    }
    kb = {
        "CATEGORIES": sorted(categories.values()),
        "PRODUCTS": products,
        "CUSTOMERS": build_customers(),
        "ORDERS": build_orders(products_by_id),
        "POLICIES": topics,
        "SERVICE_GUIDELINES": policies[7]["text"] + "\n\n" + policies[10]["text"],
    }
    body = "\n\n".join(f"{name} = {value!r}" for name, value in kb.items())
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(
        '"""Generated by scripts/build_kb.py from case/data. Do not edit by hand."""\n\n' + body + "\n",
        encoding="utf-8",
    )
    dropped = [p["id"] for p in products if p["description"] is None]
    print(f"wrote {OUT.relative_to(ROOT)}: {len(products)} products, {len(kb['ORDERS'])} orders, "
          f"{len(promotions)} active promotions, {len(policies)} policy sections")
    print(f"descriptions dropped (brand mismatch with name): {dropped}")


if __name__ == "__main__":
    main()
