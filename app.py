import io
import re
import json
import sqlite3
import random
import unicodedata
import urllib.request
import urllib.parse
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
    initial_sidebar_state="collapsed",
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
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS vocab_mastered (
                word_en TEXT PRIMARY KEY,
                word_es TEXT NOT NULL,
                category TEXT NOT NULL,
                mastered_at TEXT NOT NULL
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


def mark_vocab_mastered_db(word_en: str, word_es: str, category: str):
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with get_connection() as conn:
        conn.execute(
            """
            INSERT OR REPLACE INTO vocab_mastered (word_en, word_es, category, mastered_at)
            VALUES (?, ?, ?, ?)
            """,
            (word_en, word_es, category, now_str),
        )
        conn.commit()


def unmark_vocab_mastered_db(word_en: str):
    with get_connection() as conn:
        conn.execute("DELETE FROM vocab_mastered WHERE word_en = ?", (word_en,))
        conn.commit()


def load_vocab_mastered() -> dict:
    with get_connection() as conn:
        rows = conn.execute("SELECT word_en, word_es, category, mastered_at FROM vocab_mastered ORDER BY mastered_at DESC").fetchall()
        return {r["word_en"]: dict(r) for r in rows}


def reset_all_db():
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with get_connection() as conn:
        conn.execute("UPDATE user_stats SET score = 0, attempts = 0, updated_at = ? WHERE id = 1", (now_str,))
        conn.execute("DELETE FROM sentence_history")
        conn.execute("DELETE FROM shadowing_progress")
        conn.execute("DELETE FROM exercise_logs")
        conn.execute("DELETE FROM exam_results")
        conn.execute("DELETE FROM vocab_mastered")
        conn.commit()


init_db()

# ==============================================================================
# ESTILOS RESPONSIVOS PARA MÓVIL Y ESCRITORIO
# ==============================================================================
st.markdown(
    """
    <style>
    /* Ocultar íconos de enlace de anclaje (cadena) en todos los títulos y encabezados */
    [data-testid="stHeaderActionElements"],
    .stMarkdown a.anchor-link,
    h1 a, h2 a, h3 a, h4 a, h5 a, h6 a {
        display: none !important;
        visibility: hidden !important;
    }

    /* Mejoras táctiles generales */
    .stButton > button {
        min-height: 44px;
        border-radius: 8px;
        font-weight: 500;
    }

    /* Pestañas desplazables horizontalmente sin apilarse mal */
    .stTabs [data-baseweb="tab-list"] {
        gap: 6px;
        overflow-x: auto;
        flex-wrap: nowrap;
        scrollbar-width: none;
        -ms-overflow-style: none;
        padding-bottom: 4px;
    }
    .stTabs [data-baseweb="tab-list"]::-webkit-scrollbar {
        display: none;
    }
    .stTabs [data-baseweb="tab"] {
        white-space: nowrap;
        padding: 8px 12px;
        font-size: 0.92rem;
    }

    /* Ajustes específicos para pantallas de celular (<= 768px) */
    @media (max-width: 768px) {
        .block-container {
            padding-top: 2.2rem !important;
            padding-left: 0.85rem !important;
            padding-right: 0.85rem !important;
            padding-bottom: 2rem !important;
        }
        h1 {
            font-size: 1.55rem !important;
            line-height: 1.25 !important;
        }
        h2 {
            font-size: 1.25rem !important;
        }
        h3 {
            font-size: 1.12rem !important;
            word-break: break-word;
        }
        /* Oculta el espaciador vertical de escritorio cuando las columnas se apilan en móvil */
        .desktop-spacer {
            display: none !important;
        }
        /* Botones más grandes y cómodos para el pulgar */
        .stButton > button {
            min-height: 48px !important;
            font-size: 0.98rem !important;
        }
        /* Compactar métricas en pantalla estrecha */
        [data-testid="stMetricValue"] {
            font-size: 1.35rem !important;
        }
    }
    </style>
    """,
    unsafe_allow_html=True,
)

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
    "You": {"person": "2s", "plural": True, "es": "Tú", "be_pres": "are", "be_past": "were", "have": "have"},
    "He": {"person": "3s", "plural": False, "es": "Él", "be_pres": "is", "be_past": "was", "have": "has"},
    "She": {"person": "3s", "plural": False, "es": "Ella", "be_pres": "is", "be_past": "was", "have": "has"},
    "It": {"person": "3s", "plural": False, "es": "Eso", "be_pres": "is", "be_past": "was", "have": "has"},
    "We": {"person": "1p", "plural": True, "es": "Nosotros", "be_pres": "are", "be_past": "were", "have": "have"},
    "They": {"person": "3p", "plural": True, "es": "Ellos", "be_pres": "are", "be_past": "were", "have": "have"},
}

VERBS_DB = {
    "work": {
        "3s": "works", "past": "worked", "ing": "working", "es_inf": "trabajar",
        "es_pres_map": {"1s": "trabajo", "2s": "trabajas", "3s": "trabaja", "1p": "trabajamos", "3p": "trabajan"},
        "es_past_map": {"1s": "trabajé", "2s": "trabajaste", "3s": "trabajó", "1p": "trabajamos", "3p": "trabajaron"},
        "es_fut_map": {"1s": "trabajaré", "2s": "trabajarás", "3s": "trabajará", "1p": "trabajaremos", "3p": "trabajarán"},
        "es_cond_map": {"1s": "trabajaría", "2s": "trabajarías", "3s": "trabajaría", "1p": "trabajaríamos", "3p": "trabajarían"},
    },
    "study": {
        "3s": "studies", "past": "studied", "ing": "studying", "es_inf": "estudiar",
        "es_pres_map": {"1s": "estudio", "2s": "estudias", "3s": "estudia", "1p": "estudiamos", "3p": "estudian"},
        "es_past_map": {"1s": "estudié", "2s": "estudiaste", "3s": "estudió", "1p": "estudiamos", "3p": "estudiaron"},
        "es_fut_map": {"1s": "estudiaré", "2s": "estudiarás", "3s": "estudiará", "1p": "estudiaremos", "3p": "estudiarán"},
        "es_cond_map": {"1s": "estudiaría", "2s": "estudiarías", "3s": "estudiaría", "1p": "estudiaríamos", "3p": "estudiarían"},
    },
    "speak": {
        "3s": "speaks", "past": "spoke", "ing": "speaking", "es_inf": "hablar",
        "es_pres_map": {"1s": "hablo", "2s": "hablas", "3s": "habla", "1p": "hablamos", "3p": "hablan"},
        "es_past_map": {"1s": "hablé", "2s": "hablaste", "3s": "habló", "1p": "hablamos", "3p": "hablaron"},
        "es_fut_map": {"1s": "hablaré", "2s": "hablarás", "3s": "hablará", "1p": "hablaremos", "3p": "hablarán"},
        "es_cond_map": {"1s": "hablaría", "2s": "hablarías", "3s": "hablaría", "1p": "hablaríamos", "3p": "hablarían"},
    },
    "travel": {
        "3s": "travels", "past": "traveled", "ing": "traveling", "es_inf": "viajar",
        "es_pres_map": {"1s": "viajo", "2s": "viajas", "3s": "viaja", "1p": "viajamos", "3p": "viajan"},
        "es_past_map": {"1s": "viajé", "2s": "viajaste", "3s": "viajó", "1p": "viajamos", "3p": "viajaron"},
        "es_fut_map": {"1s": "viajaré", "2s": "viajarás", "3s": "viajará", "1p": "viajaremos", "3p": "viajarán"},
        "es_cond_map": {"1s": "viajaría", "2s": "viajarías", "3s": "viajaría", "1p": "viajaríamos", "3p": "viajarían"},
    },
    "go": {
        "3s": "goes", "past": "went", "ing": "going", "es_inf": "ir",
        "es_pres_map": {"1s": "voy", "2s": "vas", "3s": "va", "1p": "vamos", "3p": "van"},
        "es_past_map": {"1s": "fui", "2s": "fuiste", "3s": "fue", "1p": "fuimos", "3p": "fueron"},
        "es_fut_map": {"1s": "iré", "2s": "irás", "3s": "irá", "1p": "iremos", "3p": "irán"},
        "es_cond_map": {"1s": "iría", "2s": "irías", "3s": "iría", "1p": "iríamos", "3p": "irían"},
    },
    "eat": {
        "3s": "eats", "past": "ate", "ing": "eating", "es_inf": "comer",
        "es_pres_map": {"1s": "como", "2s": "comes", "3s": "come", "1p": "comemos", "3p": "comen"},
        "es_past_map": {"1s": "comí", "2s": "comiste", "3s": "comió", "1p": "comimos", "3p": "comieron"},
        "es_fut_map": {"1s": "comeré", "2s": "comerás", "3s": "comerá", "1p": "comeremos", "3p": "comerán"},
        "es_cond_map": {"1s": "comería", "2s": "comerías", "3s": "comería", "1p": "comeríamos", "3p": "comerían"},
    },
    "read": {
        "3s": "reads", "past": "read", "ing": "reading", "es_inf": "leer",
        "es_pres_map": {"1s": "leo", "2s": "lees", "3s": "lee", "1p": "leemos", "3p": "leen"},
        "es_past_map": {"1s": "leí", "2s": "leíste", "3s": "leyó", "1p": "leímos", "3p": "leyeron"},
        "es_fut_map": {"1s": "leeré", "2s": "leerás", "3s": "leerá", "1p": "leeremos", "3p": "leerán"},
        "es_cond_map": {"1s": "leería", "2s": "leerías", "3s": "leería", "1p": "leeríamos", "3p": "leerían"},
    },
    "write": {
        "3s": "writes", "past": "wrote", "ing": "writing", "es_inf": "escribir",
        "es_pres_map": {"1s": "escribo", "2s": "escribes", "3s": "escribe", "1p": "escribimos", "3p": "escriben"},
        "es_past_map": {"1s": "escribí", "2s": "escribiste", "3s": "escribió", "1p": "escribimos", "3p": "escribieron"},
        "es_fut_map": {"1s": "escribiré", "2s": "escribirás", "3s": "escribirá", "1p": "escribiremos", "3p": "escribirán"},
        "es_cond_map": {"1s": "escribiría", "2s": "escribirías", "3s": "escribiría", "1p": "escribiríamos", "3p": "escribirían"},
    },
    "learn": {
        "3s": "learns", "past": "learned", "ing": "learning", "es_inf": "aprender",
        "es_pres_map": {"1s": "aprendo", "2s": "aprendes", "3s": "aprende", "1p": "aprendemos", "3p": "aprenden"},
        "es_past_map": {"1s": "aprendí", "2s": "aprendiste", "3s": "aprendió", "1p": "aprendimos", "3p": "aprendieron"},
        "es_fut_map": {"1s": "aprenderé", "2s": "aprenderás", "3s": "aprenderá", "1p": "aprenderemos", "3p": "aprenderán"},
        "es_cond_map": {"1s": "aprendería", "2s": "aprenderías", "3s": "aprendería", "1p": "aprenderíamos", "3p": "aprenderían"},
    },
    "play": {
        "3s": "plays", "past": "played", "ing": "playing", "es_inf": "jugar",
        "es_pres_map": {"1s": "juego", "2s": "juegas", "3s": "juega", "1p": "jugamos", "3p": "juegan"},
        "es_past_map": {"1s": "jugué", "2s": "jugaste", "3s": "jugó", "1p": "jugamos", "3p": "jugaron"},
        "es_fut_map": {"1s": "jugaré", "2s": "jugarás", "3s": "jugará", "1p": "jugaremos", "3p": "jugarán"},
        "es_cond_map": {"1s": "jugaría", "2s": "jugarías", "3s": "jugaría", "1p": "jugaríamos", "3p": "jugarían"},
    },
    "buy": {
        "3s": "buys", "past": "bought", "ing": "buying", "es_inf": "comprar",
        "es_pres_map": {"1s": "compro", "2s": "compras", "3s": "compra", "1p": "compramos", "3p": "compran"},
        "es_past_map": {"1s": "compré", "2s": "compraste", "3s": "compró", "1p": "compramos", "3p": "compraron"},
        "es_fut_map": {"1s": "compraré", "2s": "comprarás", "3s": "comprará", "1p": "compraremos", "3p": "comprarán"},
        "es_cond_map": {"1s": "compraría", "2s": "comprarías", "3s": "compraría", "1p": "compraríamos", "3p": "comprarían"},
    },
    "visit": {
        "3s": "visits", "past": "visited", "ing": "visiting", "es_inf": "visitar",
        "es_pres_map": {"1s": "visito", "2s": "visitas", "3s": "visita", "1p": "visitamos", "3p": "visitan"},
        "es_past_map": {"1s": "visité", "2s": "visitaste", "3s": "visitó", "1p": "visitamos", "3p": "visitaron"},
        "es_fut_map": {"1s": "visitaré", "2s": "visitarás", "3s": "visitará", "1p": "visitaremos", "3p": "visitarán"},
        "es_cond_map": {"1s": "visitaría", "2s": "visitarías", "3s": "visitaría", "1p": "visitaríamos", "3p": "visitarían"},
    },
    "cook": {
        "3s": "cooks", "past": "cooked", "ing": "cooking", "es_inf": "cocinar",
        "es_pres_map": {"1s": "cocino", "2s": "cocinas", "3s": "cocina", "1p": "cocinamos", "3p": "cocinan"},
        "es_past_map": {"1s": "cociné", "2s": "cocinaste", "3s": "cocinó", "1p": "cocinamos", "3p": "cocinaron"},
        "es_fut_map": {"1s": "cocinaré", "2s": "cocinarás", "3s": "cocinará", "1p": "cocinaremos", "3p": "cocinarán"},
        "es_cond_map": {"1s": "cocinaría", "2s": "cocinarías", "3s": "cocinaría", "1p": "cocinaríamos", "3p": "cocinarían"},
    },
    "drive": {
        "3s": "drives", "past": "drove", "ing": "driving", "es_inf": "conducir",
        "es_pres_map": {"1s": "conduzco", "2s": "conduces", "3s": "conduce", "1p": "conducimos", "3p": "conducen"},
        "es_past_map": {"1s": "conduje", "2s": "condujiste", "3s": "condujo", "1p": "condujimos", "3p": "condujeron"},
        "es_fut_map": {"1s": "conduciré", "2s": "conducirás", "3s": "conducirá", "1p": "conduciremos", "3p": "conducirán"},
        "es_cond_map": {"1s": "conduciría", "2s": "conducirías", "3s": "conduciría", "1p": "conduciríamos", "3p": "conducirían"},
    },
    "live": {
        "3s": "lives", "past": "lived", "ing": "living", "es_inf": "vivir",
        "es_pres_map": {"1s": "vivo", "2s": "vives", "3s": "vive", "1p": "vivimos", "3p": "viven"},
        "es_past_map": {"1s": "viví", "2s": "viviste", "3s": "vivió", "1p": "vivimos", "3p": "vivieron"},
        "es_fut_map": {"1s": "viviré", "2s": "vivirás", "3s": "vivirá", "1p": "viviremos", "3p": "vivirán"},
        "es_cond_map": {"1s": "viviría", "2s": "vivirías", "3s": "viviría", "1p": "viviríamos", "3p": "vivirían"},
    },
    "make": {
        "3s": "makes", "past": "made", "ing": "making", "es_inf": "hacer",
        "es_pres_map": {"1s": "hago", "2s": "haces", "3s": "hace", "1p": "hacemos", "3p": "hacen"},
        "es_past_map": {"1s": "hice", "2s": "hiciste", "3s": "hizo", "1p": "hicimos", "3p": "hicieron"},
        "es_fut_map": {"1s": "haré", "2s": "harás", "3s": "hará", "1p": "haremos", "3p": "harán"},
        "es_cond_map": {"1s": "haría", "2s": "harías", "3s": "haría", "1p": "haríamos", "3p": "harían"},
    },
    "do": {
        "3s": "does", "past": "did", "ing": "doing", "es_inf": "hacer / realizar",
        "es_pres_map": {"1s": "hago", "2s": "haces", "3s": "hace", "1p": "hacemos", "3p": "hacen"},
        "es_past_map": {"1s": "hice", "2s": "hiciste", "3s": "hizo", "1p": "hicimos", "3p": "hicieron"},
        "es_fut_map": {"1s": "haré", "2s": "harás", "3s": "hará", "1p": "haremos", "3p": "harán"},
        "es_cond_map": {"1s": "haría", "2s": "harías", "3s": "haría", "1p": "haríamos", "3p": "harían"},
    },
    "take": {
        "3s": "takes", "past": "took", "ing": "taking", "es_inf": "tomar",
        "es_pres_map": {"1s": "tomo", "2s": "tomas", "3s": "toma", "1p": "tomamos", "3p": "toman"},
        "es_past_map": {"1s": "tomé", "2s": "tomaste", "3s": "tomó", "1p": "tomamos", "3p": "tomaron"},
        "es_fut_map": {"1s": "tomaré", "2s": "tomarás", "3s": "tomará", "1p": "tomaremos", "3p": "tomarán"},
        "es_cond_map": {"1s": "tomaría", "2s": "tomarías", "3s": "tomaría", "1p": "tomaríamos", "3p": "tomarían"},
    },
    "get": {
        "3s": "gets", "past": "got", "ing": "getting", "es_inf": "conseguir / obtener",
        "es_pres_map": {"1s": "consigo", "2s": "consigues", "3s": "consigue", "1p": "conseguimos", "3p": "consiguen"},
        "es_past_map": {"1s": "conseguí", "2s": "conseguiste", "3s": "consiguió", "1p": "conseguimos", "3p": "consiguieron"},
        "es_fut_map": {"1s": "conseguiré", "2s": "conseguirás", "3s": "conseguirá", "1p": "conseguiremos", "3p": "conseguirán"},
        "es_cond_map": {"1s": "conseguiría", "2s": "conseguirías", "3s": "conseguiría", "1p": "conseguiríamos", "3p": "conseguirían"},
    },
    "want": {
        "3s": "wants", "past": "wanted", "ing": "wanting", "es_inf": "querer",
        "es_pres_map": {"1s": "quiero", "2s": "quieres", "3s": "quiere", "1p": "queremos", "3p": "quieren"},
        "es_past_map": {"1s": "quise", "2s": "quisiste", "3s": "quiso", "1p": "quisimos", "3p": "quisieron"},
        "es_fut_map": {"1s": "querré", "2s": "querrás", "3s": "querrá", "1p": "querremos", "3p": "querrán"},
        "es_cond_map": {"1s": "querría", "2s": "querrías", "3s": "querría", "1p": "querríamos", "3p": "querrían"},
    },
    "know": {
        "3s": "knows", "past": "knew", "ing": "knowing", "es_inf": "saber / conocer",
        "es_pres_map": {"1s": "sé", "2s": "sabes", "3s": "sabe", "1p": "sabemos", "3p": "saben"},
        "es_past_map": {"1s": "supe", "2s": "supiste", "3s": "supo", "1p": "supimos", "3p": "supieron"},
        "es_fut_map": {"1s": "sabré", "2s": "sabrás", "3s": "sabrá", "1p": "sabremos", "3p": "sabrán"},
        "es_cond_map": {"1s": "sabría", "2s": "sabrías", "3s": "sabría", "1p": "sabríamos", "3p": "sabrían"},
    },
    "think": {
        "3s": "thinks", "past": "thought", "ing": "thinking", "es_inf": "pensar",
        "es_pres_map": {"1s": "pienso", "2s": "piensas", "3s": "piensa", "1p": "pensamos", "3p": "piensan"},
        "es_past_map": {"1s": "pensé", "2s": "pensaste", "3s": "pensó", "1p": "pensamos", "3p": "pensaron"},
        "es_fut_map": {"1s": "pensaré", "2s": "pensarás", "3s": "pensará", "1p": "pensaremos", "3p": "pensarán"},
        "es_cond_map": {"1s": "pensaría", "2s": "pensarías", "3s": "pensaría", "1p": "pensaríamos", "3p": "pensarían"},
    },
    "use": {
        "3s": "uses", "past": "used", "ing": "using", "es_inf": "usar",
        "es_pres_map": {"1s": "uso", "2s": "usas", "3s": "usa", "1p": "usamos", "3p": "usan"},
        "es_past_map": {"1s": "usé", "2s": "usaste", "3s": "usó", "1p": "usamos", "3p": "usaron"},
        "es_fut_map": {"1s": "usaré", "2s": "usarás", "3s": "usará", "1p": "usaremos", "3p": "usarán"},
        "es_cond_map": {"1s": "usaría", "2s": "usarías", "3s": "usaría", "1p": "usaríamos", "3p": "usarían"},
    },
    "find": {
        "3s": "finds", "past": "found", "ing": "finding", "es_inf": "encontrar",
        "es_pres_map": {"1s": "encuentro", "2s": "encuentras", "3s": "encuentra", "1p": "encontramos", "3p": "encuentran"},
        "es_past_map": {"1s": "encontré", "2s": "encontraste", "3s": "encontró", "1p": "encontramos", "3p": "encontraron"},
        "es_fut_map": {"1s": "encontraré", "2s": "encontrarás", "3s": "encontrará", "1p": "encontraremos", "3p": "encontrarán"},
        "es_cond_map": {"1s": "encontraría", "2s": "encontrarías", "3s": "encontraría", "1p": "encontraríamos", "3p": "encontrarían"},
    },
    "give": {
        "3s": "gives", "past": "gave", "ing": "giving", "es_inf": "dar",
        "es_pres_map": {"1s": "doy", "2s": "das", "3s": "da", "1p": "damos", "3p": "dan"},
        "es_past_map": {"1s": "di", "2s": "dijiste", "3s": "dio", "1p": "dimos", "3p": "dieron"},
        "es_fut_map": {"1s": "daré", "2s": "darás", "3s": "dará", "1p": "daremos", "3p": "darán"},
        "es_cond_map": {"1s": "daría", "2s": "darías", "3s": "daría", "1p": "daríamos", "3p": "darían"},
    },
    "tell": {
        "3s": "tells", "past": "told", "ing": "telling", "es_inf": "decir / contar",
        "es_pres_map": {"1s": "digo", "2s": "dices", "3s": "dice", "1p": "decimos", "3p": "dicen"},
        "es_past_map": {"1s": "dije", "2s": "dijiste", "3s": "dijo", "1p": "dijimos", "3p": "dijeron"},
        "es_fut_map": {"1s": "diré", "2s": "dirás", "3s": "dirá", "1p": "diremos", "3p": "dirán"},
        "es_cond_map": {"1s": "diría", "2s": "dirías", "3s": "diría", "1p": "diríamos", "3p": "dirían"},
    },
    "help": {
        "3s": "helps", "past": "helped", "ing": "helping", "es_inf": "ayudar",
        "es_pres_map": {"1s": "ayudo", "2s": "ayudas", "3s": "ayuda", "1p": "ayudamos", "3p": "ayudan"},
        "es_past_map": {"1s": "ayudé", "2s": "ayudaste", "3s": "ayudó", "1p": "ayudamos", "3p": "ayudaron"},
        "es_fut_map": {"1s": "ayudaré", "2s": "ayudarás", "3s": "ayudará", "1p": "ayudaremos", "3p": "ayudarán"},
        "es_cond_map": {"1s": "ayudaría", "2s": "ayudarías", "3s": "ayudaría", "1p": "ayudaríamos", "3p": "ayudarían"},
    },
    "try": {
        "3s": "tries", "past": "tried", "ing": "trying", "es_inf": "intentar / probar",
        "es_pres_map": {"1s": "intento", "2s": "intentas", "3s": "intenta", "1p": "intentamos", "3p": "intentan"},
        "es_past_map": {"1s": "intenté", "2s": "intentaste", "3s": "intentó", "1p": "intentamos", "3p": "intentaron"},
        "es_fut_map": {"1s": "intentaré", "2s": "intentarás", "3s": "intentará", "1p": "intentaremos", "3p": "intentarán"},
        "es_cond_map": {"1s": "intentaría", "2s": "intentarías", "3s": "intentaría", "1p": "intentaríamos", "3p": "intentarían"},
    },
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
    "happy": "feliz",
    "ready for the trip": "listo para el viaje",
    "a new car": "un auto nuevo",
    "time today": "tiempo hoy",
}

