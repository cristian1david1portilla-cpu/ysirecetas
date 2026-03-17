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

# --- CONFIGURACIÓN DE PÁGINA ---
st.set_page_config(page_title="¿Y Si Recetas?", page_icon="🌿", layout="centered")

# --- DISEÑO PREMIUM Y DESTRUCCIÓN INTELIGENTE DE LA BARRA ---
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Lora:ital,wght@0,500;0,700;1,500&family=Poppins:wght@300;400;500;600;700&display=swap');
    
    [data-testid="stToolbar"] { display: none !important; }
    [data-testid="stHeaderActionElements"] { display: none !important; }
    #MainMenu { visibility: hidden !important; }
    footer { visibility: hidden !important; }
    header { background-color: transparent !important; }
    
    .stApp { 
        background-color: #EAF2E8; 
        background-image: radial-gradient(#C4D4C4 1px, transparent 1px);
        background-size: 30px 30px;
        color: #2D3A2D; 
        font-family: 'Poppins', sans-serif; 
    }
    
    h1, h2, h3, .serif-title { font-family: 'Lora', serif !important; color: #1E2B1E !important; }
    
    .brand-title { text-align: center; font-size: 4rem !important; margin-top: 2rem; margin-bottom: 2rem; font-weight: 700; letter-spacing: -1px; color: #1E2B1E !important;}
    
    .recipe-card { 
        background: #FFFFFF; 
        border-radius: 16px; 
        padding: 40px; 
        box-shadow: 0 10px 40px rgba(45, 58, 45, 0.08); 
        margin-bottom: 30px; 
        margin-top: 10px;
        border: 1px solid #DCE6DC;
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

URL_WEBHOOK = "https://script.google.com/macros/s/AKfycbwBkmZtEU_h0ApOyel01MKNx_7rjUArm8P1wGiH7EgTFO-WhMOmmcfG3sElcy7N3F1x/exec"
GROQ_API_KEY = st.secrets["GROQ_API_KEY"]

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

def mostrar_tarjeta(r, modo="completo"):
    t = obtener_texto_seguro(r.get('Titulo') or r.get('titulo') or r.get('Título'), "Receta de Chef")
    tiempo = obtener_texto_seguro(r.get('Tiempo') or r.get('tiempo'), "")
    kcal = obtener_texto_seguro(r.get('Calorias') or r.get('calorias') or r.get('kcal') or r.get('Kcal'), "")
    ing_lista, pas_lista = procesar_lista(r.get('Ingredientes') or r.get('ingredientes')), procesar_lista(r.get('Pasos') or r.get('pasos'))
    id_unico = str(uuid.uuid4())[:8] 

    if modo == "completo":
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
        c1, c2 = st.columns(2)
        with c1:
            if st.button("💾 Guardar Menú", key=f"sv_{id_unico}"):
                requests.post(URL_WEBHOOK, json={"Titulo": t, "Ingredientes": " | ".join(ing_lista), "Pasos": " | ".join(pas_lista), "Tiempo": tiempo, "Calorias": kcal})
                st.toast("✅ Añadido a tu colección")
        with c2: st.download_button("📄 Imprimir PDF", data=generar_pdf(t, ing_lista, pas_lista, tiempo, kcal), file_name=f"{t.replace(' ', '_')}.pdf", mime="application/pdf", key=f"pdf_{id_unico}")
        st.markdown("</div>", unsafe_allow_html=True)
    elif modo == "resumen":
        with st.expander(f"📖 {t} — ⏱️ {tiempo} | 🔥 {kcal}"):
            st.write("### 🛒 Ingredientes")
            for i in ing_lista: st.write(f"- {i}")
            st.write("### 👨‍🍳 Elaboración")
            for idx, p in enumerate(pas_lista): st.write(f"**{idx+1}.** {p}")
            st.download_button("📄 Descargar", data=generar_pdf(t, ing_lista, pas_lista, tiempo, kcal), file_name=f"{t.replace(' ', '_')}.pdf", mime="application/pdf", key=f"pdf_res__{id_unico}")

# --- NAVEGACIÓN CORPORATIVA ---
with st.sidebar:
    st.markdown("### 🌐 Navegación")
    pagina_actual = st.radio("", ["App de Cocina", "Sobre Nosotros", "Preguntas Frecuentes", "Aviso Legal y Privacidad"])

# --- RENDERIZADO DE PÁGINAS ---
if pagina_actual == "App de Cocina":
    st.markdown("<h1 class='brand-title'>¿Y Si Recetas?</h1>", unsafe_allow_html=True)
    tab_diseno, tab_coleccion = st.tabs(["✨ DISEÑAR NUEVO PLATO", "📚 MI COLECCIÓN PRIVADA"])

    with tab_diseno:
        st.write("")
        col1, col2 = st.columns(2)
        with col1: tipo = st.selectbox("Categoría del Plato", ["Comida", "Cena", "Postre"])
        with col2: t_slider = st.select_slider("Tiempo de Elaboración", ["15 min", "30 min", "45 min", "60 min", "120 min", "+2h (Slow Food)"], value="30 min")
            
        # EL NUEVO TEXTO DE RETO (Sutil, elegante y misterioso)
        ing_input = st.text_area("Ingredientes Base (Opcional)", placeholder="Ej: Gamba roja, ajos tiernos, un toque de azafrán... ¿Te atreves a retar al Chef?")
        alergenos_input = st.text_input("🚫 Excluir Alérgenos (Opcional)", placeholder="Ej: Gluten, lactosa...")
        
        st.write("")
        if st.button("COMENZAR CREACIÓN", use_container_width=True):
            es_sorpresa = not ing_input.strip()
            
            # EL NUEVO MENSAJE DE CARGA
            mensaje_spinner = "✨ Dejando volar la imaginación del Chef..." if es_sorpresa else "👨‍🍳 Procesando técnicas culinarias..."
            
            with st.spinner(mensaje_spinner):
                resultado = generar_receta(ing_input, t_slider, tipo, alergenos_input, es_sorpresa)
                if resultado: st.session_state.actual = resultado
                else: st.error("⚠️ Los fogones digitales están saturados. Por favor, haz clic de nuevo.")
                
        if 'actual' in st.session_state: mostrar_tarjeta(st.session_state.actual, modo="completo")

    with tab_coleccion:
        st.write("")
        conn = st.connection("gsheets", type=GSheetsConnection)
        df = conn.read(ttl=0)
        if not df.empty:
            df = df.drop_duplicates(subset=['Titulo']) 
            for _, row in df.iloc[::-1].iterrows(): mostrar_tarjeta(row.to_dict(), modo="resumen")
        else: st.info("Tu colección está vacía. Diseña tu primer plato para verlo aquí.")

elif pagina_actual == "Sobre Nosotros":
    st.markdown("<h1 class='serif-title' style='text-align:center; font-size: 3rem;'>Nuestra Misión</h1>", unsafe_allow_html=True)
    st.markdown('<div class="recipe-card">', unsafe_allow_html=True)
    st.write("### Democratizando la Alta Cocina")
    st.write("¿Y Si Recetas? nace de una premisa sencilla: cualquier persona, independientemente de su nivel culinario, debería poder transformar los ingredientes olvidados de su nevera en una experiencia gastronómica de restaurante de lujo.")
    st.write("Aprovechando el poder de la Inteligencia Artificial Generativa (LLMs de última generación), hemos entrenado a nuestro motor para que actúe no solo como un recetario, sino como un Chef Ejecutivo que comprende técnicas, tiempos, balance de sabores y restricciones alimentarias en tiempo real.")
    st.write("**Fase Actual:** MVP (Producto Mínimo Viable) v1.0. Validando la integración de la API de Groq con bases de datos relacionales ligeras.")
    st.markdown('</div>', unsafe_allow_html=True)

elif pagina_actual == "Preguntas Frecuentes":
    st.markdown("<h1 class='serif-title' style='text-align:center; font-size: 3rem;'>FAQ</h1>", unsafe_allow_html=True)
    st.markdown('<div class="recipe-card">', unsafe_allow_html=True)
    with st.expander("¿Mis recetas guardadas son públicas?"):
        st.write("En esta primera versión (MVP), la colección opera sobre una base de datos central compartida para validar el flujo de información. En la Fase 2 del desarrollo (Arquitectura Escalable), implementaremos un sistema de autenticación de usuarios donde cada perfil tendrá su espacio encriptado y privado.")
    with st.expander("¿Cómo gestiona la IA las intolerancias alimentarias?"):
        st.write("El sistema inyecta instrucciones estrictas (System Prompts) en el modelo lingüístico para realizar un filtrado negativo. Si indicas 'celíaco', la IA descarta el trigo, centeno, cebada y avena de su matriz de generación, ofreciendo alternativas seguras.")
    with st.expander("¿De dónde salen las estimaciones de calorías?"):
        st.write("La IA calcula un valor heurístico aproximado basándose en las tablas nutricionales estándar de los ingredientes seleccionados y el método de cocción.")
    st.markdown('</div>', unsafe_allow_html=True)

elif pagina_actual == "Aviso Legal y Privacidad":
    st.markdown("<h1 class='serif-title' style='text-align:center; font-size: 3rem;'>Legal</h1>", unsafe_allow_html=True)
    st.markdown('<div class="recipe-card">', unsafe_allow_html=True)
    st.write("### Términos de Uso y Descargo de Responsabilidad")
    st.write("Esta aplicación es un **Prototipo Tecnológico / Prueba de Concepto** desarrollado con fines académicos e investigativos.")
    st.write("**Responsabilidad Alimentaria:** Las recetas e informaciones nutricionales y de alérgenos son generadas mediante algoritmos de Inteligencia Artificial (LLMs). Aunque el sistema está diseñado para seguir directrices estrictas, **siempre se debe aplicar el juicio humano y consultar a profesionales médicos** en caso de alergias severas o condiciones de salud específicas. Los creadores de esta plataforma no se hacen responsables de reacciones adversas.")
    st.write("**Protección de Datos:** Actualmente no recabamos datos de carácter personal ni utilizamos cookies de rastreo comercial.")
    st.markdown('</div>', unsafe_allow_html=True)
