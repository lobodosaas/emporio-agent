# Architecture: exploded view

One picture of every piece of the project and how the pieces connect: what runs in the browser, at the Cloudflare edge, in the agent core, at build time, and in local mode.

![Exploded architecture](architecture.png)

<details>
<summary>Same diagram as Mermaid source (rendered by GitHub, editable)</summary>

```mermaid
flowchart TB
    classDef client fill:#eaf2f8,stroke:#1b4f72,color:#1b4f72
    classDef edge fill:#fff4e0,stroke:#f39c12,color:#5a3a00
    classDef core fill:#e9f7ef,stroke:#1e7d4f,color:#14532d
    classDef store fill:#fdf2e9,stroke:#a04000,color:#6e2c00
    classDef ext fill:#f4f6f7,stroke:#566573,color:#2c3e50
    classDef build fill:#f5eef8,stroke:#6c3483,color:#4a235a
    classDef local fill:#eef6fc,stroke:#21709f,color:#1b4f72,stroke-dasharray: 4 3

    subgraph L1["1 · Visitor's browser (public/)"]
        direction LR
        HOME["Home · Three.js guitar<br/>featured products · categories"]
        DOCS["Policy pages<br/>/politicas · /privacidade · /cookies · /termos"]
        WIDGET["Chat widget<br/>'Fale com a Lia'"]
        CONSENT["LGPD banner<br/>Reject · Configure · Accept"]
        LS[("localStorage<br/>consent + session id<br/>(id only with consent)")]
    end
    CLI["Terminal client<br/>scripts/chat.py"]

    subgraph L2["2 · Cloudflare edge: production"]
        direction LR
        subgraph WORKER["Python Worker · src/entry.py"]
            direction TB
            GUARDS["Guards: ≤500 chars · session id format<br/>rate limit 8/min session · 20/min IP"]
            ROUTES["POST /api/chat · /api/history · /api/reset<br/>GET /api/home · /api/policies<br/>GET /api/inbox (Bearer token)"]
        end
        subgraph DOS["Durable Objects (SQLite at the edge)"]
            direction TB
            DO_SESSION[("Conversation per session_id<br/>last 20 messages · 40 msgs/day")]
            DO_GLOBAL[("__global__<br/>1,500 model calls/day cap<br/>team inbox: leads + handoffs")]
        end
        WAI["Workers AI<br/>DeepSeek V4.1 Flash"]
    end

    subgraph L3["3 · Agent core: plain Python, provider-agnostic (src/)"]
        direction LR
        LOOP["agent.py · run_turn<br/>model → tool → model<br/>max 5 steps · fallback reply"]
        PROMPT["prompt.py<br/>persona 'Lia' · rules<br/>live date · open now"]
        subgraph TOOLS["tools.py · 5 tools (function calling)"]
            direction TB
            T1["search_products"]
            T2["get_order_status<br/>(order nº + e-mail/phone)"]
            T3["get_store_policy"]
            T4["register_lead"]
            T5["handoff_to_human"]
        end
        SITE["site_data.py<br/>featured · manual → web blocks"]
    end

    subgraph L4["4 · Data"]
        direction LR
        CSV["case/data/*.csv"]
        PDF["políticas_da_loja.pdf"]
        BKB["scripts/build_kb.py<br/>runs once, offline"]
        KB[["kb_data.py in memory<br/>65 products · 20 orders · 50 customers<br/>4 active promotions · 10 policy sections"]]
        CSV --> BKB
        PDF --> BKB
        BKB ==>|generates| KB
    end

    subgraph L5["5 · Local mode, own API key (local/)"]
        direction TB
        LSRV["local/server.py<br/>same routes + website · SQLite memory"]
        LLMS["local/llm.py<br/>Claude (Anthropic SDK) · OpenAI<br/>OpenRouter · Groq · DeepSeek"]
        LSRV --> LLMS
    end

    subgraph L6["6 · Store team"]
        direction TB
        INBOX["Inbox API → CRM / helpdesk"]
        HOOK["Slack / Discord webhook<br/>(optional)"]
    end

    CONSENT --> LS
    WIDGET --> LS
    HOME & DOCS & WIDGET --> GUARDS
    CLI --> GUARDS
    CLI -.->|or| LSRV
    GUARDS --> ROUTES
    ROUTES --> DO_SESSION
    ROUTES --> DO_GLOBAL
    ROUTES --> SITE
    DO_SESSION -->|run_turn| LOOP
    LSRV -->|run_turn| LOOP
    LOOP <-->|messages + tool schemas| WAI
    LOOP <-.->|same contract| LLMS
    LOOP --> PROMPT
    LOOP --> TOOLS
    T1 & T2 & T3 --> KB
    SITE --> KB
    T4 & T5 -.->|event| DO_GLOBAL
    DO_GLOBAL --> INBOX
    DO_GLOBAL -.-> HOOK

    class HOME,DOCS,CONSENT,WIDGET,LS,CLI client
    class GUARDS,ROUTES,WAI edge
    class DO_SESSION,DO_GLOBAL store
    class LOOP,PROMPT,T1,T2,T3,T4,T5,SITE core
    class CSV,PDF,BKB,KB build
    class LSRV,LLMS local
    class INBOX,HOOK ext
```

</details>

## How to read it

| Block | What it is | Key files |
|---|---|---|
| 1 · Browser | The store website: Three.js hero, real featured data, all policy pages, the LGPD banner with per-category preferences, and the floating chat. Nothing is stored without consent except the consent choice itself. | `public/` |
| 2 · Cloudflare edge | Production. The Python Worker validates and rate-limits each message. A Durable Object per customer keeps memory and quota, and a global one keeps the cost cap and the team inbox. The model is Workers AI, so the repo holds no API key. | `src/entry.py`, `wrangler.jsonc` |
| 3 · Agent core | Plain Python, no Cloudflare imports. The model only decides **which tool to call**; prices, stock, orders and policy text always come from Python over the knowledge base. | `src/agent.py`, `src/tools.py`, `src/prompt.py`, `src/site_data.py` |
| 4 · Data | The CSVs and the policy PDF are cleaned once into a Python module loaded in memory. At runtime nothing reads CSV or PDF. | `scripts/build_kb.py` → `src/kb_data.py` |
| 5 · Local mode | The same core and website on a laptop, with SQLite instead of Durable Objects and the reviewer's own key: Claude, OpenAI, OpenRouter, Groq or DeepSeek. | `local/server.py`, `local/llm.py` |
| 6 · Store team | Leads and "talk to a human" requests reach the team through an authenticated API and an optional chat webhook. | `GET /api/inbox`, `TEAM_WEBHOOK_URL` |

The step-by-step flow of a single question is the sequence diagram in the [README](../README.md#what-happens-when-a-customer-asks-quanto-custa-o-takamine-gd20).
