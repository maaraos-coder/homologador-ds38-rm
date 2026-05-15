import streamlit as st
import geopandas as gpd
import pandas as pd
import folium
import zipfile
import unicodedata

from streamlit_folium import st_folium
from shapely.geometry import Point
from geopy.geocoders import Nominatim

st.set_page_config(page_title="Homologador DS38 RM", layout="wide")

st.title("Homologador DS38/11 MMA")
st.subheader("Región Metropolitana - Homologación Res. Ex. SMA N°491/2016")

ZIP_PATH = "data/IPTMetropolitana.zip"


# =========================================================
# UTILIDADES
# =========================================================

def normalizar(texto):
    texto = str(texto).lower()
    texto = unicodedata.normalize("NFKD", texto)
    texto = "".join([c for c in texto if not unicodedata.combining(c)])
    texto = texto.replace("ñ", "n")
    texto = texto.replace("_", " ")
    texto = texto.replace("-", " ")
    return texto.strip()


@st.cache_data
def listar_shapefiles_prc():
    with zipfile.ZipFile(ZIP_PATH, "r") as z:
        archivos = z.namelist()

    shp_prc = [
        a for a in archivos
        if a.endswith(".shp")
        and "/PRC/" in a
        and "Patrimonio" not in a
        and "ZNE" not in a
        and "poligono" not in a
        and "_R." not in a
        and "_R_" not in a
    ]

    return shp_prc


@st.cache_data
def crear_indice_comunas():
    indice = {}

    for shp in listar_shapefiles_prc():
        nombre = shp.split("/")[-1]

        comuna = nombre.replace("IPT_13_PRC_", "")
        comuna = comuna.replace("IPT_13_PNSECC_", "")
        comuna = comuna.replace(".shp", "")
        comuna_limpia = comuna.replace("_", " ")

        clave = normalizar(comuna_limpia)

        if clave not in indice:
            indice[clave] = {
                "nombre": comuna_limpia,
                "archivo": shp
            }

    return indice


@st.cache_data
def cargar_comuna(shp):
    ruta = f"zip://{ZIP_PATH}!{shp}"

    gdf = gpd.read_file(ruta)
    gdf = gdf.to_crs(epsg=4326)
    gdf["archivo_origen"] = shp

    return gdf


def normalizar_columnas(gdf):
    renombres = {
        "COM": "COMUNA",
        "NOM": "NOMBRE",
        "N_DOC": "DECRETO",
        "P_DO": "PLANO"
    }

    gdf = gdf.rename(columns=renombres)

    columnas_necesarias = [
        "COMUNA",
        "ZONA",
        "NOMBRE",
        "UPERM",
        "UPREF",
        "UPROH",
        "SUELO",
        "DECRETO",
        "PLANO"
    ]

    for col in columnas_necesarias:
        if col not in gdf.columns:
            gdf[col] = ""

    return gdf


# =========================================================
# HOMOLOGACIÓN RES. EX. SMA 491/2016
# =========================================================

