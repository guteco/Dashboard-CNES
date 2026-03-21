
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
- Salva os dados em `egressos_resultados.csv` e os erros em `egressos_erros.txt`.

### 2. Validação e Limpeza
- Remove registros incompletos (sem UF, CBO, município).
- Normaliza e padroniza os nomes.
- Associa as coordenadas geográficas via merge com um dataset de municípios.

### 3. Visualização Interativa (Folium)
- Gera um mapa HTML com pins por município.
- Cada pin exibe:
  - Quantidade de médicos
  - Especialidade (CBO)
- Cores diferentes por tipo de especialidade.
- Resultado final: `dashboard_final.html` (além de mapas isolados e da página do dashboard).

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
# Instale os requisitos
pip install -r requirements.txt

# Execute o scraping
python scraper.py

# Gere o mapa interativo e o dashboard completo
python dashboard_generator.py
```

> Requer: `egressos_resultados.csv` e `municipios.csv` na mesma pasta.

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
grafico_*.html
__pycache__/
```

---

## 📌 Licença

Projeto acadêmico com fins educacionais e de gestão pública. Compartilhável sob licença MIT.
