/* =============================================================================
   Mapa Catalogo + CNEFE 2022 + Censo 2025
   -----------------------------------------------------------------------------
   As coordenadas vem do Catalogo de Escolas do INEP e sao comparadas as do CNEFE,
   como em escolas_inep_cnefe.js. O Censo 2025 so informa a situacao de cada escola
   e as divergencias com o Catalogo; ele nao fornece nem altera posicao.

   Dados:
     data/escolas/<UF>.json (escolas__gerar_dados_mapa.py)
       inep : [codigo, nome, lat, lon, status, restricao, idx_cnefe, dist_m, endereco, municipio]
       cnefe: [cod_unico, nome, lat, lon, idx_inep, endereco]
     data/catalogo_censo_2025/<UF>.json e index.json (catalogo_censo_2025__comparar.py)
       situacao   : { codigo: 1 | 2 | 3 } - ausente = nao consta no Censo 2025
       so_no_censo: [codigo, nome, municipio, situacao]

   A camada de canvas segue a do mapa INEP x CNEFE: cada ponto e projetado uma vez
   no zoom 0 e, a cada redesenho, so escalado e transladado.
   ============================================================================= */

(function () {
  "use strict";

  const UFS = ["AC", "AL", "AM", "AP", "BA", "CE", "DF", "ES", "GO", "MA", "MG", "MS", "MT", "PA", "PB",
               "PE", "PI", "PR", "RJ", "RN", "RO", "RR", "RS", "SC", "SE", "SP", "TO"];
  const CORES = { 1: "#2166ac", 2: "#e0a800", 3: "#8e44ad", N: "#d73027", CNEFE: "#4d4d4d", DESTAQUE: "#ffd400" };
  const ROTULO_SITUACAO = { 1: "Em atividade", 2: "Paralisada", 3: "Extinta", N: "Não consta no Censo 2025" };
  const ROTULO_CATALOGO = { F: "em funcionamento", P: "paralisada", E: "exclusiva/especial" };
  const ORDEM_SITUACAO = ["1", "2", "3", "N"];   // ordem nos filtros
  // Ordem do desenho: so "nao consta" fica sobre "em atividade". Com paralisadas e extintas por cima,
  // a vista do Brasil pareceria dominada por elas, que sao poucas (9.682 contra 145.734 em atividade).
  const ORDEM_DESENHO = ["2", "3", "1", "N"];
  const ROTULO_NIVEL = {
    N1: "N1 · CEP + número + logradouro", N2: "N2 · CEP + logradouro", N3: "N3 · nome exato",
    N4: "N4 · nome ajustado", AMB: "Ambígua (empate entre candidatos)", SEM: "Sem par no CNEFE",
  };
  const FAIXAS = [
    { id: "a", rotulo: "< 50 m", max: 50 }, { id: "b", rotulo: "50 – 200 m", max: 200 },
    { id: "c", rotulo: "200 m – 1 km", max: 1000 }, { id: "d", rotulo: "1 – 5 km", max: 5000 },
    { id: "e", rotulo: "> 5 km", max: Infinity }, { id: "x", rotulo: "Sem distância (sem par ou sem coordenada)", max: null },
  ];
  const CATEGORIAS = {
    so_catalogo: { titulo: "Só no Catálogo", detalhe: "não constam no Censo 2025" },
    so_censo: { titulo: "Só no Censo 2025", detalhe: "não constam no Catálogo; sem posição" },
    sem_coord: { titulo: "No Censo e no Catálogo, sem coordenada", detalhe: "o Catálogo não informa latitude e longitude" },
  };
  const ZOOM_LINHAS = 11;
  const LIMITE_LINHAS_TABELA = 500;

  // ------------------------------------------------------------------ estado
  const filtros = {
    censo: { 1: true, 2: true, 3: true, N: true },
    semCoord: true,
    cnefe: { par: true, sem: true },
    faixa: { a: true, b: true, c: true, d: true, e: true, x: true },
    linhas: true,
  };
  let conjuntos = [];          // dados das UFs carregadas, com coordenadas projetadas
  let indice = null;           // data/catalogo_censo_2025/index.json
  let recorteAtual = null;
  let selecionado = null;      // { conj, i } escola destacada
  let geracaoRecorte = 0;      // descarta uma carga antiga quando o recorte muda no meio dela
  const cache = {};

  function fmt(n) { return Number(n).toLocaleString("pt-BR"); }
  function esc(t) {
    return String(t ?? "").replace(/[&<>"]/g, (ch) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[ch]));
  }
  function semAcento(t) { return String(t).toUpperCase().normalize("NFD").replace(/[̀-ͯ]/g, ""); }

  // ------------------------------------------------------------------ mapa
  const mapa = L.map("mapa", { zoomControl: true, preferCanvas: true }).setView([-14.5, -52], 4);
  const BASES = {
    osm: L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png",
      { maxZoom: 19, attribution: "© OpenStreetMap" }),
    esri: L.tileLayer("https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
      { maxZoom: 19, attribution: "Esri World Imagery" }),
  };
  let baseAtual = BASES.osm.addTo(mapa);
  document.getElementById("sel-base").addEventListener("change", (ev) => {
    mapa.removeLayer(baseAtual);
    baseAtual = BASES[ev.target.value].addTo(mapa);
    baseAtual.bringToBack();
  });

  fetch("data/BR_uf_2024_minima.geojson").then((r) => r.json()).then((geo) => {
    L.geoJSON(geo, { interactive: false, style: { color: "#334155", weight: 1, fill: false, opacity: 0.6 } }).addTo(mapa);
  }).catch((erro) => console.error("divisas das UFs:", erro));

  // ------------------------------------------------------------------ camada canvas
  const CamadaPontos = L.Layer.extend({
    onAdd(map) {
      this._canvas = L.DomUtil.create("canvas", "leaflet-zoom-hide");
      map.getPanes().overlayPane.appendChild(this._canvas);
      map.on("moveend zoomend resize", this.redesenhar, this);
      this.redesenhar();
    },
    onRemove(map) {
      L.DomUtil.remove(this._canvas);
      map.off("moveend zoomend resize", this.redesenhar, this);
    },
    redesenhar() {
      const map = this._map;
      if (!map) return;
      const tamanho = map.getSize();
      const dpr = window.devicePixelRatio || 1;
      const canvas = this._canvas;
      canvas.width = tamanho.x * dpr;
      canvas.height = tamanho.y * dpr;
      canvas.style.width = tamanho.x + "px";
      canvas.style.height = tamanho.y + "px";
      const topoEsq = map.containerPointToLayerPoint([0, 0]);
      L.DomUtil.setPosition(canvas, topoEsq);
      const ctx = canvas.getContext("2d");
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      desenhar(ctx, map, tamanho, topoEsq);
    },
  });
  const camada = new CamadaPontos().addTo(mapa);

  function raioPorZoom(z) {
    return z < 6 ? 1.3 : z < 9 ? 2.2 : z < 12 ? 3.2 : z < 15 ? 4.5 : 6;
  }

  function faixaDe(dist) {
    if (dist === null) return "x";
    for (const f of FAIXAS) if (f.max !== null && dist < f.max) return f.id;
    return "e";
  }

  /** A escola passa nos filtros? (situacao no Censo, origem da posicao, faixa de distancia) */
  function escolaVisivel(c, i) {
    const e = c.inep[i];
    if (!filtros.censo[c.sit[i]] || !filtros.faixa[faixaDe(e[7])]) return false;
    return e[2] !== null || filtros.semCoord;
  }

  function desenhar(ctx, map, tamanho, topoEsq) {
    const z = map.getZoom();
    const escala = Math.pow(2, z);
    const origem = map.getPixelOrigin();
    const ox = origem.x + topoEsq.x, oy = origem.y + topoEsq.y;
    const r = raioPorZoom(z);
    const margem = 10, W = tamanho.x + margem, H = tamanho.y + margem;
    const telaX = (x0) => x0 * escala - ox, telaY = (y0) => y0 * escala - oy;

    for (const c of conjuntos) {
      c.visiveis = [];   // [tipo, indice, x, y] para o clique
      // --- linhas do par
      if (filtros.linhas && z >= ZOOM_LINHAS) {
        ctx.lineWidth = z >= 15 ? 2 : 1.2;
        for (let i = 0; i < c.inep.length; i++) {
          const j = c.inep[i][6];
          if (j < 0 || isNaN(c.ix[i]) || isNaN(c.cx[j]) || !escolaVisivel(c, i)) continue;
          const x1 = telaX(c.ix[i]), y1 = telaY(c.iy[i]), x2 = telaX(c.cx[j]), y2 = telaY(c.cy[j]);
          if ((x1 < -margem && x2 < -margem) || (x1 > W && x2 > W) || (y1 < -margem && y2 < -margem) || (y1 > H && y2 > H)) continue;
          ctx.strokeStyle = CORES[c.sit[i]];
          ctx.beginPath(); ctx.moveTo(x1, y1); ctx.lineTo(x2, y2); ctx.stroke();
        }
      }
      // --- CNEFE (quadrados): com par cheio, sem par vazado
      const lado = r * 1.6;
      ctx.lineWidth = 1;
      for (let j = 0; j < c.cnefe.length; j++) {
        if (isNaN(c.cx[j])) continue;
        const idxEscola = c.cnefe[j][4], pareado = idxEscola >= 0;
        if (pareado ? !filtros.cnefe.par : !filtros.cnefe.sem) continue;
        if (pareado && !escolaVisivel(c, idxEscola)) continue;
        const x = telaX(c.cx[j]), y = telaY(c.cy[j]);
        if (x < -margem || y < -margem || x > W || y > H) continue;
        if (pareado) { ctx.fillStyle = CORES.CNEFE; ctx.fillRect(x - lado / 2, y - lado / 2, lado, lado); }
        else { ctx.strokeStyle = CORES.CNEFE; ctx.strokeRect(x - lado / 2, y - lado / 2, lado, lado); }
        c.visiveis.push(["C", j, x, y]);
      }
    }
    // --- escolas (circulos) por cima dos quadrados, na ordem de desenho, em todas as UFs
    for (const situacao of ORDEM_DESENHO) {
      const naoConsta = situacao === "N";
      const raio = naoConsta ? r * 1.35 : r;
      for (const c of conjuntos) {
        for (let i = 0; i < c.inep.length; i++) {
          if (c.sit[i] !== situacao || !escolaVisivel(c, i)) continue;
          const e = c.inep[i];
          let px = c.ix[i], py = c.iy[i], vazado = false;
          if (isNaN(px)) {   // sem coordenada no Catalogo: vazado na posicao do par no CNEFE, se houver
            if (e[6] < 0 || isNaN(c.cx[e[6]])) continue;
            px = c.cx[e[6]]; py = c.cy[e[6]]; vazado = true;
          }
          const x = telaX(px), y = telaY(py);
          if (x < -margem || y < -margem || x > W || y > H) continue;
          ctx.beginPath(); ctx.arc(x, y, raio, 0, 2 * Math.PI);
          if (vazado) { ctx.strokeStyle = CORES[situacao]; ctx.lineWidth = 1.5; ctx.stroke(); }
          else {
            ctx.fillStyle = CORES[situacao]; ctx.fill();
            // Contorno escuro: "nao consta" se distingue tambem sem depender da cor.
            // Nos zooms baixos o ponto e tao pequeno que o contorno esconderia o vermelho.
            if (naoConsta && z >= 6) { ctx.strokeStyle = "#111"; ctx.lineWidth = 1; ctx.stroke(); }
          }
          c.visiveis.push(["I", i, x, y]);
        }
      }
    }
    // --- destaque do par selecionado
    if (selecionado) {
      const { conj: c, i } = selecionado, j = c.inep[i][6];
      const pontos = [];
      if (!isNaN(c.ix[i])) pontos.push([telaX(c.ix[i]), telaY(c.iy[i])]);
      if (j >= 0 && !isNaN(c.cx[j])) pontos.push([telaX(c.cx[j]), telaY(c.cy[j])]);
      ctx.strokeStyle = "#111"; ctx.lineWidth = 3;
      if (pontos.length === 2) { ctx.beginPath(); ctx.moveTo(...pontos[0]); ctx.lineTo(...pontos[1]); ctx.stroke(); }
      for (const [x, y] of pontos) {
        ctx.beginPath(); ctx.arc(x, y, r + 6, 0, 2 * Math.PI);
        ctx.strokeStyle = "#111"; ctx.lineWidth = 3; ctx.stroke();
        ctx.strokeStyle = CORES.DESTAQUE; ctx.lineWidth = 1.5; ctx.stroke();
      }
    }
  }

  // ------------------------------------------------------------------ dados
  /** Projeta lat/lon para pixels no zoom 0 (NaN quando falta coordenada). */
  function projetar(linhas) {
    const xs = new Float64Array(linhas.length), ys = new Float64Array(linhas.length);
    for (let k = 0; k < linhas.length; k++) {
      const lat = linhas[k][2], lon = linhas[k][3];
      if (lat === null || lon === null) { xs[k] = NaN; ys[k] = NaN; continue; }
      const p = mapa.project([lat, lon], 0);
      xs[k] = p.x; ys[k] = p.y;
    }
    return [xs, ys];
  }

  async function lerJson(url) {
    const resp = await fetch(url);
    if (!resp.ok) throw new Error(url + ": HTTP " + resp.status);
    return resp.json();
  }

  async function carregarUF(uf) {
    if (!cache[uf]) {
      // Os dois arquivos sao obrigatorios: sem o do Censo, toda escola pareceria "nao consta".
      const [dados, censo] = await Promise.all([
        lerJson("data/escolas/" + uf + ".json"),
        lerJson("data/catalogo_censo_2025/" + uf + ".json"),
      ]);
      const [ix, iy] = projetar(dados.inep);
      const [cx, cy] = projetar(dados.cnefe);
      const sit = dados.inep.map((e) => {
        const s = censo.situacao[e[0]];
        return s === undefined ? "N" : String(s);
      });
      cache[uf] = { uf, inep: dados.inep, cnefe: dados.cnefe, soNoCenso: censo.so_no_censo, sit, ix, iy, cx, cy, visiveis: [] };
    }
    return cache[uf];
  }

  const statusCarga = document.getElementById("status-carga");

  async function selecionarRecorte(valor) {
    const geracao = ++geracaoRecorte;
    recorteAtual = valor;
    selecionado = null;
    mapa.closePopup();
    const lista = valor === "BR" ? UFS : [valor];
    const carregados = [], falhas = [];
    conjuntos = [];
    camada.redesenhar();
    let n = 0;
    for (const uf of lista) {
      statusCarga.textContent = "Carregando " + uf + " (" + (++n) + "/" + lista.length + ")…";
      try {
        const conjunto = await carregarUF(uf);
        if (geracao !== geracaoRecorte) return;
        carregados.push(conjunto);
        conjuntos = carregados;
        camada.redesenhar();
      } catch (erro) {
        if (geracao !== geracaoRecorte) return;
        console.error(erro);
        falhas.push(uf);
      }
    }
    atualizarContagens();
    atualizarCartoes(valor, falhas);
    enquadrar(valor);
    const totalI = conjuntos.reduce((s, c) => s + c.inep.length, 0);
    const totalC = conjuntos.reduce((s, c) => s + c.cnefe.length, 0);
    statusCarga.textContent = falhas.length
      ? "Não foi possível carregar: " + falhas.join(", ") + ". Os números abaixo do recorte estão incompletos."
      : fmt(totalI) + " escolas do Catálogo · " + fmt(totalC) + " estabelecimentos CNEFE";
  }

  function enquadrar(valor) {
    const q = new URLSearchParams(location.search);
    if (q.has("lat") && q.has("lon")) {   // vista compartilhavel: ?uf=SP&lat=..&lon=..&z=..
      mapa.setView([Number(q.get("lat")), Number(q.get("lon"))], Number(q.get("z") || 14));
      return;
    }
    if (valor === "BR") { mapa.setView([-14.5, -52], 4); return; }
    let minLat = 90, maxLat = -90, minLon = 180, maxLon = -180;
    for (const c of conjuntos) {
      for (const e of c.inep) {
        if (e[2] === null) continue;
        minLat = Math.min(minLat, e[2]); maxLat = Math.max(maxLat, e[2]);
        minLon = Math.min(minLon, e[3]); maxLon = Math.max(maxLon, e[3]);
      }
    }
    if (minLat <= maxLat) mapa.fitBounds([[minLat, minLon], [maxLat, maxLon]], { padding: [20, 20] });
  }

  // ------------------------------------------------------------------ painel
  function linhaFiltro(html, attrs, qtdId) {
    return '<label class="chk"><input type="checkbox" ' + attrs + " checked>" + html +
           '<span class="qtd" id="' + qtdId + '"></span></label>';
  }

  document.getElementById("lista-censo").innerHTML = ORDEM_SITUACAO.map((s) =>
    linhaFiltro('<span class="sw' + (s === "N" ? " destacado" : "") + '" style="background:' + CORES[s] + '"></span>' + ROTULO_SITUACAO[s],
                'data-censo="' + s + '"', "q-s" + s)).join("");
  document.getElementById("lista-faixas").innerHTML = FAIXAS.map((f) =>
    linhaFiltro(f.rotulo, 'data-faixa="' + f.id + '"', "q-f" + f.id)).join("");

  document.querySelector(".esc-sidebar").addEventListener("change", (ev) => {
    const el = ev.target, d = el.dataset;
    if (d.censo) filtros.censo[d.censo] = el.checked;
    else if (d.cnefe) filtros.cnefe[d.cnefe] = el.checked;
    else if (d.faixa) filtros.faixa[d.faixa] = el.checked;
    else if (el.id === "chk-sem-coord") filtros.semCoord = el.checked;
    else if (el.id === "chk-linhas") filtros.linhas = el.checked;
    else return;
    if (selecionado && !escolaVisivel(selecionado.conj, selecionado.i)) { selecionado = null; mapa.closePopup(); }
    camada.redesenhar();
  });

  /** Contagens dos filtros, no recorte carregado (cheios + vazados = o que pode ser desenhado). */
  function atualizarContagens() {
    const q = {}, somar = (k) => { q[k] = (q[k] || 0) + 1; };
    for (const c of conjuntos) {
      c.inep.forEach((e, i) => {
        somar("f" + faixaDe(e[7]));
        if (e[2] !== null) somar("s" + c.sit[i]);
        else if (e[6] >= 0) somar("vazado");
      });
      for (const r of c.cnefe) somar(r[4] >= 0 ? "cnefe-par" : "cnefe-sem");
    }
    for (const s of ORDEM_SITUACAO) document.getElementById("q-s" + s).textContent = fmt(q["s" + s] || 0);
    for (const f of FAIXAS) document.getElementById("q-f" + f.id).textContent = fmt(q["f" + f.id] || 0);
    document.getElementById("q-vazado").textContent = fmt(q.vazado || 0);
    document.getElementById("q-cnefe-par").textContent = fmt(q["cnefe-par"] || 0);
    document.getElementById("q-cnefe-sem").textContent = fmt(q["cnefe-sem"] || 0);
  }

  function atualizarCartoes(valor, falhas) {
    const painel = document.getElementById("painel-cartoes");
    const r = indice.resumo.find((l) => l.UF === valor);
    if (!r) { painel.textContent = "Sem resumo para " + valor + "."; return; }
    const cartoes = [
      ["so_catalogo", r.SO_NO_CATALOGO, fmt(r.SO_NO_CATALOGO_COM_COORD) + " têm coordenada: círculo vermelho com contorno"],
      ["so_censo", r.SO_NO_CENSO, fmt(r.SO_NO_CENSO_EM_ATIVIDADE) + " em atividade; só na lista"],
      ["sem_coord", r.CENSO_SEM_COORD, fmt(r.CENSO_SEM_COORD_EM_ATIVIDADE) + " em atividade; " + fmt(r.CENSO_SEM_COORD_COM_PAR_CNEFE) + " têm par no CNEFE"],
    ];
    // Sem o arquivo de uma UF, a lista ficaria menor que o numero do cartao.
    const desativar = falhas.length ? " disabled" : "";
    painel.innerHTML = cartoes.map(([id, total, nota]) =>
      '<button type="button" class="cartao" data-categoria="' + id + '"' + desativar + "><b>" + fmt(total) + "</b><span>" +
      esc(CATEGORIAS[id].titulo) + " · " + esc(CATEGORIAS[id].detalhe) + "</span><small>" + esc(nota) + " · ver lista</small></button>").join("") +
      '<p class="nota">No recorte: Catálogo ' + fmt(r.CATALOGO) + " · Censo 2025 " + fmt(r.CENSO) + " · nos dois " + fmt(r.EM_AMBOS) + ".</p>";
  }

  // ------------------------------------------------------------------ lista das divergencias
  const dlg = document.getElementById("dlg"), dlgCorpo = document.getElementById("dlg-corpo"),
        dlgFiltro = document.getElementById("dlg-filtro"), dlgAviso = document.getElementById("dlg-aviso");
  let linhasDlg = [];

  /** Monta as linhas da categoria a partir das UFs carregadas: {codigo, nome, municipio, uf, situacao, conj, i}. */
  function linhasDaCategoria(categoria) {
    const linhas = [];
    for (const c of conjuntos) {
      if (categoria === "so_censo") {
        for (const [codigo, nome, municipio, situacao] of c.soNoCenso) {
          linhas.push({ codigo, nome, municipio, uf: c.uf, situacao: ROTULO_SITUACAO[situacao] + " (Censo 2025)", conj: null, i: -1 });
        }
        continue;
      }
      c.inep.forEach((e, i) => {
        const pertence = categoria === "so_catalogo" ? c.sit[i] === "N" : c.sit[i] !== "N" && e[2] === null;
        if (!pertence) return;
        const situacao = categoria === "so_catalogo"
          ? ROTULO_CATALOGO[e[5]] + " (Catálogo)" : ROTULO_SITUACAO[c.sit[i]] + " (Censo 2025)";
        linhas.push({ codigo: e[0], nome: e[1], municipio: e[9], uf: c.uf, situacao, conj: c, i });
      });
    }
    return linhas;
  }

  function temPosicao(l) {
    if (!l.conj) return false;
    const e = l.conj.inep[l.i];
    return e[2] !== null || (e[6] >= 0 && !isNaN(l.conj.cx[e[6]]));
  }

  function desenharTabela() {
    const termo = semAcento(dlgFiltro.value.trim());
    const filtradas = termo
      ? linhasDlg.filter((l) => l.codigo.includes(termo) || semAcento(l.nome).includes(termo) || semAcento(l.municipio).includes(termo))
      : linhasDlg;
    const visiveis = filtradas.slice(0, LIMITE_LINHAS_TABELA);
    dlgCorpo.innerHTML = visiveis.map((l) =>
      "<tr><td>" + esc(l.codigo) + "</td><td>" + esc(l.nome) + "</td><td>" + esc(l.municipio) + "</td><td>" + esc(l.uf) + "</td><td>" +
      esc(l.situacao) + "</td><td>" + (temPosicao(l)
        ? '<button type="button" data-linha="' + l.posicaoNaLista + '">Ver no mapa</button>'
        : '<span class="nota">Sem posição</span>') + "</td></tr>").join("") ||
      '<tr><td colspan="6">Nenhuma escola encontrada.</td></tr>';
    dlgAviso.textContent = filtradas.length > LIMITE_LINHAS_TABELA
      ? "Mostrando " + fmt(LIMITE_LINHAS_TABELA) + " de " + fmt(filtradas.length) + " escolas. Filtre a lista ou baixe o CSV para ver todas."
      : fmt(filtradas.length) + " escolas.";
  }

  document.getElementById("painel-cartoes").addEventListener("click", (ev) => {
    const botao = ev.target.closest("[data-categoria]");
    if (!botao) return;
    const categoria = CATEGORIAS[botao.dataset.categoria];
    document.getElementById("dlg-titulo").textContent = categoria.titulo + " · " + categoria.detalhe +
      " (" + (recorteAtual === "BR" ? "Brasil" : recorteAtual) + ")";
    linhasDlg = linhasDaCategoria(botao.dataset.categoria);
    linhasDlg.forEach((l, k) => { l.posicaoNaLista = k; });
    dlgFiltro.value = "";
    desenharTabela();
    dlg.showModal();
  });
  dlgFiltro.addEventListener("input", desenharTabela);
  document.getElementById("dlg-fechar").addEventListener("click", () => dlg.close());
  dlgCorpo.addEventListener("click", (ev) => {
    const botao = ev.target.closest("[data-linha]");
    if (!botao) return;
    const { conj, i } = linhasDlg[Number(botao.dataset.linha)];
    dlg.close();
    irParaEscola(conj, i);
  });

  // ------------------------------------------------------------------ clique e popup
  function htmlPopup(c, i) {
    const e = c.inep[i], j = e[6], r = j >= 0 ? c.cnefe[j] : null, s = c.sit[i];
    let h = '<div class="pop"><div class="censo" style="color:' + CORES[s] + '">Censo 2025: ' + esc(ROTULO_SITUACAO[s]) + "</div>";
    h += '<div class="muted">' + esc(ROTULO_NIVEL[e[4]]) + "</div>";
    if (e[7] !== null) h += '<div class="dist">Distância Catálogo × CNEFE: ' + fmt(e[7]) + " m</div>";
    h += "<h4>● Catálogo " + esc(e[0]) + '</h4><div class="lado"><b>' + esc(e[1]) + "</b><br>" +
         esc(e[8]) + '<br><span class="muted">' + ROTULO_CATALOGO[e[5]] + " · " +
         (e[2] === null ? "sem coordenada no Catálogo" : e[2] + ", " + e[3]) + "</span></div>";
    if (r) {
      h += "<h4>■ CNEFE " + esc(r[0]) + '</h4><div class="lado"><b>' + esc(r[1] || "(sem nome)") + "</b><br>" +
           esc(r[5]) + '<br><span class="muted">' + r[2] + ", " + r[3] + "</span></div>";
    }
    const lat = e[2] ?? (r && r[2]), lon = e[3] ?? (r && r[3]);
    if (lat !== null && lat !== undefined) {
      h += '<a href="https://www.google.com/maps/search/?api=1&query=' + lat + "," + lon +
           '" target="_blank" rel="noopener">Abrir no Google Maps ↗</a>';
    }
    return h + "</div>";
  }

  function htmlPopupCnefe(c, j) {
    const r = c.cnefe[j];
    return '<div class="pop"><div class="muted">Estabelecimento do CNEFE sem par no Catálogo</div><h4>■ CNEFE ' +
           esc(r[0]) + '</h4><div class="lado"><b>' + esc(r[1] || "(sem nome)") + "</b><br>" + esc(r[5]) +
           '<br><span class="muted">' + r[2] + ", " + r[3] + "</span></div></div>";
  }

  function posicaoDaEscola(c, i) {
    const e = c.inep[i];
    if (e[2] !== null) return [e[2], e[3]];
    return e[6] >= 0 ? [c.cnefe[e[6]][2], c.cnefe[e[6]][3]] : null;
  }

  function abrirEscola(c, i, latlng) {
    selecionado = { conj: c, i };
    L.popup({ maxWidth: 360 }).setLatLng(latlng || posicaoDaEscola(c, i)).setContent(htmlPopup(c, i)).openOn(mapa);
    camada.redesenhar();
  }

  function irParaEscola(c, i) {
    const pos = posicaoDaEscola(c, i);
    if (!pos) { L.popup({ maxWidth: 360 }).setLatLng(mapa.getCenter()).setContent(htmlPopup(c, i)).openOn(mapa); return; }
    mapa.setView(pos, 17);
    abrirEscola(c, i, pos);
  }

  mapa.on("click", (ev) => {
    const p = ev.containerPoint;
    let melhor = null, melhorD = 64;   // raio de 8 px
    for (const c of conjuntos) {
      for (const v of c.visiveis) {
        const d = (v[2] - p.x) ** 2 + (v[3] - p.y) ** 2;
        // circulos do Catalogo tem prioridade sobre quadrados do CNEFE no mesmo lugar
        if (d < melhorD || (d === melhorD && v[0] === "I")) { melhor = [c, v]; melhorD = d; }
      }
    }
    if (!melhor) { selecionado = null; camada.redesenhar(); return; }
    const [c, v] = melhor;
    if (v[0] === "I") abrirEscola(c, v[1], ev.latlng);
    else if (c.cnefe[v[1]][4] >= 0) abrirEscola(c, c.cnefe[v[1]][4], ev.latlng);
    else {
      selecionado = null;
      L.popup({ maxWidth: 360 }).setLatLng(ev.latlng).setContent(htmlPopupCnefe(c, v[1])).openOn(mapa);
      camada.redesenhar();
    }
  });
  mapa.on("popupclose", () => { selecionado = null; camada.redesenhar(); });

  // ------------------------------------------------------------------ busca
  const busca = document.getElementById("busca"), resultados = document.getElementById("resultados-busca");
  let temporizador = null;
  busca.addEventListener("input", () => {
    clearTimeout(temporizador);
    temporizador = setTimeout(() => {
      const termo = semAcento(busca.value.trim());
      resultados.innerHTML = "";
      if (termo.length < 3) return;
      const achados = [];
      for (const c of conjuntos) {
        for (let i = 0; i < c.inep.length && achados.length < 15; i++) {
          if (c.inep[i][0] === termo || semAcento(c.inep[i][1]).includes(termo)) achados.push({ c, i });
        }
        for (const linha of c.soNoCenso) {
          if (achados.length >= 15) break;
          if (linha[0] === termo || semAcento(linha[1]).includes(termo)) achados.push({ c, linha });
        }
      }
      resultados.innerHTML = achados.map((a, k) => {
        if (a.linha) {
          return '<li class="nota">' + esc(a.linha[1]) + " · " + esc(a.linha[2]) + " - " + a.c.uf + " · só no Censo 2025, sem posição</li>";
        }
        return '<li data-k="' + k + '"><span style="color:' + CORES[a.c.sit[a.i]] + '">●</span> ' + esc(a.c.inep[a.i][1]) +
               ' <span class="nota">' + esc(a.c.inep[a.i][9]) + " - " + a.c.uf + "</span></li>";
      }).join("") || '<li class="nota">Nada encontrado no recorte carregado.</li>';
      resultados.onclick = (ev) => {
        const li = ev.target.closest("li[data-k]");
        if (!li) return;
        const { c, i } = achados[Number(li.dataset.k)];
        irParaEscola(c, i);
      };
    }, 250);
  });

  // ------------------------------------------------------------------ inicio
  const selUF = document.getElementById("sel-uf");
  selUF.innerHTML = '<option value="BR">Brasil (27 UFs)</option>' + UFS.map((uf) => '<option value="' + uf + '">' + uf + "</option>").join("");
  lerJson("data/catalogo_censo_2025/index.json").then((idx) => {
    indice = idx;
    const inicial = (new URLSearchParams(location.search).get("uf") || "").toUpperCase();
    const valor = inicial === "BR" || UFS.includes(inicial) ? inicial : "SP";
    selUF.value = valor;
    selecionarRecorte(valor);
  }).catch((erro) => {
    statusCarga.textContent = "Não foi possível ler data/catalogo_censo_2025/index.json. Rode catalogo_censo_2025__comparar.py.";
    console.error(erro);
  });
  selUF.addEventListener("change", () => {
    const url = new URL(location.href);
    url.searchParams.set("uf", selUF.value);
    history.replaceState(null, "", url);
    selecionarRecorte(selUF.value);
  });
})();
