import streamlit as st
import numpy as np
import tifffile as tiff
import io
import datetime
from utils.geo import zscore_to_heatmap
from utils.storage import save_report, load_history

st.set_page_config(page_title="Turkeller Surfer Pro", layout="wide")

# Şifre korumalı giriş
if "authenticated" not in st.session_state:
    st.session_state.authenticated = False

if not st.session_state.authenticated:
    st.sidebar.title("🔐 Giriş")
    username = st.sidebar.text_input("Kullanıcı Adı", value="")
    password = st.sidebar.text_input("Şifre", value="", type="password")
    if st.sidebar.button("Giriş Yap"):
        if username == "admin" and password == "altin2026":
            st.session_state.authenticated = True
            st.rerun()
        else:
            st.sidebar.error("❌ Geçersiz giriş!")
    st.stop()

st.success("Hoşgeldin, admin!")

st.title("🌍 Turkeller Surfer Pro v2.4")

# TIF dosya yükleme
st.subheader("📁 Sentinel-1 tif dosyası yükle")
uploaded_file = st.file_uploader("Drag and drop file here", type=["tif", "tiff"])

# Z eşik değeri
threshold = st.slider("📊 Anomali Eşiği (Z)", min_value=0.5, max_value=5.0, step=0.1, value=2.0)

# Enlem / boylam giriş
col1, col2 = st.columns(2)
with col1:
    lat = st.text_input("📍 Enlem (Latitude)")
with col2:
    lon = st.text_input("📍 Boylam (Longitude)")

# Analiz butonu
if uploaded_file and lat and lon:
    if st.button("🔍 Analiz Yap"):
        try:
            z = tiff.imread(io.BytesIO(uploaded_file.read())).astype(np.float32)
            fig = zscore_to_heatmap(z, threshold)
            st.pyplot(fig)

            now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            save_report(uploaded_file.name, lat, lon, float(np.max(z)), now)
            st.success("✅ Anomali analizi başarıyla tamamlandı.")

        except Exception as e:
            st.error(f"⚠️ Analiz sırasında hata oluştu: {e}")
else:
    st.warning("Lütfen dosya yükleyin ve enlem-boylam girin.")

# Geçmiş tarama kayıtları
st.subheader("🕒 Tarama Geçmişi")
history = load_history()
if history:
    for item in reversed(history):
        st.markdown(f"📂 **{item['filename']}** ({item['timestamp']})  \n📍 Konum: ({item['lat']}, {item['lon']}) – Z: {item['z']}")
else:
    st.info("Henüz kayıtlı tarama yok.")
