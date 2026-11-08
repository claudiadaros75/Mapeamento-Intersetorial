# Decomposição regional da variação de matrículas em tempo integral (2015–2025)

**Recorte:** Educação infantil – creche · Sexo feminino · Tempo integral · Todas as redes
**Fonte:** INEP – Censo Escolar, painel *Matrículas – Estatísticas gerais* (InepData / Power BI), página 2 de 24
**Data da coleta:** 16/10/2026

---

## 1. Pergunta de pesquisa

O gráfico de barras do painel mostra uma evolução relativamente suave de 2015 a 2025: as matrículas passam de 852.773 para 1.221.896. Há uma queda em 2020–2021 e uma recuperação em seguida.

Apesar dessa tendência agregada sem mudanças bruscas, a pergunta é: **quais estados (e regiões) mais contribuíram para as variações, para mais ou para menos?**

---

## 2. Processo de coleta dos dados

O painel do INEP não oferece exportação dos dados por UF. Por isso os valores foram extraídos diretamente da página, com automação no navegador.

1. **Identificação dos filtros ativos:** período 2015–2025, Rede = Todos, Etapa = Educação infantil – creche, Categoria = Sexo – Feminino e o botão *Tempo integral* selecionado.
2. **Estrutura do filtro "Região, UF, município":** é uma segmentação hierárquica de seleção única (Brasil → Região → UF → Município).
3. **Leitura dos valores do gráfico:** em vez de ler visualmente as barras, foram lidos os rótulos de dados do gráfico *Evolução da matrícula* (elementos `<text>` do SVG). Isso garante os números exatos exibidos.
4. **Automação da seleção:** um script em JavaScript, executado no console da página:
   - abria o menu suspenso do filtro;
   - expandia cada região e selecionava cada UF (nível 3 da hierarquia);
   - esperava o título do gráfico mudar para o nome da UF e os 11 valores carregarem;
   - armazenava a série e rolava a lista. A lista é virtualizada: só renderiza os itens visíveis.
5. **Validação:** a soma das 27 UFs foi comparada com o total Brasil em cada ano. **A diferença foi zero em todos os 11 anos**, o que confirma que a coleta está completa e correta.
6. **Cálculos** (em Python):
   - Variação absoluta da UF: Δᵢ = Xᵢ,₂₀₂₅ − Xᵢ,₂₀₁₅
   - **Contribuição para a variação nacional:** Cᵢ = Δᵢ / Δ_Brasil
   - Crescimento próprio: gᵢ = Xᵢ,₂₀₂₅ / Xᵢ,₂₀₁₅ − 1
   - Participação no total: wᵢ,t = Xᵢ,t / X_Brasil,t
   - Decomposição ano a ano: as três UFs com maior |ΔXᵢ,t| em cada transição

> **Identidade útil:** Cᵢ = wᵢ,₂₀₁₅ · gᵢ / g_Brasil. A contribuição de um estado depende do seu **tamanho inicial** e do seu **ritmo de crescimento**, ponderado pelo crescimento nacional.

---

## 3. Dados coletados

### 3.1 Série Brasil

| 2015 | 2016 | 2017 | 2018 | 2019 | 2020 | 2021 | 2022 | 2023 | 2024 | 2025 |
|---|---|---|---|---|---|---|---|---|---|---|
| 852.773 | 900.864 | 947.287 | 978.479 | 1.022.246 | 1.011.939 | 971.527 | 1.078.188 | 1.147.419 | 1.196.288 | 1.221.896 |

### 3.2 Série por UF

