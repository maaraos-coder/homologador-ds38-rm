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
st.subheader("Región Metropolitana - Motor PRC + PRMS optimizado por comuna")

if st.button("Limpiar caché"):
    st.cache_data.clear()
    st.success("Caché eliminada correctamente.")
    st.rerun()

st.warning(
    "Herramienta de apoyo técnico para homologación preliminar de zonas DS38/11 MMA. "
    "El resultado debe ser verificado con el Instrumento de Planificación Territorial vigente, "
    "la cartografía oficial y la Res. Ex. SMA N°491/2016 antes de su uso formal."
)

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


def texto_atributos(fila):
    valores = []

    for col in fila.index:
        if col == "geometry":
            continue
        try:
            valores.append(str(fila.get(col, "")))
        except:
            pass

    return normalizar(" ".join(valores))


def tiene_info_normativa(fila):
    zona = str(fila.get("ZONA", "")).strip()
    nombre = str(fila.get("NOMBRE", "")).strip()
    usos = str(fila.get("UPERM", "")).strip()

    if zona and zona.lower() != "nan":
        return True

    if nombre and nombre.lower() != "nan":
        return True

    if usos and usos.lower() != "nan":
        return True

    return False

@st.cache_data
def cargar_tabla_homologacion():
    try:
        return pd.read_csv("rules/homologacion_prc.csv")
    except:
        return pd.DataFrame()


def homologar_por_tabla_prc(comuna, zona_prc, nombre_zona):
    tabla = cargar_tabla_homologacion()

    if tabla.empty:
        return None

    comuna_norm = normalizar(comuna)
    zona_norm = normalizar(zona_prc)
    nombre_norm = normalizar(nombre_zona)

    tabla = tabla.copy()
    tabla["comuna_norm"] = tabla["comuna"].apply(normalizar)
    tabla["zona_norm"] = tabla["zona_prc"].apply(normalizar)
    tabla["nombre_norm"] = tabla["nombre_zona"].apply(normalizar)

    match = tabla[
        (tabla["comuna_norm"] == comuna_norm)
        &
        (
            (tabla["zona_norm"] == zona_norm)
            | (tabla["nombre_norm"] == nombre_norm)
        )
    ]

    if match.empty:
        return None

    return match.iloc[0].to_dict()

# =========================================================
# LISTAR CAPAS
# =========================================================

@st.cache_data
def listar_shapefiles():
    with zipfile.ZipFile(ZIP_PATH, "r") as z:
        archivos = z.namelist()

    return [a for a in archivos if a.endswith(".shp")]


@st.cache_data
def listar_shapefiles_prc():
    shps = listar_shapefiles()

    return [
        a for a in shps
        if "/PRC/" in a
        and "Patrimonio" not in a
        and "ZNE" not in a
        and "poligono" not in a
        and "_R." not in a
        and "_R_" not in a
    ]


@st.cache_data
def buscar_capa_prms_lu():
    shps = listar_shapefiles()

    candidatos = [
        a for a in shps
        if "/PRMS/" in a
        and "PRMS_LU" in a
        and a.endswith(".shp")
    ]

    if candidatos:
        return candidatos[0]

    candidatos = [
        a for a in shps
        if "/PRMS/" in a
        and "LU" in a
        and a.endswith(".shp")
    ]

    return candidatos[0] if candidatos else None


@st.cache_data
def buscar_capa_prms_uso_suelo():
    shps = listar_shapefiles()

    candidatos = [
        a for a in shps
        if "/PRMS/" in a
        and "USO_Suelo" in a
        and a.endswith(".shp")
    ]

    if candidatos:
        return candidatos[0]

    candidatos = [
        a for a in shps
        if "/PRMS/" in a
        and "Uso" in a
        and a.endswith(".shp")
    ]

    return candidatos[0] if candidatos else None


# =========================================================
# ÍNDICE COMUNAS
# =========================================================

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


# =========================================================
# CARGA CAPAS
# =========================================================

