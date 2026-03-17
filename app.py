import streamlit as st
from groq import Groq
from streamlit_gsheets import GSheetsConnection
import pandas as pd
import json
import re
import requests
import subprocess
import sys
import uuid

try:
    from fpdf import FPDF
except ImportError:
    subprocess.check_call([sys.executable, "-m", "pip", "install", "fpdf2"])
    from fpdf import FPDF

# --- MARCA Y DISEÑO: VERDE FRESCO Y CENTRO LIMPIO ---
st.set_page_config(page_title="¿Y Si Recetas? | Alta Cocina", page_icon="🌿", layout="centered")

st.markdown("""
<style>
    /* Importamos las nuevas letras: Poppins (moderna) y Lora (culinaria) */
    @import url('https://fonts.googleapis.com/css2?family=Lora:ital,wght@0,500;0,700;1,500&family=Poppins:wght@300;400;500;600;700&display=swap');
    
    /* FONDO VERDOSO CLARO MUY SUAVE */
    .stApp { 
        background-color: #EAF2E8; /* Verde menta/pistacho muy pastel */
        color: #2D3A2D; 
        font-family: 'Poppins', sans-serif; /* Letra principal moderna y limpia */
    }
    
    /* Tipografía para los títulos de los platos (Toque elegante) */
    h1, h2, h3, .serif-title { font-family: 'Lora', serif !important; color: #1E2B1E !important; }
    
    .brand-title { text-align: center; font-size: 3.5rem !important; margin-top: 1rem; margin-bottom: 0rem; font-weight: 700; letter-spacing: -1px; color: #1E2B1E !important;}
    .brand-subtitle { text-align: center; font-size: 1rem; color: #587258; letter-spacing: 3px; text-transform: uppercase; margin-bottom: 2rem; font-weight: 500;}
    
    /* EL CENTRO LIMPIO: Tarjetas de color BLANCO PURO para destacar */
    .recipe-card { 
        background: #FFFFFF; /* Blanco nuclear para que se lea perfecto */
        border-radius: 16px; /* Bordes más redondeados y modernos */
        padding: 40px; 
        box-shadow: 0 10px 40px rgba(45, 58, 45, 0.08); /* Sombra suave verdosa */
        margin-bottom: 30px; 
        margin-top: 20px;
        border: 1px solid #DCE6DC;
    }
    
    /* Etiquetas de tiempo y calorías */
    .recipe-meta {
        background-color: #F5F9F5;
        color: #4A804D; /* Verde principal vibrante */
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
    
    /* Botones vibrantes pero elegantes */
    .stButton>button, .stDownloadButton>button { 
        background-color: #1E2B1E !important; /* Verde muy oscuro casi negro */
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
        background-color: #4A804D !important; /* Verde vibrante al pasar el ratón */
        color: #FFFFFF !important;
        box-shadow: 0 4px 12px rgba(74, 128, 77, 0.3);
    }

    /* Ocultar interfaz base */
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

def procesar_lista(datos_brutos):
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
    pdf.set_text_color(30, 43, 30)
    pdf.multi_cell(ancho_max, 10, limpiar_texto_pdf(titulo), align='C')
    pdf.ln(5)

    pdf.set_font("helvetica", "I", 10)
    pdf.set_text_color(74, 128, 77)
    info_texto = f"TIEMPO: {tiempo} | CALORÍAS: {kcal}"
    pdf.cell(ancho_max, 8, limpiar_texto_pdf(info_texto), align='C', ln=True)
    pdf.ln(8)

    pdf.set_font("helvetica", "B", 12)
    pdf.set_text_color(30, 43, 30)
    pdf.cell(ancho_max, 8, "INGREDIENTES:", ln=True)
    pdf.set_font("helvetica", "", 11)
    pdf.set_text_color(60, 60, 60)
    for ing in ingredientes:
        txt = limpiar_texto_pdf(ing)
        if not txt.startswith("-"): txt = f"- {txt}"
        pdf.multi_cell(ancho_max, 6, txt)
    pdf.ln(5)
    
    pdf.set_font("helvetica", "B", 12)
    pdf.set_text_color(30, 43, 30)
    pdf.cell(ancho_max, 8, "ELABORACIÓN:", ln=True)
    pdf.set_font("helvetica", "", 10)
    for idx, p in enumerate(pasos):
        txt_p = limpiar_texto_pdf(p)
        txt_p = re.sub(r'^-\s*', '', txt_p)
        pdf.multi_cell(ancho_max, 5, f"{idx+1}. {txt_p}")
        pdf.ln(2)
            
    return bytes(pdf.output())

# --- IA RECETAS ---
def generar_receta(ingredientes, tiempo, tipo, alergenos, es_sorpresa=False):
    client = Groq(api_key=GROQ_API_KEY)
    regla_tiempo = f"Ajusta las técnicas para {tiempo}."
    if "+2h" in str(tiempo): regla_tiempo = "Tiempo ILIMITADO. Slow Food."
    regla_alergenos = f"PROHIBIDO USAR: {alergenos}. Excluye derivados." if alergenos else "Ninguna restricción."

    if es_sorpresa:
        instruccion_ingredientes = "Crea una receta totalmente libre, sorprendente y creativa utilizando ingredientes de temporada y con un toque de alta cocina mediterránea."
    else:
        instruccion_ingredientes = f"Diseña una receta con estos ingredientes base: {ingredientes}."

    prompt = f"""Eres un Chef Ejecutivo. Diseña una receta de {tipo}. {instruccion_ingredientes}
    REGLAS:
    1. TIEMPO: {regla_tiempo}
    2. CALORÍAS: Número realista y añade 'kcal'.
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
            temperature=0.6 if es_sorpresa else 0.2,
            response_format={"type": "json_object"}
        )
        return json.loads(chat.choices[0].message.content)
    except: 
        return None

