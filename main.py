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
if "coord_str" not in st.session_state: st.session_state.coord_str = "40.1048440 27.7690640"

# -------------------------
# UI
# -------------------------
st.title("🛰️ Turkeller Surfer Pro")
st.caption("VV dB + POS/NEG anomali | 2D şekilli overlay | 3D surface | isimli kayıt")

# query paramdan gelen konum varsa inputa uygula
qp_lat, qp_lon = apply_qp_location()
if qp_lat is not None and qp_lon is not None:
    st.session_state.coord_str = f"{qp_lat:.7f} {qp_lon:.7f}"

with st.form("controls", clear_on_submit=False):
    scan_name = st.text_input("📝 Tarama Adı (kayda isim ver)", value="", placeholder="Örn: Bahçe-1 / Kazı-2 / Deneme-01")

    coord_in = st.text_input("📌 Koordinat — örn: `40.1048440 27.7690640`", value=st.session_state.coord_str)
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
geolocation_button()

cA, cB = st.columns(2)
with cA:
    if st.button("🧹 Odak Temizle", use_container_width=True):
        st.session_state.focus_lat = None
        st.session_state.focus_lon = None
        st.session_state.focus_label = None
        st.rerun()
with cB:
    st.caption("İpucu: Mobilde izin vermezse konumu elle gir veya `?glat=..&glon=..` ile test et.")

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

            used_bbox, used_r = bbox1, r1
            refined = False
            cap_used = int(cap_m)

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
                used_bbox, used_r = bbox2, r2
                refined = True
                cap_used = int(cap2)
                st.success(f"✅ Oto Refine: Top1 merkezine {cap2}m ile tekrar tarandı.")

            Z_db_clip = used_r["Z_db_clip"]
            X = used_r["X"]
            Y = used_r["Y"]
            Z_z = used_r["Z_z"]
            ranked = used_r["ranked"]
            topN = ranked[: int(topn)]
            pos_mask = used_r["pos_mask"]
            neg_mask = used_r["neg_mask"]

            # =========================
            # 2D HEATMAP (ŞEKİL GİBİ OVERLAY)
            # =========================
            st.subheader("🗺️ 2D Heatmap (anomali şekilleri)")

            fig = go.Figure()

            # Zemin VV dB
            fig.add_trace(go.Heatmap(
                z=Z_db_clip,
                x=X[0, :],
                y=Y[:, 0],
                colorbar=dict(title="VV (dB)"),
                name="VV"
            ))

            # POS filled overlay (beyaz dolgu + kırmızı border)
            if np.any(pos_mask):
                fig.add_trace(go.Contour(
                    z=pos_mask.astype(int),
                    x=X[0, :],
                    y=Y[:, 0],
                    showscale=False,
                    contours=dict(start=0.5, end=0.5, size=1, coloring="fill"),
                    colorscale=[[0.0, "rgba(0,0,0,0)"], [1.0, "rgba(255,255,255,0.92)"]],
                    line=dict(width=2, color="red"),
                    hoverinfo="skip",
                    name="POS"
                ))

            # NEG filled overlay (beyaz dolgu + mavi border)
            if np.any(neg_mask):
                fig.add_trace(go.Contour(
                    z=neg_mask.astype(int),
                    x=X[0, :],
                    y=Y[:, 0],
                    showscale=False,
                    contours=dict(start=0.5, end=0.5, size=1, coloring="fill"),
                    colorscale=[[0.0, "rgba(0,0,0,0)"], [1.0, "rgba(255,255,255,0.92)"]],
                    line=dict(width=2, color="deepskyblue"),
                    hoverinfo="skip",
                    name="NEG"
                ))

            # TopN işaretleri (POS/NEG renkle)
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
                height=520,
                margin=dict(l=0, r=0, t=30, b=0),
                xaxis_title="Boylam",
                yaxis_title="Enlem",
                title="2D Isı Haritası + POS/NEG Şekilli Overlay"
            )
            st.plotly_chart(fig, use_container_width=True)

            # =========================
            # 3D SURFACE
            # =========================
            st.subheader("🧊 3D Surface (VV dB)")
            surf = go.Figure(data=[go.Surface(z=Z_db_clip, x=X, y=Y)])
            surf.update_layout(height=520, margin=dict(l=0, r=0, t=30, b=0))
            st.plotly_chart(surf, use_container_width=True)

            # =========================
            # TOPN LIST (Z / DERİNLİK + BUTONLAR)
            # =========================
            st.subheader(f"🎯 Top {topn} Hedef (Harita/Kopya = TARGET)")

            if not topN:
                st.info("Bu eşikte anomali bulunamadı. Eşiği düşürmeyi deneyebilirsin.")
            else:
                for i, t in enumerate(topN, start=1):
                    tag = "🟢 POS" if t["type"] == "POS" else "🔴 NEG"
                    # “derinlik” olarak: peak_z (işaretli) + rel_depth (göreceli)
                    st.markdown(
                        f"**#{i} {tag}** | score=`{t['score']:.2f}` | **peak z=`{t['peak_z']:.2f}`** | "
                        f"alan=`{t['area']}` px | derinlik(göreceli)=`{t['rel_depth']:.2f}`"
                    )
                    st.code(f"{t['target_lat']:.8f} {t['target_lon']:.8f}", language="text")

                    c1, c2 = st.columns(2)
                    with c1:
                        if st.button("📍 Anomaliye Git", key=f"goto_{i}", use_container_width=True):
                            st.session_state.focus_lat = t["target_lat"]
                            st.session_state.focus_lon = t["target_lon"]
                            st.session_state.focus_label = f"#{i}"
                            st.rerun()
                    with c2:
                        maps_url = f"https://www.google.com/maps/search/?api=1&query={t['target_lat']},{t['target_lon']}"
                        st.link_button("🌍 Haritada Aç", maps_url, use_container_width=True)

                    st.divider()

            # =========================
            # SAVE HISTORY (İSİMLİ + EŞİK + ÇAP + TARİH)
            # =========================
            append_history(
                name=scan_name.strip(),
                lat=float(lat_val),
                lon=float(lon_val),
                cap_m=int(cap_used),
                thr=float(thr),
                z_mode=z_mode,
                top=topN[: min(len(topN), 10)],
            )
            st.success("✅ Analiz tamamlandı ve tarama geçmişine kaydedildi.")

