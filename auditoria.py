#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Auditoria dos dados do Painel de Egressos.

Reconcilia a lista de identificadores, o log da coleta, os erros e o CSV
de resultados com o que aparece no painel, e aponta casos para revisão.

Uso:
    python auditoria.py                 relatório com identificadores (uso interno)
    python auditoria.py --anonimo       troca identificadores por códigos (E001...)
    python auditoria.py --amostra 30    tamanho da amostra para conferência manual
    python auditoria.py --nova-amostra  sorteia uma amostra nova (sobrescreve a planilha)

Saídas, na pasta auditoria/ (contêm dados individuais: ficam fora do Git
e não devem ir para o servidor web):
    auditoria.html ou auditoria_anonima.html
    auditoria_amostra.csv  planilha para conferir a amostra no site do CNES
"""

import argparse
import csv
import hashlib
import html
import random
import re
import sys
from collections import defaultdict
from datetime import datetime
from itertools import combinations
from pathlib import Path

import pandas as pd

import dashboard_generator as painel

PASTA = painel.PASTA
ARQ_NOMES = PASTA / "nomes_egressos.txt"
ARQ_RESULTADOS = PASTA / "egressos_resultados.csv"
ARQ_ERROS = PASTA / "egressos_erros.txt"
ARQ_LOG = PASTA / "scraper.log"
ARQ_MUNICIPIOS = PASTA / "municipios.csv"
# Pasta separada dos arquivos do site, para não ser publicada por engano
PASTA_SAIDA = PASTA / "auditoria"
ARQ_AMOSTRA = PASTA_SAIDA / "auditoria_amostra.csv"

# === Critérios de alerta ===
MUITOS_VINCULOS = 6
DISTANCIA_ALERTA_KM = 1000
TAMANHO_AMOSTRA = 20
SEMENTE_AMOSTRA = 2026

MOTIVO_CAMPO_VAZIO = "Campo vazio (município, UF ou CBO)"
MOTIVO_UF = "UF inválida"
MOTIVO_MUNICIPIO = "Município sem correspondência no IBGE"
MOTIVO_NAO_MEDICO = "Ocupação não médica"


def esc(valor):
    return html.escape(str(valor))


def sha256(caminho):
    if not caminho.exists():
        return "arquivo ausente"
    return hashlib.sha256(caminho.read_bytes()).hexdigest()


def tabela(cabecalhos, linhas, vazio="Nenhum caso."):
    if not linhas:
        return f"<p class='vazio'>{esc(vazio)}</p>"
    cab = "".join(f"<th>{esc(c)}</th>" for c in cabecalhos)
    corpo = "".join("<tr>" + "".join(f"<td>{c}</td>" for c in linha) + "</tr>" for linha in linhas)
    return f"<div class='tabela'><table><thead><tr>{cab}</tr></thead><tbody>{corpo}</tbody></table></div>"


# === Leitura das fontes ===
def ler_identificadores():
    with open(ARQ_NOMES, encoding="utf-8") as f:
        return [linha.strip() for linha in f if linha.strip()]


def ler_log():
    """Lê a última coleta registrada em scraper.log."""
    info = {"existe": ARQ_LOG.exists(), "execucoes": 0, "inicio": None, "fim": None,
            "total_declarado": None, "concluida": False, "por_indice": {}}
    if not info["existe"]:
        return info
    linhas = ARQ_LOG.read_text(encoding="utf-8").splitlines()
    inicios = [i for i, l in enumerate(linhas) if "Início da coleta" in l]
    info["execucoes"] = len(inicios)
    if not inicios:
        return info
    bloco = linhas[inicios[-1]:]
    info["inicio"] = bloco[0][:19]
    m = re.search(r"Início da coleta: (\d+)", bloco[0])
    info["total_declarado"] = int(m.group(1)) if m else None
    for linha in bloco:
        m = re.search(r"\[(\d+)/(\d+)\] (\d+) vínculo", linha)
        if m:
            info["por_indice"][int(m.group(1))] = int(m.group(3))
        if "Fim da coleta" in linha:
            info["concluida"] = True
            info["fim"] = linha[:19]
    return info


def ler_erros(identificadores):
    """Agrupa as mensagens de egressos_erros.txt por identificador."""
    erros = defaultdict(list)
    if not ARQ_ERROS.exists():
        return erros
    por_tamanho = sorted(set(identificadores), key=len, reverse=True)
    for linha in ARQ_ERROS.read_text(encoding="utf-8").splitlines():
        for ident in por_tamanho:
            if linha.startswith(ident + " - "):
                erros[ident].append(linha[len(ident) + 3:].strip())
                break
    return erros


def classificar_vinculos():
    """Aplica as mesmas regras do painel, registrando o motivo de cada exclusão."""
    df = pd.read_csv(ARQ_RESULTADOS, dtype=str)
    municipios = pd.read_csv(ARQ_MUNICIPIOS)
    municipios["nome_norm"] = municipios["nome"].apply(painel.normalizar)
    coords = {(n, int(c)): (la, lo) for n, c, la, lo in
              zip(municipios["nome_norm"], municipios["codigo_uf"], municipios["latitude"], municipios["longitude"])}

    registros = []
    for _, row in df.iterrows():
        municipio, uf, cbo = row.get("municipio"), row.get("uf"), row.get("cbo")
        reg = {"identificador": row["nome"], "municipio": municipio, "uf": uf, "cbo": cbo,
               "motivo": None, "area": None, "lat": None, "lon": None}
        if any(pd.isna(v) or not str(v).strip() for v in (municipio, uf, cbo)):
            reg["motivo"] = MOTIVO_CAMPO_VAZIO
        else:
            uf = str(uf).upper().strip()
            reg["uf"] = uf
            if uf not in painel.MAP_UF_REGIAO:
                reg["motivo"] = MOTIVO_UF
            else:
                norm = painel.normalizar(municipio)
                chave = painel.EQUIVALENCIAS_MUNICIPIOS.get((norm, uf), norm)
                ponto = coords.get((chave, painel.UF_CODIGO[uf]))
                if ponto is None:
                    reg["motivo"] = MOTIVO_MUNICIPIO
                else:
                    reg["lat"], reg["lon"] = ponto
                    reg["area"] = painel.categorizar_cbo(cbo)
                    if reg["area"] is None:
                        reg["motivo"] = MOTIVO_NAO_MEDICO
        registros.append(reg)
    return registros


# === Amostra para conferência manual ===
def preparar_amostra(identificadores, vinculos_por_id, tamanho, nova):
    if ARQ_AMOSTRA.exists() and not nova:
        return False
    unicos = list(dict.fromkeys(identificadores))
    sorteados = random.Random(SEMENTE_AMOSTRA).sample(unicos, min(tamanho, len(unicos)))
    codigos = {ident: f"E{i:03d}" for i, ident in enumerate(unicos, start=1)}
    with open(ARQ_AMOSTRA, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f, delimiter=";")
        w.writerow(["codigo", "identificador", "municipio", "uf", "cbo", "confere_no_cnes (S/N)", "observacao"])
        for ident in sorted(sorteados, key=lambda x: codigos[x]):
            vinculos = vinculos_por_id.get(ident, [])
            if not vinculos:
                w.writerow([codigos[ident], ident, "(nenhum vínculo coletado)", "", "", "", ""])
            for v in vinculos:
                w.writerow([codigos[ident], ident, v["municipio"], v["uf"], v["cbo"], "", ""])
    return True


def ler_conferencia():
    if not ARQ_AMOSTRA.exists():
        return None
    with open(ARQ_AMOSTRA, encoding="utf-8-sig") as f:
        linhas = list(csv.DictReader(f, delimiter=";"))
    respostas = [l["confere_no_cnes (S/N)"].strip().upper() for l in linhas]
    preenchidas = [r for r in respostas if r in ("S", "N")]
    return {"linhas": len(linhas), "egressos": len({l["codigo"] for l in linhas}),
            "preenchidas": len(preenchidas), "conferem": preenchidas.count("S")}


# === Relatório ===
def montar_relatorio(args):
    identificadores = ler_identificadores()
    codigos = {}
    for ident in identificadores:
        codigos.setdefault(ident, f"E{len(codigos) + 1:03d}")
    mostrar = (lambda i: codigos.get(i, "E???")) if args.anonimo else (lambda i: i)

    log = ler_log()
    erros = ler_erros(identificadores)
    registros = classificar_vinculos()

    vinculos_por_id = defaultdict(list)
    for r in registros:
        vinculos_por_id[r["identificador"]].append(r)
    validos = [r for r in registros if r["motivo"] is None]
    validos_por_id = defaultdict(list)
    for r in validos:
        validos_por_id[r["identificador"]].append(r)

    # Conferência cruzada com o próprio gerador do painel
    dados_painel, _, _ = painel.carregar_dados()
    confere_painel = len(dados_painel) == len(validos)

    # === 1. Funil ===
    repetidos = sorted({i for i in identificadores if identificadores.count(i) > 1})
    unicos = list(dict.fromkeys(identificadores))
    com_vinculo = [i for i in unicos if vinculos_por_id.get(i)]
    com_vinculo_valido = [i for i in unicos if validos_por_id.get(i)]
    exclusoes = defaultdict(int)
    for r in registros:
        if r["motivo"]:
            exclusoes[r["motivo"]] += 1
    funil = [
        ("Identificadores na lista (nomes_egressos.txt)", len(identificadores), ""),
        ("Identificadores repetidos na lista", len(repetidos), "alerta" if repetidos else ""),
        ("Identificadores únicos", len(unicos), ""),
        ("Consultas registradas no log (última coleta)", len(log["por_indice"]), "" if len(log["por_indice"]) == len(identificadores) else "alerta"),
        ("Identificadores com ao menos um vínculo coletado", len(com_vinculo), ""),
        ("Vínculos coletados (egressos_resultados.csv)", len(registros), ""),
    ]
    funil += [(f"Excluídos: {motivo}", -n, "") for motivo, n in sorted(exclusoes.items())]
    funil += [
        ("Vínculos no painel", len(validos), ""),
        ("Identificadores com vínculo no painel (\"Localizados no CNES\")", len(com_vinculo_valido), ""),
    ]
    linhas_funil = [[esc(e), f"<strong>{v:+d}</strong>" if v < 0 else f"<strong>{v}</strong>",
                     "<span class='tag alerta'>verificar</span>" if s else ""] for e, v, s in funil]

    # === 2. Coerência entre as fontes ===
    verificacoes = []
    def verif(descricao, ok, detalhe=""):
        verificacoes.append([esc(descricao), "<span class='tag ok'>OK</span>" if ok else "<span class='tag alerta'>Divergência</span>", esc(detalhe)])

    verif("O gerador do painel chega ao mesmo total de vínculos", confere_painel,
          f"painel: {len(dados_painel)} · auditoria: {len(validos)}")
    verif("A última coleta foi concluída", log["concluida"],
          f"início {log['inicio']} · fim {log['fim']}" if log["inicio"] else "scraper.log ausente")
    verif("O log consultou todos os identificadores da lista atual", log["total_declarado"] == len(identificadores),
          f"log: {log['total_declarado']} · lista: {len(identificadores)}")
    soma_log = sum(log["por_indice"].values())
    verif("Total de vínculos do log = linhas do CSV", soma_log == len(registros), f"log: {soma_log} · CSV: {len(registros)}")
    sem_lista = sorted({r["identificador"] for r in registros} - set(identificadores))
    verif("Todo vínculo do CSV pertence a um identificador da lista", not sem_lista,
          f"{len(sem_lista)} fora da lista" if sem_lista else "")
    verif("Nenhum identificador repetido na lista", not repetidos,
          "repetidos: " + ", ".join(mostrar(i) for i in repetidos) if repetidos else "")

    # Contagem por consulta: log x CSV (o índice do log segue a ordem da lista)
    divergentes = []
    if log["total_declarado"] == len(identificadores):
        contagem_csv = defaultdict(int)
        for r in registros:
            contagem_csv[r["identificador"]] += 1
        esperado = defaultdict(int)
        for i, ident in enumerate(identificadores, start=1):
            esperado[ident] += log["por_indice"].get(i, 0)
        divergentes = [i for i in unicos if esperado[i] != contagem_csv[i]]
        verif("Vínculos por identificador: log = CSV", not divergentes,
              f"{len(divergentes)} identificador(es) com contagem diferente" if divergentes else "")

    # Mesmo município e CBO para o mesmo egresso costuma ser outro estabelecimento,
    # que o scraper não registra; por isso é informação, não alerta
    repeticoes = sum(n - 1 for n in pd.Series([(r["identificador"], r["municipio"], r["uf"], r["cbo"]) for r in registros]).value_counts() if n > 1)
    egressos_repeticao = len({r["identificador"] for r in registros
                              if sum(1 for o in vinculos_por_id[r["identificador"]] if (o["municipio"], o["cbo"]) == (r["municipio"], r["cbo"])) > 1})
    verificacoes.append([esc("Vínculos que repetem município e CBO do mesmo egresso"), "<span class='tag info'>Informativo</span>",
                         esc(f"{repeticoes} vínculo(s) em {egressos_repeticao} egresso(s). Em geral são estabelecimentos diferentes "
                             "na mesma cidade, mas o scraper não registra o estabelecimento para confirmar.")])

    # === 3. Identificadores sem vínculo no painel ===
    sem_vinculo = []
    for ident in unicos:
        if validos_por_id.get(ident):
            continue
        msgs = erros.get(ident, [])
        if vinculos_por_id.get(ident):
            motivo = "Vínculos coletados, mas todos excluídos: " + ", ".join(sorted({r["motivo"] for r in vinculos_por_id[ident]}))
            acao = "Revisar exclusão"
        elif any("Botão" in m or "Erro inesperado" in m for m in msgs):
            motivo, acao = "Falha técnica na consulta", "Consultar de novo"
        elif any("Nenhum vínculo" in m for m in msgs):
            motivo, acao = "Cadastro encontrado, sem vínculo ativo válido", "Conferir no CNES"
        else:
            motivo, acao = "Sem resultado na busca do CNES", "Conferir grafia ou usar CPF"
        sem_vinculo.append([esc(mostrar(ident)), esc(motivo), esc(acao)])

    # === 4. Alertas por egresso ===
    alertas = []
    for ident in unicos:
        vs = vinculos_por_id.get(ident, [])
        if not vs:
            continue
        flags = []
        if ident in repetidos:
            flags.append("Repetido na lista (vínculos podem estar duplicados)")
        if len(vs) >= MUITOS_VINCULOS:
            flags.append(f"{len(vs)} vínculos")
        if any(r["motivo"] == MOTIVO_NAO_MEDICO for r in vs):
            flags.append("Ocupação não médica (provável homônimo)")
        pontos = {(r["lat"], r["lon"]) for r in vs if r["lat"] is not None}
        if len(pontos) > 1:
            dist = max(painel.haversine_km(a[0], a[1], b[0], b[1]) for a, b in combinations(pontos, 2))
            if dist > DISTANCIA_ALERTA_KM:
                flags.append(f"Vínculos a {dist:,.0f} km de distância".replace(",", "."))
        if any("(sem acento)" not in m for m in erros.get(ident, [])):
            flags.append("Só encontrado na 2ª tentativa, sem acento")
        if ident in divergentes:
            flags.append("Contagem do log diferente do CSV")
        if flags:
            ufs = sorted({r["uf"] for r in vs if r["uf"]})
            alertas.append((len(flags), [esc(mostrar(ident)), str(len(vs)), esc(", ".join(ufs)),
                                         "<br>".join(esc(f) for f in flags)]))
    alertas.sort(key=lambda x: -x[0])

    # === 5. Distribuição de vínculos por egresso ===
    distribuicao = defaultdict(int)
    for ident in unicos:
        distribuicao[len(validos_por_id.get(ident, []))] += 1
    linhas_dist = [[str(k), str(v), f"<span class='barra' style='width:{v / max(distribuicao.values()) * 100:.0f}%'></span>"]
                   for k, v in sorted(distribuicao.items())]

    # === 6. Exclusões detalhadas ===
    linhas_exclusoes = [[esc(mostrar(r["identificador"])), esc(r["municipio"]), esc(r["uf"]), esc(r["cbo"]), esc(r["motivo"])]
                        for r in registros if r["motivo"]]

    # === 7. Amostra ===
    criada = preparar_amostra(identificadores, vinculos_por_id, args.amostra, args.nova_amostra)
    conf = ler_conferencia()
    if conf and conf["preenchidas"]:
        taxa = conf["conferem"] / conf["preenchidas"] * 100
        texto_amostra = (f"<p><strong>{conf['conferem']} de {conf['preenchidas']}</strong> linhas conferidas batem com o CNES "
                         f"(<strong>{taxa:.1f}%</strong> de concordância). Ainda faltam {conf['linhas'] - conf['preenchidas']} linhas.</p>")
    else:
        texto_amostra = (f"<p>Amostra de {conf['egressos'] if conf else 0} egressos ({conf['linhas'] if conf else 0} linhas) em "
                         f"<code>auditoria/{ARQ_AMOSTRA.name}</code>, ainda não conferida. "
                         + ("Planilha criada agora. " if criada else "")
                         + "Abra a planilha no Excel, consulte cada identificador no site do CNES e preencha a coluna "
                           "<em>confere_no_cnes</em> com S ou N. Depois rode a auditoria de novo para calcular a concordância.</p>")
    texto_amostra += f"<p class='nota'>Sorteio com semente fixa ({SEMENTE_AMOSTRA}): a mesma lista gera sempre a mesma amostra.</p>"

    # === 8. Rastreabilidade ===
    arquivos = [ARQ_NOMES, ARQ_RESULTADOS, ARQ_ERROS, ARQ_LOG, ARQ_MUNICIPIOS]
    linhas_arquivos = [[esc(a.name),
                        datetime.fromtimestamp(a.stat().st_mtime).strftime("%d/%m/%Y %H:%M") if a.exists() else "—",
                        f"<code>{sha256(a)}</code>"] for a in arquivos]

    agora = datetime.now()
    resumo = [
        (len(unicos), "identificadores únicos"),
        (len(com_vinculo_valido), "com vínculo no painel"),
        (len(validos), "vínculos no painel"),
        (sum(1 for v in verificacoes if "Divergência" in v[1]), "divergências entre fontes"),
        (len(alertas), "egressos com alerta"),
    ]
    valores = {
        "titulo": "Auditoria dos dados" + (" (anonimizada)" if args.anonimo else ""),
        "data_hora": agora.strftime("%d/%m/%Y às %H:%M"),
        "aviso": ("Identificadores substituídos por códigos. Ainda assim, município e CBO de cidades pequenas podem permitir "
                  "reidentificação: compartilhe só com quem precisa.") if args.anonimo else
                 ("Este relatório contém identificadores individuais (nomes e CPFs). Uso interno: não publique nem envie ao GitHub. "
                  "Para compartilhar, gere a versão com <code>--anonimo</code>."),
        "resumo": "".join(f"<div class='numero'><strong>{v}</strong><span>{esc(r)}</span></div>" for v, r in resumo),
        "funil": tabela(["Etapa", "Quantidade", ""], linhas_funil),
        "verificacoes": tabela(["Verificação", "Resultado", "Detalhe"], verificacoes),
        "sem_vinculo": tabela(["Identificador", "Situação", "Ação sugerida"], sem_vinculo),
        "alertas": tabela(["Identificador", "Vínculos coletados", "UFs", "Alertas"], [l for _, l in alertas]),
        "distribuicao": tabela(["Vínculos no painel", "Egressos", ""], linhas_dist),
        "exclusoes": tabela(["Identificador", "Município", "UF", "CBO", "Motivo"], linhas_exclusoes),
        "amostra": texto_amostra,
        "arquivos": tabela(["Arquivo", "Modificado em", "SHA-256"], linhas_arquivos),
        "criterios": (f"Muitos vínculos: {MUITOS_VINCULOS} ou mais · distância entre vínculos acima de {DISTANCIA_ALERTA_KM} km · "
                      "as regras de exclusão e de classificação de CBO são as mesmas de <code>dashboard_generator.py</code>."),
        "ano": agora.strftime("%Y"),
    }
    destino = PASTA_SAIDA / ("auditoria_anonima.html" if args.anonimo else "auditoria.html")
    destino.write_text(painel.preencher_template("auditoria.html", **valores), encoding="utf-8")

    print(f"Relatório: auditoria/{destino.name}")
    print(f"  {len(validos)} vínculos no painel · {len(alertas)} egresso(s) com alerta · "
          f"{len(sem_vinculo)} sem vínculo · {resumo[3][0]} divergência(s) entre fontes")
    if criada:
        print(f"Amostra para conferência manual: auditoria/{ARQ_AMOSTRA.name}")
    return 0 if confere_painel else 1


def main():
    parser = argparse.ArgumentParser(description="Auditoria dos dados do Painel de Egressos.")
    parser.add_argument("--anonimo", action="store_true", help="troca os identificadores por códigos (E001...)")
    parser.add_argument("--amostra", type=int, default=TAMANHO_AMOSTRA, help="egressos na amostra de conferência manual")
    parser.add_argument("--nova-amostra", action="store_true", help="sorteia uma amostra nova, sobrescrevendo a planilha")
    args = parser.parse_args()
    for arquivo in (ARQ_NOMES, ARQ_RESULTADOS, ARQ_MUNICIPIOS):
        if not arquivo.exists():
            print(f"Erro: arquivo não encontrado - {arquivo.name}")
            return 1
    PASTA_SAIDA.mkdir(exist_ok=True)
    return montar_relatorio(args)


if __name__ == "__main__":
    sys.exit(main())
