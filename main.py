import streamlit as st
import requests
import io
import numpy as np
import matplotlib.pyplot as plt
from utils.geo import zscore_to_heatmap, zscore_to_surface, plot_map
from utils.storage import save_report, load_history

st.set_page_config(page_title="Turkeller Surfer Pro", layout="wide")

st.title("🌍 Turkeller Surfer Pro v2")
client_id = st.secrets["client_id"]
client_secret = st.secrets["client_secret"]

# KULLANICI GİRİŞİ
with st.sidebar:
    st.header("🔐 Giriş")
    username = st.text_input("Kullanıcı Adı")
    password = st.text_input("Şifre", type="password")
    login_button = st.button("Giriş Yap")

if login_button:
    if username == "admin" and password == "1234":
        st.session_state.logged_in = True
    else:
        st.error("Hatalı kullanıcı adı veya şifre.")

if not st.session_state.get("logged_in", False):
    st.stop()

st.success("Hoşgeldin, admin!")

# Dosya yükleme
uploaded_file = st.file_uploader("📁 Sentinel-1 .tif dosyası yükle", type=["tif"])
threshold = st.slider("📊 Anomali Eşiği (Z)", 1.0, 5.0, 3.0, 0.1)

if uploaded_file:
    try:
        import tifffile as tiff
        Z = tiff.imread(uploaded_file)
        Z = Z.astype(np.float32)
        mean = np.mean(Z)
        std = np.std(Z)
        Z_z = (Z - mean) / std
        anomalies = np.where(np.abs(Z_z) > threshold)
        anomaly_count = len(anomalies[0])

        st.write(f"🔍 {anomaly_count} anomali bulundu")

        fig = zscore_to_surface(Z_z)
        st.plotly_chart(fig, use_container_width=True)

        st.pyplot(zscore_to_heatmap(Z_z))

        lat = st.number_input("Enlem", value=37.0, format="%.6f")
        lon = st.number_input("Boylam", value=35.0, format="%.6f")

        st.map(plot_map(lat, lon))

        if st.button("💾 Raporu Kaydet"):
            save_report({
                "lat": lat,
                "lon": lon,
                "anomali": anomaly_count,
                "threshold": threshold
            })
            st.success("Rapor kaydedildi.")
    except Exception as e:
        st.error(f"Hata oluştu: {e}")

# Geçmiş
st.subheader("📚 Tarama Geçmişi")
history = load_history()
for item in history:
    st.write(item)