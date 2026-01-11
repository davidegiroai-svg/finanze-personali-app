import streamlit as st
import pandas as pd
from datetime import datetime, date
import plotly.express as px
import google.generativeai as genai
import json

# ---------------------------------------------------------
# Configurazione pagina
# ---------------------------------------------------------
st.set_page_config(page_title="Finanze Personali", layout="wide", page_icon="💰")
st.title("💰 Gestione Finanze Personali")
st.markdown("---")

# ---------------------------------------------------------
# Inizializzazione Gemini
# ---------------------------------------------------------
@st.cache_resource
def init_gemini():
    try:
        genai.configure(api_key=st.secrets["gemini"]["api_key"])
        model = genai.GenerativeModel(st.secrets["gemini"]["model"])
        return model
    except Exception as e:
        st.warning(f"⚠️ AI non disponibile: {e}")
        return None

gemini_model = init_gemini()

# ---------------------------------------------------------
# Sidebar: upload + opzioni
# ---------------------------------------------------------
st.sidebar.header("📁 Carica estratto conto")
uploaded_file = st.sidebar.file_uploader("Scegli il file CSV dell'estratto conto", type="csv")
st.sidebar.markdown("—")
st.sidebar.caption("Supporto Hype + altre banche (mappatura colonne manuale).")

st.sidebar.markdown("### 🤖 Intelligenza Artificiale")
use_ai = st.sidebar.checkbox("Usa AI per riclassificare 'Altro variabile'", value=True)

# ---------------------------------------------------------
# Funzioni di utilità
# ---------------------------------------------------------
def load_csv(file):
    try:
        df = pd.read_csv(file, sep=";")
        if df.shape[1] == 1:
            file.seek(0)
            df = pd.read_csv(file, sep=",")
    except Exception:
        file.seek(0)
        df = pd.read_csv(file)
    return df

FIXED_KEYWORDS = {
    "Affitto / mutuo": ["affitto", "rent", "mutuo", "mortgage", "ferrari giuliana"],
    "Utenze casa": ["enel", "a2a", "hera", "iren", "gas", "luce", "energia", "acqua"],
    "Abbonamenti ricorrenti": [
        "netflix", "spotify", "prime video", "now tv", "disney",
        "abbonamento", "subscription", "telefono", "mobile", "internet", "fibra",
        "iliad", "hype plus", "canone"
    ],
    "Rate & debiti": ["prestito", "loan", "finanziamento", "rate", "credito al consumo"],
}

VARIABLE_KEYWORDS = {
    "Cene & aperitivi": [
        "ristorante", "restaurant", "trattoria", "osteria", "pizzeria",
        "pub", "bar", "caffe", "caffè", "aperitivo", "apericena", "kebab"
    ],
    "Spesa supermercato": [
        "esselunga", "coop", "iper", "ipercoop", "conad", "carrefour",
        "lidl", "md", "pam", "aldi", "eurospin", "eurospar", "bennet", "mercato"
    ],
    "Trasporti & mobilità": [
        "atm", "trenitalia", "italo", "uber", "bolt", "taxi",
        "carburante", "benzina", "diesel", "telepass", "enjoy",
        "share now", "sharenow", "free now", "freenow", "tper", "ridemovi", "buffet"
    ],
    "Sport & benessere": [
        "palestra", "gym", "fitness", "decathlon", "sport center",
        "yoga", "pilates", "spa", "wellness"
    ],
    "Salute": [
        "farmacia", "pharmacy", "medico", "analisi", "ticket",
        "dentista", "ottico", "occhiali", "visita", "esame", "unobravo"
    ],
    "Tabacco & vizi": [
        "tabacchi", "tabaccheria", "sigarette", "tobacco",
        "svapo", "vape", "sisal", "lotto", "scommessa", "palabingo"
    ],
    "Shopping & extra": [
        "amazon", "zalando", "zara", "h&m", "hm", "mediaworld",
        "unieuro", "ikea", "temu"
    ],
    "Cultura & formazione": [
        "libreria", "feltrinelli", "ibs", "corso", "master",
        "udemy", "coursera", "libro", "libri", "cinema"
    ],
    "Casa & arredo": [
        "brico", "leroy merlin", "obi", "ikea", "casaforte", "arredo", "risparmio casa"
    ],
    "Animali": [
        "zooplus", "arcaplanet", "pet shop", "toelettatura"
    ],
    "Viaggi": [
        "booking.com", "airbnb", "hotel", "ryanair", "easyjet", "wizzair", "albergo"
    ],
    "Regali": [
        "regalo", "gift", "fiori", "florist", "flower"
    ],
}

