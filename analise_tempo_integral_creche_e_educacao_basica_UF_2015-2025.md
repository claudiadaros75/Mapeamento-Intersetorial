# Decomposição regional da variação de matrículas em tempo integral (2015–2025)
## Recortes: (A) Creche + tempo integral · (B) Educação básica + tempo integral

**Fonte:** INEP – Censo Escolar, painel *Matrículas – Estatísticas gerais* (InepData / Power BI), página 2 de 24
**Filtros comuns:** período 2015–2025 · Rede = Todos · Categoria = **Total** (ambos os sexos) · botão *Tempo integral*
**Data da coleta:** 16/10/2026

> Esta versão substitui a análise anterior, que usava apenas matrículas do sexo feminino. Agora o filtro de sexo foi retirado (categoria "Total").

---

## 1. Pergunta de pesquisa

Os gráficos de evolução do painel sugerem crescimento sem grandes rupturas no total nacional. A pergunta é: **quais estados e regiões mais contribuíram para as variações, para mais ou para menos**, em dois recortes:

- **(A) Educação infantil – creche, em tempo integral**
- **(B) Educação básica (todas as etapas), em tempo integral**

---

## 2. Processo de coleta e cálculo

O painel do INEP não permite exportar os dados por UF. Por isso os valores foram extraídos diretamente da página, com automação no navegador.

1. **Configuração dos filtros:** Categoria = *Total*, Modalidade = *Educação infantil – creche* (recorte A) ou *Educação básica* (recorte B), botão *Tempo integral* ativo.
2. **Filtro "Região, UF, município":** é uma segmentação hierárquica de seleção única (Brasil → Região → UF → Município), com lista virtualizada: só os itens visíveis ficam na página.
3. **Leitura dos valores:** foram lidos os rótulos de dados (elementos `<text>` do SVG) do gráfico *Evolução da matrícula*. Isso dá os números exatos exibidos, sem estimativa visual.
4. **Automação (JavaScript no console da página):** um script percorreu Brasil, as 5 regiões e as 27 UFs. Para cada item, ele:
   - abria o menu do filtro e rolava a lista até o item;
   - expandia as regiões e recolhia as UFs que se abriam até o nível de município;
   - selecionava o item e esperava o título do gráfico mudar para o nome correspondente e os 11 valores carregarem;
   - guardava a série.
5. **Validação:** em cada ano, a soma das 27 UFs foi comparada ao total Brasil, e a soma das 5 regiões também. **A diferença foi zero em todos os anos, nos dois recortes.**
6. **Cálculos** (Python):
   - Variação absoluta: Δᵢ = Xᵢ,fim − Xᵢ,início
   - **Contribuição para a variação nacional:** Cᵢ = Δᵢ / Δ_Brasil
   - Crescimento próprio: gᵢ = Xᵢ,fim / Xᵢ,início − 1
   - Participação: wᵢ,t = Xᵢ,t / X_Brasil,t
   - Decomposição ano a ano: as 3 UFs com maior |ΔXᵢ,t| em cada transição

> **Identidade:** Cᵢ = wᵢ,início · gᵢ / g_Brasil. A contribuição depende do **tamanho inicial** e do **ritmo de crescimento** de cada estado.

---

# PARTE A — Creche + tempo integral

### A.1 Taxa de variação anual do Brasil

| 15→16 | 16→17 | 17→18 | 18→19 | 19→20 | 20→21 | 21→22 | 22→23 | 23→24 | 24→25 |
|---|---|---|---|---|---|---|---|---|---|
| +5,7% | +5,1% | +3,1% | +4,3% | −0,7% | −4,0% | +10,8% | +6,5% | +4,3% | +2,2% |

A série é **suave**. A única interrupção é a da pandemia (2020–2021), seguida de recuperação forte em 2022.

### A.2 Contribuições 2015 → 2025

| Região | 2015 | 2025 | Δ | % do Δ Brasil | Participação 2015 → 2025 |
|---|---|---|---|---|---|
| Sudeste | 1.023.451 | 1.349.795 | +326.344 | 42,4% | 57,6% → 53,0% |
| Nordeste | 182.461 | 440.124 | +257.663 | 33,5% | 10,3% → 17,3% |
| Sul | 405.439 | 501.586 | +96.147 | 12,5% | 22,8% → 19,7% |
| Centro-Oeste | 128.516 | 188.803 | +60.287 | 7,8% | 7,2% → 7,4% |
| Norte | 36.480 | 66.229 | +29.749 | 3,9% | 2,1% → 2,6% |