MODALS_CONJ_ES = {
    "can": {"1s": "puedo", "2s": "puedes", "3s": "puede", "1p": "podemos", "3p": "pueden"},
    "could": {"1s": "podría", "2s": "podrías", "3s": "podría", "1p": "podríamos", "3p": "podrían"},
    "should": {"1s": "debería", "2s": "deberías", "3s": "debería", "1p": "deberíamos", "3p": "deberían"},
    "must": {"1s": "debo", "2s": "debes", "3s": "debe", "1p": "debemos", "3p": "deben"},
    "may": {"1s": "puedo", "2s": "puedes", "3s": "puede", "1p": "podemos", "3p": "pueden"},
    "might": {"1s": "podría", "2s": "podrías", "3s": "podría", "1p": "podríamos", "3p": "podrían"},
    "would": {"1s": "quisiera", "2s": "querrías", "3s": "querría", "1p": "querríamos", "3p": "querrían"},
    "shall": {"1s": "deberé / propongo", "2s": "deberás", "3s": "deberá", "1p": "deberemos / propongo", "3p": "deberán"},
}

SEMIMODALS_ES = {
    "have to": {"1s": "tengo que", "2s": "tienes que", "3s": "tiene que", "1p": "tenemos que", "3p": "tienen que"},
    "need to": {"1s": "necesito", "2s": "necesitas", "3s": "necesita", "1p": "necesitamos", "3p": "necesitan"},
    "used to": {"1s": "solía", "2s": "solías", "3s": "solía", "1p": "solíamos", "3p": "solían"},
    "be able to": {"1s": "soy capaz de", "2s": "eres capaz de", "3s": "es capaz de", "1p": "somos capaces de", "3p": "son capaces de"},
}

BE_PRES_ES = {"1s": "estoy", "2s": "estás", "3s": "está", "1p": "estamos", "3p": "están"}
BE_PAST_ES = {"1s": "estaba", "2s": "estabas", "3s": "estaba", "1p": "estábamos", "3p": "estaban"}
HAVE_PRES_ES = {"1s": "tengo", "2s": "tienes", "3s": "tiene", "1p": "tenemos", "3p": "tienen"}



CHALLENGES = [
    {"es": "Ella puede hablar inglés todos los días.", "en": "She can speak English every day.", "hint": "Modal 'can' + verbo base sin 's'"},
    {"es": "¿Trabajan ellos en la oficina?", "en": "Do they work in the office?", "hint": "Pregunta en presente simple con 'They' -> usa 'Do'"},
    {"es": "Él no estudió un libro nuevo.", "en": "He did not study a new book.", "hint": "Negación en pasado -> 'did not' + verbo en forma base"},
    {"es": "¿Está ella lista para el viaje?", "en": "Is she ready for the trip?", "hint": "Verbo 'to be' con 'She' en pregunta -> invierte 'Is she...'"},
    {"es": "Nosotros viajaremos a Orlando el próximo mes.", "en": "We will travel to Orlando next month.", "hint": "Futuro simple -> 'will' + verbo base"},
    {"es": "Tú deberías comer comida saludable.", "en": "You should eat healthy food.", "hint": "Consejo -> modal 'should' + verbo base"},
    {"es": "¿Tiene él un auto nuevo?", "en": "Does he have a new car?", "hint": "Pregunta con 'have' como verbo principal en 3ra persona -> 'Does he have...'"},
]


