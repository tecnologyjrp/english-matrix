import io
import re
import json
import sqlite3
import random
from datetime import datetime
import streamlit as st
from gtts import gTTS

# ==============================================================================
# CONFIGURACIÓN DE PÁGINA Y BASE DE DATOS SQLITE
# ==============================================================================
st.set_page_config(
    page_title="English Sentence Matrix & Shadowing Lab",
    page_icon="🧩",
    layout="wide",
    initial_sidebar_state="expanded",
)

DB_PATH = "english_progress.db"


def get_connection():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with get_connection() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS user_stats (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                score INTEGER NOT NULL DEFAULT 0,
                attempts INTEGER NOT NULL DEFAULT 0,
                updated_at TEXT
            )
            """
        )
        conn.execute(
            """
            INSERT OR IGNORE INTO user_stats (id, score, attempts, updated_at)
            VALUES (1, 0, 0, ?)
            """,
            (datetime.now().strftime("%Y-%m-%d %H:%M:%S"),),
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS sentence_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                affirmative TEXT NOT NULL,
                negative TEXT NOT NULL,
                interrogative TEXT NOT NULL,
                spanish TEXT,
                structure TEXT,
                created_at TEXT NOT NULL,
                UNIQUE(affirmative, negative, interrogative)
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS shadowing_progress (
                lesson_id TEXT PRIMARY KEY,
                lesson_title TEXT,
                completed_count INTEGER NOT NULL DEFAULT 1,
                last_completed_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS exercise_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                prompt_es TEXT NOT NULL,
                target_en TEXT NOT NULL,
                user_answer TEXT NOT NULL,
                is_correct INTEGER NOT NULL,
                attempted_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS exam_results (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                exam_level TEXT NOT NULL,
                exam_topic TEXT NOT NULL,
                total_questions INTEGER NOT NULL,
                correct_answers INTEGER NOT NULL,
                percentage REAL NOT NULL,
                passed INTEGER NOT NULL,
                details_json TEXT NOT NULL,
                taken_at TEXT NOT NULL
            )
            """
        )
        conn.commit()


def load_stats() -> dict:
    with get_connection() as conn:
        row = conn.execute("SELECT score, attempts FROM user_stats WHERE id = 1").fetchone()
        return {"score": row["score"], "attempts": row["attempts"]} if row else {"score": 0, "attempts": 0}


def update_stats(score_delta: int, attempts_delta: int):
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with get_connection() as conn:
        conn.execute(
            """
            UPDATE user_stats
            SET score = score + ?, attempts = attempts + ?, updated_at = ?
            WHERE id = 1
            """,
            (score_delta, attempts_delta, now_str),
        )
        conn.commit()


def save_sentence_db(aff: str, neg: str, ques: str, spanish: str, structure: str) -> bool:
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with get_connection() as conn:
        cur = conn.execute(
            """
            INSERT OR IGNORE INTO sentence_history
            (affirmative, negative, interrogative, spanish, structure, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (aff, neg, ques, spanish, structure, now_str),
        )
        conn.commit()
        return cur.rowcount > 0


def load_sentence_history() -> list:
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT id, affirmative, negative, interrogative, spanish, structure, created_at
            FROM sentence_history
            ORDER BY id DESC
            """
        ).fetchall()
        return [dict(r) for r in rows]


def delete_sentence_db(sentence_id: int):
    with get_connection() as conn:
        conn.execute("DELETE FROM sentence_history WHERE id = ?", (sentence_id,))
        conn.commit()


def mark_shadowing_db(lesson_id: str, lesson_title: str):
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO shadowing_progress (lesson_id, lesson_title, completed_count, last_completed_at)
            VALUES (?, ?, 1, ?)
            ON CONFLICT(lesson_id) DO UPDATE SET
                completed_count = completed_count + 1,
                lesson_title = excluded.lesson_title,
                last_completed_at = excluded.last_completed_at
            """,
            (lesson_id, lesson_title, now_str),
        )
        conn.commit()


def load_shadowing_progress() -> dict:
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT lesson_id, lesson_title, completed_count, last_completed_at FROM shadowing_progress"
        ).fetchall()
        return {r["lesson_id"]: dict(r) for r in rows}


def log_exercise_attempt(prompt_es: str, target_en: str, user_answer: str, is_correct: bool):
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO exercise_logs (prompt_es, target_en, user_answer, is_correct, attempted_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (prompt_es, target_en, user_answer, 1 if is_correct else 0, now_str),
        )
        conn.commit()


def load_exercise_logs(limit: int = 20) -> list:
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT prompt_es, target_en, user_answer, is_correct, attempted_at
            FROM exercise_logs
            ORDER BY id DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
        return [dict(r) for r in rows]


def save_exam_result_db(exam_level: str, exam_topic: str, total_q: int, correct_q: int, details: list) -> int:
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    pct = round((correct_q / total_q) * 100, 1) if total_q > 0 else 0.0
    passed = 1 if pct >= 70.0 else 0
    with get_connection() as conn:
        cur = conn.execute(
            """
            INSERT INTO exam_results
            (exam_level, exam_topic, total_questions, correct_answers, percentage, passed, details_json, taken_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (exam_level, exam_topic, total_q, correct_q, pct, passed, json.dumps(details, ensure_ascii=False), now_str),
        )
        conn.commit()
        return cur.lastrowid


