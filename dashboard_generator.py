#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Gera o Painel de Egressos EMCM/UFRN a partir de egressos_resultados.csv.

Saídas: dashboard_final.html, mapa_pins.html, mapa_calor.html,
relatorio_impressao.html e metodologia.html.
"""

import hashlib
import math
import sys
import unicodedata
from datetime import datetime
from pathlib import Path
from string import Template

import folium
import pandas as pd
import plotly.express as px
from folium.plugins import Fullscreen, HeatMap, MiniMap
from plotly.offline import get_plotlyjs_version

PASTA = Path(__file__).resolve().parent
PASTA_TEMPLATES = PASTA / "templates"

# === Parâmetros da análise ===
CENTRO_RAIO = ("CAICO", "RN")  # município normalizado e UF
RAIO_KM = 150
RAIO_TERRA_KM = 6371.0088
DESLOCAMENTO_MAX = 0.009  # graus; deslocamento visual dos pinos no mesmo município

AREAS = ["Atenção Básica", "Especialidades Clínicas", "Especialidades Cirúrgicas", "Médico Residente", "Outras Especialidades"]
CORES_AREA = {
    "Atenção Básica": "#16a085",
    "Especialidades Clínicas": "#2563eb",
    "Especialidades Cirúrgicas": "#7c3aed",
    "Médico Residente": "#f59e0b",
    "Outras Especialidades": "#e11d48",
}
CORES_RECORTE = {"raio": "#f59e0b", "Restante do RN": "#2563eb", "Outros estados": "#64748b"}

MAP_UF_REGIAO = {
    "AC": "Norte", "AP": "Norte", "AM": "Norte", "PA": "Norte", "RO": "Norte", "RR": "Norte", "TO": "Norte",
    "AL": "Nordeste", "BA": "Nordeste", "CE": "Nordeste", "MA": "Nordeste", "PB": "Nordeste", "PE": "Nordeste", "PI": "Nordeste", "RN": "Nordeste", "SE": "Nordeste",
    "DF": "Centro-Oeste", "GO": "Centro-Oeste", "MT": "Centro-Oeste", "MS": "Centro-Oeste",
    "ES": "Sudeste", "MG": "Sudeste", "RJ": "Sudeste", "SP": "Sudeste",
    "PR": "Sul", "SC": "Sul", "RS": "Sul"
}
UF_CODIGO = {
    "RO": 11, "AC": 12, "AM": 13, "RR": 14, "PA": 15, "AP": 16, "TO": 17,
    "MA": 21, "PI": 22, "CE": 23, "RN": 24, "PB": 25, "PE": 26, "AL": 27,
    "SE": 28, "BA": 29, "MG": 31, "ES": 32, "RJ": 33, "SP": 35, "PR": 41,
    "SC": 42, "RS": 43, "MS": 50, "MT": 51, "GO": 52, "DF": 53
}
# Nome do município no CNES -> nome em municipios.csv (IBGE), ambos normalizados
EQUIVALENCIAS_MUNICIPIOS = {
    ("ASSU", "RN"): "ACU",
    ("JANUARIO CICCO", "RN"): "JANUARIO CICCO (BOA SAUDE)",
}


# === Funções auxiliares ===
def remover_acentos(txt):
    if pd.isna(txt):
        return ""
    return "".join(c for c in unicodedata.normalize("NFD", str(txt)) if unicodedata.category(c) != "Mn")


def normalizar(txt):
    return remover_acentos(txt).upper().strip()


def categorizar_cbo(cbo_completo):
    # Classificação operacional usada no painel publicado
    if pd.isna(cbo_completo):
        return "Outras Especialidades"
    cbo_codigo = str(cbo_completo).split(" - ")[0]
    if cbo_codigo.startswith(("225120", "225142", "225125")):
        return "Atenção Básica"
    elif cbo_codigo.startswith(("225135", "225250", "225265", "225112", "225210", "225270")):
        return "Especialidades Clínicas"
    elif cbo_codigo.startswith(("225225", "225285", "225235")):
        return "Especialidades Cirúrgicas"
    elif cbo_codigo.startswith("2231F9") or "RESIDENTE" in str(cbo_completo).upper():
        return "Médico Residente"
    return "Outras Especialidades"


def haversine_km(lat1, lon1, lat2, lon2):
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * RAIO_TERRA_KM * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def deslocamento(chave):
    # Valor fixo em [-DESLOCAMENTO_MAX, DESLOCAMENTO_MAX] para cada chave: o mapa sai igual a cada execução
    h = hashlib.md5(chave.encode("utf-8")).digest()
    dx = int.from_bytes(h[:4], "big") / 0xFFFFFFFF
    dy = int.from_bytes(h[4:8], "big") / 0xFFFFFFFF
    return (dx * 2 - 1) * DESLOCAMENTO_MAX, (dy * 2 - 1) * DESLOCAMENTO_MAX


def pct(parte, total):
    return f"{(parte / total * 100) if total else 0:.1f}%"


def nome_municipio(municipio, uf):
    return f"{str(municipio).title()}/{uf}"


def preencher_template(nome, **valores):
    texto = (PASTA_TEMPLATES / nome).read_text(encoding="utf-8")
    return Template(texto).substitute(**valores)


# === Leitura e preparação dos dados ===
def carregar_dados():
    egressos_df = pd.read_csv(PASTA / "egressos_resultados.csv", dtype=str)
    municipios_df = pd.read_csv(PASTA / "municipios.csv")

    caminho_nomes = PASTA / "nomes_egressos.txt"
    if caminho_nomes.exists():
        with open(caminho_nomes, encoding="utf-8") as f:
            total_lista = len([linha for linha in f if linha.strip()])
    else:
        print("Aviso: nomes_egressos.txt não encontrado; o total da lista será 0.")
        total_lista = 0

    egressos_df["municipio_norm"] = egressos_df["municipio"].apply(normalizar)
    egressos_df["uf"] = egressos_df["uf"].str.upper().str.strip()
    egressos_df["codigo_uf"] = egressos_df["uf"].map(UF_CODIGO)
    # Chave só para o cruzamento; mapa e tabelas continuam com o nome do CNES
    egressos_df["municipio_chave"] = [
        EQUIVALENCIAS_MUNICIPIOS.get((m, uf), m) for m, uf in zip(egressos_df["municipio_norm"], egressos_df["uf"])
    ]
    municipios_df["nome_norm"] = municipios_df["nome"].apply(normalizar)

    dados = pd.merge(
        egressos_df,
        municipios_df[["nome_norm", "codigo_uf", "latitude", "longitude"]],
        how="left",
        left_on=["municipio_chave", "codigo_uf"],
        right_on=["nome_norm", "codigo_uf"],
    )
    sem_coordenada = dados[dados["latitude"].isna()]
    if not sem_coordenada.empty:
        nao_encontrados = sorted({f"{m}/{u}" for m, u in zip(sem_coordenada["municipio_norm"], sem_coordenada["uf"])})
        print(f"Aviso: {len(sem_coordenada)} vínculo(s) sem coordenadas, excluídos: {', '.join(nao_encontrados)}")

    dados = dados.dropna(subset=["municipio", "uf", "cbo", "latitude", "longitude"])
    dados = dados[dados["uf"].isin(MAP_UF_REGIAO.keys())].copy()
    dados["grande_area_cbo"] = dados["cbo"].apply(categorizar_cbo)
    dados["regiao"] = dados["uf"].map(MAP_UF_REGIAO)

    centro = municipios_df[(municipios_df["nome_norm"] == CENTRO_RAIO[0]) & (municipios_df["codigo_uf"] == UF_CODIGO[CENTRO_RAIO[1]])].iloc[0]
    dados["dist_centro_km"] = [haversine_km(centro["latitude"], centro["longitude"], la, lo) for la, lo in zip(dados["latitude"], dados["longitude"])]

    # Deslocamento determinístico dos pinos que compartilham o mesmo município
    dados["ordem_municipio"] = dados.groupby(["municipio_norm", "uf"]).cumcount()
    dados["qtd_municipio"] = dados.groupby(["municipio_norm", "uf"])["municipio"].transform("size")
    lat_pin, lon_pin = [], []
    for _, row in dados.iterrows():
        if row["qtd_municipio"] > 1:
            dlat, dlon = deslocamento(f"{row['municipio_norm']}|{row['uf']}|{row['ordem_municipio']}")
        else:
            dlat, dlon = 0.0, 0.0
        lat_pin.append(row["latitude"] + dlat)
        lon_pin.append(row["longitude"] + dlon)
    dados["lat_pin"], dados["lon_pin"] = lat_pin, lon_pin

    return dados, total_lista, centro


def calcular_indicadores(dados, total_lista, centro):
    no_raio = dados[dados["dist_centro_km"] <= RAIO_KM]
    vinculos_rn = (dados["uf"] == "RN").sum()
    total = len(dados)
    localizados = dados["nome"].nunique()
    return {
        "total_lista": total_lista,
        "localizados": localizados,
        "pct_localizados": pct(localizados, total_lista),
        "vinculos": total,
        "municipios": dados[["municipio_norm", "uf"]].drop_duplicates().shape[0],
        "ocupacoes": dados["cbo"].nunique(),
        "pct_atencao_basica": pct((dados["grande_area_cbo"] == "Atenção Básica").sum(), total),
        "raio_egressos": no_raio["nome"].nunique(),
        "raio_vinculos": len(no_raio),
        "raio_municipios": no_raio[["municipio_norm", "uf"]].drop_duplicates().shape[0],
        # Mantém a fórmula do painel publicado: vínculos no raio (inclusive de outras UFs) sobre os vínculos do RN
        "raio_pct_rn": pct(len(no_raio), vinculos_rn),
        "centro_nome": centro["nome"],
        "centro_uf": CENTRO_RAIO[1],
    }


# === Mapas ===
def camada_esri():
    # Mapa base sem chave de API. O CartoDB passou a exigir chave e o OpenStreetMap
    # bloqueia páginas abertas direto do disco, por isso ficou só a Esri.
    return folium.TileLayer(
        tiles="https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Light_Gray_Base/MapServer/tile/{z}/{y}/{x}",
        attr="Tiles &copy; Esri &mdash; Esri, DeLorme, NAVTEQ",
        name="Cinza claro (Esri)",
        max_zoom=16,
        control=False,
    )


def criar_mapa_base():
    mapa = folium.Map(location=[-14.2, -51.9], zoom_start=4, tiles=None, control_scale=True)
    camada_esri().add_to(mapa)
    Fullscreen(position="topright").add_to(mapa)
    return mapa


def adicionar_raio(mapa, centro, preenchido):
    folium.Circle(
        location=[centro["latitude"], centro["longitude"]],
        radius=RAIO_KM * 1000,
        color="#f59e0b",
        weight=3,
        fill=preenchido,
        fill_color="#fbbf24" if preenchido else "#f59e0b",
        fill_opacity=0.08 if preenchido else 0.2,
        tooltip=f"Raio de {RAIO_KM} km a partir de {centro['nome']}/{CENTRO_RAIO[1]}",
    ).add_to(mapa)


def gerar_mapa_pins(dados, centro):
    mapa = criar_mapa_base()
    MiniMap(tile_layer=camada_esri(), position="bottomright", toggle_display=True, minimized=True, zoom_level_offset=-5).add_to(mapa)
    adicionar_raio(mapa, centro, preenchido=True)
    folium.Marker(
        location=[centro["latitude"], centro["longitude"]],
        tooltip=f"{centro['nome']}/{CENTRO_RAIO[1]} - centro do raio",
        icon=folium.Icon(color="orange", icon="star"),
    ).add_to(mapa)

    for area in AREAS:
        dados_area = dados[dados["grande_area_cbo"] == area]
        if dados_area.empty:
            continue
        cor = CORES_AREA[area]
        grupo = folium.FeatureGroup(name=f"{area} ({len(dados_area)})")
        for _, row in dados_area.iterrows():
            popup_html = (
                f"<div style='font-family:Arial;min-width:220px'><strong>{nome_municipio(row['municipio'], row['uf'])}</strong>"
                f"<br><span>{row['cbo']}</span><br><small style='color:{cor}'>{area}</small></div>"
            )
            folium.CircleMarker(
                location=[row["lat_pin"], row["lon_pin"]],
                radius=5.5,
                color="#ffffff",
                weight=1,
                fill=True,
                fill_color=cor,
                fill_opacity=0.88,
                popup=folium.Popup(popup_html, max_width=320),
                tooltip=f"{row['municipio_norm']}/{row['uf']} · {area}",
            ).add_to(grupo)
        grupo.add_to(mapa)

    itens_legenda = "".join(
        f"<div style='margin:5px 0'><span style='display:inline-block;width:9px;height:9px;border-radius:50%;"
        f"background:{CORES_AREA[area]};margin-right:7px'></span>{area}</div>"
        for area in AREAS
    )
    legenda = f"""
    <div style="position:fixed;left:18px;bottom:28px;z-index:9999;background:#fff;
    padding:12px 14px;border-radius:12px;box-shadow:0 8px 24px rgba(15,23,42,.18);
    font:12px Arial;color:#334155"><strong style="display:block;margin-bottom:8px">
    Áreas de atuação</strong>
    {itens_legenda}
    <div style="margin-top:8px;color:#94a3b8;font-size:11px">Pinos dispersos para evidenciar o volume.</div></div>
    """
    mapa.get_root().html.add_child(folium.Element(legenda))
    folium.LayerControl(position="topright", collapsed=False).add_to(mapa)
    mapa.save(PASTA / "mapa_pins.html")


def gerar_mapa_calor(dados, centro):
    mapa = criar_mapa_base()
    HeatMap(
        dados[["lat_pin", "lon_pin"]].values.tolist(),
        min_opacity=0.25, max_zoom=13, radius=24, blur=19,
    ).add_to(mapa)
    adicionar_raio(mapa, centro, preenchido=False)
    mapa.save(PASTA / "mapa_calor.html")


# === Gráficos ===
def estilizar_grafico(fig, titulo, altura=400):
    fig.update_layout(
        title=dict(text=titulo, font=dict(size=18, color="#0f172a"), x=0.03),
        height=altura,
        margin=dict(t=56, b=28, l=28, r=24),
        font=dict(family="Inter, Arial, sans-serif", color="#475569"),
        hoverlabel=dict(bgcolor="#0f172a", font=dict(color="white")),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        xaxis_title=None,
        yaxis_title=None,
    )
    if fig.data and fig.data[0].type == "bar":
        fig.update_traces(cliponaxis=False)  # não corta o rótulo da maior barra
    return fig


def grafico_html(fig):
    return fig.to_html(include_plotlyjs=False, full_html=False, config={"displayModeBar": False, "responsive": True})


def gerar_graficos(dados, centro):
    graficos = {}

    uf_counts = dados["uf"].value_counts().reset_index()
    uf_counts.columns = ["uf", "quantidade"]
    fig = px.bar(uf_counts, x="uf", y="quantidade", color="quantidade",
                 color_continuous_scale=["#bfdbfe", "#1d4ed8"], labels={"quantidade": "Vínculos"})
    fig.update_traces(texttemplate="%{y}", textposition="outside", hovertemplate="<b>%{x}</b><br>%{y} vínculos<extra></extra>")
    fig.update_layout(coloraxis_showscale=False)
    graficos["grafico_uf"] = grafico_html(estilizar_grafico(fig, "Distribuição por estado"))

    cbo_counts = dados["cbo"].value_counts().nlargest(10).reset_index()
    cbo_counts.columns = ["cbo", "quantidade"]
    cbo_counts = cbo_counts.sort_values("quantidade")
    cbo_counts["cbo_curto"] = cbo_counts["cbo"].str.slice(0, 42)
    fig = px.bar(cbo_counts, x="quantidade", y="cbo_curto", orientation="h", custom_data=["cbo"])
    fig.update_traces(marker_color="#f59e0b", texttemplate="%{x}", textposition="outside",
                      hovertemplate="<b>%{customdata[0]}</b><br>%{x} vínculos<extra></extra>")
    graficos["grafico_cbo"] = grafico_html(estilizar_grafico(fig, "10 ocupações mais frequentes", altura=430))

    regiao_counts = dados["regiao"].value_counts().reset_index()
    regiao_counts.columns = ["regiao", "quantidade"]
    fig = px.pie(regiao_counts, names="regiao", values="quantidade", hole=0.58,
                 color_discrete_sequence=["#2563eb", "#16a085", "#f59e0b", "#7c3aed", "#e11d48"])
    fig.update_traces(textinfo="percent+label", hovertemplate="<b>%{label}</b><br>%{value} vínculos<extra></extra>")
    graficos["grafico_regiao"] = grafico_html(estilizar_grafico(fig, "Presença por região"))

    area_counts = dados["grande_area_cbo"].value_counts().reset_index()
    area_counts.columns = ["area", "quantidade"]
    fig = px.bar(area_counts, x="area", y="quantidade", color="area", color_discrete_map=CORES_AREA, labels={"area": "Área"})
    fig.update_traces(texttemplate="%{y}", textposition="outside", hovertemplate="<b>%{x}</b><br>%{y} vínculos<extra></extra>")
    fig.update_layout(showlegend=False)
    graficos["grafico_area"] = grafico_html(estilizar_grafico(fig, "Vínculos por área de atuação"))

    rotulo_raio = f"Até {RAIO_KM} km de {centro['nome']}"
    recorte = pd.Series(
        [rotulo_raio if d <= RAIO_KM else ("Restante do RN" if uf == "RN" else "Outros estados")
         for d, uf in zip(dados["dist_centro_km"], dados["uf"])]
    )
    ordem = [rotulo_raio, "Restante do RN", "Outros estados"]
    recorte_counts = recorte.value_counts().reindex(ordem, fill_value=0).reset_index()
    recorte_counts.columns = ["recorte", "quantidade"]
    cores = {rotulo_raio: CORES_RECORTE["raio"], "Restante do RN": CORES_RECORTE["Restante do RN"], "Outros estados": CORES_RECORTE["Outros estados"]}
    fig = px.bar(recorte_counts, x="recorte", y="quantidade", color="recorte", color_discrete_map=cores,
                 category_orders={"recorte": ordem}, labels={"recorte": "Recorte"})
    fig.update_traces(texttemplate="%{y}", textposition="outside", hovertemplate="<b>%{x}</b><br>%{y} vínculos<extra></extra>")
    fig.update_layout(showlegend=False)
    graficos["grafico_raio"] = grafico_html(estilizar_grafico(fig, f"Comparativo territorial: raio de {RAIO_KM} km de {centro['nome']}"))

    return graficos


# === Páginas HTML ===
def tabela_html(cabecalho, linhas):
    corpo = "".join(f"<tr><td>{a}</td><td>{b}</td></tr>" for a, b in linhas)
    return f"<table><thead><tr><th>{cabecalho}</th><th>Vínculos</th></tr></thead><tbody>{corpo}</tbody></table>"


def gerar_paginas(dados, ind, graficos):
    agora = datetime.now()
    comuns = {
        "plotly_js": f"https://cdn.plot.ly/plotly-{get_plotlyjs_version()}.min.js",
        "data_geracao": agora.strftime("%d/%m/%Y"),
        "data_hora_geracao": agora.strftime("%d/%m/%Y às %H:%M"),
        "ano": agora.strftime("%Y"),
        "centro_nome": ind["centro_nome"],
        "centro_uf": ind["centro_uf"],
        "raio_km": RAIO_KM,
    }

    metricas = [
        ("Egressos na lista", ind["total_lista"], "Base consultada"),
        ("Localizados no CNES", ind["localizados"], f"{ind['pct_localizados']} da lista"),
        ("Vínculos ativos", ind["vinculos"], "Registros geolocalizados"),
        ("Municípios", ind["municipios"], "Com presença de egressos"),
        ("Ocupações distintas", ind["ocupacoes"], "Códigos CBO encontrados"),
        ("Atenção básica", ind["pct_atencao_basica"], "Dos vínculos identificados"),
    ]
    metricas_raio = [
        (ind["raio_egressos"], "Egressos únicos"),
        (ind["raio_vinculos"], "Vínculos no raio"),
        (ind["raio_municipios"], "Municípios alcançados"),
        (ind["raio_pct_rn"], "Dos vínculos no RN"),
    ]

    dashboard = preencher_template(
        "dashboard.html", **comuns, **graficos,
        metricas="".join(f"<article class='metric'><p>{r}</p><strong>{v}</strong><span>{d}</span></article>" for r, v, d in metricas),
        metricas_raio="".join(f"<article class='regional-metric'><strong>{v}</strong><span>{r}</span></article>" for v, r in metricas_raio),
    )
    (PASTA / "dashboard_final.html").write_text(dashboard, encoding="utf-8")

    metricas_relatorio = [
        (ind["total_lista"], "Egressos na lista"),
        (ind["localizados"], f"Localizados no CNES ({ind['pct_localizados']})"),
        (ind["vinculos"], "Vínculos geolocalizados"),
        (ind["municipios"], "Municípios com presença"),
        (ind["ocupacoes"], "Ocupações distintas"),
        (ind["pct_atencao_basica"], "Vínculos na Atenção Básica"),
    ]
    top_ufs = dados["uf"].value_counts().head(5)
    top_municipios = dados.groupby(["municipio_norm", "uf"]).agg(municipio=("municipio", "first"), quantidade=("cbo", "size"))
    top_municipios = top_municipios.sort_values("quantidade", ascending=False, kind="stable").head(8)
    relatorio = preencher_template(
        "relatorio_impressao.html", **comuns, **graficos,
        metricas="".join(f"<div class=\"metric\"><strong>{v}</strong><span>{r}</span></div>" for v, r in metricas_relatorio),
        metricas_raio="".join(f"<div><strong>{v}</strong><span>{r}</span></div>" for v, r in metricas_raio),
        tabela_ufs=tabela_html("UF", top_ufs.items()),
        tabela_municipios=tabela_html("Município", [(nome_municipio(r["municipio"], uf), r["quantidade"]) for (_, uf), r in top_municipios.iterrows()]),
    )
    (PASTA / "relatorio_impressao.html").write_text(relatorio, encoding="utf-8")

    numeros = [
        (ind["total_lista"], "registros na lista de consulta"),
        (ind["localizados"], "egressos localizados"),
        (ind["vinculos"], "vínculos geolocalizados"),
        (ind["municipios"], "municípios representados"),
    ]
    metodologia = preencher_template(
        "metodologia.html", **comuns,
        numeros="".join(f"<div class=\"number\"><strong>{v}</strong><span>{r}</span></div>" for v, r in numeros),
    )
    (PASTA / "metodologia.html").write_text(metodologia, encoding="utf-8")


def main():
    print("Lendo arquivos de dados...")
    try:
        dados, total_lista, centro = carregar_dados()
    except FileNotFoundError as e:
        print(f"Erro: arquivo não encontrado - {e.filename}")
        return 1

    if dados.empty:
        print("Erro: nenhum vínculo válido após o cruzamento com municipios.csv. Painel não gerado.")
        return 1

    print(f"Vínculos válidos após limpeza e cruzamento: {len(dados)}")
    indicadores = calcular_indicadores(dados, total_lista, centro)

    print("Gerando mapas...")
    gerar_mapa_pins(dados, centro)
    gerar_mapa_calor(dados, centro)

    print("Gerando gráficos e páginas...")
    graficos = gerar_graficos(dados, centro)
    gerar_paginas(dados, indicadores, graficos)

    print("Painel gerado: dashboard_final.html, relatorio_impressao.html, metodologia.html, mapa_pins.html, mapa_calor.html")
    return 0


if __name__ == "__main__":
    sys.exit(main())
