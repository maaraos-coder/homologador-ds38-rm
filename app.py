import streamlit as st
import geopandas as gpd
import pandas as pd
import folium
import zipfile
import unicodedata

from streamlit_folium import st_folium
from shapely.geometry import Point
from geopy.geocoders import Nominatim


# =========================================================
# CONFIGURACIÓN GENERAL
# =========================================================

st.set_page_config(
    page_title="Homologador DS38 RM",
    layout="wide"
)

st.title("Homologador DS38/11 MMA")
st.subheader("Región Metropolitana - Motor PRC + PRMS + Tabla Normativa")

if st.button("Limpiar caché"):
    st.cache_data.clear()
    st.success("Caché eliminada correctamente.")
    st.rerun()

st.warning(
    "Herramienta de apoyo técnico para homologación preliminar de zonas DS38/11 MMA. "
    "El resultado debe ser verificado con el Instrumento de Planificación Territorial vigente, "
    "la cartografía oficial, la Ordenanza correspondiente y la Res. Ex. SMA N°491/2016 antes de su uso formal."
)

ZIP_PATH = "data/IPTMetropolitana.zip"
TABLA_HOMOLOGACION_PATH = "rules/homologacion_prc.csv"


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
    texto = " ".join(texto.split())
    return texto.strip()


def texto_atributos(fila):
    valores = []

    for col in fila.index:
        if col == "geometry":
            continue
        try:
            valores.append(str(fila.get(col, "")))
        except Exception:
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


def crear_gdf_vacio():
    return gpd.GeoDataFrame(
        {
            "COMUNA": [],
            "ZONA": [],
            "NOMBRE": [],
            "UPERM": [],
            "UPREF": [],
            "UPROH": [],
            "SUELO": [],
            "DECRETO": [],
            "PLANO": [],
            "fuente_normativa": [],
            "archivo_origen": [],
            "observacion_jerarquia": []
        },
        geometry=[],
        crs="EPSG:4326"
    )


# =========================================================
# TABLA MAESTRA DE HOMOLOGACIÓN
# =========================================================

@st.cache_data
def cargar_tabla_homologacion():
    try:
        return pd.read_csv(TABLA_HOMOLOGACION_PATH)
    except Exception:
        return pd.DataFrame()


def homologar_por_tabla_prc(comuna, zona_prc, nombre_zona):
    tabla = cargar_tabla_homologacion()

    if tabla.empty:
        return None

    tabla = tabla.copy()

    comuna_norm = normalizar(comuna)
    zona_norm = normalizar(zona_prc)
    nombre_norm = normalizar(nombre_zona)

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
        and "poligono" not in a.lower()
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
# ÍNDICE DE COMUNAS
# =========================================================

@st.cache_data
def crear_indice_comunas():
    indice = {}

    for shp in listar_shapefiles():

        nombre_archivo = shp.split("/")[-1]

        if not shp.endswith(".shp"):
            continue

        if "Patrimonio" in shp:
            continue

        if "ZNE" in shp:
            continue

        if "poligono" in shp.lower():
            continue

        if (
            "/PRC/" not in shp
            and "/PRI/" not in shp
            and "PNSECC" not in shp
        ):
            continue

        comuna = nombre_archivo

        reemplazos = [
            "IPT_13_PRC_",
            "IPT_13_PRI_",
            "IPT_13_PNSECC_",
            ".shp"
        ]

        for r in reemplazos:
            comuna = comuna.replace(r, "")

        comuna = comuna.replace("_", " ")
        comuna = comuna.strip()

        especiales = {
            "Nunoa AP": "Ñuñoa",
            "Pudahuel San Francisco": "Pudahuel"
        }

        if comuna in especiales:
            comuna = especiales[comuna]

        basura = [
            " AP",
            " Rural",
            " Urbano"
        ]

        for b in basura:
            if comuna.endswith(b):
                comuna = comuna.replace(b, "").strip()

        clave = normalizar(comuna)

        if clave not in indice:
            indice[clave] = {
                "nombre": comuna,
                "archivo": shp
            }

    faltantes = {
        "alhue": "Alhué",
        "buin": "Buin",
        "calera de tango": "Calera de Tango",
        "el monte": "El Monte",
        "lampa": "Lampa",
        "maria pinto": "María Pinto",
        "san jose de maipo": "San José de Maipo",
        "san pedro": "San Pedro",
        "tiltil": "Tiltil"
    }

    for clave, nombre in faltantes.items():
        if clave not in indice:
            indice[clave] = {
                "nombre": nombre,
                "archivo": None
            }

    return indice


