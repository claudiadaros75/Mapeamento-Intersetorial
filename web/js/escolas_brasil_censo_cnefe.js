/* =============================================================================
   Mapa nacional: Censo Escolar x CNEFE
   -----------------------------------------------------------------------------
   Pontos: data/escolas_brasil/pontos.json, gerado por
   scripts/commands/escolas__gerar_dados_mapa_nacional.py.
   Detalhes do ponto clicado: data/escolas/<UF>.json, baixado sob demanda.
     inep : [codigo, nome, lat, lon, status, restricao, idx_cnefe, dist_m, endereco, municipio]
     cnefe: [cod_unico, nome, lat, lon, idx_inep, endereco]
   ============================================================================= */

(function () {
  "use strict";

  const CAMADAS = {
    cnefe: { cor: "#d55e00", forma: "quadrado" },
    censo_par: { cor: "#56b4e9", forma: "vazado" },
    censo: { cor: "#0072b2", forma: "circulo" },
  };
  const ORDEM = ["cnefe", "censo_par", "censo"]; // a ultima fica por cima
  const SITUACAO = { F: "Em funcionamento", P: "Paralisada", E: "Atendimento exclusivo" };
  const ROTULO_PAR = { N1: "CEP + número + logradouro", N2: "CEP + logradouro", N3: "nome exato", N4: "nome ajustado" };
  const ZOOM_FORMAS = 9; // abaixo disso, retangulos: sao mais rapidos e as formas nao se distinguem
  const FATIAS = 16;

  const visivel = { cnefe: true, censo_par: true, censo: true };
  const pontos = {}; // camada -> { n, x: Float64Array, y: Float64Array, i: Int32Array, uf: Uint8Array }
  let listaUfs = [];
  const cacheUf = {};

  // ------------------------------------------------------------------ mapa
  const mapa = L.map("mapa", { preferCanvas: true }).setView([-14.5, -52], 4);
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
  }).catch(() => {});

  // ------------------------------------------------------------------ canvas
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

  function desenhar(ctx, map, tamanho, topoEsq) {
    const z = map.getZoom();
    const escala = Math.pow(2, z);
    const origem = map.getPixelOrigin();
    const ox = origem.x + topoEsq.x, oy = origem.y + topoEsq.y;
    const r = raioPorZoom(z);
    const W = tamanho.x + 10, H = tamanho.y + 10;

    // Com o mapa afastado, os pontos se sobrepoem: desenhar uma camada inteira por
    // cima esconderia a outra. Por isso cada camada e dividida em fatias alternadas.
    const formas = z >= ZOOM_FORMAS;
    const fatias = formas ? 1 : FATIAS;
    ctx.lineWidth = 1.5;
    ctx.globalAlpha = formas ? 0.9 : 0.6;
    for (let fatia = 0; fatia < fatias; fatia++) {
      for (const nome of ORDEM) {
        const p = pontos[nome];
        if (!p || !visivel[nome]) continue;
        const estilo = CAMADAS[nome];
        ctx.fillStyle = estilo.cor;
        ctx.strokeStyle = estilo.cor;
        for (let k = fatia; k < p.n; k += fatias) {
          const px = p.x[k] * escala - ox, py = p.y[k] * escala - oy;
          if (px < -10 || py < -10 || px > W || py > H) continue;
          if (!formas || estilo.forma === "quadrado") {
            ctx.fillRect(px - r, py - r, 2 * r, 2 * r);
          } else {
            ctx.beginPath();
            ctx.arc(px, py, r, 0, 2 * Math.PI);
            if (estilo.forma === "vazado") ctx.stroke(); else ctx.fill();
          }
        }
      }
    }
    ctx.globalAlpha = 1;
  }

  // ------------------------------------------------------------------ dados
  function fmt(n) { return Number(n).toLocaleString("pt-BR"); }

  /** Projeta no zoom 0 com a mesma formula do Leaflet (EPSG:3857, mundo de 256 px). */
  function montarCamada(nome, ufs) {
    let n = 0;
    for (const uf of listaUfs) n += ufs[uf][nome].length / 3;
    const p = { n, x: new Float64Array(n), y: new Float64Array(n), i: new Int32Array(n), uf: new Uint8Array(n) };
    let k = 0;
    listaUfs.forEach((uf, idxUf) => {
      const v = ufs[uf][nome];
      for (let j = 0; j < v.length; j += 3, k++) {
        const lat = v[j + 1] * Math.PI / 180;
        p.i[k] = v[j];
        p.uf[k] = idxUf;
        p.x[k] = (v[j + 2] + 180) / 360 * 256;
        p.y[k] = (0.5 - Math.log(Math.tan(lat) + 1 / Math.cos(lat)) / (2 * Math.PI)) * 256;
      }
    });
    return p;
  }

  const statusCarga = document.getElementById("status-carga");
  fetch("data/escolas_brasil/pontos.json")
    .then((r) => { if (!r.ok) throw new Error("HTTP " + r.status); return r.json(); })
    .then((dados) => {
      listaUfs = Object.keys(dados.ufs);
      for (const nome of ORDEM) {
        pontos[nome] = montarCamada(nome, dados.ufs);
        document.getElementById("qtd-" + nome).textContent = fmt(pontos[nome].n);
      }
      const t = dados.totais;
      document.getElementById("qtd-total").textContent = fmt(t.escolas_censo);
      document.getElementById("qtd-sem").textContent = fmt(t.sem_coordenada);
      statusCarga.textContent = fmt(t.censo + t.censo_par) + " escolas do Censo · " + fmt(t.cnefe) + " do CNEFE";
      camada.redesenhar();
    })
    .catch((erro) => {
      console.error(erro);
      statusCarga.textContent = "Não foi possível carregar os dados do mapa.";
    });

  for (const nome of ORDEM) {
    document.getElementById("chk-" + nome).addEventListener("change", (ev) => {
      visivel[nome] = ev.target.checked;
      mapa.closePopup();
      camada.redesenhar();
    });
  }

  // ------------------------------------------------------------------ clique
  function pontoMaisProximo(latlng) {
    const z = mapa.getZoom();
    const alvo = mapa.project(latlng, z);
    const escala = Math.pow(2, z);
    const limite = Math.max(raioPorZoom(z) + 4, 8);
    let melhor = null, menor = limite * limite;
    for (const nome of ORDEM) {
      const p = pontos[nome];
      if (!p || !visivel[nome]) continue;
      for (let k = 0; k < p.n; k++) {
        const dx = p.x[k] * escala - alvo.x, dy = p.y[k] * escala - alvo.y;
        const d2 = dx * dx + dy * dy;
        // <= favorece a camada desenhada por cima quando os pontos coincidem
        if (d2 <= menor) { menor = d2; melhor = { nome, k }; }
      }
    }
    return melhor;
  }

  function carregarUf(uf) {
    if (!cacheUf[uf]) {
      cacheUf[uf] = fetch("data/escolas/" + uf + ".json").then((r) => {
        if (!r.ok) throw new Error("HTTP " + r.status);
        return r.json();
      }).catch((erro) => { delete cacheUf[uf]; throw erro; });
    }
    return cacheUf[uf];
  }

  function esc(texto) {
    const d = document.createElement("div");
    d.textContent = texto === null || texto === undefined ? "" : String(texto);
    return d.innerHTML;
  }

  function linkMapa(lat, lon) {
    return '<a href="https://www.google.com/maps?q=' + encodeURIComponent(lat + "," + lon) +
           '" target="_blank" rel="noopener">Abrir no Google Maps ↗</a>';
  }

  function htmlCenso(linha, dados, nome) {
    const par = linha[6] >= 0 ? dados.cnefe[linha[6]] : null;
    const lat = linha[2] !== null ? linha[2] : par[2], lon = linha[2] !== null ? linha[3] : par[3];
    let h = '<div class="pop"><span class="pop-base" style="color:' + CAMADAS[nome].cor + '">Censo Escolar</span>' +
            "<h4>" + esc(linha[1]) + "</h4>" +
            "<div>Código INEP: " + esc(linha[0]) + " · " + esc(SITUACAO[linha[5]]) + "</div>" +
            "<div>" + esc(linha[9]) + "</div><div class=\"muted\">" + esc(linha[8]) + "</div>";
    if (nome === "censo_par") {
      h += '<div class="aviso">Sem coordenada do INEP: posição emprestada do par no CNEFE.</div>';
    }
    if (par) {
      h += "<div>Par no CNEFE (" + esc(ROTULO_PAR[linha[4]]) + "): " + esc(par[1]) + "</div>";
      if (linha[7] !== null) h += "<div>Distância entre as coordenadas: <strong>" + fmt(linha[7]) + " m</strong></div>";
    } else {
      h += '<div class="muted">Sem par definido no CNEFE.</div>';
    }
    return h + "<div>" + linkMapa(lat, lon) + "</div></div>";
  }

  function htmlCnefe(linha, dados) {
    const par = linha[4] >= 0 ? dados.inep[linha[4]] : null;
    let h = '<div class="pop"><span class="pop-base" style="color:' + CAMADAS.cnefe.cor + '">CNEFE 2022</span>' +
            "<h4>" + esc(linha[1] || "(sem identificação)") + "</h4>" +
            "<div class=\"muted\">" + esc(linha[5]) + "</div>" +
            "<div>Código do endereço: " + esc(linha[0]) + "</div>";
    if (par) {
      h += "<div>Par no Censo Escolar: " + esc(par[1]) + " (" + esc(par[0]) + ")</div>";
      if (par[7] !== null) h += "<div>Distância entre as coordenadas: <strong>" + fmt(par[7]) + " m</strong></div>";
    } else {
      h += '<div class="muted">Sem par definido no Censo Escolar.</div>';
    }
    return h + "<div>" + linkMapa(linha[2], linha[3]) + "</div></div>";
  }

  mapa.on("click", (ev) => {
    const achado = pontoMaisProximo(ev.latlng);
    if (!achado) return;
    const p = pontos[achado.nome];
    const uf = listaUfs[p.uf[achado.k]];
    const i = p.i[achado.k];
    const popup = L.popup({ maxWidth: 340 }).setLatLng(ev.latlng)
      .setContent("Carregando os dados de " + esc(uf) + "…").openOn(mapa);
    carregarUf(uf).then((dados) => {
      popup.setContent(achado.nome === "cnefe" ? htmlCnefe(dados.cnefe[i], dados) : htmlCenso(dados.inep[i], dados, achado.nome));
    }).catch((erro) => {
      console.error(erro);
      popup.setContent("Não foi possível carregar os dados de " + esc(uf) + ".");
    });
  });
})();
