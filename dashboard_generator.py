#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import pandas as pd
import folium
from folium.plugins import HeatMap # Importado para o mapa de calor
import unicodedata
from branca.element import Template, MacroElement
from folium import Element
import plotly.express as px
from pathlib import Path
import json
import random

# === Funções Auxiliares ===
def remover_acentos(txt):
    if pd.isna(txt):
        return ""
    return "".join(c for c in unicodedata.normalize("NFD", str(txt)) if unicodedata.category(c) != "Mn")

def categorizar_cbo(cbo_completo):
    if pd.isna(cbo_completo):
        return "Outras"
    cbo_codigo = str(cbo_completo).split(" - ")[0]
    if cbo_codigo.startswith("225120") or cbo_codigo.startswith("225142") or cbo_codigo.startswith("225125"):
        return "Atenção Básica"
    elif cbo_codigo.startswith("225135") or cbo_codigo.startswith("225250") or cbo_codigo.startswith("225265") or cbo_codigo.startswith("225112") or cbo_codigo.startswith("225210") or cbo_codigo.startswith("225270") : # Psiquiatra, GO, Pediatra, Cancerologista Clínico, Dermatologista, Infectologista
        return "Especialidades Clínicas"
    elif cbo_codigo.startswith("225225") or cbo_codigo.startswith("225285") or cbo_codigo.startswith("225235"): # Cirurgião Geral, Urologista, Cirurgião Plástico
        return "Especialidades Cirúrgicas"
    elif cbo_codigo.startswith("2231F9") or "RESIDENTE" in str(cbo_completo).upper():
        return "Médico Residente"
    else:
        return "Outras Especialidades"

map_uf_to_regiao = {
    "AC": "Norte", "AP": "Norte", "AM": "Norte", "PA": "Norte", "RO": "Norte", "RR": "Norte", "TO": "Norte",
    "AL": "Nordeste", "BA": "Nordeste", "CE": "Nordeste", "MA": "Nordeste", "PB": "Nordeste", "PE": "Nordeste", "PI": "Nordeste", "RN": "Nordeste", "SE": "Nordeste",
    "DF": "Centro-Oeste", "GO": "Centro-Oeste", "MT": "Centro-Oeste", "MS": "Centro-Oeste",
    "ES": "Sudeste", "MG": "Sudeste", "RJ": "Sudeste", "SP": "Sudeste",
    "PR": "Sul", "SC": "Sul", "RS": "Sul"
}

# === Leitura e Preparação dos Dados ===
print("Lendo arquivos de dados...")
try:
    egressos_df = pd.read_csv("egressos_resultados.csv")
    municipios_df = pd.read_csv("municipios.csv")
    with open("nomes_egressos.txt", "r", encoding="utf-8") as f_nomes:
        total_egressos_lista_original = len([line for line in f_nomes if line.strip()])
except FileNotFoundError as e:
    print(f"Erro: Arquivo não encontrado - {e}. Certifique-se que os arquivos CSV e TXT estão no mesmo diretório.")
    total_egressos_lista_original = 0
    if "egressos_resultados.csv" in str(e) or "municipios.csv" in str(e):
        exit()

print("Processando dados dos egressos...")
egressos_df["municipio_norm"] = egressos_df["municipio"].str.upper().str.strip().apply(remover_acentos)
municipios_df["nome_norm"] = municipios_df["nome"].str.upper().str.strip().apply(remover_acentos)

uf_to_codigo = {
    "RO": 11, "AC": 12, "AM": 13, "RR": 14, "PA": 15, "AP": 16, "TO": 17,
    "MA": 21, "PI": 22, "CE": 23, "RN": 24, "PB": 25, "PE": 26, "AL": 27,
    "SE": 28, "BA": 29, "MG": 31, "ES": 32, "RJ": 33, "SP": 35, "PR": 41,
    "SC": 42, "RS": 43, "MS": 50, "MT": 51, "GO": 52, "DF": 53
}
egressos_df["codigo_uf"] = egressos_df["uf"].map(uf_to_codigo)

dados_completos = pd.merge(
    egressos_df,
    municipios_df,
    how="left",
    left_on=["municipio_norm", "codigo_uf"],
    right_on=["nome_norm", "codigo_uf"]
)

dados_validos = dados_completos.dropna(subset=["latitude", "longitude", "uf"])
dados_validos = dados_validos[dados_validos["uf"].isin(map_uf_to_regiao.keys())].copy()

