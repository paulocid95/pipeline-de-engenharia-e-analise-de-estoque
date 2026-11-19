// Efeitos da página inicial. O Streamlit pode reexecutar este script a cada
// interação, então tudo é idempotente: cada elemento é ligado uma única vez.
(() => {
  if (window.__siEfeitos) { window.__siEfeitos.vincular(); return; }

  const reduz = matchMedia("(prefers-reduced-motion: reduce)").matches;
  const mouse = { x: -999, y: -999 };
  let rede = null;   // { canvas, ctx, pontos }
  let agendado = false;

  // ---------------- Rede de partículas que reage ao mouse ----------------
  function iniciarRede(canvas) {
    const ctx = canvas.getContext("2d");
    rede = { canvas, ctx, pontos: [] };
    redimensionar();
    requestAnimationFrame(quadro);
  }
  function redimensionar() {
    if (!rede) return;
    const W = (rede.canvas.width = innerWidth), H = (rede.canvas.height = innerHeight);
    const n = Math.min(90, Math.floor((W * H) / 16000));
    rede.pontos = Array.from({ length: n }, () => ({
      x: Math.random() * W, y: Math.random() * H, vx: (Math.random() - 0.5) * 0.4, vy: (Math.random() - 0.5) * 0.4,
    }));
  }
  function quadro() {
    if (!rede || !rede.canvas.isConnected) { rede = null; return; }   // saiu da página inicial
    const { ctx, pontos } = rede, W = rede.canvas.width, H = rede.canvas.height;
    ctx.clearRect(0, 0, W, H);
    for (const p of pontos) {
      const dx = p.x - mouse.x, dy = p.y - mouse.y, d = Math.hypot(dx, dy);
      if (d < 140 && d > 0) { p.x += (dx / d) * 1.6; p.y += (dy / d) * 1.6; }   // foge do cursor
      p.x += p.vx; p.y += p.vy;
      if (p.x < 0 || p.x > W) p.vx *= -1;
      if (p.y < 0 || p.y > H) p.vy *= -1;
      ctx.fillStyle = "rgba(140,180,255,.7)";
      ctx.beginPath(); ctx.arc(p.x, p.y, 1.6, 0, 7); ctx.fill();
    }
    for (let i = 0; i < pontos.length; i++) for (let j = i + 1; j < pontos.length; j++) {
      const a = pontos[i], b = pontos[j], d = Math.hypot(a.x - b.x, a.y - b.y);
      if (d < 130) {
        ctx.strokeStyle = `rgba(110,150,255,${0.22 * (1 - d / 130)})`; ctx.lineWidth = 1;
        ctx.beginPath(); ctx.moveTo(a.x, a.y); ctx.lineTo(b.x, b.y); ctx.stroke();
      }
    }
    for (const p of pontos) {
      const d = Math.hypot(p.x - mouse.x, p.y - mouse.y);
      if (d < 200) {
        ctx.strokeStyle = `rgba(91,224,176,${0.35 * (1 - d / 200)})`;
        ctx.beginPath(); ctx.moveTo(p.x, p.y); ctx.lineTo(mouse.x, mouse.y); ctx.stroke();
      }
    }
    requestAnimationFrame(quadro);
  }

  addEventListener("resize", redimensionar);
  addEventListener("mousemove", (e) => {
    mouse.x = e.clientX; mouse.y = e.clientY;
    const luz = document.getElementById("si-luz");
    if (luz) { luz.style.left = e.clientX + "px"; luz.style.top = e.clientY + "px"; }
  });

  // ---------------- Efeito de clique (onda) e volta ao topo ----------------
  document.addEventListener("click", (e) => {
    const b = e.target.closest(".si-btn, .st-key-si_acoes button, .st-key-si_cta button");
    if (!b) return;
    const r = b.getBoundingClientRect(), s = Math.max(r.width, r.height), o = document.createElement("span");
    o.className = "si-onda";
    o.style.cssText = `width:${s}px;height:${s}px;left:${e.clientX - r.left - s / 2}px;top:${e.clientY - r.top - s / 2}px`;
    b.appendChild(o); setTimeout(() => o.remove(), 700);
    if (b.closest(".st-key-si_demo, .st-key-si_cta")) {
      // Ao abrir a demonstração, o painel começa do topo
      document.querySelectorAll("[data-testid='stMain'], .stMain, [data-testid='stAppViewContainer']").forEach((el) => el.scrollTo?.(0, 0));
      scrollTo(0, 0);
    }
  }, true);

  // ---------------- Revelar ao rolar ----------------
  const observador = new IntersectionObserver((es) => es.forEach((e) => {
    if (e.isIntersecting) { e.target.classList.add("vis"); observador.unobserve(e.target); }
  }), { threshold: 0.12 });

  // ---------------- Passos com detalhe ----------------
  const DETALHES = [
    { t: "📤 Passo 1: Envie seus dados", i: [
      "<b>Formatos:</b> um Excel com abas (Estoque, Cotações, Ocorrências, Vendas) ou arquivos CSV separados.",
      "<b>Do jeito que estiver:</b> colunas com nomes diferentes, cabeçalho fora da primeira linha e linhas de \"TOTAL\" são reconhecidos automaticamente.",
      "<b>Coluna não reconhecida?</b> Você mesmo aponta qual coluna é o quê, numa lista simples.",
      "<b>Seus limites:</b> informe a partir de quantas unidades um item entra em alerta ou excesso. Se não informar, usamos o nosso padrão (alerta até 15 unidades, excesso acima de 100), que fica visível na tela.",
      "<b>Privacidade:</b> os dados ficam só na sua sessão e somem quando você fecha a página. Limite de 5 MB e 10 mil linhas por arquivo." ] },
    { t: "🧹 Passo 2: Higienização automática", i: [
      "<b>Preços:</b> \"R$ 1.234,56\", \"1234.56\" e \"1,234.56\" viram o mesmo número.",
      "<b>Quantidades:</b> \"12 un\", \"12,0\" e células vazias são corrigidas; estoques negativos são sinalizados.",
      "<b>Fornecedores:</b> \"FORNECEDOR A LTDA\" e \"forn. a\" são unificados em um só nome.",
      "<b>Produtos:</b> nomes parecidos em abas diferentes são ligados entre si, e SKUs duplicados são somados.",
      "<b>Casos duvidosos</b> são mostrados para você confirmar. Nada é descartado em silêncio: tudo aparece no relatório de limpeza." ] },
    { t: "📊 Passo 3: Análise inteligente", i: [
      "<b>Estoque:</b> status de cada item, capital imobilizado e produtos em ruptura.",
      "<b>Fornecedores:</b> nota de 0 a 100 combinando preço (30%), prazo (20%), lote mínimo (10%) e confiabilidade (40%).",
      "<b>Risco:</b> processos judiciais e problemas graves sem solução classificam o fornecedor como 🔴 Perigoso.",
      "<b>Compras:</b> a melhor opção de cada produto ao lado da mais barata e da mais rápida, com o motivo de cada uma ter perdido.",
      "<b>Previsão (em breve):</b> com o histórico de vendas, quando cada item acaba e quanto comprar." ] },
    { t: "🤖 Passo 4: Pergunte à IA", i: [
      "<b>Em português:</b> \"o que preciso comprar esta semana?\", \"qual fornecedor devo evitar?\".",
      "<b>Contexto completo:</b> a IA lê o estoque, as cotações e o ranking de risco.",
      "<b>Com responsabilidade:</b> nunca recomenda um fornecedor perigoso como opção principal e explica o porquê de cada sugestão.",
      "<b>Uso consciente:</b> limite de perguntas por sessão para manter o serviço gratuito." ] },
  ];
  // Ilustrações animadas dos passos (SVG via JS: o filtro do st.html remove <svg>)
  const ILUSTRACOES = [
    "<svg width=\"140\" height=\"100\" viewBox=\"0 0 140 100\"> <rect x=\"35\" y=\"70\" width=\"70\" height=\"20\" rx=\"6\" fill=\"none\" stroke=\"#3987e5\" stroke-width=\"3\"/> <g class=\"si-doc\"><rect x=\"55\" y=\"18\" width=\"30\" height=\"38\" rx=\"4\" fill=\"#1d2c5a\" stroke=\"#7fb6ff\" stroke-width=\"2\"/> <line x1=\"61\" y1=\"30\" x2=\"79\" y2=\"30\" stroke=\"#7fb6ff\" stroke-width=\"2\"/><line x1=\"61\" y1=\"38\" x2=\"79\" y2=\"38\" stroke=\"#7fb6ff\" stroke-width=\"2\"/> <line x1=\"61\" y1=\"46\" x2=\"72\" y2=\"46\" stroke=\"#7fb6ff\" stroke-width=\"2\"/></g> </svg>",
    "<svg width=\"140\" height=\"100\" viewBox=\"0 0 140 100\"> <g><rect class=\"si-cel\" x=\"20\" y=\"22\" width=\"30\" height=\"20\" rx=\"4\"/><rect class=\"si-cel\" x=\"55\" y=\"22\" width=\"30\" height=\"20\" rx=\"4\"/> <rect class=\"si-cel\" x=\"90\" y=\"22\" width=\"30\" height=\"20\" rx=\"4\"/><rect class=\"si-cel\" x=\"20\" y=\"50\" width=\"30\" height=\"20\" rx=\"4\"/> <rect class=\"si-cel\" x=\"55\" y=\"50\" width=\"30\" height=\"20\" rx=\"4\"/><rect class=\"si-cel\" x=\"90\" y=\"50\" width=\"30\" height=\"20\" rx=\"4\"/></g> <g class=\"si-varre\"><rect x=\"0\" y=\"14\" width=\"6\" height=\"66\" rx=\"3\" fill=\"#a99cff\" opacity=\".8\"/><text x=\"-4\" y=\"12\" font-size=\"12\">✨</text></g> </svg>",
    "<svg width=\"140\" height=\"100\" viewBox=\"0 0 140 100\"> <g><rect class=\"si-bar\" x=\"25\" y=\"40\" width=\"16\" height=\"45\" rx=\"3\" fill=\"#3987e5\"/><rect class=\"si-bar\" x=\"50\" y=\"25\" width=\"16\" height=\"60\" rx=\"3\" fill=\"#9085e9\"/> <rect class=\"si-bar\" x=\"75\" y=\"50\" width=\"16\" height=\"35\" rx=\"3\" fill=\"#199e70\"/><rect class=\"si-bar\" x=\"100\" y=\"15\" width=\"16\" height=\"70\" rx=\"3\" fill=\"#e0a020\"/></g> <line x1=\"18\" y1=\"86\" x2=\"124\" y2=\"86\" stroke=\"#3a4a7a\" stroke-width=\"2\"/> </svg>",
    "<svg width=\"140\" height=\"100\" viewBox=\"0 0 140 100\"> <g class=\"si-bolha\"><rect x=\"14\" y=\"16\" width=\"78\" height=\"26\" rx=\"12\" fill=\"#1d2c5a\" stroke=\"#7fb6ff\"/><text x=\"24\" y=\"33\" font-size=\"10\" fill=\"#cfe0ff\">O que comprar?</text></g> <g class=\"si-bolha b2\"><rect x=\"44\" y=\"52\" width=\"84\" height=\"30\" rx=\"12\" fill=\"#3987e5\"/><text x=\"54\" y=\"71\" font-size=\"10\" fill=\"#fff\">🤖 iPhone 15 com B</text></g> </svg>",
  ];
  function abrirPasso(n) {
    document.querySelectorAll(".si-passo").forEach((p) => p.classList.toggle("ativo", +p.dataset.p === n));
    const det = document.getElementById("si-detalhe");
    if (!det) return;
    det.classList.remove("entra"); void det.offsetWidth;
    det.innerHTML = `<h3>${DETALHES[n].t}</h3><ul>${DETALHES[n].i.map((x) => `<li>${x}</li>`).join("")}</ul>`;
    det.classList.add("entra");
  }

  // ---------------- Antes e depois ----------------
  const LINHAS = [
    [["  iphone 15 128gb ", "iPhone 15 128GB"], ["FORNECEDOR A LTDA", "Fornecedor A"], ["R$ 4.599,00", "4599.00"], ["12 un", "12"], ["", "Smartphones"]],
    [["Galaxy S24", "Galaxy S24"], ["forn. a", "Fornecedor A"], ["3,899.90", "3899.90"], ["-3", "0 ⚠️"], ["celular", "Smartphones"]],
    [["FONE JBL tune", "Fone JBL Tune"], ["Fornecedor_B", "Fornecedor B"], ["R$199", "199.00"], ["doze", "12"], ["Audio", "Fones de Ouvido"]],
    [["Carregador 20W", "Carregador 20W"], ["fornecedor b ", "Fornecedor B"], ["89,9", "89.90"], ["", "0"], ["carregadores", "Carregadores"]],
  ];
  const RELATORIO = ["✓ 4 preços padronizados", "✓ 4 fornecedores unificados em 2", "✓ 3 categorias deduzidas", "✓ 3 quantidades corrigidas", "⚠️ 1 estoque negativo sinalizado"];
  function sujar(caixa) {
    caixa.querySelector("tbody").innerHTML = LINHAS.map((l) => `<tr>${l.map((c) =>
      `<td class="${c[0] !== c[1] ? "sujo" : ""}">${c[0] === "" ? '<i style="opacity:.5">(vazio)</i>' : c[0]}</td>`).join("")}</tr>`).join("");
    caixa.querySelector(".si-rel").innerHTML = RELATORIO.map((r) => `<span>${r}</span>`).join("");
    caixa.querySelector(".si-ad-titulo").textContent = "❌ Antes: dados brutos";
    caixa.querySelector(".si-btn").textContent = "✨ Higienizar";
    caixa.dataset.limpo = "";
  }
  function limpar(caixa) {
    const tds = [...caixa.querySelectorAll("tbody td")]; let k = 0;
    LINHAS.flat().forEach((c, i) => {
      if (c[0] !== c[1]) setTimeout(() => { tds[i].textContent = c[1]; tds[i].className = "limpo"; }, 140 * k++);
    });
    [...caixa.querySelector(".si-rel").children].forEach((s, i) => setTimeout(() => s.classList.add("vis"), 140 * k + 200 * i));
    caixa.querySelector(".si-ad-titulo").textContent = "✅ Depois: dados higienizados";
    caixa.querySelector(".si-btn").textContent = "↺ Bagunçar de novo";
    caixa.dataset.limpo = "1";
  }

  // ---------------- O que a planilha precisa ter ----------------
  const FONTES = [
    { n: "📦 Estoque", d: '<span class="si-obrig">Obrigatório.</span> <code>produto</code> <code>quantidade</code> <code>preço</code> · opcional: <code>sku</code> <code>categoria</code> <code>fornecedor</code> <code>estoque_minimo</code>', on: true, fixo: true },
    { n: "💰 Cotações", d: "<code>produto</code> <code>fornecedor</code> <code>preço</code> · opcional: <code>prazo_dias</code> <code>lote_minimo</code>", on: false },
    { n: "⚠️ Ocorrências", d: "<code>fornecedor</code> <code>tipo</code> <code>data</code> · opcional: <code>gravidade</code> <code>status</code> <code>data_resolucao</code>", on: false },
    { n: "📈 Vendas", d: "<code>produto</code> <code>data</code> <code>quantidade_vendida</code>", on: false },
  ];
  const LIBERA = [
    { n: "📊 Visão Geral", r: [0] }, { n: "📋 Tabela completa", r: [0] }, { n: "🚨 Alertas de ruptura", r: [0] },
    { n: "🤖 Assistente de IA", r: [0] }, { n: "🏭 Fornecedores", r: [1] }, { n: "🛒 Simulador de compras", r: [1] },
    { n: "🛡️ Ranking & Risco", r: [1, 2] }, { n: "📈 Previsão de demanda", r: [3] },
  ];
  function desenharFontes(fEl, lEl) {
    fEl.innerHTML = FONTES.map((f, i) => `<div class="si-fonte ${f.on ? "on" : ""} ${f.fixo ? "fixo" : ""}" data-i="${i}">
      <div class="si-chk">${f.on ? "✓" : ""}</div><div><h4>${f.n}</h4><p>${f.d}</p></div></div>`).join("");
    const ok = (l) => l.r.every((r) => FONTES[r].on);
    const ativos = LIBERA.filter(ok).length;
    lEl.innerHTML = LIBERA.map((l) => `<div class="si-lib ${ok(l) ? "on" : ""}">${l.n}<span class="si-cad">${ok(l) ? "🔓" : "🔒"}</span></div>`).join("")
      + `<div class="si-barra-prog"><div style="width:${(ativos / LIBERA.length) * 100}%"></div></div>`
      + `<div class="si-prog-txt">${ativos} de ${LIBERA.length} análises liberadas${ativos === LIBERA.length ? " 🎉 potencial máximo!" : ""}</div>`;
    fEl.querySelectorAll(".si-fonte").forEach((el) => el.addEventListener("click", () => {
      const f = FONTES[+el.dataset.i];
      if (f.fixo) return;
      f.on = !f.on; desenharFontes(fEl, lEl);
    }));
  }

  // ---------------- Contadores ----------------
  function contar(el) {
    const fim = +el.dataset.conta, t0 = performance.now();
    (function passo(t) {
      const k = Math.min(1, (t - t0) / 1600);
      el.textContent = Math.round(fim * (1 - Math.pow(1 - k, 3)));
      if (k < 1) requestAnimationFrame(passo);
    })(t0);
  }

  // ---------------- Liga cada elemento novo uma única vez ----------------
  // Cada efeito tem a sua própria marca: um elemento pode receber vários efeitos
  function novos(seletor) {
    const marca = "si" + seletor.replace(/[^a-z]/gi, "");
    return [...document.querySelectorAll(seletor)].filter((el) => !el.dataset[marca] && (el.dataset[marca] = "1"));
  }
  function vincular() {
    const canvas = document.getElementById("si-rede");
    if (canvas && !reduz && (!rede || rede.canvas !== canvas)) iniciarRede(canvas);

    novos(".si-tilt").forEach((el) => {
      const forca = el.classList.contains("si-painel") ? 12 : 7;
      el.addEventListener("mousemove", (e) => {
        const r = el.getBoundingClientRect(), x = (e.clientX - r.left) / r.width, y = (e.clientY - r.top) / r.height;
        el.style.setProperty("--mx", x * 100 + "%"); el.style.setProperty("--my", y * 100 + "%");
        if (!reduz) el.style.transform = `perspective(900px) rotateY(${(x - 0.5) * forca}deg) rotateX(${(0.5 - y) * forca}deg)`;
      });
      el.addEventListener("mouseleave", () => (el.style.transform = ""));
    });

    novos(".si-rev").forEach((el, i) => {
      if (reduz) { el.classList.add("vis"); return; }
      el.style.transitionDelay = (i % 4) * 90 + "ms"; observador.observe(el);
    });
    novos("[data-conta]").forEach(contar);

    const passos = novos(".si-passo");
    passos.forEach((p) => {
      const ilus = p.querySelector(".si-ilus");
      if (ilus) ilus.innerHTML = ILUSTRACOES[+p.dataset.p] || "";
      p.addEventListener("click", () => abrirPasso(+p.dataset.p));
    });
    if (passos.length) abrirPasso(0);

    novos(".si-ad").forEach((caixa) => {
      sujar(caixa);
      caixa.querySelector(".si-btn").addEventListener("click", () => (caixa.dataset.limpo ? sujar(caixa) : limpar(caixa)));
    });

    const fEl = novos("#si-fontes")[0];
    if (fEl) desenharFontes(fEl, document.getElementById("si-libera"));
  }
  function agendar() {
    if (agendado) return;
    agendado = true;
    requestAnimationFrame(() => { agendado = false; vincular(); });
  }

  window.__siEfeitos = { vincular };
  new MutationObserver(agendar).observe(document.body, { childList: true, subtree: true });
  vincular();
})();