def detectar_categorias_oguc(fila):
    texto = " ".join([
        str(fila.get("UPERM", "")),
        str(fila.get("UPREF", "")),
        str(fila.get("SUELO", "")),
        str(fila.get("NOMBRE", "")),
        str(fila.get("ZONA", "")),
    ])

    texto_norm = normalizar(texto)

    categorias = set()

    # R = Residencial
    if (
        "residencial" in texto_norm
        or "vivienda" in texto_norm
        or "habitacional" in texto_norm
    ):
        categorias.add("R")

    # Eq = Equipamiento
    if (
        "equipamiento" in texto_norm
        or "comercio" in texto_norm
        or "educacion" in texto_norm
        or "salud" in texto_norm
        or "culto" in texto_norm
        or "cultura" in texto_norm
        or "deporte" in texto_norm
        or "seguridad" in texto_norm
        or "servicio" in texto_norm
        or "servicios" in texto_norm
        or "social" in texto_norm
        or "esparcimiento" in texto_norm
        or "cientifico" in texto_norm
    ):
        categorias.add("Eq")

    # AP = Actividades Productivas
    if (
        "actividad productiva" in texto_norm
        or "actividades productivas" in texto_norm
        or "industrial" in texto_norm
        or "industria" in texto_norm
        or "taller" in texto_norm
        or "bodega" in texto_norm
        or "almacenamiento" in texto_norm
        or "inofensiva" in texto_norm
        or "molesta" in texto_norm
        or "insalubre" in texto_norm
        or "contaminante" in texto_norm
        or "peligrosa" in texto_norm
    ):
        categorias.add("AP")

    # Inf = Infraestructura
    if (
        "infraestructura" in texto_norm
        or "transporte" in texto_norm
        or "sanitaria" in texto_norm
        or "energetica" in texto_norm
        or "telecomunicacion" in texto_norm
        or "telecomunicaciones" in texto_norm
        or "red vial" in texto_norm
        or "terminal" in texto_norm
        or "estacion" in texto_norm
        or "subestacion" in texto_norm
        or "planta" in texto_norm
    ):
        categorias.add("Inf")

    # AV = Área Verde
    if (
        "area verde" in texto_norm
        or "areas verdes" in texto_norm
        or "parque" in texto_norm
        or "plaza" in texto_norm
    ):
        categorias.add("AV")

    # EP = Espacio Público
    if (
        "espacio publico" in texto_norm
        or "espacios publicos" in texto_norm
        or "vialidad" in texto_norm
        or "bien nacional de uso publico" in texto_norm
    ):
        categorias.add("EP")

    return categorias


def homologar_por_tabla_sma491(categorias):
    cats = set(categorias)

    if cats in [
        {"AV"},
        {"EP"},
        {"AV", "EP"}
    ]:
        return "Zona I", "55 dBA", "45 dBA", "AV/EP solos o combinados entre sí se homologan a Zona I."

    if (
        ("AP" in cats or "Inf" in cats)
        and "R" not in cats
        and "Eq" not in cats
    ):
        return "Zona IV", "70 dBA", "70 dBA", "Actividad Productiva y/o Infraestructura sin uso Residencial ni Equipamiento."

    if "AP" in cats or "Inf" in cats:
        return "Zona III", "65 dBA", "55 dBA", "Combinación con Actividad Productiva y/o Infraestructura junto a R/Eq/AV/EP."

    if "Eq" in cats:
        return "Zona II", "60 dBA", "50 dBA", "Combinación con Equipamiento, sin Actividad Productiva ni Infraestructura."

    if "R" in cats:
        return "Zona I", "55 dBA", "45 dBA", "Uso Residencial solo o combinado únicamente con Área Verde/Espacio Público."

    return "No clasificada", "-", "-", "No se detectaron categorías suficientes para homologar automáticamente."


def homologar_ds38(fila):
    categorias = detectar_categorias_oguc(fila)
    zona, dia, noche, criterio = homologar_por_tabla_sma491(categorias)

    categorias_texto = " + ".join(sorted(categorias)) if categorias else "No detectadas"

    return zona, dia, noche, criterio, categorias_texto


# =========================================================
# CRUCE ESPACIAL CON TOLERANCIA
# =========================================================

