import streamlit as st
import pandas as pd
from datetime import datetime, date
import plotly.express as px
import gspread
from google.oauth2.service_account import Credentials

st.set_page_config(
    page_title="Finanze Personali",
    layout="wide",
    page_icon="💰"
)

st.title("💰 Gestione Finanze Personali")
st.markdown("---")

# ---------- CONNESSIONE GOOGLE SHEETS ----------

@st.cache_resource
def init_gsheets():
    """Inizializza connessione a Google Sheets"""
    scope = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive"
    ]
    creds = Credentials.from_service_account_info(
        st.secrets["connections"]["gsheets"],
        scopes=scope
    )
    gc = gspread.authorize(creds)
    spreadsheet = gc.open_by_key(st.secrets["config"]["SPREADSHEET_ID"])
    return spreadsheet

spreadsheet = init_gsheets()

st.sidebar.header("📁 Carica estratto conto")

uploaded_file = st.sidebar.file_uploader(
    "Scegli il file CSV dell'estratto conto",
    type="csv"
)

st.sidebar.markdown("—")
st.sidebar.caption("Supporto Hype + altre banche (mappatura colonne manuale).")


# ---------- UTILITÀ CARICAMENTO CSV ----------

def load_csv(file) -> pd.DataFrame:
    """Carica il CSV provando separatori ; e ,"""
    try:
        df = pd.read_csv(file, sep=";")
        if df.shape[1] == 1:
            file.seek(0)
            df = pd.read_csv(file, sep=",")
    except Exception:
        file.seek(0)
        df = pd.read_csv(file)
    return df


# ---------- REGOLE DI CATEGORIZZAZIONE ----------

FIXED_KEYWORDS = {
    "Affitto / mutuo": ["affitto", "rent", "mutuo", "mortgage"],
    "Utenze casa": ["enel", "a2a", "hera", "iren", "gas", "luce", "energia", "acqua"],
    "Abbonamenti ricorrenti": [
        "netflix", "spotify", "prime video", "now tv", "disney",
        "abbonamento", "subscription", "telefono", "mobile", "internet", "fibra"
    ],
    "Rate & debiti": ["prestito", "loan", "finanziamento", "rate", "credito al consumo"],
}

VARIABLE_KEYWORDS = {
    "Cene & aperitivi": [
        "ristorante", "restaurant", "trattoria", "osteria", "pizzeria",
        "pub", "bar", "caffe", "caffè", "aperitivo", "apericena"
    ],
    "Spesa supermercato": [
        "esselunga", "coop", "iper", "ipercoop", "conad", "carrefour",
        "lidl", "md", "pam", "aldi", "eurospin"
    ],
    "Trasporti & mobilità": [
        "atm", "trenitalia", "italo", "uber", "bolt", "taxi",
        "carburante", "benzina", "diesel", "telepass",
        "enjoy", "share now", "sharenow", "free now", "freenow"
    ],
    "Sport & benessere": [
        "palestra", "gym", "fitness", "decathlon", "sport center",
        "yoga", "pilates", "spa", "wellness"
    ],
    "Salute": [
        "farmacia", "pharmacy", "medico", "analisi", "ticket",
        "dentista", "ottico", "occhiali", "visita", "esame"
    ],
    "Tabacco & vizi": [
        "tabacchi", "tabaccheria", "sigarette", "tobacco",
        "svapo", "vape", "sisal", "lotto", "scommessa"
    ],
    "Shopping & extra": [
        "amazon", "zalando", "zara", "h&m", "hm",
        "mediaworld", "unieuro", "ikea"
    ],
    "Cultura & formazione": [
        "libreria", "feltrinelli", "ibs", "corso", "master", "udemy",
        "coursera", "libro", "libri"
    ],
    "Casa & arredo": [
        "brico", "leroy merlin", "obi", "ikea", "casaforte", "arredo"
    ],
    "Animali": [
        "zooplus", "arcaplanet", "pet shop", "toelettatura"
    ],
    "Viaggi": [
        "booking.com", "airbnb", "hotel", "ryanair", "easyjet", "wizzair"
    ],
    "Regali": [
        "regalo", "gift", "fiori", "florist"
    ],
}