| UF | Δ 2015–2025 | % do Δ Brasil | Crescimento próprio | Part. 2015 | Part. 2025 |
|---|---|---|---|---|---|
| SP | +214.540 | 27,9% | +30,2% | 39,9% | 36,3% |
| BA | +76.756 | 10,0% | +104,3% | 4,1% | 5,9% |
| MG | +73.486 | 9,5% | +45,4% | 9,1% | 9,2% |
| CE | +45.765 | 5,9% | +227,0% | 1,1% | 2,6% |
| RS | +37.371 | 4,9% | +27,3% | 7,7% | 6,8% |
| PR | +36.162 | 4,7% | +24,8% | 8,2% | 7,1% |
| RJ | +35.403 | 4,6% | +26,6% | 7,5% | 6,6% |
| GO | +31.792 | 4,1% | +67,2% | 2,7% | 3,1% |
| PE | +31.563 | 4,1% | +118,0% | 1,5% | 2,3% |
| AL | +28.408 | 3,7% | +192,3% | 0,8% | 1,7% |
| PI | +25.597 | 3,3% | +2529,3% | 0,1% | 1,0% |
| SC | +22.614 | 2,9% | +18,4% | 6,9% | 5,7% |
| PB | +22.505 | 2,9% | +103,2% | 1,2% | 1,7% |
| DF | +20.208 | 2,6% | +182,2% | 0,6% | 1,2% |
| MA | +17.760 | 2,3% | +150,5% | 0,7% | 1,2% |
| PA | +17.247 | 2,2% | +150,4% | 0,6% | 1,1% |
| SE | +9.924 | 1,3% | +179,4% | 0,3% | 0,6% |
| MT | +4.819 | 0,6% | +15,4% | 1,8% | 1,4% |
| AM | +3.991 | 0,5% | +82,1% | 0,3% | 0,3% |
| MS | +3.468 | 0,5% | +8,9% | 2,2% | 1,7% |
| TO | +3.176 | 0,4% | +25,8% | 0,7% | 0,6% |
| RR | +2.952 | 0,4% | +373,2% | 0,0% | 0,1% |
| ES | +2.915 | 0,4% | +15,2% | 1,1% | 0,9% |
| AC | +1.675 | 0,2% | +57,5% | 0,2% | 0,2% |
| RO | +745 | 0,1% | +19,1% | 0,2% | 0,2% |
| AP | −37 | −0,0% | −14,9% | 0,0% | 0,0% |
| RN | −615 | −0,1% | −8,7% | 0,4% | 0,3% |

| Transição | Δ Brasil | 3 UFs com maior variação absoluta |
|---|---|---|
| 2015→2016 | +100.966 | SP +46.651 · PR +18.184 · MG +10.331 |
| 2016→2017 | +95.805 | SP +45.644 · BA +10.623 · RJ +9.669 |
| 2017→2018 | +61.472 | SP +26.230 · MG +6.993 · RS +6.070 |
| 2018→2019 | +87.060 | SP +43.299 · BA +7.526 · PR +6.609 |
| 2019→2020 | −14.927 | RS −7.038 · SP +6.922 · PR −4.633 |
| 2020→2021 | −83.274 | SP −36.027 · MG −15.829 · SC −14.868 |
| 2021→2022 | +219.417 | SP +59.723 · MG +23.007 · RS +22.131 |
| 2022→2023 | +145.469 | SP +31.891 · MG +15.062 · BA +14.100 |
| 2023→2024 | +102.499 | MG +13.713 · SP +13.099 · RJ +10.275 |
| 2024→2025 | +55.703 | SP −22.892 · BA +11.233 · MA +8.436 |

### A.3 Interpretação (creche)

1. **Mesma estrutura do recorte feminino:** o total é cerca de 2,08 vezes a série feminina, e as contribuições relativas praticamente não mudam. Isso indica que a expansão da creche integral não difere por sexo.
2. **O Sudeste lidera em volume (42%), mas perde participação** (57,6% → 53,0%). Sozinho, **SP** responde por 28% do crescimento, mas cresce só 30% e perde 3,6 p.p. de participação.
3. **O Nordeste é o motor relativo:** passa de 10,3% para 17,3% do total. BA, CE, PE, AL, PB, MA e SE mais que dobram. O **Piauí** salta de 1.012 para 26.609 (×26), concentrado entre 2021 e 2023. Vale verificar se é expansão real ou mudança de registro.
4. **Pandemia:** a queda de 2020–2021 (−83 mil) se concentra em SP, MG e SC (e RS/PR em 2020). Em 2022 vem o maior salto da série (+219 mil).
5. **2025:** SP recua 22.892, mas o Brasil ainda cresce +55.703, puxado pelo Nordeste (BA, MA).
6. **Queda no período:** apenas RN (−8,7%) e AP (−14,9%). MS, MT e ES ficam quase estagnados.

