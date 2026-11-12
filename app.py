import io
import re
import random
import streamlit as st
from gtts import gTTS

# ==============================================================================
# CONFIGURACIÓN DE PÁGINA Y ESTADO
# ==============================================================================
st.set_page_config(
    page_title="English Sentence Matrix & Shadowing Lab",
    page_icon="🧩",
    layout="wide",
    initial_sidebar_state="expanded",
)

if "score" not in st.session_state:
    st.session_state.score = 0
if "attempts" not in st.session_state:
    st.session_state.attempts = 0
if "history" not in st.session_state:
    st.session_state.history = []
if "current_challenge" not in st.session_state:
    st.session_state.current_challenge = None
if "shadowing_completed" not in st.session_state:
    st.session_state.shadowing_completed = []

# ==============================================================================
# DICCIONARIOS DE REFERENCIA Y CONJUGACIÓN
# ==============================================================================
SUBJECTS = {
    "I": {"person": "1s", "plural": False, "es": "Yo", "be_pres": "am", "be_past": "was", "have": "have"},
    "You": {"person": "2s", "plural": True, "es": "Tú / Ustedes", "be_pres": "are", "be_past": "were", "have": "have"},
    "He": {"person": "3s", "plural": False, "es": "Él", "be_pres": "is", "be_past": "was", "have": "has"},
    "She": {"person": "3s", "plural": False, "es": "Ella", "be_pres": "is", "be_past": "was", "have": "has"},
    "It": {"person": "3s", "plural": False, "es": "Eso / Ello", "be_pres": "is", "be_past": "was", "have": "has"},
    "We": {"person": "1p", "plural": True, "es": "Nosotros", "be_pres": "are", "be_past": "were", "have": "have"},
    "They": {"person": "3p", "plural": True, "es": "Ellos", "be_pres": "are", "be_past": "were", "have": "have"},
}

VERBS_DB = {
    "work": {"3s": "works", "past": "worked", "ing": "working", "es_inf": "trabajar", "es_pres": "trabaja(s)", "es_past": "trabajó/trabajaba"},
    "study": {"3s": "studies", "past": "studied", "ing": "studying", "es_inf": "estudiar", "es_pres": "estudia(s)", "es_past": "estudió/estudiaba"},
    "speak": {"3s": "speaks", "past": "spoke", "ing": "speaking", "es_inf": "hablar", "es_pres": "habla(s)", "es_past": "habló/hablaba"},
    "travel": {"3s": "travels", "past": "traveled", "ing": "traveling", "es_inf": "viajar", "es_pres": "viaja(s)", "es_past": "viajó/viajaba"},
    "go": {"3s": "goes", "past": "went", "ing": "going", "es_inf": "ir", "es_pres": "va(s)", "es_past": "fue/iba"},
    "eat": {"3s": "eats", "past": "ate", "ing": "eating", "es_inf": "comer", "es_pres": "come(s)", "es_past": "comió/comía"},
    "read": {"3s": "reads", "past": "read", "ing": "reading", "es_inf": "leer", "es_pres": "lee(s)", "es_past": "leyó/leía"},
    "write": {"3s": "writes", "past": "wrote", "ing": "writing", "es_inf": "escribir", "es_pres": "escribe(s)", "es_past": "escribió/escribía"},
    "learn": {"3s": "learns", "past": "learned", "ing": "learning", "es_inf": "aprender", "es_pres": "aprende(s)", "es_past": "aprendió/aprendía"},
    "play": {"3s": "plays", "past": "played", "ing": "playing", "es_inf": "jugar / tocar", "es_pres": "juega(s)", "es_past": "jugó/jugaba"},
    "buy": {"3s": "buys", "past": "bought", "ing": "buying", "es_inf": "comprar", "es_pres": "compra(s)", "es_past": "compró/compraba"},
    "visit": {"3s": "visits", "past": "visited", "ing": "visiting", "es_inf": "visitar", "es_pres": "visita(s)", "es_past": "visitó/visitaba"},
    "cook": {"3s": "cooks", "past": "cooked", "ing": "cooking", "es_inf": "cocinar", "es_pres": "cocina(s)", "es_past": "cocinó/cocinaba"},
    "drive": {"3s": "drives", "past": "drove", "ing": "driving", "es_inf": "conducir", "es_pres": "conduce(s)", "es_past": "condujo/conducía"},
    "live": {"3s": "lives", "past": "lived", "ing": "living", "es_inf": "vivir", "es_pres": "vive(s)", "es_past": "vivió/vivía"},
}

COMPLEMENTS_PRESETS = {
    "English every day": "inglés todos los días",
    "in the office": "en la oficina",
    "to Orlando next month": "a Orlando el próximo mes",
    "a new book": "un libro nuevo",
    "healthy food": "comida saludable",
    "at home": "en casa",
    "with my family": "con mi familia",
    "very fast": "muy rápido",
    "happy": "feliz / felices",
    "ready for the trip": "listo(s) para el viaje",
    "a new car": "un auto nuevo",
    "time today": "tiempo hoy",
}

MODALS_INFO = {
    "can": {"es": "poder (habilidad / posibilidad)", "neg": "cannot / can't"},
    "could": {"es": "podría / pude (posibilidad / pasado)", "neg": "could not / couldn't"},
    "should": {"es": "debería (consejo / recomendación)", "neg": "should not / shouldn't"},
    "must": {"es": "deber (obligación fuerte)", "neg": "must not / mustn't"},
    "may": {"es": "poder (permiso formal / probabilidad)", "neg": "may not"},
    "might": {"es": "podría (probabilidad baja)", "neg": "might not"},
}