# =========================================================
# CARGA Y NORMALIZACIÓN DE CAPAS
# =========================================================

@st.cache_data
def cargar_shp(shp):
    if not shp:
        return crear_gdf_vacio()

    ruta = f"zip://{ZIP_PATH}!{shp}"

    gdf = gpd.read_file(ruta)
    gdf = gdf.to_crs(epsg=4326)
    gdf["archivo_origen"] = shp

    return gdf


def normalizar_columnas(gdf):
    if gdf.empty:
        return crear_gdf_vacio()

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


def filtrar_por_comuna(gdf, nombre_comuna):
    if gdf.empty or "COMUNA" not in gdf.columns:
        return crear_gdf_vacio()

    comuna_norm = normalizar(nombre_comuna)

    gdf_filtrado = gdf[
        gdf["COMUNA"].apply(normalizar) == comuna_norm
    ].copy()

    if gdf_filtrado.empty:
        return crear_gdf_vacio()

    return gdf_filtrado


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
# HOMOLOGACIÓN DS38
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

    # Regla específica PRMS: Zona Habitacional Mixta
    if (
        "zona habitacional mixto" in texto_norm
        or "zona habitacional mixta" in texto_norm
        or "habitacional mixto" in texto_norm
        or "habitacional mixta" in texto_norm
    ):
        return {"R", "Eq", "AP", "Inf"}

    # Residencial
    if (
        "residencial" in texto_norm
        or "vivienda" in texto_norm
        or "habitacional" in texto_norm
        or "habitacionales" in texto_norm
    ):
        categorias.add("R")

    # Equipamiento
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

    # =====================================================
    # ACTIVIDADES PRODUCTIVAS
    # CRITERIO SMA 491/2016
    # Las actividades productivas INOFENSIVAS
    # se homologan como Equipamiento.
    # =====================================================

    actividad_productiva_detectada = (
        "actividad productiva" in texto_norm
        or "actividades productivas" in texto_norm
        or "productiva" in texto_norm
        or "productivas" in texto_norm
        or "industrial" in texto_norm
        or "industria" in texto_norm
        or "taller" in texto_norm
        or "talleres" in texto_norm
        or "bodega" in texto_norm
        or "bodegas" in texto_norm
        or "almacenamiento" in texto_norm
        or "servicio de caracter industrial" in texto_norm
        or "servicios de caracter industrial" in texto_norm
        or "zona industrial" in texto_norm
        or "industrial exclusiva" in texto_norm
    )

    actividad_productiva_inofensiva = (
        "actividad productiva inofensiva" in texto_norm
        or "actividades productivas inofensivas" in texto_norm
        or "industria inofensiva" in texto_norm
        or "industrial inofensiva" in texto_norm
        or "industrial inofensivo" in texto_norm
        or "taller inofensivo" in texto_norm
        or "talleres inofensivos" in texto_norm
        or "almacenamiento inofensivo" in texto_norm
        or "bodega inofensiva" in texto_norm
        or "bodegas inofensivas" in texto_norm
    )

    actividad_productiva_no_inofensiva = (
        "molesta" in texto_norm
        or "molestas" in texto_norm
        or "insalubre" in texto_norm
        or "insalubres" in texto_norm
        or "contaminante" in texto_norm
        or "contaminantes" in texto_norm
        or "peligrosa" in texto_norm
        or "peligrosas" in texto_norm
        or "industrial exclusiva" in texto_norm
        or "industria exclusiva" in texto_norm
    )

    if actividad_productiva_detectada:

        if actividad_productiva_inofensiva and not actividad_productiva_no_inofensiva:
            categorias.add("Eq")
        else:
            categorias.add("AP")

    # Infraestructura
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

    # Área Verde
    if (
        "area verde" in texto_norm
        or "areas verdes" in texto_norm
        or "parque" in texto_norm
        or "plaza" in texto_norm
        or "recreacion" in texto_norm
    ):
        categorias.add("AV")

    # Espacio Público
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
        return (
            "Zona I",
            "55 dBA",
            "45 dBA",
            "AV/EP solos o combinados entre sí se homologan a Zona I."
        )

    if (
        ("AP" in cats or "Inf" in cats)
        and "R" not in cats
        and "Eq" not in cats
    ):
        return (
            "Zona IV",
            "70 dBA",
            "70 dBA",
            "Actividad Productiva y/o Infraestructura sin uso Residencial ni Equipamiento."
        )

    if "AP" in cats or "Inf" in cats:
        return (
            "Zona III",
            "65 dBA",
            "50 dBA",
            "Combinación con Actividad Productiva y/o Infraestructura junto a R/Eq/AV/EP."
        )

    if "Eq" in cats:
        return (
            "Zona II",
            "60 dBA",
            "45 dBA",
            "Combinación con Equipamiento, sin Actividad Productiva ni Infraestructura."
        )

    if "R" in cats:
        return (
            "Zona I",
            "55 dBA",
            "45 dBA",
            "Uso Residencial solo o combinado únicamente con Área Verde/Espacio Público."
        )

    return (
        "No clasificada",
        "-",
        "-",
        "No se detectaron categorías suficientes para homologar automáticamente."
    )


