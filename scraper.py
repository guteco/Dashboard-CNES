import csv
import logging
import os
import sys
import unicodedata
from pathlib import Path
from urllib.parse import quote
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager

PASTA = Path(__file__).resolve().parent
ARQUIVO_NOMES = PASTA / "nomes_egressos.txt"
ARQUIVO_RESULTADOS = PASTA / "egressos_resultados.csv"
ARQUIVO_TEMPORARIO = PASTA / "egressos_resultados.tmp.csv"
ARQUIVO_ERROS = PASTA / "egressos_erros.txt"
ARQUIVO_LOG = PASTA / "scraper.log"

logging.basicConfig(
    filename=ARQUIVO_LOG,
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    encoding="utf-8",
)

# ======= Função para remover acentos =======
def remover_acentos(texto):
    return ''.join(
        c for c in unicodedata.normalize('NFD', texto)
        if unicodedata.category(c) != 'Mn'
    )

# ======= Configuração do navegador =======
def criar_driver():
    chrome_options = Options()
    # chrome_options.add_argument("--headless")  # descomente se quiser rodar sem abrir a janela
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")

    # Use webdriver-manager para baixar o ChromeDriver compatível com a versão do Chrome instalada
    service = Service(ChromeDriverManager().install())
    return webdriver.Chrome(service=service, options=chrome_options)

# Log de erros
erros = []

def registrar_erro(msg):
    erros.append(msg)
    logging.warning(msg)

# ======= Função principal de scraping =======
def processar_nome(driver, nome):
    def tentar_busca(nome_para_buscar, tentativa_extra=False):
        try:
            url = f"https://cnes.datasus.gov.br/pages/profissionais/consulta.jsp?search={quote(nome_para_buscar, safe='')}"
            driver.get(url)

            WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.XPATH, "//body"))
            )

            if "Não Existem Dados" in driver.page_source:
                return []

            try:
                botao = WebDriverWait(driver, 10).until(
                    EC.element_to_be_clickable((By.XPATH, "//button[@title='Vínculos ativos']"))
                )
                driver.execute_script("arguments[0].scrollIntoView(true);", botao)
                botao.click()
            except Exception as e:
                msg = f"{nome} - Botão de vínculos não clicável: {e}"
                if tentativa_extra: msg += " (sem acento)"
                registrar_erro(msg)
                return []

            WebDriverWait(driver, 10).until(
                EC.visibility_of_element_located((By.ID, "vinculoModal"))
            )
            modal = driver.find_element(By.ID, "vinculoModal")
            tabela = modal.find_element(By.CLASS_NAME, "table")
            linhas = tabela.find_elements(By.TAG_NAME, "tr")

            resultados = []
            for linha in linhas[1:]:
                colunas = linha.find_elements(By.TAG_NAME, "td")
                if len(colunas) >= 4:
                    municipio = colunas[2].text.strip()
                    uf = colunas[1].text.strip()
                    cbo = colunas[3].text.strip()

                    # Validação dos dados
                    if len(municipio) < 3 or len(uf) != 2 or '-' not in cbo:
                        continue  # pula linha inválida

                    resultados.append({
                        "nome": nome,
                        "municipio": municipio,
                        "uf": uf,
                        "cbo": cbo
                    })

            if not resultados:
                msg = f"{nome} - Nenhum vínculo encontrado (dados inválidos)"
                if tentativa_extra: msg += " (sem acento)"
                registrar_erro(msg)

            return resultados

        except Exception as e:
            msg = f"{nome} - Erro inesperado: {str(e)}"
            if tentativa_extra: msg += " (sem acento)"
            registrar_erro(msg)
            return []

    # ======= Primeira tentativa com nome original
    resultados = tentar_busca(nome)

    # ======= Segunda tentativa com nome sem acento
    if not resultados:
        nome_sem = remover_acentos(nome)
        if nome_sem != nome:
            print(f"   ↪️ Tentando sem acento: {nome_sem}")
            resultados = tentar_busca(nome_sem, tentativa_extra=True)

    return resultados

def main():
    # ======= Lê os nomes do TXT =======
    if not ARQUIVO_NOMES.exists():
        print(f"❌ Arquivo não encontrado: {ARQUIVO_NOMES.name}")
        return 1
    with open(ARQUIVO_NOMES, 'r', encoding='utf-8') as f:
        nomes = [linha.strip() for linha in f if linha.strip()]
    if not nomes:
        print(f"❌ {ARQUIVO_NOMES.name} está vazio.")
        return 1

    logging.info("Início da coleta: %d identificadores", len(nomes))
    total_vinculos = 0
    driver = criar_driver()
    try:
        # ======= Grava primeiro em arquivo temporário =======
        with open(ARQUIVO_TEMPORARIO, 'w', newline='', encoding='utf-8') as csvfile:
            campos = ['nome', 'municipio', 'uf', 'cbo']
            writer = csv.DictWriter(csvfile, fieldnames=campos)
            writer.writeheader()

            for i, nome in enumerate(nomes, start=1):
                print(f"\n🔎 [{i}/{len(nomes)}] Buscando: {nome}")
                resultados = processar_nome(driver, nome)
                for linha in resultados:
                    writer.writerow(linha)
                csvfile.flush()
                total_vinculos += len(resultados)
                print(f"   {len(resultados)} vínculo(s)")
                logging.info("[%d/%d] %d vínculo(s)", i, len(nomes), len(resultados))
    except KeyboardInterrupt:
        print("\n⚠️ Coleta interrompida. A base anterior foi mantida.")
        logging.error("Coleta interrompida pelo usuário")
        return 1
    finally:
        driver.quit()

    # ======= Gera log de erros =======
    if erros:
        with open(ARQUIVO_ERROS, 'w', encoding='utf-8') as f:
            f.write("Nomes com falha durante o scraping:\n\n")
            for linha in erros:
                f.write(linha + "\n")

    # ======= Substitui a base oficial somente se a coleta produziu dados =======
    if total_vinculos == 0:
        print("\n❌ Nenhum vínculo válido coletado. A base anterior foi mantida.")
        logging.error("Nenhum vínculo válido coletado; base anterior mantida")
        return 1
    os.replace(ARQUIVO_TEMPORARIO, ARQUIVO_RESULTADOS)
    logging.info("Fim da coleta: %d vínculos, %d ocorrências", total_vinculos, len(erros))

    print(f"\n✅ Fim! {total_vinculos} vínculos salvos em '{ARQUIVO_RESULTADOS.name}'")
    if erros:
        print(f"⚠️ Alguns nomes apresentaram erro. Veja '{ARQUIVO_ERROS.name}'")
    return 0

if __name__ == "__main__":
    sys.exit(main())
