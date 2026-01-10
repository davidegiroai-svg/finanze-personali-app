import streamlit as st
import pandas as pd
from datetime import datetime, date
import plotly.express as px

st.set_page_config(
    page_title="Finanze Personali",
    layout="wide",
    page_icon="💰"
)

st.title("💰 Gestione Finanze Personali")
st.markdown("---")

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
            index=(columns.index(default_iban) + 1) if default_iban in columns else 0,
        )

    if st.button("✅ Conferma mappatura e prepara dati"):
        df_internal = build_internal_df(
            df_raw=df_raw,
            col_date=col_date,
            col_desc=col_desc,
            col_amount=col_amount,
            col_name=None if col_name == "(nessuna)" else col_name,
            col_type=None if col_type == "(nessuna)" else col_type,
            col_iban=None if col_iban == "(nessuna)" else col_iban,
        )

        df_categorized = df_internal.apply(categorize_row, axis=1)

        # ---- FILTRI PERIODO ----
        st.markdown("### 🎛 Filtro periodo")
        min_dt = df_categorized["date"].min()
        max_dt = df_categorized["date"].max()
        start_default = min_dt.date() if pd.notnull(min_dt) else date.today()
        end_default = max_dt.date() if pd.notnull(max_dt) else date.today()

        start_date, end_date = st.date_input(
            "Seleziona intervallo date",
            value=(start_default, end_default),
            min_value=start_default,
            max_value=end_default,
        )

        mask = df_categorized["date"].between(
            pd.to_datetime(start_date), pd.to_datetime(end_date)
        )
        df_filtered = df_categorized[mask]

        # ---- METRICHE ----
        st.markdown("### 📌 Sintesi periodo selezionato")
        col_a, col_b, col_c = st.columns(3)
        with col_a:
            st.metric("Numero transazioni", len(df_filtered))
        with col_b:
            saldo = df_filtered["amount"].sum(skipna=True)
            st.metric("Saldo totale", f"€ {saldo:,.2f}")
        with col_c:
            tot_fisso = df_filtered.loc[df_filtered["macro_category"] == "Fisso", "amount"].sum()
            tot_var = df_filtered.loc[df_filtered["macro_category"] == "Variabile", "amount"].sum()
            st.metric("Spese fisse / variabili", f"Fisso: {tot_fisso:,.0f}€ • Var: {tot_var:,.0f}€")

        # ---- GRAFICO MACRO-CATEGORIE ----
        st.markdown("### 🥧 Macro-categorie (Entrate / Fissi / Variabili / Risparmi)")
        agg_macro = (
            df_filtered.groupby("macro_category")["amount"]
            .sum()
            .reset_index()
        )
        if not agg_macro.empty:
            fig_macro = px.pie(
                agg_macro,
                names="macro_category",
                values="amount",
                hole=0.4,
                title="Distribuzione importi per macro-categoria",
            )
            st.plotly_chart(fig_macro, use_container_width=True)
        else:
            st.info("Nessuna transazione nel periodo selezionato.")

        # ---- GRAFICO SOTTOCATEGORIE VARIABILI ----
        st.markdown("### 📊 Sottocategorie spese variabili")
        df_var = df_filtered[df_filtered["macro_category"] == "Variabile"]
        agg_sub = (
            df_var.groupby("subcategory")["amount"]
            .sum()
            .reset_index()
            .sort_values("amount")
        )
        if not agg_sub.empty:
            fig_sub = px.bar(
                agg_sub,
                x="amount",
                y="subcategory",
                orientation="h",
                title="Spese variabili per sottocategoria",
            )
            st.plotly_chart(fig_sub, use_container_width=True)
        else:
            st.info("Nessuna spesa variabile nel periodo selezionato.")

        # ---- TABELLA COMPLETA ----
        st.markdown("### 📚 Transazioni categorizzate (filtrate)")
        st.dataframe(
            df_filtered,
            use_container_width=True,
            hide_index=True
        )

else:
    st.info("👆 Carica un CSV dal sidebar per iniziare.")
    st.markdown(
        """
        **Consigli CSV Hype**

        - Esporta da Hype in formato CSV.
        - Le colonne tipiche sono: `Data operazione`, `Data contabile`, `Iban`,
          `Tipologia`, `Nome`, `Descrizione`, `Importo ( € )`.
        - L'app proverà a riconoscerle automaticamente, ma puoi sempre
          cambiarle dalla mappatura.
        """
    )