---

# PARTE B — Educação básica + tempo integral

### B.1 Taxa de variação anual do Brasil

| 15→16 | 16→17 | 17→18 | 18→19 | 19→20 | 20→21 | 21→22 | 22→23 | 23→24 | 24→25 |
|---|---|---|---|---|---|---|---|---|---|
| **−26,1%** | **+27,7%** | **−15,1%** | +2,8% | −7,3% | +9,2% | **+20,1%** | +11,6% | +7,9% | +9,6% |

Diferente da creche, a educação básica em tempo integral tem **forte instabilidade entre 2015 e 2018**, um zigue-zague de ±2 milhões de matrículas. Depois disso, cresce de forma consistente a partir de 2021.

> ⚠️ **Atenção à escolha do ano-base.** 2015 é um ano alto (7,70 milhões), seguido de uma queda brusca em 2016 (5,69 milhões). Comparar 2015 → 2025 **subestima** o crescimento recente e faz estados com 2015 inflado parecerem em declínio. Por isso, a análise é apresentada para **2015 → 2025** (comparável com a creche) e para **2019 → 2025** (base pré-pandemia, após o período instável).
>
> **Hipótese para investigar, não verificada nesta análise:** as oscilações de 2015 a 2018 coincidem com a transição entre programas federais de ampliação de jornada no ensino fundamental (Mais Educação → Novo Mais Educação). Em programas de atividades complementares, a contagem de alunos em tempo integral depende da adesão e do financiamento de cada ano. Isso explicaria variações grandes em estados do Nordeste e do Norte, onde a adesão era alta.

### B.2 Contribuições 2015 → 2025

| Região | 2015 | 2025 | Δ | % do Δ Brasil | Participação 2015 → 2025 |
|---|---|---|---|---|---|
| Sudeste | 2.623.588 | 4.120.106 | +1.496.518 | 61,2% | 34,1% → 40,6% |
| Nordeste | 2.756.776 | 3.596.489 | +839.713 | 34,3% | 35,8% → 35,5% |
| Sul | 1.073.303 | 1.198.372 | +125.069 | 5,1% | 13,9% → 11,8% |
| Centro-Oeste | 459.198 | 553.939 | +94.741 | 3,9% | 6,0% → 5,5% |
| Norte | 783.544 | 674.356 | −109.188 | −4,5% | 10,2% → 6,6% |

| UF | Δ 2015–2025 | % do Δ Brasil | Crescimento próprio | Part. 2015 | Part. 2025 |
|---|---|---|---|---|---|
| SP | +1.141.247 | 46,6% | +75,2% | 19,7% | 26,2% |
| CE | +419.262 | 17,1% | +96,6% | 5,6% | 8,4% |
| RJ | +170.609 | 7,0% | +38,7% | 5,7% | 6,0% |
| PI | +170.067 | 7,0% | +95,6% | 2,3% | 3,4% |
| MG | +131.251 | 5,4% | +22,9% | 7,4% | 6,9% |
| PR | +96.259 | 3,9% | +24,9% | 5,0% | 4,8% |
| MA | +87.414 | 3,6% | +20,0% | 5,7% | 5,2% |
| GO | +73.831 | 3,0% | +38,7% | 2,5% | 2,6% |
| AL | +73.806 | 3,0% | +59,2% | 1,6% | 2,0% |
| BA | +63.836 | 2,6% | +8,7% | 9,6% | 7,9% |
| ES | +53.411 | 2,2% | +57,6% | 1,2% | 1,4% |
| SE | +45.618 | 1,9% | +69,9% | 0,8% | 1,1% |
| PB | +42.537 | 1,7% | +20,8% | 2,7% | 2,4% |
| SC | +29.738 | 1,2% | +11,3% | 3,4% | 2,9% |
| MS | +27.625 | 1,1% | +33,0% | 1,1% | 1,1% |
| DF | +18.145 | 0,7% | +31,6% | 0,7% | 0,7% |
| RR | +7.226 | 0,3% | +112,9% | 0,1% | 0,1% |
| TO | +4.039 | 0,2% | +3,2% | 1,6% | 1,3% |
| RS | −928 | −0,0% | −0,2% | 5,5% | 4,2% |
| PA | −7.040 | −0,3% | −2,1% | 4,3% | 3,2% |
| AC | −7.342 | −0,3% | −17,5% | 0,5% | 0,3% |
| AP | −15.661 | −0,6% | −44,4% | 0,5% | 0,2% |
| PE | −21.008 | −0,9% | −4,8% | 5,7% | 4,1% |
| MT | −24.860 | −1,0% | −19,6% | 1,7% | 1,0% |
| AM | −27.493 | −1,1% | −17,0% | 2,1% | 1,3% |
| RN | −41.819 | −1,7% | −30,4% | 1,8% | 0,9% |
| RO | −62.917 | −2,6% | −73,6% | 1,1% | 0,2% |