| UF | 2015 | 2016 | 2017 | 2018 | 2019 | 2020 | 2021 | 2022 | 2023 | 2024 | 2025 |
|---|---|---|---|---|---|---|---|---|---|---|---|
| **Centro-Oeste** | | | | | | | | | | | |
| DF | 5.342 | 5.913 | 6.457 | 7.557 | 8.133 | 9.004 | 10.022 | 11.096 | 11.774 | 14.068 | 15.066 |
| GO | 22.343 | 24.495 | 26.924 | 28.000 | 29.916 | 28.308 | 27.593 | 30.799 | 32.211 | 34.635 | 37.642 |
| MT | 15.001 | 16.087 | 15.926 | 15.329 | 15.289 | 13.991 | 12.849 | 14.164 | 14.343 | 15.239 | 17.193 |
| MS | 18.780 | 18.728 | 19.758 | 20.214 | 20.562 | 19.632 | 17.082 | 18.715 | 19.084 | 19.878 | 20.167 |
| **Nordeste** | | | | | | | | | | | |
| AL | 7.147 | 7.298 | 8.845 | 9.454 | 9.787 | 9.764 | 11.912 | 13.763 | 15.608 | 18.572 | 20.350 |
| BA | 34.976 | 37.493 | 42.552 | 44.025 | 47.762 | 47.511 | 52.297 | 55.046 | 61.529 | 66.575 | 71.958 |
| CE | 9.496 | 11.644 | 14.508 | 16.253 | 17.495 | 17.695 | 20.419 | 23.981 | 27.819 | 28.494 | 30.977 |
| MA | 5.775 | 5.227 | 5.127 | 6.068 | 5.782 | 5.233 | 6.142 | 8.873 | 10.146 | 9.779 | 13.747 |
| PB | 10.031 | 10.972 | 12.212 | 12.812 | 14.218 | 14.329 | 16.051 | 17.495 | 19.311 | 20.064 | 20.721 |
| PE | 12.452 | 13.402 | 13.705 | 15.427 | 16.379 | 16.126 | 16.353 | 18.106 | 21.310 | 24.744 | 27.519 |
| PI | 471 | 435 | 665 | 1.222 | 1.544 | 1.188 | 2.646 | 7.369 | 10.124 | 9.716 | 12.768 |
| RN | 3.291 | 2.942 | 1.637 | 1.365 | 1.280 | 1.185 | 1.164 | 1.382 | 1.768 | 2.528 | 3.002 |
| SE | 2.497 | 2.948 | 3.328 | 3.369 | 3.861 | 3.726 | 3.874 | 5.062 | 5.701 | 6.611 | 7.254 |
| **Norte** | | | | | | | | | | | |
| AC | 1.399 | 1.532 | 1.955 | 2.099 | 2.071 | 2.172 | 1.873 | 1.951 | 1.950 | 2.033 | 2.178 |
| AP | 116 | 106 | 32 | 42 | 117 | 102 | 81 | 81 | 150 | 145 | 91 |
| AM | 2.331 | 2.300 | 2.345 | 2.226 | 2.665 | 2.386 | 2.399 | 2.797 | 3.197 | 3.740 | 4.365 |
| PA | 5.329 | 5.716 | 6.186 | 6.952 | 7.091 | 8.093 | 7.907 | 9.249 | 10.255 | 11.536 | 13.362 |
| RO | 1.889 | 1.675 | 1.619 | 1.442 | 1.540 | 1.361 | 1.190 | 1.433 | 1.649 | 1.629 | 2.245 |
| RR | 368 | 726 | 894 | 1.023 | 1.106 | 1.300 | 1.220 | 2.450 | 2.198 | 1.661 | 1.767 |
| TO | 5.858 | 5.075 | 5.071 | 5.029 | 4.838 | 4.279 | 4.846 | 5.340 | 5.825 | 6.125 | 7.191 |
| **Sudeste** | | | | | | | | | | | |
| ES | 9.074 | 8.673 | 8.877 | 7.868 | 8.026 | 7.547 | 6.346 | 7.807 | 8.953 | 9.809 | 10.422 |
| MG | 77.667 | 82.402 | 86.665 | 90.008 | 92.873 | 91.860 | 84.197 | 95.236 | 102.882 | 109.292 | 112.551 |
| RJ | 62.794 | 61.077 | 66.248 | 66.404 | 65.739 | 65.182 | 61.459 | 69.040 | 73.931 | 78.859 | 80.642 |
| SP | 341.740 | 364.476 | 386.260 | 400.196 | 421.324 | 424.618 | 406.217 | 434.983 | 450.049 | 456.576 | 445.594 |
| **Sul** | | | | | | | | | | | |
| PR | 70.886 | 79.325 | 76.496 | 77.351 | 81.067 | 78.376 | 71.992 | 79.852 | 85.317 | 88.280 | 88.704 |
| RS | 66.464 | 69.872 | 71.951 | 74.771 | 77.269 | 73.080 | 66.815 | 77.900 | 82.285 | 83.978 | 84.235 |
| SC | 59.256 | 60.325 | 61.044 | 61.973 | 64.512 | 63.891 | 56.581 | 64.218 | 68.050 | 71.722 | 70.185 |

---

## 4. Resultados