@st.cache_data
def cargar_shp(shp):
    ruta = f"zip://{ZIP_PATH}!{shp}"

    gdf = gpd.read_file(ruta)
    gdf = gdf.to_crs(epsg=4326)
    gdf["archivo_origen"] = shp

    return gdf


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

    columnas_necesarias = [
        "COMUNA",
        "ZONA",
        "NOMBRE",
        "UPERM",
        "UPREF",
        "UPROH",
        "SUELO",
        "DECRETO",
        "PLANO",
        "fuente_normativa",
        "archivo_origen",
        "observacion_jerarquia"
    ]

    for col in columnas_necesarias:
        if col not in gdf.columns:
            gdf[col] = ""

    return gdf


# =========================================================
# LÍMITE URBANO PRMS
# =========================================================

def detectar_limite_urbano_prms(lat, lon, gdf_prms_lu):
    if gdf_prms_lu.empty:
        return "No evaluado", "No se cargó PRMS_LU."

    punto = gpd.GeoDataFrame(
        {"id": [1]},
        geometry=[Point(lon, lat)],
        crs="EPSG:4326"
    )

    try:
        resultado = gpd.sjoin(
            punto,
            gdf_prms_lu,
            how="left",
            predicate="intersects"
        )

        if not resultado.empty and not pd.isna(resultado.iloc[0].get("index_right")):
            fila = resultado.iloc[0]
            return "Dentro de límite urbano PRMS", fila.get("archivo_origen", "")

        return "Fuera de límite urbano PRMS / área rural", "No intersecta PRMS_LU."

    except Exception as e:
        return "No evaluado", str(e)


# =========================================================
# HOMOLOGACIÓN SMA 491
# =========================================================

def detectar_categorias_oguc(fila):
    texto = " ".join([
        str(fila.get("UPERM", "")),
        str(fila.get("UPREF", "")),
        str(fila.get("UPROH", "")),
        str(fila.get("SUELO", "")),
        str(fila.get("NOMBRE", "")),
        str(fila.get("ZONA", "")),
        texto_atributos(fila)
    ])

    texto_norm = normalizar(texto)

    categorias = set()

    # =========================================================
    # REGLA ESPECÍFICA PRMS
    # Zona Habitacional Mixta
    # Art. 3.1.1.1 PRMS:
    # Residencial + Equipamiento + Productiva inofensiva + Infraestructura/Transporte
    # =========================================================

    if (
        "zona habitacional mixto" in texto_norm
        or "zona habitacional mixta" in texto_norm
        or "habitacional mixto" in texto_norm
        or "habitacional mixta" in texto_norm
    ):
        return {"R", "Eq", "AP", "Inf"}

    # R = Residencial
    if (
        "residencial" in texto_norm
        or "vivienda" in texto_norm
        or "habitacional" in texto_norm
        or "habitacionales" in texto_norm
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
        or "esparcimiento" in texto_norm
        or "cientifico" in texto_norm
        or "metropolitano" in texto_norm
        or "intercomunal" in texto_norm
    ):
        categorias.add("Eq")

    # AP = Actividad Productiva
    if (
        "actividad productiva" in texto_norm
        or "actividades productivas" in texto_norm
        or "industrial" in texto_norm
        or "industria" in texto_norm
        or "molesta" in texto_norm
        or "inofensiva" in texto_norm
        or "taller" in texto_norm
        or "bodega" in texto_norm
        or "almacenamiento" in texto_norm
        or "productivas" in texto_norm
        or "productiva" in texto_norm
        or "servicio de caracter industrial" in texto_norm
        or "zona industrial" in texto_norm
        or "industrial exclusiva" in texto_norm
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
        or "macroinfraestructura" in texto_norm
    ):
        categorias.add("Inf")

    # AV = Área Verde
    if (
        "area verde" in texto_norm
        or "areas verdes" in texto_norm
        or "parque" in texto_norm
        or "plaza" in texto_norm
        or "recreacion" in texto_norm
    ):
        categorias.add("AV")

    # EP = Espacio Público
    if (
        "espacio publico" in texto_norm
        or "espacios publicos" in texto_norm
        or "uso publico" in texto_norm
        or "vialidad" in texto_norm
        or "bien nacional de uso publico" in texto_norm
    ):
        categorias.add("EP")

    return categorias