CHALLENGES = [
    {"es": "Ella puede hablar inglés todos los días.", "en": "She can speak English every day.", "hint": "Modal 'can' + verbo base sin 's'"},
    {"es": "¿Trabajan ellos en la oficina?", "en": "Do they work in the office?", "hint": "Pregunta en presente simple con 'They' -> usa 'Do'"},
    {"es": "Él no estudió un libro nuevo.", "en": "He did not study a new book.", "hint": "Negación en pasado -> 'did not' + verbo en forma base"},
    {"es": "¿Está ella lista para el viaje?", "en": "Is she ready for the trip?", "hint": "Verbo 'to be' con 'She' en pregunta -> invierte 'Is she...'"},
    {"es": "Nosotros viajaremos a Orlando el próximo mes.", "en": "We will travel to Orlando next month.", "hint": "Futuro simple -> 'will' + verbo base"},
    {"es": "Tú deberías comer comida saludable.", "en": "You should eat healthy food.", "hint": "Consejo -> modal 'should' + verbo base"},
    {"es": "¿Tiene él un auto nuevo?", "en": "Does he have a new car?", "hint": "Pregunta con 'have' como verbo principal en 3ra persona -> 'Does he have...'"},
]

SHADOWING_LESSONS = [
    {
        "id": "sh_01",
        "title": "01. Rutina Diaria y Hábitos (Nivel Básico)",
        "level": "Básico (A1-A2)",
        "sentences": [
            {
                "en": "I usually wake up early and drink a cup of coffee.",
                "chunks": "I **usually** wake **up** / **early** / and **drink** a cup of **coffee**.",
                "es": "Usualmente me despierto temprano y tomo una taza de café.",
                "tip": "Une 'wake up' como si fuera una sola palabra: /wei-kap/.",
            },
            {
                "en": "Then I check my emails before I start working.",
                "chunks": "Then I **check** my **emails** / be**fore** I **start** **work**ing.",
                "es": "Luego reviso mis correos antes de empezar a trabajar.",
                "tip": "En 'check my', la 'k' casi se suaviza para conectar rápido con 'my'.",
            },
            {
                "en": "If I have free time, I practice English for twenty minutes.",
                "chunks": "If I have **free** **time**, / I **prac**tice **Eng**lish / for **twen**ty **mi**nutes.",
                "es": "Si tengo tiempo libre, practico inglés durante veinte minutos.",
                "tip": "En inglés americano, 'twenty' suele sonar cercano a /tweni/.",
            },
        ],
    },
    {
        "id": "sh_02",
        "title": "02. En el Aeropuerto y Viajes (Nivel Intermedio)",
        "level": "Intermedio (B1)",
        "sentences": [
            {
                "en": "Excuse me, could you tell me where the boarding gate is?",
                "chunks": "Ex**cuse** me, / could you **tell** me / where the **board**ing **gate** is?",
                "es": "Disculpe, ¿podría decirme dónde está la puerta de embarque?",
                "tip": "'Could you' suele fusionarse en conversación rápida como /kud-yu/ o /kud-ya/.",
            },
            {
                "en": "You should go straight ahead and turn left after security.",
                "chunks": "You should go **straight** a**head** / and turn **left** / **af**ter se**cu**rity.",
                "es": "Debería seguir derecho y girar a la izquierda después de seguridad.",
                "tip": "La palabra 'should' no suena la 'l'; se pronuncia /shud/.",
            },
            {
                "en": "Our flight will depart on time if the weather stays clear.",
                "chunks": "Our **flight** will de**part** on **time** / if the **wea**ther stays **clear**.",
                "es": "Nuestro vuelo saldrá a tiempo si el clima se mantiene despejado.",
                "tip": "Conecta 'depart on' como /di-par-ton/.",
            },
        ],
    },
    {
        "id": "sh_03",
        "title": "03. Conversación Profesional y Proyectos (Nivel Intermedio-Alto)",
        "level": "Intermedio-Alto (B1-B2)",
        "sentences": [
            {
                "en": "We might need to update the server configuration tonight.",
                "chunks": "We might **need** to up**date** / the **ser**ver configu**ra**tion / to**night**.",
                "es": "Es posible que necesitemos actualizar la configuración del servidor esta noche.",
                "tip": "En 'need to', las dos 't/d' se fusionan en una sola pausa corta.",
            },
            {
                "en": "Can you verify whether the backup finished without any errors?",
                "chunks": "Can you **ve**rify / **whe**ther the **back**up **fi**nished / with**out** any **e**rrors?",
                "es": "¿Puedes verificar si la copia de seguridad terminó sin errores?",
                "tip": "Entonación ascendente al final por ser pregunta cerrada ('Can you...').",
            },
            {
                "en": "Once everything works smoothly, we can deploy the new version.",
                "chunks": "Once **e**verything works **smooth**ly, / we can de**ploy** / the **new** **ver**sion.",
                "es": "Una vez que todo funcione sin problemas, podremos desplegar la nueva versión.",
                "tip": "Pronuncia 'everything' en 3 sílabas naturales: /ev-ri-thing/.",
            },
        ],
    },
]