dados_validos.loc[:, "grande_area_cbo"] = dados_validos["cbo"].apply(categorizar_cbo)
dados_validos.loc[:, "regiao"] = dados_validos["uf"].map(map_uf_to_regiao)

print(f"Total de vínculos válidos após limpeza e merge: {len(dados_validos)}")

kpis = {
    "total_egressos_lista_original": total_egressos_lista_original,
    "total_vinculos": 0,
    "total_municipios_unicos": 0,
    "total_cbos_distintos": 0,
    "cbo_mais_frequente": "N/A",
    "percentual_atencao_basica": 0,
    "media_vinculos_por_municipio": 0,
    "top_3_ufs": "N/A",
    "vinculos_por_regiao": {}
}

if dados_validos.empty:
    print("Nenhum dado válido encontrado após o processamento.")
    Path("mapa_pins.html").write_text("<h1>Nenhum dado para exibir no mapa de pins.</h1>", encoding="utf-8")
    Path("mapa_calor.html").write_text("<h1>Nenhum dado para exibir no mapa de calor.</h1>", encoding="utf-8")
    Path("grafico_uf_novo.html").write_text("<h1>Nenhum dado para exibir.</h1>", encoding="utf-8")
    Path("grafico_cbo_novo.html").write_text("<h1>Nenhum dado para exibir.</h1>", encoding="utf-8")
    Path("grafico_regiao_novo.html").write_text("<h1>Nenhum dado para exibir.</h1>", encoding="utf-8")
    Path("grafico_grande_area_novo.html").write_text("<h1>Nenhum dado para exibir.</h1>", encoding="utf-8")