def buscar_punto(lat, lon, gdf, tolerancia_m=50):
    punto = gpd.GeoDataFrame(
        {"id": [1]},
        geometry=[Point(lon, lat)],
        crs="EPSG:4326"
    )

    # 1. Búsqueda exacta dentro/intersección del polígono
    resultado = gpd.sjoin(
        punto,
        gdf,
        how="left",
        predicate="intersects"
    )

    if not resultado.empty and not pd.isna(resultado.iloc[0].get("ZONA")):
        resultado["metodo_busqueda"] = "Dentro del polígono"
        resultado["distancia_m"] = 0
        return resultado

    # 2. Búsqueda por tolerancia espacial en metros
    try:
        punto_m = punto.to_crs(epsg=32719)
        gdf_m = gdf.to_crs(epsg=32719)

        punto_geom = punto_m.geometry.iloc[0]

        gdf_m = gdf_m.copy()
        gdf_m["distancia_m"] = gdf_m.geometry.distance(punto_geom)

        cercanos = gdf_m[gdf_m["distancia_m"] <= tolerancia_m].copy()

        if cercanos.empty:
            resultado["metodo_busqueda"] = "Sin coincidencia"
            resultado["distancia_m"] = None
            return resultado

        cercano = cercanos.sort_values("distancia_m").iloc[[0]].copy()
        distancia = round(float(cercano.iloc[0]["distancia_m"]), 2)

        cercano = cercano.to_crs(epsg=4326)
        cercano["id"] = 1
        cercano["metodo_busqueda"] = "Por tolerancia espacial"
        cercano["distancia_m"] = distancia

        return cercano

    except Exception:
        resultado["metodo_busqueda"] = "Error en tolerancia"
        resultado["distancia_m"] = None
        return resultado


# =========================================================
# RESULTADO
# =========================================================

def mostrar_resultado(lat, lon, gdf, tolerancia_m):
    resultado = buscar_punto(lat, lon, gdf, tolerancia_m)

    st.subheader("Resultado de homologación")

    if resultado.empty or pd.isna(resultado.iloc[0].get("ZONA")):
        st.warning("No se encontró homologación para el punto en la comuna seleccionada.")
        return

    fila = resultado.iloc[0]

    metodo = fila.get("metodo_busqueda", "")
    distancia = fila.get("distancia_m", "")

    if metodo == "Por tolerancia espacial":
        st.warning(
            f"El punto no cayó exactamente dentro del polígono. "
            f"Se homologó usando el polígono más cercano a {distancia} m."
        )
    else:
        st.success("Punto ubicado dentro de zona PRC/IPT")

    zona_ds38, limite_dia, limite_noche, criterio, categorias = homologar_ds38(fila)

    col1, col2 = st.columns(2)

    with col1:
        st.write("**Coordenadas:**", lat, lon)
        st.write("**Comuna:**", fila.get("COMUNA", ""))
        st.write("**Zona PRC:**", fila.get("ZONA", ""))
        st.write("**Nombre zona:**", fila.get("NOMBRE", ""))
        st.write("**Suelo:**", fila.get("SUELO", ""))
        st.write("**Método de búsqueda:**", metodo)
        st.write("**Distancia de ajuste:**", distancia)

    with col2:
        st.write("**Categorías detectadas:**", categorias)
        st.write("**Zona DS38:**", zona_ds38)
        st.write("**Límite diurno:**", limite_dia)
        st.write("**Límite nocturno:**", limite_noche)
        st.write("**Decreto:**", fila.get("DECRETO", ""))
        st.write("**Plano:**", fila.get("PLANO", ""))

    st.write("**Usos preferentes:**")
    st.write(fila.get("UPREF", ""))

    st.write("**Usos permitidos:**")
    st.write(fila.get("UPERM", ""))

    st.write("**Usos prohibidos:**")
    st.write(fila.get("UPROH", ""))

    st.subheader("Criterio de homologación")
    st.write(criterio)

    advertencia = ""
    if metodo == "Por tolerancia espacial":
        advertencia = (
            f" Cabe hacer presente que el punto no intersectó directamente el polígono "
            f"de zonificación, por lo que se aplicó una tolerancia espacial de {tolerancia_m} m, "
            f"identificándose el polígono más cercano a {distancia} m."
        )

    texto = f"""
Para el punto consultado, ubicado en la comuna de {fila.get("COMUNA", "")}, se identifica la zona PRC/IPT {fila.get("ZONA", "")}, denominada {fila.get("NOMBRE", "")}. De acuerdo con los usos de suelo informados en la cartografía IPT revisada, se identifican las siguientes categorías de uso de suelo para efectos de homologación acústica: {categorias}.

Conforme a los criterios establecidos en la Resolución Exenta N°491/2016 de la Superintendencia del Medio Ambiente, la zona se homologa preliminarmente como {zona_ds38} del D.S. N°38/2011 del MMA, con límite máximo permisible de {limite_dia} en periodo diurno y {limite_noche} en periodo nocturno.{advertencia}
"""

    st.subheader("Texto técnico preliminar")
    st.text_area("Redacción", texto.strip(), height=220)


