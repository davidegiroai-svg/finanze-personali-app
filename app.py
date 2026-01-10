import streamlit as st
import pandas as pd
from datetime import datetime

st.set_page_config(page_title="Finanze Personali", layout="wide", page_icon="💰")

st.title("💰 Gestione Finanze Personali")
st.markdown("---")

# Sidebar per upload
st.sidebar.header("📁 Carica estratto conto")
uploaded_file = st.sidebar.file_uploader("Scegli CSV estratto conto", type="csv")

if uploaded_file is not None:
    df = pd.read_csv(uploaded_file)
    st.success(f"Caricato {len(df)} transazioni!")
    
    st.subheader("📊 Anteprima dati")
    st.dataframe(df.head(10))
    
    if 'Descrizione' in df.columns and 'Importo' in df.columns:
        st.info("✅ Rilevate colonne: Descrizione + Importo")
    else:
        st.warning("⚠️ Verifica colonne: cerca 'Descrizione', 'Causale', 'Importo', 'Data'")
    
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Totale transazioni", len(df))
    with col2:
        total = df['Importo'].sum()
        st.metric("Saldo", f"€ {total:,.2f}")
    with col3:
        st.metric("Data ultima", df['Data'].max() if 'Data' in df else "N/D")
else:
    st.info("👆 Carica un CSV dal sidebar per iniziare!")

st.markdown("---")
st.caption("Prossimo: categorizzazione automatica + Kimi AI + Google Sheets")