def homologar_ds38(fila, estado_lu=None):
    if estado_lu == "Fuera de límite urbano PRMS / área rural":
        return (
            "Zona Rural",
            "Rf + 10 dBA, con tope Zona III",
            "Rf + 10 dBA, con tope Zona III",
            "El punto se encuentra fuera del límite urbano PRMS; corresponde evaluación como Zona Rural del D.S. N°38/2011 MMA.",
            "Rural"
        )

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

    if gdf.empty:
        return gpd.GeoDataFrame()

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
        return gpd.GeoDataFrame()

    try:
        punto_m = punto.to_crs(epsg=32719)
        gdf_m = gdf.to_crs(epsg=32719).copy()

        punto_geom = punto_m.geometry.iloc[0]

        gdf_m["distancia_m"] = gdf_m.geometry.distance(punto_geom)

        cercanos = gdf_m[gdf_m["distancia_m"] <= tolerancia_m].copy()

        if cercanos.empty:
            return gpd.GeoDataFrame()

        cercano = cercanos.sort_values("distancia_m").iloc[[0]].copy()
        distancia = round(float(cercano.iloc[0]["distancia_m"]), 2)

        cercano = cercano.to_crs(epsg=4326)
        cercano["id"] = 1
        cercano["metodo_busqueda"] = "Por tolerancia espacial"
        cercano["distancia_m"] = distancia

        return cercano

    except Exception:
        return gpd.GeoDataFrame()


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
    resultado_prc = buscar_punto_en_capa(
        lat,
        lon,
        gdf_prc,
        tolerancia_m
    )

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

    return gpd.GeoDataFrame()


# =========================================================
# RESULTADOS
# =========================================================