# ==============================================================================
# FUNCIONES DE LÓGICA GRAMATICAL Y CONJUGACIÓN
# ==============================================================================
def infer_subject_profile(subj_raw: str) -> dict:
    clean = subj_raw.strip()
    cap = clean.capitalize()
    if cap in SUBJECTS:
        return {**SUBJECTS[cap], "display": "I" if cap == "I" else clean}
    lower = clean.lower()
    is_plural = (
        " and " in lower
        or (lower.endswith("s") and not lower.endswith(("ss", "us", "is")))
        or lower in ("people", "children", "men", "women", "friends", "students")
    )
    if is_plural:
        return {"person": "3p", "plural": True, "es": clean, "be_pres": "are", "be_past": "were", "have": "have", "display": clean}
    return {"person": "3s", "plural": False, "es": clean, "be_pres": "is", "be_past": "was", "have": "has", "display": clean}


def conjugate_3s(verb: str) -> str:
    v = verb.strip().lower()
    if v in VERBS_DB:
        return VERBS_DB[v]["3s"]
    if v == "have":
        return "has"
    if v.endswith(("s", "sh", "ch", "x", "z", "o")):
        return v + "es"
    if len(v) > 2 and v.endswith("y") and v[-2] not in "aeiou":
        return v[:-1] + "ies"
    return v + "s"


def conjugate_past(verb: str) -> str:
    v = verb.strip().lower()
    if v in VERBS_DB:
        return VERBS_DB[v]["past"]
    if v == "have":
        return "had"
    if v.endswith("e"):
        return v + "d"
    if len(v) > 2 and v.endswith("y") and v[-2] not in "aeiou":
        return v[:-1] + "ied"
    return v + "ed"


def cap_first(text: str) -> str:
    text = re.sub(r"\s+", " ", text).strip()
    if not text:
        return ""
    return text[0].upper() + text[1:]