def homologar_por_tabla_sma491(categorias):
    cats = set(categorias)

    if cats in [{"AV"}, {"EP"}, {"AV", "EP"}]:
        return "Zona I", "55 dBA", "45 dBA", "AV/EP solos o combinados entre sí se homologan a Zona I."

    if (
        ("AP" in cats or "Inf" in cats)
        and "R" not in cats
        and "Eq" not in cats
    ):
        return "Zona IV", "70 dBA", "70 dBA", "Actividad Productiva y/o Infraestructura sin uso Residencial ni Equipamiento."

    if "AP" in cats or "Inf" in cats:
        return "Zona III", "65 dBA", "50 dBA", "Combinación con Actividad Productiva y/o Infraestructura junto a R/Eq/AV/EP."

    if "Eq" in cats:
        return "Zona II", "60 dBA", "45 dBA", "Combinación con Equipamiento, sin Actividad Productiva ni Infraestructura."

    if "R" in cats:
        return "Zona I", "55 dBA", "45 dBA", "Uso Residencial solo o combinado únicamente con Área Verde/Espacio Público."

    return "No clasificada", "-", "-", "No se detectaron categorías suficientes para homologar automáticamente."


def homologar_ds38(fila):
    comuna = fila.get("COMUNA", "")
    zona_prc = fila.get("ZONA", "")
    nombre_zona = fila.get("NOMBRE", "")

    regla = homologar_por_tabla_prc(
        comuna,
        zona_prc,
        nombre_zona
    )

    if regla:
        return (
            regla["zona_ds38"],
            f'{regla["limite_dia"]} dBA',
            f'{regla["limite_noche"]} dBA',
            regla["fundamento"],
            regla["categorias"]
        )

    categorias = detectar_categorias_oguc(fila)
    zona, dia, noche, criterio = homologar_por_tabla_sma491(categorias)

    categorias_texto = " + ".join(sorted(categorias)) if categorias else "No detectadas"

    return zona, dia, noche, criterio, categorias_texto

# =========================================================
# BÚSQUEDA ESPACIAL
# =========================================================

def buscar_punto_en_capa(lat, lon, gdf, tolerancia_m=50):
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

    if not resultado.empty:
        fila = resultado.iloc[0]

        if not pd.isna(fila.get("index_right")):
            resultado["metodo_busqueda"] = "Dentro del polígono"
            resultado["distancia_m"] = 0
            return resultado

    if tolerancia_m == 0:
        resultado["metodo_busqueda"] = "Sin coincidencia"
        resultado["distancia_m"] = None
        return resultado

    try:
        punto_m = punto.to_crs(epsg=32719)
        gdf_m = gdf.to_crs(epsg=32719).copy()

        punto_geom = punto_m.geometry.iloc[0]

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


def debe_revisar_prms(fila):
    texto = texto_atributos(fila)

    claves = [
        "revisar prms",
        "ver prms",
        "segun prms",
        "según prms",
        "aplica prms",
        "remitase prms",
        "remítase prms",
        "remitirse prms",
        "normativa prms",
        "segun el prms",
        "según el prms",
        "prms"
    ]

    return any(clave in texto for clave in claves)