def mostrar_resultado(lat, lon, gdf_prc, gdf_prms_uso, gdf_prms_lu, tolerancia_m):
    estado_lu, detalle_lu = detectar_limite_urbano_prms(
        lat,
        lon,
        gdf_prms_lu
    )

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
            "Se homologa preliminarmente como Zona Rural del D.S. N°38/2011 MMA."
        )

    if resultado.empty:
        st.warning("No se encontró información territorial para el punto.")
        return

    fila = resultado.iloc[0]

    zona_ds38, limite_dia, limite_noche, criterio, categorias = homologar_ds38(
        fila,
        estado_lu
    )

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
        st.info(
            "Homologación aplicada desde tabla maestra PRC validada por ordenanza comunal."
        )

    advertencia_lu = ""
    if estado_lu == "Fuera de límite urbano PRMS / área rural":
        advertencia_lu = (
            " Asimismo, el punto se encuentra fuera del límite urbano PRMS, "
            "por lo que corresponde su evaluación como Zona Rural del D.S. N°38/2011 MMA."
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

El punto presenta la siguiente clasificación territorial según la capa PRMS_LU: {estado_lu}. Conforme a los criterios establecidos en la Resolución Exenta N°491/2016 de la Superintendencia del Medio Ambiente y el D.S. N°38/2011 del MMA, la zona se homologa preliminarmente como {zona_ds38}, con límite máximo permisible de {limite_dia} en periodo diurno y {limite_noche} en periodo nocturno.{advertencia_jerarquia}{advertencia_lu}{advertencia_tol}
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

if "comuna_actual" not in st.session_state:
    st.session_state.comuna_actual = comuna_clave

if st.session_state.comuna_actual != comuna_clave:
    st.session_state.lat = None
    st.session_state.lon = None
    st.session_state.comuna_actual = comuna_clave

comuna_info = indice[comuna_clave]


# =========================================================
# CARGA PRC
# =========================================================

if comuna_info["archivo"]:
    gdf_prc = cargar_shp(comuna_info["archivo"])
    gdf_prc = normalizar_columnas(gdf_prc)
    gdf_prc["fuente_normativa"] = "PRC"
else:
    gdf_prc = crear_gdf_vacio()


# =========================================================
# CARGA PRMS
# =========================================================

capa_prms_lu = buscar_capa_prms_lu()
capa_prms_uso = buscar_capa_prms_uso_suelo()

gdf_prms_lu_total = cargar_shp(capa_prms_lu) if capa_prms_lu else crear_gdf_vacio()
gdf_prms_uso_total = cargar_shp(capa_prms_uso) if capa_prms_uso else crear_gdf_vacio()

gdf_prms_lu_total = normalizar_columnas(gdf_prms_lu_total)
gdf_prms_uso_total = normalizar_columnas(gdf_prms_uso_total)


# =========================================================
# RECORTE PRMS POR COMUNA
# =========================================================

if not gdf_prc.empty:
    xmin, ymin, xmax, ymax = gdf_prc.total_bounds

    try:
        gdf_prms_lu = gdf_prms_lu_total.cx[
            xmin:xmax,
            ymin:ymax
        ].copy()
    except Exception:
        gdf_prms_lu = gdf_prms_lu_total.copy()

    try:
        gdf_prms_uso = gdf_prms_uso_total.cx[
            xmin:xmax,
            ymin:ymax
        ].copy()
    except Exception:
        gdf_prms_uso = gdf_prms_uso_total.copy()

else:
    gdf_prms_uso = filtrar_por_comuna(
        gdf_prms_uso_total,
        comuna_info["nombre"]
    )

    if not gdf_prms_uso.empty:
        xmin, ymin, xmax, ymax = gdf_prms_uso.total_bounds

        try:
            gdf_prms_lu = gdf_prms_lu_total.cx[
                xmin:xmax,
                ymin:ymax
            ].copy()
        except Exception:
            gdf_prms_lu = gdf_prms_lu_total.copy()

    else:
        gdf_prms_lu = filtrar_por_comuna(
            gdf_prms_lu_total,
            comuna_info["nombre"]
        )

gdf_prms_lu = normalizar_columnas(gdf_prms_lu)
gdf_prms_lu["fuente_normativa"] = "PRMS_LU"

gdf_prms_uso = normalizar_columnas(gdf_prms_uso)
gdf_prms_uso["fuente_normativa"] = "PRMS_USO_Suelo"

st.success(
    f"Comuna seleccionada: {comuna_info['nombre']} | "
    f"Polígonos PRC: {len(gdf_prc)} | "
    f"PRMS_LU comuna: {len(gdf_prms_lu)} | "
    f"PRMS_USO_Suelo comuna: {len(gdf_prms_uso)}"
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
# CENTROS COMUNALES DE RESPALDO
# =========================================================

CENTROS_COMUNAS = {
    "alhue": [-34.03, -71.10],
    "buin": [-33.73, -70.74],
    "calera de tango": [-33.67, -70.82],
    "el monte": [-33.68, -70.98],
    "lampa": [-33.29, -70.88],
    "maria pinto": [-33.51, -71.13],
    "san jose de maipo": [-33.64, -70.35],
    "san pedro": [-33.90, -71.47],
    "tiltil": [-33.08, -70.93]
}


# =========================================================
# MAPA
# =========================================================

centro = [-33.45, -70.66]

try:
    if not gdf_prc.empty:
        bounds = gdf_prc.total_bounds

        if not pd.isna(bounds).any():
            centro = [
                (bounds[1] + bounds[3]) / 2,
                (bounds[0] + bounds[2]) / 2
            ]

    elif not gdf_prms_uso.empty:
        bounds = gdf_prms_uso.total_bounds

        if not pd.isna(bounds).any():
            centro = [
                (bounds[1] + bounds[3]) / 2,
                (bounds[0] + bounds[2]) / 2
            ]

    else:
        clave_centro = normalizar(comuna_info["nombre"])

        if clave_centro in CENTROS_COMUNAS:
            centro = CENTROS_COMUNAS[clave_centro]

except Exception:
    centro = [-33.45, -70.66]

if st.session_state.lat is not None and st.session_state.lon is not None:
    centro = [
        st.session_state.lat,
        st.session_state.lon
    ]

m = folium.Map(
    location=centro,
    zoom_start=13
)

# Capa invisible clickeable
folium.Rectangle(
    bounds=[
        [-34.35, -71.75],
        [-32.75, -69.75]
    ],
    color=None,
    fill=True,
    fill_opacity=0.01,
    weight=0,
    interactive=True,
    name="Área clickeable"
).add_to(m)


# PRMS_LU
try:
    gdf_prms_lu_mapa = gdf_prms_lu.copy()

    if not gdf_prms_lu_mapa.empty:
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

except Exception:
    pass


# PRMS_USO_Suelo
try:
    gdf_prms_uso_mapa = gdf_prms_uso.copy()

    if not gdf_prms_uso_mapa.empty:
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
                fields=[
                    col for col in ["NOMBRE", "UPERM"]
                    if col in gdf_prms_uso_mapa.columns
                ],
                aliases=[
                    alias for col, alias in zip(
                        ["NOMBRE", "UPERM"],
                        ["Nombre PRMS", "Uso permitido"]
                    )
                    if col in gdf_prms_uso_mapa.columns
                ]
            )
        ).add_to(m)