def build_sentences(subject_str: str, structure_type: str, action_str: str, complement_str: str):
    warnings = []
    notes = []

    subj_clean = subject_str.strip() or "I"
    prof = infer_subject_profile(subj_clean)
    s_disp = prof["display"]
    s_lower_for_q = "I" if s_disp == "I" else (s_disp[0].lower() + s_disp[1:] if s_disp in SUBJECTS else s_disp)

    action_clean = action_str.strip().lower()
    comp_clean = complement_str.strip()

    if structure_type in ("To Be (Presente: am/is/are)", "To Be (Pasado: was/were)") and action_clean in VERBS_DB:
        warnings.append(
            f"⚠️ Con **To Be** no se usa un verbo base (`{action_clean}`) directamente; "
            f"usa un adjetivo/lugar en el complemento (ej. *happy*, *at home*). Se ajustará la estructura."
        )

    aff = neg = ques = ""
    es_trans = ""

    if structure_type.startswith("Modal:"):
        modal = structure_type.split(":")[1].strip().lower()
        verb_base = action_clean if action_clean else "go"
        if verb_base in ("am", "is", "are", "was", "were"):
            verb_base = "be"
            warnings.append("ℹ️ Después de un verbo modal, 'to be' siempre va en su forma base: **be**.")

        aff = cap_first(f"{s_disp} {modal} {verb_base} {comp_clean}.")
        neg_mod = "cannot" if modal == "can" else f"{modal} not"
        neg = cap_first(f"{s_disp} {neg_mod} {verb_base} {comp_clean}.")
        ques = cap_first(f"{modal} {s_lower_for_q} {verb_base} {comp_clean}?")

        notes.append(f"**Regla Modal (`{modal}`):** Nunca cambia en tercera persona (`He {modal}`, nunca *He {modal}s*) y el verbo principal (`{verb_base}`) va siempre en **forma base** sin *to*.")
        notes.append(f"**Pregunta:** Se invierte el modal antes del sujeto (`{modal.capitalize()} {s_lower_for_q}...`), sin usar *do/does*.")

        v_es = VERBS_DB.get(verb_base, {}).get("es_inf", verb_base)
        c_es = COMPLEMENTS_PRESETS.get(comp_clean, comp_clean)
        es_trans = f"{prof['es']} [{MODALS_INFO[modal]['es'].split(' ')[0]}] {v_es} {c_es}".strip() + "."

    elif structure_type == "To Be (Presente: am/is/are)":
        be_form = prof["be_pres"]
        mid = action_clean if (action_clean and action_clean not in VERBS_DB) else ""
        aff = cap_first(f"{s_disp} {be_form} {mid} {comp_clean}.")
        neg = cap_first(f"{s_disp} {be_form} not {mid} {comp_clean}.")
        ques = cap_first(f"{be_form} {s_lower_for_q} {mid} {comp_clean}?")

        notes.append(f"**Verbo To Be (Presente):** Para `{s_disp}` corresponde **`{be_form}`**.")
        notes.append("**Negación y Pregunta:** `To be` es autosuficiente; no utiliza *do/does*. Se niega añadiendo `not` y se pregunta invirtiendo el orden.")
        c_es = COMPLEMENTS_PRESETS.get(comp_clean, comp_clean)
        es_trans = f"{prof['es']} está / es {mid} {c_es}".strip() + "."

    elif structure_type == "To Be (Pasado: was/were)":
        be_form = prof["be_past"]
        mid = action_clean if (action_clean and action_clean not in VERBS_DB) else ""
        aff = cap_first(f"{s_disp} {be_form} {mid} {comp_clean}.")
        neg = cap_first(f"{s_disp} {be_form} not {mid} {comp_clean}.")
        ques = cap_first(f"{be_form} {s_lower_for_q} {mid} {comp_clean}?")

        notes.append(f"**Verbo To Be (Pasado):** Para `{s_disp}` corresponde **`{be_form}`**.")
        notes.append("**Negación y Pregunta:** No uses *did* con `was/were`. Invierte `{be_form}` para preguntar.")
        c_es = COMPLEMENTS_PRESETS.get(comp_clean, comp_clean)
        es_trans = f"{prof['es']} estaba / fue {mid} {c_es}".strip() + "."

    elif structure_type == "Have (Presente Simple: have/has)":
        have_aff = prof["have"]
        aux_do = "does" if prof["person"] == "3s" else "do"
        extra = action_clean if (action_clean and action_clean not in VERBS_DB) else ""
        aff = cap_first(f"{s_disp} {have_aff} {extra} {comp_clean}.")
        neg = cap_first(f"{s_disp} {aux_do} not have {extra} {comp_clean}.")
        ques = cap_first(f"{aux_do} {s_lower_for_q} have {extra} {comp_clean}?")

        notes.append(f"**Have como verbo principal:** En afirmativa usa **`{have_aff}`**, pero en negativa e interrogativa usa el auxiliar **`{aux_do}`** y el verbo vuelve a su forma base **`have`**.")
        c_es = COMPLEMENTS_PRESETS.get(comp_clean, comp_clean)
        es_trans = f"{prof['es']} tiene(n) {extra} {c_es}".strip() + "."

    elif structure_type == "Presente Simple (do / does)":
        verb_base = action_clean if action_clean else "work"
        is_3s = prof["person"] == "3s"
        verb_aff = conjugate_3s(verb_base) if is_3s else verb_base
        aux = "does" if is_3s else "do"

        aff = cap_first(f"{s_disp} {verb_aff} {comp_clean}.")
        neg = cap_first(f"{s_disp} {aux} not {verb_base} {comp_clean}.")
        ques = cap_first(f"{aux} {s_lower_for_q} {verb_base} {comp_clean}?")

        if is_3s:
            notes.append(f"**3ra Persona Singular (`{s_disp}`):** En afirmativa se agrega `-s/-es` al verbo (**`{verb_aff}`**). Al usar **`does`** en negativa o pregunta, la `-s` desaparece (**`{verb_base}`**).")
        else:
            notes.append(f"**Presente Simple (`{s_disp}`):** El verbo queda en forma base (**`{verb_base}`**) y se auxilia con **`do`** en negativa e interrogativa.")

        v_es = VERBS_DB.get(verb_base, {}).get("es_pres", verb_base)
        c_es = COMPLEMENTS_PRESETS.get(comp_clean, comp_clean)
        es_trans = f"{prof['es']} {v_es} {c_es}".strip() + "."

    elif structure_type == "Pasado Simple (did)":
        verb_base = action_clean if action_clean else "work"
        verb_past = conjugate_past(verb_base)

        aff = cap_first(f"{s_disp} {verb_past} {comp_clean}.")
        neg = cap_first(f"{s_disp} did not {verb_base} {comp_clean}.")
        ques = cap_first(f"did {s_lower_for_q} {verb_base} {comp_clean}?")

        notes.append(f"**Pasado Simple:** En afirmativa se usa el verbo en pasado (**`{verb_past}`**) para todos los sujetos.")
        notes.append(f"**Efecto Imán de `did`:** En negativa (`did not`) y pregunta (`Did...`), el auxiliar absorbe el pasado y el verbo principal regresa a su forma base (**`{verb_base}`**).")

        v_es = VERBS_DB.get(verb_base, {}).get("es_past", verb_base)
        c_es = COMPLEMENTS_PRESETS.get(comp_clean, comp_clean)
        es_trans = f"{prof['es']} {v_es} {c_es}".strip() + "."

    elif structure_type == "Futuro Simple (will)":
        verb_base = action_clean if action_clean else "travel"
        aff = cap_first(f"{s_disp} will {verb_base} {comp_clean}.")
        neg = cap_first(f"{s_disp} will not {verb_base} {comp_clean}.")
        ques = cap_first(f"will {s_lower_for_q} {verb_base} {comp_clean}?")

        notes.append(f"**Futuro con `will`:** Funciona igual para todos los sujetos. Siempre va seguido del verbo en forma base (**`{verb_base}`**). Contracción negativa común: *won't*.")
        v_es = VERBS_DB.get(verb_base, {}).get("es_inf", verb_base)
        c_es = COMPLEMENTS_PRESETS.get(comp_clean, comp_clean)
        es_trans = f"{prof['es']} va a / {v_es} (futuro) {c_es}".strip() + "."

    return {
        "affirmative": aff,
        "negative": neg,
        "interrogative": ques,
        "spanish": es_trans,
        "warnings": warnings,
        "notes": notes,
    }


@st.cache_data(show_spinner=False)
def synthesize_speech(text: str, slow_mode: bool = False, tld: str = "com") -> bytes:
    """Genera audio MP3 en inglés usando gTTS con acento seleccionable."""
    tts = gTTS(text=text, lang="en", slow=slow_mode, tld=tld)
    fp = io.BytesIO()
    tts.write_to_fp(fp)
    fp.seek(0)
    return fp.read()


