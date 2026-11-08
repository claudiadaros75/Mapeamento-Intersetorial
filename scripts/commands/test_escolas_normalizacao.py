"""Testes dos normalizadores (casos reais do Catalogo de Escolas e do CNEFE).

Rodar: python3 -m unittest scripts/commands/test_escolas_normalizacao.py
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import escolas_normalizacao as n  # noqa: E402


class TestEndereco(unittest.TestCase):
    def test_formato_completo(self):
        r = n.parse_endereco_inep("RUA PORTO CARREIRO, 1956 AEROPORTO. 79332-090 Corumbá - MS.")
        self.assertTrue(r["ok"])
        self.assertEqual(
            (r["logradouro"], r["numero"], r["bairro"], r["cep"], r["municipio"], r["uf"]),
            ("RUA PORTO CARREIRO", "1956", "AEROPORTO", "79332090", "Corumbá", "MS"),
        )

    def test_complemento_e_bairro(self):
        r = n.parse_endereco_inep("RESIDENCIAL SIDENCIAL VIDA VIVA, 6395 RUA DR JUVENAL. VALE DO GAVIAO. 64069-125 Teresina - PI.")
        self.assertEqual((r["numero"], r["complemento"], r["bairro"]), ("6395", "RUA DR JUVENAL", "VALE DO GAVIAO"))

    def test_sem_numero(self):
        r = n.parse_endereco_inep("AV JOAO PEDRO FERNANDES, 79150-000 Maracaju - MS.")
        self.assertTrue(r["ok"])
        self.assertEqual((r["logradouro"], r["numero"], r["bairro"], r["cep"]), ("AV JOAO PEDRO FERNANDES", "", "", "79150000"))

    def test_sn(self):
        r = n.parse_endereco_inep("RUA NOSSA SENHORA DA CANDELARIA, SN MARIA LEITE. 79310-050 Corumbá - MS.")
        self.assertEqual((r["numero"], r["bairro"]), ("", "MARIA LEITE"))

    def test_numero_zero(self):
        r = n.parse_endereco_inep("POV DE ABOBORAS, 0 39188-000 Couto de Magalhães de Minas - MG.")
        self.assertEqual((r["numero"], r["municipio"]), ("", "Couto de Magalhães de Minas"))

    def test_municipio_com_hifen(self):
        r = n.parse_endereco_inep("RUA A, 10 CENTRO. 68371-000 Pau-d'Arco - PA.")
        self.assertEqual((r["municipio"], r["uf"]), ("Pau-d'Arco", "PA"))


class TestLogradouro(unittest.TestCase):
    def test_inep_igual_cnefe(self):
        self.assertEqual(
            n.normalizar_logradouro("AV. PROF. JOSE DA SILVA"),
            n.logradouro_cnefe("AVENIDA", "PROFESSOR", "JOSE DA SILVA"),
        )

    def test_rua_abreviada(self):
        self.assertEqual(n.normalizar_logradouro("R NOVA"), n.logradouro_cnefe("RUA", "", "NOVA"))

    def test_rua_com_letra_nao_e_desfigurada(self):
        self.assertEqual(n.normalizar_logradouro("RUA D"), "D")

    def test_so_tipo_nao_esvazia(self):
        self.assertEqual(n.normalizar_logradouro("RODOVIA"), "RODOVIA")


class TestNumeroCep(unittest.TestCase):
    def test_numero(self):
        self.assertEqual([n.normalizar_numero(x) for x in ("0", "SN", "S/N", "0064", "12A", "")], ["", "", "", "64", "12", ""])

    def test_cep(self):
        self.assertEqual(n.normalizar_cep("7661410"), "07661410")
        self.assertEqual(n.normalizar_cep("79310-050"), "79310050")
        self.assertTrue(n.cep_generico("78350000"))
        self.assertFalse(n.cep_generico("78350010"))


class TestNomeEscola(unittest.TestCase):
    def test_exato(self):
        self.assertEqual(n.nome_escola_exato("E.E. Prof. João  Ávila"), "E E PROF JOAO AVILA")

    def test_nucleo_inep_vs_cnefe(self):
        self.assertEqual(
            n.nome_escola_nucleo("EE PROF ANTONIO FERREIRA DE SOUZA"),
            n.nome_escola_nucleo("ANTONIO FERREIRA DE SOUZA"),
        )

    def test_nucleo_emef(self):
        self.assertEqual(n.nome_escola_nucleo("EMEF DONA MARIA"), n.nome_escola_nucleo("ESCOLA MUNICIPAL DE ENSINO FUNDAMENTAL DONA MARIA"))

    def test_romanos_diferenciam(self):
        self.assertNotEqual(n.nome_escola_nucleo("EE DOM PEDRO I"), n.nome_escola_nucleo("EE DOM PEDRO II"))

    def test_nucleo_vazio_devolve_expandido(self):
        self.assertEqual(n.nome_escola_nucleo("ESCOLA MUNICIPAL"), "ESCOLA MUNICIPAL")


class TestNomeEscolaV2(unittest.TestCase):
    """Casos reais vistos no diagnostico de perdas (2026-11-07)."""

    def test_letras_soltas(self):
        self.assertEqual(n.nome_escola_nucleo("E M E I WALDENIZE BARBOSA"), "WALDENIZE BARBOSA")

    def test_codigo_numerico_e_sigla(self):
        self.assertEqual(n.nome_escola_nucleo("0918611 CM MARIO LOMBARDI"), n.nome_escola_nucleo("CRECHE MUNICIPAL MARIO LOMBARDI"))

    def test_sigla_desconhecida(self):
        self.assertEqual(n.nome_escola_nucleo("EEIEF DE TUNCAS"), "TUNCAS")

    def test_conjuncao_e_nao_some(self):
        self.assertIn("SANTOS", n.nome_escola_nucleo("ESCOLA SANTOS E SILVA"))

    def test_logradouro_df(self):
        self.assertEqual(n.normalizar_logradouro("QUADRA SGAS 912"), n.logradouro_cnefe("EDF", "", "SGAS 912"))


class TestNomeGenerico(unittest.TestCase):
    def test_genericos(self):
        for nome in ("ESCOLA", "ESCOLA MUNICIPAL", "CRECHE", "EMEF", "E M E I", "ESCOLA DE ENSINO FUNDAMENTAL"):
            self.assertTrue(n.nome_escola_generico(nome), nome)

    def test_especificos(self):
        for nome in ("IGREJA ADVENTISTA DO SETIMO DIA", "EMEF DONA MARIA", "APAE", "COLEGIO CETES"):
            self.assertFalse(n.nome_escola_generico(nome), nome)


class TestDistancia(unittest.TestCase):
    def test_um_grau_de_latitude(self):
        self.assertAlmostEqual(n.haversine_m(0, 0, 1, 0), 111_195, delta=5)

    def test_faixas(self):
        self.assertEqual([n.faixa_distancia(m) for m in (10, 100, 500, 2000, 9000)],
                         ["a_<50m", "b_50-200m", "c_200m-1km", "d_1-5km", "e_>5km"])


if __name__ == "__main__":
    unittest.main()