else:
    print("Calculando KPIs...")
    total_vinculos = len(dados_validos)
    total_municipios_unicos = dados_validos[["municipio_norm", "uf"]].drop_duplicates().shape[0]
    total_cbos_distintos = dados_validos["cbo"].nunique()
    cbo_mais_frequente_serie = dados_validos["cbo"].mode()
    cbo_mais_frequente = cbo_mais_frequente_serie[0] if not cbo_mais_frequente_serie.empty else "N/A"
    vinculos_atencao_basica = dados_validos[dados_validos["grande_area_cbo"] == "Atenção Básica"].shape[0]
    percentual_atencao_basica = (vinculos_atencao_basica / total_vinculos) * 100 if total_vinculos > 0 else 0
    media_vinculos_por_municipio = total_vinculos / total_municipios_unicos if total_municipios_unicos > 0 else 0
    top_ufs_serie = dados_validos["uf"].value_counts().nlargest(3)
    top_3_ufs = ", ".join([f"{idx} ({val})" for idx, val in top_ufs_serie.items()]) if not top_ufs_serie.empty else "N/A"
    vinculos_por_regiao = dados_validos["regiao"].value_counts().to_dict()

    kpis.update({
        "total_vinculos": total_vinculos,
        "total_municipios_unicos": total_municipios_unicos,
        "total_cbos_distintos": total_cbos_distintos,
        "cbo_mais_frequente": cbo_mais_frequente,
        "percentual_atencao_basica": round(percentual_atencao_basica, 2),
        "media_vinculos_por_municipio": round(media_vinculos_por_municipio, 2),
        "top_3_ufs": top_3_ufs,
        "vinculos_por_regiao": vinculos_por_regiao
    })
    print(f"KPIs calculados: {kpis}")

    # Cores para Plotly e Legenda HTML (mantendo consistência visual)
    cores_hex_grande_area = {
        "Atenção Básica": "#28a745", # Verde
        "Especialidades Clínicas": "#007bff", # Azul
        "Especialidades Cirúrgicas": "#6f42c1", # Roxo
        "Médico Residente": "#fd7e14", # Laranja
        "Outras Especialidades": "#dc3545", # Vermelho
        "Outras": "#6c757d" # Cinza
    }
    # Mapeamento para cores suportadas pelo Folium Icon
    cores_folium_grande_area = {
        "Atenção Básica": "green",
        "Especialidades Clínicas": "blue",
        "Especialidades Cirúrgicas": "purple",
        "Médico Residente": "orange",
        "Outras Especialidades": "red",
        "Outras": "gray"
    }

    # === Criação do Mapa de Pins ===
    print("Gerando mapa interativo com pinos individuais...")
    mapa_pins = folium.Map(location=[-14.235, -51.9253], zoom_start=4, tiles="CartoDB positron")
    offset_magnitude = 0.008

    for _, row in dados_validos.iterrows():
        original_lat = row["latitude"]
        original_lon = row["longitude"]
        offset_lat = random.uniform(-offset_magnitude, offset_magnitude)
        offset_lon = random.uniform(-offset_magnitude, offset_magnitude)
        marker_lat = original_lat + offset_lat
        marker_lon = original_lon + offset_lon

        area_atuacao = row["grande_area_cbo"]
        cor_hex_legenda = cores_hex_grande_area.get(area_atuacao, cores_hex_grande_area["Outras"])
        cor_folium_icon = cores_folium_grande_area.get(area_atuacao, cores_folium_grande_area["Outras"])

        popup_html = f"<div style='font-family: Arial, sans-serif; font-size: 13px; max-width: 250px;'>"
        popup_html += f"<b>Município:</b> {row['municipio'].title()}/{row['uf']}<br>"
        popup_html += f"<b>CBO:</b> {row['cbo']}<br>"
        popup_html += f"<b>Área:</b> <span style='color:{cor_hex_legenda}; font-weight:bold;'>{area_atuacao}</span>"
        popup_html += "</div>"

        folium.Marker(
            location=[marker_lat, marker_lon],
            popup=folium.Popup(popup_html, max_width=300),
            icon=folium.Icon(color=cor_folium_icon, icon="circle", prefix="fa")
        ).add_to(mapa_pins)

    legenda_html_pins = """
    <div style="position: fixed; bottom: 20px; left: 20px; width: auto; height: auto; 
         background-color: rgba(255,255,255,0.9); border:1px solid #ccc; z-index:9999; font-size:12px;
         padding: 10px; border-radius: 5px; box-shadow: 0 2px 5px rgba(0,0,0,0.1); max-width: 250px;">
         <h4 style='margin-top:0; margin-bottom:5px; font-size:14px;'>Legenda - Áreas de Atuação</h4>
         <hr style='margin-top:2px; margin-bottom:8px;'>"""
    areas_presentes = dados_validos["grande_area_cbo"].unique()
    for area, cor_legenda_hex in cores_hex_grande_area.items():
        if area != "Outras" and area in areas_presentes:
                legenda_html_pins += f"<i class='fa fa-circle' style='color:{cor_legenda_hex}; margin-right: 5px;'></i> {area}<br>"
    if "Outras" in areas_presentes:
         legenda_html_pins += f"<i class='fa fa-circle' style='color:{cores_hex_grande_area['Outras']}; margin-right: 5px;'></i> Outras<br>"
    legenda_html_pins += "</div>"
    mapa_pins.get_root().html.add_child(Element(legenda_html_pins))
    folium.LayerControl(collapsed=False).add_to(mapa_pins) 
    mapa_pins.save("mapa_pins.html")
    print("Mapa de pins salvo em mapa_pins.html")

    # === Criação do Mapa de Calor ===
    print("Gerando mapa de calor...")
    mapa_calor = folium.Map(location=[-14.235, -51.9253], zoom_start=4, tiles="CartoDB positron")
    
    dados_heatmap = dados_validos[['latitude', 'longitude']].values.tolist()
    
    if dados_heatmap: 
        heatmap_layer = HeatMap(
            dados_heatmap,
            name="Mapa de Calor dos Egressos", 
            min_opacity=0.25, 
            radius=25,       
            blur=20,         
            max_zoom=13,     
            scale_radius=False 
        )
        heatmap_layer.add_to(mapa_calor)
        folium.LayerControl(collapsed=False).add_to(mapa_calor) 

    mapa_calor.save("mapa_calor.html")
    print("Mapa de calor salvo em mapa_calor.html")

    # === Geração de Gráficos (Plotly) ===
    print("Gerando gráficos...")
    plotly_template = "plotly_white"
    
    # Paletas de cores para os gráficos
    cor_grafico_uf = '#0056b3' 
    cor_grafico_cbo = '#fd7e14' 
    palette_regiao = px.colors.qualitative.Vivid 

    # Configurações de fonte padrão para os gráficos
    font_config = dict(family="Open Sans, sans-serif", size=11, color="var(--cor-texto)")
    title_font_config = dict(family="Roboto, sans-serif", size=16, color="var(--cor-primaria)")

    # Gráfico de UF
    uf_counts = dados_validos["uf"].value_counts().reset_index()
    uf_counts.columns = ["uf", "quantidade"]
    fig_uf = px.bar(uf_counts, x="uf", y="quantidade", 
                    title="Distribuição de Vínculos por UF", 
                    labels={"uf":"UF", "quantidade":"Nº de Vínculos"}, 
                    template=plotly_template,
                    text_auto=True) 
    fig_uf.update_traces(marker_color=cor_grafico_uf, textposition='outside', hovertemplate="<b>UF:</b> %{x}<br><b>Vínculos:</b> %{y}<extra></extra>")
    fig_uf.update_layout(
        title_x=0.5, title_font=title_font_config,
        xaxis_title=None, yaxis_title="Nº de Vínculos",
        plot_bgcolor='rgba(0,0,0,0)', paper_bgcolor='rgba(0,0,0,0)',
        font=font_config,
        margin=dict(t=50, b=20, l=20, r=20)
    )
    fig_uf.write_html("grafico_uf_novo.html", include_plotlyjs="cdn", full_html=False)

    # Gráfico de CBO
    cbo_counts = dados_validos["cbo"].value_counts().nlargest(10).reset_index()
    cbo_counts.columns = ["cbo", "quantidade"]
    cbo_counts["cbo_display"] = cbo_counts["cbo"].apply(lambda x: (x[:35] + '...') if len(x) > 38 else x)
    fig_cbo = px.bar(cbo_counts.sort_values(by="quantidade", ascending=True), 
                     y="cbo_display", x="quantidade", 
                     title="Top 10 CBOs mais Frequentes", orientation="h", 
                     labels={"cbo_display":"CBO", "quantidade":"Nº de Vínculos"}, 
                     template=plotly_template,
                     text_auto=True)
    fig_cbo.update_traces(marker_color=cor_grafico_cbo, textposition='outside', 
                          customdata=cbo_counts['cbo'],
                          hovertemplate="<b>CBO:</b> %{customdata}<br><b>Vínculos:</b> %{x}<extra></extra>")
    fig_cbo.update_layout(
        title_x=0.5, title_font=title_font_config,
        yaxis={"categoryorder":"total ascending", "title": None, "tickfont": {"size": 10}}, 
        xaxis_title="Nº de Vínculos",
        plot_bgcolor='rgba(0,0,0,0)', paper_bgcolor='rgba(0,0,0,0)',
        font=font_config,
        margin=dict(t=50, b=20, l=5, r=20)
    )
    fig_cbo.write_html("grafico_cbo_novo.html", include_plotlyjs="cdn", full_html=False)

    # Gráfico de Região (Donut)
    regiao_counts = dados_validos["regiao"].value_counts().reset_index()
    regiao_counts.columns = ["regiao", "quantidade"]
    fig_regiao = px.pie(regiao_counts, names="regiao", values="quantidade", 
                        title="Distribuição de Vínculos por Região", 
                        template=plotly_template, 
                        color_discrete_sequence=palette_regiao, 
                        hole=0.45) 
    fig_regiao.update_traces(
        textposition='inside', 
        textinfo='percent+label', 
        insidetextorientation='radial',
        hovertemplate="<b>Região:</b> %{label}<br><b>Vínculos:</b> %{value} (%{percent})<extra></extra>",
        textfont_size=11
    )
    fig_regiao.update_layout(
        title_x=0.5, title_font=title_font_config,
        plot_bgcolor='rgba(0,0,0,0)', paper_bgcolor='rgba(0,0,0,0)',
        font=font_config,
        legend_title_text='Regiões',
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="center", x=0.5, font=dict(size=10)),
        margin=dict(t=80, b=20, l=20, r=20) 
    )
    fig_regiao.write_html("grafico_regiao_novo.html", include_plotlyjs="cdn", full_html=False)

    # Gráfico de Grande Área (consistente com cores do mapa)
    grande_area_counts = dados_validos["grande_area_cbo"].value_counts().reset_index()
    grande_area_counts.columns = ["grande_area_cbo", "quantidade"]
    fig_grande_area = px.bar(grande_area_counts, x="grande_area_cbo", y="quantidade", 
                             title="Vínculos por Grande Área de Atuação", 
                             labels={"grande_area_cbo":"Grande Área de Atuação", "quantidade":"Nº de Vínculos"},
                             color="grande_area_cbo", color_discrete_map=cores_hex_grande_area, 
                             template=plotly_template,
                             text_auto=True)
    fig_grande_area.update_layout(
        title_x=0.5, title_font=title_font_config,
        xaxis_title=None, yaxis_title="Nº de Vínculos",
        plot_bgcolor='rgba(0,0,0,0)', paper_bgcolor='rgba(0,0,0,0)',
        font=font_config,
        margin=dict(t=50, b=20, l=20, r=20),
        showlegend=False 
    )
    fig_grande_area.update_traces(textposition='outside', hovertemplate="<b>Área:</b> %{x}<br><b>Vínculos:</b> %{y}<extra></extra>")
    fig_grande_area.write_html("grafico_grande_area_novo.html", include_plotlyjs="cdn", full_html=False)
    print("Gráficos salvos.")

