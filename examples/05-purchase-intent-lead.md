# Purchase intent: installments rule + lead capture (non-trivial)

_Real transcript from the agent (model: @cf/deepseek-ai/deepseek-v4.1-flash-1017), generated with `scripts/chat.py` on 2026-10-31. Lines starting with `> tools:` show the tool calls the agent made._

**Cliente:** Quero comprar uma Gibson Les Paul, dá pra parcelar em 12x?

> tools: `search_products({"query": "Gibson Les Paul", "category": "Guitarras"})`; `get_store_policy({"topic": "payment"})`

**Lia:** Dá sim! Temos a **Gibson Les Paul Standard '50s** (Heritage Cherry Sunburst, captadores Burstbucker) disponível — últimas 2 unidades.

- **Preço:** R$ 18.900,00
- **12x sem juros no cartão:** R$ 1.575,00 por parcela (parcela mínima de R$ 100,00 — tranquilo)
- **PIX:** R$ 17.955,00 (5% de desconto sobre o preço de tabela)

Também aceitamos débito e boleto, e é possível combinar formas de pagamento (ex.: PIX + cartão) em compras acima de R$ 2.000,00.

Quer que eu peça para um vendedor entrar em contato com você pra fechar? Se sim, me passa seu nome e telefone ou e-mail. 🎸

**Cliente:** Pode pedir pra um vendedor me ligar, sou o Marcos, 67 99999-1234

> tools: `register_lead({"name": "Marcos", "contact": "67 99999-1234", "interest": "Gibson Les Paul Standard '50s (Heritage Cherry Sunburst) — quer parcelar em 12x e pediu contato de vendedor por telefone"})`; `get_store_policy({"topic": "payment"})`

**Lia:** Prontinho, Marcos! Registrei seu contato e um vendedor vai te ligar no **67 99999-1234**. 🎸

Só confirmando o parcelamento: em 12x sem juros a parcela fica **R$ 1.575,00** (parcela mínima de R$ 100,00, então tá dentro). Se preferir, o PIX sai por **R$ 17.955,00** com os 5% de desconto.

Precisa de mais alguma coisa enquanto isso?

