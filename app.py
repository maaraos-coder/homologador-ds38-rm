import streamlit as st
import geopandas as gpd
import pandas as pd
import folium
import zipfile
import unicodedata

from streamlit_folium import st_folium
from shapely.geometry import Point

st.set_page_config(page_title="Diagnóstico PRMS", layout="wide")

st.title("Diagnóstico PRC + PRMS")
st.subheader("Selector de capas para revisar homologación DS38")

ZIP_PATH = "data/IPTMetropolitana.zip"
NACLU_PATH = "data/02.NACLU.zip"


def normalizar(texto):
    texto = str(texto).lower()
    texto = unicodedata.normalize("NFKD", texto)
    texto = "".join([c for c in texto if not unicodedata.combining(c)])
    texto = texto.replace("ñ", "n")
    texto = texto.replace("_", " ")
    texto = texto.replace("-", " ")
    return texto.strip()


@st.cache_data
def listar_shapefiles():
    with zipfile.ZipFile(ZIP_PATH, "r") as z:
        archivos = z.namelist()
    return [a for a in archivos if a.endswith(".shp")]


@st.cache_data
def listar_prc():
    return [
        a for a in listar_shapefiles()
        if "/PRC/" in a
        and "Patrimonio" not in a
        and "ZNE" not in a
        and "poligono" not in a
    ]


@st.cache_data
def listar_prms():
    return [
        a for a in listar_shapefiles()
        if "/PRMS/" in a
    ]


@st.cache_data
def cargar_shp(shp):
    ruta = f"zip://{ZIP_PATH}!{shp}"
    gdf = gpd.read_file(ruta)
    gdf = gdf.to_crs(epsg=4326)
    gdf["archivo_origen"] = shp
    return gdf


@st.cache_data
def crear_indice_comunas():
    indice = {}

    for shp in listar_prc():
        nombre = shp.split("/")[-1]
        comuna = nombre.replace("IPT_13_PRC_", "")
        comuna = comuna.replace("IPT_13_PNSECC_", "")
        comuna = comuna.replace(".shp", "")
        comuna = comuna.replace("_", " ")

        indice[normalizar(comuna)] = {
            "nombre": comuna,
            "archivo": shp
        }

    return indice


def normalizar_columnas(gdf):
    renombres = {
        "COM": "COMUNA",
        "NOM": "NOMBRE",
        "NOMBRE_ZON": "NOMBRE",
        "NOM_ZONA": "NOMBRE",
        "N_DOC": "DECRETO",
        "P_DO": "PLANO",
        "COD_ZONA": "ZONA",
        "ZONIF": "ZONA",
        "USO": "UPERM",
        "USO_SUELO": "UPERM",
        "DESTINO": "UPERM",
        "NOM_USO": "NOMBRE",
        "TIPO": "NOMBRE",
        "CLASE": "NOMBRE"
    }

    gdf = gdf.rename(columns=renombres)

    for col in ["COMUNA", "ZONA", "NOMBRE", "UPERM", "UPREF", "UPROH", "SUELO", "DECRETO", "PLANO"]:
        if col not in gdf.columns:
            gdf[col] = ""

    return gdf


def buscar_punto(lat, lon, gdf):
    punto = gpd.GeoDataFrame(
        {"id": [1]},
        geometry=[Point(lon, lat)],
        crs="EPSG:4326"
    )

    resultado = gpd.sjoin(
        punto,
        gdf,
        how="left",
        predicate="intersects"
    )

    return resultado


def mostrar_resultado_capa(nombre, lat, lon, gdf):
    st.subheader(nombre)

    resultado = buscar_punto(lat, lon, gdf)

    if resultado.empty or pd.isna(resultado.iloc[0].get("index_right")):
        st.warning("El punto NO intersecta esta capa.")
        return

    fila = resultado.iloc[0]

    st.success("El punto SÍ intersecta esta capa.")

    st.write("**Archivo origen:**", fila.get("archivo_origen", ""))
    st.write("**Comuna:**", fila.get("COMUNA", ""))
    st.write("**Zona:**", fila.get("ZONA", ""))
    st.write("**Nombre:**", fila.get("NOMBRE", ""))
    st.write("**Usos permitidos:**", fila.get("UPERM", ""))
    st.write("**Usos prohibidos:**", fila.get("UPROH", ""))

    with st.expander("Ver todos los atributos encontrados"):
        datos = fila.drop(labels=["geometry"], errors="ignore")
        st.dataframe(pd.DataFrame([datos]))


