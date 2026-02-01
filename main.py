import streamlit as st
from utils.geo import plot_map
from utils.storage import save_report, load_history
import datetime
import json
import os

st.set_page_config(layout="wide", page_title="Turkeller Surfer Pro v2.2")

# Giriş kontrolü
with st.sidebar:
    st.title("🔐 Giriş")
    username = st.text_input("Kullanıcı Adı", value="")
    password = st.text_input("Şifre", value="", type="password")
    if st.button("Giriş Yap"):
        if username == "admin" and password == "altin2026":
            st.session_state["authenticated"] = True
        else:
            st.error("Kullanıcı adı veya şifre hatalı!")

if not st.session_state.get("authenticated"):
    st.stop()

st.success(f"Hoşgeldin, {username}!")

st.title("🌍 Turkeller Surfer Pro v2.2")

uploaded_file = st.file_uploader("📁 Sentinel-1 tif dosyası yükle", type=["tif", "tiff"])

z_threshold = st.slider("📊 Anomali Eşiği (Z)", min_value=1.0, max_value=4.0, step=0.1, value=2.0)

col1, col2 = st.columns(2)
with col1:
    lat = st.text_input("📍 Enlem (Latitude)", value="")
with col2:
    lon = st.text_input("📍 Boylam (Longitude)", value="")

if uploaded_file and lat and lon:
    # Dummy sonuç üret
    anomaly_data = {
        "filename": uploaded_file.name,
        "datetime": datetime.datetime.now().isoformat(),
        "latitude": lat,
        "longitude": lon,
        "z_threshold": z_threshold,
        "anomaly_score": round(z_threshold + 0.5, 2),  # sahte skor
    }
    save_report(anomaly_data)
    st.success("✅ Tarama tamamlandı. Aşağıda harita görüntüleniyor.")
    plot_map(lat, lon, anomaly_data["anomaly_score"])

    with st.expander("📌 Bu Anomaliye Git"):
        st.map(data={"lat": [float(lat)], "lon": [float(lon)]})
        st.write(f"Z Skoru: {anomaly_data['anomaly_score']}")

st.header("🕓 Tarama Geçmişi")
history = load_history()
if history:
    for item in history[::-1]:
        st.markdown(f"📁 **{item['filename']}** ({item['datetime'][:19]})")
        st.write(f"Konum: ({item['latitude']}, {item['longitude']}) – Z: {item['anomaly_score']}")
else:
    st.info("Henüz kayıtlı tarama yok.")