# --- TARJETA INTELIGENTE ---
def mostrar_tarjeta(r, modo="completo"):
    t = obtener_texto_seguro(r.get('Titulo') or r.get('titulo') or r.get('Título'), "Receta de Chef")
    tiempo = obtener_texto_seguro(r.get('Tiempo') or r.get('tiempo'), "")
    kcal = obtener_texto_seguro(r.get('Calorias') or r.get('calorias') or r.get('kcal') or r.get('Kcal'), "")
    ing_lista = procesar_lista(r.get('Ingredientes') or r.get('ingredientes'))
    pas_lista = procesar_lista(r.get('Pasos') or r.get('pasos'))
    
    id_unico = str(uuid.uuid4())[:8] 

    if modo == "completo":
        st.markdown('<div class="recipe-card">', unsafe_allow_html=True)
        st.markdown(f'<h2 class="serif-title" style="margin-top:0px; font-size: 2.2rem; margin-bottom:15px;">🍽️ {t}</h2>', unsafe_allow_html=True)
        
        info_texto = ""
        if tiempo and tiempo.upper() != "N/A": info_texto += f"⏱️ {tiempo} &nbsp;&nbsp;&nbsp;&nbsp;|&nbsp;&nbsp;&nbsp;&nbsp; "
        if kcal and kcal.upper() != "N/A": info_texto += f"🔥 {kcal}"
        if info_texto: st.markdown(f'<div class="recipe-meta">{info_texto}</div>', unsafe_allow_html=True)

        st.write("### 🛒 Ingredientes")
        for i in ing_lista: st.write(f"- {i}")
        st.write("---")
        st.write("### 👨‍🍳 Elaboración")
        for idx, p in enumerate(pas_lista): st.write(f"**{idx+1}.** {p}")
        
        st.write("") 
        c1, c2 = st.columns(2)
        with c1:
            if st.button("💾 Guardar Menú", key=f"sv_{id_unico}"):
                payload = {"Titulo": t, "Ingredientes": " | ".join(ing_lista), "Pasos": " | ".join(pas_lista), "Tiempo": tiempo, "Calorias": kcal}
                requests.post(URL_WEBHOOK, json=payload)
                st.toast("✅ Añadido a tu colección privada")
        with c2:
            pdf_b = generar_pdf(t, ing_lista, pas_lista, tiempo, kcal)
            st.download_button("📄 Imprimir PDF", data=pdf_b, file_name=f"{t.replace(' ', '_')}.pdf", mime="application/pdf", key=f"pdf_{id_unico}")
        st.markdown("</div>", unsafe_allow_html=True)
        
    elif modo == "resumen":
        with st.expander(f"📖 {t} — ⏱️ {tiempo} | 🔥 {kcal}"):
            st.write("### 🛒 Ingredientes")
            for i in ing_lista: st.write(f"- {i}")
            st.write("### 👨‍🍳 Elaboración")
            for idx, p in enumerate(pas_lista): st.write(f"**{idx+1}.** {p}")
            
            pdf_b = generar_pdf(t, ing_lista, pas_lista, tiempo, kcal)
            st.download_button("📄 Descargar Receta", data=pdf_b, file_name=f"{t.replace(' ', '_')}.pdf", mime="application/pdf", key=f"pdf_resumen_{id_unico}")

# --- ESTRUCTURA DE LA PÁGINA ---
st.markdown("<h1 class='brand-title'>¿Y Si Recetas?</h1>", unsafe_allow_html=True)
st.markdown("<p class='brand-subtitle'>Inteligencia Artificial Gastronómica</p>", unsafe_allow_html=True)

tab_diseno, tab_coleccion = st.tabs(["✨ DISEÑAR NUEVO PLATO", "📚 MI COLECCIÓN PRIVADA"])

with tab_diseno:
    st.write("")
    col1, col2 = st.columns(2)
    with col1: tipo = st.selectbox("Categoría del Plato", ["Comida", "Cena", "Postre"])
    with col2: t_slider = st.select_slider("Tiempo de Elaboración", ["15 min", "30 min", "45 min", "60 min", "120 min", "+2h (Slow Food)"], value="30 min")
        
    ing_input = st.text_area("Ingredientes Base (Opcional)", placeholder="Si lo dejas en blanco, el Chef improvisará una receta por ti...")
    alergenos_input = st.text_input("🚫 Excluir Alérgenos (Opcional)", placeholder="Ej: Gluten, lactosa...")
    
    st.write("")
    if st.button("COMENZAR CREACIÓN", use_container_width=True):
        es_sorpresa = not ing_input.strip()
        
        if es_sorpresa: st.toast("🎲 ¡Activando Modo Chef Sorpresa!")
            
        with st.spinner("👨‍🍳 Procesando técnicas culinarias..."):
            resultado = generar_receta(ing_input, t_slider, tipo, alergenos_input, es_sorpresa)
            if resultado: 
                st.session_state.actual = resultado
            else:
                st.error("⚠️ Los fogones digitales están saturados. Por favor, haz clic de nuevo.")
            
    if 'actual' in st.session_state: 
        mostrar_tarjeta(st.session_state.actual, modo="completo")

with tab_coleccion:
    st.write("")
    conn = st.connection("gsheets", type=GSheetsConnection)
    df = conn.read(ttl=0)
    if not df.empty:
        df = df.drop_duplicates(subset=['Titulo']) 
        for _, row in df.iloc[::-1].iterrows(): 
            mostrar_tarjeta(row.to_dict(), modo="resumen")
    else:
        st.info("Tu colección está vacía. Diseña tu primer plato para verlo aquí.")
