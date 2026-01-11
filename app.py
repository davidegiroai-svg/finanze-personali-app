import streamlit as st
import pandas as pd
from datetime import datetime, date
import plotly.express as px
from huggingface_hub import InferenceClient
import json

# ---------------------------------------------------------
# Configurazione pagina
# ---------------------------------------------------------
st.set_page_config(
    page_title="Finanze Personali",
    layout="wide",
    page_icon="💰"
)

st.title("💰 Gestione Finanze Personali")
st.markdown("---")

# ---------------------------------------------------------
# Inizializzazione Hugging Face
# ---------------------------------------------------------
@st.cache_resource
def init_ai():
    try:
        client = InferenceClient(
            token=st.secrets["huggingface"]["api_key"]
        )
        return client
    except Exception as e:
        st.warning(f"⚠️ AI non disponibile: {e}")
        return None

ai_client = init_ai()

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

def normalize_text(s: str) -> str:
    if not isinstance(s, str):
        s = str(s)
    return s.lower()

def normalize_merchant(desc: str) -> str:
    txt = normalize_text(desc)
    remove_tokens = [
        "pagamento pos", "pagamento carta", "acquisto carta",
        "operazione pos", "contactless", "e-commerce", "ecommerce", "pagamento"
    ]
    for t in remove_tokens:
        txt = txt.replace(t, " ")
    return " ".join(txt.split())

def match_keywords(description: str, rules: dict):
    desc = normalize_text(description)
    for category, words in rules.items():
        for w in words:
            if w in desc:
                return category
    return None

def ai_batch_categorize(transactions: list, client) -> dict:
    if client is None or len(transactions) == 0:
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

        messages = [{"role": "user", "content": prompt}]
        
        response = client.chat_completion(
            messages=messages,
            model="mistralai/Mistral-7B-Instruct-v0.2",
            max_tokens=2000,
            temperature=0.1
        )
        
        result_text = response.choices[0].message.content.strip()

        # Pulisci eventuale code block
        if "```json" in result_text:
            result_text = result_text.split("```json", 1)[1]
            result_text = result_text.split("```", 1).strip()
        elif "```" in result_text:
            result_text = result_text.split("```", 1)[11]
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