SAVINGS_INVEST_KEYWORDS = {
    "Risparmio conto / deposito": [
        "conto deposito", "risparmio", "saving", "savings", "deposito", "caparra"
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
    "Stipendio & lavoro": [
        "stipendio", "salary", "paga", "retribuzione", "busta paga",
        "azioninnova", "saldo", "compenso", "mensilita"
    ],
    "Rimborsi & rientri": [
        "rimborso", "refund", "rimborso spese", "chargeback",
        "accredito", "restituzione", "referendum"
    ],
    "Entrate passive": [
        "interessi", "dividendo", "royalty", "cedola"
    ],
}

ALL_SUBCATEGORIES = (
    list(FIXED_KEYWORDS.keys())
    + list(VARIABLE_KEYWORDS.keys())
    + list(SAVINGS_INVEST_KEYWORDS.keys())
    + list(INCOME_KEYWORDS.keys())
)

def normalize_text(s):
    return str(s).lower()

def normalize_merchant(desc):
    txt = normalize_text(desc)
    for t in [
        "pagamento pos", "pagamento carta", "acquisto carta",
        "operazione pos", "contactless", "e-commerce",
        "ecommerce", "pagamento"
    ]:
        txt = txt.replace(t, " ")
    return " ".join(txt.split())

def match_keywords(description, rules):
    desc = normalize_text(description)
    for category, words in rules.items():
        for w in words:
            if w in desc:
                return category
    return None

def ai_batch_categorize(transactions, model):
    if model is None or len(transactions) == 0:
        return {}
    try:
        trans_list = "\n".join(
            [f"{i}. Descrizione: '{t['description']}', Importo: {t['amount']}€"
             for i, t in enumerate(transactions)]
        )

        prompt = f"""Sei un esperto di finanza personale. Categorizza TUTTE queste transazioni bancarie italiane.
Sottocategorie disponibili: {', '.join(ALL_SUBCATEGORIES)}
Transazioni da categorizzare:
{trans_list}
Rispondi SOLO con un JSON valido in questo formato: {{"0": "Nome sottocategoria", "1": "Nome sottocategoria", ...}}
Usa SOLO i nomi esatti delle sottocategorie della lista."""

        response = model.generate_content(prompt)
        result_text = response.text.strip()

        # Pulisci eventuale code block ```json ... ```
        if "```json" in result_text:
            result_text = result_text.split("```json", 1)[1]
            result_text = result_text.split("```", 1).strip()
        elif "```" in result_text:
            result_text = result_text.split("```", 1)[16]
            result_text = result_text.split("```", 1)[0].strip()

        categorization = json.loads(result_text)
        return categorization
    except Exception as e:
        st.warning(f"AI batch errore: {e}")
        return {}

def categorize_row_basic(row):
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

def generate_budget_advice(df, model):
    if model is None:
        return "AI non disponibile per consigli."
    try:
        entrate = df[df["macro_category"] == "Entrata"]["amount"].sum()
        fisso = abs(df[df["macro_category"] == "Fisso"]["amount"].sum())
        variabile = abs(df[df["macro_category"] == "Variabile"]["amount"].sum())
        risparmi = abs(df[df["macro_category"] == "Risparmi & investimenti"]["amount"].sum())

        var_by_cat = (
            df[df["macro_category"] == "Variabile"]
            .groupby("subcategory")["amount"]
            .sum().abs()
            .sort_values(ascending=False)
            .head(5)
        )

        prompt = f"""Sei un consulente finanziario personale. Analizza questi dati e dai 3-4 consigli pratici per ottimizzare il budget mensile.
Dati periodo analizzato:
- Entrate totali: {entrate:.0f}€
- Spese fisse: {fisso:.0f}€ ({(fisso/entrate*100) if entrate > 0 else 0:.1f}%)
- Spese variabili: {variabile:.0f}€ ({(variabile/entrate*100) if entrate > 0 else 0:.1f}%)
- Risparmi/investimenti: {risparmi:.0f}€ ({(risparmi/entrate*100) if entrate > 0 else 0:.1f}%)
Principali spese variabili:
{var_by_cat.to_string()}
Fornisci consigli pratici, con numeri specifici e percentuali. Sii conciso (max 4 punti)."""

        response = model.generate_content(prompt)
        return response.text.strip()
    except Exception as e:
        return f"Errore generazione consigli: {e}"

def build_internal_df(df_raw, col_date, col_desc, col_amount, col_name=None, col_type=None, col_iban=None):
    df = df_raw.copy()

    # Data
    df["date"] = pd.to_datetime(df[col_date], errors="coerce", dayfirst=True)

    # Descrizione = (nome esercente) + descrizione banca
    if col_name and col_name in df.columns:
        df["description"] = (
            df[col_name].astype(str).fillna("")
            + " - "
            + df[col_desc].astype(str).fillna("")
        ).str.strip(" -")
    else:
        df["description"] = df[col_desc].astype(str)

    # Importo
    raw_amount = (
        df[col_amount]
        .astype(str)
        .str.strip()
        .str.replace("€", "", regex=False)
        .str.replace("\u20ac", "", regex=False)
        .str.replace(" ", "", regex=False)
    )

    def parse_amount(x):
        if x is None or x == "" or str(x).lower() == "nan":
            return None
        x = str(x)
        # Formato europeo vs US
        if "," in x and x.rfind(",") > x.rfind("."):
            x = x.replace(".", "").replace(",", ".")
        elif "." in x and x.rfind(".") > x.rfind(","):
            x = x.replace(",", "")
        try:
            return float(x)
        except ValueError:
            return None

    df["amount"] = raw_amount.apply(parse_amount)

    # Altre colonne
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

    return df[
        [
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
    ]

# ---------------------------------------------------------
# Corpo principale app
# ---------------------------------------------------------
if uploaded_file is None:
    st.info("Carica un CSV dell'estratto conto per iniziare.")
else:
    # Caricamento CSV grezzo
    df_raw = load_csv(uploaded_file)
    st.subheader("📄 Anteprima CSV originale")
    st.dataframe(df_raw.head())

    st.markdown("### 🔧 Mappa le colonne del tuo CSV")

    cols = df_raw.columns.tolist()

    col_date = st.selectbox("Colonna data", cols, index=0)
    col_desc = st.selectbox("Colonna descrizione", cols, index=1 if len(cols) > 1 else 0)
    col_amount = st.selectbox("Colonna importo", cols, index=2 if len(cols) > 2 else 0)

    col_name = st.selectbox(
        "(Opzionale) Colonna nome esercente / controparte",
        ["<nessuna>"] + cols,
        index=0,
    )
    col_type = st.selectbox(
        "(Opzionale) Colonna tipo operazione / categoria banca",
        ["<nessuna>"] + cols,
        index=0,
    )
    col_iban = st.selectbox(
        "(Opzionale) Colonna IBAN / conto",
        ["<nessuna>"] + cols,
        index=0,
    )

    if st.button("✅ Elabora estratto conto"):
        with st.spinner("Elaborazione in corso..."):
            name_col = None if col_name == "<nessuna>" else col_name
            type_col = None if col_type == "<nessuna>" else col_type
            iban_col = None if col_iban == "<nessuna>" else col_iban

            df_internal = build_internal_df(
                df_raw,
                col_date=col_date,
                col_desc=col_desc,
                col_amount=col_amount,
                col_name=name_col,
                col_type=type_col,
                col_iban=iban_col,
            )

            # Rimuove righe senza importo o data valida
            df_internal = df_internal.dropna(subset=["amount", "date"])

            # Categorizzazione base
            df_internal = df_internal.apply(categorize_row_basic, axis=1)

            # AI per "Altro variabile"
            if use_ai:
                mask_ai = (
                    (df_internal["macro_category"] == "Variabile")
                    & (df_internal["subcategory"] == "Altro variabile")
                )
                to_ai = df_internal[mask_ai].reset_index()

                if not to_ai.empty:
                    transactions_for_ai = [
                        {
                            "description": row["description"],
                            "amount": row["amount"],
                        }
                        for _, row in to_ai.iterrows()
                    ]
                    cat_map = ai_batch_categorize(transactions_for_ai, gemini_model)

                    # Aggiorna sottocategorie dove ai ha risposto
                    for i, row in to_ai.iterrows():
                        idx = row["index"]
                        key = str(i)
                        if key in cat_map and cat_map[key] in ALL_SUBCATEGORIES:
                            df_internal.loc[idx, "subcategory"] = cat_map[key]

            # Salva in sessione
            st.session_state["df_internal"] = df_internal

    # Se abbiamo già elaborato (o appena elaborato)
    if "df_internal" in st.session_state:
        df_internal = st.session_state["df_internal"]

        st.markdown("### 📊 Transazioni elaborate")
        st.dataframe(df_internal.head(50))

        # Filtri periodo
        st.markdown("### 🗓️ Filtri")
        col1, col2 = st.columns(2)
        with col1:
            min_date = df_internal["date"].min().date()
            max_date = df_internal["date"].max().date()
            start_date = st.date_input("Data inizio", value=min_date, min_value=min_date, max_value=max_date)
        with col2:
            end_date = st.date_input("Data fine", value=max_date, min_value=min_date, max_value=max_date)

        mask_period = (df_internal["date"] >= pd.to_datetime(start_date)) & (
            df_internal["date"] <= pd.to_datetime(end_date)
        )
        df_period = df_internal[mask_period].copy()

        if df_period.empty:
            st.warning("Nessuna transazione nel periodo selezionato.")
        else:
            # Riepilogo
            entrate = df_period[df_period["macro_category"] == "Entrata"]["amount"].sum()
            spese_fisse = df_period[df_period["macro_category"] == "Fisso"]["amount"].sum()
            spese_var = df_period[df_period["macro_category"] == "Variabile"]["amount"].sum()
            risparmi = df_period[df_period["macro_category"] == "Risparmi & investimenti"]["amount"].sum()
            saldo = df_period["amount"].sum()

            st.markdown("### 📌 Riepilogo periodo")

            c1, c2, c3, c4, c5 = st.columns(5)
            c1.metric("Entrate", f"{entrate:,.0f}€")
            c2.metric("Spese fisse", f"{spese_fisse:,.0f}€")
            c3.metric("Spese variabili", f"{spese_var:,.0f}€")
            c4.metric("Risparmi / investimenti", f"{risparmi:,.0f}€")
            c5.metric("Saldo netto", f"{saldo:,.0f}€")

            # Grafici
            st.markdown("### 📈 Grafici")

            col_a, col_b = st.columns(2)

            # Spese per macro categoria
            df_spese = df_period[df_period["amount"] < 0].copy()
            if not df_spese.empty:
                df_macro = (
                    df_spese.groupby("macro_category")["amount"]
                    .sum()
                    .abs()
                    .reset_index()
                )
                fig_macro = px.pie(
                    df_macro,
                    names="macro_category",
                    values="amount",
                    title="Spese per macro categoria",
                )
                col_a.plotly_chart(fig_macro, use_container_width=True)

                df_sub = (
                    df_spese.groupby("subcategory")["amount"]
                    .sum()
                    .abs()
                    .sort_values(ascending=False)
                    .reset_index()
                )
                fig_sub = px.bar(
                    df_sub,
                    x="subcategory",
                    y="amount",
                    title="Top spese per sottocategoria",
                )
                fig_sub.update_layout(xaxis_tickangle=-45)
                col_b.plotly_chart(fig_sub, use_container_width=True)

            # Serie temporale saldo cumulato
            df_period_sorted = df_period.sort_values("date")
            df_period_sorted["cum_balance"] = df_period_sorted["amount"].cumsum()
            fig_time = px.line(
                df_period_sorted,
                x="date",
                y="cum_balance",
                title="Andamento saldo cumulato",
            )
            st.plotly_chart(fig_time, use_container_width=True)

            # Consigli AI
            st.markdown("### 🧠 Consigli personalizzati sul budget")
            advice = generate_budget_advice(df_period, gemini_model)
            st.write(advice)