# === Geração do HTML do Dashboard ===
print("Gerando HTML do dashboard...")

if dados_validos.empty:
    mapa_inicial_src = "" 
else:
    mapa_inicial_src = "mapa_pins.html"

try: grafico_uf_content = Path("grafico_uf_novo.html").read_text(encoding="utf-8")
except FileNotFoundError: grafico_uf_content = "<p class='text-danger'>Erro ao carregar gráfico UF.</p>"
try: grafico_cbo_content = Path("grafico_cbo_novo.html").read_text(encoding="utf-8")
except FileNotFoundError: grafico_cbo_content = "<p class='text-danger'>Erro ao carregar gráfico CBO.</p>"
try: grafico_regiao_content = Path("grafico_regiao_novo.html").read_text(encoding="utf-8")
except FileNotFoundError: grafico_regiao_content = "<p class='text-danger'>Erro ao carregar gráfico Região.</p>"
try: grafico_grande_area_content = Path("grafico_grande_area_novo.html").read_text(encoding="utf-8")
except FileNotFoundError: grafico_grande_area_content = "<p class='text-danger'>Erro ao carregar gráfico Grande Área.</p>"

vinculos_por_regiao_html = "<ul class='list-unstyled mb-0'>"
if kpis.get("vinculos_por_regiao"):
    for reg, val in sorted(kpis["vinculos_por_regiao"].items(), key=lambda item: item[1], reverse=True):
        vinculos_por_regiao_html += f"<li><strong>{reg}:</strong> {val}</li>"