@st.cache_data(show_spinner=False)
def synthesize_shadowing_loop(sentences_list: tuple, slow_mode: bool = False, tld: str = "com", repeat_each: int = 2) -> bytes:
    """
    Construye una pista continua estilo curso de Shadowing:
    Pronuncia cada frase N veces con pausas naturales intercaladas.
    """
    combined = io.BytesIO()
    for sentence in sentences_list:
        clean_s = sentence.strip()
        if not clean_s:
            continue
        tts = gTTS(text=clean_s, lang="en", slow=slow_mode, tld=tld)
        seg_fp = io.BytesIO()
        tts.write_to_fp(seg_fp)
        seg_bytes = seg_fp.getvalue()
        # Generar silencio acústico mediante puntos suspensivos en gTTS
        pause_tts = gTTS(text=". . . . .", lang="en", slow=True, tld=tld)
        pause_fp = io.BytesIO()
        pause_tts.write_to_fp(pause_fp)
        pause_bytes = pause_fp.getvalue()

        for _ in range(repeat_each):
            combined.write(seg_bytes)
            combined.write(pause_bytes)

    combined.seek(0)
    return combined.read()


# ==============================================================================
# INTERFAZ DE USUARIO (SIDEBAR Y TABS)
# ==============================================================================
with st.sidebar:
    st.title("🧩 English Matrix")
    st.caption("Constructor Gramatical & Shadowing Lab")
    st.divider()

    st.subheader("🔊 Ajustes de Pronunciación")
    speech_speed = st.radio(
        "Velocidad de audio (TTS):",
        options=["Normal (1.0x)", "Lenta / Didáctica (0.75x)"],
        index=0,
    )
    is_slow = "Lenta" in speech_speed

    accent_choice = st.selectbox(
        "Acento en inglés:",
        options=[
            ("Estados Unidos (US)", "com"),
            ("Reino Unido (UK)", "co.uk"),
            ("Australia (AU)", "com.au"),
            ("Canadá (CA)", "ca"),
        ],
        format_func=lambda x: x[0],
        index=0,
    )
    selected_tld = accent_choice[1]

    st.divider()
    st.subheader("📊 Tu Progreso")
    col_s1, col_s2 = st.columns(2)
    col_s1.metric("Aciertos", st.session_state.score)
    col_s2.metric("Shadowing", len(st.session_state.shadowing_completed))

    if st.session_state.attempts > 0:
        acc = int((st.session_state.score / st.session_state.attempts) * 100)
        st.progress(acc / 100, text=f"Precisión Ejercicios: {acc}%")

    if st.button("Reiniciar estadísticas", use_container_width=True):
        st.session_state.score = 0
        st.session_state.attempts = 0
        st.session_state.history = []
        st.session_state.shadowing_completed = []
        st.rerun()

st.title("🧩 Matriz Gramatical y Laboratorio de Shadowing")
st.markdown(
    "Construye oraciones combinando bloques gramaticales y entrénalas en el **Estudio de Shadowing** "
    "con escucha activa, ritmo marcado, pausas de repetición y grabación de voz."
)

tab_matrix, tab_shadowing, tab_practice, tab_reference = st.tabs(
    [
        "🎛️ Matriz Interactiva",
        "🎧 Estudio de Shadowing",
        "🎯 Ejercicios Guiados",
        "📘 Guía Rápida de Estructuras",
    ]
)

