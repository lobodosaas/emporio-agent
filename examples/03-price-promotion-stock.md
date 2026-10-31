# Price, promotion and out-of-stock handling

_Real transcript from the agent (model: @cf/deepseek-ai/deepseek-v4.1-flash-1017), generated with `scripts/chat.py` on 2026-10-31. Lines starting with `> tools:` show the tool calls the agent made._

**Cliente:** Quanto custa o Takamine GD20?

> tools: `search_products({"query": "Takamine GD20"})`

**Lia:** O Takamine GD20 Dreadnought Natural está disponível aqui, na categoria Violões:

- **Preço:** R$ 2.199,00
- **No PIX:** R$ 2.089,05 (5% de desconto)

Ele tem tampo sólido em cedro, laterais e fundo em sapele, braço em mogno, escala de 650mm e cordas de aço — sem eletrônica. Timbre quente e definido, ótimo pra fingerstyle.

Quer que eu veja mais detalhes ou que um vendedor entre em contato?

**Cliente:** E o Giannini GF-3D, tem? E o ukulele Kalani KAL-700T tá em promoção?

> tools: `search_products({"query": "Giannini GF-3D"})`; `search_products({"query": "Kalani KAL-700T ukulele"})`; `search_products({"category": "Violões", "max_price": 900})`

**Lia:** Sobre os dois:

**Giannini GF-3D Dreadnought Sunburst** — está **esgotado no momento**. O preço dele é R$ 799,90 (R$ 759,90 no PIX), mas sem estoque. Alternativas parecidas disponíveis em violão aço:
- Giannini GF-1R Aço Folk Sunburst — R$ 579,90 (R$ 550,90 no PIX)
- Yamaha F310 Aço Natural — R$ 699,90 (R$ 664,90 no PIX)
- Tagima Dallas Tuner Aço Natural — R$ 749,00 (R$ 711,55 no PIX)

**Kalani KAL-700T Tenor Natural** — sim, está em promoção "Oferta Especial":
- De R$ 359,00 por **R$ 323,10** (10% de desconto)
- Tampo em Spruce, corpo em Sapele, cordas de nylon, escala 432mm
- Atenção: nesse preço promocional **não incide** o desconto extra de 5% no PIX

Quer que eu detalhe algum desses ou que um vendedor te ajude?