# -------------------------
# HISTORY
# -------------------------
st.divider()
st.subheader("🕓 Tarama Geçmişi")

hist = load_history()
if not hist:
    st.info("Henüz tarama geçmişi yok.")
else:
    for idx, h in enumerate(hist[-15:][::-1], start=1):
        name = h.get("name") or "(İsimsiz)"
        ts = h.get("ts") or "Tarih yok"
        lat = h.get("lat")
        lon = h.get("lon")
        capm = h.get("cap_m")
        thr = h.get("thr")
        zm = h.get("z_mode") or ""

        st.markdown(f"**{idx}) {name}** — {ts}")
        st.write(f"📍 {lat}, {lon} | çap: {capm} m | eşik: {thr} | {zm}")

        # Kayda “Haritada Aç”
        if lat is not None and lon is not None:
            maps_url = f"https://www.google.com/maps/search/?api=1&query={lat},{lon}"
            st.link_button("🌍 Bu Taramayı Haritada Aç", maps_url, use_container_width=True)

        top = h.get("top") or []
        if top:
            with st.expander("Top anomaliler (peak z / derinlik)"):
                for j, t in enumerate(top, start=1):
                    tag = "POS" if t.get("type") == "POS" else "NEG"
                    st.write(
                        f"#{j} {tag} | peak z={t.get('peak_z', 0):.2f} | derinlik={t.get('rel_depth', 0):.2f} | "
                        f"{t.get('target_lat', 0):.6f}, {t.get('target_lon', 0):.6f}"
                    )
        st.divider()