# =========================
# LIMPIAR CACHE
# =========================

if st.button("Limpiar caché"):
    st.cache_data.clear()
    st.rerun()


# =========================
# SELECTORES
# =========================

indice = crear_indice_comunas()

comunas = sorted(
    indice.keys(),
    key=lambda x: indice[x]["nombre"]
)

st.subheader("1. Seleccionar comuna PRC")

comuna_clave = st.selectbox(
    "Comuna",
    comunas,
    format_func=lambda x: indice[x]["nombre"]
)

comuna_info = indice[comuna_clave]

gdf_prc = cargar_shp(comuna_info["archivo"])
gdf_prc = normalizar_columnas(gdf_prc)

st.write("**PRC cargado:**", comuna_info["archivo"])
st.write("**Polígonos PRC:**", len(gdf_prc))


st.subheader("2. Seleccionar capa PRMS")

capas_prms = listar_prms()

capa_prms = st.selectbox(
    "Capa PRMS",
    capas_prms
)

gdf_prms = cargar_shp(capa_prms)
gdf_prms = normalizar_columnas(gdf_prms)

st.write("**PRMS cargado:**", capa_prms)
st.write("**Polígonos PRMS:**", len(gdf_prms))
st.write("**Columnas PRMS:**", list(gdf_prms.columns))


# =========================
# COORDENADAS
# =========================

st.subheader("3. Coordenadas de prueba")

col1, col2 = st.columns(2)

with col1:
    lat = st.number_input(
        "Latitud",
        value=-33.6076141593194,
        format="%.12f"
    )

with col2:
    lon = st.number_input(
        "Longitud",
        value=-70.86627958980972,
        format="%.12f"
    )

if st.button("Evaluar punto"):
    st.session_state.lat = lat
    st.session_state.lon = lon

if "lat" not in st.session_state:
    st.session_state.lat = lat

if "lon" not in st.session_state:
    st.session_state.lon = lon


# =========================
# MAPA
# =========================

centro = [st.session_state.lat, st.session_state.lon]

m = folium.Map(location=centro, zoom_start=14)

try:
    prc_mapa = gdf_prc.copy()
    prc_mapa["geometry"] = prc_mapa.geometry.simplify(0.0003, preserve_topology=True)

    folium.GeoJson(
        prc_mapa,
        name="PRC",
        tooltip=folium.GeoJsonTooltip(
            fields=["ZONA", "NOMBRE"],
            aliases=["Zona PRC", "Nombre PRC"]
        )
    ).add_to(m)
except:
    pass

try:
    prms_mapa = gdf_prms.copy()
    prms_mapa["geometry"] = prms_mapa.geometry.simplify(0.0005, preserve_topology=True)

    folium.GeoJson(
        prms_mapa,
        name="PRMS seleccionado",
        style_function=lambda x: {
            "fillOpacity": 0.15,
            "weight": 2
        },
        tooltip=folium.GeoJsonTooltip(
            fields=["ZONA", "NOMBRE"],
            aliases=["Zona PRMS", "Nombre PRMS"]
        )
    ).add_to(m)
except:
    pass

folium.Marker(
    [st.session_state.lat, st.session_state.lon],
    popup="Punto evaluado",
    icon=folium.Icon(color="red")
).add_to(m)

folium.LayerControl().add_to(m)

map_data = st_folium(m, width=1200, height=650)

if map_data["last_clicked"]:
    st.session_state.lat = map_data["last_clicked"]["lat"]
    st.session_state.lon = map_data["last_clicked"]["lng"]
    st.rerun()


# =========================
# RESULTADOS
# =========================

st.subheader("4. Resultados")

mostrar_resultado_capa(
    "Resultado PRC",
    st.session_state.lat,
    st.session_state.lon,
    gdf_prc
)

mostrar_resultado_capa(
    "Resultado PRMS seleccionado",
    st.session_state.lat,
    st.session_state.lon,
    gdf_prms
)