### 4.1 Variação total 2015 → 2025

**Δ Brasil = +369.123 matrículas (+43,3%)**

### 4.2 Contribuição por região

| Região | 2015 | 2025 | Δ | % do Δ Brasil | Participação 2015 → 2025 |
|---|---|---|---|---|---|
| Sudeste | 491.275 | 649.209 | +157.934 | 42,8% | 57,6% → 53,1% |
| Nordeste | 86.136 | 208.296 | +122.160 | 33,1% | 10,1% → 17,0% |
| Sul | 196.606 | 243.124 | +46.518 | 12,6% | 23,1% → 19,9% |
| Centro-Oeste | 61.466 | 90.068 | +28.602 | 7,7% | 7,2% → 7,4% |
| Norte | 17.290 | 31.199 | +13.909 | 3,8% | 2,0% → 2,6% |

### 4.3 Contribuição por UF (ordenada)

| UF | Δ 2015–25 | % do Δ Brasil | Crescimento próprio | Part. 2015 | Part. 2025 |
|---|---|---|---|---|---|
| SP | +103.854 | 28,1% | +30,4% | 40,1% | 36,5% |
| BA | +36.982 | 10,0% | +105,7% | 4,1% | 5,9% |
| MG | +34.884 | 9,5% | +44,9% | 9,1% | 9,2% |
| CE | +21.481 | 5,8% | +226,2% | 1,1% | 2,5% |
| RJ | +17.848 | 4,8% | +28,4% | 7,4% | 6,6% |
| PR | +17.818 | 4,8% | +25,1% | 8,3% | 7,3% |
| RS | +17.771 | 4,8% | +26,7% | 7,8% | 6,9% |
| GO | +15.299 | 4,1% | +68,5% | 2,6% | 3,1% |
| PE | +15.067 | 4,1% | +121,0% | 1,5% | 2,3% |
| AL | +13.203 | 3,6% | +184,7% | 0,8% | 1,7% |
| PI | +12.297 | 3,3% | +2.610,8% | 0,1% | 1,0% |
| SC | +10.929 | 3,0% | +18,4% | 6,9% | 5,7% |
| PB | +10.690 | 2,9% | +106,6% | 1,2% | 1,7% |
| DF | +9.724 | 2,6% | +182,0% | 0,6% | 1,2% |
| PA | +8.033 | 2,2% | +150,7% | 0,6% | 1,1% |
| MA | +7.972 | 2,2% | +138,0% | 0,7% | 1,1% |
| SE | +4.757 | 1,3% | +190,5% | 0,3% | 0,6% |
| MT | +2.192 | 0,6% | +14,6% | 1,8% | 1,4% |
| AM | +2.034 | 0,6% | +87,3% | 0,3% | 0,4% |
| RR | +1.399 | 0,4% | +380,2% | 0,0% | 0,1% |
| MS | +1.387 | 0,4% | +7,4% | 2,2% | 1,7% |
| ES | +1.348 | 0,4% | +14,9% | 1,1% | 0,9% |
| TO | +1.333 | 0,4% | +22,8% | 0,7% | 0,6% |
| AC | +779 | 0,2% | +55,7% | 0,2% | 0,2% |
| RO | +356 | 0,1% | +18,8% | 0,2% | 0,2% |
| AP | −25 | −0,0% | −21,6% | 0,0% | 0,0% |
| RN | −289 | −0,1% | −8,8% | 0,4% | 0,2% |

### 4.4 Decomposição ano a ano (3 UFs com maior variação absoluta)

| Transição | Δ Brasil | Principais UFs |
|---|---|---|
| 2015→16 | +48.091 | SP +22.736 · PR +8.439 · MG +4.735 |
| 2016→17 | +46.423 | SP +21.784 · RJ +5.171 · BA +5.059 |
| 2017→18 | +31.192 | SP +13.936 · MG +3.343 · RS +2.820 |
| 2018→19 | +43.767 | SP +21.128 · BA +3.737 · PR +3.716 |
| 2019→20 | **−10.307** | RS −4.189 · SP +3.294 · PR −2.691 |
| 2020→21 | **−40.412** | SP −18.401 · MG −7.663 · SC −7.310 |
| 2021→22 | **+106.661** | SP +28.766 · RS +11.085 · MG +11.039 |
| 2022→23 | +69.231 | SP +15.066 · MG +7.646 · BA +6.483 |
| 2023→24 | +48.869 | SP +6.527 · MG +6.410 · BA +5.046 |
| 2024→25 | +25.608 | **SP −10.982** · BA +5.383 · MA +3.968 |