# =========================================================
# SESSION STATE
# =========================================================

if "lat" not in st.session_state:
    st.session_state.lat = None

if "lon" not in st.session_state:
    st.session_state.lon = None


# =========================================================
# COMUNAS
# =========================================================

indice = crear_indice_comunas()

comunas_ordenadas = sorted(
    indice.keys(),
    key=lambda x: indice[x]["nombre"]
)

st.subheader("Seleccionar comuna")

comuna_clave = st.selectbox(
    "Comuna",
    comunas_ordenadas,
    format_func=lambda x: indice[x]["nombre"]
)

comuna_info = indice[comuna_clave]

gdf = cargar_comuna(comuna_info["archivo"])
gdf = normalizar_columnas(gdf)

st.success(
    f"Comuna cargada: {comuna_info['nombre']} | Polígonos: {len(gdf)}"
)

# =========================================================
# TOLERANCIA
# =========================================================

st.subheader("Ajuste espacial")

tolerancia_m = st.selectbox(
    "Tolerancia si el punto no cae dentro del polígono",
    [0, 25, 50, 100, 150, 200],
    index=2
)


# =========================================================
# BUSCADOR
# =========================================================

st.subheader("Buscar dirección")

direccion = st.text_input(
    "Ingrese dirección",
    placeholder=f"Ej: Av. Grecia 8735, {comuna_info['nombre']}, Chile"
)

if st.button("Buscar dirección y homologar"):
    geolocator = Nominatim(
        user_agent="homologador_ds38_rm"
    )

    consulta = direccion

    if comuna_info["nombre"].lower() not in direccion.lower():
        consulta = f"{direccion}, {comuna_info['nombre']}, Chile"

    location = geolocator.geocode(consulta)

    if location:
        st.session_state.lat = location.latitude
        st.session_state.lon = location.longitude

        st.success("Dirección encontrada")

    else:
        st.error("No se encontró la dirección.")


# =========================================================
# MAPA
# =========================================================

centro = [-33.45, -70.66]

try:
    bounds = gdf.total_bounds

    centro = [
        (bounds[1] + bounds[3]) / 2,
        (bounds[0] + bounds[2]) / 2
    ]

except:
    pass

if st.session_state.lat and st.session_state.lon:
    centro = [
        st.session_state.lat,
        st.session_state.lon
    ]

m = folium.Map(
    location=centro,
    zoom_start=13
)

gdf_mapa = gdf.copy()

gdf_mapa["geometry"] = gdf_mapa.geometry.simplify(
    0.0003,
    preserve_topology=True
)

folium.GeoJson(
    gdf_mapa,
    name=f"PRC {comuna_info['nombre']}",
    tooltip=folium.GeoJsonTooltip(
        fields=["COMUNA", "ZONA", "NOMBRE"],
        aliases=["Comuna", "Zona", "Nombre"]
    )
).add_to(m)

if st.session_state.lat and st.session_state.lon:
    folium.Marker(
        [
            st.session_state.lat,
            st.session_state.lon
        ],
        popup="Punto seleccionado",
        icon=folium.Icon(color="red")
    ).add_to(m)

map_data = st_folium(
    m,
    width=1200,
    height=650
)


# =========================================================
# CLICK MAPA
# =========================================================

if map_data["last_clicked"]:
    st.session_state.lat = map_data["last_clicked"]["lat"]
    st.session_state.lon = map_data["last_clicked"]["lng"]


# =========================================================
# RESULTADO
# =========================================================

if st.session_state.lat and st.session_state.lon:
    mostrar_resultado(
        st.session_state.lat,
        st.session_state.lon,
        gdf,
        tolerancia_m
    )