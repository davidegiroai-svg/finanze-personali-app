import streamlit as st
import pandas as pd
from datetime import datetime

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


def load_csv(file) -> pd.DataFrame:
    """Carica il CSV provando separatori ; e ,"""
    try:
        # Prova con separatore ; (molte banche italiane)
        df = pd.read_csv(file, sep=";")
        if df.shape[1] == 1:
            # Se c'è solo una colonna, riprova con virgola
            file.seek(0)
            df = pd.read_csv(file, sep=",")
    except Exception:
        file.seek(0)
        df = pd.read_csv(file)
    return df


def build_internal_df(
    df_raw: pd.DataFrame,
    col_date: str,
    col_desc: str,
    col_amount: str,
    col_name: str | None = None,
    col_type: str | None = None,
    col_iban: str | None = None
) -> pd.DataFrame:
    """Crea il DataFrame interno standard a partire dal CSV originale."""
    df = df_raw.copy()

    # Data (italiana: giorno/mese/anno)
    df["date"] = pd.to_datetime(df[col_date], errors="coerce", dayfirst=True)

    # Descrizione: uniamo Nome + Descrizione se disponibile
    if col_name and col_name in df.columns:
        df["description"] = (
            df[col_name].astype(str).fillna("") + " - " + df[col_desc].astype(str).fillna("")
        ).str.strip(" -")
    else:
        df["description"] = df[col_desc].astype(str)

    # Importo numerico (gestione robusta di . e ,)
    raw_amount = df[col_amount].astype(str).str.strip()

    # Rimuovi simboli euro e spazi
    raw_amount = (
        raw_amount
        .str.replace("€", "", regex=False)
        .str.replace("\u20ac", "", regex=False)  # simbolo euro alternativo
        .str.replace(" ", "", regex=False)
    )

    def parse_amount(x: str) -> float | None:
        if x is None or x == "" or x.lower() == "nan":
            return None

        # Esempi:
        # "1.234,56"  -> 1234.56  (italiano)
        # "1234,56"   -> 1234.56
        # "1,234.56"  -> 1234.56  (stile US/UK)
        # "1234.56"   -> 1234.56

        # Caso tipico italiano: virgola come decimale
        if "," in x and x.rfind(",") > x.rfind("."):
            x = x.replace(".", "").replace(",", ".")
        # Caso stile inglese: punto come decimale
        elif "." in x and x.rfind(".") > x.rfind(","):
            x = x.replace(",", "")

        try:
            return float(x)
        except ValueError:
            return None

    df["amount"] = raw_amount.apply(parse_amount)

    # Account / IBAN
    if col_iban and col_iban in df.columns:
        df["account"] = df[col_iban].astype(str)
    else:
        df["account"] = "Conto principale"

    # Tipologia originale banca
    if col_type and col_type in df.columns:
        df["bank_category"] = df[col_type].astype(str)
    else:
        df["bank_category"] = ""

    # Direzione Entrata/Uscita (per ora solo segno importo)
    df["direction"] = df["amount"].apply(
        lambda x: "Entrata" if x is not None and x > 0 else "Uscita"
    )

    # Campi che useremo dopo
    df["macro_category"] = ""
    df["subcategory"] = ""
    df["normalized_merchant"] = ""

    # Ordiniamo per data
    df = df.sort_values("date")

    # Selezioniamo solo le colonne interne
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


if uploaded_file is not None:
    df_raw = load_csv(uploaded_file)

    st.subheader("📄 Anteprima CSV originale")
    st.dataframe(df_raw.head(20), use_container_width=True)

    st.markdown("### 🧩 Mappa le colonne del tuo estratto conto")

    # Proviamo a proporre i default per Hype
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
        st.success("Mappatura confermata, preparo i dati standardizzati...")

        df_internal = build_internal_df(
            df_raw=df_raw,
            col_date=col_date,
            col_desc=col_desc,
            col_amount=col_amount,
            col_name=None if col_name == "(nessuna)" else col_name,
            col_type=None if col_type == "(nessuna)" else col_type,
            col_iban=None if col_iban == "(nessuna)" else col_iban,
        )

        st.subheader("📚 Dati standardizzati (interni)")
        st.dataframe(
            df_internal,
            use_container_width=True,
            hide_index=True
        )

        col_a, col_b, col_c = st.columns(3)
        with col_a:
            st.metric("Numero transazioni", len(df_internal))
        with col_b:
            saldo = df_internal["amount"].sum(skipna=True)
            st.metric("Saldo totale", f"€ {saldo:,.2f}")
        with col_c:
            data_min = df_internal["date"].min()
            data_max = df_internal["date"].max()
            periodo = (
                f"{data_min.date()} → {data_max.date()}"
                if pd.notnull(data_min) and pd.notnull(data_max)
                else "N/D"
            )
            st.metric("Periodo coperto", periodo)

        st.info(
            "Prossimo passo: categorizzazione automatica "
            "(Fisso / Variabile / Entrate / Risparmi) e dashboard."
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


