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

# --- MARCA Y DISEÑO MINIMALISTA ---
st.set_page_config(page_title="¿Y Si Recetas? | Alta Cocina", page_icon="🌿", layout="wide")

st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Lora:ital,wght@0,400;0,600;1,400&family=Nunito:wght@300;400;600;700&display=swap');
    .stApp { background-color: #FDFBF7; color: #2C362B; font-family: 'Nunito', sans-serif; }
    h1, h2, h3, .serif-title { font-family: 'Lora', serif !important; color: #1A2619 !important; font-weight: 600; }
    .brand-title { text-align: center; font-size: 4rem !important; margin-top: 1rem; margin-bottom: 0rem; text-transform: uppercase; letter-spacing: 2px;}
    
    .recipe-card { 
        background: linear-gradient(145deg, #ffffff, #FDFBF7);
        border-left: 6px solid #C86C58;
        border-radius: 12px; 
        padding: 32px; 
        box-shadow: 0 10px 30px rgba(0,0,0,0.04); 
        margin-bottom: 24px; 
    }
    .recipe-meta {
        background-color: #F4EFE6;
        padding: 10px 18px;
        border-radius: 8px;
        display: inline-block;
        color: #C86C58;
        font-weight: 700;
        font-size: 1.05rem;
        margin-bottom: 20px;
        border: 1px solid #EAE6D8;
    }
    
    .stButton>button, .stDownloadButton>button { border-radius: 8px !important; font-weight: 700 !important; width: 100%; height: 3.5em; }
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
    pdf.set_text_color(44, 54, 43)
    pdf.multi_cell(ancho_max, 10, limpiar_texto_pdf(titulo), align='C')
    pdf.ln(5)

    pdf.set_font("helvetica", "I", 11)
    pdf.set_text_color(200, 108, 88)
    info_texto = f"Tiempo: {tiempo} | Calorías: {kcal}"
    pdf.cell(ancho_max, 8, limpiar_texto_pdf(info_texto), align='C', ln=True)
    pdf.ln(8)

    pdf.set_font("helvetica", "B", 14)
    pdf.set_text_color(44, 54, 43)
    pdf.cell(ancho_max, 8, "Ingredientes:", ln=True)
    pdf.set_font("helvetica", "", 11)
    pdf.set_text_color(60, 60, 60)
    
    for ing in ingredientes:
        txt = limpiar_texto_pdf(ing)
        if not txt.startswith("-"): txt = f"- {txt}"
        pdf.multi_cell(ancho_max, 6, txt)
    pdf.ln(5)
    
    pdf.set_font("helvetica", "B", 14)
    pdf.set_text_color(44, 54, 43)
    pdf.cell(ancho_max, 8, "Preparación Paso a Paso:", ln=True)
    pdf.set_font("helvetica", "", 10)
    
    for idx, p in enumerate(pasos):
        txt_p = limpiar_texto_pdf(p)
        txt_p = re.sub(r'^-\s*', '', txt_p)
        pdf.multi_cell(ancho_max, 5, f"{idx+1}. {txt_p}")
        pdf.ln(2)
            
    return bytes(pdf.output())

# --- IA RECETAS (AHORA CON ALÉRGENOS) ---
def generar_receta(ingredientes, tiempo, tipo, alergenos):
    client = Groq(api_key=GROQ_API_KEY)
    
    regla_tiempo = f"Ajusta las técnicas para {tiempo}."
    if "+2h" in str(tiempo): regla_tiempo = "Tiempo ILIMITADO. Slow Food."
    
    # Nueva regla estricta de alérgenos
    regla_alergenos = f"ESTÁ TOTAL Y ABSOLUTAMENTE PROHIBIDO USAR: {alergenos}. Excluye cualquier derivado." if alergenos else "Ninguna restricción de alérgenos."

    prompt = f"""Eres un Chef Ejecutivo. Diseña una receta de {tipo} con: {ingredientes}.
    
    REGLAS ESTRICTAS:
    1. TIEMPO: {regla_tiempo}
    2. CALORÍAS: Inventa un número realista y añade 'kcal'. ESTÁ PROHIBIDO ESCRIBIR EL TIEMPO AQUÍ.
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

# --- INTERFAZ ELEGANTE ---
def mostrar_tarjeta(r, indice=0):
    t = obtener_texto_seguro(r.get('Titulo') or r.get('titulo') or r.get('Título'), "Receta Gourmet")
    tiempo = obtener_texto_seguro(r.get('Tiempo') or r.get('tiempo'), "")
    kcal = obtener_texto_seguro(r.get('Calorias') or r.get('calorias') or r.get('kcal') or r.get('Kcal'), "")
    
    ing_lista = procesar_lista(r.get('Ingredientes') or r.get('ingredientes'), es_paso=False)
    pas_lista = procesar_lista(r.get('Pasos') or r.get('pasos'), es_paso=True)

    st.markdown('<div class="recipe-card">', unsafe_allow_html=True)
    
    st.markdown(f'<h2 class="serif-title" style="margin-top:0px; font-size: 2.2rem; margin-bottom:15px;">🍽️ {t}</h2>', unsafe_allow_html=True)
    
    info_texto = ""
    if tiempo and tiempo.upper() != "N/A": info_texto += f"⏱️ {tiempo} &nbsp;&nbsp;&nbsp;&nbsp;|&nbsp;&nbsp;&nbsp;&nbsp; "
    if kcal and kcal.upper() != "N/A": info_texto += f"🔥 {kcal}"
        
    if info_texto:
        st.markdown(f'<div class="recipe-meta">{info_texto}</div>', unsafe_allow_html=True)

    with st.expander("VER RECETA PASO A PASO"):
        st.write("### 🛒 Ingredientes")
        for i in ing_lista: st.write(f"- {i}")
        st.write("---")
        st.write("### 👨‍🍳 Preparación")
        for idx, p in enumerate(pas_lista): st.write(f"**{idx+1}.** {p}")
        
        st.write("") 
        c1, c2 = st.columns(2)
        with c1:
            if st.button("💾 Guardar en Colección", key=f"sv_{indice}"):
                payload = {"Titulo": t, "Ingredientes": " | ".join(ing_lista), "Pasos": " | ".join(pas_lista), "Tiempo": tiempo, "Calorias": kcal}
                requests.post(URL_WEBHOOK, json=payload)
                st.toast("¡Guardado en la base de datos!")
        with c2:
            nombre_archivo = f"{t.replace(' ', '_')}.pdf"
            pdf_b = generar_pdf(t, ing_lista, pas_lista, tiempo, kcal)
            st.download_button("📄 Descargar PDF", data=pdf_b, file_name=nombre_archivo, mime="application/pdf", key=f"pdf_{indice}")
            
    st.markdown("</div>", unsafe_allow_html=True)

st.markdown("<h1 class='brand-title serif-title'>¿Y Si Recetas?</h1>", unsafe_allow_html=True)

with st.sidebar: menu = st.radio("MENÚ", ["Diseñar", "Mi Colección"])

if menu == "Diseñar":
    col1, col2 = st.columns(2)
    with col1: tipo = st.selectbox("Momento", ["Comida", "Cena", "Postre"])
    with col2: t_slider = st.select_slider("Tiempo", ["15 min", "30 min", "45 min", "60 min", "120 min", "+2h (Slow Food)"], value="30 min")
        
    ing_input = st.text_area("Ingredientes principales", placeholder="Ej: pollo, arroz, pimientos...")
    # AQUÍ ESTÁ EL NUEVO CAMPO DE ALÉRGENOS
    alergenos_input = st.text_input("🚫 Alérgenos a evitar (Opcional)", placeholder="Ej: gluten, lactosa, frutos secos, huevo...")
    
    if st.button("DISEÑAR MI PLATO", use_container_width=True):
        if ing_input:
            with st.spinner("👨‍🍳 El Chef está redactando tu obra de arte..."):
                # Le pasamos los alérgenos a la IA
                resultado = generar_receta(ing_input, t_slider, tipo, alergenos_input)
                if resultado: st.session_state.actual = resultado
            
    if 'actual' in st.session_state: mostrar_tarjeta(st.session_state.actual)

elif menu == "Mi Colección":
    conn = st.connection("gsheets", type=GSheetsConnection)
    df = conn.read(ttl=0)
    if not df.empty:
        for idx, row in df.iloc[::-1].iterrows(): mostrar_tarjeta(row.to_dict(), idx)
