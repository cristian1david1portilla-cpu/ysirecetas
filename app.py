import streamlit as st
from groq import Groq
from streamlit_gsheets import GSheetsConnection
import pandas as pd
import json
import re
import requests
import subprocess
import sys

try:
    from fpdf import FPDF
except ImportError:
    subprocess.check_call([sys.executable, "-m", "pip", "install", "fpdf2"])
    from fpdf import FPDF

# --- MARCA Y DISEÑO: LUJO MINIMALISTA ---
st.set_page_config(page_title="¿Y Si Recetas? | Alta Cocina", page_icon="🍽️", layout="centered")

st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Playfair+Display:ital,wght@0,400;0,700;1,400&family=Inter:wght@300;400;600&display=swap');
    
    /* Fondo blanco puro, texto negro carbón */
    .stApp { background-color: #FFFFFF; color: #111111; font-family: 'Inter', sans-serif; }
    
    /* Tipografía Serif para títulos (Estilo Menú de Restaurante) */
    h1, h2, h3, .serif-title { font-family: 'Playfair Display', serif !important; color: #000000 !important; }
    
    .brand-title { text-align: center; font-size: 3.5rem !important; margin-top: 1rem; margin-bottom: 0rem; letter-spacing: 2px; text-transform: uppercase;}
    .brand-subtitle { text-align: center; font-size: 1rem; color: #666666; letter-spacing: 4px; text-transform: uppercase; margin-bottom: 2rem;}
    
    /* Tarjetas limpias con acento dorado */
    .recipe-card { 
        background: #FFFFFF;
        border-top: 4px solid #D4AF37; /* Dorado Michelin */
        border-bottom: 1px solid #EEEEEE;
        border-left: 1px solid #EEEEEE;
        border-right: 1px solid #EEEEEE;
        padding: 40px; 
        box-shadow: 0 20px 40px rgba(0,0,0,0.05); 
        margin-bottom: 30px; 
        margin-top: 20px;
    }
    
    /* Metadatos en gris elegante */
    .recipe-meta {
        color: #555555;
        font-weight: 600;
        font-size: 0.95rem;
        text-transform: uppercase;
        letter-spacing: 1px;
        margin-bottom: 25px;
        border-bottom: 1px solid #EEEEEE;
        padding-bottom: 15px;
    }
    
    /* Botones oscuros y elegantes */
    .stButton>button, .stDownloadButton>button { 
        background-color: #111111 !important; 
        color: #FFFFFF !important; 
        border-radius: 0px !important; /* Bordes rectos, más serios */
        font-weight: 600 !important; 
        width: 100%; 
        height: 3em; 
        border: none !important;
        text-transform: uppercase;
        letter-spacing: 1px;
        transition: all 0.3s ease;
    }
    .stButton>button:hover, .stDownloadButton>button:hover {
        background-color: #D4AF37 !important; /* Dorado al pasar el ratón */
        color: #111111 !important;
    }
    
    /* Ocultar elementos feos de Streamlit */
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
</style>
""", unsafe_allow_html=True)

URL_WEBHOOK = "https://script.google.com/macros/s/AKfycbwBkmZtEU_h0ApOyel01MKNx_7rjUArm8P1wGiH7EgTFO-WhMOmmcfG3sElcy7N3F1x/exec"
GROQ_API_KEY = st.secrets["GROQ_API_KEY"]

def obtener_texto_seguro(valor, por_defecto=""):
    if isinstance(valor, float): return por_defecto
    if not valor: return por_defecto
    return str(valor)

def limpiar_texto_pdf(texto):
    texto_limpio = str(texto).replace('•', '-').replace('–', '-').replace('—', '-')
    return texto_limpio.encode('latin-1', 'ignore').decode('latin-1').strip()

def procesar_lista(datos_brutos, es_paso=False):
    if isinstance(datos_brutos, float): return []
    lista = datos_brutos if isinstance(datos_brutos, list) else [x.strip() for x in str(datos_brutos).split('|') if x.strip()]
    limpia = []
    for item in lista:
        txt = str(item).strip()
        if len(txt) < 5: continue 
        if re.fullmatch(r'^-?\s*\d+\s*[a-zA-Z]{1,2}\.?$', txt): continue 
        limpia.append(txt)
    return limpia

def generar_pdf(titulo, ingredientes, pasos, tiempo, kcal):
    pdf = FPDF()
    pdf.add_page()
    pdf.set_auto_page_break(auto=True, margin=15)
    ancho_max = 190
    
    pdf.set_font("helvetica", "B", 22)
    pdf.set_text_color(17, 17, 17)
    pdf.multi_cell(ancho_max, 10, limpiar_texto_pdf(titulo), align='C')
    pdf.ln(5)

    pdf.set_font("helvetica", "I", 10)
    pdf.set_text_color(100, 100, 100)
    info_texto = f"TIEMPO: {tiempo} | CALORÍAS: {kcal}"
    pdf.cell(ancho_max, 8, limpiar_texto_pdf(info_texto), align='C', ln=True)
    pdf.ln(8)

    pdf.set_font("helvetica", "B", 12)
    pdf.set_text_color(17, 17, 17)
    pdf.cell(ancho_max, 8, "INGREDIENTES:", ln=True)
    pdf.set_font("helvetica", "", 11)
    pdf.set_text_color(50, 50, 50)
    
    for ing in ingredientes:
        txt = limpiar_texto_pdf(ing)
        if not txt.startswith("-"): txt = f"- {txt}"
        pdf.multi_cell(ancho_max, 6, txt)
    pdf.ln(5)
    
    pdf.set_font("helvetica", "B", 12)
    pdf.set_text_color(17, 17, 17)
    pdf.cell(ancho_max, 8, "ELABORACIÓN:", ln=True)
    pdf.set_font("helvetica", "", 10)
    
    for idx, p in enumerate(pasos):
        txt_p = limpiar_texto_pdf(p)
        txt_p = re.sub(r'^-\s*', '', txt_p)
        pdf.multi_cell(ancho_max, 5, f"{idx+1}. {txt_p}")
        pdf.ln(2)
            
    return bytes(pdf.output())

# --- IA RECETAS ---
def generar_receta(ingredientes, tiempo, tipo, alergenos):
    client = Groq(api_key=GROQ_API_KEY)
    
    regla_tiempo = f"Ajusta las técnicas para {tiempo}."
    if "+2h" in str(tiempo): regla_tiempo = "Tiempo ILIMITADO. Slow Food."
    
    regla_alergenos = f"ESTÁ PROHIBIDO USAR: {alergenos}. Excluye derivados." if alergenos else "Ninguna restricción."

    prompt = f"""Eres un Chef Ejecutivo. Diseña una receta de {tipo} con: {ingredientes}.
    
    REGLAS:
    1. TIEMPO: {regla_tiempo}
    2. CALORÍAS: Número realista y añade 'kcal'. NO escribas el tiempo aquí.
    3. ALÉRGENOS: {regla_alergenos}
    
    Devuelve EXACTAMENTE este formato JSON:
    {{
        "titulo": "Nombre del plato",
        "tiempo": "{tiempo}",
        "calorias": "500 kcal",
        "ingredientes": ["ingrediente 1"],
        "pasos": ["paso 1"]
    }}"""
    
    try:
        chat = client.chat.completions.create(
            messages=[{"role":"user","content":prompt}], 
            model="llama-3.3-70b-versatile",
            temperature=0.2, 
            response_format={"type": "json_object"}
        )
        return json.loads(chat.choices[0].message.content)
    except: 
        return None

# --- TARJETA DE RESULTADO ---
def mostrar_tarjeta(r, indice=0):
    t = obtener_texto_seguro(r.get('Titulo') or r.get('titulo') or r.get('Título'), "Receta de Chef")
    tiempo = obtener_texto_seguro(r.get('Tiempo') or r.get('tiempo'), "")
    kcal = obtener_texto_seguro(r.get('Calorias') or r.get('calorias') or r.get('kcal') or r.get('Kcal'), "")
    
    ing_lista = procesar_lista(r.get('Ingredientes') or r.get('ingredientes'), es_paso=False)
    pas_lista = procesar_lista(r.get('Pasos') or r.get('pasos'), es_paso=True)

    st.markdown('<div class="recipe-card">', unsafe_allow_html=True)
    
    st.markdown(f'<h2 class="serif-title" style="margin-top:0px; font-size: 2.2rem; margin-bottom:10px;">{t}</h2>', unsafe_allow_html=True)
    
    info_texto = ""
    if tiempo and tiempo.upper() != "N/A": info_texto += f"⏱️ {tiempo} &nbsp;&nbsp;&nbsp;&nbsp;|&nbsp;&nbsp;&nbsp;&nbsp; "
    if kcal and kcal.upper() != "N/A": info_texto += f"🔥 {kcal}"
        
    if info_texto:
        st.markdown(f'<div class="recipe-meta">{info_texto}</div>', unsafe_allow_html=True)

    st.write("### 🛒 Ingredientes")
    for i in ing_lista: st.write(f"- {i}")
    st.write("---")
    st.write("### 👨‍🍳 Elaboración")
    for idx, p in enumerate(pas_lista): st.write(f"**{idx+1}.** {p}")
    
    st.write("") 
    c1, c2 = st.columns(2)
    with c1:
        if st.button("💾 Guardar Menú", key=f"sv_{indice}"):
            payload = {"Titulo": t, "Ingredientes": " | ".join(ing_lista), "Pasos": " | ".join(pas_lista), "Tiempo": tiempo, "Calorias": kcal}
            requests.post(URL_WEBHOOK, json=payload)
            st.toast("✅ Añadido a tu colección privada")
    with c2:
        nombre_archivo = f"{t.replace(' ', '_')}.pdf"
        pdf_b = generar_pdf(t, ing_lista, pas_lista, tiempo, kcal)
        st.download_button("📄 Imprimir PDF", data=pdf_b, file_name=nombre_archivo, mime="application/pdf", key=f"pdf_{indice}")
        
    st.markdown("</div>", unsafe_allow_html=True)

# --- CABECERA SUPERIOR ---
st.markdown("<h1 class='brand-title serif-title'>¿Y Si Recetas?</h1>", unsafe_allow_html=True)
st.markdown("<p class='brand-subtitle'>Inteligencia Artificial Gastronómica</p>", unsafe_allow_html=True)

# --- EL NUEVO MENÚ SUPERIOR (ADIÓS BARRA LATERAL) ---
tab_diseno, tab_coleccion = st.tabs(["✨ DISEÑAR NUEVO PLATO", "📚 MI COLECCIÓN PRIVADA"])

with tab_diseno:
    st.write("") # Espaciador
    col1, col2 = st.columns(2)
    with col1: tipo = st.selectbox("Categoría del Plato", ["Comida", "Cena", "Postre"])
    with col2: t_slider = st.select_slider("Tiempo de Elaboración", ["15 min", "30 min", "45 min", "60 min", "120 min", "+2h (Slow Food)"], value="30 min")
        
    ing_input = st.text_area("Ingredientes Base", placeholder="Ej: Atún rojo, sésamo, salsa de soja, jengibre...")
    alergenos_input = st.text_input("🚫 Excluir Alérgenos (Opcional)", placeholder="Ej: Gluten, lactosa, trazas de frutos secos...")
    
    st.write("")
    if st.button("COMENZAR CREACIÓN", use_container_width=True):
        if not ing_input.strip():
            # ESCUDO ANTI-FALLOS 1: Si no ponen ingredientes, lanzamos aviso.
            st.warning("⚠️ El Chef necesita saber qué ingredientes tienes antes de empezar.")
        else:
            with st.spinner("👨‍🍳 Procesando técnicas culinarias..."):
                resultado = generar_receta(ing_input, t_slider, tipo, alergenos_input)
                if resultado: 
                    st.session_state.actual = resultado
                else:
                    # ESCUDO ANTI-FALLOS 2: Si la IA falla, damos la cara con elegancia.
                    st.error("⚠️ Los fogones digitales están saturados. Por favor, haz clic de nuevo.")
            
    if 'actual' in st.session_state: 
        st.markdown("---")
        mostrar_tarjeta(st.session_state.actual)

with tab_coleccion:
    st.write("")
    conn = st.connection("gsheets", type=GSheetsConnection)
    df = conn.read(ttl=0)
    if not df.empty:
        for idx, row in df.iloc[::-1].iterrows(): mostrar_tarjeta(row.to_dict(), idx)
    else:
        st.info("Tu colección está vacía. Diseña tu primer plato para verlo aquí.")