SAVINGS_INVEST_KEYWORDS = {
    "Risparmio conto / deposito": [
        "conto deposito", "risparmio", "saving", "savings"
    ],
    "Investimenti azioni/ETF": [
        "degiro", "etoro", "revolut trading", "trade republic",
        "fineco", "directa", "interactive brokers", "broker"
    ],
    "Crypto & speculativi": [
        "binance", "coinbase", "kraken", "crypto.com", "bitpanda"
    ],
    "Altri investimenti": [
        "polizza", "assicurazione vita", "gestione patrimoniale"
    ],
}

INCOME_KEYWORDS = {
    "Stipendio & lavoro": ["stipendio", "salary", "paga", "retribuzione", "busta paga"],
    "Rimborsi & rientri": ["rimborso", "refund", "rimborso spese", "chargeback"],
    "Entrate passive": ["interessi", "dividendo", "royalty", "cedola"],
}


def normalize_text(s: str) -> str:
    if not isinstance(s, str):
        s = str(s)
    return s.lower()


def normalize_merchant(desc: str) -> str:
    txt = normalize_text(desc)
    remove_tokens = [
        "pagamento pos", "pagamento carta", "acquisto carta",
        "operazione pos", "contactless", "e-commerce", "ecommerce"
    ]
    for t in remove_tokens:
        txt = txt.replace(t, " ")
    return " ".join(txt.split())


def match_keywords(description: str, rules: dict) -> str | None:
    desc = normalize_text(description)
    for category, words in rules.items():
        for w in words:
            if w in desc:
                return category
    return None


def categorize_row(row: pd.Series) -> pd.Series:
    desc = row["description"]
    amount = row["amount"] or 0.0

    row["normalized_merchant"] = normalize_merchant(desc)

    if amount > 0:
        sub = match_keywords(desc, INCOME_KEYWORDS)
        row["macro_category"] = "Entrata"
        row["subcategory"] = sub if sub else "Entrate varie"
        return row

    sub_save = match_keywords(desc, SAVINGS_INVEST_KEYWORDS)
    if sub_save:
        row["macro_category"] = "Risparmi & investimenti"
        row["subcategory"] = sub_save
        return row

    sub_fixed = match_keywords(desc, FIXED_KEYWORDS)
    if sub_fixed:
        row["macro_category"] = "Fisso"
        row["subcategory"] = sub_fixed
        return row

    sub_var = match_keywords(desc, VARIABLE_KEYWORDS)
    if sub_var:
        row["macro_category"] = "Variabile"
        row["subcategory"] = sub_var
        return row

    row["macro_category"] = "Variabile"
    row["subcategory"] = "Altro variabile"
    return row


def build_internal_df(
    df_raw: pd.DataFrame,
    col_date: str,
    col_desc: str,
    col_amount: str,
    col_name: str | None = None,
    col_type: str | None = None,
    col_iban: str | None = None
) -> pd.DataFrame:
    df = df_raw.copy()

    df["date"] = pd.to_datetime(df[col_date], errors="coerce", dayfirst=True)

    if col_name and col_name in df.columns:
        df["description"] = (
            df[col_name].astype(str).fillna("") + " - " + df[col_desc].astype(str).fillna("")
        ).str.strip(" -")
    else:
        df["description"] = df[col_desc].astype(str)

    raw_amount = df[col_amount].astype(str).str.strip()
    raw_amount = (
        raw_amount
        .str.replace("€", "", regex=False)
        .str.replace("\u20ac", "", regex=False)
        .str.replace(" ", "", regex=False)
    )

    def parse_amount(x: str) -> float | None:
        if x is None or x == "" or x.lower() == "nan":
            return None
        if "," in x and x.rfind(",") > x.rfind("."):
            x = x.replace(".", "").replace(",", ".")
        elif "." in x and x.rfind(".") > x.rfind(","):
            x = x.replace(",", "")
        try:
            return float(x)
        except ValueError:
            return None

    df["amount"] = raw_amount.apply(parse_amount)

    if col_iban and col_iban in df.columns:
        df["account"] = df[col_iban].astype(str)
    else:
        df["account"] = "Conto principale"

    if col_type and col_type in df.columns:
        df["bank_category"] = df[col_type].astype(str)
    else:
        df["bank_category"] = ""

    df["direction"] = df["amount"].apply(
        lambda x: "Entrata" if x is not None and x > 0 else "Uscita"
    )

    df["macro_category"] = ""
    df["subcategory"] = ""
    df["normalized_merchant"] = ""

    df = df.sort_values("date")

    cols = [
        "date",
        "description",
        "amount",
        "account",
        "bank_category",
        "direction",
        "macro_category",
        "subcategory",
        "normalized_merchant",
    ]
    return df[cols]


