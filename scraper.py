import csv
import unicodedata
from urllib.parse import quote
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager

# ======= Função para remover acentos =======
def remover_acentos(texto):
    return ''.join(
        c for c in unicodedata.normalize('NFD', texto)
        if unicodedata.category(c) != 'Mn'
    )

# ======= Configuração do navegador =======
chrome_options = Options()
# chrome_options.add_argument("--headless")  # descomente se quiser rodar sem abrir a janela
chrome_options.add_argument("--disable-gpu")
chrome_options.add_argument("--no-sandbox")
chrome_options.add_argument("--disable-dev-shm-usage")

# Use webdriver-manager para baixar o ChromeDriver compatível com a versão do Chrome instalada
service = Service(ChromeDriverManager().install())
driver = webdriver.Chrome(service=service, options=chrome_options)

# Log de erros
erros = []

# ======= Função principal de scraping =======
def processar_nome(nome):
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
                erros.append(msg)
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
                erros.append(msg)

            return resultados

        except Exception as e:
            msg = f"{nome} - Erro inesperado: {str(e)}"
            if tentativa_extra: msg += " (sem acento)"
            erros.append(msg)
            return []

    # ======= Primeira tentativa com nome original
    print(f"\n🔎 Buscando: {nome}")
    resultados = tentar_busca(nome)

    # ======= Segunda tentativa com nome sem acento
    if not resultados:
        nome_sem = remover_acentos(nome)
        print(f"↪️ Tentando sem acento: {nome_sem}")
        resultados = tentar_busca(nome_sem, tentativa_extra=True)

    return resultados

# ======= Lê os nomes do TXT =======
with open('nomes_egressos.txt', 'r', encoding='utf-8') as f:
    nomes = [linha.strip() for linha in f if linha.strip()]

# ======= Gera CSV final =======
with open('egressos_resultados.csv', 'w', newline='', encoding='utf-8') as csvfile:
    campos = ['nome', 'municipio', 'uf', 'cbo']
    writer = csv.DictWriter(csvfile, fieldnames=campos)
    writer.writeheader()

    for nome in nomes:
        resultados = processar_nome(nome)
        for linha in resultados:
            writer.writerow(linha)

# ======= Gera log de erros =======
if erros:
    with open('egressos_erros.txt', 'w', encoding='utf-8') as f:
        f.write("Nomes com falha durante o scraping:\n\n")
        for linha in erros:
            f.write(linha + "\n")

driver.quit()
print("\n✅ Fim! Resultados salvos em 'egressos_resultados.csv'")
if erros:
    print("⚠️ Alguns nomes apresentaram erro. Veja 'egressos_erros.txt'")