def load_exam_results() -> list:
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT id, exam_level, exam_topic, total_questions, correct_answers, percentage, passed, details_json, taken_at
            FROM exam_results
            ORDER BY id DESC
            """
        ).fetchall()
        return [dict(r) for r in rows]


def delete_exam_result_db(exam_id: int):
    with get_connection() as conn:
        conn.execute("DELETE FROM exam_results WHERE id = ?", (exam_id,))
        conn.commit()


def reset_all_db():
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with get_connection() as conn:
        conn.execute("UPDATE user_stats SET score = 0, attempts = 0, updated_at = ? WHERE id = 1", (now_str,))
        conn.execute("DELETE FROM sentence_history")
        conn.execute("DELETE FROM shadowing_progress")
        conn.execute("DELETE FROM exercise_logs")
        conn.execute("DELETE FROM exam_results")
        conn.commit()


init_db()

if "current_challenge" not in st.session_state:
    st.session_state.current_challenge = None
if "active_exam" not in st.session_state:
    st.session_state.active_exam = None
if "last_exam_report" not in st.session_state:
    st.session_state.last_exam_report = None

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
        "id": "sh_a1_01",
        "title": "01. Presentaciones y Rutina Cotidiana (A1)",
        "level": "A1 - Principiante",
        "category": "Diálogos Cotidianos",
        "sentences": [
            {
                "speaker": "A",
                "en": "Hi! My name is Carlos and I live in Colombia.",
                "chunks": "**Hi!** / My **name** is **Car**los / and I **live** in Co**lom**bia.",
                "es": "¡Hola! Mi nombre es Carlos y vivo en Colombia.",
                "tip": "Une 'name is' como /nei-miz/ y 'live in' como /li-vin/.",
            },
            {
                "speaker": "B",
                "en": "Nice to meet you! What do you usually do in the morning?",
                "chunks": "**Nice** to **meet** you! / What do you **u**sually **do** / in the **mor**ning?",
                "es": "¡Mucho gusto! ¿Qué haces normalmente en la mañana?",
                "tip": "'Meet you' suele sonar suavizado como /mi-chu/ en habla natural.",
            },
            {
                "speaker": "A",
                "en": "I wake up at six, drink coffee, and check my phone.",
                "chunks": "I wake **up** at **six**, / drink **cof**fee, / and **check** my **phone**.",
                "es": "Me despierto a las seis, tomo café y reviso mi teléfono.",
                "tip": "Conecta 'wake up at' de forma fluida: /wei-ka-pat/.",
            },
            {
                "speaker": "B",
                "en": "That sounds great! Do you work from home or in an office?",
                "chunks": "That **sounds** **great**! / Do you **work** from **home** / or in an **o**ffice?",
                "es": "¡Suena genial! ¿Trabajas desde casa o en una oficina?",
                "tip": "Une 'in an office' en un solo bloque rítmico: /i-na-no-fis/.",
            },
        ],
    },
    {
        "id": "sh_a1_02",
        "title": "02. Pidiendo en un Café o Restaurante Rápido (A1)",
        "level": "A1 - Principiante",
        "category": "Restaurantes",
        "sentences": [
            {
                "speaker": "Mesero",
                "en": "Good morning! Can I take your order?",
                "chunks": "Good **mor**ning! / Can I **take** your **or**der?",
                "es": "¡Buenos días! ¿Puedo tomar su orden?",
                "tip": "'Can I' se pronuncia rápido y ligado: /ka-nai/.",
            },
            {
                "speaker": "Cliente",
                "en": "Yes, please. I would like a chicken sandwich and a bottle of water.",
                "chunks": "**Yes**, please. / I would **like** a **chi**cken **sand**wich / and a **bo**ttle of **wa**ter.",
                "es": "Sí, por favor. Quisiera un sándwich de pollo y una botella de agua.",
                "tip": "En inglés americano, 'bottle of water' suena cercano a /ba-dl-ov-wa-der/.",
            },
            {
                "speaker": "Mesero",
                "en": "Would you like anything else, maybe some dessert?",
                "chunks": "Would you **like** **a**nything **else**, / **may**be some de**ssert**?",
                "es": "¿Le gustaría algo más, tal vez algún postre?",
                "tip": "'Would you' se fusiona naturalmente en /wud-yu/.",
            },
            {
                "speaker": "Cliente",
                "en": "No, thank you. How much is the total?",
                "chunks": "**No**, **thank** you. / How **much** is the **to**tal?",
                "es": "No, gracias. ¿Cuánto es el total?",
                "tip": "Conecta 'much is' como /ma-chiz/ con entonación descendente al final.",
            },
        ],
    },
    {
        "id": "sh_a2_01",
        "title": "03. Planes de Fin de Semana con Amigos (A2)",
        "level": "A2 - Elemental",
        "category": "Diálogos Cotidianos",
        "sentences": [
            {
                "speaker": "A",
                "en": "Are you free this Saturday afternoon? We are going to the countryside.",
                "chunks": "Are you **free** this **Sa**turday after**noon**? / We are **go**ing to the **coun**tryside.",
                "es": "¿Estás libre este sábado por la tarde? Vamos a ir al campo.",
                "tip": "'Going to' en conversación cotidiana suele reducirse a /go-na/.",
            },
            {
                "speaker": "B",
                "en": "I would love to go, but I have to finish a family project first.",
                "chunks": "I would **love** to **go**, / but I **have** to **fi**nish / a **fa**mily **pro**ject **first**.",
                "es": "Me encantaría ir, pero primero tengo que terminar un proyecto familiar.",
                "tip": "'Have to' cuando indica obligación suena /haf-tu/ (con sonido 'f').",
            },
            {
                "speaker": "A",
                "en": "No problem at all! We can pick you up around four if you finish early.",
                "chunks": "No **pro**blem at **all**! / We can **pick** you **up** a**round** **four** / if you **fi**nish **ear**ly.",
                "es": "¡No hay ningún problema! Podemos recogerte alrededor de las cuatro si terminas temprano.",
                "tip": "'Problem at all' se encadena como /pro-ble-ma-tol/.",
            },
            {
                "speaker": "B",
                "en": "That works for me. I will text you as soon as I am ready.",
                "chunks": "That **works** for **me**. / I will **text** you / as **soon** as I am **rea**dy.",
                "es": "Me funciona perfecto. Te escribo tan pronto como esté listo.",
                "tip": "En 'as soon as', las palabras 'as' son débiles: /ez-su-nez/.",
            },
        ],
    },
    {
        "id": "sh_a2_02",
        "title": "04. Check-in y Solicitudes en un Hotel (A2)",
        "level": "A2 - Elemental",
        "category": "Hoteles",
        "sentences": [
            {
                "speaker": "Huésped",
                "en": "Hello, I have a reservation under the name Rivera for four nights.",
                "chunks": "He**llo**, / I have a reser**va**tion / **un**der the name Ri**ve**ra / for **four** **nights**.",
                "es": "Hola, tengo una reservación a nombre de Rivera por cuatro noches.",
                "tip": "Marca bien la 's' final en 'nights' para diferenciar singular y plural.",
            },
            {
                "speaker": "Recepcionista",
                "en": "Welcome! Could I see your passport and a credit card for incidentals?",
                "chunks": "**Wel**come! / Could I **see** your **pass**port / and a **cre**dit **card** for inci**den**tals?",
                "es": "¡Bienvenido! ¿Podría ver su pasaporte y una tarjeta de crédito para gastos adicionales?",
                "tip": "Une 'Could I' como /ku-dai/ y 'and a' como /a-na/.",
            },
            {
                "speaker": "Huésped",
                "en": "Here you go. Also, is breakfast included in our booking?",
                "chunks": "**Here** you **go**. / **Al**so, is **break**fast in**clu**ded / in our **boo**king?",
                "es": "Aquí tiene. Además, ¿el desayuno está incluido en nuestra reserva?",
                "tip": "Pronuncia 'breakfast' en dos sílabas cortas: /brek-fast/ (no /breik/).",
            },
            {
                "speaker": "Recepcionista",
                "en": "Yes, breakfast is served from seven to ten in the main dining room.",
                "chunks": "**Yes**, **break**fast is **served** / from **se**ven to **ten** / in the **main** **di**ning room.",
                "es": "Sí, el desayuno se sirve de siete a diez en el comedor principal.",
                "tip": "Conecta 'breakfast is' como /brek-fas-tiz/.",
            },
        ],
    },
    {
        "id": "sh_b1_01",
        "title": "05. Reservación y Reclamo Amable en Restaurante (B1)",
        "level": "B1 - Intermedio",
        "category": "Restaurantes",
        "sentences": [
            {
                "speaker": "Cliente",
                "en": "Good evening. We booked a table for five people on the terrace at eight.",
                "chunks": "Good **e**vening. / We **booked** a **ta**ble for **five** **peo**ple / on the **te**rrace at **eight**.",
                "es": "Buenas noches. Reservamos una mesa para cinco personas en la terraza a las ocho.",
                "tip": "El pasado 'booked' termina en sonido /t/: /bukt a tei-bol/.",
            },
            {
                "speaker": "Anfitrión",
                "en": "Right this way, please. Our chef recommends the grilled salmon tonight.",
                "chunks": "**Right** this **way**, please. / Our **chef** recom**mends** / the **grilled** **sal**mon to**night**.",
                "es": "Por aquí, por favor. Nuestro chef recomienda el salmón a la parrilla esta noche.",
                "tip": "En 'salmon', la letra 'l' es muda: /sa-mon/.",
            },
            {
                "speaker": "Cliente",
                "en": "Excuse me, I ordered my steak medium-well, and this one is still quite rare.",
                "chunks": "Ex**cuse** me, / I **or**dered my **steak** **me**dium-**well**, / and **this** one is **still** quite **rare**.",
                "es": "Disculpe, pedí mi corte tres cuartos, y este todavía está bastante crudo.",
                "tip": "Mantén un tono cortés pero firme elevando ligeramente la voz en 'medium-well'.",
            },
            {
                "speaker": "Mesero",
                "en": "I sincerely apologize for that. Let me bring you a fresh one right away.",
                "chunks": "I sin**cere**ly a**po**logize for **that**. / Let me **bring** you a **fresh** one / **right** a**way**.",
                "es": "Me disculpo sinceramente por eso. Permítame traerle uno recién hecho de inmediato.",
                "tip": "'Right away' se pronuncia unido como /rai-da-wei/.",
            },
        ],
    },
    {
        "id": "sh_b1_02",
        "title": "06. Resolviendo un Inconveniente en el Hotel (B1)",
        "level": "B1 - Intermedio",
        "category": "Hoteles",
        "sentences": [
            {
                "speaker": "Huésped",
                "en": "Hi, I am calling from room four-twelve because the air conditioning is not cooling.",
                "chunks": "**Hi**, I am **cal**ling from room **four**-**twelve** / be**cause** the **air** con**di**tioning / is **not** **coo**ling.",
                "es": "Hola, llamo desde la habitación 412 porque el aire acondicionado no está enfriando.",
                "tip": "Agrupa 'air conditioning' como una unidad rítmica con acento en '-di-'.",
            },
            {
                "speaker": "Recepcionista",
                "en": "I am sorry to hear that. Would you like us to send maintenance or move you to another room?",
                "chunks": "I am **so**rry to **hear** that. / Would you **like** us to send **main**tenance / or **move** you to a**no**ther **room**?",
                "es": "Lamento escuchar eso. ¿Le gustaría que enviemos mantenimiento o cambiarlo a otra habitación?",
                "tip": "'Maintenance' se reduce a dos sílabas fuertes: /meint-nens/.",
            },
            {
                "speaker": "Huésped",
                "en": "If you have a quiet room available on a higher floor, moving would be much better.",
                "chunks": "If you **have** a **qui**et **room** a**vai**lable / on a **high**er **floor**, / **mo**ving would be **much** **be**tter.",
                "es": "Si tienen una habitación tranquila disponible en un piso más alto, cambiarme sería mucho mejor.",
                "tip": "Conecta 'have a' como /ha-va/ y 'on a' como /o-na/.",
            },
            {
                "speaker": "Recepcionista",
                "en": "Certainly. I have upgraded you to a suite on the eighth floor at no extra charge.",
                "chunks": "**Cer**tainly. / I have up**gra**ded you to a **suite** / on the **eighth** **floor** / at **no** **ex**tra **charge**.",
                "es": "Por supuesto. Le he hecho un ascenso a una suite en el octavo piso sin cargo adicional.",
                "tip": "'Suite' se pronuncia exactamente igual que 'sweet': /suit/.",
            },
        ],
    },
    {
        "id": "sh_b2_01",
        "title": "07. Reunión de Seguimiento Técnico y Servidores (B2)",
        "level": "B2 - Intermedio Alto",
        "category": "Trabajo",
        "sentences": [
            {
                "speaker": "Líder",
                "en": "Before we migrate the database, we should double-check all user permissions and cron jobs.",
                "chunks": "Be**fore** we **mi**grate the **da**tabase, / we should **dou**ble-**check** / all **u**ser per**mi**ssions and **cron** **jobs**.",
                "es": "Antes de migrar la base de datos, deberíamos revisar doblemente todos los permisos de usuario y tareas programadas.",
                "tip": "Marca pausa breve tras 'database,' para dar claridad ejecutiva a la condición.",
            },
            {
                "speaker": "Ingeniero",
                "en": "I already tested the staging environment, and query performance improved by thirty percent.",
                "chunks": "I al**rea**dy **tes**ted the **sta**ging en**vi**ronment, / and **que**ry per**for**mance im**proved** / by **thir**ty per**cent**.",
                "es": "Ya probé el entorno de pruebas y el rendimiento de las consultas mejoró en un treinta por ciento.",
                "tip": "Pronuncia 'environment' cuidando la 'n' intermedia: /en-vai-ron-ment/.",
            },
            {
                "speaker": "Líder",
                "en": "What happens if an unexpected bottleneck occurs during peak hours tomorrow?",
                "chunks": "What **ha**ppens if an unex**pec**ted **bo**ttleneck oc**curs** / **du**ring **peak** **hours** to**mo**rrow?",
                "es": "¿Qué ocurre si se presenta un cuello de botella inesperado durante las horas pico mañana?",
                "tip": "Une 'if an unexpected' de manera fluida: /i-fa-na-niks-pek-tid/.",
            },
            {
                "speaker": "Ingeniero",
                "en": "We have automated rollback scripts ready, so downtime would be under two minutes.",
                "chunks": "We have **au**tomated **roll**back **scripts** **rea**dy, / so **down**time would be / **un**der **two** **mi**nutes.",
                "es": "Tenemos listos scripts automatizados de reversión, así que el tiempo de inactividad sería menor a dos minutos.",
                "tip": "Enfatiza 'automated' y 'under two minutes' para proyectar seguridad profesional.",
            },
        ],
    },
    {
        "id": "sh_b2_02",
        "title": "08. Negociación de Plazos y Entregables en el Trabajo (B2)",
        "level": "B2 - Intermedio Alto",
        "category": "Trabajo",
        "sentences": [
            {
                "speaker": "Gerente",
                "en": "Given the new scope requirements, do you think we can still meet Friday's deadline?",
                "chunks": "**Gi**ven the **new** **scope** re**quire**ments, / do you **think** we can **still** **meet** / **Fri**day's **dead**line?",
                "es": "Dados los nuevos requisitos de alcance, ¿crees que aún podamos cumplir con la fecha límite del viernes?",
                "tip": "Enfatiza 'still meet' para destacar la pregunta clave sobre el plazo.",
            },
            {
                "speaker": "Especialista",
                "en": "Honestly, delivering everything by Friday might compromise quality unless we prioritize core features.",
                "chunks": "**Ho**nestly, de**li**vering **e**verything by **Fri**day / might **com**promise **qua**lity / un**less** we pri**o**ritize **core** **fea**tures.",
                "es": "Honestamente, entregar todo para el viernes podría comprometer la calidad a menos que prioricemos las funciones principales.",
                "tip": "La 'h' en 'Honestly' es completamente muda: /o-nest-li/.",
            },
            {
                "speaker": "Gerente",
                "en": "That makes complete sense. Let us deploy the core module first and schedule phase two for Tuesday.",
                "chunks": "That **makes** com**plete** **sense**. / Let us de**ploy** the **core** **mo**dule **first** / and **sche**dule **phase** **two** for **Tues**day.",
                "es": "Tiene todo el sentido. Despleguemos primero el módulo principal y programemos la fase dos para el martes.",
                "tip": "En inglés americano, 'schedule' suena /ske-dyul/; en británico /she-dyul/.",
            },
            {
                "speaker": "Especialista",
                "en": "Agreed. I will send out an updated roadmap right after this meeting wraps up.",
                "chunks": "A**greed**. / I will **send** **out** an up**da**ted **road**map / **right** **af**ter this **mee**ting **wraps** **up**.",
                "es": "De acuerdo. Enviaré una hoja de ruta actualizada justo después de que termine esta reunión.",
                "tip": "Conecta los phrasal verbs: 'send out' (/sen-daut/) y 'wraps up' (/rap-sap/).",
            },
        ],
    },
]

# ==============================================================================
# BANCO DE PREGUNTAS PARA EXÁMENES (A1, A2, B1, B2)
# ==============================================================================
EXAM_BANK = [
    # A1
    {
        "id": "ex_01",
        "level": "A1 - Básico",
        "topic": "To Be & Presente Simple",
        "type": "choice",
        "question": "Selecciona la forma correcta: 'She ___ in Cali and ___ every morning.'",
        "options": [
            "live / work",
            "lives / works",
            "is live / works",
            "living / work",
        ],
        "answer": "lives / works",
        "explanation": "En presente simple afirmativo con tercera persona singular ('She'), los verbos llevan '-s'.",
    },
    {
        "id": "ex_02",
        "level": "A1 - Básico",
        "topic": "To Be & Presente Simple",
        "type": "choice",
        "question": "¿Cuál es la forma interrogativa correcta de 'They are ready for the trip'?",
        "options": [
            "Do they are ready for the trip?",
            "Are they ready for the trip?",
            "Is they ready for the trip?",
            "Does they ready for the trip?",
        ],
        "answer": "Are they ready for the trip?",
        "explanation": "Con el verbo 'to be' (are), la pregunta se forma invirtiendo 'Are' antes del sujeto, sin usar 'do/does'.",
    },
    {
        "id": "ex_03",
        "level": "A1 - Básico",
        "topic": "Modales Básicos (can / should)",
        "type": "write",
        "question": "Traduce al inglés: 'Ella puede hablar inglés muy rápido.'",
        "answer": "She can speak English very fast.",
        "explanation": "Después del modal 'can', el verbo principal ('speak') va en forma base sin '-s'.",
    },
    {
        "id": "ex_04",
        "level": "A1 - Básico",
        "topic": "To Be & Presente Simple",
        "type": "choice",
        "question": "Completa la negación: 'My brother ___ like coffee.'",
        "options": [
            "don't",
            "doesn't",
            "isn't",
            "not",
        ],
        "answer": "doesn't",
        "explanation": "'My brother' equivale a 'He' (3ra persona singular); en presente simple se niega con 'doesn't + verbo base'.",
    },
    {
        "id": "ex_05",
        "level": "A1 - Básico",
        "topic": "Comprensión Auditiva (Listening)",
        "type": "listening",
        "audio_text": "We have a reservation for four nights.",
        "question": "Escucha el audio y elige lo que dice el locutor:",
        "options": [
            "We have a reservation for four nights.",
            "We had a reservation for five nights.",
            "We want a reservation for four days.",
            "They have a reservation for four nights.",
        ],
        "answer": "We have a reservation for four nights.",
        "explanation": "El audio dice exactamente: 'We have a reservation for four nights.'",
    },
    # A2
    {
        "id": "ex_06",
        "level": "A2 - Elemental",
        "topic": "Pasado Simple (did) y Futuro (will)",
        "type": "choice",
        "question": "Elige la pregunta correcta en pasado simple:",
        "options": [
            "Did he traveled to Orlando last month?",
            "Did he travel to Orlando last month?",
            "Does he traveled to Orlando last month?",
            "Was he travel to Orlando last month?",
        ],
        "answer": "Did he travel to Orlando last month?",
        "explanation": "Cuando aparece el auxiliar 'Did', el verbo principal regresa a su forma base ('travel', sin '-ed').",
    },
    {
        "id": "ex_07",
        "level": "A2 - Elemental",
        "topic": "Modales Básicos (can / should)",
        "type": "write",
        "question": "Escribe en inglés: 'Tú deberías comer comida saludable.'",
        "answer": "You should eat healthy food.",
        "explanation": "Para consejos o recomendaciones se usa 'should' seguido del verbo en forma base ('eat').",
    },
    {
        "id": "ex_08",
        "level": "A2 - Elemental",
        "topic": "Pasado Simple (did) y Futuro (will)",
        "type": "choice",
        "question": "Completa la oración en futuro: 'They ___ deploy the app tomorrow.'",
        "options": [
            "will",
            "wills",
            "are will",
            "did",
        ],
        "answer": "will",
        "explanation": "'Will' es invariable para todos los sujetos y va seguido del verbo en forma base.",
    },
    {
        "id": "ex_09",
        "level": "A2 - Elemental",
        "topic": "Have & Posesión",
        "type": "choice",
        "question": "¿Cómo se pregunta '¿Tiene ella tiempo hoy?' en inglés?",
        "options": [
            "Has she time today?",
            "Does she has time today?",
            "Does she have time today?",
            "Do she have time today?",
        ],
        "answer": "Does she have time today?",
        "explanation": "Con 'have' como verbo principal en presente simple, se usa 'Does' y el verbo vuelve a 'have'.",
    },
    {
        "id": "ex_10",
        "level": "A2 - Elemental",
        "topic": "Comprensión Auditiva (Listening)",
        "type": "listening",
        "audio_text": "Could you tell me where the boarding gate is?",
        "question": "Escucha el audio y selecciona la transcripción exacta:",
        "options": [
            "Can you tell me where the boarding pass is?",
            "Could you tell me where the boarding gate is?",
            "Could you show me where the exit gate is?",
            "Should you tell me when the boarding starts?",
        ],
        "answer": "Could you tell me where the boarding gate is?",
        "explanation": "La frase pregunta por la puerta de embarque ('boarding gate') usando el modal cortés 'Could you'.",
    },
    # B1 / B2
    {
        "id": "ex_11",
        "level": "B1/B2 - Intermedio",
        "topic": "Modales Avanzados (must / might / could)",
        "type": "choice",
        "question": "Selecciona la opción más natural: 'We ___ double-check the backup before migrating the server.'",
        "options": [
            "must to",
            "should",
            "shoulds",
            "musted",
        ],
        "answer": "should",
        "explanation": "Los verbos modales ('should', 'must') nunca llevan 'to' después ni conjugación en pasado o '-s'.",
    },
    {
        "id": "ex_12",
        "level": "B1/B2 - Intermedio",
        "topic": "Modales Avanzados (must / might / could)",
        "type": "write",
        "question": "Escribe en inglés: 'Nosotros no trabajamos en la oficina ayer.' (usa 'yesterday' al final)",
        "answer": "We did not work in the office yesterday.",
        "explanation": "Negación en pasado simple: 'did not' + verbo en forma base ('work').",
    },
    {
        "id": "ex_13",
        "level": "B1/B2 - Intermedio",
        "topic": "Comprensión Auditiva (Listening)",
        "type": "listening",
        "audio_text": "I have upgraded you to a suite on the eighth floor at no extra charge.",
        "question": "Escucha el audio del recepcionista y elige qué ofrece:",
        "options": [
            "A discount on breakfast on the first floor.",
            "An upgrade to a suite on the eighth floor at no extra charge.",
            "A different room on the second floor for an extra fee.",
            "Maintenance service for the air conditioning tonight.",
        ],
        "answer": "An upgrade to a suite on the eighth floor at no extra charge.",
        "explanation": "El audio indica: 'I have upgraded you to a suite on the eighth floor at no extra charge.'",
    },
    {
        "id": "ex_14",
        "level": "B1/B2 - Intermedio",
        "topic": "Estructuras Mixtas y Negociación",
        "type": "choice",
        "question": "Completa la frase profesional: 'Delivering everything by Friday ___ compromise quality.'",
        "options": [
            "might",
            "mights",
            "might to",
            "is might",
        ],
        "answer": "might",
        "explanation": "'Might' expresa posibilidad moderada y se conecta directamente con el verbo base 'compromise'.",
    },
    {
        "id": "ex_15",
        "level": "B1/B2 - Intermedio",
        "topic": "Estructuras Mixtas y Negociación",
        "type": "write",
        "question": "Escribe en inglés: '¿Pueden ellos verificar los permisos hoy?' (usa 'permissions' y 'today')",
        "answer": "Can they verify the permissions today?",
        "explanation": "Pregunta con modal 'Can': se coloca 'Can' al inicio seguido del sujeto 'they' y el verbo base 'verify'.",
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


def normalize_english_answer(text: str) -> str:
    norm = re.sub(r"[?.!,]", "", text.strip().lower())
    norm = re.sub(r"\s+", " ", norm)
    norm = (
        norm.replace("can't", "cannot")
        .replace("don't", "do not")
        .replace("doesn't", "does not")
        .replace("didn't", "did not")
        .replace("won't", "will not")
        .replace("isn't", "is not")
        .replace("aren't", "are not")
        .replace("shouldn't", "should not")
        .replace("couldn't", "could not")
    )
    return norm


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
stats = load_stats()
shadowing_map = load_shadowing_progress()
saved_sentences = load_sentence_history()
exam_history = load_exam_results()

with st.sidebar:
    st.title("🧩 English Matrix")
    st.caption("Constructor Gramatical, Shadowing & Exámenes")
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
    st.subheader("🗄️ Progreso Guardado (SQLite)")
    col_s1, col_s2 = st.columns(2)
    col_s1.metric("Aciertos", stats["score"])
    completed_lessons_count = len([k for k in shadowing_map if k.startswith("sh_")])
    col_s2.metric("Shadowing", f"{completed_lessons_count}/{len(SHADOWING_LESSONS)}")

    col_s3, col_s4 = st.columns(2)
    col_s3.metric("Exámenes", len(exam_history))
    passed_exams = len([e for e in exam_history if e["passed"] == 1])
    col_s4.metric("Aprobados", passed_exams)

    if stats["attempts"] > 0:
        acc = int((stats["score"] / stats["attempts"]) * 100)
        st.progress(acc / 100, text=f"Precisión Práctica: {acc}%")

    if st.button("🗑️ Reiniciar base de datos", use_container_width=True):
        reset_all_db()
        st.session_state.active_exam = None
        st.session_state.last_exam_report = None
        st.toast("Base de datos SQLite reiniciada.")
        st.rerun()

st.title("🧩 Matriz Gramatical, Shadowing y Evaluación")
st.markdown(
    "Construye oraciones combinando bloques gramaticales, entrénalas en el **Estudio de Shadowing (A1–B2)**, "
    "presenta **Exámenes Calificados** y conserva todo tu historial en **SQLite**."
)

tab_matrix, tab_shadowing, tab_exams, tab_practice, tab_progress_db, tab_reference = st.tabs(
    [
        "🎛️ Matriz Interactiva",
        "🎧 Estudio de Shadowing (A1–B2)",
        "📝 Exámenes Calificados",
        "🎯 Práctica Rápida",
        "🗄️ Historial y Progreso SQL",
        "📘 Guía de Estructuras",
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
        st.markdown("<div style='height: 36px;'></div>", unsafe_allow_html=True)
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
        if st.button("💾 Guardar oración en SQLite", use_container_width=True):
            inserted = save_sentence_db(
                result["affirmative"],
                result["negative"],
                result["interrogative"],
                result["spanish"],
                struct_val,
            )
            if inserted:
                st.toast("✅ Oración guardada en la base de datos SQLite.")
                st.rerun()
            else:
                st.toast("ℹ️ Esta oración ya estaba guardada en tu base de datos.")

    with c_gram:
        st.markdown("#### 🧠 Análisis y Reglas Gramaticales")
        for note in result["notes"]:
            st.markdown(f"- {note}")

# ------------------------------------------------------------------------------
# TAB 2: ESTUDIO DE SHADOWING (BANCO DE 8 LECCIONES A1-B2)
# ------------------------------------------------------------------------------
with tab_shadowing:
    st.subheader("🎧 Estudio de Shadowing (Imitación Activa y Ritmo)")
    st.markdown(
        """
        **Metodología de entrenamiento en 4 pasos:**
        1. **Escucha ciega:** Activa *Ocultar texto en inglés* y escucha el diálogo captando entonación y velocidad.
        2. **Lectura rítmica:** Activa los *Chunks* para ver los **golpes de voz en negrita** y pausas `/`.
        3. **Bucle con pausas (Listen & Repeat):** Usa la pista maestra que deja silencio después de cada turno para repetir en voz alta.
        4. **Shadowing simultáneo + Grabación:** Imita al hablante en tiempo real y graba tu voz para compararla.
        """
    )

    st.divider()

    source_mode = st.radio(
        "Selecciona el material de entrenamiento:",
        options=[
            "📚 Lecciones del Curso (8 Diálogos A1–B2)",
            "🧩 Oraciones creadas en la Matriz",
            "✍️ Texto personalizado / Subir audio propio",
        ],
        horizontal=True,
    )

    ctrl1, ctrl2, ctrl3 = st.columns(3)
    with ctrl1:
        blind_mode = st.toggle("🙈 Modo Escucha Ciega (Ocultar inglés)", value=False)
    with ctrl2:
        show_chunks = st.toggle("🎵 Mostrar ritmo y acentos (Chunks)", value=True)
    with ctrl3:
        show_es_sub = st.toggle("🇪🇸 Mostrar traducción al español", value=True)

    active_sentences = []
    lesson_id = "custom"
    lesson_title_for_db = "Práctica Personalizada"

    if source_mode == "📚 Lecciones del Curso (8 Diálogos A1–B2)":
        f_col1, f_col2, f_col3 = st.columns([1, 1, 2])
        with f_col1:
            level_filter = st.selectbox(
                "Filtrar por Nivel MCER:",
                options=["Todos", "A1 - Principiante", "A2 - Elemental", "B1 - Intermedio", "B2 - Intermedio Alto"],
            )
        with f_col2:
            cat_filter = st.selectbox(
                "Filtrar por Situación:",
                options=["Todas", "Diálogos Cotidianos", "Restaurantes", "Hoteles", "Trabajo"],
            )

        filtered_lessons = [
            l for l in SHADOWING_LESSONS
            if (level_filter == "Todos" or l["level"] == level_filter)
            and (cat_filter == "Todas" or l["category"] == cat_filter)
        ]

        if not filtered_lessons:
            st.warning("No hay lecciones que coincidan con esa combinación exacta de nivel y situación.")
        else:
            with f_col3:
                lesson_titles = [
                    f"{'✅ ' if l['id'] in shadowing_map else ''}{l['title']} [{l['category']}]"
                    for l in filtered_lessons
                ]
                sel_idx = st.selectbox("Selecciona el diálogo:", options=range(len(filtered_lessons)), format_func=lambda i: lesson_titles[i])
                lesson = filtered_lessons[sel_idx]

            lesson_id = lesson["id"]
            lesson_title_for_db = lesson["title"]
            prev_info = shadowing_map.get(lesson_id)
            badge_db = f" | ✅ Completada {prev_info['completed_count']} vez/veces" if prev_info else " | ⏳ Pendiente"
            st.info(f"**Nivel:** {lesson['level']}  |  **Situación:** {lesson['category']}{badge_db}")

            active_sentences = [s["en"] for s in lesson["sentences"]]

            st.markdown("### 🔁 Pista Maestra de Entrenamiento (Diálogo completo o con pausas)")
            col_loop1, col_loop2, col_loop3 = st.columns([1, 1.3, 1.3])
            with col_loop1:
                reps = st.selectbox("Repeticiones por turno:", options=[1, 2, 3], index=1)
            with col_loop2:
                if st.button("▶️ Escuchar Diálogo Fluido (Sin pausas)", use_container_width=True):
                    fluid_audio = synthesize_speech(" ".join(active_sentences), is_slow, selected_tld)
                    st.audio(fluid_audio, format="audio/mp3", autoplay=True)
            with col_loop3:
                if st.button("🔁 Pista Shadowing (Con pausas para repetir)", type="primary", use_container_width=True):
                    loop_audio = synthesize_shadowing_loop(tuple(active_sentences), is_slow, selected_tld, reps)
                    st.audio(loop_audio, format="audio/mp3", autoplay=True)

            st.markdown("### 📝 Desglose del Diálogo Turno por Turno")
            for idx, item in enumerate(lesson["sentences"], 1):
                with st.container(border=True):
                    c_txt, c_aud = st.columns([2.3, 1])
                    with c_txt:
                        speaker_badge = item.get("speaker", f"Turno {idx}")
                        st.markdown(f"**Turno {idx} — 👤 {speaker_badge}**")
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
                        if st.button(f"🔊 Escuchar Turno {idx}", key=f"sh_btn_{lesson_id}_{idx}", use_container_width=True):
                            s_audio = synthesize_speech(item["en"], is_slow, selected_tld)
                            st.audio(s_audio, format="audio/mp3", autoplay=True)

    elif source_mode == "🧩 Oraciones creadas en la Matriz":
        lesson_id = "matrix_live"
        lesson_title_for_db = f"Matriz: {result['affirmative']}"
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
                c_t, c_a = st.columns([2.3, 1])
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

    else:
        lesson_id = "custom_text"
        lesson_title_for_db = "Texto Libre / Audio Externo"
        custom_paragraph = st.text_area(
            "Pega aquí un diálogo, párrafo o lista de frases en inglés (una por línea):",
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

    st.divider()
    st.markdown("### 🎙️ Cabina de Grabación y Autoevaluación")
    st.caption("Graba tu voz imitando la entonación y velocidad del audio nativo, y luego escúchate para detectar diferencias.")

    rec_col1, rec_col2 = st.columns([1.5, 1])
    with rec_col1:
        user_recording = st.audio_input("Haz clic en el micrófono para grabar tu práctica de Shadowing:")
        if user_recording is not None:
            st.success("✅ Grabación lista. Reprodúcela arriba y compárala con el modelo nativo.")

    with rec_col2:
        st.markdown("**Registro persistente en SQLite**")
        if st.button("🏅 Guardar sesión completada en BD", use_container_width=True):
            mark_shadowing_db(lesson_id, lesson_title_for_db)
            st.toast("✅ Progreso de Shadowing guardado en SQLite.")
            st.rerun()

# ------------------------------------------------------------------------------
# TAB 3: EXÁMENES CALIFICADOS (CON GUARDADO EN SQLITE)
# ------------------------------------------------------------------------------
with tab_exams:
    st.subheader("📝 Exámenes de Evaluación (Gramática, Traducción y Listening)")
    st.write("Configura un examen por nivel o tema, respóndelo completo y guarda tu nota y revisión detallada en la base de datos SQLite.")

    cfg_col1, cfg_col2, cfg_col3, cfg_col4 = st.columns([1.2, 1.3, 1, 1.2])
    with cfg_col1:
        exam_level_sel = st.selectbox(
            "Nivel del Examen:",
            options=["Todos los niveles", "A1 - Básico", "A2 - Elemental", "B1/B2 - Intermedio"],
        )
    with cfg_col2:
        all_topics = ["Todos los temas"] + sorted(list({q["topic"] for q in EXAM_BANK}))
        exam_topic_sel = st.selectbox("Enfoque temático:", options=all_topics)
    with cfg_col3:
        num_questions = st.selectbox("N.º de preguntas:", options=[5, 8, 10], index=0)
    with cfg_col4:
        st.markdown("<br>", unsafe_allow_html=True)
        if st.button("🚀 Iniciar Nuevo Examen", type="primary", use_container_width=True):
            pool = [
                q for q in EXAM_BANK
                if (exam_level_sel == "Todos los niveles" or q["level"] == exam_level_sel)
                and (exam_topic_sel == "Todos los temas" or q["topic"] == exam_topic_sel)
            ]
            if not pool:
                st.warning("No hay preguntas con esa combinación exacta. Se tomarán preguntas de todos los temas del nivel.")
                pool = [q for q in EXAM_BANK if exam_level_sel == "Todos los niveles" or q["level"] == exam_level_sel]
            chosen = random.sample(pool, min(num_questions, len(pool)))
            st.session_state.active_exam = {
                "level": exam_level_sel,
                "topic": exam_topic_sel,
                "questions": chosen,
            }
            st.session_state.last_exam_report = None
            st.rerun()

    st.divider()

    # Renderizar examen activo
    if st.session_state.active_exam is not None:
        ex = st.session_state.active_exam
        st.info(f"**Examen en curso** — Nivel: `{ex['level']}` | Tema: `{ex['topic']}` | Preguntas: **{len(ex['questions'])}** *(Nota mínima aprobatoria: 70%)*")

        # Botones de audio para preguntas de Listening (fuera del form)
        for idx, q in enumerate(ex["questions"], 1):
            if q["type"] == "listening":
                c_l_btn, c_l_aud = st.columns([1.2, 2.5])
                with c_l_btn:
                    if st.button(f"🔊 Escuchar Audio Pregunta {idx}", key=f"ex_listen_btn_{q['id']}_{idx}", use_container_width=True):
                        st.session_state[f"play_ex_{idx}"] = True
                with c_l_aud:
                    if st.session_state.get(f"play_ex_{idx}"):
                        st.audio(synthesize_speech(q["audio_text"], is_slow, selected_tld), format="audio/mp3", autoplay=True)

        with st.form("exam_submission_form"):
            user_responses = {}
            for idx, q in enumerate(ex["questions"], 1):
                st.markdown(f"#### Pregunta {idx} de {len(ex['questions'])}  `[{q['level']} • {q['topic']}]`")
                st.write(q["question"])

                if q["type"] in ("choice", "listening"):
                    user_responses[idx] = st.radio(
                        f"Selecciona tu respuesta para la pregunta {idx}:",
                        options=q["options"],
                        index=None,
                        key=f"ex_ans_{q['id']}_{idx}",
                    )
                else:
                    user_responses[idx] = st.text_input(
                        f"Escribe la oración en inglés (Pregunta {idx}):",
                        key=f"ex_ans_{q['id']}_{idx}",
                        placeholder="Escribe aquí tu respuesta completa...",
                    )
                st.markdown("---")

            submitted_exam = st.form_submit_button("✅ Finalizar Examen, Calificar y Guardar en SQLite", type="primary", use_container_width=True)

            if submitted_exam:
                correct_count = 0
                details_list = []
                total_q = len(ex["questions"])

                for idx, q in enumerate(ex["questions"], 1):
                    raw_u = user_responses.get(idx)
                    u_str = raw_u.strip() if isinstance(raw_u, str) else ""

                    if q["type"] in ("choice", "listening"):
                        is_ok = (u_str == q["answer"])
                    else:
                        is_ok = (normalize_english_answer(u_str) == normalize_english_answer(q["answer"])) and bool(u_str)

                    if is_ok:
                        correct_count += 1

                    details_list.append(
                        {
                            "num": idx,
                            "level": q["level"],
                            "topic": q["topic"],
                            "question": q["question"],
                            "user_answer": u_str if u_str else "(Sin responder)",
                            "correct_answer": q["answer"],
                            "is_correct": is_ok,
                            "explanation": q["explanation"],
                        }
                    )

                exam_id = save_exam_result_db(ex["level"], ex["topic"], total_q, correct_count, details_list)
                update_stats(correct_count, total_q)

                pct = round((correct_count / total_q) * 100, 1)
                st.session_state.last_exam_report = {
                    "id": exam_id,
                    "level": ex["level"],
                    "topic": ex["topic"],
                    "total": total_q,
                    "correct": correct_count,
                    "percentage": pct,
                    "passed": pct >= 70.0,
                    "details": details_list,
                }
                st.session_state.active_exam = None
                st.rerun()

    # Mostrar reporte recién calificado
    if st.session_state.last_exam_report is not None:
        rep = st.session_state.last_exam_report
        st.markdown("### 🏆 Resultado del Examen Guardado en SQLite")

        r1, r2, r3, r4 = st.columns(4)
        r1.metric("Examen ID", f"#{rep['id']}")
        r2.metric("Calificación", f"{rep['percentage']}%")
        r3.metric("Respuestas Correctas", f"{rep['correct']} / {rep['total']}")
        r4.metric("Estado", "APROBADO ✅" if rep["passed"] else "REPASAR ⚠️")

        if rep["passed"]:
            st.success(f"¡Felicitaciones! Aprobaste el examen con **{rep['percentage']}%** y el resultado ya quedó registrado en SQLite.")
        else:
            st.warning(f"Obtuviste **{rep['percentage']}%** (se requiere 70% para aprobar). Revisa las explicaciones abajo y vuelve a intentarlo.")

        for d in rep["details"]:
            with st.container(border=True):
                badge = "✅ Correcta" if d["is_correct"] else "❌ Incorrecta"
                st.markdown(f"**{badge} — Pregunta {d['num']}:** {d['question']}")
                st.markdown(f"- **Tu respuesta:** `{d['user_answer']}`")
                if not d["is_correct"]:
                    st.markdown(f"- **Respuesta correcta:** `{d['correct_answer']}`")
                st.caption(f"💡 **Explicación:** {d['explanation']}")

    # Historial rápido de exámenes guardados dentro de la misma pestaña
    st.divider()
    st.markdown("### 📊 Historial de Exámenes Presentados (Guardados en SQLite)")
    latest_exams = load_exam_results()
    if not latest_exams:
        st.info("Aún no has presentado ningún examen. Haz clic en **🚀 Iniciar Nuevo Examen** arriba.")
    else:
        for ex_row in latest_exams:
            status_txt = "✅ APROBADO" if ex_row["passed"] == 1 else "❌ NO APROBADO"
            header = (
                f"Examen #{ex_row['id']}  |  {ex_row['taken_at']}  |  "
                f"Nivel: {ex_row['exam_level']} ({ex_row['exam_topic']})  |  "
                f"Nota: {ex_row['percentage']}% ({ex_row['correct_answers']}/{ex_row['total_questions']}) — {status_txt}"
            )
            with st.expander(header):
                parsed_details = json.loads(ex_row["details_json"])
                for item in parsed_details:
                    ic = "✅" if item["is_correct"] else "❌"
                    st.markdown(
                        f"{ic} **P{item['num']}:** {item['question']}  \n"
                        f"Tu respuesta: `{item['user_answer']}` | Correcta: `{item['correct_answer']}`  \n"
                        f"*{item['explanation']}*"
                    )
                if st.button(f"🗑️ Eliminar registro del Examen #{ex_row['id']}", key=f"del_ex_{ex_row['id']}"):
                    delete_exam_result_db(ex_row["id"])
                    st.rerun()

# ------------------------------------------------------------------------------
# TAB 4: PRÁCTICA RÁPIDA (EJERCICIOS GUIADOS)
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
            is_ok = normalize_english_answer(user_ans) == normalize_english_answer(ch["en"])
            update_stats(1 if is_ok else 0, 1)
            log_exercise_attempt(ch["es"], ch["en"], user_ans.strip(), is_ok)

            if is_ok:
                st.success(f"🎉 ¡Excelente! Respuesta correcta guardada en SQLite: **{ch['en']}**")
                audio_ok = synthesize_speech(ch["en"], is_slow, selected_tld)
                st.audio(audio_ok, format="audio/mp3")
            else:
                st.error(f"❌ No coincide exactamente.\n\n- **Tu respuesta:** `{user_ans}`\n- **Forma esperada:** `{ch['en']}`\n- **Regla clave:** {ch['hint']}")

# ------------------------------------------------------------------------------
# TAB 5: HISTORIAL Y PROGRESO SQL
# ------------------------------------------------------------------------------
with tab_progress_db:
    st.subheader("🗄️ Panel General de Progreso Persistente (SQLite)")
    st.caption(f"Archivo de base de datos local: `{DB_PATH}`")

    avg_exam = (
        round(sum(e["percentage"] for e in exam_history) / len(exam_history), 1)
        if exam_history
        else 0.0
    )

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Exámenes Realizados", len(exam_history), delta=f"Promedio: {avg_exam}%")
    m2.metric("Lecciones Shadowing", f"{completed_lessons_count} / {len(SHADOWING_LESSONS)}")
    m3.metric("Oraciones Guardadas", len(saved_sentences))
    m4.metric("Aciertos Totales", f"{stats['score']} / {stats['attempts']}")

    st.divider()
    st.markdown("### 📝 Resumen de Exámenes Guardados")
    if not exam_history:
        st.info("No hay exámenes guardados aún. Ve a la pestaña **📝 Exámenes Calificados** para presentar uno.")
    else:
        for e in exam_history:
            badge_e = "✅ APROBADO" if e["passed"] == 1 else "⚠️ REPASAR"
            st.write(
                f"**Examen #{e['id']}** (`{e['taken_at']}`) — **{e['exam_level']}** | Tema: *{e['exam_topic']}* | "
                f"Puntaje: **{e['correct_answers']}/{e['total_questions']} ({e['percentage']}%)** — {badge_e}"
            )

    st.divider()
    st.markdown("### 📜 Oraciones Guardadas desde la Matriz")
    if not saved_sentences:
        st.info("Aún no has guardado oraciones. Usa el botón **💾 Guardar oración en SQLite** en la primera pestaña.")
    else:
        for row in saved_sentences:
            with st.container(border=True):
                c_r1, c_r2 = st.columns([4, 1])
                with c_r1:
                    st.markdown(f"**➕** `{row['affirmative']}`  |  **➖** `{row['negative']}`  |  **❓** `{row['interrogative']}`")
                    st.caption(f"🇪🇸 {row['spanish']}  •  Estructura: {row['structure']}  •  Guardado: {row['created_at']}")
                with c_r2:
                    if st.button("🔊 Escuchar", key=f"db_play_{row['id']}", use_container_width=True):
                        st.audio(synthesize_speech(row["affirmative"], is_slow, selected_tld), format="audio/mp3", autoplay=True)
                    if st.button("🗑️ Eliminar", key=f"db_del_{row['id']}", use_container_width=True):
                        delete_sentence_db(row["id"])
                        st.rerun()

    st.divider()
    st.markdown("### 🎧 Estado de Lecciones de Shadowing")
    for l in SHADOWING_LESSONS:
        info = shadowing_map.get(l["id"])
        if info:
            st.success(f"✅ **{l['title']}** — Completada **{info['completed_count']}** vez/veces (Última práctica: `{info['last_completed_at']}`)")
        else:
            st.write(f"⬜ {l['title']} — *Pendiente*")

    st.divider()
    st.markdown("### 🎯 Últimos Intentos en Práctica Rápida")
    logs = load_exercise_logs(15)
    if not logs:
        st.info("Todavía no hay intentos registrados en práctica rápida.")
    else:
        for lg in logs:
            icon = "✅" if lg["is_correct"] else "❌"
            st.markdown(f"{icon} **{lg['prompt_es']}** → Tu respuesta: `{lg['user_answer']}` *(Esperada: `{lg['target_en']}` — {lg['attempted_at']})*")

# ------------------------------------------------------------------------------
# TAB 6: GUÍA RÁPIDA DE ESTRUCTURAS
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