except Exception:
    pass


# PRC comuna seleccionada
try:
    if not gdf_prc.empty:
        gdf_prc_mapa = gdf_prc.copy()

        gdf_prc_mapa["geometry"] = gdf_prc_mapa.geometry.simplify(
            0.0003,
            preserve_topology=True
        )

        folium.GeoJson(
            gdf_prc_mapa,
            name=f"PRC {comuna_info['nombre']}",
            tooltip=folium.GeoJsonTooltip(
                fields=[
                    col for col in ["COMUNA", "ZONA", "NOMBRE"]
                    if col in gdf_prc_mapa.columns
                ],
                aliases=[
                    alias for col, alias in zip(
                        ["COMUNA", "ZONA", "NOMBRE"],
                        ["Comuna", "Zona", "Nombre"]
                    )
                    if col in gdf_prc_mapa.columns
                ]
            )
        ).add_to(m)

except Exception:
    pass


if st.session_state.lat is not None and st.session_state.lon is not None:
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

if map_data and map_data.get("last_clicked"):
    st.session_state.lat = map_data["last_clicked"]["lat"]
    st.session_state.lon = map_data["last_clicked"]["lng"]
    st.rerun()


# =========================================================
# RESULTADO FINAL
# =========================================================

if st.session_state.lat is not None and st.session_state.lon is not None:
    mostrar_resultado(
        st.session_state.lat,
        st.session_state.lon,
        gdf_prc,
        gdf_prms_uso,
        gdf_prms_lu,
        tolerancia_m
    )
