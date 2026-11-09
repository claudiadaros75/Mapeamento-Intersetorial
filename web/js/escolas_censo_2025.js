/* =============================================================================
   Mapa do Censo Escolar 2025
   -----------------------------------------------------------------------------
   Dados: data/censo_2025/escolas.json, gerado por
   scripts/commands/censo_escolar_2025__georreferenciar.py. Linhas:
     [codigo, nome, uf, municipio, situacao, rede, localizacao, origem, lat, lon]
     origem: I = catalogo do INEP | N1..N4 = par no CNEFE | S = sem localizacao
   ============================================================================= */

(function () {
  "use strict";

  const C = { codigo: 0, nome: 1, uf: 2, municipio: 3, situacao: 4, rede: 5, localizacao: 6, origem: 7, lat: 8, lon: 9 };
  const CAMADAS = {
    catalogo: { cor: "#0072b2", forma: "circulo" },
    endereco: { cor: "#009e73", forma: "losango" },
    nome: { cor: "#d55e00", forma: "quadrado" },
  };
  const ORDEM = ["nome", "endereco", "catalogo"]; // a ultima fica por cima
  const CAMADA_DA_ORIGEM = { I: "catalogo", N1: "endereco", N2: "endereco", N3: "nome", N4: "nome" };
  const ORIGEM = {
    I: "Coordenada do Catálogo de Escolas do INEP",
    N1: "CNEFE, por CEP + número + logradouro",
    N2: "CNEFE, por CEP + logradouro",
    N3: "CNEFE, por nome exato no município",
    N4: "CNEFE, por nome ajustado no município",
  };
  const SITUACAO = { 1: "Em atividade", 2: "Paralisada", 3: "Extinta" };
  const REDE = { 1: "Federal", 2: "Estadual", 3: "Municipal", 4: "Privada" };
  const LOCAL = { 1: "Urbana", 2: "Rural" };
  const ZOOM_FORMAS = 9;
  const FATIAS = 16;
  const POR_PAGINA = 50;

  const visivel = { catalogo: true, endereco: true, nome: true };
  const situacaoVisivel = { 1: true, 2: true, 3: true };
  let linhas = [];
  let semLocal = [];
  const pontos = {}; // camada -> { n, x, y, i (linha), s (situacao) }

  function fmt(n) { return Number(n).toLocaleString("pt-BR"); }
  const el = (id) => document.getElementById(id);

  // ------------------------------------------------------------------ mapa
  const mapa = L.map("mapa", { preferCanvas: true }).setView([-14.5, -52], 4);
  const BASES = {
    osm: L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png",
      { maxZoom: 19, attribution: "© OpenStreetMap" }),
    esri: L.tileLayer("https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
      { maxZoom: 19, attribution: "Esri World Imagery" }),
  };
  let baseAtual = BASES.osm.addTo(mapa);
  el("sel-base").addEventListener("change", (ev) => {
    mapa.removeLayer(baseAtual);
    baseAtual = BASES[ev.target.value].addTo(mapa);
    baseAtual.bringToBack();
  });

  fetch("data/BR_uf_2024_minima.geojson").then((r) => r.json()).then((geo) => {
    L.geoJSON(geo, { interactive: false, style: { color: "#334155", weight: 1, fill: false, opacity: 0.6 } }).addTo(mapa);
  }).catch(() => {});

  // Cada ponto e projetado uma vez no zoom 0; a cada redesenho so escala e translada.
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
    return z < 6 ? 0.8 : z < 9 ? 1.6 : z < 12 ? 3 : z < 15 ? 4.5 : 6;
  }

  function marcar(ctx, forma, px, py, r) {
    if (forma === "circulo") {
      ctx.beginPath();
      ctx.arc(px, py, r, 0, 2 * Math.PI);
      ctx.fill();
    } else if (forma === "losango") {
      const d = r * 1.3;
      ctx.beginPath();
      ctx.moveTo(px, py - d);
      ctx.lineTo(px + d, py);
      ctx.lineTo(px, py + d);
      ctx.lineTo(px - d, py);
      ctx.closePath();
      ctx.fill();
    } else {
      ctx.fillRect(px - r, py - r, 2 * r, 2 * r);
    }
  }

  function desenhar(ctx, map, tamanho, topoEsq) {
    const z = map.getZoom();
    const escala = Math.pow(2, z);
    const origem = map.getPixelOrigin();
    const ox = origem.x + topoEsq.x, oy = origem.y + topoEsq.y;
    const r = raioPorZoom(z);
    const W = tamanho.x + 10, H = tamanho.y + 10;
    // Com o mapa afastado, fatias alternadas evitam que uma camada esconda as outras.
    const formas = z >= ZOOM_FORMAS;
    const fatias = formas ? 1 : FATIAS;
    ctx.globalAlpha = formas ? 0.9 : 0.6;
    for (let fatia = 0; fatia < fatias; fatia++) {
      for (const nome of ORDEM) {
        const p = pontos[nome];
        if (!p || !visivel[nome]) continue;
        const estilo = CAMADAS[nome];
        ctx.fillStyle = estilo.cor;
        for (let k = fatia; k < p.n; k += fatias) {
          if (!situacaoVisivel[p.s[k]]) continue;
          const px = p.x[k] * escala - ox, py = p.y[k] * escala - oy;
          if (px < -10 || py < -10 || px > W || py > H) continue;
          if (formas) marcar(ctx, estilo.forma, px, py, r);
          else ctx.fillRect(px - r, py - r, 2 * r, 2 * r);
        }
      }
    }
    ctx.globalAlpha = 1;
  }

  // ------------------------------------------------------------------ dados
  /** Projeta no zoom 0 com a mesma formula do Leaflet (EPSG:3857, mundo de 256 px). */
  function montarCamadas() {
    const listas = { catalogo: [], endereco: [], nome: [] };
    linhas.forEach((l, i) => {
      if (l[C.lat] !== null) listas[CAMADA_DA_ORIGEM[l[C.origem]]].push(i);
    });
    for (const nome of ORDEM) {
      const lista = listas[nome], n = lista.length;
      const p = { n, x: new Float64Array(n), y: new Float64Array(n), i: new Int32Array(n), s: new Uint8Array(n) };
      lista.forEach((i, k) => {
        const l = linhas[i];
        const lat = l[C.lat] * Math.PI / 180;
        p.i[k] = i;
        p.s[k] = l[C.situacao];
        p.x[k] = (l[C.lon] + 180) / 360 * 256;
        p.y[k] = (0.5 - Math.log(Math.tan(lat) + 1 / Math.cos(lat)) / (2 * Math.PI)) * 256;
      });
      pontos[nome] = p;
    }
  }

  function atualizarContagens() {
    for (const nome of ORDEM) {
      const p = pontos[nome];
      let n = 0;
      for (let k = 0; k < p.n; k++) if (situacaoVisivel[p.s[k]]) n++;
      el("qtd-" + nome).textContent = fmt(n);
    }
  }

  // ------------------------------------------------------------------ clique
  function pontoMaisProximo(latlng) {
    const z = mapa.getZoom();
    const alvo = mapa.project(latlng, z);
    const escala = Math.pow(2, z);
    const limite = Math.max(raioPorZoom(z) + 4, 8);
    let melhor = -1, menor = limite * limite;
    for (const nome of ORDEM) {
      const p = pontos[nome];
      if (!p || !visivel[nome]) continue;
      for (let k = 0; k < p.n; k++) {
        if (!situacaoVisivel[p.s[k]]) continue;
        const dx = p.x[k] * escala - alvo.x, dy = p.y[k] * escala - alvo.y;
        const d2 = dx * dx + dy * dy;
        // <= favorece a camada desenhada por cima quando os pontos coincidem
        if (d2 <= menor) { menor = d2; melhor = p.i[k]; }
      }
    }
    return melhor;
  }

  function esc(texto) {
    const d = document.createElement("div");
    d.textContent = texto === null || texto === undefined ? "" : String(texto);
    return d.innerHTML;
  }

  function htmlEscola(l) {
    const camadaDe = CAMADA_DA_ORIGEM[l[C.origem]];
    let h = '<div class="pop"><h4>' + esc(l[C.nome]) + "</h4>" +
            "<div>Código INEP: " + esc(l[C.codigo]) + "</div>" +
            "<div>" + esc(l[C.municipio]) + " - " + esc(l[C.uf]) + "</div>" +
            "<div>" + esc(SITUACAO[l[C.situacao]]) + " · " + esc(REDE[l[C.rede]]) + " · " + esc(LOCAL[l[C.localizacao]]) + "</div>" +
            '<div class="pop-origem" style="border-color:' + CAMADAS[camadaDe].cor + '">' + esc(ORIGEM[l[C.origem]]) + "</div>";
    if (l[C.origem] === "N3" || l[C.origem] === "N4") {
      h += '<div class="muted">Localizada só pela semelhança do nome. Confira antes de usar.</div>';
    }
    return h + '<div><a href="https://www.google.com/maps?q=' + encodeURIComponent(l[C.lat] + "," + l[C.lon]) +
           '" target="_blank" rel="noopener">Abrir no Google Maps ↗</a></div></div>';
  }

  mapa.on("click", (ev) => {
    const i = pontoMaisProximo(ev.latlng);
    if (i < 0) return;
    L.popup({ maxWidth: 340 }).setLatLng([linhas[i][C.lat], linhas[i][C.lon]]).setContent(htmlEscola(linhas[i])).openOn(mapa);
  });

  // ------------------------------------------------------------------ controles
  for (const nome of ORDEM) {
    el("chk-" + nome).addEventListener("change", (ev) => {
      visivel[nome] = ev.target.checked;
      mapa.closePopup();
      camada.redesenhar();
    });
  }
  for (const s of [1, 2, 3]) {
    el("chk-sit-" + s).addEventListener("change", (ev) => {
      situacaoVisivel[s] = ev.target.checked;
      mapa.closePopup();
      atualizarContagens();
      camada.redesenhar();
    });
  }

  // ------------------------------------------------------------------ tabela
  const dialogo = el("dlg-tabela");
  let pagina = 0;

  function semAcento(t) {
    return String(t).normalize("NFD").replace(/[̀-ͯ]/g, "").toUpperCase();
  }

  function filtrarTabela() {
    const uf = el("flt-uf").value, sit = el("flt-sit").value;
    const busca = semAcento(el("flt-busca").value.trim());
    return semLocal.filter((l) => (!uf || l[C.uf] === uf) && (!sit || String(l[C.situacao]) === sit) &&
      (!busca || l[C.codigo].includes(busca) || semAcento(l[C.nome]).includes(busca) || semAcento(l[C.municipio]).includes(busca)));
  }

  function desenharTabela() {
    const filtradas = filtrarTabela();
    const paginas = Math.max(1, Math.ceil(filtradas.length / POR_PAGINA));
    pagina = Math.min(pagina, paginas - 1);
    const corpo = el("tabela-corpo");
    corpo.textContent = "";
    for (const l of filtradas.slice(pagina * POR_PAGINA, (pagina + 1) * POR_PAGINA)) {
      const tr = document.createElement("tr");
      for (const valor of [l[C.codigo], l[C.nome], l[C.uf], l[C.municipio], REDE[l[C.rede]], SITUACAO[l[C.situacao]]]) {
        const td = document.createElement("td");
        td.textContent = valor;
        tr.appendChild(td);
      }
      corpo.appendChild(tr);
    }
    el("tabela-resumo").textContent = fmt(filtradas.length) + " escolas · página " + fmt(pagina + 1) + " de " + fmt(paginas);
    el("btn-ant").disabled = pagina === 0;
    el("btn-prox").disabled = pagina >= paginas - 1;
  }

  function reiniciarTabela() { pagina = 0; desenharTabela(); }

  el("btn-tabela").addEventListener("click", () => { desenharTabela(); dialogo.showModal(); });
  el("btn-fechar").addEventListener("click", () => dialogo.close());
  el("btn-ant").addEventListener("click", () => { pagina--; desenharTabela(); });
  el("btn-prox").addEventListener("click", () => { pagina++; desenharTabela(); });
  el("flt-uf").addEventListener("change", reiniciarTabela);
  el("flt-sit").addEventListener("change", reiniciarTabela);
  el("flt-busca").addEventListener("input", reiniciarTabela);

  // ------------------------------------------------------------------ carga
  const statusCarga = el("status-carga");
  fetch("data/censo_2025/escolas.json")
    .then((r) => { if (!r.ok) throw new Error("HTTP " + r.status); return r.json(); })
    .then((dados) => {
      linhas = dados.linhas;
      semLocal = linhas.filter((l) => l[C.lat] === null);
      montarCamadas();
      atualizarContagens();
      const noMapa = linhas.length - semLocal.length;
      el("qtd-total").textContent = fmt(linhas.length);
      el("qtd-mapa").textContent = fmt(noMapa);
      el("qtd-sem").textContent = fmt(semLocal.length);
      statusCarga.textContent = fmt(noMapa) + " de " + fmt(linhas.length) + " escolas no mapa";
      const ufs = [...new Set(semLocal.map((l) => l[C.uf]))].sort();
      for (const uf of ufs) el("flt-uf").add(new Option(uf, uf));
      el("btn-tabela").disabled = false;
      camada.redesenhar();
    })
    .catch((erro) => {
      console.error(erro);
      statusCarga.textContent = "Não foi possível carregar os dados do mapa.";
    });
})();
