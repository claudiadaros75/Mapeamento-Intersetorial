#!/usr/bin/env python3
"""Baixa as coordenadas das escolas do Censo Escolar (INEP) distribuidas pelo geobr (Ipea).

O INEP coleta a localizacao das escolas no Censo Escolar desde 2018, mas
nao a publica nos microdados (ver docs/06-georeferenciamento-escolas.org).
Ela aparece no Catalogo de Escolas do INEP (painel do INEP Data, com
exportacao manual), e o pacote geobr, do Ipea, redistribui esse cadastro
ja pronto, um GeoPackage por ano, com a coordenada de cada escola e o
codigo INEP (code_school = CO_ENTIDADE dos microdados).

E a fonte "coordenada do INEP" do mapa de auditoria: entra so para as
escolas que ficaram sem correspondencia no CNEFE, e para medir a
distancia entre o ponto do CNEFE e o do INEP (ver
docs/08-mapeamento-intersetorial-nacional-diagnostico-norte.org).

Anos disponiveis (metadata do geobr 1.7.0): 2020 e 2023. Nao ha checksum
publicado, entao a unica conferencia de integridade e o tamanho.

Uso:
    .venv/bin/python scripts/commands/ipea_geobr_escolas__baixar_dados.py
    .venv/bin/python scripts/commands/ipea_geobr_escolas__baixar_dados.py 2020 2023
    .venv/bin/python ... --forcar
"""

import argparse
import importlib.util
from pathlib import Path

# Reaproveita o download com retomada e conferencia de tamanho do CNEFE.
_spec = importlib.util.spec_from_file_location(
    "ibge_cnefe__baixar_dados", Path(__file__).resolve().parent / "ibge_cnefe__baixar_dados.py"
)
_cnefe = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_cnefe)
baixar, mb, tamanho_remoto = _cnefe.baixar, _cnefe.mb, _cnefe.tamanho_remoto

BASE_URL = "https://www.ipea.gov.br/geobr/data_gpkg/schools"

DESTINO = Path(__file__).resolve().parent.parent.parent / "data" / "ipea_geobr_escolas"

ANOS = ["2020", "2023"]


def baixar_ano(ano: str, forcar: bool) -> None:
    """Garante data/ipea_geobr_escolas/schools_<ano>.gpkg, baixando-o se for preciso.

    Um arquivo ja presente e reaproveitado, a menos que o tamanho divirja do
    servidor - sinal de download truncado - ou que forcar seja verdadeiro.
    """
    url = "{}/{}/schools_{}.gpkg".format(BASE_URL, ano, ano)
    destino = DESTINO / "schools_{}.gpkg".format(ano)

    print("[{}] {}".format(ano, destino.name))

    if destino.exists() and not forcar:
        local = destino.stat().st_size
        remoto = tamanho_remoto(url)
        if remoto and local != remoto:
            print("    tamanho difere do servidor ({} vs {}), rebaixando".format(mb(local), mb(remoto)))
            destino.unlink()
        else:
            print("    ja baixado: {} ({})".format(destino, mb(local)))
            return

    print("    GET {}".format(url))
    baixar(url, destino)
    print("    OK: {} ({})".format(destino, mb(destino.stat().st_size)))


def principal() -> None:
    """Le a linha de comando e baixa os anos pedidos (padrao: o mais recente)."""
    analisador = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    analisador.add_argument(
        "anos",
        nargs="*",
        choices=ANOS + [[]],
        default=[ANOS[-1]],
        help="anos a baixar (padrao: {})".format(ANOS[-1]),
    )
    analisador.add_argument("--forcar", action="store_true", help="rebaixar mesmo que o arquivo ja exista")
    argumentos = analisador.parse_args()

    for ano in argumentos.anos:
        baixar_ano(ano, argumentos.forcar)


if __name__ == "__main__":
    principal()
