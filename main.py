import streamlit as st
import numpy as np
import plotly.graph_objects as go

from utils.cdse import get_token_from_secrets, fetch_s1_tiff_bytes
from utils.analysis import (
    parse_coord_pair, bbox_from_latlon,
    run_analysis_from_tiff_bytes,
)
from utils.storage import append_history, load_history
from utils.geo_ui import geolocation_button, apply_qp_location

# -------------------------
# PAGE
# -------------------------
st.set_page_config(page_title="Turkeller Surfer Pro", layout="centered", initial_sidebar_state="collapsed")

# -------------------------
# LOGIN (sabit)
# -------------------------
APP_USER = "admin"
APP_PASS = "altin2026"

if "auth" not in st.session_state:
    st.session_state.auth = False

if not st.session_state.auth:
    st.title("🔐 Giriş")
    u = st.text_input("Kullanıcı Adı", value="")
    p = st.text_input("Şifre", value="", type="password")
    if st.button("Giriş Yap", use_container_width=True):
        if u == APP_USER and p == APP_PASS:
            st.session_state.auth = True
            st.rerun()
        else:
            st.error("Hatalı kullanıcı adı/şifre")
    st.stop()

# -------------------------
# STATE
# -------------------------
if "focus_lat" not in st.session_state: st.session_state.focus_lat = None
if "focus_lon" not in st.session_state: st.session_state.focus_lon = None
if "focus_label" not in st.session_state: st.session_state.focus_label = None

# -------------------------
# UI
# -------------------------
st.title("🛰️ Turkeller Surfer Pro")
st.caption("Sentinel-1 VV | Pozitif/Negatif anomali | Renkli 2D Heatmap | ‘Analize Başla’ stabil akış")

# canlı konum query param’dan geldiyse inputa bas
qp_lat, qp_lon = apply_qp_location()

default_coord = "40.1048440 27.7690640"
if "coord_str" not in st.session_state:
    st.session_state.coord_str = default_coord

if qp_lat is not None and qp_lon is not None:
    st.session_state.coord_str = f"{qp_lat:.7f} {qp_lon:.7f}"

with st.form("controls", clear_on_submit=False):
    coord_in = st.text_input("📌 Koordinat (tek kutu) — örn: `40.1048440 27.7690640`", value=st.session_state.coord_str)
    st.session_state.coord_str = coord_in
    lat_val, lon_val = parse_coord_pair(coord_in)

    c1, c2 = st.columns(2)
    with c1:
        cap_m = st.slider("Tarama Çapı (m)", 20, 300, 50)
    with c2:
        res_opt = st.selectbox("Çözünürlük", [120, 200, 300], index=0)

    c3, c4 = st.columns(2)
    with c3:
        topn = st.slider("TopN", 1, 15, 3)
    with c4:
        thr = st.slider("Anomali Eşiği (z)", 1.5, 6.0, 2.8, 0.1)

    c5, c6 = st.columns(2)
    with c5:
        z_mode = st.selectbox("Z türü", ["Robust (Median+MAD)", "Klasik (Mean+Std)"], index=0)
    with c6:
        clip_lo, clip_hi = st.slider("Clip % (lo/hi)", 0, 99, (1, 99))

    c7, c8 = st.columns(2)
    with c7:
        smooth_on = st.checkbox("Smoothing (BoxBlur)", value=True)
    with c8:
        smooth_k = st.selectbox("Kernel", [1, 3, 5], index=1, disabled=(not smooth_on))

    posneg = st.checkbox("Pozitif/Negatif ayır", value=True)
    auto_refine = st.checkbox("🎯 Oto Refine (Top1 ile tekrar tarama)", value=True)

    submitted = st.form_submit_button("🔍 Analize Başla", use_container_width=True)

st.divider()
geolocation_button("📍 Canlı Konumu Çek (mobil)")

if st.button("🧹 Odak Temizle", use_container_width=True):
    st.session_state.focus_lat = None
    st.session_state.focus_lon = None
    st.session_state.focus_label = None
    st.rerun()