| Transição | Δ Brasil | 3 UFs com maior variação absoluta |
|---|---|---|
| 2015→2016 | −2.011.159 | BA −276.559 · MA −268.209 · PA −218.473 |
| 2016→2017 | +1.572.765 | CE +254.806 · BA +169.256 · PE +163.906 |
| 2017→2018 | −1.099.371 | BA −181.164 · PE −134.056 · CE −121.152 |
| 2018→2019 | +169.557 | CE +155.956 · SP +89.701 · MG −77.878 |
| 2019→2020 | −463.422 | MA −134.435 · SP +124.101 · BA −103.437 |
| 2020→2021 | +539.523 | SP +194.359 · MA +120.361 · CE +71.874 |
| 2021→2022 | +1.289.231 | SP +412.723 · MA +132.106 · MG +117.910 |
| 2022→2023 | +890.084 | SP +191.910 · BA +136.417 · CE +126.576 |
| 2023→2024 | +674.665 | BA +86.834 · PA +80.682 · SP +78.833 |
| 2024→2025 | +884.980 | BA +178.161 · MA +107.773 · CE +75.070 |

### B.3 Contribuições 2019 → 2025 (base mais estável)

| Região | 2019 | 2025 | Δ | % do Δ Brasil | Participação 2019 → 2025 |
|---|---|---|---|---|---|
| Sudeste | 2.579.662 | 4.120.106 | +1.540.444 | 40,4% | 40,8% → 40,6% |
| Nordeste | 2.097.617 | 3.596.489 | +1.498.872 | 39,3% | 33,1% → 35,5% |
| Norte | 359.021 | 674.356 | +315.335 | 8,3% | 5,7% → 6,6% |
| Sul | 907.709 | 1.198.372 | +290.663 | 7,6% | 14,3% → 11,8% |
| Centro-Oeste | 384.192 | 553.939 | +169.747 | 4,4% | 6,1% → 5,5% |

| UF | Δ 2019–2025 | % do Δ Brasil | Crescimento próprio | Part. 2019 | Part. 2025 |
|---|---|---|---|---|---|
| SP | +1.047.177 | 27,4% | +65,0% | 25,5% | 26,2% |
| BA | +407.893 | 10,7% | +104,3% | 6,2% | 7,9% |
| CE | +332.710 | 8,7% | +63,9% | 8,2% | 8,4% |
| MG | +255.682 | 6,7% | +57,0% | 7,1% | 6,9% |
| MA | +199.805 | 5,2% | +61,4% | 5,1% | 5,2% |
| PI | +189.607 | 5,0% | +119,7% | 2,5% | 3,4% |
| PA | +178.294 | 4,7% | +125,2% | 2,3% | 3,2% |
| RJ | +151.762 | 4,0% | +33,0% | 7,3% | 6,0% |
| PR | +139.890 | 3,7% | +40,8% | 5,4% | 4,8% |
| RS | +102.016 | 2,7% | +31,9% | 5,1% | 4,2% |
| PE | +98.058 | 2,6% | +30,6% | 5,1% | 4,1% |
| GO | +90.225 | 2,4% | +51,7% | 2,8% | 2,6% |
| PB | +88.961 | 2,3% | +56,2% | 2,5% | 2,4% |
| AL | +88.816 | 2,3% | +80,9% | 1,7% | 2,0% |
| ES | +85.823 | 2,2% | +142,5% | 1,0% | 1,4% |
| SE | +66.586 | 1,7% | +150,3% | 0,7% | 1,1% |
| TO | +53.844 | 1,4% | +71,5% | 1,2% | 1,3% |
| SC | +48.757 | 1,3% | +19,9% | 3,9% | 2,9% |
| AM | +47.940 | 1,3% | +55,6% | 1,4% | 1,3% |
| MS | +35.550 | 0,9% | +46,9% | 1,2% | 1,1% |
| RN | +26.436 | 0,7% | +38,0% | 1,1% | 0,9% |
| MT | +23.572 | 0,6% | +30,0% | 1,2% | 1,0% |
| DF | +20.400 | 0,5% | +37,0% | 0,9% | 0,7% |
| AC | +15.987 | 0,4% | +86,2% | 0,3% | 0,3% |
| AP | +9.829 | 0,3% | +100,5% | 0,2% | 0,2% |
| RR | +6.147 | 0,2% | +82,2% | 0,1% | 0,1% |
| RO | +3.294 | 0,1% | +17,1% | 0,3% | 0,2% |