# ------------------------------------------------------------------------------
# TAB 1: MATRIZ INTERACTIVA
# ------------------------------------------------------------------------------
with tab_matrix:
    st.subheader("1. Configura los bloques de la oración")

    c1, c2, c3, c4 = st.columns(4)

    with c1:
        st.markdown("**1️⃣ Sujeto (Subject)**")
        subj_mode = st.toggle("Escribir sujeto libre", key="t_subj")
        if subj_mode:
            subject_val = st.text_input("Sujeto personalizado:", value="My brother", placeholder="Ej: Maria, The dogs, Carlos")
        else:
            subject_val = st.selectbox("Selecciona sujeto:", options=list(SUBJECTS.keys()), index=2)

    with c2:
        st.markdown("**2️⃣ Verbo / Modal / Tiempo**")
        structures = [
            "Presente Simple (do / does)",
            "Pasado Simple (did)",
            "Futuro Simple (will)",
            "Modal: can",
            "Modal: could",
            "Modal: should",
            "Modal: must",
            "Modal: may",
            "Modal: might",
            "To Be (Presente: am/is/are)",
            "To Be (Pasado: was/were)",
            "Have (Presente Simple: have/has)",
        ]
        struct_val = st.selectbox("Estructura gramatical:", options=structures, index=3)

    with c3:
        st.markdown("**3️⃣ Acción (Verbo base)**")
        verb_mode = st.toggle("Escribir verbo libre", key="t_verb")
        is_to_be_or_have = struct_val.startswith(("To Be", "Have"))
        if verb_mode:
            action_val = st.text_input(
                "Verbo en forma base:",
                value="" if is_to_be_or_have else "design",
                placeholder="Ej: cook, run, build (opcional en To Be)",
            )
        else:
            verb_options = ["(ninguno - para To Be / Have)"] + list(VERBS_DB.keys())
            default_v_idx = 0 if is_to_be_or_have else 3
            sel_v = st.selectbox("Selecciona acción:", options=verb_options, index=default_v_idx)
            action_val = "" if sel_v.startswith("(") else sel_v

    with c4:
        st.markdown("**4️⃣ Complemento**")
        comp_mode = st.toggle("Escribir complemento libre", key="t_comp")
        if comp_mode:
            comp_val = st.text_input("Complemento:", value="every morning", placeholder="Ej: in Cali, very well")
        else:
            comp_val = st.selectbox("Selecciona complemento:", options=list(COMPLEMENTS_PRESETS.keys()), index=0)

    result = build_sentences(subject_val, struct_val, action_val, comp_val)

    for w in result["warnings"]:
        st.warning(w)

    st.divider()
    st.subheader("2. Resultados generados en tiempo real")

    col_aff, col_neg, col_ques = st.columns(3)

    with col_aff:
        st.success(f"**➕ Afirmativa**\n\n### {result['affirmative']}")
        if st.button("🔊 Escuchar Afirmativa", key="tts_aff", use_container_width=True):
            audio_bytes = synthesize_speech(result["affirmative"], is_slow, selected_tld)
            st.audio(audio_bytes, format="audio/mp3", autoplay=True)

    with col_neg:
        st.error(f"**➖ Negativa**\n\n### {result['negative']}")
        if st.button("🔊 Escuchar Negativa", key="tts_neg", use_container_width=True):
            audio_bytes = synthesize_speech(result["negative"], is_slow, selected_tld)
            st.audio(audio_bytes, format="audio/mp3", autoplay=True)

    with col_ques:
        st.info(f"**❓ Interrogativa**\n\n### {result['interrogative']}")
        if st.button("🔊 Escuchar Pregunta", key="tts_ques", use_container_width=True):
            audio_bytes = synthesize_speech(result["interrogative"], is_slow, selected_tld)
            st.audio(audio_bytes, format="audio/mp3", autoplay=True)

    st.markdown("---")
    c_trans, c_gram = st.columns([1, 1.4])

    with c_trans:
        st.markdown("#### 🇪🇸 Referencia en Español (Afirmativa)")
        st.info(f"**Traducción aproximada:**\n\n{result['spanish']}")
        if st.button("💾 Guardar oración en historial", use_container_width=True):
            entry = f"{result['affirmative']} | {result['negative']} | {result['interrogative']}"
            if entry not in st.session_state.history:
                st.session_state.history.append(entry)
                st.toast("Oración guardada en tu historial de sesión.")

    with c_gram:
        st.markdown("#### 🧠 Análisis y Reglas Gramaticales")
        for note in result["notes"]:
            st.markdown(f"- {note}")

    if st.session_state.history:
        with st.expander(f"📜 Historial de oraciones construidas ({len(st.session_state.history)})"):
            for idx, item in enumerate(reversed(st.session_state.history), 1):
                st.markdown(f"{idx}. `{item}`")