def buscar_jerarquico(lat, lon, gdf_prc, gdf_prms_uso, tolerancia_m):
    resultado_prc = buscar_punto_en_capa(lat, lon, gdf_prc, tolerancia_m)

    if not resultado_prc.empty:
        fila_prc = resultado_prc.iloc[0]

        if tiene_info_normativa(fila_prc):

            if debe_revisar_prms(fila_prc):
                resultado_prms = buscar_punto_en_capa(
                    lat,
                    lon,
                    gdf_prms_uso,
                    tolerancia_m
                )

                if not resultado_prms.empty:
                    fila_prms = resultado_prms.iloc[0]

                    if tiene_info_normativa(fila_prms):
                        resultado_prms["fuente_normativa"] = "PRMS_USO_Suelo"
                        resultado_prms["observacion_jerarquia"] = (
                            "El PRC contiene referencia a revisión PRMS; "
                            "por ello se utilizó la capa PRMS_USO_Suelo."
                        )
                        return resultado_prms

                resultado_prc["fuente_normativa"] = "PRC"
                resultado_prc["observacion_jerarquia"] = (
                    "El PRC indica revisar PRMS, pero no se encontró información normativa válida en PRMS_USO_Suelo."
                )
                return resultado_prc

            resultado_prc["fuente_normativa"] = "PRC"
            resultado_prc["observacion_jerarquia"] = "Se utilizó la zonificación del PRC comunal."
            return resultado_prc

    resultado_prms = buscar_punto_en_capa(
        lat,
        lon,
        gdf_prms_uso,
        tolerancia_m
    )

    if not resultado_prms.empty:
        fila_prms = resultado_prms.iloc[0]

        if tiene_info_normativa(fila_prms):
            resultado_prms["fuente_normativa"] = "PRMS_USO_Suelo"
            resultado_prms["observacion_jerarquia"] = (
                "No se encontró PRC aplicable; se utilizó PRMS_USO_Suelo."
            )
            return resultado_prms

    return resultado_prc


# =========================================================
# RESULTADO
# =========================================================

def mostrar_resultado(lat, lon, gdf_prc, gdf_prms_uso, gdf_prms_lu, tolerancia_m):
    estado_lu, detalle_lu = detectar_limite_urbano_prms(lat, lon, gdf_prms_lu)

    resultado = buscar_jerarquico(
        lat,
        lon,
        gdf_prc,
        gdf_prms_uso,
        tolerancia_m
    )

    st.subheader("Resultado de homologación")

    st.write("**Clasificación territorial:**", estado_lu)
    st.write("**Detalle límite urbano PRMS:**", detalle_lu)

    if estado_lu == "Fuera de límite urbano PRMS / área rural":
        st.warning(
            "El punto consultado se encuentra fuera del límite urbano PRMS. "
            "La homologación debe revisarse con especial cuidado, considerando condición rural, PRMS "
            "y eventuales restricciones al desarrollo urbano."
        )

    if resultado.empty:
        st.warning("No se encontró homologación para el punto.")
        return

    fila = resultado.iloc[0]

    zona_ds38, limite_dia, limite_noche, criterio, categorias = homologar_ds38(fila)

    metodo = fila.get("metodo_busqueda", "")
    distancia = fila.get("distancia_m", "")
    fuente = fila.get("fuente_normativa", "")
    observacion_jerarquia = fila.get("observacion_jerarquia", "")

    if metodo == "Por tolerancia espacial":
        st.warning(
            f"El punto no cayó exactamente dentro del polígono. "
            f"Se usó el polígono más cercano a {distancia} m."
        )
    else:
        st.success("Punto ubicado dentro de una capa IPT.")

    col1, col2 = st.columns(2)

    with col1:
        st.write("**Coordenadas:**", lat, lon)
        st.write("**Fuente normativa:**", fuente)
        st.write("**Observación jerárquica:**", observacion_jerarquia)
        st.write("**Comuna:**", fila.get("COMUNA", ""))
        st.write("**Zona IPT:**", fila.get("ZONA", ""))
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
        st.write("**Archivo origen:**", fila.get("archivo_origen", ""))

    st.write("**Usos preferentes:**")
    st.write(fila.get("UPREF", ""))

    st.write("**Usos permitidos / atributos de uso:**")
    st.write(fila.get("UPERM", ""))

    st.write("**Usos prohibidos:**")
    st.write(fila.get("UPROH", ""))

    st.subheader("Criterio de homologación")
    st.write(criterio)

    if "PRC Santiago" in str(criterio):
        st.info("Homologación aplicada desde tabla maestra PRC validada por ordenanza comunal.")

    advertencia_lu = ""
    if estado_lu == "Fuera de límite urbano PRMS / área rural":
        advertencia_lu = (
            " Asimismo, el punto se encuentra fuera del límite urbano PRMS, "
            "por lo que la homologación debe entenderse como preliminar y sujeta a revisión "
            "de la condición rural y normativa territorial aplicable."
        )

    advertencia_tol = ""
    if metodo == "Por tolerancia espacial":
        advertencia_tol = (
            f" Cabe hacer presente que el punto no intersectó directamente el polígono "
            f"de zonificación, por lo que se aplicó una tolerancia espacial de {tolerancia_m} m, "
            f"identificándose el polígono más cercano a {distancia} m."
        )

    advertencia_jerarquia = ""
    if observacion_jerarquia:
        advertencia_jerarquia = f" {observacion_jerarquia}"

    texto = f"""
Para el punto consultado, se identifica información territorial proveniente de {fuente}, correspondiente a la zona IPT {fila.get("ZONA", "")}, denominada {fila.get("NOMBRE", "")}. De acuerdo con los atributos de uso de suelo de la cartografía revisada, se identifican las siguientes categorías para efectos de homologación acústica: {categorias}.

El punto presenta la siguiente clasificación territorial según la capa PRMS_LU: {estado_lu}. Conforme a los criterios establecidos en la Resolución Exenta N°491/2016 de la Superintendencia del Medio Ambiente, la zona se homologa preliminarmente como {zona_ds38} del D.S. N°38/2011 del MMA, con límite máximo permisible de {limite_dia} en periodo diurno y {limite_noche} en periodo nocturno.{advertencia_jerarquia}{advertencia_lu}{advertencia_tol}
"""

    st.subheader("Texto técnico preliminar")
    st.text_area("Redacción", texto.strip(), height=260)

    with st.expander("Ver todos los atributos de la capa"):
        st.write(pd.DataFrame([fila.drop(labels=["geometry"], errors="ignore")]))
        