### B.4 Interpretação (educação básica)

1. **De 2015 a 2025, São Paulo responde por quase metade do crescimento (46,6%)**, com +1,14 milhão de matrículas (+75%). A participação de SP sobe de 19,7% para 26,2%. **Aqui o padrão se inverte em relação à creche:** na creche SP perde participação; na educação básica, ganha. A expansão paulista se concentra entre 2019 e 2023 (de 1,61 para 2,53 milhões). Uma hipótese a verificar é a ampliação do Programa Ensino Integral (PEI) na rede estadual.
2. **O Ceará é o segundo maior contribuinte (17%)**, quase dobrando (+97%), com tendência de alta desde 2018, apesar de um recuo em 2020. Também se destacam PI (+96%), RJ e AL.
3. **Contribuições negativas em 2015→2025:** RO (−74%), RN (−30%), AM (−17%), MT (−20%), AP (−44%), AC, PE, PA e RS. **A região Norte termina abaixo de 2015** (−109 mil). Porém, com base em 2019, **todas as regiões crescem**, e o Norte cresce acima da média. Boa parte das "quedas" é efeito da base de 2015 inflada.
4. **Com base em 2019, Sudeste (40%) e Nordeste (39%) dividem o crescimento quase igualmente.** O Nordeste ganha participação (33% → 35,5%) e o Sul perde (14,3% → 11,8%).
5. **2024 → 2025 (+885 mil):** o crescimento recente é puxado pelo Nordeste (BA +178 mil, MA +108 mil, CE +75 mil), e não mais por SP. Esse período coincide com o Programa Escola em Tempo Integral (Lei 14.640/2023).
6. **O Sul é o caso de estagnação:** RS fica praticamente igual a 2015 e SC cresce 11%. A participação da região cai de 13,9% para 11,8%.

---

## 3. Comparação entre os recortes

| Aspecto | Creche + TI | Educação básica + TI |
|---|---|---|
| Δ Brasil 2015–25 | +770 mil (+43%) | +2,45 milhões (+32%); de 2019 a 2025: +3,8 milhões (+60%) |
| Trajetória | Suave; queda só na pandemia | Instável até 2018; forte alta a partir de 2021 |
| Maior contribuinte | SP (28%), **perdendo** participação | SP (47%), **ganhando** participação |
| Motor relativo | Nordeste (BA, CE, PI, AL) | CE, PI e, desde 2023, BA e MA |
| Estados em queda | RN, AP | RO, RN, AM, MT, AP, AC, PE, PA, RS (com base 2015) |
| Sensibilidade ao ano-base | Baixa | **Alta** |

---

## 4. Limitações

- Os valores do Censo cobrem a população, não uma amostra. As diferenças são descritivas e não exigem inferência amostral; testes de hipótese exigem cuidado na interpretação.
- A análise trata **contagens**, não **proporções**. Um estado pode aumentar suas matrículas em tempo integral simplesmente porque o total de matrículas cresceu. O próximo passo natural é coletar a série "Total" por UF e analisar a **participação do tempo integral** em cada estado.
- As explicações de política pública (Mais Educação, PEI-SP, Lei 14.640/2023) são **hipóteses** a verificar com documentação e microdados, não conclusões desta análise.
- A decomposição por município (≈5.570) não é viável pelo painel. Recomenda-se usar os **microdados do Censo Escolar**.

---

## 5. Questões para uso em aula