def generate_budget_advice(df, client):
    if client is None:
        return "AI non disponibile per consigli."
    try:
        entrate = df[df["macro_category"] == "Entrata"]["amount"].sum()
        fisso = abs(df[df["macro_category"] == "Fisso"]["amount"].sum())
        variabile = abs(df[df["macro_category"] == "Variabile"]["amount"].sum())
        risparmi = abs(df[df["macro_category"] == "Risparmi & investimenti"]["amount"].sum())
        var_by_cat = (
            df[df["macro_category"] == "Variabile"]
            .groupby("subcategory")["amount"]
            .sum()
            .abs()
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

        messages = [{"role": "user", "content": prompt}]
        response = client.chat_completion(
            messages=messages,
            model="mistralai/Mistral-7B-Instruct-v0.2",
            max_tokens=500,
            temperature=0.7
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        return f"Errore generazione consigli: {e}"

def build_internal_df(df_raw, col_date, col_desc, col_amount, col_name=None, col_type=None, col_iban=None):
    df = df_raw.copy()
    df["date"] = pd.to_datetime(df[col_date], errors="coerce", dayfirst=True)

    if col_name and col_name in df.columns:
        df["description"] = (
            df[col_name].astype(str).fillna("") + " - " + df[col_desc].astype(str).fillna("")
        ).str.strip(" -")
    else:
        df["description"] = df[col_desc].astype(str)

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

# ---------------------------------------------------------
# Corpo principale app
# ---------------------------------------------------------
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
            index=(columns.index(default_iban) + 1) if default_iban in columns else 0,
        )

    if st.button("✅ Conferma mappatura e prepara dati"):
        df_internal = build_internal_df(
            df_raw,
            col_date,
            col_desc,
            col_amount,
            None if col_name == "(nessuna)" else col_name,
            None if col_type == "(nessuna)" else col_type,
            None if col_iban == "(nessuna)" else col_iban,
        )

        with st.spinner("📊 Categorizzazione con regole..."):
            df_categorized = df_internal.apply(categorize_row_basic, axis=1)

        if use_ai and ai_client:
            uncategorized = df_categorized[df_categorized["subcategory"] == "Altro variabile"]
            if len(uncategorized) > 0:
                st.info(
                    f"🤖 Trovate {len(uncategorized)} transazioni in 'Altro variabile'. L'AI le sta categorizzando..."
                )
                trans_for_ai = [
                    {"description": row["description"], "amount": row["amount"]}
                    for _, row in uncategorized.iterrows()
                ]
                with st.spinner(
                    f"🤖 Categorizzazione AI in corso ({len(trans_for_ai)} transazioni)..."
                ):
                    ai_results = ai_batch_categorize(trans_for_ai, ai_client)
                if ai_results:
                    for idx_str, subcategory in ai_results.items():
                        try:
                            idx = int(idx_str)
                            original_idx = uncategorized.iloc[idx].name
                            if subcategory in FIXED_KEYWORDS:
                                df_categorized.at[original_idx, "macro_category"] = "Fisso"
                            elif subcategory in VARIABLE_KEYWORDS:
                                df_categorized.at[original_idx, "macro_category"] = "Variabile"
                            elif subcategory in SAVINGS_INVEST_KEYWORDS:
                                df_categorized.at[original_idx, "macro_category"] = "Risparmi & investimenti"
                            elif subcategory in INCOME_KEYWORDS:
                                df_categorized.at[original_idx, "macro_category"] = "Entrata"
                            df_categorized.at[original_idx, "subcategory"] = subcategory
                        except Exception:
                            pass
                    st.success(f"✅ AI ha categorizzato {len(ai_results)} transazioni!")

        st.subheader("📚 Transazioni categorizzate")
        csv_export = df_categorized.to_csv(index=False).encode("utf-8")
        st.download_button(
            label="💾 Scarica dati categorizzati (CSV)",
            data=csv_export,
            file_name=f"finanze_categorizzate_{datetime.now().strftime('%Y%m%d')}.csv",
            mime="text/csv",
        )
        st.dataframe(df_categorized, use_container_width=True, hide_index=True)

        col_a, col_b, col_c = st.columns(3)
        with col_a:
            st.metric("Numero transazioni", len(df_categorized))
        with col_b:
            saldo = df_categorized["amount"].sum(skipna=True)
            st.metric("Saldo totale", f"€ {saldo:,.2f}")
        with col_c:
            data_min = df_categorized["date"].min()
            data_max = df_categorized["date"].max()
            if pd.notnull(data_min) and pd.notnull(data_max):
                periodo = f"{data_min.date()} → {data_max.date()}"
            else:
                periodo = "N/D"
            st.metric("Periodo coperto", periodo)

        st.markdown("### 🎛 Filtro periodo")
        if pd.notnull(data_min) and pd.notnull(data_max):
            start_default = data_min.date()
            end_default = data_max.date()
        else:
            start_default = end_default = date.today()

        start_date, end_date = st.date_input(
            "Seleziona intervallo date",
            value=(start_default, end_default),
        )

        mask = df_categorized["date"].between(
            pd.to_datetime(start_date), pd.to_datetime(end_date)
        )
        df_filtered = df_categorized[mask].copy()
        df_filtered["amount_abs"] = df_filtered["amount"].abs()

        st.markdown("### 📌 Sintesi periodo selezionato")
        col_a, col_b, col_c = st.columns(3)
        with col_a:
            st.metric("Numero transazioni", len(df_filtered))
        with col_b:
            saldo_reale = df_filtered["amount"].sum(skipna=True)
            st.metric("Saldo netto (Entrate - Uscite)", f"€ {saldo_reale:,.2f}")
        with col_c:
            spese_fisse = df_filtered.loc[
                df_filtered["macro_category"] == "Fisso", "amount_abs"
            ].sum()
            spese_var = df_filtered.loc[
                df_filtered["macro_category"] == "Variabile", "amount_abs"
            ].sum()
            st.metric(
                "Spese fisse / variabili",
                f"Fisso: {spese_fisse:,.0f}€ • Var: {spese_var:,.0f}€",
            )

        st.markdown("### 🥧 Macro-categorie (Entrate / Fissi / Variabili / Risparmi)")
        df_macro = df_filtered.copy()
        df_macro["value_for_chart"] = df_macro.apply(
            lambda r: r["amount"] if r["macro_category"] == "Entrata" else r["amount_abs"],
            axis=1,
        )
        agg_macro = df_macro.groupby("macro_category")["value_for_chart"].sum().reset_index()
        if not agg_macro.empty:
            fig_macro = px.pie(
                agg_macro,
                names="macro_category",
                values="value_for_chart",
                hole=0.4,
                title="Distribuzione importi per macro-categoria",
            )
            st.plotly_chart(fig_macro, use_container_width=True)
        else:
            st.info("Nessuna transazione nel periodo selezionato.")

        st.markdown("### 📊 Sottocategorie spese variabili")
        df_var = df_filtered[df_filtered["macro_category"] == "Variabile"]
        agg_sub = (
            df_var.groupby("subcategory")["amount_abs"]
            .sum()
            .reset_index()
            .sort_values("amount_abs")
        )
        if not agg_sub.empty:
            fig_sub = px.bar(
                agg_sub,
                x="amount_abs",
                y="subcategory",
                orientation="h",
                title="Spese variabili per sottocategoria",
                labels={"amount_abs": "Importo €", "subcategory": "Categoria"},
            )
            st.plotly_chart(fig_sub, use_container_width=True)
        else:
            st.info("Nessuna spesa variabile nel periodo selezionato.")

        if ai_client and len(df_filtered) > 0:
            st.markdown("### 💡 Consigli AI per il budget")
            with st.spinner("🤖 Sto generando consigli personalizzati..."):
                consigli = generate_budget_advice(df_filtered, ai_client)
            st.info(consigli)

        st.markdown("### 📚 Transazioni filtrate")
        st.dataframe(
            df_filtered.drop(columns=["amount_abs"]),
            use_container_width=True,
            hide_index=True,
        )

else:
    st.info("👆 Carica un CSV dal sidebar per iniziare.")
    st.markdown(
        """**Consigli CSV Hype**
- Esporta da Hype in formato CSV.
- Le colonne tipiche sono: `Data operazione`, `Data contabile`, `Iban`, `Tipologia`, `Nome`, `Descrizione`, `Importo ( € )`.
- L'app proverà a riconoscerle automaticamente, ma puoi sempre cambiarle dalla mappatura."""
    )