# -------------------------
# ANALYZE
# -------------------------
if submitted:
    if lat_val is None or lon_val is None:
        st.error("Koordinat formatı hatalı. Örn: `41.0073777 28.7962100`")
    else:
        with st.spinner("🛰️ Veri çekiliyor ve analiz ediliyor..."):
            token = get_token_from_secrets()

            # 1) geniş tarama
            bbox1 = bbox_from_latlon(lat_val, lon_val, cap_m)
            tiff_bytes1 = fetch_s1_tiff_bytes(token, bbox1, res_opt, res_opt)
            r1 = run_analysis_from_tiff_bytes(
                tiff_bytes1, bbox1,
                clip_lo, clip_hi,
                smooth_on, int(smooth_k),
                z_mode, float(thr),
                bool(posneg),
            )
            ranked1 = r1["ranked"]
            topN1 = ranked1[: int(topn)]

            used = (bbox1, r1)
            refined = False
            cap2 = None

            # 2) oto refine
            if auto_refine and len(topN1) > 0 and cap_m > 25:
                top1 = topN1[0]
                cap2 = max(20, min(30, int(cap_m * 0.5)))
                bbox2 = bbox_from_latlon(top1["target_lat"], top1["target_lon"], cap2)
                tiff_bytes2 = fetch_s1_tiff_bytes(token, bbox2, res_opt, res_opt)
                r2 = run_analysis_from_tiff_bytes(
                    tiff_bytes2, bbox2,
                    clip_lo, clip_hi,
                    smooth_on, int(smooth_k),
                    z_mode, float(thr),
                    bool(posneg),
                )
                used = (bbox2, r2)
                refined = True

            bbox, r = used
            Z_db_clip = r["Z_db_clip"]
            X = r["X"]
            Y = r["Y"]
            Z_z = r["Z_z"]
            ranked = r["ranked"]
            topN = ranked[: int(topn)]
            pos_mask = r["pos_mask"]
            neg_mask = r["neg_mask"]

            if refined:
                st.success(f"✅ Oto Refine yapıldı: Top1 merkezine {cap2}m ile tekrar tarandı.")

            # ----- 2D HEATMAP (Renkli + POS/NEG kontur)
            st.subheader("🗺️ 2D Heatmap (POS/NEG renkli kontur)")

            fig = go.Figure()
            fig.add_trace(go.Heatmap(
                z=Z_db_clip,
                x=X[0, :],
                y=Y[:, 0],
                colorbar=dict(title="VV (dB)"),
                name="VV dB"
            ))

            # POS kontur (kırmızı)
            if np.any(pos_mask):
                fig.add_trace(go.Contour(
                    z=pos_mask.astype(int),
                    x=X[0, :],
                    y=Y[:, 0],
                    showscale=False,
                    contours=dict(start=0.5, end=0.5, size=1),
                    line=dict(width=2, color="red"),
                    hoverinfo="skip",
                    name="POS"
                ))

            # NEG kontur (mavi)
            if np.any(neg_mask):
                fig.add_trace(go.Contour(
                    z=neg_mask.astype(int),
                    x=X[0, :],
                    y=Y[:, 0],
                    showscale=False,
                    contours=dict(start=0.5, end=0.5, size=1),
                    line=dict(width=2, color="deepskyblue"),
                    hoverinfo="skip",
                    name="NEG"
                ))

            # TopN işaretleri
            for i, t in enumerate(topN, start=1):
                fig.add_trace(go.Scatter(
                    x=[t["target_lon"]],
                    y=[t["target_lat"]],
                    mode="markers+text",
                    text=[f"#{i}"],
                    textposition="top center",
                    marker=dict(size=10, color=("red" if t["type"] == "POS" else "deepskyblue")),
                    name=f"Top {i}"
                ))

            # Odak
            if st.session_state.focus_lat is not None and st.session_state.focus_lon is not None:
                fig.add_trace(go.Scatter(
                    x=[st.session_state.focus_lon],
                    y=[st.session_state.focus_lat],
                    mode="markers+text",
                    text=[f"ODAK {st.session_state.focus_label or ''}"],
                    textposition="bottom center",
                    marker=dict(size=16, symbol="x", color="yellow"),
                    name="Odak"
                ))

            fig.update_layout(
                height=560,
                margin=dict(l=0, r=0, t=30, b=0),
                xaxis_title="Boylam",
                yaxis_title="Enlem",
                title="2D Heatmap + POS/NEG Anomali"
            )
            st.plotly_chart(fig, use_container_width=True)

            # ----- TOPN LIST + “Anomaliye Git”
            st.subheader(f"🎯 Top {topn} Hedef (TARGET koordinatı)")

            if not topN:
                st.info("Bu eşikte anomali bulunamadı. Eşiği düşürmeyi deneyebilirsin.")
            else:
                for i, t in enumerate(topN, start=1):
                    tag = "🟥 POS" if t["type"] == "POS" else "🟦 NEG"
                    st.markdown(
                        f"**#{i} {tag}** | score=`{t['score']:.2f}` | peak z=`{t['peak_z']:.2f}` | alan=`{t['area']}` px | "
                        f"Z(göreceli)=`{t['rel_depth']:.2f}`"
                    )
                    st.code(f"{t['target_lat']:.8f} {t['target_lon']:.8f}", language="text")

                    cA, cB = st.columns(2)
                    with cA:
                        if st.button("📍 Anomaliye Git", key=f"goto_{i}", use_container_width=True):
                            st.session_state.focus_lat = t["target_lat"]
                            st.session_state.focus_lon = t["target_lon"]
                            st.session_state.focus_label = f"#{i}"
                            st.rerun()
                    with cB:
                        maps_url = f"https://www.google.com/maps/search/?api=1&query={t['target_lat']},{t['target_lon']}"
                        st.link_button("🌍 Haritada Aç", maps_url, use_container_width=True)

                    st.divider()

            # ----- geçmişe kaydet (tarama konumu)
            append_history(
                lat=float(lat_val),
                lon=float(lon_val),
                cap_m=int(cap_m if not refined else cap2),
                thr=float(thr),
                top=topN[: min(len(topN), 5)],
            )
            st.success("✅ Analiz tamamlandı ve tarama geçmişine kaydedildi.")

# -------------------------
# HISTORY
# -------------------------
st.divider()
st.subheader("🕓 Tarama Geçmişi (Kaydedilen konumlar)")

hist = load_history()
if not hist:
    st.info("Henüz tarama geçmişi yok.")
else:
    # son 10
    for idx, h in enumerate(hist[-10:][::-1], start=1):
        st.markdown(f"**{idx})** {h.get('ts','Tarih yok')}  —  📍 `{h.get('lat')}, {h.get('lon')}`  —  çap `{h.get('cap_m')}`m  —  eşik `{h.get('thr')}`")
        top = h.get("top") or []
        if top:
            with st.expander("Top anomaliler"):
                for j, t in enumerate(top, start=1):
                    tag = "POS" if t.get("type") == "POS" else "NEG"
                    st.write(f"#{j} {tag} | z={t.get('peak_z'):.2f} | {t.get('target_lat'):.6f}, {t.get('target_lon'):.6f}")