# ------------------------------------------------------------------------------
# TAB 2: ESTUDIO DE SHADOWING (ESTILO CURSO DE IDIOMAS)
# ------------------------------------------------------------------------------
with tab_shadowing:
    st.subheader("🎧 Estudio de Shadowing (Imitación Activa y Ritmo)")
    st.markdown(
        """
        **¿Cómo trabajar esta sección como en un curso de Shadowing?**
        1. **Escucha ciega:** Activa *Ocultar texto en inglés* y escucha el audio 2 veces captando la melodía.
        2. **Lectura rítmica:** Muestra el texto con **golpes de voz en negrita** y pausas `/`.
        3. **Bucle con pausas (Listen & Repeat):** Usa la pista continua que deja silencio después de cada frase para repetir en voz alta sin detener el audio.
        4. **Shadowing simultáneo + Grabación:** Habla *al mismo tiempo* que el locutor y graba tu voz para compararla.
        """
    )

    st.divider()

    source_mode = st.radio(
        "Selecciona el material de entrenamiento:",
        options=[
            "📚 Lecciones Guiadas del Curso",
            "🧩 Oraciones creadas en la Matriz",
            "✍️ Texto personalizado / Subir audio propio",
        ],
        horizontal=True,
    )

    # Controles visuales de entrenamiento
    ctrl1, ctrl2, ctrl3 = st.columns(3)
    with ctrl1:
        blind_mode = st.toggle("🙈 Modo Escucha Ciega (Ocultar inglés)", value=False)
    with ctrl2:
        show_chunks = st.toggle("🎵 Mostrar ritmo y acentos (Chunks)", value=True)
    with ctrl3:
        show_es_sub = st.toggle("🇪🇸 Mostrar traducción al español", value=True)

    active_sentences = []
    lesson_id = "custom"

    # MODO A: LECCIONES GUIADAS
    if source_mode == "📚 Lecciones Guiadas del Curso":
        lesson_titles = [l["title"] for l in SHADOWING_LESSONS]
        sel_lesson_title = st.selectbox("Elige una lección:", options=lesson_titles)
        lesson = next(l for l in SHADOWING_LESSONS if l["title"] == sel_lesson_title)
        lesson_id = lesson["id"]
        st.caption(f"Nivel recomendado: **{lesson['level']}**")

        active_sentences = [s["en"] for s in lesson["sentences"]]

        # Reproductor Maestro de la Lección (Pista continua con pausas)
        st.markdown("### 🔁 Pista Maestra de Entrenamiento (Con pausas para repetir)")
        col_loop1, col_loop2 = st.columns([1, 2])
        with col_loop1:
            reps = st.selectbox("Repeticiones por frase:", options=[1, 2, 3], index=1)
        with col_loop2:
            if st.button("▶️ Generar Pista de Shadowing Completa", type="primary", use_container_width=True):
                loop_audio = synthesize_shadowing_loop(tuple(active_sentences), is_slow, selected_tld, reps)
                st.audio(loop_audio, format="audio/mp3", autoplay=True)

        st.markdown("### 📝 Desglose Frase por Frase (Shadowing Intensivo)")
        for idx, item in enumerate(lesson["sentences"], 1):
            with st.container(border=True):
                c_txt, c_aud = st.columns([2.2, 1])
                with c_txt:
                    st.markdown(f"**Frase {idx}**")
                    if blind_mode:
                        st.info("🙈 *Texto oculto — escucha el audio e intenta repetir lo que oyes.*")
                    else:
                        if show_chunks:
                            st.markdown(f"#### {item['chunks']}")
                            st.caption(f"Texto limpio: {item['en']}")
                        else:
                            st.markdown(f"#### {item['en']}")
                    if show_es_sub:
                        st.markdown(f"🇪🇸 *{item['es']}*")
                    st.caption(f"💡 **Tip de pronunciación / Linking:** {item['tip']}")

                with c_aud:
                    if st.button(f"🔊 Escuchar Frase {idx}", key=f"sh_btn_{lesson_id}_{idx}", use_container_width=True):
                        s_audio = synthesize_speech(item["en"], is_slow, selected_tld)
                        st.audio(s_audio, format="audio/mp3", autoplay=True)

    # MODO B: ORACIONES DE LA MATRIZ
    elif source_mode == "🧩 Oraciones creadas en la Matriz":
        lesson_id = "matrix_live"
        matrix_triplet = [
            ("Afirmativa (+)", result["affirmative"]),
            ("Negativa (-)", result["negative"]),
            ("Interrogativa (?)", result["interrogative"]),
        ]
        active_sentences = [t[1] for t in matrix_triplet]

        st.info("Entrenando las 3 variaciones generadas actualmente en la pestaña **Matriz Interactiva**.")

        if st.button("🔁 Generar Bucle de Shadowing (Afirmativa + Negativa + Pregunta)", type="primary"):
            loop_audio = synthesize_shadowing_loop(tuple(active_sentences), is_slow, selected_tld, repeat_each=2)
            st.audio(loop_audio, format="audio/mp3", autoplay=True)

        for idx, (label, sent) in enumerate(matrix_triplet, 1):
            with st.container(border=True):
                c_t, c_a = st.columns([2.2, 1])
                with c_t:
                    st.markdown(f"**{label}**")
                    if blind_mode:
                        st.info("🙈 *Texto oculto para entrenamiento auditivo.*")
                    else:
                        st.markdown(f"#### {sent}")
                with c_a:
                    if st.button(f"🔊 Practicar {label}", key=f"sh_mat_{idx}", use_container_width=True):
                        s_audio = synthesize_speech(sent, is_slow, selected_tld)
                        st.audio(s_audio, format="audio/mp3", autoplay=True)

    # MODO C: TEXTO PERSONALIZADO O AUDIO EXTERNO
    else:
        lesson_id = "custom_text"
        custom_paragraph = st.text_area(
            "Pega aquí un diálogo, párrafo o lista de frases en inglés (una por línea o separadas por punto):",
            value="Hello! How is everything going today?\nI am practicing my English pronunciation using the shadowing technique.\nIf I practice every day, my fluency will improve very fast.",
            height=130,
        )
        raw_lines = [line.strip() for line in re.split(r"[\n]+", custom_paragraph) if line.strip()]
        active_sentences = raw_lines

        col_c1, col_c2 = st.columns(2)
        with col_c1:
            if st.button("🔊 Escuchar párrafo completo fluido", use_container_width=True):
                full_audio = synthesize_speech(" ".join(active_sentences), is_slow, selected_tld)
                st.audio(full_audio, format="audio/mp3", autoplay=True)
        with col_c2:
            if st.button("🔁 Generar pista con pausas frase por frase", type="primary", use_container_width=True):
                loop_audio = synthesize_shadowing_loop(tuple(active_sentences), is_slow, selected_tld, repeat_each=2)
                st.audio(loop_audio, format="audio/mp3", autoplay=True)

        if not blind_mode:
            for idx, line in enumerate(active_sentences, 1):
                with st.container(border=True):
                    c_l1, c_l2 = st.columns([2.5, 1])
                    c_l1.markdown(f"**{idx}.** {line}")
                    if c_l2.button(f"🔊 Frase {idx}", key=f"cust_sh_{idx}", use_container_width=True):
                        st.audio(synthesize_speech(line, is_slow, selected_tld), format="audio/mp3", autoplay=True)

        st.markdown("---")
        uploaded_audio = st.file_uploader("📂 O sube un archivo de audio MP3/WAV de tu curso externo:", type=["mp3", "wav", "ogg"])
        if uploaded_audio is not None:
            st.audio(uploaded_audio)

    # LABORATORIO DE GRABACIÓN Y COMPARACIÓN (Disponible en todos los modos)
    st.divider()
    st.markdown("### 🎙️ Cabina de Grabación y Autoevaluación")
    st.caption("Graba tu voz imitando la entonación y velocidad del audio nativo, y luego escúchate para detectar diferencias.")

    rec_col1, rec_col2 = st.columns([1.5, 1])
    with rec_col1:
        user_recording = st.audio_input("Haz clic en el micrófono para grabar tu práctica de Shadowing:")
        if user_recording is not None:
            st.success("✅ Grabación lista. Reprodúcela arriba y compárala con el modelo nativo.")

    with rec_col2:
        st.markdown("**Registro de sesión**")
        if st.button("🏅 Marcar esta sesión de Shadowing como completada", use_container_width=True):
            tag = f"{lesson_id}_{len(st.session_state.shadowing_completed) + 1}"
            st.session_state.shadowing_completed.append(tag)
            st.toast("¡Sesión de Shadowing sumada a tu progreso!")
            st.rerun()

