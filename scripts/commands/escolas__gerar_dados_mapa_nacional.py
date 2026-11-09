#!/usr/bin/env python3
"""Gera o arquivo leve do mapa nacional Censo Escolar x CNEFE.

Reaproveita web/data/escolas/<UF>.json (gerados por
escolas__gerar_dados_mapa.py) e grava so as coordenadas, para o mapa abrir o
Brasil inteiro sem baixar os 69 MB dos arquivos por UF. Os detalhes de um ponto
continuam nos arquivos por UF e so sao baixados quando ele e clicado; por isso
cada ponto guarda a posicao "i" da sua linha no arquivo da UF.

Saida: web/data/escolas_brasil/pontos.json
    {"totais": {...},
     "ufs": {"RO": {"censo":     [i, lat, lon, i, lat, lon, ...],
                    "censo_par": [...],
                    "cnefe":     [...]}, ...}}
        censo     = escola com coordenada publicada pelo INEP
        censo_par = escola sem coordenada do INEP, no ponto do seu par no CNEFE
        cnefe     = estabelecimento de ensino do CNEFE

Uso:
    .venv/bin/python scripts/commands/escolas__gerar_dados_mapa_nacional.py
"""

import json
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent.parent
DIR_UFS = RAIZ / "web" / "data" / "escolas"
SAIDA = RAIZ / "web" / "data" / "escolas_brasil" / "pontos.json"
CASAS = 5  # cerca de 1 m, abaixo do erro de 5,84 m do GNSS do CNEFE em situacao ideal


def main():
    arquivos = sorted(p for p in DIR_UFS.glob("*.json") if len(p.stem) == 2 and p.stem.isupper())
    if len(arquivos) != 27:
        raise SystemExit("esperava 27 arquivos de UF em {}, achei {}".format(DIR_UFS, len(arquivos)))

    ufs = {}
    totais = {"escolas_censo": 0, "censo": 0, "censo_par": 0, "sem_coordenada": 0, "cnefe": 0}
    for arquivo in arquivos:
        dados = json.loads(arquivo.read_text(encoding="utf-8"))
        censo, censo_par, cnefe = [], [], []
        for i, linha in enumerate(dados["inep"]):
            totais["escolas_censo"] += 1
            idx_par = linha[6]
            if linha[2] is not None:
                censo += [i, round(linha[2], CASAS), round(linha[3], CASAS)]
                totais["censo"] += 1
            elif idx_par >= 0:
                par = dados["cnefe"][idx_par]
                censo_par += [i, round(par[2], CASAS), round(par[3], CASAS)]
                totais["censo_par"] += 1
            else:
                totais["sem_coordenada"] += 1
        for i, linha in enumerate(dados["cnefe"]):
            cnefe += [i, round(linha[2], CASAS), round(linha[3], CASAS)]
            totais["cnefe"] += 1
        ufs[arquivo.stem] = {"censo": censo, "censo_par": censo_par, "cnefe": cnefe}

    SAIDA.parent.mkdir(parents=True, exist_ok=True)
    SAIDA.write_text(json.dumps({"totais": totais, "ufs": ufs}, separators=(",", ":")), encoding="utf-8")
    print(totais)
    print("{}: {:.1f} MB".format(SAIDA.relative_to(RAIZ), SAIDA.stat().st_size / 1e6))


if __name__ == "__main__":
    main()