def save_to_gsheets(df_categorized: pd.DataFrame):
    """Salva i dati nel Google Sheet"""
    try:
        general_sheet = spreadsheet.worksheet("Generale")
        
        # Prepara i dati per il salvataggio
        rows_to_save = []
        for _, row in df_categorized.iterrows():
            rows_to_save.append([
                row["date"].strftime("%d/%m/%Y") if pd.notnull(row["date"]) else "",
                row["description"],
                f"{row['amount']:.2f}" if pd.notnull(row["amount"]) else "",
                row["account"],
                row["direction"],
                row["macro_category"],
                row["subcategory"],
                row["normalized_merchant"],
            ])
        
        # Aggiungi le righe al foglio
        if rows_to_save:
            general_sheet.append_rows(rows_to_save)
            st.success(f"✅ {len(rows_to_save)} transazioni salvate nel Google Sheet!")
    except Exception as e:
        st.error(f"❌ Errore nel salvataggio: {e}")


# ---------- UI PRINCIPALE ----------

if uploaded_file is not None:
    df_raw = load_csv(uploaded_file)

    st.subheader("📄 Anteprima CSV originale")
    st.dataframe(df_raw.head(20), use_container_width=True)

    st.markdown("### 🧩 Mappa le colonne del tuo estratto conto")

    columns = df_raw.columns.tolist()

    def suggest(col_names, keywords):
        for k in keywords:
            for c in col_names:
                if k.lower() in c.lower():
                    return c
        return None

    default_date = suggest(columns, ["Data operazione", "Data", "date"])
    default_desc = suggest(columns, ["Descrizione", "Causale", "Description"])
    default_amount = suggest(columns, ["Importo", "Amount", "Valore"])
    default_name = suggest(columns, ["Nome", "Name", "Beneficiario", "Controparte"])
    default_type = suggest(columns, ["Tipologia", "Tipo", "Type"])
    default_iban = suggest(columns, ["Iban", "IBAN", "Account"])

    col1, col2, col3 = st.columns(3)
    with col1:
        col_date = st.selectbox(
            "Colonna DATA operazione",
            options=columns,
            index=columns.index(default_date) if default_date in columns else 0,
        )
        col_amount = st.selectbox(
            "Colonna IMPORTO",
            options=columns,
            index=columns.index(default_amount) if default_amount in columns else 0,
        )
    with col2:
        col_desc = st.selectbox(
            "Colonna DESCRIZIONE",
            options=columns,
            index=columns.index(default_desc) if default_desc in columns else 0,
        )
        col_name = st.selectbox(
            "Colonna NOME / merchant (opzionale)",
            options=["(nessuna)"] + columns,
            index=(columns.index(default_name) + 1) if default_name in columns else 0,
        )
    with col3:
        col_type = st.selectbox(
            "Colonna TIPOLOGIA (opzionale)",
            options=["(nessuna)"] + columns,
            index=(columns.index(default_type) + 1) if default_type in columns else 0,
        )
        col_iban = st.selectbox(
            "Colonna IBAN / conto (opzionale)",
            options=["(nessuna)"] + columns,
            index=(columns.index(default_iban) + 1