1. Na educação básica, comparar 2015 → 2025 e 2019 → 2025 leva a conclusões diferentes sobre a região Norte. Explique por quê e discuta critérios para escolher o ano-base de uma comparação.
2. A série de educação básica em tempo integral oscila ±25% entre 2015 e 2018, e a de creche não. Que tipo de mudança (de oferta real, de definição ou de registro) produz esse padrão? Como você testaria isso com os microdados?
3. Na creche, SP perde participação; na educação básica, ganha. Construa uma explicação coerente para as duas tendências ao mesmo tempo, considerando qual rede responde por cada etapa.
4. Mostre que Cᵢ = wᵢ,início · gᵢ / g_Brasil. Use os números de SP e do CE na educação básica (2015–2025) para verificar a identidade.
5. RO perdeu 74% das matrículas em tempo integral entre 2015 e 2025 (de 85 mil para 23 mil), com a queda concentrada em 2016–2018. Que verificações você faria antes de afirmar que "Rondônia abandonou o tempo integral"?
6. A validação "soma das UFs = total Brasil" deu diferença zero. Por que essa checagem é indispensável ao extrair dados de painéis? Que outras verificações de consistência seriam úteis?
7. Proponha um teste para avaliar se o crescimento do Nordeste a partir de 2023 está associado à Lei 14.640/2023. Que grupo de comparação você usaria em um desenho de diferença em diferenças?
8. Contagens absolutas ou proporção de tempo integral sobre o total: qual métrica é mais adequada para comparar estados de tamanhos muito diferentes? Por quê?

---

## Anexo A — Série completa: creche + tempo integral

| UF | 2015 | 2016 | 2017 | 2018 | 2019 | 2020 | 2021 | 2022 | 2023 | 2024 | 2025 |
|---|---|---|---|---|---|---|---|---|---|---|---|
| **Brasil** | 1.776.347 | 1.877.313 | 1.973.118 | 2.034.590 | 2.121.650 | 2.106.723 | 2.023.449 | 2.242.866 | 2.388.335 | 2.490.834 | 2.546.537 |
| **Centro-Oeste** | **128.516** | **135.531** | **143.735** | **147.447** | **153.527** | **148.649** | **141.853** | **156.926** | **162.846** | **175.885** | **188.803** |
| DF | 11.094 | 12.496 | 13.614 | 15.875 | 17.144 | 18.895 | 21.030 | 23.135 | 24.515 | 29.398 | 31.302 |
| GO | 47.278 | 51.286 | 56.604 | 58.455 | 62.623 | 59.916 | 58.612 | 65.132 | 67.933 | 72.845 | 79.070 |
| MT | 31.210 | 32.677 | 32.381 | 31.498 | 31.211 | 28.960 | 26.594 | 29.611 | 30.240 | 32.128 | 36.029 |
| MS | 38.934 | 39.072 | 41.136 | 41.619 | 42.549 | 40.878 | 35.617 | 39.048 | 40.158 | 41.514 | 42.402 |
| **Nordeste** | **182.461** | **195.800** | **216.452** | **231.864** | **248.723** | **247.307** | **274.483** | **317.469** | **365.132** | **394.380** | **440.124** |
| AL | 14.771 | 15.257 | 18.503 | 19.722 | 20.465 | 20.603 | 24.795 | 28.850 | 32.660 | 39.206 | 43.179 |
| BA | 73.574 | 78.598 | 89.221 | 92.538 | 100.064 | 99.990 | 108.688 | 115.116 | 129.216 | 139.097 | 150.330 |
| CE | 20.158 | 24.684 | 30.345 | 34.001 | 37.020 | 37.661 | 42.953 | 50.705 | 58.965 | 60.219 | 65.923 |
| MA | 11.803 | 11.531 | 10.881 | 12.625 | 12.006 | 10.993 | 13.085 | 18.734 | 21.714 | 21.127 | 29.563 |
| PB | 21.806 | 23.572 | 26.373 | 27.453 | 30.279 | 30.400 | 33.981 | 37.010 | 40.712 | 42.803 | 44.311 |
| PE | 26.755 | 28.712 | 29.277 | 32.855 | 34.651 | 34.493 | 34.737 | 38.123 | 44.682 | 52.394 | 58.318 |
| PI | 1.012 | 965 | 1.388 | 2.560 | 3.196 | 2.493 | 5.353 | 15.137 | 21.274 | 20.283 | 26.609 |
| RN | 7.049 | 6.221 | 3.492 | 2.891 | 2.616 | 2.511 | 2.502 | 3.023 | 3.796 | 5.379 | 6.434 |
| SE | 5.533 | 6.260 | 6.972 | 7.219 | 8.426 | 8.163 | 8.389 | 10.771 | 12.113 | 13.872 | 15.457 |
| **Norte** | **36.480** | **36.377** | **38.328** | **39.558** | **40.848** | **41.506** | **41.049** | **48.920** | **53.078** | **57.003** | **66.229** |
| AC | 2.912 | 3.323 | 4.076 | 4.425 | 4.357 | 4.515 | 3.764 | 4.054 | 4.155 | 4.357 | 4.587 |
| AP | 249 | 205 | 80 | 80 | 239 | 219 | 198 | 262 | 334 | 355 | 212 |
| AM | 4.863 | 4.822 | 4.973 | 4.682 | 5.476 | 5.033 | 5.003 | 5.779 | 6.646 | 7.591 | 8.854 |
| PA | 11.464 | 12.404 | 13.370 | 14.754 | 15.149 | 17.121 | 16.765 | 19.254 | 21.618 | 24.623 | 28.711 |
| RO | 3.908 | 3.464 | 3.435 | 3.025 | 3.189 | 2.847 | 2.486 | 3.081 | 3.540 | 3.447 | 4.653 |
| RR | 791 | 1.516 | 1.902 | 2.137 | 2.312 | 2.697 | 2.636 | 5.092 | 4.447 | 3.419 | 3.743 |
| TO | 12.293 | 10.643 | 10.492 | 10.455 | 10.126 | 9.074 | 10.197 | 11.398 | 12.338 | 13.211 | 15.469 |
| **Sudeste** | **1.023.451** | **1.076.780** | **1.141.115** | **1.171.514** | **1.219.430** | **1.222.813** | **1.160.324** | **1.260.857** | **1.321.236** | **1.360.105** | **1.349.795** |
| ES | 19.169 | 18.244 | 18.660 | 16.808 | 17.165 | 16.017 | 13.487 | 16.530 | 18.789 | 20.571 | 22.084 |
| MG | 161.764 | 172.095 | 180.701 | 187.694 | 193.642 | 192.100 | 176.271 | 199.278 | 214.340 | 228.053 | 235.250 |
| RJ | 133.085 | 130.357 | 140.026 | 139.054 | 137.366 | 136.517 | 128.414 | 143.174 | 154.341 | 164.616 | 168.488 |
| SP | 709.433 | 756.084 | 801.728 | 827.958 | 871.257 | 878.179 | 842.152 | 901.875 | 933.766 | 946.865 | 923.973 |
| **Sul** | **405.439** | **432.825** | **433.488** | **444.207** | **459.122** | **446.448** | **405.740** | **458.694** | **486.043** | **503.461** | **501.586** |
| PR | 145.817 | 164.001 | 158.038 | 160.179 | 166.788 | 162.155 | 148.906 | 164.440 | 175.749 | 181.733 | 181.979 |
| RS | 137.026 | 144.158 | 149.286 | 155.356 | 158.328 | 151.290 | 138.699 | 160.830 | 169.751 | 173.094 | 174.397 |
| SC | 122.596 | 124.666 | 126.164 | 128.672 | 134.006 | 133.003 | 118.135 | 133.424 | 140.543 | 148.634 | 145.210 |