else:
    vinculos_por_regiao_html += "<li>N/A</li>"
vinculos_por_regiao_html += "</ul>"

dashboard_html_content = f"""
<!DOCTYPE html>
<html lang="pt-BR">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Dashboard de Egressos da EMCM</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.2/dist/css/bootstrap.min.css" rel="stylesheet">
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Roboto:wght@300;400;500;700&family=Open+Sans:wght@400;600;700&display=swap" rel="stylesheet">
    <style>
        :root {{
            --cor-primaria: #004080;
            --cor-secundaria: #0056b3;
            --cor-destaque: #fd7e14; 
            --cor-texto: #343a40;
            --cor-texto-secundario: #5a6268; /* Cor para texto de parágrafo e itens de lista */
            --cor-fundo-card: #ffffff;
            --cor-fundo-body: #eef1f5;
            --fonte-principal: 'Open Sans', sans-serif;
            --fonte-titulos: 'Roboto', sans-serif;
            --cor-cabecalho-fundo: #f0f8ff; /* Azul Alice - bem claro */
            --cor-cabecalho-texto: var(--cor-primaria);
            --cor-cabecalho-borda-inferior: var(--cor-secundaria);
        }}
        body {{ font-family: var(--fonte-principal); background-color: var(--cor-fundo-body); color: var(--cor-texto); line-height: 1.6; }}
        .header {{ 
            background-color: var(--cor-cabecalho-fundo); 
            color: var(--cor-cabecalho-texto); 
            padding: 20px 0; 
            margin-bottom: 30px; 
            text-align: center; 
            border-bottom: 4px solid var(--cor-cabecalho-borda-inferior); 
            box-shadow: 0 2px 8px rgba(0, 0, 0, 0.08); 
        }}
        .header-content {{ display: flex; align-items: center; justify-content: center; flex-wrap: wrap; }}
        .header-logos img {{ 
            max-height: 70px; 
            margin: 0 15px;
        }}
        .header-title-block {{ text-align: center; flex-grow: 1; }}
        .header h1 {{ margin: 0; font-size: 2.1em; font-weight: 700; font-family: var(--fonte-titulos); color: var(--cor-primaria); }}
        .header p {{ margin: 5px 0 0; font-size: 0.9em; opacity: 0.9; color: var(--cor-texto);}}
        
        .kpi-card {{ 
            background-color: var(--cor-fundo-card); 
            border-radius: 12px; 
            box-shadow: 0 4px 12px rgba(0,0,0,0.08); 
            padding: 25px; 
            text-align: center; 
            margin-bottom: 25px; 
            transition: transform 0.3s ease-out, box-shadow 0.3s ease-out;
            border-left: 5px solid var(--cor-secundaria);
            height: 100%;
            display: flex;
            flex-direction: column;
            justify-content: center;
        }}
        .kpi-card:hover {{ transform: translateY(-6px) scale(1.02); box-shadow: 0 8px 20px rgba(0,0,0,0.12); }}
        .kpi-card h3 {{ 
            font-size: 2.8em; 
            color: var(--cor-secundaria); 
            margin: 0 0 10px; 
            font-weight: 700; 
            font-family: var(--fonte-titulos);
        }}
        .kpi-card p {{ font-size: 1em; color: var(--cor-texto-secundario); margin: 0; font-family: var(--fonte-principal); }}
        .kpi-card .icon {{ 
            font-size: 2em; 
            color: var(--cor-destaque); 
            margin-bottom: 12px; 
            display: block; 
        }}
        
        .kpi-card-small-text .kpi-label {{
            font-size: 1em; 
            color: var(--cor-texto);
            margin-bottom: 5px;
            font-weight: 600; 
            font-family: var(--fonte-principal);
        }}
        .kpi-card-small-text .kpi-value {{ 
            font-size: 1.2em; 
            color: var(--cor-secundaria);
            font-weight: 700; 
            font-family: var(--fonte-titulos); 
            margin-bottom: 8px; 
        }}
         .kpi-card-small-text .kpi-value.large {{ 
            font-size: 1.8em;
            font-family: var(--fonte-titulos); 
            color: var(--cor-secundaria);
            font-weight: 700;
        }}
        .kpi-card-small-text .kpi-value.cbo-value {{
            font-size: 1em; 
            font-weight: 600;
            line-height: 1.3;
            font-family: var(--fonte-principal); /* CBO usa fonte principal para melhor leitura */
            color: var(--cor-texto-secundario);
        }}

        .kpi-card-list ul {{ 
            font-size: 0.95em; 
            text-align: left; 
            margin-top: 0; 
            padding-left: 0; 
            list-style: none; 
            font-family: var(--fonte-principal);
        }}
        .kpi-card-list li {{ 
            margin-bottom: 5px;  
            color: var(--cor-texto-secundario);
            font-weight: 400; 
            font-family: var(--fonte-principal); /* Garante a fonte principal */
        }}
        .kpi-card-list li strong {{ 
            color: var(--cor-texto); 
            font-weight: 600; 
            font-family: var(--fonte-principal); /* Garante a fonte principal */
        }}


        .chart-container {{ 
            background-color: var(--cor-fundo-card); 
            border-radius: 12px; 
            box-shadow: 0 4px 12px rgba(0,0,0,0.08); 
            padding: 20px; 
            margin-bottom: 30px; 
            height: 480px; 
            overflow: hidden; 
            font-family: var(--fonte-principal);
            color: var(--cor-texto); 
        }}
        .map-outer-container {{
            background-color: var(--cor-fundo-card);
            border-radius: 12px;
            box-shadow: 0 4px 12px rgba(0,0,0,0.08);
            padding: 20px;
            margin-bottom: 30px;
        }}
        .map-toggle-buttons {{
            margin-bottom: 15px;
            text-align: center;
        }}
        .map-toggle-buttons .btn {{
            margin: 0 8px;
            padding: 8px 18px;
            font-size: 0.95em;
            border-radius: 20px; 
            transition: all 0.3s ease;
            font-weight: 500;
        }}
         .map-toggle-buttons .btn.btn-primary.active {{ 
            background-color: var(--cor-destaque);
            border-color: var(--cor-destaque);
            color: white;
            box-shadow: 0 2px 5px rgba(0,0,0,0.2);
        }}
        .map-toggle-buttons .btn:not(.active) {{
            background-color: #f0f0f0;
            border-color: #d0d0d0;
            color: var(--cor-texto);
        }}
        .map-container {{ 
            height: 600px; 
            border: 1px solid #ddd;
            border-radius: 8px;
            overflow: hidden; 
        }}
        .map-container iframe {{ width: 100%; height: 100%; border: none; }}
        
        .footer {{ text-align: center; padding: 25px 0; font-size: 0.9em; color: #6c757d; border-top: 1px solid #dee2e6; margin-top: 40px; background-color: #fff; }}
        .section-title {{ 
            color: var(--cor-primaria); 
            margin-bottom: 25px; 
            border-bottom: 3px solid var(--cor-destaque); 
            padding-bottom: 12px; 
            font-size: 1.8em; 
            font-weight: 600; 
            font-family: var(--fonte-titulos);
        }}
        .chart-container .js-plotly-plot .plotly svg,
        .chart-container .js-plotly-plot .plotly svg .main-svg {{
            background: transparent !important;
        }}
        
        @media (max-width: 768px) {{
            .header-logos img {{ max-height: 50px; margin: 5px 10px; }}
            .header h1 {{ font-size: 1.8em; }}
            .kpi-card h3 {{ font-size: 2.2em; }}
            .kpi-card .icon {{ font-size: 1.8em; }}
            .chart-container {{ height: 400px; padding: 15px; }}
            .map-container {{ height: 500px; }}
            .map-toggle-buttons .btn {{ padding: 6px 12px; font-size: 0.9em;}}
        }}
    </style>
</head>
<body>
    <header class="header">
        <div class="container">
            <div class="header-content">
                <div class="header-logos">
                    <img src="assets/EMCM-UFRN-VERTICAL.png" alt="Logo EMCM-UFRN" onerror="this.style.display='none'">
                </div>
                <div class="header-title-block">
                    <h1><i class="fas fa-chart-line"></i> Dashboard de Egressos EMCM</h1>
                    <p>Acompanhamento da Distribuição e Atuação dos Profissionais Formados</p>
                </div>
                <div class="header-logos">
                     <img src="assets/ufrn-logo-2.png" alt="Logo UFRN" onerror="this.style.display='none'">
                </div>
            </div>
        </div>
    </header>

    <div class="container-fluid mt-4">
        <h2 class="section-title"><i class="fas fa-tachometer-alt"></i> Indicadores Gerais</h2>
        <div class="row row-eq-height">
            <div class="col-xl-3 col-lg-6 mb-4">
                <div class="kpi-card">
                    <span class="icon"><i class="fas fa-graduation-cap"></i></span>
                    <h3>{kpis.get("total_egressos_lista_original", 0)}</h3>
                    <p>Total de Egressos (Lista Original)</p>
                </div>
            </div>
            <div class="col-xl-3 col-lg-6 mb-4">
                <div class="kpi-card">
                    <span class="icon"><i class="fas fa-users"></i></span>
                    <h3>{kpis.get("total_vinculos", 0)}</h3>
                    <p>Total de Vínculos Encontrados</p>
                </div>
            </div>
            <div class="col-xl-3 col-lg-6 mb-4">
                <div class="kpi-card">
                    <span class="icon"><i class="fas fa-map-marked-alt"></i></span>
                    <h3>{kpis.get("total_municipios_unicos", 0)}</h3>
                    <p>Municípios com Presença</p>
                </div>
            </div>
            <div class="col-xl-3 col-lg-6 mb-4">
                <div class="kpi-card">
                    <span class="icon"><i class="fas fa-briefcase-medical"></i></span>
                    <h3>{kpis.get("total_cbos_distintos", 0)}</h3>
                    <p>CBOs Distintos</p>
                </div>
            </div>
            <div class="col-xl-3 col-lg-6 mb-4">
                <div class="kpi-card kpi-card-small-text"> 
                    <span class="icon"><i class="fas fa-clinic-medical"></i></span>
                    <h3 class="kpi-value">{kpis.get("percentual_atencao_basica", 0)}%</h3> 
                    <p class="kpi-label">Vínculos na Atenção Básica</p> 
                </div>
            </div>
            <div class="col-xl-3 col-lg-6 mb-4">
                <div class="kpi-card kpi-card-small-text">
                    <span class="icon"><i class="fas fa-stethoscope"></i></span>
                    <p class="kpi-label">CBO Mais Frequente:</p>
                    <p class="kpi-value cbo-value">{kpis.get("cbo_mais_frequente", "N/A")}</p>
                </div>
            </div>
            <div class="col-xl-3 col-lg-6 mb-4">
                <div class="kpi-card kpi-card-small-text">
                    <span class="icon"><i class="fas fa-map-pin"></i></span>
                     <p class="kpi-label">Média de Vínculos por Município:</p>
                     <p class="kpi-value large">{kpis.get("media_vinculos_por_municipio", "N/A")}</p>
                </div>
            </div>
            <div class="col-xl-3 col-lg-6 mb-4">
                <div class="kpi-card kpi-card-list kpi-card-small-text"> <span class="icon"><i class="fas fa-globe-americas"></i></span>
                    <p class="kpi-label">Vínculos por Região:</p> {vinculos_por_regiao_html}
                </div>
            </div>
        </div>

        <div class="map-outer-container">
            <h2 class="section-title text-center mb-4"><i class="fas fa-map-location-dot"></i> Mapa de Distribuição dos Egressos</h2>
            <div class="map-toggle-buttons">
                <button id="btnPins" class="btn btn-primary active" onclick="alternarMapa('mapa_pins.html')">Pins</button>
                <button id="btnCalor" class="btn btn-secondary" onclick="alternarMapa('mapa_calor.html')">Mapa de Calor</button>
            </div>
            <div class="map-container">
                <iframe id="mapaFrame" src="{mapa_inicial_src}" width="100%" height="100%" frameborder="0" allowfullscreen>
                    O seu navegador não suporta iframes.
                </iframe>
            </div>
        </div>

        <h2 class="section-title"><i class="fas fa-chart-pie"></i> Análises Gráficas Detalhadas</h2>
        <div class="row">
            <div class="col-lg-6 mb-4">
                <div class="chart-container" id="chart-uf">
                    {grafico_uf_content}
                </div>
            </div>
            <div class="col-lg-6 mb-4">
                <div class="chart-container" id="chart-cbo">
                    {grafico_cbo_content}
                </div>
            </div>
        </div>
        <div class="row">
            <div class="col-lg-6 mb-4">
                <div class="chart-container" id="chart-regiao">
                    {grafico_regiao_content}
                </div>
            </div>
            <div class="col-lg-6 mb-4">
                <div class="chart-container" id="chart-grande-area">
                    {grafico_grande_area_content}
                </div>
            </div>
        </div>
    </div>

    <footer class="footer">
        <p>Fonte dos dados: CNES DATASUS. Coleta e processamento realizados em {pd.Timestamp('today').strftime('%d/%m/%Y')}.</p>
        <p>Desenvolvido por Augusto Severo de Araújo como parte do projeto de mestrado. EMCM/UFRN.</p>
        <p>&copy; {pd.Timestamp('today').strftime('%Y')} Todos os direitos reservados.</p>
    </footer>

    <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.2/dist/js/bootstrap.bundle.min.js"></script>
    <script>
    function alternarMapa(mapaSrc) {{
        console.log("Tentando carregar mapa:", mapaSrc); 
        const iframe = document.getElementById('mapaFrame');
        if (iframe) {{
            iframe.src = mapaSrc;
            console.log("Iframe src definido para:", iframe.src);
        }} else {{
            console.error("Elemento iframe 'mapaFrame' não encontrado.");
        }}

        const btnPins = document.getElementById('btnPins');
        const btnCalor = document.getElementById('btnCalor');

        if (btnPins) {{
            btnPins.classList.remove('active', 'btn-primary');
            btnPins.classList.add('btn-secondary');
        }}
        if (btnCalor) {{
            btnCalor.classList.remove('active', 'btn-primary');
            btnCalor.classList.add('btn-secondary');
        }}

        if (mapaSrc === 'mapa_pins.html' && btnPins) {{
            btnPins.classList.add('active', 'btn-primary');
            btnPins.classList.remove('btn-secondary');
        }} else if (mapaSrc === 'mapa_calor.html' && btnCalor) {{
            btnCalor.classList.add('active', 'btn-primary');
            btnCalor.classList.remove('btn-secondary');
        }}
    }}
    
    window.addEventListener('DOMContentLoaded', (event) => {{
        const iframe = document.getElementById('mapaFrame');
        if (iframe && iframe.src.includes('mapa_pins.html')) {{
            alternarMapa('mapa_pins.html'); 
        }} else if (iframe && iframe.src.includes('mapa_calor.html')) {{
            alternarMapa('mapa_calor.html');
        }}
    }});
    </script>
</body>
</html>
"""

output_path = Path("dashboard_final.html")
output_path.write_text(dashboard_html_content, encoding="utf-8")

print(f"✅ Dashboard final gerado com sucesso: {output_path.resolve()}")
print("Certifique-se de que os arquivos 'mapa_pins.html' e 'mapa_calor.html' foram gerados na mesma pasta.")
print("Verifique também os arquivos HTML individuais dos gráficos na pasta do projeto.")

if __name__ == "__main__":
    print("Script de geração de dashboard concluído.")