# =========================================================
# SESSION STATE
# =========================================================

if "lat" not in st.session_state:
    st.session_state.lat = None

if "lon" not in st.session_state:
    st.session_state.lon = None


# =========================================================
# SELECTOR COMUNA
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

gdf_prc = cargar_shp(comuna_info["archivo"])
gdf_prc = normalizar_columnas(gdf_prc)
gdf_prc["fuente_normativa"] = "PRC"

capa_prms_lu = buscar_capa_prms_lu()
capa_prms_uso = buscar_capa_prms_uso_suelo()

gdf_prms_lu_total = (
    cargar_shp(capa_prms_lu)
    if capa_prms_lu
    else gpd.GeoDataFrame(geometry=[], crs="EPSG:4326")
)

gdf_prms_uso_total = (
    cargar_shp(capa_prms_uso)
    if capa_prms_uso
    else gpd.GeoDataFrame(geometry=[], crs="EPSG:4326")
)

# =========================================================
# RECORTE PRMS POR COMUNA
# =========================================================

xmin, ymin, xmax, ymax = gdf_prc.total_bounds

try:
    gdf_prms_lu = gdf_prms_lu_total.cx[
        xmin:xmax,
        ymin:ymax
    ].copy()
except:
    gdf_prms_lu = gdf_prms_lu_total.copy()

try:
    gdf_prms_uso = gdf_prms_uso_total.cx[
        xmin:xmax,
        ymin:ymax
    ].copy()
except:
    gdf_prms_uso = gdf_prms_uso_total.copy()

gdf_prms_lu = normalizar_columnas(gdf_prms_lu)
gdf_prms_lu["fuente_normativa"] = "PRMS_LU"

gdf_prms_uso = normalizar_columnas(gdf_prms_uso)
gdf_prms_uso["fuente_normativa"] = "PRMS_USO_Suelo"

st.success(
    f"PRC cargado: {comuna_info['nombre']} | Polígonos PRC: {len(gdf_prc)} | "
    f"PRMS_LU comuna: {len(gdf_prms_lu)} | PRMS_USO_Suelo comuna: {len(gdf_prms_uso)}"
)


# =========================================================
# INSPECCIÓN DE CAPAS
# =========================================================