---

## 5. Interpretação

1. **A estabilidade do agregado esconde uma realocação regional.** O total cresce de forma suave, mas o Sudeste e o Sul perdem participação, enquanto o Nordeste passa de 10% para 17% do total.
2. **São Paulo domina em volume, mas desacelera.** Respondeu por 28% do crescimento absoluto, mas cresceu só 30% e perdeu 3,6 p.p. de participação. Em 2025, SP **recuou** 10.982 matrículas, e o Brasil ainda assim cresceu, sustentado por estados do Nordeste.
3. **O Nordeste é o motor relativo.** BA, CE, PE, AL, PB, MA e PI dobraram ou mais que dobraram suas matrículas. O **Piauí** saiu de 471 para 12.768 (×27), com o salto concentrado entre 2021 e 2023. Esse caso merece verificação: pode ser expansão real da oferta ou mudança no registro/declaração ao Censo.
4. **O choque da pandemia (2020–2021)** foi concentrado no Sudeste e no Sul: SP, MG, SC, RS e PR explicam a maior parte da queda de −40 mil. A recuperação em 2022 (+106 mil) foi a maior da série e generalizada.
5. **Estagnação e queda:** apenas RN e AP terminam abaixo de 2015. MS, MT e ES crescem bem abaixo da média nacional. O RN chama atenção pela queda forte entre 2016 e 2021, seguida de recuperação apenas parcial.

### Limitações

- O recorte é **feminino + creche + tempo integral**. As conclusões não devem ser generalizadas para todas as etapas ou para o total de matrículas sem uma nova coleta.
- Os dados do Censo cobrem a população, não uma amostra. As diferenças são descritivas; testes de hipótese exigem cuidado na interpretação (ver seção 6).
- Não se avaliou a **proporção** de tempo integral em relação ao total de matrículas em creche. Isso exigiria coletar também a série "Total" por UF.
- A análise municipal (≈5.570 municípios) não é viável pelo painel. Recomenda-se usar os **microdados do Censo Escolar**.

---

## 6. Próximos passos sugeridos

- Coletar a série **Total** por UF e analisar a **participação do tempo integral** (TI / total) em cada estado.
- Testar formalmente se a participação do Nordeste aumentou de forma sustentada, com teste de Mann-Kendall, regressão da participação contra o ano ou teste de quebra estrutural (Chow) em 2021/2022.
- Usar os microdados do INEP para decompor por **município** e por **rede** (municipal × privada conveniada), já que a rede municipal concentra a maior parte das creches em tempo integral.
- Investigar as políticas associadas aos saltos (por exemplo, o Programa Escola em Tempo Integral, Lei 14.640/2023), possivelmente com diferença em diferenças.

---

## 7. Questões para uso em aula

1. SP respondeu por 28% do crescimento absoluto, mas cresceu só 30%. O Piauí cresceu 2.600%, mas respondeu por 3%. Qual métrica responde "quem mais contribuiu" e qual responde "quem mais se transformou"? Por que as duas levam a conclusões diferentes?
2. Mostre algebricamente que Cᵢ = Δᵢ / Δ_Brasil = wᵢ,₂₀₁₅ · gᵢ / g_Brasil. O que isso implica para estados grandes que crescem pouco?
3. Em 2025, SP caiu e o Brasil cresceu. Construa um exemplo numérico com três estados em que o total sobe enquanto o maior estado cai.
4. O salto do Piauí entre 2021 e 2023 é um outlier. Que gráficos ou testes (resíduos de uma tendência, boxplot das taxas de crescimento) você usaria para detectá-lo? Que hipóteses não estatísticas investigaria?
5. Como testar formalmente se a participação do Nordeste aumentou de forma sustentada, e não por um choque pontual?
6. A validação "soma das UFs = total Brasil" foi exata. Por que essa checagem é importante ao extrair dados de painéis? Que outras verificações de consistência você faria?
7. Os dados são só de matrículas femininas em creche. Que viés surgiria ao generalizar as conclusões para "tempo integral" em geral?
8. Como os dados do Censo cobrem toda a população, faz sentido calcular p-valores para a diferença entre 2015 e 2025? Discuta a ideia de "superpopulação" ou de processo gerador dos dados.
