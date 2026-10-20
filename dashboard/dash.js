// Runtime mínimo do painel: a mesma API `dash` que a página usava no artifact,
// lendo os arquivos versionados em data/ (um diretório por freeze) e static/.
(() => {
  const POR_FREEZE = ["totais", "por_uf", "mudancas", "votos_mapa", "candidatos"];

  // Freeze escolhido: ?freeze= na URL; sem ele, o mais recente processado (definido ao ler freezes.csv)
  let freeze = new URLSearchParams(location.search).get("freeze") || "";

  function urlDe(id) {
    if (id === "freezes") return "data/freezes.csv";
    if (id === "ufs") return "static/ufs.json";
    if (!freeze) return null;
    if (POR_FREEZE.includes(id)) return `data/${freeze}/${id}.csv`;
    const m = /^agreg_([A-Z]{2})$/.exec(id);
    if (m) return `data/${freeze}/agregadas_uf/${m[1]}.json`;
    return null;
  }
  const conhecido = id => id === "freezes" || id === "ufs" || POR_FREEZE.includes(id) || /^agreg_[A-Z]{2}$/.test(id);

  const cache = new Map();   // id -> {status, data, columns, message}
  const calcs = new Map();   // id -> {inputs, fn}
  const ouvintes = [];
  let agendado = false;

  function avisa() {
    if (agendado) return;
    agendado = true;
    requestAnimationFrame(() => {
      agendado = false;
      for (const fn of ouvintes) {
        try { fn(); } catch (e) { console.error(e); }
      }
    });
  }

  function linhas(json) {
    if (Array.isArray(json)) return json;
    for (const k of ["rows", "data", "results"]) if (json && Array.isArray(json[k])) return json[k];
    return json;
  }

  function carrega(id) {
    const url = urlDe(id);
    const st = { status: "loading", data: [], columns: [], message: "" };
    cache.set(id, st);
    if (!url) return st;  // o freeze ainda não é conhecido: freezes.csv vai chamar de novo
    fetch(url)
      .then(r => { if (!r.ok) throw new Error(`${r.status} ao ler ${url}`); return r.text(); })
      .then(txt => {
        if (cache.get(id) !== st) return;  // o freeze mudou no meio do caminho
        if (url.endsWith(".csv")) {
          const rows = d3.csvParse(txt);
          st.columns = rows.columns;
          st.data = Array.from(rows);
        } else {
          st.data = linhas(JSON.parse(txt));
          st.columns = Array.isArray(st.data) && st.data[0] ? Object.keys(st.data[0]) : [];
        }
        st.status = "ok";
        if (id === "freezes") escolheFreeze(st.data);
        avisa();
      })
      .catch(e => {
        if (cache.get(id) !== st) return;
        console.error(e);
        st.status = "error";
        st.message = String(e.message || e);
        avisa();
      });
    return st;
  }

  function calcula(id) {
    const c = calcs.get(id);
    const ins = c.inputs.map(i => dados(i));
    if (ins.some(s => s.status === "error")) return { status: "error", data: [], columns: [], message: "Uma das entradas não carregou" };
    if (ins.some(s => s.status !== "ok")) return { status: "loading", data: [], columns: [], message: "" };
    // Recalcula só quando alguma entrada mudou (a página lê o mesmo calc várias vezes por desenho)
    const chave = ins.map(s => s.data);
    if (c.memo && c.chave.every((d, i) => d === chave[i])) return c.memo;
    try {
      const data = c.fn(...chave);
      c.chave = chave;
      c.memo = { status: "ok", data, columns: Array.isArray(data) && data[0] ? Object.keys(data[0]) : [], message: "" };
      return c.memo;
    } catch (e) {
      console.error(e);
      return { status: "error", data: [], columns: [], message: String(e.message || e) };
    }
  }

  function dados(id) {
    let st;
    if (calcs.has(id)) st = calcula(id);
    else if (cache.has(id)) st = cache.get(id);
    else if (conhecido(id)) st = carrega(id);
    else st = { status: "missing", data: [], columns: [], message: `Fonte ${id} não existe` };
    return { ...st, refreshing: false, meta: [], rows: st.data, value: st.data };
  }

  // Freezes processados, do mais recente ao mais antigo
  const processados = rows => rows.filter(r => r.processado === "sim").map(r => r.freeze).sort().reverse();

  function escolheFreeze(rows) {
    const lista = processados(rows);
    if (!freeze || !lista.includes(freeze)) trocaFreeze(lista[0] || "", false);
    preencheSeletor(lista);
  }

  function trocaFreeze(nome, naUrl = true) {
    freeze = nome;
    for (const id of [...cache.keys()]) if (id !== "freezes" && id !== "ufs") cache.delete(id);
    if (naUrl) {
      const u = new URL(location.href);
      u.searchParams.set("freeze", nome);
      history.replaceState(null, "", u);
    }
    const sel = document.getElementById("freeze-sel");
    if (sel) sel.value = nome;
    avisa();
  }

  function preencheSeletor(lista) {
    const sel = document.getElementById("freeze-sel");
    if (!sel) return;
    const rot = n => { const [d, h] = n.split("_"); const [a, m, dia] = d.split("-"); return `${dia}/${m}/${a} ${h.slice(0, 2)}h${h.slice(2)}`; };
    sel.replaceChildren(...lista.map((n, i) => new Option(rot(n) + (i === 0 ? " (mais recente)" : ""), n)));
    sel.value = freeze;
    sel.disabled = lista.length < 2;
    if (!sel.dataset.ligado) {
      sel.dataset.ligado = "1";
      sel.addEventListener("change", () => trocaFreeze(sel.value));
    }
  }

  const cores = escuro => escuro
    ? ["#6ea8fe", "#f0a35e", "#5fc9a8", "#e58fb6", "#b49cf0", "#d8c25a", "#7fc4e8", "#e0857a"]
    : ["#2f6fdb", "#d9781f", "#1f9a75", "#c64f86", "#7a5bd1", "#a68a12", "#2a8fc0", "#c4473a"];
  const temaEscuro = matchMedia("(prefers-color-scheme: dark)");

  window.dash = {
    data: dados,
    onData(fn) {
      ouvintes.push(fn);
      try { fn(); } catch (e) { console.error(e); }
    },
    calc(id, { inputs, fn }) { calcs.set(id, { inputs, fn }); },
    loader() {},
    colors: cores(temaEscuro.matches),
    refresh() {},
    params: () => ({}),
    setParams() {},
    resetParams() {},
    setLink(nome) { history.replaceState(null, "", "#" + nome); },
    freeze: () => freeze,
  };

  // Redesenha quando a largura muda
  let largura = 0;
  new ResizeObserver(([e]) => {
    const w = Math.round(e.contentRect.width);
    if (w !== largura) { largura = w; avisa(); }
  }).observe(document.getElementById("dash-root"));

  dados("freezes");
})();
