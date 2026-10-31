
# Scraper CNES – Mapeamento Geográfico de Egressos Médicos da EMCM

## 🎯 Objetivo Geral

Este projeto tem como finalidade desenvolver uma ferramenta automatizada para **rastrear, extrair e geolocalizar os médicos egressos da Escola Multicampi de Ciências Médicas da UFRN (EMCM)**, com base nos dados públicos disponibilizados pelo CNES (Cadastro Nacional de Estabelecimentos de Saúde). A aplicação principal é construir um **mapa interativo que demonstre a distribuição desses profissionais no território nacional**, com destaque para sua área de atuação (CBO).

---

## 🧱 Estrutura do Projeto

### 1. Web Scraper Automatizado (Python + Selenium)
- Lê uma lista de egressos da EMCM (nome completo).
- Acessa o portal CNES e faz a busca individualizada.
- Extrai:
  - Nome do médico
  - Município
  - UF
  - CBO (Classificação Brasileira de Ocupações)
- Faz fallback com nome sem acento, se necessário.
- Mostra o progresso de cada consulta e registra ocorrências em `scraper.log`.
- Grava primeiro em `egressos_resultados.tmp.csv` e só substitui `egressos_resultados.csv` se a coleta trouxer ao menos um vínculo válido.
- Salva os erros em `egressos_erros.txt`.

### 2. Validação e Limpeza
- Remove registros incompletos (sem UF, CBO, município).
- Normaliza e padroniza os nomes.
- Associa as coordenadas geográficas via merge com um dataset de municípios.

### 3. Painel (Folium + Plotly)
- Mapa de pinos com um pino por vínculo, colorido pela grande área de atuação, com camadas que podem ser ligadas e desligadas. Pinos do mesmo município recebem um pequeno deslocamento determinístico.
- Mapa de calor da densidade de vínculos.
- Raio de 150 km em torno de Caicó/RN (distância em linha reta pela fórmula de Haversine), com indicadores e um gráfico comparativo.
- Gráficos por UF, região, CBO, grande área e recorte territorial.
- Mapas base sem chave de API (Esri cinza-claro e OpenStreetMap).
- Saídas: `dashboard_final.html`, `mapa_pins.html`, `mapa_calor.html`, `relatorio_impressao.html` e `metodologia.html`. Os modelos das páginas ficam em `templates/`.

### 4. Auditoria dos Dados
`auditoria.py` confere se os números do painel podem ser rastreados até a coleta:
- **Funil:** da lista de identificadores aos vínculos exibidos, com o motivo de cada exclusão.
- **Coerência entre fontes:** lista, `scraper.log`, `egressos_resultados.csv` e o próprio gerador do painel precisam bater, inclusive na contagem de vínculos de cada identificador.
- **Egressos sem vínculo:** separa falha técnica (consultar de novo), cadastro sem vínculo ativo e ausência na busca.
- **Alertas para revisão:** identificador repetido na lista, ocupação não médica, 6 ou mais vínculos, vínculos a mais de 1.000 km entre si, encontrado só na busca sem acento.
- **Conferência manual:** sorteia uma amostra (semente fixa) em `auditoria_amostra.csv`. Depois de conferir no site do CNES e preencher a coluna `confere_no_cnes`, a auditoria calcula a taxa de concordância.
- **Rastreabilidade:** SHA-256 de cada arquivo de entrada, para provar quais dados geraram o painel.

```bash
python auditoria.py             # relatório interno, com identificadores
python auditoria.py --anonimo   # identificadores trocados por códigos, para compartilhar
```

Os relatórios e a amostra são gravados na pasta `auditoria/`, separada dos arquivos do site. Eles contêm dados individuais: ficam fora do Git e **não devem ser enviados ao servidor web**.

---

## 🧭 Justificativa

A EMCM é uma escola comprometida com a descentralização da formação médica e com foco na atenção básica. Este projeto oferece uma ferramenta visual, automatizada e de fácil atualização para acompanhamento dos egressos e avaliação de políticas públicas.

---

## 🧑‍🎓 Tese de Mestrado

Este projeto é desenvolvido como parte de uma tese de mestrado profissional na área de saúde e educação médica, apoiando-se em:
- Inovação tecnológica
- Acompanhamento institucional
- Dados abertos e automação

---

## ▶️ Como Usar

**Atenção:** Antes de executar os scripts, crie um arquivo chamado `nomes_egressos.txt` na mesma pasta do projeto. Dentro dele, insira o nome completo ou o CPF de cada egresso que deseja pesquisar, colocando um por linha.


```bash
pip install -r requirements.txt
```

No Windows, rode o fluxo completo com `executar_pipeline.bat`. Ele faz a coleta e só gera o painel se a coleta der certo.

Para rodar cada etapa separadamente:

```bash
python scraper.py
python dashboard_generator.py
```

> O gerador requer `egressos_resultados.csv` e `municipios.csv` na mesma pasta. Para publicar, envie os cinco HTMLs gerados e a pasta `assets/`. A auditoria roda automaticamente no fim de `executar_pipeline.bat`.

---

## 📁 .gitignore recomendado

```text
venv/
nomes_egressos.txt
egressos_resultados.csv
egressos_erros.txt
mapa_pins.html
mapa_calor.html
dashboard_final.html
/relatorio_impressao.html
/metodologia.html
egressos_resultados.tmp.csv
*.log
__pycache__/
```

---

## 📌 Licença

Projeto acadêmico com fins educacionais e de gestão pública. Compartilhável sob licença MIT.
