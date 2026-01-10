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
            return No

