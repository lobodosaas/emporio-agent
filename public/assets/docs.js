// Renders sections of the store manual (/api/policies) into document pages
// and keeps the side navigation in sync with the section being read.
(() => {
  const esc = (s) => String(s).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));

  function block(b) {
    switch (b.type) {
      case "h3": return `<h3>${esc(b.text)}</h3>`;
      case "p": return `<p>${esc(b.text)}</p>`;
      case "ul": return `<ul>${b.items.map((i) => `<li>${esc(i)}</li>`).join("")}</ul>`;
      case "ol": return `<ol>${b.items.map((i) => `<li>${esc(i)}</li>`).join("")}</ol>`;
      case "table":
        return `<div class="table-wrap"><table><thead><tr>${b.header.map((h) => `<th scope="col">${esc(h)}</th>`).join("")}</tr></thead>
          <tbody>${b.rows.map((r) => `<tr>${r.map((c) => `<td>${esc(c)}</td>`).join("")}</tr>`).join("")}</tbody></table></div>`;
      default: return "";
    }
  }

  async function renderPolicies(target, { only } = {}) {
    let sections;
    try { sections = await (await fetch("/api/policies")).json(); }
    catch { target.innerHTML = "<p>Não foi possível carregar as políticas agora. Fale com a Lia ou ligue (67) 3341-4444.</p>"; return []; }
    if (only) sections = sections.filter((s) => only.includes(s.slug));
    target.innerHTML = sections.map((s, i) => `
      <section class="doc-section" id="${s.slug}" aria-labelledby="${s.slug}-t">
        <h2 id="${s.slug}-t">${only ? "" : `${i + 1}. `}${esc(s.title)}</h2>
        <hr class="rule">
        ${s.blocks.map(block).join("")}
      </section>`).join("");
    return sections;
  }

  function syncNav(nav) {
    const links = [...nav.querySelectorAll("a[href^='#']")];
    const map = new Map(links.map((a) => [a.getAttribute("href").slice(1), a]));
    const observer = new IntersectionObserver((entries) => {
      for (const e of entries) {
        if (!e.isIntersecting) continue;
        links.forEach((a) => a.classList.remove("active"));
        map.get(e.target.id)?.classList.add("active");
      }
    }, { rootMargin: "-20% 0px -70% 0px" });
    map.forEach((_, id) => { const el = document.getElementById(id); if (el) observer.observe(el); });
  }

  window.EmporioDocs = { renderPolicies, syncNav, esc };
})();
