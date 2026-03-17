import streamlit as st
from groq import Groq
import json
import re
import subprocess
import sys
import uuid

# Instalación de librería para PDF si no existe
try:
    from fpdf import FPDF
except ImportError:
    subprocess.check_call([sys.executable, "-m", "pip", "install", "fpdf2"])
    from fpdf import FPDF

# --- CONFIGURACIÓN DE PÁGINA (LOGO EN PESTAÑA) ---
st.set_page_config(
    page_title="YSi Recetas", 
    page_icon="logo.png", 
    layout="centered", 
    initial_sidebar_state="expanded"
)

# --- DISEÑO PREMIUM Y LIMPIEZA DE INTERFAZ ---
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Lora:ital,wght@0,500;0,700;1,500&family=Poppins:wght@300;400;500;600;700&display=swap');
    
    /* Ocultar elementos innecesarios de Streamlit */
    [data-testid="stHeaderActionElements"] { display: none !important; }
    #MainMenu { display: none !important; }
    footer { display: none !important; }
    header { background-color: transparent !important; }
    
    /* FONDO LIMPIO CON ICONOS DE COCINA REALES */
    .stApp { 
        background-color: #F4F7F4; 
        background-image: 
            url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24'%3E%3Cpath fill='%236A856A' fill-opacity='0.12' d='M11 9H9V2H7v7H5V2H3v7c0 2.12 1.66 3.84 3.75 3.97V22h1.5v-9.03C10.34 12.84 12 11.12 12 9V2h-1v7zm5-7v7h2.5V22H20V2h-4z'/%3E%3C/svg%3E"),
            url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24'%3E%3Cpath fill='%236A856A' fill-opacity='0.12' d='M12 2C6.5 2 2 6.5 2 12v1h20v-1c0-5.5-4.5-10-10-10zm0 2c4.4 0 8 3.6 8 8H4c0-4.4 3.6-8 8-8zM2 14v2h20v-2H2z'/%3E%3C/svg%3E"),
            url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24'%3E%3Cpath fill='%236A856A' fill-opacity='0.12' d='M21 3H3v2l8 9v5H8v2h8v-2h-3v-5l8-9V3zm-2.8 2l-1.8 2H7.6L5.8 5h12.4z'/%3E%3C/svg%3E"),
            url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24'%3E%3Cpath fill='%236A856A' fill-opacity='0.12' d='M12 3a7 7 0 00-6.3 4.1C3.5 7.6 2 9.6 2 12c0 2.8 2.2 5 5 5h10c2.8 0 5-2.2 5-5 0-2.4-1.5-4.4-3.7-4.9A7 7 0 0012 3zm0 2c2.4 0 4.5 1.5 5.3 3.6.2.6.8 1.1 1.4 1.1 1.6.2 2.8 1.5 2.8 3.3 0 1.7-1.3 3-3 3H7c-1.7 0-3-1.3-3-3 0-1.8 1.2-3.1 2.8-3.3.6 0 1.2-.5 1.4-1.1C9.1 6.5 10.4 5 12 5zm-4 11v2h8v-2H8z'/%3E%3C/svg%3E");
        background-position: 30px 40px, calc(100% - 30px) 40px, 30px calc(100% - 40px), calc(100% - 30px) calc(100% - 40px); 
        background-repeat: no-repeat;
        background-attachment: fixed;
        background-size: 150px 150px; 
        color: #2D3A2D; 
        font-family: 'Poppins', sans-serif; 
    }
    
    h1, h2, h3, .serif-title { font-family: 'Lora', serif !important; color: #1E2B1E !important; }
    
    .recipe-card { 
        background: #FFFFFF; 
        border-radius: 16px; 
        padding: 40px; 
        box-shadow: 0 10px 40px rgba(45, 58, 45, 0.08); 
        margin-bottom: 30px; 
        margin-top: 10px;
        border: 1px solid #DCE6DC;
        position: relative; 
        z-index: 10;
    }
    
    .recipe-meta {
        background-color: #F5F9F5;
        color: #4A804D; 
        font-weight: 600;
        font-size: 0.95rem;
        text-transform: uppercase;
        letter-spacing: 1px;
        margin-bottom: 25px;
        padding: 10px 15px;
        border-radius: 8px;
        display: inline-block;
        border: 1px solid #DCE6DC;
    }
    
    .stButton>button, .stDownloadButton>button { 
        background-color: #1E2B1E !important; 
        color: #FFFFFF !important; 
        border-radius: 10px !important; 
        font-weight: 600 !important; 
        width: 100%; 
        height: 3.2em; 
        border: none !important;
        text-transform: uppercase;
        letter-spacing: 1px;
        font-family: 'Poppins', sans-serif;
        transition: all 0.3s ease;
    }
    .stButton>button:hover, .stDownloadButton>button:hover {
        background-color: #4A804D !important; 
        color: #FFFFFF !important;
        box-shadow: 0 4px 12px rgba(74, 128, 77, 0.3);
    }
</style>
""", unsafe_allow_html=True)

GROQ_API_KEY = st.secrets["GROQ_API_KEY"]

# --- FUNCIONES DE APOYO ---
def obtener_texto_seguro(valor, por_defecto=""): return str(valor) if not isinstance(valor, float) and valor else por_defecto
def limpiar_texto_pdf(texto): return str(texto).replace('•', '-').replace('–', '-').replace('—', '-').encode('latin-1', 'ignore').decode('latin-1').strip()
def procesar_lista(datos_brutos):
    if isinstance(datos_brutos, float): return []
    lista = datos_brutos if isinstance(datos_brutos, list) else [x.strip() for x in str(datos_brutos).split('|') if x.strip()]
    return [str(item).strip() for item in lista if len(str(item).strip()) >= 5 and not re.fullmatch(r'^-?\s*\d+\s*[a-zA-Z]{1,2}\.?$', str(item).strip())]

def generar_pdf(titulo, ingredientes, pasos, tiempo, kcal):
    pdf = FPDF()
    pdf.add_page()
    pdf.set_auto_page_break(auto=True, margin=15)
    ancho_max = 190
    pdf.set_font("helvetica", "B", 22)
    pdf.set_text_color(30, 43, 30)
    pdf.multi_cell(ancho_max, 10, limpiar_texto_pdf(titulo), align='C')
    pdf.ln(5)
    pdf.set_font("helvetica", "I", 10)
    pdf.set_text_color(74, 128, 77)
    pdf.cell(ancho_max, 8, limpiar_texto_pdf(f"TIEMPO: {tiempo} | CALORÍAS: {kcal}"), align='C', ln=True)
    pdf.ln(8)
    pdf.set_font("helvetica", "B", 12)
    pdf.set_text_color(30, 43, 30)
    pdf.cell(ancho_max, 8, "INGREDIENTES:", ln=True)
    pdf.set_font("helvetica", "", 11)
    pdf.set_text_color(60, 60, 60)
    for ing in ingredientes: pdf.multi_cell(ancho_max, 6, f"- {limpiar_texto_pdf(ing)}" if not limpiar_texto_pdf(ing).startswith("-") else limpiar_texto_pdf(ing))
    pdf.ln(5)
    pdf.set_font("helvetica", "B", 12)
    pdf.set_text_color(30, 43, 30)
    pdf.cell(ancho_max, 8, "ELABORACIÓN:", ln=True)
    pdf.set_font("helvetica", "", 10)
    for idx, p in enumerate(pasos): pdf.multi_cell(ancho_max, 5, f"{idx+1}. {re.sub(r'^-\s*', '', limpiar_texto_pdf(p))}"); pdf.ln(2)
    return bytes(pdf.output())

def generar_receta(ingredientes, tiempo, tipo, alergenos, es_sorpresa=False):
    client = Groq(api_key=GROQ_API_KEY)
    regla_tiempo = "Tiempo ILIMITADO. Slow Food." if "+2h" in str(tiempo) else f"Ajusta las técnicas para {tiempo}."
    regla_alergenos = f"PROHIBIDO USAR: {alergenos}. Excluye derivados." if alergenos else "Ninguna restricción."
    instruccion_ingredientes = "Diseña una receta de autor, creativa, equilibrada y con técnicas de alta cocina." if es_sorpresa else f"Diseña una receta con: {ingredientes}."

    prompt = f"""Eres un Chef Ejecutivo. Diseña una receta de {tipo}. {instruccion_ingredientes}
    REGLAS:
    1. TIEMPO: {regla_tiempo}
    2. CALORÍAS: Número realista y añade 'kcal'.
    3. ALÉRGENOS: {regla_alergenos}
    Devuelve EXACTAMENTE este formato JSON:
    {{"titulo": "Nombre del plato", "tiempo": "{tiempo}", "calorias": "500 kcal", "ingredientes": ["ingrediente 1"], "pasos": ["paso 1"]}}"""
    try:
        chat = client.chat.completions.create(messages=[{"role":"user","content":prompt}], model="llama-3.3-70b-versatile", temperature=0.6 if es_sorpresa else 0.2, response_format={"type": "json_object"})
        return json.loads(chat.choices[0].message.content)
    except: return None

def mostrar_tarjeta(r):
    t = obtener_texto_seguro(r.get('Titulo') or r.get('titulo') or r.get('Título'), "Receta de Chef")
    tiempo = obtener_texto_seguro(r.get('Tiempo') or r.get('tiempo'), "")
    kcal = obtener_texto_seguro(r.get('Calorias') or r.get('calorias') or r.get('kcal') or r.get('Kcal'), "")
    ing_lista, pas_lista = procesar_lista(r.get('Ingredientes') or r.get('ingredientes')), procesar_lista(r.get('Pasos') or r.get('pasos'))
    id_unico = str(uuid.uuid4())[:8] 

    st.markdown('<div class="recipe-card">', unsafe_allow_html=True)
    st.markdown(f'<h2 class="serif-title" style="margin-top:0px; font-size: 2.2rem; margin-bottom:15px;">🍽️ {t}</h2>', unsafe_allow_html=True)
    info_texto = ("" if not tiempo or tiempo.upper() == "N/A" else f"⏱️ {tiempo} &nbsp;&nbsp;&nbsp;&nbsp;|&nbsp;&nbsp;&nbsp;&nbsp; ") + ("" if not kcal or kcal.upper() == "N/A" else f"🔥 {kcal}")
    if info_texto: st.markdown(f'<div class="recipe-meta">{info_texto}</div>', unsafe_allow_html=True)
    st.write("### 🛒 Ingredientes")
    for i in ing_lista: st.write(f"- {i}")
    st.write("---")
    st.write("### 👨‍🍳 Elaboración")
    for idx, p in enumerate(pas_lista): st.write(f"**{idx+1}.** {p}")
    st.write("") 
    
    pdf_b = generar_pdf(t, ing_lista, pas_lista, tiempo, kcal)
    st.download_button("📄 Descargar Receta en PDF", data=pdf_b, file_name=f"{t.replace(' ', '_')}.pdf", mime="application/pdf", key=f"pdf_{id_unico}")
    st.markdown("</div>", unsafe_allow_html=True)

# --- NAVEGACIÓN CORPORATIVA ---
with st.sidebar:
    st.markdown("### 🌐 Navegación")
    pagina_actual = st.radio("", ["App de Cocina", "Sobre Nosotros", "Preguntas Frecuentes", "Aviso Legal y Privacidad"])

# --- RENDERIZADO DE PÁGINAS ---
if pagina_actual == "App de Cocina":
    # INTEGRACIÓN DEL LOGO CENTRADO
    st.write("")
    col_l1, col_l2, col_l3 = st.columns([1, 1.5, 1])
    with col_l2:
        try:
            st.image("logo.png", use_container_width=True)
        except:
            st.markdown("<h1 class='brand-title'>YSi Recetas</h1>", unsafe_allow_html=True)
    st.write("")
    
    col1, col2 = st.columns(2)
    with col1: tipo = st.selectbox("Categoría del Plato", ["Comida", "Cena", "Postre"])
    with col2: t_slider = st.select_slider("Tiempo de Elaboración", ["15 min", "30 min", "45 min", "60 min", "120 min", "+2h (Slow Food)"], value="30 min")
        
    ing_input = st.text_area("Ingredientes Base (Opcional)", placeholder="Ej: Gamba roja, ajos tiernos... ¿Te atreves a retar al Chef?")
    alergenos_input = st.text_input("🚫 Excluir Alérgenos (Opcional)", placeholder="Ej: Gluten, lactosa...")
    
    st.write("")
    if st.button("COMENZAR CREACIÓN", use_container_width=True):
        es_sorpresa = not ing_input.strip()
        mensaje_spinner = "✨ Dejando volar la imaginación del Chef..." if es_sorpresa else "👨‍🍳 Procesando técnicas culinarias..."
        with st.spinner(mensaje_spinner):
            resultado = generar_receta(ing_input, t_slider, tipo, alergenos_input, es_sorpresa)
            if resultado: st.session_state.actual = resultado
            else: st.error("⚠️ Error en los fogones. Inténtalo de nuevo.")
            
    if 'actual' in st.session_state: 
        st.markdown("---")
        mostrar_tarjeta(st.session_state.actual)

elif pagina_actual == "Sobre Nosotros":
    col_l1, col_l2, col_l3 = st.columns([1, 1, 1])
    with col_l2:
        try: st.image("logo.png", use_container_width=True)
        except: pass
    st.markdown("<h1 class='serif-title' style='text-align:center; font-size: 2rem; margin-top:-10px;'>La Nostra Missió</h1>", unsafe_allow_html=True)
    st.markdown('<div class="recipe-card">', unsafe_allow_html=True)
    st.write("YSi Recetas neix de la idea que qualsevol pot gaudir de l'alta cuina amb el que té a casa. Utilitzem IA per reduir el malbaratament alimentari i democratitzar la gastronomia d'autor.")
    st.markdown('</div>', unsafe_allow_html=True)

elif pagina_actual == "Preguntas Frecuentes":
    st.markdown("<h1 class='serif-title' style='text-align:center; font-size: 3rem;'>FAQ</h1>", unsafe_allow_html=True)
    st.markdown('<div class="recipe-card">', unsafe_allow_html=True)
    with st.expander("¿Se guardan mis recetas?"):
        st.write("No. Las recetas se generan al momento y son efímeras. Descárgalas en PDF si te gustan.")
    st.markdown('</div>', unsafe_allow_html=True)

elif pagina_actual == "Aviso Legal y Privacidad":
    st.markdown("<h1 class='serif-title' style='text-align:center; font-size: 3rem;'>Legal</h1>", unsafe_allow_html=True)
    st.markdown('<div class="recipe-card">', unsafe_allow_html=True)
    st.write("Prototip tecnològic creat amb finalitats acadèmiques. Totes les dades es processen en temps real sense emmagatzematge extern.")
    st.markdown('</div>', unsafe_allow_html=True)