## Anexo B — Série completa: educação básica + tempo integral

| UF | 2015 | 2016 | 2017 | 2018 | 2019 | 2020 | 2021 | 2022 | 2023 | 2024 | 2025 |
|---|---|---|---|---|---|---|---|---|---|---|---|
| **Brasil** | 7.696.409 | 5.685.250 | 7.258.015 | 6.158.644 | 6.328.201 | 5.864.779 | 6.404.302 | 7.693.533 | 8.583.617 | 9.258.282 | 10.143.262 |
| **Centro-Oeste** | **459.198** | **365.098** | **437.188** | **372.989** | **384.192** | **363.097** | **363.654** | **430.788** | **478.291** | **503.319** | **553.939** |
| DF | 57.392 | 51.647 | 53.356 | 54.109 | 55.137 | 57.669 | 56.524 | 63.284 | 64.519 | 74.075 | 75.537 |
| GO | 190.878 | 159.005 | 207.010 | 172.768 | 174.484 | 162.307 | 165.107 | 200.194 | 204.455 | 233.286 | 264.709 |
| MT | 127.135 | 79.864 | 94.100 | 76.440 | 78.703 | 66.714 | 63.112 | 75.590 | 111.516 | 88.560 | 102.275 |
| MS | 83.793 | 74.582 | 82.722 | 69.672 | 75.868 | 76.407 | 78.911 | 91.720 | 97.801 | 107.398 | 111.418 |
| **Nordeste** | **2.756.776** | **1.490.348** | **2.495.068** | **1.923.861** | **2.097.617** | **1.610.513** | **1.969.417** | **2.416.965** | **2.872.795** | **3.077.503** | **3.596.489** |
| AL | 124.777 | 63.446 | 114.514 | 107.688 | 109.767 | 110.811 | 117.378 | 126.802 | 146.923 | 173.658 | 198.583 |
| BA | 735.022 | 458.463 | 627.719 | 446.555 | 390.965 | 287.528 | 343.138 | 397.446 | 533.863 | 620.697 | 798.858 |
| CE | 433.855 | 230.797 | 485.603 | 364.451 | 520.407 | 442.125 | 513.999 | 601.950 | 728.526 | 778.047 | 853.117 |
| MA | 438.044 | 169.835 | 316.745 | 288.591 | 325.653 | 191.218 | 311.579 | 443.685 | 453.225 | 417.685 | 525.458 |
| PB | 204.599 | 106.688 | 181.820 | 146.872 | 158.175 | 145.698 | 178.945 | 188.002 | 204.784 | 222.802 | 247.136 |
| PE | 439.523 | 266.176 | 430.082 | 296.026 | 320.457 | 258.090 | 272.904 | 316.634 | 364.735 | 416.896 | 418.515 |
| PI | 177.940 | 106.232 | 185.657 | 162.261 | 158.400 | 104.259 | 143.282 | 216.808 | 288.461 | 275.079 | 348.007 |
| RN | 137.749 | 60.523 | 98.654 | 66.684 | 69.494 | 37.109 | 37.782 | 48.027 | 63.576 | 76.210 | 95.930 |
| SE | 65.267 | 28.188 | 54.274 | 44.733 | 44.299 | 33.675 | 50.410 | 77.611 | 88.702 | 96.429 | 110.885 |
| **Norte** | **783.544** | **373.005** | **530.995** | **397.405** | **359.021** | **263.933** | **298.781** | **362.430** | **443.433** | **566.878** | **674.356** |
| AC | 41.885 | 28.545 | 26.062 | 22.081 | 18.556 | 17.970 | 15.953 | 17.909 | 21.763 | 29.446 | 34.543 |
| AP | 35.271 | 25.921 | 9.216 | 9.218 | 9.781 | 8.928 | 11.165 | 11.804 | 15.003 | 19.787 | 19.610 |
| AM | 161.671 | 92.207 | 137.588 | 78.871 | 86.238 | 66.369 | 67.755 | 81.603 | 100.491 | 113.278 | 134.178 |
| PA | 327.728 | 109.255 | 210.203 | 188.701 | 142.394 | 85.505 | 103.007 | 129.628 | 170.684 | 251.366 | 320.688 |
| RO | 85.475 | 38.400 | 28.721 | 18.140 | 19.264 | 17.480 | 18.239 | 17.946 | 18.608 | 19.877 | 22.558 |
| RR | 6.398 | 7.356 | 6.737 | 8.275 | 7.477 | 6.423 | 6.349 | 13.832 | 12.978 | 9.771 | 13.624 |
| TO | 125.116 | 71.321 | 112.468 | 72.119 | 75.311 | 61.258 | 76.313 | 89.708 | 103.906 | 123.353 | 129.155 |
| **Sudeste** | **2.623.588** | **2.530.332** | **2.785.676** | **2.574.964** | **2.579.662** | **2.739.000** | **2.954.134** | **3.537.844** | **3.764.678** | **3.979.487** | **4.120.106** |
| ES | 92.659 | 57.509 | 66.312 | 54.991 | 60.247 | 63.136 | 74.584 | 98.539 | 114.186 | 133.145 | 146.070 |
| MG | 572.674 | 559.657 | 593.338 | 526.121 | 448.243 | 474.002 | 487.259 | 605.169 | 583.208 | 643.785 | 703.925 |
| RJ | 440.711 | 403.429 | 520.100 | 471.939 | 459.558 | 466.147 | 462.217 | 491.339 | 532.577 | 589.017 | 611.320 |
| SP | 1.517.544 | 1.509.737 | 1.605.926 | 1.521.913 | 1.611.614 | 1.735.715 | 1.930.074 | 2.342.797 | 2.534.707 | 2.613.540 | 2.658.791 |
| **Sul** | **1.073.303** | **926.467** | **1.009.088** | **889.425** | **907.709** | **888.236** | **818.316** | **945.506** | **1.024.420** | **1.131.095** | **1.198.372** |
| PR | 386.082 | 363.211 | 368.719 | 334.954 | 342.451 | 342.884 | 324.342 | 370.851 | 418.846 | 479.027 | 482.341 |
| RS | 423.147 | 320.690 | 387.568 | 311.601 | 320.203 | 303.564 | 272.793 | 323.254 | 352.077 | 370.856 | 422.219 |
| SC | 264.074 | 242.566 | 252.801 | 242.870 | 245.055 | 241.788 | 221.181 | 251.401 | 253.497 | 281.212 | 293.812 |