with st.expander("Ver capas usadas"):
    st.write("PRC:")
    st.write(comuna_info["archivo"])

    st.write("PRMS_LU:")
    st.write(capa_prms_lu)

    st.write("PRMS_USO_Suelo:")
    st.write(capa_prms_uso)

    st.write("Columnas PRMS_USO_Suelo:")
    st.write(list(gdf_prms_uso.columns))


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
# BUSCADOR DIRECCIÓN
# =========================================================

st.subheader("Buscar dirección")

direccion = st.text_input(
    "Ingrese dirección",
    placeholder=f"Ej: Av. Grecia 8735, {comuna_info['nombre']}, Chile"
)

if st.button("Buscar dirección y homologar"):

    geolocator = Nominatim(
        user_agent="homologador_ds38_rm",
        timeout=10
    )

    consulta = direccion

    if comuna_info["nombre"].lower() not in direccion.lower():
        consulta = f"{direccion}, {comuna_info['nombre']}, Chile"

    try:
        with st.spinner("Buscando dirección..."):
            location = geolocator.geocode(
                consulta,
                timeout=10
            )

        if location:
            st.session_state.lat = location.latitude
            st.session_state.lon = location.longitude
            st.success("Dirección encontrada")

        else:
            st.error(
                "No se encontró la dirección. "
                "Prueba agregando comuna y país, o selecciona el punto en el mapa."
            )

    except Exception as e:
        st.warning(
            "El servicio de búsqueda de direcciones no respondió correctamente. "
            "Puedes seleccionar el punto directamente en el mapa o ingresar coordenadas manualmente."
        )
        st.caption(f"Detalle técnico: {e}")


# =========================================================
# COORDENADAS MANUALES
# =========================================================

st.subheader("Ingresar coordenadas manualmente")

col_lat, col_lon = st.columns(2)

with col_lat:
    lat_manual = st.number_input(
        "Latitud",
        value=-33.45,
        format="%.8f"
    )

with col_lon:
    lon_manual = st.number_input(
        "Longitud",
        value=-70.66,
        format="%.8f"
    )

if st.button("Homologar coordenadas"):
    st.session_state.lat = lat_manual
    st.session_state.lon = lon_manual
    st.success("Coordenadas cargadas correctamente")


# =========================================================
# MAPA
# =========================================================

centro = [-33.45, -70.66]

try:
    bounds = gdf_prc.total_bounds
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

# PRMS_LU
try:
    gdf_prms_lu_mapa = gdf_prms_lu.copy()
    gdf_prms_lu_mapa["geometry"] = gdf_prms_lu_mapa.geometry.simplify(
        0.0004,
        preserve_topology=True
    )

    folium.GeoJson(
        gdf_prms_lu_mapa,
        name="PRMS_LU",
        style_function=lambda x: {
            "fillOpacity": 0.00,
            "weight": 2,
            "color": "black"
        }
    ).add_to(m)
except:
    pass

# PRMS_USO_Suelo
try:
    gdf_prms_uso_mapa = gdf_prms_uso.copy()
    gdf_prms_uso_mapa["geometry"] = gdf_prms_uso_mapa.geometry.simplify(
        0.0008,
        preserve_topology=True
    )

    folium.GeoJson(
        gdf_prms_uso_mapa,
        name="PRMS_USO_Suelo",
        style_function=lambda x: {
            "fillOpacity": 0.10,
            "weight": 1
        },
        tooltip=folium.GeoJsonTooltip(
            fields=["NOMBRE", "UPERM"],
            aliases=["Nombre PRMS", "Uso permitido"]
        )
    ).add_to(m)
except:
    pass

# PRC comuna seleccionada
gdf_prc_mapa = gdf_prc.copy()
gdf_prc_mapa["geometry"] = gdf_prc_mapa.geometry.simplify(
    0.0003,
    preserve_topology=True
)

folium.GeoJson(
    gdf_prc_mapa,
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

folium.LayerControl().add_to(m)

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
        gdf_prc,
        gdf_prms_uso,
        gdf_prms_lu,
        tolerancia_m
    )
