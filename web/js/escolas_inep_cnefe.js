/* =============================================================================
   Mapa de escolas INEP x CNEFE
   -----------------------------------------------------------------------------
   Dados: web/data/escolas/<UF>.json e index.json, gerados por
   scripts/commands/escolas__gerar_dados_mapa.py. Formato das linhas:
     inep : [codigo, nome, lat, lon, status, restricao, idx_cnefe, dist_m, endereco, municipio]
     cnefe: [cod_unico, nome, lat, lon, idx_inep, endereco]

   Por que uma camada de canvas propria: o Brasil inteiro passa de 400 mil
   pontos. Marcadores DOM do Leaflet (e ate circleMarker em canvas) ficam
   lentos nessa escala; aqui cada ponto e projetado uma unica vez no zoom 0 e,
   a cada redesenho, so escalado e transladado - alguns milissegundos.
   ============================================================================= */

(function () {
  "use strict";

  const UFS = ["AC", "AL", "AM", "AP", "BA", "CE", "DF", "ES", "GO", "MA", "MG", "MS", "MT", "PA", "PB",
               "PE", "PI", "PR", "RJ", "RN", "RO", "RR", "RS", "SC", "SE", "SP", "TO"];
  const CORES = { N1: "#1b7837", N2: "#5aae61", N3: "#2166ac", N4: "#8e44ad", AMB: "#e08214", SEM: "#d73027",
                  CNEFE: "#4d4d4d", DESTAQUE: "#ffd400" };
  const ROTULO_STATUS = {
    N1: "N1 · CEP + número + logradouro", N2: "N2 · CEP + logradouro", N3: "N3 · nome exato",
    N4: "N4 · nome ajustado", AMB: "Ambígua (empate entre candidatos)", SEM: "Sem par no CNEFE",
  };
  const FAIXAS = [
    { id: "a", rotulo: "< 50 m", max: 50 }, { id: "b", rotulo: "50 – 200 m", max: 200 },
    { id: "c", rotulo: "200 m – 1 km", max: 1000 }, { id: "d", rotulo: "1 – 5 km", max: 5000 },
    { id: "e", rotulo: "> 5 km", max: Infinity }, { id: "x", rotulo: "Sem distância (sem par ou sem coordenada)", max: null },
  ];
  const ZOOM_LINHAS = 11;

  // ------------------------------------------------------------------ estado
  const filtros = {
    status: { N1: true, N2: true, N3: true, N4: true, AMB: true, SEM: true },
    cnefe: { par: true, sem: true },
    faixa: { a: true, b: true, c: true, d: true, e: true, x: true },
    restr: { F: true, P: true, E: true },
    linhas: true,
  };
  let conjuntos = [];          // dados das UFs carregadas, com coordenadas projetadas
  let indice = null;           // index.json
  let selecionado = null;      // { conj, i } escola INEP destacada
  const cache = {};

  // ------------------------------------------------------------------ mapa
  const mapa = L.map("mapa", { zoomControl: true, preferCanvas: true }).setView([-14.5, -52], 4);
  const BASES = {
    carto: L.tileLayer("https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png",
      { maxZoom: 20, attribution: "© OpenStreetMap · © CARTO" }),
    osm: L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png",
      { maxZoom: 19, attribution: "© OpenStreetMap" }),
    esri: L.tileLayer("https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
      { maxZoom: 19, attribution: "Esri World Imagery" }),
  };
  // CARTO passou a exigir chave de API (tiles com marca "API KEY REQUIRED" em 2026-11) - OSM e o padrao.
  let baseAtual = BASES.osm.addTo(mapa);
  document.getElementById("sel-base").addEventListener("change", (ev) => {
    mapa.removeLayer(baseAtual);
    baseAtual = BASES[ev.target.value].addTo(mapa);
    baseAtual.bringToBack();
  });

  fetch("data/BR_uf_2024_minima.geojson").then((r) => r.json()).then((geo) => {
    L.geoJSON(geo, { interactive: false, style: { color: "#334155", weight: 1, fill: false, opacity: 0.6 } }).addTo(mapa);
  }).catch(() => {});

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

  /** A escola INEP passa nos filtros? (status, situacao, faixa de distancia) */
  function inepVisivel(linha) {
    return filtros.status[linha[4]] && filtros.restr[linha[5]] && filtros.faixa[faixaDe(linha[7])];
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
          const e = c.inep[i], j = e[6];
          if (j < 0 || isNaN(c.ix[i]) || isNaN(c.cx[j]) || !inepVisivel(e)) continue;
          const x1 = telaX(c.ix[i]), y1 = telaY(c.iy[i]), x2 = telaX(c.cx[j]), y2 = telaY(c.cy[j]);
          if ((x1 < -margem && x2 < -margem) || (x1 > W && x2 > W) || (y1 < -margem && y2 < -margem) || (y1 > H && y2 > H)) continue;
          ctx.strokeStyle = CORES[e[4]];
          ctx.beginPath(); ctx.moveTo(x1, y1); ctx.lineTo(x2, y2); ctx.stroke();
        }
      }
      // --- CNEFE (quadrados): pareado cheio, sem par vazado
      const lado = r * 1.6;
      ctx.lineWidth = 1;
      for (let j = 0; j < c.cnefe.length; j++) {
        if (isNaN(c.cx[j])) continue;
        const pareado = c.cnefe[j][4] >= 0;
        if (pareado ? !filtros.cnefe.par : !filtros.cnefe.sem) continue;
        if (pareado && !inepVisivel(c.inep[c.cnefe[j][4]])) continue;
        const x = telaX(c.cx[j]), y = telaY(c.cy[j]);
        if (x < -margem || y < -margem || x > W || y > H) continue;
        if (pareado) { ctx.fillStyle = CORES.CNEFE; ctx.fillRect(x - lado / 2, y - lado / 2, lado, lado); }
        else { ctx.strokeStyle = CORES.CNEFE; ctx.strokeRect(x - lado / 2, y - lado / 2, lado, lado); }
        c.visiveis.push(["C", j, x, y]);
      }
      // --- INEP (circulos) por cima; sem coordenada INEP mas pareada -> vazado na posicao do CNEFE
      for (let i = 0; i < c.inep.length; i++) {
        const e = c.inep[i];
        if (!inepVisivel(e)) continue;
        let px = c.ix[i], py = c.iy[i], vazado = false;
        if (isNaN(px)) {
          if (e[6] < 0 || isNaN(c.cx[e[6]])) continue;
          px = c.cx[e[6]]; py = c.cy[e[6]]; vazado = true;
        }
        const x = telaX(px), y = telaY(py);
        if (x < -margem || y < -margem || x > W || y > H) continue;
        ctx.beginPath(); ctx.arc(x, y, r, 0, 2 * Math.PI);
        if (vazado) { ctx.strokeStyle = CORES[e[4]]; ctx.lineWidth = 1.5; ctx.stroke(); }
        else { ctx.fillStyle = CORES[e[4]]; ctx.fill(); }
        c.visiveis.push(["I", i, x, y]);
      }
    }
    // --- destaque do par selecionado
    if (selecionado) {
      const { conj: c, i } = selecionado, e = c.inep[i], j = e[6];
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

  async function carregarUF(uf) {
    if (!cache[uf]) {
      const resp = await fetch("data/escolas/" + uf + ".json");
      if (!resp.ok) throw new Error(uf + ": HTTP " + resp.status);
      const dados = await resp.json();
      const [ix, iy] = projetar(dados.inep);
      const [cx, cy] = projetar(dados.cnefe);
      cache[uf] = { uf, inep: dados.inep, cnefe: dados.cnefe, ix, iy, cx, cy, visiveis: [] };
    }
    return cache[uf];
  }

  const statusCarga = document.getElementById("status-carga");

  async function selecionarRecorte(valor) {
    selecionado = null;
    mapa.closePopup();
    const lista = valor === "BR" ? UFS.filter((u) => ufsDisponiveis.has(u)) : [valor];
    conjuntos = [];
    let n = 0;
    for (const uf of lista) {
      statusCarga.textContent = "Carregando " + uf + " (" + (++n) + "/" + lista.length + ")…";
      try {
        conjuntos.push(await carregarUF(uf));
      } catch (erro) {
        console.error(erro);
      }
      camada.redesenhar();
    }
    atualizarContagens();
    atualizarResumo(valor);
    enquadrar(valor);
    const totalI = conjuntos.reduce((s, c) => s + c.inep.length, 0);
    const totalC = conjuntos.reduce((s, c) => s + c.cnefe.length, 0);
    statusCarga.textContent = totalI.toLocaleString("pt-BR") + " escolas INEP · " +
                              totalC.toLocaleString("pt-BR") + " estabelecimentos CNEFE";
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
    return '<label class="chk"><input type="checkbox" ' + attrs + ' checked>' + html +
           '<span class="qtd" id="' + qtdId + '"></span></label>';
  }

  document.getElementById("lista-status").innerHTML = Object.keys(ROTULO_STATUS).map((s) =>
    linhaFiltro('<span class="sw" style="background:' + CORES[s] + '"></span>' + ROTULO_STATUS[s],
                'data-status="' + s + '"', "q-" + s)).join("");
  document.getElementById("lista-faixas").innerHTML = FAIXAS.map((f) =>
    linhaFiltro(f.rotulo, 'data-faixa="' + f.id + '"', "q-f" + f.id)).join("");

  document.querySelector(".esc-sidebar").addEventListener("change", (ev) => {
    const el = ev.target, d = el.dataset;
    if (d.status) filtros.status[d.status] = el.checked;
    else if (d.cnefe) filtros.cnefe[d.cnefe] = el.checked;
    else if (d.faixa) filtros.faixa[d.faixa] = el.checked;
    else if (d.restr) filtros.restr[d.restr] = el.checked;
    else if (el.id === "chk-linhas") filtros.linhas = el.checked;
    else return;
    camada.redesenhar();
  });

  function fmt(n) { return Number(n).toLocaleString("pt-BR"); }

  function atualizarContagens() {
    const q = {}, set = (k) => { q[k] = (q[k] || 0) + 1; };
    for (const c of conjuntos) {
      for (const e of c.inep) { set(e[4]); set("f" + faixaDe(e[7])); }
      for (const r of c.cnefe) set(r[4] >= 0 ? "cnefe-par" : "cnefe-sem");
    }
    for (const s of Object.keys(ROTULO_STATUS)) document.getElementById("q-" + s).textContent = fmt(q[s] || 0);
    for (const f of FAIXAS) document.getElementById("q-f" + f.id).textContent = fmt(q["f" + f.id] || 0);
    document.getElementById("q-cnefe-par").textContent = fmt(q["cnefe-par"] || 0);
    document.getElementById("q-cnefe-sem").textContent = fmt(q["cnefe-sem"] || 0);
  }

  function atualizarResumo(valor) {
    const painel = document.getElementById("painel-resumo");
    if (!indice) { painel.textContent = "—"; return; }
    const r = indice.resumo.find((l) => l.UF === valor);
    const dist = indice.distancias.filter((l) => l.UF === valor);
    if (!r) { painel.textContent = "Sem resumo para " + valor; return; }
    const pct = (v) => (100 * v / (r.ESCOLAS_INEP || 1)).toFixed(1).replace(".", ",") + "%";
    let html = '<table class="stats"><tr><th></th><th>Escolas</th><th>%</th></tr>';
    for (const nv of ["N1", "N2", "N3", "N4"]) html += "<tr><td>" + nv + "</td><td>" + fmt(r[nv]) + "</td><td>" + pct(r[nv]) + "</td></tr>";
    html += "<tr><td><b>Pareadas</b></td><td><b>" + fmt(r.PAREADAS) + "</b></td><td><b>" + pct(r.PAREADAS) + "</b></td></tr>";
    html += "<tr><td>Ambíguas</td><td>" + fmt(r.AMBIGUAS) + "</td><td>" + pct(r.AMBIGUAS) + "</td></tr>";
    html += "<tr><td>Sem par</td><td>" + fmt(r.INEP_SEM_PAR) + "</td><td>" + pct(r.INEP_SEM_PAR) + "</td></tr>";
    html += "<tr><td>CNEFE sem par</td><td>" + fmt(r.CNEFE_SEM_PAR) + "</td><td></td></tr></table>";
    if (dist.length) {
      html += '<table class="stats" style="margin-top:.6rem"><tr><th>Distância</th><th>mediana</th><th>p90</th><th>&lt;50 m</th></tr>';
      for (const d of dist) {
        html += "<tr><td>" + d.NIVEL + "</td><td>" + fmt(d.MEDIANA_M) + " m</td><td>" + fmt(d.P90_M) + " m</td><td>" +
                String(d["PCT_<50m"]).replace(".", ",") + "%</td></tr>";
      }
      html += "</table>";
    }
    painel.innerHTML = html;
  }

  // ------------------------------------------------------------------ clique e popup
  function esc(t) {
    return String(t ?? "").replace(/[&<>"]/g, (ch) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[ch]));
  }

  function htmlPopup(c, i) {
    const e = c.inep[i], j = e[6], r = j >= 0 ? c.cnefe[j] : null;
    const restr = { F: "em funcionamento", P: "paralisada", E: "exclusiva/especial" }[e[5]];
    let h = '<div class="pop"><div class="muted">' + esc(ROTULO_STATUS[e[4]]) + "</div>";
    if (e[7] !== null) h += '<div class="dist">Distância entre as coordenadas: ' + fmt(e[7]) + " m</div>";
    h += '<h4 style="color:' + CORES[e[4]] + '">● INEP ' + esc(e[0]) + "</h4><div class=\"lado\"><b>" + esc(e[1]) + "</b><br>" +
         esc(e[8]) + '<br><span class="muted">' + restr + " · " +
         (e[2] === null ? "sem coordenada no INEP" : e[2] + ", " + e[3]) + "</span></div>";
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
    return '<div class="pop"><div class="muted">Estabelecimento do CNEFE sem par no INEP</div><h4>■ CNEFE ' +
           esc(r[0]) + '</h4><div class="lado"><b>' + esc(r[1] || "(sem nome)") + "</b><br>" + esc(r[5]) +
           '<br><span class="muted">' + r[2] + ", " + r[3] + "</span></div></div>";
  }

  function abrirEscola(c, i, latlng) {
    selecionado = { conj: c, i };
    const e = c.inep[i], j = e[6];
    const pos = latlng || (e[2] !== null ? [e[2], e[3]] : [c.cnefe[j][2], c.cnefe[j][3]]);
    L.popup({ maxWidth: 360 }).setLatLng(pos).setContent(htmlPopup(c, i)).openOn(mapa);
    camada.redesenhar();
  }

  mapa.on("click", (ev) => {
    const p = ev.containerPoint;
    let melhor = null, melhorD = 64;   // raio de 8 px
    for (const c of conjuntos) {
      for (const v of c.visiveis) {
        const d = (v[2] - p.x) ** 2 + (v[3] - p.y) ** 2;
        // circulos INEP tem prioridade sobre quadrados CNEFE no mesmo lugar
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
      const termo = busca.value.trim().toUpperCase().normalize("NFD").replace(/[̀-ͯ]/g, "");
      resultados.innerHTML = "";
      if (termo.length < 3) return;
      const achados = [];
      for (const c of conjuntos) {
        for (let i = 0; i < c.inep.length && achados.length < 15; i++) {
          const e = c.inep[i];
          if (e[0] === termo || e[1].normalize("NFD").replace(/[̀-ͯ]/g, "").includes(termo)) achados.push([c, i]);
        }
      }
      resultados.innerHTML = achados.map(([c, i], k) =>
        '<li data-k="' + k + '"><span style="color:' + CORES[c.inep[i][4]] + '">●</span> ' + esc(c.inep[i][1]) +
        ' <span class="nota">' + esc(c.inep[i][9]) + " - " + c.uf + "</span></li>").join("") ||
        '<li class="nota">Nada encontrado no recorte carregado.</li>';
      resultados.onclick = (ev) => {
        const li = ev.target.closest("li[data-k]");
        if (!li) return;
        const [c, i] = achados[Number(li.dataset.k)];
        const e = c.inep[i];
        const pos = e[2] !== null ? [e[2], e[3]] : (e[6] >= 0 ? [c.cnefe[e[6]][2], c.cnefe[e[6]][3]] : null);
        if (!pos) { L.popup().setLatLng(mapa.getCenter()).setContent(htmlPopup(c, i)).openOn(mapa); return; }
        mapa.setView(pos, 17);
        abrirEscola(c, i, pos);
      };
    }, 250);
  });

  // ------------------------------------------------------------------ inicio
  const selUF = document.getElementById("sel-uf");
  let ufsDisponiveis = new Set();
  fetch("data/escolas/index.json").then((r) => r.json()).then((idx) => {
    indice = idx;
    ufsDisponiveis = new Set(idx.resumo.map((l) => l.UF).filter((u) => u !== "BR"));
    const opcoes = ['<option value="BR">Brasil (todas as UFs disponíveis)</option>'];
    for (const uf of UFS) if (ufsDisponiveis.has(uf)) opcoes.push('<option value="' + uf + '">' + uf + "</option>");
    selUF.innerHTML = opcoes.join("");
    const inicial = new URLSearchParams(location.search).get("uf");
    const valor = inicial && (inicial === "BR" || ufsDisponiveis.has(inicial.toUpperCase())) ? inicial.toUpperCase()
                  : (ufsDisponiveis.has("SP") ? "SP" : [...ufsDisponiveis][0]);
    selUF.value = valor;
    selecionarRecorte(valor);
  }).catch((erro) => {
    statusCarga.textContent = "Não foi possível ler data/escolas/index.json - rode escolas__gerar_dados_mapa.py";
    console.error(erro);
  });
  selUF.addEventListener("change", () => {
    const url = new URL(location.href);
    url.searchParams.set("uf", selUF.value);
    history.replaceState(null, "", url);
    selecionarRecorte(selUF.value);
  });
})();
