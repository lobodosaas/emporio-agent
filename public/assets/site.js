// Shared on every page: LGPD storage consent, store status and the Lia chat widget.
(() => {
  const CONSENT_KEY = "emporio_consent";   // "granted" | "denied"
  const SESSION_KEY = "emporio_session";

  // ---------- storage, only after consent ----------
  const store = {
    get(key) { try { return localStorage.getItem(key); } catch { return null; } },
    set(key, value) { try { localStorage.setItem(key, value); } catch { /* private mode */ } },
    remove(key) { try { localStorage.removeItem(key); } catch { /* private mode */ } },
  };
  const consent = () => store.get(CONSENT_KEY);

  function newSessionId() {
    const id = (crypto.randomUUID && crypto.randomUUID()) || String(Date.now()) + Math.random().toString(16).slice(2);
    return "web-" + id.replace(/[^A-Za-z0-9_-]/g, "");
  }
  // Without consent the id lives only in memory: the conversation is forgotten on reload.
  let sessionId = (consent() === "granted" && store.get(SESSION_KEY)) || newSessionId();

  // ---------- icons (authored, one stroke weight) ----------
  const icon = {
    chat: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M4 5h16v11H9l-5 4z"/><path d="M8 9.5h8M8 12.5h5"/></svg>',
    close: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" aria-hidden="true"><path d="M6 6l12 12M18 6L6 18"/></svg>',
    reset: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M4 12a8 8 0 1 0 2.3-5.7"/><path d="M4 4v4h4"/></svg>',
    send: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M5 12h13M13 6l6 6-6 6"/></svg>',
  };

  // ---------- consent banner ----------
  function showConsent() {
    let banner = document.getElementById("consent");
    if (!banner) {
      banner = document.createElement("section");
      banner.id = "consent";
      banner.className = "consent";
      banner.setAttribute("aria-label", "Privacidade e armazenamento");
      banner.innerHTML = `
        <h2>Sua privacidade</h2>
        <p>Não usamos cookies de publicidade nem de rastreamento. Com sua permissão, guardamos no seu navegador
        apenas um identificador da conversa com a Lia, para ela lembrar o papo quando você voltar.
        <a href="/privacidade#cookies">Saiba mais</a>.</p>
        <div class="consent-actions">
          <button class="btn btn-primary btn-small" data-consent="granted">Aceitar</button>
          <button class="btn btn-ghost btn-small" data-consent="denied">Recusar</button>
        </div>`;
      banner.addEventListener("click", (e) => {
        const choice = e.target.closest("[data-consent]")?.dataset.consent;
        if (!choice) return;
        store.set(CONSENT_KEY, choice);  // the choice itself is strictly necessary storage
        if (choice === "granted") store.set(SESSION_KEY, sessionId);
        else store.remove(SESSION_KEY);
        banner.hidden = true;
      });
      document.body.appendChild(banner);
    }
    banner.hidden = false;
  }
  window.EmporioConsent = { open: showConsent };
  document.addEventListener("click", (e) => {
    if (e.target.closest("[data-open-consent]")) { e.preventDefault(); showConsent(); }
  });

  // ---------- store status in the header ----------
  async function loadStatus() {
    const el = document.querySelector("[data-store-status]");
    if (!el) return null;
    try {
      const data = await (await fetch("/api/home")).json();
      el.textContent = data.open_now ? "Aberto agora" : "Fechado agora";
      el.classList.add(data.open_now ? "open" : "closed");
      return data;
    } catch { el.textContent = ""; return null; }
  }
  window.EmporioHome = loadStatus();

  // ---------- chat widget ----------
  const SUGGESTIONS = ["Violões até R$ 1.000", "Status do meu pedido", "Horário da loja", "Como funciona a troca?"];

  // Escape first, then allow only **bold** and "- " lists from the model's Markdown.
  function render(text) {
    const escaped = text.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
      .replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>");
    let html = "", inList = false;
    for (const line of escaped.split("\n")) {
      const item = line.match(/^\s*[-•]\s+(.*)$/);
      if (item) { html += (inList ? "" : "<ul>") + `<li>${item[1]}</li>`; inList = true; continue; }
      if (inList) { html += "</ul>"; inList = false; }
      html += line ? `${line}<br>` : "<br>";
    }
    if (inList) html += "</ul>";
    return html.replace(/(<br>)+$/, "");
  }

  const launcher = document.createElement("button");
  launcher.className = "chat-launcher";
  launcher.setAttribute("aria-expanded", "false");
  launcher.setAttribute("aria-controls", "chat-panel");
  launcher.innerHTML = `${icon.chat}<span class="label">Fale com a Lia</span><span class="dot" aria-hidden="true"></span>`;

  const panel = document.createElement("section");
  panel.id = "chat-panel";
  panel.className = "chat-panel";
  panel.hidden = true;
  panel.setAttribute("role", "dialog");
  panel.setAttribute("aria-label", "Conversa com a Lia, assistente virtual");
  panel.innerHTML = `
    <header class="chat-head">
      <div class="who"><strong>Lia</strong><span>Assistente virtual da Empório da Música</span></div>
      <button class="icon-btn" data-action="reset" title="Começar nova conversa" aria-label="Começar nova conversa">${icon.reset}</button>
      <button class="icon-btn" data-action="close" title="Fechar" aria-label="Fechar conversa">${icon.close}</button>
    </header>
    <div class="chat-log" aria-live="polite"></div>
    <div class="chat-suggest"></div>
    <form class="chat-form">
      <label class="visually-hidden" for="chat-input">Sua mensagem</label>
      <input id="chat-input" maxlength="500" autocomplete="off" placeholder="Pergunte sobre instrumentos, pedidos, trocas..." required>
      <button type="submit" aria-label="Enviar">${icon.send}</button>
    </form>
    <p class="chat-foot">Respostas automáticas com dados da loja. Para falar com uma pessoa, é só pedir. <a href="/privacidade#assistente">Como usamos seus dados</a></p>`;

  document.body.append(launcher, panel);
  const log = panel.querySelector(".chat-log");
  const form = panel.querySelector(".chat-form");
  const input = panel.querySelector("input");
  const sendBtn = form.querySelector("button");
  const suggest = panel.querySelector(".chat-suggest");
  let started = false;

  function add(text, cls) {
    const div = document.createElement("div");
    div.className = "msg " + cls;
    div.innerHTML = render(text);
    log.appendChild(div);
    log.scrollTop = log.scrollHeight;
    return div;
  }
  function addTrace(trace) {
    if (!trace || !trace.length) return;
    const labels = { search_products: "catálogo", get_order_status: "pedido", get_store_policy: "políticas",
      register_lead: "contato de vendas", handoff_to_human: "equipe humana" };
    const div = document.createElement("div");
    div.className = "trace";
    div.textContent = "consultou: " + [...new Set(trace.map((t) => labels[t.tool] || t.tool))].join(", ");
    log.appendChild(div);
    log.scrollTop = log.scrollHeight;
  }
  function showSuggestions(show) {
    suggest.innerHTML = "";
    if (!show) return;
    for (const s of SUGGESTIONS) {
      const b = document.createElement("button");
      b.type = "button";
      b.textContent = s;
      b.addEventListener("click", () => send(s));
      suggest.appendChild(b);
    }
  }
  function greet() {
    add("Oi! Eu sou a Lia, da Empório da Música. Posso ajudar com instrumentos, preços, pedidos, trocas, frete e pagamento.", "bot");
    showSuggestions(true);
  }

  async function start() {
    if (started) return;
    started = true;
    if (consent() === "granted" && store.get(SESSION_KEY)) {
      try {
        const res = await fetch("/api/history", { method: "POST", headers: { "content-type": "application/json" },
          body: JSON.stringify({ session_id: sessionId }) });
        const history = res.ok ? await res.json() : [];
        if (history.length) {
          history.forEach((m) => add(m.content, m.role === "user" ? "user" : "bot"));
          return;
        }
      } catch { /* fall through to greeting */ }
    }
    greet();
  }

  async function send(message) {
    message = message.trim();
    if (!message) return;
    showSuggestions(false);
    add(message, "user");
    const pending = add("digitando", "bot pending");
    sendBtn.disabled = true;
    try {
      const res = await fetch("/api/chat", { method: "POST", headers: { "content-type": "application/json" },
        body: JSON.stringify({ session_id: sessionId, message }) });
      const data = await res.json();
      pending.remove();
      add(data.reply || data.error || "Não consegui responder agora. Tente de novo.", "bot");
      addTrace(data.trace);
    } catch {
      pending.classList.remove("pending");
      pending.textContent = "Sem conexão. Verifique a internet e tente de novo.";
    } finally {
      sendBtn.disabled = false;
      input.focus();
    }
  }

  function open(prefill) {
    panel.hidden = false;
    launcher.setAttribute("aria-expanded", "true");
    start().then(() => { if (prefill) send(prefill); });
    setTimeout(() => input.focus(), 50);
  }
  function close() {
    panel.hidden = true;
    launcher.setAttribute("aria-expanded", "false");
    launcher.focus();
  }

  launcher.addEventListener("click", () => open());
  panel.querySelector('[data-action="close"]').addEventListener("click", close);
  panel.querySelector('[data-action="reset"]').addEventListener("click", async () => {
    fetch("/api/reset", { method: "POST", headers: { "content-type": "application/json" },
      body: JSON.stringify({ session_id: sessionId }) }).catch(() => {});
    sessionId = newSessionId();
    if (consent() === "granted") store.set(SESSION_KEY, sessionId);
    log.innerHTML = "";
    greet();
  });
  panel.addEventListener("keydown", (e) => { if (e.key === "Escape") close(); });
  form.addEventListener("submit", (e) => { e.preventDefault(); const m = input.value; input.value = ""; send(m); });
  document.addEventListener("click", (e) => {
    const trigger = e.target.closest("[data-ask]");
    if (trigger) { e.preventDefault(); open(trigger.dataset.ask || undefined); }
  });
  window.Lia = { open };

  if (!consent()) showConsent();
})();