# ==============================================================================
# BANCO DE VIDEOS REALES DE SHADOWING CON SUBTÍTULOS EN INGLÉS (6 A 12 MINUTOS)
# ==============================================================================
SHADOWING_VIDEOS = [
    {
        "id": "vid_dev_01",
        "video_id": "ky37JpN0Qeg",
        "title": "CURSO de INGLÉS SOLO Escuchando desde 0 | Episodio 4",
        "channel": "English by Deivid",
        "duration": "58:43",
        "level": "A1 - Principiante Absoluto",
        "category": "Inmersión Total / Inédito",
        "url": "https://www.youtube.com/watch?v=ky37JpN0Qeg",
        "desc": "Inmersión auditiva intensiva desde cero basada en el método natural de escucha repetida sin memorizar gramática.",
    },
    {
        "id": "vid_dev_02",
        "video_id": "HURxZJJ4r7w",
        "title": "De 0 a Entender TODO en Inglés (Solo Escuchando) [Episodio 3]",
        "channel": "English by Deivid",
        "duration": "50:11",
        "level": "A1/A2 - Básico / Elemental",
        "category": "Inmersión Total / Inédito",
        "url": "https://www.youtube.com/watch?v=HURxZJJ4r7w",
        "desc": "Entrenamiento auditivo progresivo para conectar sonidos y empezar a comprender frases cotidianas de forma natural.",
    },
    {
        "id": "vid_dev_03",
        "video_id": "dpC2gwLZptI",
        "title": "Te ahorraré 10 AÑOS de APRENDER INGLÉS Solo Escuchando [Episodio 2]",
        "channel": "English by Deivid",
        "duration": "49:52",
        "level": "A1 - Principiante Absoluto",
        "category": "Inmersión Total / Inédito",
        "url": "https://www.youtube.com/watch?v=dpC2gwLZptI",
        "desc": "Enfoque natural enfocado en el desarrollo del oído y la asimilación pasiva y activa de estructuras básicas.",
    },
    {
        "id": "vid_dev_04",
        "video_id": "kCzRBKNBYy0",
        "title": "NO sigas estudiando INGLÉS sin entender ESTO | Inglés hablado rápido",
        "channel": "English by Deivid",
        "duration": "50:20",
        "level": "A2/B1 - Elemental a Intermedio",
        "category": "Inmersión Total / Inédito",
        "url": "https://www.youtube.com/watch?v=kCzRBKNBYy0",
        "desc": "Desglose de los patrones de contracción y velocidad real del inglés hablado por nativos para mejorar la comprensión.",
    },
    {
        "id": "vid_01",
        "video_id": "o6a9kAswl-s",
        "title": "10 Minutes of American English Shadowing Practice (Part 1!)",
        "channel": "English Teacher Claire",
        "duration": "07:17",
        "level": "A2/B1 - Intermedio",
        "category": "Shadowing Guiado (US)",
        "url": "https://www.youtube.com/watch?v=o6a9kAswl-s",
        "desc": "Práctica guiada de pronunciación y ritmo en inglés americano con frases en pantalla y pausas para repetir.",
    },
    {
        "id": "vid_02",
        "video_id": "MrrxN6GZJaU",
        "title": "Shadowing English Speaking Practice | Daily Conversation for Beginners",
        "channel": "English Unleashed: The Podcast",
        "duration": "08:01",
        "level": "A1/A2 - Básico",
        "category": "Conversación Diaria",
        "url": "https://www.youtube.com/watch?v=MrrxN6GZJaU",
        "desc": "Entrenamiento de conversación cotidiana estilo podcast lento y claro con subtítulos integrados en inglés.",
    },
    {
        "id": "vid_03",
        "video_id": "KRXodcqsQXk",
        "title": "Shadowing in English: Speak More Naturally in 10 Minutes",
        "channel": "ez english practice",
        "duration": "10:20",
        "level": "B1 - Intermedio",
        "category": "Fluidez y Entonación",
        "url": "https://www.youtube.com/watch?v=KRXodcqsQXk",
        "desc": "Sesión de 10 minutos enfocada en hablar con naturalidad, conectando palabras y mejorando la entonación.",
    },
    {
        "id": "vid_04",
        "video_id": "N6fE7ukKyd0",
        "title": "Shadowing: Repeat-After-Me | English Speaking Practice",
        "channel": "English Coach Chad",
        "duration": "11:08",
        "level": "B1/B2 - Intermedio",
        "category": "Shadowing Guiado (US)",
        "url": "https://www.youtube.com/watch?v=N6fE7ukKyd0",
        "desc": "Ejercicio práctico de repetición inmediata ('Repeat-After-Me') para entrenar músculo articulatorio y acento estadounidense.",
    },
    {
        "id": "vid_05",
        "video_id": "_t3pBsFMBVU",
        "title": "How to do 10 minutes of speaking every day? | 8 Minute English",
        "channel": "LEP - Learn English Podcast",
        "duration": "08:55",
        "level": "A2/B1 - Elemental",
        "category": "Conversación Diaria",
        "url": "https://www.youtube.com/watch?v=_t3pBsFMBVU",
        "desc": "Episodio corto con texto en pantalla sobre cómo crear el hábito diario de hablar inglés 10 minutos al día.",
    },
    {
        "id": "vid_06",
        "video_id": "aOLsQN98aI4",
        "title": "10 Minutes to Improve English Speaking Skills Efficiently",
        "channel": "English Speaking Course",
        "duration": "11:15",
        "level": "A2/B1 - Intermedio",
        "category": "Diálogos Cotidianos",
        "url": "https://www.youtube.com/watch?v=aOLsQN98aI4",
        "desc": "Diálogos cotidianos subtitulados en inglés para practicar shadowing continuo en situaciones reales.",
    },
    {
        "id": "vid_07",
        "video_id": "eQbtmufQT0Y",
        "title": "A1-A2 English Listening & Speaking Practice | 10-Minute Practice",
        "channel": "PodEnglish",
        "duration": "11:58",
        "level": "A1/A2 - Básico",
        "category": "Conversación Diaria",
        "url": "https://www.youtube.com/watch?v=eQbtmufQT0Y",
        "desc": "Práctica progresiva para niveles A1 y A2 con vocabulario esencial y subtítulos claros en inglés.",
    },
    {
        "id": "vid_08",
        "video_id": "hkF_qsA88Ic",
        "title": "Business English | Shadowing Practice to Improve Fluency",
        "channel": "Fluency Ninja",
        "duration": "11:37",
        "level": "B1/B2 - Profesional",
        "category": "Trabajo y Negocios",
        "url": "https://www.youtube.com/watch?v=hkF_qsA88Ic",
        "desc": "Entrenamiento de frases profesionales para el trabajo, reuniones y comunicación corporativa en inglés.",
    },
    {
        "id": "vid_09",
        "video_id": "mhFQIStljzA",
        "title": "Business English Online Meetings | Shadowing Practice to Speak Fluently",
        "channel": "Fluency Ninja",
        "duration": "11:52",
        "level": "B2 - Intermedio Alto",
        "category": "Trabajo y Negocios",
        "url": "https://www.youtube.com/watch?v=mhFQIStljzA",
        "desc": "Expresiones clave con subtítulos en inglés para participar con fluidez en reuniones virtuales de trabajo.",
    },
    {
        "id": "vid_10",
        "video_id": "HTG_ObwJRUw",
        "title": "10-MIN SHADOWING ENGLISH SPEAKING PRACTICE | Expressing Opinions",
        "channel": "Simply Explained English",
        "duration": "12:25",
        "level": "B1/B2 - Intermedio",
        "category": "Fluidez y Entonación",
        "url": "https://www.youtube.com/watch?v=HTG_ObwJRUw",
        "desc": "Práctica intensiva para expresar opiniones, acuerdos y sentimientos en inglés de forma natural.",
    },
    {
        "id": "vid_11",
        "video_id": "Y681hXWwhQY",
        "title": "The benefits of doing nothing ⏲️ 6 Minute English",
        "channel": "BBC Learning English",
        "duration": "06:20",
        "level": "B1/B2 - Intermedio",
        "category": "BBC 6 Minute English (UK)",
        "url": "https://www.youtube.com/watch?v=Y681hXWwhQY",
        "desc": "Diálogo auténtico en inglés británico con vocabulario explicado y subtítulos sincronizados.",
    },
    {
        "id": "vid_12",
        "video_id": "pjFlVc-EDzc",
        "title": "What should you eat for a better night’s sleep? ⏲️ 6 Minute English",
        "channel": "BBC Learning English",
        "duration": "06:33",
        "level": "B1/B2 - Intermedio",
        "category": "BBC 6 Minute English (UK)",
        "url": "https://www.youtube.com/watch?v=pjFlVc-EDzc",
        "desc": "Conversación dinámica de 6 minutos con subtítulos en inglés para entrenar oído y pronunciación británica.",
    },
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

# ==============================================================================
# BANCO DE VOCABULARIO VISUAL (42 PALABRAS CON FONÉTICA, TRADUCCIÓN E ILUSTRACIÓN)
# ==============================================================================

# ==============================================================================
# GUÍA PEDAGÓGICA INTERACTIVA POR ESTRUCTURA / MODAL / TIEMPO
# ==============================================================================
STRUCTURE_PEDAGOGY = {
    "Presente Simple (do / does)": {
        "meaning": "Acciones habituales, rutinas diarias, hechos reales o verdades permanentes.",
        "when_to_use": "Úsalo cuando quieras expresar lo que alguien hace regularmente (todos los días, en el trabajo, en casa). NO se usa para lo que está pasando en este exacto segundo.",
        "translation_guide": "Se traduce como el presente indicativo en español (ej. trabajo, trabajas, trabaja).",
        "contrast": "En 3.ª persona singular (He, She, It) el verbo afirmativo lleva '-s/-es' (She works). En negativa y pregunta aparece el auxiliar 'do / does' y el verbo vuelve a su forma base.",
        "coherent_tip": "Combínalo con adverbios de frecuencia o rutinas como 'English every day', 'in the office' o 'at home'."
    },
    "Pasado Simple (did)": {
        "meaning": "Acciones que iniciaron y terminaron completamente en el pasado.",
        "when_to_use": "Úsalo para relatar eventos cerrados (ayer, la semana pasada, en un viaje anterior).",
        "translation_guide": "Se traduce como pretérito perfecto simple (ej. trabajé, viajó, comimos).",
        "contrast": "En afirmativa el verbo cambia a pasado (worked, went, spoke). En negativa (did not) y pregunta (Did...?), el auxiliar 'did' absorbe el pasado y el verbo principal vuelve a su forma base.",
        "coherent_tip": "Evita combinarlo con expresiones futuras como 'next month'. Úsalo con acciones concretas como 'a new book', 'in the office' o 'healthy food'."
    },
    "Futuro Simple (will)": {
        "meaning": "Decisiones espontáneas tomadas en el momento, promesas, predicciones o eventos futuros.",
        "when_to_use": "Úsalo cuando proyectes algo que ocurrirá después de hoy o para hacer una promesa firme.",
        "translation_guide": "Se traduce como futuro simple en español (ej. viajaré, aprenderás, trabajaremos).",
        "contrast": "'Will' es un modal puro: nunca cambia según el sujeto y el verbo siguiente va siempre en forma base sin 'to'. Negación común: 'will not' (won't).",
        "coherent_tip": "Funciona de forma excelente con 'to Orlando next month', 'English every day' o 'a new car'."
    },
    "Modal: can": {
        "meaning": "Habilidad física/mental (saber hacer algo), posibilidad real o permiso informal.",
        "when_to_use": "Elígelo cuando quieras decir que alguien TIENE LA CAPACIDAD de hacer algo o para pedir/dar permiso en confianza.",
        "translation_guide": "Se traduce como 'puedo / puedes / puede / podemos / pueden' + verbo infinitivo.",
        "contrast": "Diferencia con 'may': 'can' indica habilidad (He can speak English = Él sabe hablar inglés), mientras que 'may' indica duda ('puede que...') o permiso muy formal.",
        "coherent_tip": "Ideal con verbos de habilidad o acción como 'speak English every day', 'drive a new car' o 'cook healthy food'."
    },
    "Modal: could": {
        "meaning": "Posibilidad suave (50% opcional), habilidad en el pasado o petición muy cortés.",
        "when_to_use": "Elígelo para sugerir una alternativa sin imponerla ('podríamos viajar...'), hablar de lo que podías hacer antes o pedir algo con mucha educación ('Could you...?').",
        "translation_guide": "Se traduce como condicional 'podría / podrías / podríamos' o pasado 'pude / podía'.",
        "contrast": "Diferencia con 'must': 'could' es una sugerencia abierta y opcional; 'must' es una obligación innegociable.",
        "coherent_tip": "Úsalo para proponer planes como 'travel to Orlando next month' o 'study a new book'."
    },
    "Modal: should": {
        "meaning": "Consejo, recomendación saludable o sugerencia de lo que es correcto hacer.",
        "when_to_use": "Elígelo cuando quieras dar una opinión o recomendación amable sin llegar a ser una orden estricta.",
        "translation_guide": "Se traduce exactamente como 'debería / deberías / deberíamos / deberían'.",
        "contrast": "Es más suave que 'must' y 'have to'. Con 'should' aconsejas (You should eat healthy food); con 'must' ordenas.",
        "coherent_tip": "Muy natural con hábitos positivos: 'eat healthy food', 'study English every day' o 'read a new book'."
    },
    "Modal: must": {
        "meaning": "Obligación estricta/urgente (100%), regla innegociable o deducción lógica casi segura.",
        "when_to_use": "Elígelo para órdenes firmes, leyes, reglamentos o cuando algo es absolutamente indispensable.",
        "translation_guide": "Se traduce como 'debo / debes / debe / debemos / deben' (obligación fuerte).",
        "contrast": "¡Cuidado en negativa! 'must not (mustn't)' significa PROHIBICIÓN ESTRICTA (está prohibido hacerlo), mientras que 'don't have to' significa que es opcional.",
        "coherent_tip": "Úsalo en contextos de normas o deberes como 'work in the office' o 'study English every day'."
    },
    "Modal: may": {
        "meaning": "Probabilidad futura moderada (50% de duda: 'tal vez / puede que') o permiso formal.",
        "when_to_use": "Elígelo cuando NO estés seguro de si algo pasará o cuando pidas permiso en un entorno formal o profesional ('May I...?').",
        "translation_guide": "En afirmaciones de probabilidad equivale a 'puede que... / tal vez...'; en preguntas con 'I/We' traduce '¿Puedo / Podemos (formalmente)...?'.",
        "contrast": "Nunca uses 'may' para habilidades (no digas 'I may swim' para decir que sabes nadar; usa 'can').",
        "coherent_tip": "Excelente para planes posibles: 'travel to Orlando next month' o 'buy a new car'."
    },
    "Modal: might": {
        "meaning": "Probabilidad baja o remota (30% de certeza: 'quizás / a lo mejor podría').",
        "when_to_use": "Elígelo cuando una idea sea todavía más incierta o lejana que con 'may'.",
        "translation_guide": "Se traduce como 'podría (quizás) / tal vez...' indicando duda.",
        "contrast": "En preguntas casi no se usa; para preguntar por posibilidades es preferible usar 'can' o 'could'.",
        "coherent_tip": "Combínalo con acciones futuras posibles como 'visit with my family' o 'buy a new book'."
    },
    "Modal: would": {
        "meaning": "Condicional en español (terminación '-ría' en el verbo) u ofrecimientos/peticiones corteses.",
        "when_to_use": "Elígelo para situaciones hipotéticas ('Yo viajaría...') o preguntas educadas ('Would you...?' = ¿Te gustaría / Harías...?).",
        "translation_guide": "Convierte el verbo principal al condicional: 'would speak' = hablaría, 'would travel' = viajaría, 'would eat' = comería.",
        "contrast": "No indica obligación ni capacidad por sí mismo, sino deseo o condición hipotética.",
        "coherent_tip": "Pruébalo con cualquier verbo de acción: 'travel to Orlando next month' (viajaría a Orlando el próximo mes)."
    },
    "Modal: shall": {
        "meaning": "Sugerencia formal u ofrecimiento cortés (usado casi siempre con 'I' o 'We').",
        "when_to_use": "Elígelo principalmente en preguntas con 'I' o 'We' para proponer un plan ('Shall we go?' = ¿Vamos? / ¿Qué tal si vamos?).",
        "translation_guide": "Se traduce como '¿Propongo que...? / Deberemos...'.",
        "contrast": "Con sujetos como He, She, They o You suena anticuado o de contrato legal; con esos sujetos prefiere 'will' o 'should'.",
        "coherent_tip": "Selecciona el sujeto 'We' o 'I' en el Bloque 1 para crear una oración 100% natural."
    },
    "Semimodal: have to": {
        "meaning": "Obligación externa impuesta por horarios, trabajo, normas o circunstancias ('tener que').",
        "when_to_use": "Elígelo cuando la obligación venga de afuera (el jefe, la universidad, una cita) y no de un deseo propio.",
        "translation_guide": "Se traduce literalmente como 'tengo que / tienes que / tiene que / tenemos que / tienen que'.",
        "contrast": "A diferencia de 'must', SÍ cambia a 'has to' con He/She/It y usa 'do/does' en negativa y pregunta. En negativa ('don't/doesn't have to') significa 'NO es necesario (es opcional)'.",
        "coherent_tip": "Combínalo con responsabilidades cotidianas como 'work in the office' o 'drive a new car'."
    },
    "Semimodal: need to": {
        "meaning": "Necesidad práctica o requisito para lograr un objetivo ('necesitar hacer algo').",
        "when_to_use": "Elígelo cuando quieras expresar que algo es necesario o conveniente para el sujeto.",
        "translation_guide": "Se traduce como 'necesito / necesitas / necesita / necesitamos / necesitan' + verbo.",
        "contrast": "Es un semimodal: lleva '-s' en 3.ª persona singular ('He needs to...') y requiere 'do / does' para negar y preguntar.",
        "coherent_tip": "Muy útil con 'study English every day', 'eat healthy food' o 'buy a new car'."
    },
    "Semimodal: used to": {
        "meaning": "Hábito o costumbre del pasado que ya NO ocurre en el presente ('solía...').",
        "when_to_use": "Elígelo para contrastar tu vida de antes con la de ahora (ej. 'Yo solía vivir allá, pero ya no').",
        "translation_guide": "Se traduce como 'solía / solías / solíamos / solían' + verbo en infinitivo.",
        "contrast": "En afirmativa lleva '-d' (used to), pero en negativa (did not use to) y pregunta (Did ... use to?) pierde la '-d' por efecto del auxiliar 'did'.",
        "coherent_tip": "Evita complementos de futuro como 'next month'. Úsalo con 'live at home', 'work in the office' o 'play with my family'."
    },
    "Semimodal: be able to": {
        "meaning": "Ser capaz de / lograr hacer algo (sustituto formal y flexible de 'can').",
        "when_to_use": "Elígelo cuando quieras enfatizar la capacidad de lograr algo. Además, permite expresarse en todos los tiempos donde 'can' no existe.",
        "translation_guide": "Se traduce como 'soy / eres / es / somos / son capaz (capaces) de' + verbo.",
        "contrast": "Se conjuga a través del verbo To Be (am / is / are able to) y no utiliza 'do / does'.",
        "coherent_tip": "Combínalo con retos o habilidades como 'speak English every day' o 'drive very fast'."
    },
    "To Be (Presente: am/is/are)": {
        "meaning": "Identidad, profesión, estado de ánimo, característica o ubicación actual ('ser o estar').",
        "when_to_use": "Elígelo cuando NO vayas a usar un verbo de acción en base, sino para describir cómo está alguien o dónde se encuentra hoy.",
        "translation_guide": "Se traduce simultáneamente como 'soy/estoy', 'eres/estás', 'es/está', 'somos/estamos', 'son/están'.",
        "contrast": "Es autosuficiente: jamás usa 'do/does' ni se combina con verbos en forma base (no digas 'He is work'). En el bloque 3 selecciona '(ninguno - para To Be / Have)'.",
        "coherent_tip": "Deja el Bloque 3 en '(ninguno)' y elige en el Bloque 4 un estado o lugar: 'happy', 'ready for the trip', 'at home' o 'in the office'."
    },
    "To Be (Pasado: was/were)": {
        "meaning": "Estado de ánimo, condición o ubicación en el pasado ('era / estaba / fue / estuvo').",
        "when_to_use": "Elígelo para describir dónde estaba o cómo se sentía alguien en el pasado.",
        "translation_guide": "Usa 'was' para I, He, She, It ('estaba/era') y 'were' para You, We, They ('estaban/éramos/eran').",
        "contrast": "No utiliza el auxiliar 'did'. Se niega con 'was not / were not' y se pregunta invirtiendo 'Was / Were' al inicio.",
        "coherent_tip": "Deja el Bloque 3 en '(ninguno)' y usa complementos de estado o lugar como 'happy', 'at home' o 'in the office'."
    },
    "Have (Presente Simple: have/has)": {
        "meaning": "Posesión de objetos, tiempo, relaciones o características ('tener').",
        "when_to_use": "Elígelo cuando quieras decir que alguien posee algo (un auto, un libro, tiempo libre). Para obligación ('tener que hacer algo'), usa 'Semimodal: have to'.",
        "translation_guide": "Se traduce como 'tengo / tienes / tiene / tenemos / tienen'.",
        "contrast": "En afirmativa cambia a 'has' con He/She/It (She has a new car), pero en negativa (doesn't have) y pregunta (Does she have...?) usa el auxiliar 'do/does' y regresa a 'have'.",
        "coherent_tip": "Deja el Bloque 3 en '(ninguno)' y selecciona un objeto poseíble en el Bloque 4: 'a new car', 'a new book', 'time today' o 'healthy food'."
    }
}

VOCABULARY_BANK = [
    # Viajes y Aeropuerto
    {"en": "Boarding pass", "ipa": "/ˈbɔːr.dɪŋ ˌpæs/", "phonetic": "bór-ding pas", "es": "Pase de abordar", "cat": "Viajes y Aeropuerto", "icon": "🎫", "color": "#2563eb", "example_en": "Please show your boarding pass at the gate.", "example_es": "Por favor muestre su pase de abordar en la puerta."},
    {"en": "Luggage", "ipa": "/ˈlʌɡ.ɪdʒ/", "phonetic": "lá-guich", "es": "Equipaje / Maletas", "cat": "Viajes y Aeropuerto", "icon": "🧳", "color": "#2563eb", "example_en": "My luggage is already at the hotel.", "example_es": "Mi equipaje ya está en el hotel."},
    {"en": "Customs", "ipa": "/ˈkʌs.təmz/", "phonetic": "kás-tomz", "es": "Aduana / Migración", "cat": "Viajes y Aeropuerto", "icon": "🛃", "color": "#2563eb", "example_en": "It took twenty minutes to go through customs.", "example_es": "Tomó veinte minutos pasar por la aduana."},
    {"en": "Flight attendant", "ipa": "/ˈflaɪt əˌten.dənt/", "phonetic": "fláit a-tén-dant", "es": "Auxiliar de vuelo", "cat": "Viajes y Aeropuerto", "icon": "✈️", "color": "#2563eb", "example_en": "The flight attendant offered us water.", "example_es": "El auxiliar de vuelo nos ofreció agua."},
    {"en": "Round-trip ticket", "ipa": "/ˌraʊnd ˈtrɪp ˈtɪk.ɪt/", "phonetic": "ráund trip tí-ket", "es": "Tiquete de ida y vuelta", "cat": "Viajes y Aeropuerto", "icon": "🛫", "color": "#2563eb", "example_en": "We bought a round-trip ticket to Orlando.", "example_es": "Compramos un tiquete de ida y vuelta a Orlando."},
    {"en": "Shuttle bus", "ipa": "/ˈʃʌt.əl ˌbʌs/", "phonetic": "shá-tol bas", "es": "Autobús de traslado", "cat": "Viajes y Aeropuerto", "icon": "🚐", "color": "#2563eb", "example_en": "The resort has a free shuttle bus to the parks.", "example_es": "El complejo tiene un autobús gratuito a los parques."},
    {"en": "Rental car", "ipa": "/ˈren.təl ˌkɑːr/", "phonetic": "rén-tal kar", "es": "Auto de alquiler", "cat": "Viajes y Aeropuerto", "icon": "🚗", "color": "#2563eb", "example_en": "We picked up the rental car at the airport.", "example_es": "Recogimos el auto de alquiler en el aeropuerto."},
    {"en": "Roller coaster", "ipa": "/ˈroʊ.lər ˌkoʊ.stər/", "phonetic": "róu-ler kóus-ter", "es": "Montaña rusa", "cat": "Viajes y Aeropuerto", "icon": "🎢", "color": "#2563eb", "example_en": "That roller coaster is super fast!", "example_es": "¡Esa montaña rusa es súper rápida!"},
    {"en": "Passport", "ipa": "/ˈpæs.pɔːrt/", "phonetic": "pás-port", "es": "Pasaporte", "cat": "Viajes y Aeropuerto", "icon": "🛂", "color": "#2563eb", "example_en": "Keep your passport in a safe place.", "example_es": "Guarda tu pasaporte en un lugar seguro."},

    # Restaurantes y Comida
    {"en": "Appetizer", "ipa": "/ˈæp.ə.taɪ.zər/", "phonetic": "á-pe-tai-zer", "es": "Entrada / Aperitivo", "cat": "Restaurantes y Comida", "icon": "🥗", "color": "#d97706", "example_en": "Would you like to order an appetizer first?", "example_es": "¿Les gustaría pedir una entrada primero?"},
    {"en": "Main course", "ipa": "/ˌmeɪn ˈkɔːrs/", "phonetic": "méin kors", "es": "Plato fuerte / principal", "cat": "Restaurantes y Comida", "icon": "🍽️", "color": "#d97706", "example_en": "For the main course, I will have the grilled chicken.", "example_es": "Para el plato fuerte, pediré el pollo a la parrilla."},
    {"en": "Side dish", "ipa": "/ˈsaɪd ˌdɪʃ/", "phonetic": "sáid dish", "es": "Acompañamiento / Guarnición", "cat": "Restaurantes y Comida", "icon": "🍟", "color": "#d97706", "example_en": "Does it come with a side dish?", "example_es": "¿Viene con algún acompañamiento?"},
    {"en": "Check / Bill", "ipa": "/tʃek/ • /bɪl/", "phonetic": "chek / bil", "es": "La cuenta", "cat": "Restaurantes y Comida", "icon": "🧾", "color": "#d97706", "example_en": "Could we have the check, please?", "example_es": "¿Nos podría traer la cuenta, por favor?"},
    {"en": "Tip / Gratuity", "ipa": "/tɪp/ • /ɡrəˈtuː.ə.t̬i/", "phonetic": "tip / gra-tú-i-ti", "es": "Propina", "cat": "Restaurantes y Comida", "icon": "💵", "color": "#d97706", "example_en": "Is the tip included in the bill?", "example_es": "¿Está incluida la propina en la cuenta?"},
    {"en": "Napkin", "ipa": "/ˈnæp.kɪn/", "phonetic": "náp-kin", "es": "Servilleta", "cat": "Restaurantes y Comida", "icon": "🧻", "color": "#d97706", "example_en": "Can I get some extra napkins, please?", "example_es": "¿Me puede dar unas servilletas extra, por favor?"},
    {"en": "Refill", "ipa": "/ˈriː.fɪl/", "phonetic": "rí-fil", "es": "Recarga de bebida", "cat": "Restaurantes y Comida", "icon": "🥤", "color": "#d97706", "example_en": "Soft drinks include free refills.", "example_es": "Las gaseosas incluyen recargas gratuitas."},
    {"en": "Silverware", "ipa": "/ˈsɪl.vər.wer/", "phonetic": "síl-ver-wer", "es": "Cubiertos", "cat": "Restaurantes y Comida", "icon": "🍴", "color": "#d97706", "example_en": "We need another set of silverware.", "example_es": "Necesitamos otro juego de cubiertos."},

    # Hoteles y Compras
    {"en": "Front desk", "ipa": "/ˈfrʌnt ˌdesk/", "phonetic": "fránt desk", "es": "Recepción del hotel", "cat": "Hoteles y Compras", "icon": "🛎️", "color": "#059669", "example_en": "Leave the room key at the front desk.", "example_es": "Deja la llave de la habitación en la recepción."},
    {"en": "Housekeeping", "ipa": "/ˈhaʊsˌkiː.pɪŋ/", "phonetic": "jáus-ki-ping", "es": "Servicio de limpieza", "cat": "Hoteles y Compras", "icon": "🧹", "color": "#059669", "example_en": "Call housekeeping for clean towels.", "example_es": "Llama al servicio de limpieza por toallas limpias."},
    {"en": "Receipt", "ipa": "/rɪˈsiːt/", "phonetic": "ri-sít (la 'p' es muda)", "es": "Recibo / Factura de compra", "cat": "Hoteles y Compras", "icon": "🛍️", "color": "#059669", "example_en": "Keep your receipt in case you want to exchange it.", "example_es": "Guarda tu recibo en caso de que quieras cambiarlo."},
    {"en": "Fitting room", "ipa": "/ˈfɪt̬.ɪŋ ˌruːm/", "phonetic": "fí-ting rum", "es": "Vestier / Probador", "cat": "Hoteles y Compras", "icon": "👕", "color": "#059669", "example_en": "Where are the fitting rooms?", "example_es": "¿Dónde quedan los probadores?"},
    {"en": "Discount", "ipa": "/ˈdɪs.kaʊnt/", "phonetic": "dís-kaunt", "es": "Descuento", "cat": "Hoteles y Compras", "icon": "🏷️", "color": "#059669", "example_en": "This outlet store has a fifty percent discount.", "example_es": "Esta tienda outlet tiene un cincuenta por ciento de descuento."},
    {"en": "Refund", "ipa": "/ˈriː.fʌnd/", "phonetic": "rí-fand", "es": "Reembolso / Devolución", "cat": "Hoteles y Compras", "icon": "💳", "color": "#059669", "example_en": "They gave me a full refund.", "example_es": "Me dieron un reembolso completo."},
    {"en": "Vacancy", "ipa": "/ˈveɪ.kən.si/", "phonetic": "véi-kan-si", "es": "Disponibilidad de habitaciones", "cat": "Hoteles y Compras", "icon": "🏨", "color": "#059669", "example_en": "Does the hotel have any vacancies tonight?", "example_es": "¿Tiene el hotel habitaciones disponibles esta noche?"},
    {"en": "Pillow", "ipa": "/ˈpɪl.oʊ/", "phonetic": "pí-lou", "es": "Almohada", "cat": "Hoteles y Compras", "icon": "🛌", "color": "#059669", "example_en": "Could you send two extra pillows to room 305?", "example_es": "¿Podrían enviar dos almohadas extra a la habitación 305?"},

    # Trabajo y Tecnología
    {"en": "Database backup", "ipa": "/ˈdeɪ.t̬ə.beɪs ˈbæk.ʌp/", "phonetic": "déi-ta-beis bák-ap", "es": "Copia de seguridad de BD", "cat": "Trabajo y Tecnología", "icon": "🗄️", "color": "#7c3aed", "example_en": "The automated database backup runs at midnight.", "example_es": "La copia de seguridad automática corre a medianoche."},
    {"en": "Deadline", "ipa": "/ˈded.laɪn/", "phonetic": "déd-lain", "es": "Fecha límite de entrega", "cat": "Trabajo y Tecnología", "icon": "⏰", "color": "#7c3aed", "example_en": "We met the project deadline on time.", "example_es": "Cumplimos la fecha límite del proyecto a tiempo."},
    {"en": "Server downtime", "ipa": "/ˈsɝː.vər ˈdaʊn.taɪm/", "phonetic": "sér-ver dáun-taim", "es": "Tiempo de inactividad del servidor", "cat": "Trabajo y Tecnología", "icon": "🖥️", "color": "#7c3aed", "example_en": "The migration finished with zero server downtime.", "example_es": "La migración terminó con cero tiempo de inactividad."},
    {"en": "Troubleshooting", "ipa": "/ˈtrʌb.əlˌʃuː.t̬ɪŋ/", "phonetic": "trá-bol-shu-ting", "es": "Diagnóstico y solución de fallos", "cat": "Trabajo y Tecnología", "icon": "🛠️", "color": "#7c3aed", "example_en": "I spent the morning troubleshooting a network issue.", "example_es": "Pasé la mañana solucionando un problema de red."},
    {"en": "Schedule", "ipa": "/ˈskedʒ.uːl/", "phonetic": "ské-dyul", "es": "Horario / Cronograma / Programar", "cat": "Trabajo y Tecnología", "icon": "📅", "color": "#7c3aed", "example_en": "Let us schedule a quick meeting for tomorrow.", "example_es": "Programemos una reunión rápida para mañana."},
    {"en": "Network share", "ipa": "/ˈnet.wɝːk ˌʃer/", "phonetic": "nét-work sher", "es": "Carpeta compartida en red", "cat": "Trabajo y Tecnología", "icon": "🌐", "color": "#7c3aed", "example_en": "All files are stored on the Linux network share.", "example_es": "Todos los archivos están en la carpeta compartida de Linux."},
    {"en": "Update", "ipa": "/ʌpˈdeɪt/", "phonetic": "ap-déit", "es": "Actualizar / Actualización", "cat": "Trabajo y Tecnología", "icon": "🔄", "color": "#7c3aed", "example_en": "We need to update user permissions today.", "example_es": "Necesitamos actualizar los permisos de usuario hoy."},
    {"en": "Password", "ipa": "/ˈpæs.wɝːd/", "phonetic": "pás-word", "es": "Contraseña", "cat": "Trabajo y Tecnología", "icon": "🔐", "color": "#7c3aed", "example_en": "Never share your administrator password.", "example_es": "Nunca compartas tu contraseña de administrador."},

    # Vida Diaria y Familia
    {"en": "Countryside", "ipa": "/ˈkʌn.tri.saɪd/", "phonetic": "kán-tri-said", "es": "El campo / Zona rural", "cat": "Vida Diaria y Familia", "icon": "🏡", "color": "#0d9488", "example_en": "We spent the weekend with our family in the countryside.", "example_es": "Pasamos el fin de semana con nuestra familia en el campo."},
    {"en": "Granddaughter", "ipa": "/ˈɡræn.dɑː.t̬ər/", "phonetic": "grán-do-ter", "es": "Nieta", "cat": "Vida Diaria y Familia", "icon": "👧", "color": "#0d9488", "example_en": "Our granddaughter loves listening to music.", "example_es": "A nuestra nieta le encanta escuchar música."},
    {"en": "Headphones", "ipa": "/ˈhed.foʊnz/", "phonetic": "jéd-founz", "es": "Audífonos / Auriculares", "cat": "Vida Diaria y Familia", "icon": "🎧", "color": "#0d9488", "example_en": "Use headphones to practice your English shadowing.", "example_es": "Usa audífonos para practicar tu shadowing en inglés."},
    {"en": "Neighborhood", "ipa": "/ˈneɪ.bər.hʊd/", "phonetic": "néi-bor-jud", "es": "Barrio / Vecindario", "cat": "Vida Diaria y Familia", "icon": "🏘️", "color": "#0d9488", "example_en": "This is a very quiet and safe neighborhood.", "example_es": "Este es un barrio muy tranquilo y seguro."},
    {"en": "Groceries", "ipa": "/ˈɡroʊ.sər.iz/", "phonetic": "gróu-se-riz", "es": "Mercado / Víveres", "cat": "Vida Diaria y Familia", "icon": "🛒", "color": "#0d9488", "example_en": "We need to buy groceries for dinner.", "example_es": "Necesitamos comprar el mercado para la cena."},
    {"en": "Weather", "ipa": "/ˈweð.ər/", "phonetic": "wé-der", "es": "Clima / Tiempo atmosférico", "cat": "Vida Diaria y Familia", "icon": "🌤️", "color": "#0d9488", "example_en": "The weather in Cali is warm and sunny.", "example_es": "El clima en Cali es cálido y soleado."},
    {"en": "Gift / Present", "ipa": "/ɡɪft/ • /ˈprez.ənt/", "phonetic": "guift / pré-zent", "es": "Regalo / Obsequio", "cat": "Vida Diaria y Familia", "icon": "🎁", "color": "#0d9488", "example_en": "We prepared a special birthday gift for her.", "example_es": "Preparamos un regalo de cumpleaños especial para ella."},
    {"en": "Breakfast", "ipa": "/ˈbrek.fəst/", "phonetic": "brék-fast", "es": "Desayuno", "cat": "Vida Diaria y Familia", "icon": "🥞", "color": "#0d9488", "example_en": "Breakfast is the most important meal of the day.", "example_es": "El desayuno es la comida más importante del día."},
    {"en": "Gathering", "ipa": "/ˈɡæð.ər.ɪŋ/", "phonetic": "gá-de-ring", "es": "Reunión familiar / Encuentro", "cat": "Vida Diaria y Familia", "icon": "🎉", "color": "#0d9488", "example_en": "We organized a Thanksgiving family gathering.", "example_es": "Organizamos una reunión familiar de Acción de Gracias."},
]


def render_vocab_visual_card(item: dict, is_mastered: bool = False) -> str:
    """Genera una tarjeta HTML/SVG con ilustración visual integrada para la palabra de vocabulario."""
    badge_html = (
        '<span style="background:#dcfce7;color:#166534;padding:3px 9px;border-radius:12px;font-size:0.76rem;font-weight:700;">✅ Aprendida</span>'
        if is_mastered
        else f'<span style="background:{item["color"]}18;color:{item["color"]};padding:3px 9px;border-radius:12px;font-size:0.76rem;font-weight:600;">{item["cat"]}</span>'
    )
    return f"""
    <div style="border:1px solid #e2e8f0; border-top:4px solid {item['color']}; border-radius:12px; padding:14px; background:#ffffff; margin-bottom:10px; box-shadow:0 2px 5px rgba(15,23,42,0.04);">
        <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:8px;">
            {badge_html}
            <span style="font-size:0.8rem; color:#64748b; font-family:monospace;">{item['ipa']}</span>
        </div>
        <div style="display:flex; align-items:center; gap:14px; margin:8px 0 10px 0;">
            <div style="width:68px; height:68px; min-width:68px; border-radius:14px; background:linear-gradient(135deg, {item['color']}22, {item['color']}08); border:1px solid {item['color']}33; display:flex; align-items:center; justify-content:center; font-size:2.3rem;">
                {item['icon']}
            </div>
            <div>
                <div style="font-size:1.3rem; font-weight:800; color:#0f172a; line-height:1.2;">{item['en']}</div>
                <div style="font-size:0.9rem; color:#2563eb; font-weight:600; margin-top:2px;">🗣️ Se pronuncia: <code>/{item['phonetic']}/</code></div>
                <div style="font-size:1.05rem; color:#15803d; font-weight:700; margin-top:3px;">🇪🇸 {item['es']}</div>
            </div>
        </div>
        <div style="background:#f8fafc; border-radius:8px; padding:8px 10px; font-size:0.86rem; color:#334155; border-left:3px solid {item['color']};">
            <div><strong>Ejemplo:</strong> <em>"{item['example_en']}"</em></div>
            <div style="color:#64748b; margin-top:2px;">{item['example_es']}</div>
        </div>
    </div>
    """

EXAM_BANK = [
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
# FUNCIONES DE LÓGICA GRAMATICAL, VALIDACIÓN PROFUNDA Y CONJUGACIÓN
# ==============================================================================
VERB_COMPATIBILITY = {
    "work": {"allowed": {"in the office", "at home", "with my family", "very fast", "English every day", "time today"}, "recommended": "in the office"},
    "study": {"allowed": {"English every day", "in the office", "at home", "with my family", "a new book"}, "recommended": "English every day"},
    "speak": {"allowed": {"English every day", "in the office", "at home", "with my family", "very fast"}, "recommended": "English every day"},
    "travel": {"allowed": {"to Orlando next month", "with my family", "very fast"}, "recommended": "to Orlando next month"},
    "go": {"allowed": {"to Orlando next month", "in the office", "at home", "with my family", "very fast"}, "recommended": "to Orlando next month"},
    "eat": {"allowed": {"healthy food", "in the office", "at home", "with my family", "very fast"}, "recommended": "healthy food"},
    "read": {"allowed": {"a new book", "English every day", "in the office", "at home", "with my family", "very fast"}, "recommended": "a new book"},
    "write": {"allowed": {"a new book", "English every day", "in the office", "at home", "very fast"}, "recommended": "a new book"},
    "learn": {"allowed": {"English every day", "a new book", "at home", "with my family", "very fast"}, "recommended": "English every day"},
    "play": {"allowed": {"in the office", "at home", "with my family", "very fast"}, "recommended": "with my family"},
    "buy": {"allowed": {"a new book", "healthy food", "a new car"}, "recommended": "a new car"},
    "visit": {"allowed": {"with my family"}, "recommended": "with my family"},
    "cook": {"allowed": {"healthy food", "at home", "with my family", "very fast"}, "recommended": "healthy food"},
    "drive": {"allowed": {"a new car", "to Orlando next month", "very fast", "with my family"}, "recommended": "a new car"},
    "live": {"allowed": {"at home", "with my family", "happy"}, "recommended": "with my family"},
}

BE_ALLOWED_COMPLEMENTS = {"in the office", "at home", "with my family", "happy", "ready for the trip"}
HAVE_ALLOWED_COMPLEMENTS = {"a new book", "healthy food", "a new car", "time today"}

PAST_TIME_WORDS = ("yesterday", "last night", "last week", "last month", "last year", "ago")
FUTURE_TIME_WORDS = ("tomorrow", "next week", "next month", "next year", "soon")


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
        .replace("wouldn't", "would not")
        .replace("shan't", "shall not")
    )
    return norm


def translate_complement_es(comp_clean: str, person: str, is_female_3s: bool = False) -> str:
    if comp_clean == "happy":
        return "felices" if person in ("1p", "3p") else "feliz"
    if comp_clean == "ready for the trip":
        if person in ("1p", "3p"):
            return "listos para el viaje"
        return "lista para el viaje" if is_female_3s else "listo para el viaje"
    return COMPLEMENTS_PRESETS.get(comp_clean, comp_clean)


def validate_sentence_logic_and_grammar(subject_str: str, structure_type: str, action_raw: str, comp_raw: str) -> tuple:
    """
    Valida errores estructurales, gramaticales, temporales y de coherencia semántica (lógica).
    Retorna: (warnings_list, sanitized_action_str)
    """
    warnings = []
    subj = subject_str.strip()
    act = action_raw.strip()
    act_low = act.lower()
    comp = comp_raw.strip()
    comp_low = comp.lower()

    is_to_be = structure_type.startswith("To Be")
    is_have = structure_type.startswith("Have")
    needs_action_verb = not (is_to_be or is_have)

    # 1. Validación de Sujeto
    if not subj:
        warnings.append("⚠️ **Error de Estructura (Sujeto vacío):** Toda oración en inglés necesita un sujeto explícito (ej. `I`, `She`, `They`). Se usará **`I`** por defecto.")

    # 2. Validación de Verbo en modo libre (to + verbo, gerundio, conjugado o pasado)
    if act_low.startswith("to ") and len(act_low) > 3:
        clean_v = act_low[3:].strip()
        warnings.append(
            f"⚠️ **Error Gramatical en Acción (`{act}`):** No escribas `to` antes del verbo base porque la estructura (`{structure_type}`) ya maneja sus propios auxiliares/modales. Se corrigió automáticamente a **`{clean_v}`**."
        )
        act_low = clean_v

    for base_v, v_data in VERBS_DB.items():
        if act_low == v_data["3s"]:
            warnings.append(
                f"⚠️ **Error de Conjugación (`{act}`):** Ingresaste el verbo conjugado con `-s`. En el bloque **Acción** debes usar siempre la **forma base (`{base_v}`)**; el sistema agrega `-s` solo cuando corresponde."
            )
            act_low = base_v
            break
        if act_low == v_data["past"] and base_v != v_data["past"]:
            warnings.append(
                f"⚠️ **Error de Forma Verbal (`{act}`):** Ingresaste el verbo en pasado. Debes escribir la **forma base (`{base_v}`)** para que las formas negativa e interrogativa no dupliquen el pasado."
            )
            act_low = base_v
            break
        if act_low == v_data["ing"]:
            if is_to_be:
                warnings.append(
                    f"ℹ️ **Presente/Pasado Continuo detectado (`{act}`):** Al combinar **To Be** con un gerundio (`-ing`), estás formando tiempo continuo (*estar haciendo algo*)."
                )
            else:
                warnings.append(
                    f"⚠️ **Error Gramatical (`{act}`):** Con `{structure_type}` no se usa el verbo con `-ing` directamente; se requiere la **forma base (`{base_v}`)**."
                )
                act_low = base_v
            break

    # 3. Falta de verbo en estructuras que exigen acción
    if needs_action_verb and not act_low:
        warnings.append(
            f"⚠️ **Error de Estructura (Falta el verbo de acción):** La estructura **`{structure_type}`** exige un verbo principal en el bloque **3️⃣ Acción** (ej. `work`, `speak`, `travel`). No puedes elegir *(ninguno)* aquí."
        )

    # 4. Incompatibilidad de To Be / Have con verbos base
    if is_to_be and act_low and not act_low.endswith("ing"):
        warnings.append(
            f"⚠️ **Error Gramatical (`To Be` + `{act_low}`):** En inglés no se puede juntar el verbo **To Be (`am/is/are/was/were`)** con otro verbo en forma base (`{act_low}`). "
            f"Para usar **To Be**, selecciona **`(ninguno - para To Be / Have)`** en el bloque 3, o cambia el bloque 2 a **Presente Simple / Modal**."
        )
    if is_have and act_low:
        warnings.append(
            f"⚠️ **Error Gramatical (`Have` de posesión + verbo `{act_low}`):** Cuando usas **`Have (have/has)`** para indicar posesión (*tener algo*), en el bloque 3 debes elegir **`(ninguno - para To Be / Have)`** y poner un objeto en el complemento (ej. `a new car`, `a new book`). Si quieres decir *'tener que {act_low}'*, elige **`Semimodal: have to`** en el bloque 2."
        )

    # 5. Coherencia Temporal (Pasado vs Expresiones de Futuro y viceversa)
    is_past_struct = ("Pasado" in structure_type) or ("used to" in structure_type)
    is_future_struct = "Futuro" in structure_type

    if is_past_struct and any(fw in comp_low for fw in FUTURE_TIME_WORDS):
        warnings.append(
            f"⚠️ **Error de Lógica Temporal (Pasado + Futuro):** Estás usando una estructura en **pasado (`{structure_type}`)** con un complemento de **futuro (`{comp}`)**. "
            f"Cambia el tiempo a **Futuro Simple (`will`)** o usa una expresión de pasado (ej. *yesterday*, *last month*)."
        )
    if is_future_struct and any(pw in comp_low for pw in PAST_TIME_WORDS):
        warnings.append(
            f"⚠️ **Error de Lógica Temporal (Futuro + Pasado):** Estás usando **Futuro (`will`)** con una expresión de tiempo **pasado (`{comp}`)**."
        )
    if ("Presente" in structure_type or is_have) and any(pw in comp_low for pw in PAST_TIME_WORDS):
        warnings.append(
            f"⚠️ **Error de Lógica Temporal (Presente + Pasado):** Estás combinando una estructura en **presente** con una expresión de **pasado (`{comp}`)**."
        )

    # 6. Coherencia Semántica / Lógica entre Estructura, Acción y Complemento
    if is_to_be and not act_low.endswith("ing") and comp in COMPLEMENTS_PRESETS:
        if comp not in BE_ALLOWED_COMPLEMENTS:
            warnings.append(
                f"⚠️ **Error de Lógica Semántica (`To Be` + `{comp}`):** Decir *'{subj} is/are {comp}'* no tiene sentido lógico en inglés. "
                f"Con **To Be** debes usar un estado, adjetivo o lugar como **`happy`**, **`ready for the trip`**, **`at home`** o **`in the office`**."
            )

    if is_have and comp in COMPLEMENTS_PRESETS:
        if comp not in HAVE_ALLOWED_COMPLEMENTS:
            warnings.append(
                f"⚠️ **Error de Lógica Semántica (`Have` + `{comp}`):** Con el verbo **Have (tener)** el complemento debe ser un sustantivo u objeto poseíble como **`a new car`**, **`a new book`**, **`time today`** o **`healthy food`** (no *'{comp}'*)."
            )

    if needs_action_verb and act_low in VERB_COMPATIBILITY and comp in COMPLEMENTS_PRESETS:
        allowed_set = VERB_COMPATIBILITY[act_low]["allowed"]
        rec_comp = VERB_COMPATIBILITY[act_low]["recommended"]
        if comp not in allowed_set:
            if comp in ("happy", "ready for the trip"):
                warnings.append(
                    f"⚠️ **Error Gramatical y Lógico (`{act_low}` + `{comp}`):** `{comp}` es un adjetivo/estado que requiere el verbo **To Be**, no el verbo de acción `{act_low}`. "
                    f"Con **`{act_low}`** usa un complemento coherente como **`{rec_comp}`**."
                )
            elif act_low in ("go", "travel") and comp in ("in the office", "at home") and act_low == "travel":
                warnings.append(
                    f"⚠️ **Error de Preposición / Lógica (`{act_low}` + `{comp}`):** Los verbos de desplazamiento como `{act_low}` requieren destino con `to` (ej. **`to Orlando next month`**), no ubicación estática (`{comp}`)."
                )
            else:
                warnings.append(
                    f"⚠️ **Error de Lógica / Sentido (`{act_low}` + `{comp}`):** La combinación del verbo **`{act_low}`** (*{VERBS_DB[act_low]['es_inf']}*) con el complemento **`{comp}`** (*{COMPLEMENTS_PRESETS[comp]}*) no tiene coherencia lógica. "
                    f"Sugerencia para `{act_low}`: selecciona **`{rec_comp}`**."
                )

    # 7. Caso especial de preposición en go + in the office / at home
    if needs_action_verb and act_low == "go" and comp in ("in the office", "at home"):
        warnings.append(
            f"⚠️ **Error Gramatical de Preposición (`go {comp}`):** Con el verbo **`go`** (*ir*) no se dice `go in the office` ni `go at home`; en inglés lo correcto es **`go to the office`** o **`go home`** (o elegir **`to Orlando next month`**)."
        )

    # 8. Modal 'shall' con sujetos de 2da o 3ra persona
    if structure_type == "Modal: shall" and subj.capitalize() not in ("I", "We"):
        warnings.append(
            f"ℹ️ **Aviso de Uso (`shall` con `{subj}`):** En inglés moderno, **`shall`** se utiliza casi exclusivamente con **`I`** y **`We`** (para ofrecimientos o sugerencias como *'Shall we go?'*). Con `{subj}` es mucho más natural usar **`will`** o **`should`**."
        )

    return warnings, act_low


def build_sentences(subject_str: str, structure_type: str, action_str: str, complement_str: str, action_es_custom: str = "", comp_es_custom: str = ""):
    notes = []

    subj_clean = subject_str.strip() or "I"
    prof = infer_subject_profile(subj_clean)
    person = prof["person"]
    is_female_3s = subj_clean.strip().lower() == "she"
    s_disp = prof["display"]
    s_lower_for_q = "I" if s_disp == "I" else (s_disp[0].lower() + s_disp[1:] if s_disp in SUBJECTS else s_disp)

    warnings, action_clean = validate_sentence_logic_and_grammar(subject_str, structure_type, action_str, complement_str)
    comp_clean = complement_str.strip()
    if comp_es_custom.strip():
        c_es = comp_es_custom.strip()
    else:
        c_es_preset = translate_complement_es(comp_clean, person, is_female_3s)
        if c_es_preset == comp_clean and comp_clean not in COMPLEMENTS_PRESETS and comp_clean:
            c_es = auto_translate_text(comp_clean, "en", "es").lower()
        else:
            c_es = c_es_preset

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

        notes.append(f"**Regla Modal Puro (`{modal}`):** Nunca cambia en tercera persona (`He {modal}`, nunca *He {modal}s*) y el verbo principal (`{verb_base}`) va siempre en **forma base** sin *to*.")
        notes.append(f"**Pregunta:** Se invierte el modal antes del sujeto (`{modal.capitalize()} {s_lower_for_q}...`), sin usar *do/does*.")
        if modal == "must":
            notes.append("**`must` vs `have to`:** `must` expresa obligación interna o regla estricta; en negativa (`must not`) significa **prohibición**, mientras que `don't/doesn't have to` significa **ausencia de obligación** (es opcional).")
        elif modal == "may":
            notes.append("**`may` vs `can`:** `may` se usa para **permiso formal** (*May I...?*) o **probabilidad / duda** (*puede que / tal vez*), pero nunca para habilidades físicas o mentales (para habilidad usa `can`).")
        elif modal == "would":
            notes.append("**Uso de `would`:** Forma el condicional (*-ría*) y se usa para peticiones muy corteses (`Would you...`) u ofrecimientos.")
        elif modal == "shall":
            notes.append("**Uso de `shall`:** Muy usado con `I` o `We` para sugerencias formales u ofrecimientos (`Shall we go?`).")

        modal_es = MODALS_CONJ_ES[modal][person]
        v_es = action_es_custom.strip() if action_es_custom.strip() else ("ser / estar" if verb_base == "be" else VERBS_DB.get(verb_base, {}).get("es_inf", auto_translate_text(verb_base, "en", "es").lower()))
        if modal == "would" and verb_base in VERBS_DB:
            cond_v = VERBS_DB[verb_base]["es_cond_map"][person]
            es_trans = cap_first(f"{prof['es']} {cond_v} {c_es}.")
        elif modal == "may":
            es_trans = cap_first(f"Puede que {prof['es'].lower()} ({modal_es} formalmente) {v_es} {c_es}.")
        elif modal == "might":
            es_trans = cap_first(f"Tal vez {prof['es'].lower()} {modal_es} {v_es} {c_es}.")
        else:
            es_trans = cap_first(f"{prof['es']} {modal_es} {v_es} {c_es}.")

    elif structure_type.startswith("Semimodal:"):
        semi = structure_type.split(":")[1].strip().lower()
        verb_base = action_clean if action_clean else "work"
        if verb_base in ("am", "is", "are", "was", "were"):
            verb_base = "be"

        is_3s = prof["person"] == "3s"
        v_es = action_es_custom.strip() if action_es_custom.strip() else ("ser / estar" if verb_base == "be" else VERBS_DB.get(verb_base, {}).get("es_inf", auto_translate_text(verb_base, "en", "es").lower()))
        semi_es = SEMIMODALS_ES[semi][person]

        if semi == "have to":
            aff_semi = "has to" if is_3s else "have to"
            aux = "does" if is_3s else "do"
            aff = cap_first(f"{s_disp} {aff_semi} {verb_base} {comp_clean}.")
            neg = cap_first(f"{s_disp} {aux} not have to {verb_base} {comp_clean}.")
            ques = cap_first(f"{aux} {s_lower_for_q} have to {verb_base} {comp_clean}?")
            notes.append(f"**Semimodal `have to`:** A diferencia de `must`, sí se conjuga (`has to` en 3ra persona singular) y necesita **`{aux}`** para negar y preguntar.")
            notes.append("**Contraste clave con `must`:** En afirmativa ambos indican obligación (*tener que / deber*), pero en negativa `doesn't/don't have to` significa *no tiene que hacerlo (es opcional)*, mientras `must not` significa *está prohibido*.")
            es_trans = cap_first(f"{prof['es']} {semi_es} {v_es} {c_es}.")

        elif semi == "need to":
            aff_semi = "needs to" if is_3s else "need to"
            aux = "does" if is_3s else "do"
            aff = cap_first(f"{s_disp} {aff_semi} {verb_base} {comp_clean}.")
            neg = cap_first(f"{s_disp} {aux} not need to {verb_base} {comp_clean}.")
            ques = cap_first(f"{aux} {s_lower_for_q} need to {verb_base} {comp_clean}?")
            notes.append(f"**Semimodal `need to`:** Expresa necesidad. Lleva `-s` en 3ra persona singular (**`{aff_semi}`**) y usa el auxiliar **`{aux}`** en negativa y pregunta.")
            es_trans = cap_first(f"{prof['es']} {semi_es} {v_es} {c_es}.")

        elif semi == "used to":
            aff = cap_first(f"{s_disp} used to {verb_base} {comp_clean}.")
            neg = cap_first(f"{s_disp} did not use to {verb_base} {comp_clean}.")
            ques = cap_first(f"did {s_lower_for_q} use to {verb_base} {comp_clean}?")
            notes.append("**Semimodal `used to` (Hábitos en el pasado):** Expresa acciones habituales del pasado que ya no ocurren (*solía...*). Al usar **`did`** en negativa o pregunta, pierde la `-d` y queda **`use to`**.")
            es_trans = cap_first(f"{prof['es']} {semi_es} {v_es} {c_es}.")

        elif semi == "be able to":
            be_form = prof["be_pres"]
            aff = cap_first(f"{s_disp} {be_form} able to {verb_base} {comp_clean}.")
            neg = cap_first(f"{s_disp} {be_form} not able to {verb_base} {comp_clean}.")
            ques = cap_first(f"{be_form} {s_lower_for_q} able to {verb_base} {comp_clean}?")
            notes.append(f"**Semimodal `be able to`:** Equivalente a `can` (*ser capaz de / poder*) que se conjuga con el verbo `to be` (**`{be_form}`**), lo que permite usarlo también en futuro (`will be able to`) o pasado (`was/were able to`).")
            es_trans = cap_first(f"{prof['es']} {semi_es} {v_es} {c_es}.")

    elif structure_type == "To Be (Presente: am/is/are)":
        be_form = prof["be_pres"]
        mid = action_clean if (action_clean and action_clean not in VERBS_DB) else ""
        aff = cap_first(f"{s_disp} {be_form} {mid} {comp_clean}.")
        neg = cap_first(f"{s_disp} {be_form} not {mid} {comp_clean}.")
        ques = cap_first(f"{be_form} {s_lower_for_q} {mid} {comp_clean}?")

        notes.append(f"**Verbo To Be (Presente):** Para `{s_disp}` corresponde **`{be_form}`**.")
        notes.append("**Negación y Pregunta:** `To be` es autosuficiente; no utiliza *do/does*. Se niega añadiendo `not` y se pregunta invirtiendo el orden.")
        be_es = BE_PRES_ES[person]
        es_trans = cap_first(f"{prof['es']} {be_es} {mid} {c_es}.")

    elif structure_type == "To Be (Pasado: was/were)":
        be_form = prof["be_past"]
        mid = action_clean if (action_clean and action_clean not in VERBS_DB) else ""
        aff = cap_first(f"{s_disp} {be_form} {mid} {comp_clean}.")
        neg = cap_first(f"{s_disp} {be_form} not {mid} {comp_clean}.")
        ques = cap_first(f"{be_form} {s_lower_for_q} {mid} {comp_clean}?")

        notes.append(f"**Verbo To Be (Pasado):** Para `{s_disp}` corresponde **`{be_form}`**.")
        notes.append("**Negación y Pregunta:** No uses *did* con `was/were`. Invierte `{be_form}` para preguntar.")
        be_es = BE_PAST_ES[person]
        es_trans = cap_first(f"{prof['es']} {be_es} {mid} {c_es}.")

    elif structure_type == "Have (Presente Simple: have/has)":
        have_aff = prof["have"]
        aux_do = "does" if prof["person"] == "3s" else "do"
        extra = action_clean if (action_clean and action_clean not in VERBS_DB) else ""
        aff = cap_first(f"{s_disp} {have_aff} {extra} {comp_clean}.")
        neg = cap_first(f"{s_disp} {aux_do} not have {extra} {comp_clean}.")
        ques = cap_first(f"{aux_do} {s_lower_for_q} have {extra} {comp_clean}?")

        notes.append(f"**Have como verbo principal:** En afirmativa usa **`{have_aff}`**, pero en negativa e interrogativa usa el auxiliar **`{aux_do}`** y el verbo vuelve a su forma base **`have`**.")
        have_es = HAVE_PRES_ES[person]
        es_trans = cap_first(f"{prof['es']} {have_es} {extra} {c_es}.")

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

        v_info = VERBS_DB.get(verb_base, {})
        v_es = action_es_custom.strip() if action_es_custom.strip() else v_info.get("es_pres_map", {}).get(person, auto_translate_text(verb_base, "en", "es").lower())
        es_trans = cap_first(f"{prof['es']} {v_es} {c_es}.")

    elif structure_type == "Pasado Simple (did)":
        verb_base = action_clean if action_clean else "work"
        verb_past = conjugate_past(verb_base)

        aff = cap_first(f"{s_disp} {verb_past} {comp_clean}.")
        neg = cap_first(f"{s_disp} did not {verb_base} {comp_clean}.")
        ques = cap_first(f"did {s_lower_for_q} {verb_base} {comp_clean}?")

        notes.append(f"**Pasado Simple:** En afirmativa se usa el verbo en pasado (**`{verb_past}`**) para todos los sujetos.")
        notes.append(f"**Efecto Imán de `did`:** En negativa (`did not`) y pregunta (`Did...`), el auxiliar absorbe el pasado y el verbo principal regresa a su forma base (**`{verb_base}`**).")

        v_info = VERBS_DB.get(verb_base, {})
        v_es = action_es_custom.strip() if action_es_custom.strip() else v_info.get("es_past_map", {}).get(person, auto_translate_text(verb_base, "en", "es").lower())
        es_trans = cap_first(f"{prof['es']} {v_es} {c_es}.")

    elif structure_type == "Futuro Simple (will)":
        verb_base = action_clean if action_clean else "travel"
        aff = cap_first(f"{s_disp} will {verb_base} {comp_clean}.")
        neg = cap_first(f"{s_disp} will not {verb_base} {comp_clean}.")
        ques = cap_first(f"will {s_lower_for_q} {verb_base} {comp_clean}?")

        notes.append(f"**Futuro con `will`:** Funciona igual para todos los sujetos. Siempre va seguido del verbo en forma base (**`{verb_base}`**). Contracción negativa común: *won't*.")
        v_info = VERBS_DB.get(verb_base, {})
        v_es = action_es_custom.strip() if action_es_custom.strip() else v_info.get("es_fut_map", {}).get(person, f"va a {verb_base}")
        es_trans = cap_first(f"{prof['es']} {v_es} {c_es}.")

    return {
        "affirmative": aff,
        "negative": neg,
        "interrogative": ques,
        "spanish": es_trans,
        "warnings": warnings,
        "notes": notes,
    }


# Diccionario bidireccional instantáneo Español <-> Inglés para verbos y complementos
SPANISH_TO_ENGLISH_VERBS = {
    "trabajar": "work", "estudiar": "study", "hablar": "speak", "viajar": "travel",
    "ir": "go", "comer": "eat", "leer": "read", "escribir": "write",
    "aprender": "learn", "jugar": "play", "comprar": "buy", "visitar": "visit",
    "cocinar": "cook", "conducir": "drive", "manejar": "drive", "vivir": "live",
    "hacer": "make", "realizar": "do", "tomar": "take", "beber": "drink",
    "conseguir": "get", "obtener": "get", "querer": "want", "saber": "know",
    "conocer": "know", "pensar": "think", "usar": "use", "utilizar": "use",
    "encontrar": "find", "dar": "give", "decir": "tell", "contar": "tell",
    "ayudar": "help", "intentar": "try", "probar": "try", "nadar": "swim",
    "correr": "run", "caminar": "walk", "dormir": "sleep", "abrir": "open",
    "cerrar": "close", "pagar": "pay", "vender": "sell", "enviar": "send",
    "recibir": "receive", "escuchar": "listen", "mirar": "watch", "ver": "see",
    "limpiar": "clean", "lavar": "wash", "bailar": "dance", "cantar": "sing",
    "enseñar": "teach", "ensenar": "teach", "construir": "build", "diseñar": "design",
    "disenar": "design", "programar": "code", "reparar": "fix", "arreglar": "fix",
    "esperar": "wait", "llamar": "call", "entender": "understand", "comprender": "understand",
    "recordar": "remember", "olvidar": "forget", "empezar": "start", "comenzar": "start",
    "terminar": "finish", "elegir": "choose", "cambiar": "change", "practicar": "practice",
    "preparar": "prepare", "volar": "fly", "traer": "bring", "llevar": "take",
    "salir": "leave", "llegar": "arrive", "volver": "return", "regresar": "return",
    "sentir": "feel", "necesitar": "need", "amar": "love", "gustar": "like",
    "preferir": "prefer", "buscar": "look for", "perder": "lose", "ganar": "win",
    "ahorrar": "save", "gastar": "spend", "explicar": "explain", "preguntar": "ask",
    "responder": "answer", "contestar": "answer", "descansar": "rest", "entrenar": "train",
}

ENGLISH_TO_SPANISH_VERBS_EXTRA = {v: k for k, v in SPANISH_TO_ENGLISH_VERBS.items() if " " not in v}
for _v_en, _v_data in VERBS_DB.items():
    ENGLISH_TO_SPANISH_VERBS_EXTRA[_v_en] = _v_data["es_inf"]

SPANISH_PHRASE_CHUNKS_ES_EN = {
    "todos los dias": "every day",
    "todas las mananas": "every morning",
    "todas las noches": "every night",
    "todas las tardes": "every afternoon",
    "todas las semanas": "every week",
    "todos los fines de semana": "every weekend",
    "algunos dias": "some days",
    "algunas mananas": "some mornings",
    "algunas tardes": "some afternoons",
    "algunas noches": "some nights",
    "algunas veces": "sometimes",
    "a veces": "sometimes",
    "en la manana": "in the morning",
    "por la manana": "in the morning",
    "en las mananas": "in the mornings",
    "por las mananas": "in the mornings",
    "en la tarde": "in the afternoon",
    "por la tarde": "in the afternoon",
    "en las tardes": "in the afternoons",
    "en la noche": "at night",
    "por la noche": "at night",
    "en las noches": "at night",
    "al mediodia": "at noon",
    "en la oficina": "in the office",
    "en el trabajo": "at work",
    "en casa": "at home",
    "en la casa": "in the house",
    "en mi casa": "at my house",
    "en el parque": "in the park",
    "en la escuela": "at school",
    "en el colegio": "at school",
    "en la universidad": "at the university",
    "en el gimnasio": "at the gym",
    "en el hospital": "in the hospital",
    "en el restaurante": "at the restaurant",
    "en el hotel": "at the hotel",
    "en el aeropuerto": "at the airport",
    "en la playa": "on the beach",
    "en la piscina": "in the pool",
    "en el campo": "in the countryside",
    "en el centro comercial": "at the mall",
    "en el supermercado": "at the supermarket",
    "en la calle": "on the street",
    "en la ciudad": "in the city",
    "con mi familia": "with my family",
    "con toda mi familia": "with all my family",
    "con mis amigos": "with my friends",
    "con un amigo": "with a friend",
    "con mi esposa": "with my wife",
    "con mi esposo": "with my husband",
    "con mi hermano": "with my brother",
    "con mi hermana": "with my sister",
    "con mi hijo": "with my son",
    "con mi hija": "with my daughter",
    "con mi nieta": "with my granddaughter",
    "con mi nieto": "with my grandson",
    "con mis padres": "with my parents",
    "con mis companeros": "with my coworkers",
    "con el jefe": "with the boss",
    "el proximo mes": "next month",
    "la proxima semana": "next week",
    "el proximo ano": "next year",
    "el proximo verano": "next summer",
    "el fin de semana": "on the weekend",
    "este fin de semana": "this weekend",
    "los fines de semana": "on weekends",
    "la semana pasada": "last week",
    "el mes pasado": "last month",
    "el ano pasado": "last year",
    "ayer por la manana": "yesterday morning",
    "ayer por la tarde": "yesterday afternoon",
    "ayer por la noche": "last night",
    "anoche": "last night",
    "manana por la manana": "tomorrow morning",
    "manana por la tarde": "tomorrow afternoon",
    "manana por la noche": "tomorrow night",
    "hoy en la tarde": "this afternoon",
    "hoy en la manana": "this morning",
    "hoy en la noche": "tonight",
    "esta noche": "tonight",
    "esta manana": "this morning",
    "esta tarde": "this afternoon",
    "esta semana": "this week",
    "este mes": "this month",
    "este ano": "this year",
    "muy rapido": "very fast",
    "muy bien": "very well",
    "muy despacio": "very slowly",
    "muy temprano": "very early",
    "muy tarde": "very late",
    "muy duro": "very hard",
    "mucho": "a lot",
    "un poco": "a little",
    "un libro nuevo": "a new book",
    "un auto nuevo": "a new car",
    "un carro nuevo": "a new car",
    "una casa nueva": "a new house",
    "comida saludable": "healthy food",
    "comida deliciosa": "delicious food",
    "agua fria": "cold water",
    "cafe caliente": "hot coffee",
    "listo para el viaje": "ready for the trip",
    "lista para el viaje": "ready for the trip",
    "tiempo hoy": "time today",
    "ingles todos los dias": "English every day",
    "a orlando el proximo mes": "to Orlando next month",
}

ENGLISH_PHRASE_CHUNKS_EN_ES = {
    "some days": "algunos días",
    "every day": "todos los días",
    "every morning": "todas las mañanas",
    "every afternoon": "todas las tardes",
    "every night": "todas las noches",
    "every week": "todas las semanas",
    "every weekend": "todos los fines de semana",
    "in the morning": "en la mañana",
    "in the mornings": "en las mañanas",
    "in the afternoon": "en la tarde",
    "in the afternoons": "en las tardes",
    "at night": "en la noche",
    "at noon": "al mediodía",
    "in the office": "en la oficina",
    "at work": "en el trabajo",
    "at home": "en casa",
    "in the house": "en la casa",
    "in the park": "en el parque",
    "at school": "en la escuela",
    "at the university": "en la universidad",
    "at the gym": "en el gimnasio",
    "in the hospital": "en el hospital",
    "at the restaurant": "en el restaurante",
    "at the hotel": "en el hotel",
    "at the airport": "en el aeropuerto",
    "on the beach": "en la playa",
    "in the pool": "en la piscina",
    "in the countryside": "en el campo",
    "at the mall": "en el centro comercial",
    "at the supermarket": "en el supermercado",
    "in the city": "en la ciudad",
    "with my family": "con mi familia",
    "with my friends": "con mis amigos",
    "with a friend": "con un amigo",
    "with my wife": "con mi esposa",
    "with my husband": "con mi esposo",
    "with my brother": "con mi hermano",
    "with my sister": "con mi hermana",
    "with my son": "con mi hijo",
    "with my daughter": "con mi hija",
    "with my granddaughter": "con mi nieta",
    "with my parents": "con mis padres",
    "with my coworkers": "con mis compañeros",
    "next month": "el próximo mes",
    "next week": "la próxima semana",
    "next year": "el próximo año",
    "on the weekend": "el fin de semana",
    "this weekend": "este fin de semana",
    "on weekends": "los fines de semana",
    "last week": "la semana pasada",
    "last month": "el mes pasado",
    "last year": "el año pasado",
    "last night": "anoche",
    "tomorrow morning": "mañana por la mañana",
    "tomorrow afternoon": "mañana por la tarde",
    "tomorrow night": "mañana por la noche",
    "this morning": "esta mañana",
    "this afternoon": "esta tarde",
    "tonight": "esta noche",
    "this week": "esta semana",
    "this month": "este mes",
    "this year": "este año",
    "very fast": "muy rápido",
    "very well": "muy bien",
    "very slowly": "muy despacio",
    "very early": "muy temprano",
    "very late": "muy tarde",
    "very hard": "muy duro",
    "a lot": "mucho",
    "a little": "un poco",
    "a new book": "un libro nuevo",
    "a new car": "un auto nuevo",
    "a new house": "una casa nueva",
    "healthy food": "comida saludable",
    "delicious food": "comida deliciosa",
    "cold water": "agua fría",
    "hot coffee": "café caliente",
    "ready for the trip": "listo para el viaje",
    "time today": "tiempo hoy",
}

SPANISH_WORD_ES_EN = {
    "en": "in", "el": "the", "la": "the", "los": "the", "las": "the",
    "un": "a", "una": "a", "unos": "some", "unas": "some",
    "algun": "some", "alguno": "some", "alguna": "some", "algunos": "some", "algunas": "some",
    "mucho": "much", "muchos": "many", "muchas": "many", "poco": "little", "pocos": "few",
    "todo": "all", "toda": "all", "todos": "every", "todas": "every", "cada": "every",
    "otro": "another", "otra": "another", "otros": "other", "otras": "other",
    "dia": "day", "dias": "days", "manana": "morning", "mananas": "mornings",
    "tarde": "afternoon", "tardes": "afternoons", "noche": "night", "noches": "nights",
    "semana": "week", "semanas": "weeks", "mes": "month", "meses": "months",
    "ano": "year", "anos": "years", "hora": "hour", "horas": "hours", "minuto": "minute", "minutos": "minutes",
    "hoy": "today", "ayer": "yesterday", "ahora": "now", "siempre": "always", "nunca": "never",
    "pronto": "soon", "temprano": "early", "rapido": "fast", "lento": "slowly", "despacio": "slowly", "bien": "well",
    "con": "with", "sin": "without", "para": "for", "por": "in", "de": "of", "del": "from the", "a": "to", "al": "to the",
    "desde": "from", "hasta": "until", "durante": "during", "antes": "before", "despues": "after", "sobre": "about",
    "mi": "my", "mis": "my", "tu": "your", "tus": "your", "su": "his", "sus": "their",
    "nuestro": "our", "nuestra": "our", "nuestros": "our", "nuestras": "our",
    "familia": "family", "amigo": "friend", "amigos": "friends", "amiga": "friend", "amigas": "friends",
    "esposa": "wife", "esposo": "husband", "hijo": "son", "hija": "daughter", "hijos": "children",
    "nieta": "granddaughter", "nieto": "grandson", "hermano": "brother", "hermana": "sister",
    "padre": "father", "madre": "mother", "padres": "parents", "jefe": "boss", "cliente": "client", "clientes": "clients",
    "casa": "home", "oficina": "office", "trabajo": "work", "parque": "park", "calle": "street",
    "escuela": "school", "colegio": "school", "universidad": "university", "ciudad": "city", "pais": "country",
    "gimnasio": "gym", "playa": "beach", "piscina": "pool", "aeropuerto": "airport", "hotel": "hotel",
    "restaurante": "restaurant", "tienda": "store", "supermercado": "supermarket", "banco": "bank",
    "ingles": "English", "espanol": "Spanish", "musica": "music", "libro": "book", "libros": "books",
    "carro": "car", "auto": "car", "coche": "car", "comida": "food", "agua": "water", "cafe": "coffee",
    "desayuno": "breakfast", "almuerzo": "lunch", "cena": "dinner", "proyecto": "project", "reunion": "meeting",
    "computador": "computer", "computadora": "computer", "servidor": "server", "telefono": "phone", "celular": "phone",
    "viaje": "trip", "vacaciones": "vacation", "dinero": "money", "tiempo": "time", "pelicula": "movie", "futbol": "soccer",
    "feliz": "happy", "cansado": "tired", "ocupado": "busy", "listo": "ready", "lista": "ready",
    "nuevo": "new", "nueva": "new", "nuevos": "new", "nuevas": "new",
    "bueno": "good", "buena": "good", "grande": "big", "pequeno": "small", "importante": "important",
    "muy": "very", "mas": "more", "menos": "less", "tambien": "also", "solo": "only", "aqui": "here", "alli": "there",
    "y": "and", "o": "or", "pero": "but", "porque": "because", "cuando": "when", "donde": "where",
}

ENGLISH_WORD_EN_ES = {
    "in": "en", "on": "en", "at": "en", "the": "el/la", "a": "un/una", "an": "un/una",
    "some": "algunos", "many": "muchos", "every": "todos los", "all": "todo",
    "day": "día", "days": "días", "morning": "mañana", "mornings": "mañanas",
    "afternoon": "tarde", "afternoons": "tardes", "night": "noche", "nights": "noches",
    "week": "semana", "weeks": "semanas", "month": "mes", "months": "meses", "year": "año", "years": "años",
    "today": "hoy", "yesterday": "ayer", "tomorrow": "mañana", "tonight": "esta noche",
    "now": "ahora", "always": "siempre", "never": "nunca", "sometimes": "a veces", "soon": "pronto",
    "early": "temprano", "late": "tarde", "fast": "rápido", "slowly": "despacio", "well": "bien",
    "with": "con", "without": "sin", "for": "para", "of": "de", "to": "a", "from": "desde",
    "my": "mi", "your": "tu", "his": "su", "her": "su", "our": "nuestro", "their": "su",
    "family": "familia", "friend": "amigo", "friends": "amigos", "wife": "esposa", "husband": "esposo",
    "son": "hijo", "daughter": "hija", "granddaughter": "nieta", "brother": "hermano", "sister": "hermana",
    "home": "casa", "house": "casa", "office": "oficina", "work": "trabajo", "park": "parque",
    "school": "escuela", "university": "universidad", "city": "ciudad", "country": "país",
    "gym": "gimnasio", "beach": "playa", "pool": "piscina", "airport": "aeropuerto", "hotel": "hotel",
    "english": "inglés", "spanish": "español", "music": "música", "book": "libro", "books": "libros",
    "car": "auto", "food": "comida", "water": "agua", "coffee": "café", "breakfast": "desayuno",
    "lunch": "almuerzo", "dinner": "cena", "project": "proyecto", "meeting": "reunión", "trip": "viaje",
    "time": "tiempo", "money": "dinero", "happy": "feliz", "tired": "cansado", "busy": "ocupado",
    "ready": "listo", "new": "nuevo", "good": "bueno", "very": "muy", "and": "y", "or": "o", "here": "aquí",
}


def _strip_accents(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn")


def _local_compositional_es_to_en(text: str) -> str:
    norm = _strip_accents(text.strip().lower())
    norm = re.sub(r"\s+", " ", norm)
    if norm in SPANISH_PHRASE_CHUNKS_ES_EN:
        return SPANISH_PHRASE_CHUNKS_ES_EN[norm]
    result_str = norm
    for es_chunk in sorted(SPANISH_PHRASE_CHUNKS_ES_EN.keys(), key=len, reverse=True):
        pattern = r" " + re.escape(es_chunk) + r" "
        if re.search(pattern, result_str):
            result_str = re.sub(pattern, SPANISH_PHRASE_CHUNKS_ES_EN[es_chunk], result_str)
    tokens = result_str.split()
    out_tokens = [SPANISH_WORD_ES_EN.get(tok, SPANISH_TO_ENGLISH_VERBS.get(tok, tok)) for tok in tokens]
    return " ".join(out_tokens)


def _local_compositional_en_to_es(text: str) -> str:
    norm = re.sub(r"\s+", " ", text.strip().lower())
    if norm in ENGLISH_PHRASE_CHUNKS_EN_ES:
        return ENGLISH_PHRASE_CHUNKS_EN_ES[norm]
    result_str = norm
    for en_chunk in sorted(ENGLISH_PHRASE_CHUNKS_EN_ES.keys(), key=len, reverse=True):
        pattern = r" " + re.escape(en_chunk) + r" "
        if re.search(pattern, result_str):
            result_str = re.sub(pattern, ENGLISH_PHRASE_CHUNKS_EN_ES[en_chunk], result_str)
    tokens = result_str.split()
    out_tokens = [ENGLISH_WORD_EN_ES.get(tok, ENGLISH_TO_SPANISH_VERBS_EXTRA.get(tok, tok)) for tok in tokens]
    return " ".join(out_tokens)


def looks_like_spanish_text(text: str) -> bool:
    """Detecta si una frase o palabra escrita en la casilla de inglés está realmente en español."""
    clean = text.strip().lower()
    if not clean:
        return False
    if any(ch in clean for ch in "áéíóúñ¿¡"):
        return True
    norm = _strip_accents(clean)
    if norm in SPANISH_TO_ENGLISH_VERBS or norm in SPANISH_PHRASE_CHUNKS_ES_EN:
        return True
    tokens = re.findall(r"[a-z]+", norm)
    if not tokens:
        return False
    es_hits = sum(1 for t in tokens if t in SPANISH_WORD_ES_EN or t in SPANISH_TO_ENGLISH_VERBS)
    en_hits = sum(1 for t in tokens if t in ENGLISH_WORD_EN_ES or t in VERBS_DB)
    return es_hits > 0 and es_hits >= en_hits


@st.cache_data(show_spinner=False, ttl=86400)
def auto_translate_text(text: str, source_lang: str, target_lang: str) -> str:
    """
    Traduce texto entre español ('es') e inglés ('en').
    1) Diccionarios locales exactos
    2) Google Translate GTX API
    3) MyMemory Translation API
    4) Traductor composicional local por bloques y palabras (100% offline fallback)
    """
    clean = text.strip()
    if not clean:
        return ""
    low = clean.lower()
    norm_no_acc = _strip_accents(low)

    if source_lang == "es" and target_lang == "en":
        if low in SPANISH_TO_ENGLISH_VERBS:
            return SPANISH_TO_ENGLISH_VERBS[low]
        if norm_no_acc in SPANISH_TO_ENGLISH_VERBS:
            return SPANISH_TO_ENGLISH_VERBS[norm_no_acc]
        if norm_no_acc in SPANISH_PHRASE_CHUNKS_ES_EN:
            return SPANISH_PHRASE_CHUNKS_ES_EN[norm_no_acc]
        for en_c, es_c in COMPLEMENTS_PRESETS.items():
            if _strip_accents(es_c.lower()) == norm_no_acc:
                return en_c
    elif source_lang == "en" and target_lang == "es":
        if low in VERBS_DB:
            return VERBS_DB[low]["es_inf"]
        if low in ENGLISH_TO_SPANISH_VERBS_EXTRA:
            return ENGLISH_TO_SPANISH_VERBS_EXTRA[low]
        if clean in COMPLEMENTS_PRESETS:
            return COMPLEMENTS_PRESETS[clean]
        if low in ENGLISH_PHRASE_CHUNKS_EN_ES:
            return ENGLISH_PHRASE_CHUNKS_EN_ES[low]

    # Intento 1: Google Translate GTX
    try:
        url = (
            "https://translate.googleapis.com/translate_a/single?client=gtx"
            f"&sl={source_lang}&tl={target_lang}&dt=t&q={urllib.parse.quote(clean)}"
        )
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=3) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            translated = "".join([part[0] for part in data[0] if part[0]]).strip()
            if translated and _strip_accents(translated.lower()) != norm_no_acc:
                if source_lang == "es" and target_lang == "en":
                    if translated.lower().startswith("to ") and len(translated.split()) == 2:
                        translated = translated[3:].strip()
                return translated
    except Exception:
        pass

    # Intento 2: MyMemory API
    try:
        mm_url = (
            f"https://api.mymemory.translated.net/get?q={urllib.parse.quote(clean)}"
            f"&langpair={source_lang}|{target_lang}"
        )
        req2 = urllib.request.Request(mm_url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req2, timeout=3) as resp2:
            mm_data = json.loads(resp2.read().decode("utf-8"))
            mm_trans = mm_data.get("responseData", {}).get("translatedText", "").strip()
            if mm_trans and _strip_accents(mm_trans.lower()) != norm_no_acc:
                if source_lang == "es" and target_lang == "en":
                    if mm_trans.lower().startswith("to ") and len(mm_trans.split()) == 2:
                        mm_trans = mm_trans[3:].strip()
                return mm_trans
    except Exception:
        pass

    # Intento 3: Motor composicional local infalible (nunca devuelve el texto sin traducir)
    if source_lang == "es" and target_lang == "en":
        return _local_compositional_es_to_en(clean)
    if source_lang == "en" and target_lang == "es":
        return _local_compositional_en_to_es(clean)
    return clean


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
    Pronuncia cada frase N veces con pausas reales de silencio MP3 intercaladas.
    """
    # Frame MP3 silencioso válido (MPEG1 Layer 3, 128kbps, 44100Hz, ~26ms por frame)
    silent_mp3_frame = b"\xff\xfb\x90\x00" + (b"\x00" * 413)
    # ~2.5 segundos de silencio acústico limpio (96 frames)
    silence_block = silent_mp3_frame * 96

    combined = io.BytesIO()
    for sentence in sentences_list:
        clean_s = sentence.strip()
        if not clean_s:
            continue
        tts = gTTS(text=clean_s, lang="en", slow=slow_mode, tld=tld)
        seg_fp = io.BytesIO()
        tts.write_to_fp(seg_fp)
        seg_bytes = seg_fp.getvalue()

        for _ in range(repeat_each):
            combined.write(seg_bytes)
            combined.write(silence_block)

    combined.seek(0)
    return combined.read()


if "vocab_batch" not in st.session_state:
    # Al ingresar a la aplicación, selecciona aleatoriamente un lote fresco de palabras
    st.session_state.vocab_batch = random.sample(range(len(VOCABULARY_BANK)), 6)
if "video_batch" not in st.session_state:
    # Asegurar que al menos el primer video sea uno de English by Deivid (ej. índice 0)
    deivid_indices = [i for i, v in enumerate(SHADOWING_VIDEOS) if v["channel"] == "English by Deivid"]
    other_indices = [i for i, v in enumerate(SHADOWING_VIDEOS) if v["channel"] != "English by Deivid"]
    chosen_initial = [deivid_indices[0]] + random.sample(other_indices, 2)
    st.session_state.video_batch = chosen_initial
if "selected_video_idx" not in st.session_state:
    st.session_state.selected_video_idx = st.session_state.video_batch[0]

# ==============================================================================
# INTERFAZ DE USUARIO (SIDEBAR Y TABS)
# ==============================================================================
stats = load_stats()
shadowing_map = load_shadowing_progress()
saved_sentences = load_sentence_history()
exam_history = load_exam_results()
vocab_mastered_map = load_vocab_mastered()

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
    st.subheader("🗄️ Progreso Guardado")
    col_s1, col_s2 = st.columns(2)
    col_s1.metric("Aciertos", stats["score"])
    completed_lessons_count = len([k for k in shadowing_map if k.startswith("sh_")])
    col_s2.metric("Shadowing", f"{completed_lessons_count}/{len(SHADOWING_LESSONS)}")

    col_s3, col_s4 = st.columns(2)
    col_s3.metric("Exámenes", len(exam_history))
    col_s4.metric("Vocabulario", f"{len(vocab_mastered_map)}/{len(VOCABULARY_BANK)}")

    if stats["attempts"] > 0:
        acc = int((stats["score"] / stats["attempts"]) * 100)
        st.progress(acc / 100, text=f"Precisión Práctica: {acc}%")

    if st.button("🗑️ Reiniciar base de datos", use_container_width=True):
        reset_all_db()
        st.session_state.active_exam = None
        st.session_state.last_exam_report = None
        st.toast("Progreso reiniciado.")
        st.rerun()

st.title("🧩 Matriz Gramatical, Shadowing y Evaluación", anchor=False)
st.markdown(
    "Construye oraciones combinando bloques gramaticales, entrénalas en el **Estudio de Shadowing (A1–B2)**, "
    "presenta **Exámenes Calificados** y conserva todo tu historial."
)

with st.expander("🔊 Opciones rápidas de voz (Velocidad y Acento)", expanded=False):
    q_aud1, q_aud2 = st.columns(2)
    with q_aud1:
        quick_slow = st.toggle("🐢 Velocidad lenta / didáctica (0.75x)", value=is_slow, key="mobile_quick_slow")
        if quick_slow != is_slow:
            is_slow = quick_slow
    with q_aud2:
        st.caption(f"Acento activo: **{accent_choice[0]}** *(cámbialo en el menú lateral `>`)*")


tab_matrix, tab_vocab, tab_shadowing, tab_exams, tab_practice, tab_progress_db, tab_reference = st.tabs(
    [
        "🎛️ Matriz Interactiva",
        "🖼️ Vocabulario Visual",
        "🎧 Estudio de Shadowing (A1–B2)",
        "📝 Exámenes Calificados",
        "🎯 Práctica Rápida",
        "🗄️ Historial y Progreso",
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
        st.markdown("<div class='desktop-spacer' style='height: 36px;'></div>", unsafe_allow_html=True)
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
            "Modal: would",
            "Modal: shall",
            "Semimodal: have to",
            "Semimodal: need to",
            "Semimodal: used to",
            "Semimodal: be able to",
            "To Be (Presente: am/is/are)",
            "To Be (Pasado: was/were)",
            "Have (Presente Simple: have/has)",
        ]
        struct_val = st.selectbox("Estructura gramatical:", options=structures, index=3)

    with c3:
        st.markdown("**3️⃣ Acción (Verbo base)**")
        verb_mode = st.toggle("Escribir verbo libre", key="t_verb")
        is_to_be_or_have = struct_val.startswith(("To Be", "Have"))
        action_es_custom = ""
        if verb_mode:
            if "free_verb_en" not in st.session_state:
                st.session_state.free_verb_en = "" if is_to_be_or_have else "make"
            if "custom_verb_es" not in st.session_state:
                st.session_state.custom_verb_es = "" if is_to_be_or_have else "hacer"

            def _sync_verb_from_en():
                en_w = st.session_state.free_verb_en.strip().lower()
                if en_w.startswith("to ") and len(en_w) > 3:
                    en_w = en_w[3:].strip()
                if en_w:
                    # Si el usuario escribió una palabra en español en la casilla de inglés, la detectamos y traducimos
                    if en_w in SPANISH_TO_ENGLISH_VERBS and en_w not in VERBS_DB:
                        st.session_state.custom_verb_es = en_w
                        st.session_state.free_verb_en = SPANISH_TO_ENGLISH_VERBS[en_w]
                    else:
                        st.session_state.custom_verb_es = auto_translate_text(en_w, "en", "es").lower()

            def _sync_verb_from_es():
                es_w = st.session_state.custom_verb_es.strip().lower()
                if es_w:
                    en_tr = auto_translate_text(es_w, "es", "en").lower()
                    if en_tr.startswith("to ") and len(en_tr) > 3:
                        en_tr = en_tr[3:].strip()
                    st.session_state.free_verb_en = en_tr

            action_val = st.text_input(
                "Verbo en forma base (en inglés):",
                key="free_verb_en",
                on_change=_sync_verb_from_en,
                placeholder="Ej: make, speak, swim (o escribe abajo en español)",
            )
            action_es_custom = st.text_input(
                "Traducción al español del verbo (escribe aquí si no lo sabes en inglés):",
                key="custom_verb_es",
                on_change=_sync_verb_from_es,
                placeholder="Ej: hablar, nadar, hacer...",
            )

            # Respaldo inmediato si el usuario borró la casilla de inglés o si ambas quedaron en español
            if not action_val.strip() and action_es_custom.strip():
                action_val = auto_translate_text(action_es_custom.strip(), "es", "en").lower()
                if action_val.startswith("to ") and len(action_val) > 3:
                    action_val = action_val[3:].strip()
            elif action_val.strip() and not action_es_custom.strip():
                action_es_custom = auto_translate_text(action_val.strip(), "en", "es").lower()
            elif action_val.strip().lower() == action_es_custom.strip().lower() and looks_like_spanish_text(action_es_custom):
                action_val = auto_translate_text(action_es_custom.strip(), "es", "en").lower()

            if action_val.strip():
                st.caption(f"🔄 **En la Matriz:** `{action_val.strip()}` ⇄ **Español:** *{action_es_custom.strip()}*")
        else:
            verb_options = ["(ninguno - para To Be / Have)"] + list(VERBS_DB.keys())
            default_v_idx = 0 if is_to_be_or_have else 3
            sel_v = st.selectbox("Selecciona acción:", options=verb_options, index=default_v_idx)
            action_val = "" if sel_v.startswith("(") else sel_v

    with c4:
        st.markdown("**4️⃣ Complemento**")
        comp_mode = st.toggle("Escribir complemento libre", key="t_comp")
        comp_es_custom = ""
        if comp_mode:
            if "free_comp_en" not in st.session_state:
                st.session_state.free_comp_en = "every morning"
            if "custom_comp_es" not in st.session_state:
                st.session_state.custom_comp_es = "todas las mañanas"

            def _sync_comp_from_en():
                en_c = st.session_state.free_comp_en.strip()
                if en_c:
                    if looks_like_spanish_text(en_c):
                        st.session_state.custom_comp_es = en_c
                        st.session_state.free_comp_en = auto_translate_text(en_c, "es", "en")
                    else:
                        st.session_state.custom_comp_es = auto_translate_text(en_c, "en", "es").lower()

            def _sync_comp_from_es():
                es_c = st.session_state.custom_comp_es.strip()
                if es_c:
                    st.session_state.free_comp_en = auto_translate_text(es_c, "es", "en")

            # Auto-reparación si ambas casillas quedaron iguales en español por un intento anterior
            if (
                st.session_state.free_comp_en.strip()
                and st.session_state.free_comp_en.strip().lower() == st.session_state.custom_comp_es.strip().lower()
                and looks_like_spanish_text(st.session_state.custom_comp_es)
            ):
                st.session_state.free_comp_en = auto_translate_text(st.session_state.custom_comp_es.strip(), "es", "en")

            comp_val = st.text_input(
                "Complemento (en inglés):",
                key="free_comp_en",
                on_change=_sync_comp_from_en,
                placeholder="Ej: some days in the morning, in Cali",
            )
            comp_es_custom = st.text_input(
                "Traducción del complemento (escribe aquí si no lo sabes en inglés):",
                key="custom_comp_es",
                on_change=_sync_comp_from_es,
                placeholder="Ej: algunos días en la mañana, en la oficina...",
            )

            if not comp_val.strip() and comp_es_custom.strip():
                comp_val = auto_translate_text(comp_es_custom.strip(), "es", "en")
            elif comp_val.strip() and not comp_es_custom.strip():
                comp_es_custom = auto_translate_text(comp_val.strip(), "en", "es").lower()
            elif comp_val.strip().lower() == comp_es_custom.strip().lower() and looks_like_spanish_text(comp_es_custom):
                comp_val = auto_translate_text(comp_es_custom.strip(), "es", "en")

            if comp_val.strip():
                st.caption(f"🔄 **En la Matriz:** `{comp_val.strip()}` ⇄ **Español:** *{comp_es_custom.strip()}*")
        else:
            comp_val = st.selectbox("Selecciona complemento:", options=list(COMPLEMENTS_PRESETS.keys()), index=0)

    # Panel guía en vivo al seleccionar Verbo / Modal / Tiempo
    ped = STRUCTURE_PEDAGOGY.get(struct_val)
    if ped:
        st.markdown(
            f"""
            <div style="background: linear-gradient(135deg, #eff6ff 0%, #f0f9ff 100%); border: 1px solid #bfdbfe; border-left: 5px solid #2563eb; border-radius: 10px; padding: 14px 18px; margin: 10px 0 14px 0; box-shadow: 0 2px 6px rgba(37, 99, 235, 0.06);">
                <div style="font-size: 1.05rem; font-weight: 700; color: #1e3a8a; margin-bottom: 10px;">
                    🧭 Guía de Uso y Significado: <code style="background: #dbeafe; color: #1e40af; padding: 2px 8px; border-radius: 5px; font-weight: 700;">{struct_val}</code>
                </div>
                <div style="display: flex; flex-wrap: wrap; gap: 16px; color: #1e293b; font-size: 0.94rem; line-height: 1.5;">
                    <div style="flex: 1 1 320px;">
                        <div style="margin-bottom: 6px;">• <strong>🎯 Qué expresa en la frase:</strong> {ped['meaning']}</div>
                        <div style="margin-bottom: 6px;">• <strong>🗣️ Cuándo elegirla:</strong> {ped['when_to_use']}</div>
                        <div>• <strong>🇪🇸 Cómo se traduce:</strong> {ped['translation_guide']}</div>
                    </div>
                    <div style="flex: 1 1 320px;">
                        <div style="margin-bottom: 6px;">• <strong>⚖️ Regla / Diferencia clave:</strong> {ped['contrast']}</div>
                        <div>• <strong>💡 Consejo para una frase real:</strong> {ped['coherent_tip']}</div>
                    </div>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    result = build_sentences(
        subject_val,
        struct_val,
        action_val,
        comp_val,
        action_es_custom=action_es_custom if verb_mode else "",
        comp_es_custom=comp_es_custom if comp_mode else "",
    )

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
        st.info(f"**Traducción al español:**\n\n{result['spanish']}")
        if st.button("💾 Guardar oración", use_container_width=True):
            inserted = save_sentence_db(
                result["affirmative"],
                result["negative"],
                result["interrogative"],
                result["spanish"],
                struct_val,
            )
            if inserted:
                st.toast("✅ Oración guardada correctamente.")
                st.rerun()
            else:
                st.toast("ℹ️ Esta oración ya estaba guardada en tu base de datos.")

    with c_gram:
        st.markdown("#### 🧠 Análisis y Reglas Gramaticales")
        for note in result["notes"]:
            st.markdown(f"- {note}")

# ------------------------------------------------------------------------------
# TAB VOCABULARIO VISUAL (ROTACIÓN ALEATORIA AL INGRESAR + IMAGEN + AUDIO + SQLITE)
# ------------------------------------------------------------------------------
with tab_vocab:
    st.subheader("🖼️ Laboratorio de Vocabulario Visual (Rotación Automática)")
    st.write(
        "Cada vez que ingresas a la aplicación o presionas **🎲 Traer nuevas palabras aleatorias**, "
        "el sistema selecciona un grupo diferente de vocabulario con su **ilustración visual**, **pronunciación figurada y fonética (IPA)**, "
        "**audio nativo**, **traducción al español** y **oración de ejemplo**."
    )

    v_ctrl1, v_ctrl2, v_ctrl3, v_ctrl4 = st.columns([1.4, 1, 1.1, 1.3], vertical_alignment="bottom")
    with v_ctrl1:
        vocab_categories = ["Todas las categorías"] + sorted(list({w["cat"] for w in VOCABULARY_BANK}))
        sel_vocab_cat = st.selectbox("Filtrar por categoría temática:", options=vocab_categories)
    with v_ctrl2:
        batch_size = st.selectbox("Palabras en pantalla:", options=[4, 6, 8, 12], index=1)
    with v_ctrl3:
        hide_mastered = st.toggle("Ocultar ya aprendidas", value=False)
    with v_ctrl4:
        if st.button("🎲 Traer nuevas palabras aleatorias", type="primary", use_container_width=True):
            candidate_indices = [
                i for i, w in enumerate(VOCABULARY_BANK)
                if (sel_vocab_cat == "Todas las categorías" or w["cat"] == sel_vocab_cat)
                and (not hide_mastered or w["en"] not in vocab_mastered_map)
            ]
            if not candidate_indices:
                candidate_indices = list(range(len(VOCABULARY_BANK)))
            st.session_state.vocab_batch = random.sample(candidate_indices, min(batch_size, len(candidate_indices)))
            st.rerun()

    # Filtrar el lote actual según la categoría o tamaño elegido
    valid_pool = [
        i for i, w in enumerate(VOCABULARY_BANK)
        if (sel_vocab_cat == "Todas las categorías" or w["cat"] == sel_vocab_cat)
        and (not hide_mastered or w["en"] not in vocab_mastered_map)
    ]

    if not valid_pool:
        st.success("🎉 ¡Ya marcaste como aprendidas todas las palabras de esta categoría! Desactiva 'Ocultar ya aprendidas' para repasarlas.")
    else:
        # Ajustar lote si cambió el filtro o el número de tarjetas
        current_indices = [i for i in st.session_state.vocab_batch if i in valid_pool]
        if len(current_indices) != min(batch_size, len(valid_pool)):
            current_indices = random.sample(valid_pool, min(batch_size, len(valid_pool)))
            st.session_state.vocab_batch = current_indices

        st.divider()
        grid_cols = st.columns(2)
        for pos, vocab_idx in enumerate(current_indices):
            item = VOCABULARY_BANK[vocab_idx]
            is_learned = item["en"] in vocab_mastered_map
            with grid_cols[pos % 2]:
                st.markdown(render_vocab_visual_card(item, is_learned), unsafe_allow_html=True)
                b_col1, b_col2, b_col3 = st.columns([1.1, 1.2, 1.1])
                with b_col1:
                    if st.button(f"🔊 Palabra", key=f"voc_w_{vocab_idx}", use_container_width=True):
                        st.audio(synthesize_speech(item["en"], is_slow, selected_tld), format="audio/mp3", autoplay=True)
                with b_col2:
                    if st.button(f"🗣️ Ejemplo", key=f"voc_ex_{vocab_idx}", use_container_width=True):
                        st.audio(synthesize_speech(item["example_en"], is_slow, selected_tld), format="audio/mp3", autoplay=True)
                with b_col3:
                    if is_learned:
                        if st.button("↩️ Repasar", key=f"voc_unm_{vocab_idx}", use_container_width=True):
                            unmark_vocab_mastered_db(item["en"])
                            st.rerun()
                    else:
                        if st.button("✅ Aprendida", key=f"voc_mst_{vocab_idx}", use_container_width=True):
                            mark_vocab_mastered_db(item["en"], item["es"], item["cat"])
                            st.toast(f"✅ '{item['en']}' guardada como aprendida.")
                            st.rerun()

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
            "🎬 Videos con Subtítulos CC (~10 min)",
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
            col_loop1, col_loop2, col_loop3 = st.columns([1, 1.3, 1.3], vertical_alignment="bottom")
            with col_loop1:
                reps = st.selectbox("Repeticiones por turno:", options=[1, 2, 3], index=1)
            with col_loop2:
                play_fluid = st.button("▶️ Escuchar Diálogo Fluido (Sin pausas)", use_container_width=True)
            with col_loop3:
                play_loop = st.button("🔁 Pista Shadowing (Con pausas para repetir)", type="primary", use_container_width=True)

            if play_fluid:
                fluid_audio = synthesize_speech(" ".join(active_sentences), is_slow, selected_tld)
                st.audio(fluid_audio, format="audio/mp3", autoplay=True)
            if play_loop:
                loop_audio = synthesize_shadowing_loop(tuple(active_sentences), is_slow, selected_tld, reps)
                st.audio(loop_audio, format="audio/mp3", autoplay=True)

            st.markdown("<br>", unsafe_allow_html=True)
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

    elif source_mode == "🎬 Videos con Subtítulos CC (~10 min)":
        st.markdown("### 🎬 Videos de Shadowing con Subtítulos en Inglés (6 a 12 min)")
        st.write(
            "Entrena con videos reales en inglés de ~10 minutos con **subtítulos en inglés (`cc_load_policy=1`)** activados automáticamente. "
            "Presiona **🔄 Actualizar / Traer otros videos diferentes** cuando quieras rotar la selección."
        )

        v_f1, v_f2, v_f3 = st.columns([1.3, 1.3, 1.4], vertical_alignment="bottom")
        with v_f1:
            vid_cats = ["Todas las categorías"] + sorted(list({v["category"] for v in SHADOWING_VIDEOS}))
            sel_vid_cat = st.selectbox("Filtrar por estilo de video:", options=vid_cats)
        with v_f2:
            vid_levels = ["Todos los niveles"] + sorted(list({v["level"] for v in SHADOWING_VIDEOS}))
            sel_vid_lvl = st.selectbox("Filtrar por nivel:", options=vid_levels)
        with v_f3:
            if st.button("🔄 Actualizar / Traer otros videos diferentes", type="primary", use_container_width=True):
                pool_v = [
                    i for i, v in enumerate(SHADOWING_VIDEOS)
                    if (sel_vid_cat == "Todas las categorías" or v["category"] == sel_vid_cat)
                    and (sel_vid_lvl == "Todos los niveles" or v["level"] == sel_vid_lvl)
                ]
                if not pool_v:
                    pool_v = list(range(len(SHADOWING_VIDEOS)))
                others = [i for i in pool_v if i != st.session_state.selected_video_idx]
                chosen_pool = others if len(others) >= 3 else pool_v
                st.session_state.video_batch = random.sample(chosen_pool, min(3, len(chosen_pool)))
                st.session_state.selected_video_idx = st.session_state.video_batch[0]
                st.rerun()

        filtered_vid_indices = [
            i for i, v in enumerate(SHADOWING_VIDEOS)
            if (sel_vid_cat == "Todas las categorías" or v["category"] == sel_vid_cat)
            and (sel_vid_lvl == "Todos los niveles" or v["level"] == sel_vid_lvl)
        ]
        if not filtered_vid_indices:
            st.warning("No hay videos con esa combinación exacta; mostrando todo el catálogo.")
            filtered_vid_indices = list(range(len(SHADOWING_VIDEOS)))

        # Asegurar que el lote actual pertenezca al filtro
        batch_valid = [i for i in st.session_state.video_batch if i in filtered_vid_indices]
        if not batch_valid:
            batch_valid = random.sample(filtered_vid_indices, min(3, len(filtered_vid_indices)))
            st.session_state.video_batch = batch_valid
            st.session_state.selected_video_idx = batch_valid[0]

        st.markdown("#### 🎯 Videos sugeridos en esta tanda (Haz clic en uno para cargarlo):")
        v_cards = st.columns(len(batch_valid))
        for col_i, v_idx in enumerate(batch_valid):
            v_obj = SHADOWING_VIDEOS[v_idx]
            is_active_v = (v_idx == st.session_state.selected_video_idx)
            with v_cards[col_i]:
                border_col = "#2563eb" if is_active_v else "#cbd5e1"
                bg_col = "#eff6ff" if is_active_v else "#ffffff"
                st.markdown(
                    f"""
                    <div style="border:2px solid {border_col}; background:{bg_col}; border-radius:10px; padding:12px 14px; margin-bottom:8px; height:128px; display:flex; flex-direction:column; justify-content:space-between; box-sizing:border-box;">
                        <div>
                            <div style="font-size:0.76rem; font-weight:700; color:#1d4ed8;">⏱️ {v_obj['duration']} • {v_obj['level']}</div>
                            <div style="font-size:0.95rem; font-weight:700; color:#0f172a; margin:6px 0 4px 0; line-height:1.35; max-height:2.7em; overflow:hidden; display:-webkit-box; -webkit-line-clamp:2; -webkit-box-orient:vertical;">{v_obj['title']}</div>
                        </div>
                        <div style="font-size:0.8rem; color:#475569; white-space:nowrap; overflow:hidden; text-overflow:ellipsis;">📺 {v_obj['channel']} | <em>{v_obj['category']}</em></div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )
                btn_lbl = "▶️ Viendo ahora" if is_active_v else "🎬 Seleccionar este video"
                if st.button(btn_lbl, key=f"sel_vid_btn_{v_idx}", use_container_width=True, disabled=is_active_v):
                    st.session_state.selected_video_idx = v_idx
                    st.rerun()

        current_vid = SHADOWING_VIDEOS[st.session_state.selected_video_idx]
        lesson_id = current_vid["id"]
        lesson_title_for_db = f"Video: {current_vid['title']}"

        st.divider()
        vid_col_player, vid_col_info = st.columns([1.8, 1])
        with vid_col_player:
            # Reproductor YouTube embebido con subtítulos en inglés forzados (cc_load_policy=1 & cc_lang_pref=en)
            embed_url = f"https://www.youtube.com/embed/{current_vid['video_id']}?enablejsapi=1&cc_load_policy=1&cc_lang_pref=en&hl=en&rel=0"
            st.markdown(
                f"""
                <div id="yt-player-container" style="position:relative; padding-bottom:56.25%; height:0; overflow:hidden; border-radius:12px; box-shadow:0 4px 12px rgba(0,0,0,0.12); border:1px solid #cbd5e1;">
                    <iframe id="yt-iframe" src="{embed_url}"
                        style="position:absolute; top:0; left:0; width:100%; height:100%; border:0;"
                        allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture; web-share"
                        allowfullscreen>
                    </iframe>
                </div>
                <script>
                // Script para detener el video de YouTube si el usuario cambia de pestaña en Streamlit
                const observer = new MutationObserver(() => {{
                    const iframe = document.getElementById('yt-iframe');
                    if (iframe && iframe.offsetParent === null) {{
                        iframe.contentWindow.postMessage('{{\"event\":\"command\",\"func\":\"pauseVideo\",\"args\":\"\"}}', '*');
                    }}
                }});
                const container = document.getElementById('yt-player-container');
                if (container && container.parentNode) {{
                    observer.observe(container.parentNode, {{ attributes: true, subtree: true, childList: true }});
                }}
                </script>
                """,
                unsafe_allow_html=True,
            )

        with vid_col_info:
            done_v = shadowing_map.get(lesson_id)
            done_badge = f"✅ Practicado {done_v['completed_count']} vez/veces" if done_v else "⏳ Pendiente por registrar"
            st.info(
                f"**🎬 Reproduciendo ahora:**\n\n"
                f"**{current_vid['title']}**\n\n"
                f"- **Canal:** {current_vid['channel']}\n"
                f"- **Duración:** `{current_vid['duration']}` min\n"
                f"- **Nivel:** {current_vid['level']}\n"
                f"- **Estado en BD:** {done_badge}\n\n"
                f"📝 *{current_vid['desc']}*"
            )
            st.markdown(f"🔗 [Abrir video directamente en YouTube]({current_vid['url']})")
            st.caption(
                "💡 **Tip para Subtítulos (CC) y Velocidad:** El reproductor activa automáticamente los subtítulos en inglés (`CC`). "
                "En el ícono de engranaje ⚙️ del video puedes ajustar la velocidad a `0.75x` en las frases rápidas."
            )

        with st.expander("➕ ¿Tienes el enlace de otro video de YouTube en inglés? Pégalo aquí para practicar"):
            custom_yt_url = st.text_input(
                "Pega cualquier URL de YouTube (ej. https://www.youtube.com/watch?v=...):",
                placeholder="https://www.youtube.com/watch?v=o6a9kAswl-s",
            )
            if custom_yt_url.strip():
                yt_match = re.search(r"(?:v=|youtu\.be/|embed/)([A-Za-z0-9_-]{11})", custom_yt_url.strip())
                if yt_match:
                    custom_vid_id = yt_match.group(1)
                    custom_embed = f"https://www.youtube.com/embed/{custom_vid_id}?cc_load_policy=1&cc_lang_pref=en&hl=en&rel=0"
                    st.markdown(
                        f"""
                        <div style="position:relative; padding-bottom:56.25%; height:0; overflow:hidden; border-radius:12px; margin-top:8px;">
                            <iframe src="{custom_embed}"
                                style="position:absolute; top:0; left:0; width:100%; height:100%; border:0;"
                                allowfullscreen>
                            </iframe>
                        </div>
                        """,
                        unsafe_allow_html=True,
                    )
                else:
                    st.warning("No se detectó un ID válido de YouTube en ese enlace.")

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
        st.markdown("**Registro de progreso**")
        if st.button("🏅 Guardar sesión completada", use_container_width=True):
            mark_shadowing_db(lesson_id, lesson_title_for_db)
            st.toast("✅ Progreso de Shadowing guardado.")
            st.rerun()

# ------------------------------------------------------------------------------
# TAB 3: EXÁMENES CALIFICADOS (CON GUARDADO EN SQLITE)
# ------------------------------------------------------------------------------
with tab_exams:
    st.subheader("📝 Exámenes de Evaluación (Gramática, Traducción y Listening)")
    st.write("Configura un examen por nivel o tema, respóndelo completo y guarda tu nota y revisión detallada.")

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

            submitted_exam = st.form_submit_button("✅ Finalizar Examen, Calificar y Guardar", type="primary", use_container_width=True)

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
        st.markdown("### 🏆 Resultado del Examen")

        r1, r2, r3, r4 = st.columns(4)
        r1.metric("Examen ID", f"#{rep['id']}")
        r2.metric("Calificación", f"{rep['percentage']}%")
        r3.metric("Respuestas Correctas", f"{rep['correct']} / {rep['total']}")
        r4.metric("Estado", "APROBADO ✅" if rep["passed"] else "REPASAR ⚠️")

        if rep["passed"]:
            st.success(f"¡Felicitaciones! Aprobaste el examen con **{rep['percentage']}%** y el resultado ya quedó registrado.")
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
    st.markdown("### 📊 Historial de Exámenes Presentados")
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
                st.success(f"🎉 ¡Excelente! Respuesta correcta guardada: **{ch['en']}**")
                audio_ok = synthesize_speech(ch["en"], is_slow, selected_tld)
                st.audio(audio_ok, format="audio/mp3")
            else:
                st.error(f"❌ No coincide exactamente.\n\n- **Tu respuesta:** `{user_ans}`\n- **Forma esperada:** `{ch['en']}`\n- **Regla clave:** {ch['hint']}")

# ------------------------------------------------------------------------------
# TAB 5: HISTORIAL Y PROGRESO SQL
# ------------------------------------------------------------------------------
with tab_progress_db:
    st.subheader("🗄️ Panel General de Progreso")
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
        st.info("Aún no has guardado oraciones. Usa el botón **💾 Guardar oración** en la primera pestaña.")
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
| **Modales Puros** (`can`, `could`, `should`, `must`, `may`, `might`, `will`, `would`, `shall`) | El mismo modal | `Sujeto + Modal + Verbo Base` | `Sujeto + Modal + not + Verbo Base` | `Modal + Sujeto + Verbo Base?` |
| **Semimodal `have to`** (Obligación externa) | `do` / `does` | `Sujeto + have/has to + Verbo Base` | `Sujeto + do/does + not + have to + Verbo Base` | `Do/Does + Sujeto + have to + Verbo Base?` |
| **Semimodal `need to`** (Necesidad) | `do` / `does` | `Sujeto + need/needs to + Verbo Base` | `Sujeto + do/does + not + need to + Verbo Base` | `Do/Does + Sujeto + need to + Verbo Base?` |
| **Semimodal `used to`** (Hábito pasado) | `did` | `Sujeto + used to + Verbo Base` | `Sujeto + did not use to + Verbo Base` | `Did + Sujeto + use to + Verbo Base?` |
| **Semimodal `be able to`** (Capacidad) | `am` / `is` / `are` | `Sujeto + am/is/are able to + Verbo Base` | `Sujeto + am/is/are not able to + Verbo Base` | `Am/Is/Are + Sujeto + able to + Verbo Base?` |
| **To Be (Presente)** | `am` / `is` / `are` | `Sujeto + am/is/are + Comp.` | `Sujeto + am/is/are + not + Comp.` | `Am/Is/Are + Sujeto + Comp.?` |
| **To Be (Pasado)** | `was` / `were` | `Sujeto + was/were + Comp.` | `Sujeto + was/were + not + Comp.` | `Was/Were + Sujeto + Comp.?` |
| **Presente Simple** | `do` / `does` | `Sujeto + Verbo (-s en He/She/It)` | `Sujeto + do/does + not + Verbo Base` | `Do/Does + Sujeto + Verbo Base?` |
| **Pasado Simple** | `did` | `Sujeto + Verbo en Pasado` | `Sujeto + did + not + Verbo Base` | `Did + Sujeto + Verbo Base?` |
| **Futuro Simple** | `will` | `Sujeto + will + Verbo Base` | `Sujeto + will + not + Verbo Base` | `Will + Sujeto + Verbo Base?` |
| **Have (Posesión)** | `have` / `has` (`do`/`does`) | `Sujeto + have/has + Objeto` | `Sujeto + do/does + not + have + Objeto` | `Do/Does + Sujeto + have + Objeto?` |
        """
    )

    st.divider()
    st.subheader("⚖️ Guía Comparativa: `must` vs `have to` (Caso Clave)")
    st.markdown(
        "Aunque ambos expresan obligación (*deber / tener que*), cambian radicalmente de significado al pasar a **negativa** y se comportan distinto gramaticalmente:"
    )
    comp_c1, comp_c2 = st.columns(2)
    with comp_c1:
        st.info(
            "**1. `must` (Modal Puro — Obligación interna o norma estricta)**\n\n"
            "- **Afirmativa:** *She **must** study today.* (Ella debe estudiar hoy — convicción o regla).\n"
            "- **Negativa (`must not` / `mustn't`):** *She **must not** smoke here.* (**Prohibición estricta**: está prohibido).\n"
            "- **Gramática:** No lleva `-s` en 3.ª persona y no usa `do/does`."
        )
    with comp_c2:
        st.success(
            "**2. `have to` (Semimodal — Obligación externa o requisito)**\n\n"
            "- **Afirmativa:** *She **has to** work tomorrow.* (Ella tiene que trabajar mañana — horario/jefe).\n"
            "- **Negativa (`doesn't / don't have to`):** *She **does not have to** work tomorrow.* (**Opcionalidad**: no es necesario, puede descansar).\n"
            "- **Gramática:** Sí cambia a `has to` con *He/She/It* y usa `do/does/did`."
        )