# ------------------------------------------------------------------------------
# TAB 3: EJERCICIOS GUIADOS
# ------------------------------------------------------------------------------
with tab_practice:
    st.subheader("🎯 Práctica Activa de Traducción y Estructura")
    st.write("Traduce o reconstruye la oración en inglés aplicando las reglas de auxiliares y modales.")

    if st.session_state.current_challenge is None:
        st.session_state.current_challenge = random.choice(CHALLENGES)

    ch = st.session_state.current_challenge

    col_ch1, col_ch2 = st.columns([2, 1])
    with col_ch1:
        st.info(f"**Reto en Español:**\n\n### {ch['es']}")
    with col_ch2:
        if st.button("🔄 Nuevo reto aleatorio", use_container_width=True):
            available = [c for c in CHALLENGES if c != ch]
            st.session_state.current_challenge = random.choice(available)
            st.rerun()
        with st.expander("💡 Ver pista gramatical"):
            st.write(ch["hint"])

    user_ans = st.text_input("Escribe tu respuesta en inglés:", key="challenge_input", placeholder="Escribe la oración completa aquí...")

    if st.button("✅ Verificar respuesta", type="primary"):
        if not user_ans.strip():
            st.warning("Escribe una oración antes de verificar.")
        else:
            st.session_state.attempts += 1
            norm_user = re.sub(r"[?.!,]", "", user_ans.strip().lower())
            norm_user = re.sub(r"\s+", " ", norm_user)
            norm_target = re.sub(r"[?.!,]", "", ch["en"].strip().lower())

            norm_user_expanded = (
                norm_user.replace("can't", "cannot")
                .replace("don't", "do not")
                .replace("doesn't", "does not")
                .replace("didn't", "did not")
                .replace("won't", "will not")
                .replace("isn't", "is not")
                .replace("aren't", "are not")
            )

            if norm_user == norm_target or norm_user_expanded == norm_target:
                st.session_state.score += 1
                st.success(f"🎉 ¡Excelente! Respuesta correcta: **{ch['en']}**")
                audio_ok = synthesize_speech(ch["en"], is_slow, selected_tld)
                st.audio(audio_ok, format="audio/mp3")
            else:
                st.error(f"❌ No coincide exactamente.\n\n- **Tu respuesta:** `{user_ans}`\n- **Forma esperada:** `{ch['en']}`\n- **Regla clave:** {ch['hint']}")

# ------------------------------------------------------------------------------
# TAB 4: GUÍA RÁPIDA DE ESTRUCTURAS
# ------------------------------------------------------------------------------
with tab_reference:
    st.subheader("📘 Tabla Maestra de Referencia Rápida")
    st.markdown(
        """
| Tipo de Estructura | Auxiliar / Verbo | Regla en Afirmativa (+) | Regla en Negativa (-) | Regla en Pregunta (?) |
| :--- | :--- | :--- | :--- | :--- |
| **Modales** (`can`, `could`, `should`, `must`, `may`, `might`) | El mismo modal | `Sujeto + Modal + Verbo Base` | `Sujeto + Modal + not + Verbo Base` | `Modal + Sujeto + Verbo Base?` |
| **To Be (Presente)** | `am` / `is` / `are` | `Sujeto + am/is/are + Comp.` | `Sujeto + am/is/are + not + Comp.` | `Am/Is/Are + Sujeto + Comp.?` |
| **To Be (Pasado)** | `was` / `were` | `Sujeto + was/were + Comp.` | `Sujeto + was/were + not + Comp.` | `Was/Were + Sujeto + Comp.?` |
| **Presente Simple** | `do` / `does` | `Sujeto + Verbo (-s en He/She/It)` | `Sujeto + do/does + not + Verbo Base` | `Do/Does + Sujeto + Verbo Base?` |
| **Pasado Simple** | `did` | `Sujeto + Verbo en Pasado` | `Sujeto + did + not + Verbo Base` | `Did + Sujeto + Verbo Base?` |
| **Futuro Simple** | `will` | `Sujeto + will + Verbo Base` | `Sujeto + will + not + Verbo Base` | `Will + Sujeto + Verbo Base?` |
| **Have (Posesión)** | `have` / `has` (`do`/`does`) | `Sujeto + have/has + Objeto` | `Sujeto + do/does + not + have + Objeto` | `Do/Does + Sujeto + have + Objeto?` |
        """
    )