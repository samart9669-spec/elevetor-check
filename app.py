import streamlit as st
import pandas as pd
import requests
import folium
import json
import os
from datetime import datetime, timezone
from streamlit_folium import st_folium
from streamlit_geolocation import streamlit_geolocation

st.set_page_config(page_title="เช็กระดับโกดัง", page_icon="🏭", layout="centered")
LABELS = {"A": "ถนนใหญ่หน้าโครงการ", "B": "ถนนภายในโครงการ", "C": "พื้นโกดัง"}
CHECKS = [
    ("มีคราบน้ำ/รอยน้ำบนผนังหรือเสา", 3),
    ("เจ้าของหรือผู้เช่าเดิมแจ้งว่าเคยมีน้ำท่วม", 4),
    ("ถนนภายในมีแอ่งต่ำหรือน้ำขังหลังฝนตก", 2),
    ("พื้นโกดังเสมอหรือต่ำกว่าถนนหน้าประตู", 3),
    ("ทางเข้าโกดังไม่มีธรณี/แนวกั้นน้ำ", 1),
    ("ท่อระบายน้ำหรือบ่อพักอยู่ใกล้ประตูและระบายช้า", 2),
    ("มีทางน้ำไหลจากถนน/พื้นที่ข้างเคียงเข้าหาโกดัง", 3),
    ("มีพื้นที่ต่ำหรือคลอง/แหล่งน้ำใกล้โครงการ", 1),
]

def supabase_config():
    try:
        url = st.secrets.get("SUPABASE_URL", "")
        key = st.secrets.get("SUPABASE_KEY", "")
    except Exception:
        url, key = os.getenv("SUPABASE_URL", ""), os.getenv("SUPABASE_KEY", "")
    return url.rstrip("/"), key

def supabase_headers(key):
    return {"apikey": key, "Authorization": f"Bearer {key}",
            "Content-Type": "application/json", "Prefer": "return=representation"}

def db_insert(record):
    url, key = supabase_config()
    if not url or not key:
        return False, "ยังไม่ได้ตั้งค่า Supabase จึงบันทึกได้เฉพาะในหน้าปัจจุบัน ไม่ใช่ฐานข้อมูลร่วม"
    endpoint = f"{url}/rest/v1/warehouse_sites"
    try:
        r = requests.post(endpoint, headers=supabase_headers(key), json=record, timeout=20)
        if r.status_code not in (200, 201):
            return False, f"Supabase ตอบกลับ {r.status_code}: {r.text[:300]}"
        return True, "บันทึกลงฐานข้อมูลกลางแล้ว"
    except Exception as e:
        return False, f"บันทึกไม่สำเร็จ: {e}"

def db_read():
    url, key = supabase_config()
    if not url or not key:
        return None, "ยังไม่ได้ตั้งค่า Supabase"
    endpoint = f"{url}/rest/v1/warehouse_sites?select=id,created_at,site,notes,risk_score,risk_label,points,risk_checks,elevations_model_m&order=created_at.desc"
    try:
        r = requests.get(endpoint, headers=supabase_headers(key), timeout=20)
        if r.status_code != 200:
            return None, f"อ่านฐานข้อมูลไม่สำเร็จ ({r.status_code}): {r.text[:300]}"
        return r.json(), None
    except Exception as e:
        return None, str(e)

def risk_assessment(selected):
    score = sum(weight for label, weight in CHECKS if selected.get(label, False))
    if score >= 10:
        label, advice = "สัญญาณเสี่ยงสูง", "ควรตรวจประวัติน้ำท่วมและระดับพื้นจริงอย่างละเอียดก่อนพิจารณาเช่า"
    elif score >= 5:
        label, advice = "ควรตรวจเพิ่ม", "ควรถามประวัติน้ำท่วม ตรวจรอยน้ำและการระบายน้ำ"
    else:
        label, advice = "พบสัญญาณที่เลือกไว้น้อย", "ไม่ได้แปลว่าปลอดภัย ต้องยืนยันประวัติน้ำท่วมและระดับพื้นจริง"
    return score, label, advice

st.title("🏭 เช็กระดับโกดังและคัดกรองน้ำท่วม")
st.caption("บันทึก 3 จุด • ประเมินสัญญาณเสี่ยง • เก็บประวัติโกดังร่วมกัน")
st.warning("เครื่องมือนี้ใช้คัดกรองเบื้องต้น ไม่ใช่การรับรองความปลอดภัยจากน้ำท่วม ระดับจาก GPS/แบบจำลองภูมิประเทศอาจคลาดเคลื่อนหลายเมตร จึงใช้ยืนยันความต่างระดับ 10–50 ซม. ไม่ได้")

tab_check, tab_history, tab_how = st.tabs(["📍 ตรวจโกดัง", "📚 ประวัติร่วม", "ℹ️ วิธีใช้"])

with tab_check:
    if "points" not in st.session_state:
        st.session_state.points = {"A": None, "B": None, "C": None}
    if "last_geo" not in st.session_state:
        st.session_state.last_geo = None
    if "elevations" not in st.session_state:
        st.session_state.elevations = None

    site = st.text_input("ชื่อโครงการ / โกดัง", placeholder="เช่น อรุณสุนทรี มินิแฟคตอรี่")
    notes = st.text_area("บันทึกเพิ่มเติม", placeholder="เช่น มีรอยน้ำ น้ำขังหน้าประตู เจ้าของแจ้งประวัติน้ำท่วม")
    st.subheader("1. บันทึกตำแหน่งจากโทรศัพท์")
    st.info("กดปุ่มขอตำแหน่งใหม่ แล้วรอให้ค่าพิกัด/ความแม่นยำอัปเดตทุกครั้งก่อนบันทึก A, B หรือ C")
    geo = streamlit_geolocation()
    if geo and geo.get("latitude") is not None and geo.get("longitude") is not None:
        new_geo = {
            "lat": float(geo["latitude"]), "lon": float(geo["longitude"]),
            "accuracy_m": float(geo["accuracy"]) if geo.get("accuracy") is not None else None,
            "captured_at": datetime.now(timezone.utc).isoformat()
        }
        previous_geo = st.session_state.last_geo
        # Do not overwrite a better current fix with a clearly worse fix.
        if previous_geo is None or (
            (new_geo["accuracy_m"] is not None and previous_geo.get("accuracy_m") is not None
             and new_geo["accuracy_m"] <= previous_geo["accuracy_m"])
            or (new_geo["accuracy_m"] is not None and previous_geo.get("accuracy_m") is None)
            or (new_geo["accuracy_m"] is None and previous_geo.get("accuracy_m") is None)
        ):
            st.session_state.last_geo = new_geo
        acc = st.session_state.last_geo.get("accuracy_m")
        st.success(f"พิกัดพร้อมใช้ {st.session_state.last_geo['lat']:.6f}, {st.session_state.last_geo['lon']:.6f}" +
                   (f" • ความแม่นยำแนวราบ ±{acc:.0f} ม." if acc is not None else " • ไม่ทราบค่าความแม่นยำ"))
        if acc is None:
            st.warning("เบราว์เซอร์ไม่ได้ส่งค่าความแม่นยำ GPS มา ควรตรวจตำแหน่งบนแผนที่ก่อนบันทึก")
        elif acc > 50:
            st.error(f"GPS ยังคลาดเคลื่อนสูง (±{acc:.0f} ม.) ไม่ควรใช้พิกัดนี้ระบุจุดตรวจโกดัง ให้กดขอตำแหน่งใหม่และรอให้แม่นยำขึ้น")
        elif acc > 20:
            st.warning(f"GPS คลาดเคลื่อนประมาณ ±{acc:.0f} ม. ควรรอให้ดีขึ้นและตรวจตำแหน่งกับแผนที่ก่อนบันทึก")
        else:
            st.caption("ค่าความแม่นยำแนวราบดีขึ้น แต่ยังไม่ใช่การวัดระดับความสูงของพื้น")

    cols = st.columns(3)
    for i, k in enumerate(["A", "B", "C"]):
        with cols[i]:
            st.markdown(f"**{k} — {LABELS[k]}**")
            p = st.session_state.points[k]
            if p:
                st.caption(f"{p['lat']:.6f}, {p['lon']:.6f}")
            if st.button(f"บันทึก {k}", key=f"save_{k}", use_container_width=True):
                fix = st.session_state.last_geo
                if not fix:
                    st.error("กดขอตำแหน่ง GPS ก่อน")
                elif fix.get("accuracy_m") is None:
                    st.error("ยังไม่มีค่าความแม่นยำ GPS จึงยังไม่บันทึก กรุณาขอตำแหน่งใหม่")
                elif fix["accuracy_m"] > 50:
                    st.error(f"ยังไม่บันทึก {k}: GPS คลาดเคลื่อน ±{fix['accuracy_m']:.0f} ม. ให้ขอตำแหน่งใหม่และรอให้ต่ำกว่า 50 ม. ก่อน")
                else:
                    same_as = [other for other in "ABC" if other != k and st.session_state.points.get(other)
                               and abs(st.session_state.points[other]["lat"] - fix["lat"]) < 0.00015
                               and abs(st.session_state.points[other]["lon"] - fix["lon"]) < 0.00015]
                    if same_as:
                        st.error(f"ยังไม่บันทึก {k}: พิกัดนี้ใกล้กับจุด {', '.join(same_as)} มาก ตรวจว่าคุณเดินไปตำแหน่งใหม่และขอ GPS ใหม่แล้วหรือยัง")
                    else:
                        st.session_state.points[k] = dict(fix)
                        st.session_state.elevations = None
                        st.success(f"บันทึกจุด {k} แล้ว")
                        st.rerun()
            if p and st.button(f"ล้าง {k}", key=f"clear_{k}", use_container_width=True):
                st.session_state.points[k] = None
                st.session_state.elevations = None
                st.rerun()

    points = st.session_state.points
    existing = [p for p in points.values() if p]
    center = [sum(p["lat"] for p in existing)/len(existing), sum(p["lon"] for p in existing)/len(existing)] if existing else [13.95, 100.45]
    map_obj = folium.Map(location=center, zoom_start=14, control_scale=True)
    colors = {"A": "blue", "B": "orange", "C": "green"}
    for k, p in points.items():
        if p:
            folium.Marker([p["lat"], p["lon"]], tooltip=f"{k} — {LABELS[k]}",
                          icon=folium.Icon(color=colors[k])).add_to(map_obj)
    st_folium(map_obj, height=300, use_container_width=True, returned_objects=[])

    if st.button("ดึงระดับภูมิประเทศโดยประมาณ", use_container_width=True):
        if not all(points[k] for k in ["A", "B", "C"]):
            st.error("บันทึก A, B, C ให้ครบก่อน")
        else:
            try:
                r = requests.get("https://api.open-meteo.com/v1/elevation",
                    params={"latitude": ",".join(str(points[k]["lat"]) for k in "ABC"),
                            "longitude": ",".join(str(points[k]["lon"]) for k in "ABC")}, timeout=20)
                r.raise_for_status()
                values = r.json().get("elevation")
                if not values or len(values) != 3:
                    raise ValueError("ข้อมูลระดับความสูงไม่ครบ")
                st.session_state.elevations = dict(zip("ABC", map(float, values)))
                st.info("ระดับนี้มาจากแบบจำลองภูมิประเทศ ไม่ใช่ค่าระดับพื้นจริง และอาจไม่ละเอียดพอสำหรับส่วนต่างระดับ 10–50 ซม.")
            except Exception as e:
                st.error(f"ดึงข้อมูลไม่สำเร็จ: {e}")

    if st.session_state.elevations:
        e = st.session_state.elevations
        st.dataframe(pd.DataFrame([{"จุด": k, "ตำแหน่ง": LABELS[k], "ระดับภูมิประเทศโดยประมาณ (ม.)": e[k]} for k in "ABC"]), hide_index=True, use_container_width=True)
        for title, delta in [("B เทียบ A", e["B"]-e["A"]), ("C เทียบ B", e["C"]-e["B"]), ("C เทียบ A", e["C"]-e["A"])]:
            st.write(f"- {title}: {'สูงกว่า' if delta > 0 else 'ต่ำกว่า' if delta < 0 else 'ใกล้เคียง'} {abs(delta):.1f} ม. (แบบจำลองเท่านั้น)")
        st.caption("ค่าระดับภูมิประเทศอาจไม่สะท้อนพื้นถนน/พื้นโกดังจริง")

    st.subheader("2. เช็กลิสต์หน้างาน")
    selected = {label: st.checkbox(label, key="risk_"+label) for label, _ in CHECKS}
    score, risk_label, advice = risk_assessment(selected)
    st.metric("คะแนนสัญญาณเสี่ยง (ไม่ใช่ความน่าจะเป็น)", f"{score}", risk_label)
    st.write(advice)

    report = {
        "site": site, "notes": notes, "created_at": datetime.now(timezone.utc).isoformat(),
        "points": points, "risk_checks": selected, "risk_score": score,
        "risk_label": risk_label, "elevations_model_m": st.session_state.elevations
    }
    st.download_button("ดาวน์โหลดรายงาน JSON", json.dumps(report, ensure_ascii=False, indent=2),
                       file_name="warehouse-report.json", mime="application/json", use_container_width=True)

    if st.button("💾 บันทึกลงประวัติส่วนกลาง", type="primary", use_container_width=True):
        if not site.strip():
            st.error("กรุณาใส่ชื่อโครงการ/โกดังก่อน")
        elif not any(points.values()):
            st.error("กรุณาบันทึกพิกัดอย่างน้อย 1 จุด")
        else:
            record = {
                "site": site.strip(), "notes": notes.strip(),
                "risk_score": score, "risk_label": risk_label,
                "points": points, "risk_checks": selected,
                "elevations_model_m": st.session_state.elevations,
                "created_at": datetime.now(timezone.utc).isoformat()
            }
            ok, message = db_insert(record)
            (st.success if ok else st.error)(message)

with tab_history:
    st.subheader("ประวัติที่ทุกคนบันทึก")
    rows, error = db_read()
    if error:
        st.info("ฐานข้อมูลส่วนกลางยังไม่ได้เชื่อมต่อ หรือยังตั้งค่าไม่ครบ")
        st.caption(error)
    elif not rows:
        st.info("ยังไม่มีรายการบันทึก")
    else:
        history_df = pd.DataFrame([{
            "รหัส": row.get("id"),
            "วันที่บันทึก": pd.to_datetime(row.get("created_at"), errors="coerce").strftime("%Y-%m-%d %H:%M") if row.get("created_at") else "",
            "โครงการ / โกดัง": row.get("site", ""),
            "คะแนนเสี่ยง": row.get("risk_score", 0),
            "สรุปความเสี่ยง": row.get("risk_label", ""),
            "บันทึกเพิ่มเติม": row.get("notes", "") or ""
        } for row in rows])
        st.dataframe(history_df, hide_index=True, use_container_width=True)
        st.download_button("ส่งออก CSV", history_df.to_csv(index=False).encode("utf-8-sig"),
                           file_name="warehouse-history.csv", mime="text/csv", use_container_width=True)

        st.markdown("---")
        st.subheader("เปิดดูรายละเอียดรายการย้อนหลัง")
        def history_label(row):
            stamp = pd.to_datetime(row.get("created_at"), errors="coerce")
            stamp_text = stamp.strftime("%Y-%m-%d %H:%M") if not pd.isna(stamp) else "ไม่ทราบวันที่"
            return f'#{row.get("id")} · {row.get("site") or "ไม่ระบุชื่อ"} · {stamp_text}'
        chosen = st.selectbox("เลือกโกดัง/รายการที่ต้องการดู", rows, format_func=history_label, key="history_detail_select")
        if chosen:
            st.markdown(f"### {chosen.get('site') or 'ไม่ระบุชื่อโครงการ / โกดัง'}")
            stamp = pd.to_datetime(chosen.get("created_at"), errors="coerce")
            if not pd.isna(stamp):
                st.caption("วันที่บันทึก: " + stamp.strftime("%Y-%m-%d %H:%M"))
            st.metric("คะแนนสัญญาณเสี่ยง", chosen.get("risk_score", 0), chosen.get("risk_label", ""))
            if chosen.get("notes"):
                st.markdown("**บันทึกเพิ่มเติม**")
                st.write(chosen["notes"])

            saved_points = chosen.get("points") or {}
            saved_elevations = chosen.get("elevations_model_m") or {}
            if isinstance(saved_points, dict) and any(saved_points.get(k) for k in "ABC"):
                st.markdown("#### ตำแหน่ง A / B / C ที่บันทึกไว้")
                map_points = [(k, saved_points[k]) for k in "ABC"
                              if isinstance(saved_points.get(k), dict)
                              and saved_points[k].get("lat") is not None
                              and saved_points[k].get("lon") is not None]
                if map_points:
                    center = [sum(p["lat"] for _, p in map_points)/len(map_points),
                              sum(p["lon"] for _, p in map_points)/len(map_points)]
                    detail_map = folium.Map(location=center, zoom_start=15, control_scale=True)
                    detail_colors = {"A": "blue", "B": "orange", "C": "green"}
                    for k, p in map_points:
                        label = f"{k} — {LABELS[k]}"
                        folium.Marker([p["lat"], p["lon"]], tooltip=label,
                                      popup=f"{label}<br>{p['lat']:.6f}, {p['lon']:.6f}",
                                      icon=folium.Icon(color=detail_colors[k])).add_to(detail_map)
                    st_folium(detail_map, height=300, use_container_width=True,
                              key=f"history_map_{chosen.get('id')}", returned_objects=[])
                    point_rows = []
                    for k in "ABC":
                        p = saved_points.get(k)
                        if not isinstance(p, dict):
                            continue
                        elev = saved_elevations.get(k) if isinstance(saved_elevations, dict) else None
                        point_rows.append({
                            "จุด": k, "ตำแหน่ง": LABELS[k],
                            "ละติจูด": p.get("lat"), "ลองจิจูด": p.get("lon"),
                            "ความแม่นยำ GPS (ม.)": p.get("accuracy_m"),
                            "ระดับภูมิประเทศโดยประมาณ (ม.)": elev
                        })
                    st.dataframe(pd.DataFrame(point_rows), hide_index=True, use_container_width=True)
            else:
                st.info("รายการนี้บันทึกไว้โดยไม่มีพิกัด A/B/C")

            if isinstance(saved_elevations, dict) and all(saved_elevations.get(k) is not None for k in "ABC"):
                st.markdown("#### ผลต่างระดับภูมิประเทศโดยประมาณ")
                for title, delta in [
                    ("B เทียบ A", float(saved_elevations["B"]) - float(saved_elevations["A"])),
                    ("C เทียบ B", float(saved_elevations["C"]) - float(saved_elevations["B"])),
                    ("C เทียบ A", float(saved_elevations["C"]) - float(saved_elevations["A"]))
                ]:
                    st.write(f"- {title}: {'สูงกว่า' if delta > 0 else 'ต่ำกว่า' if delta < 0 else 'ใกล้เคียง'} {abs(delta):.1f} ม. (แบบจำลองเท่านั้น)")
            else:
                st.info("รายการนี้ยังไม่มีค่าระดับภูมิประเทศที่คำนวณไว้ตอนบันทึก")

            saved_checks = chosen.get("risk_checks") or {}
            st.markdown("#### เช็กลิสต์สัญญาณเสี่ยงที่บันทึกไว้")
            checked_items = [label for label, _ in CHECKS if isinstance(saved_checks, dict) and saved_checks.get(label)]
            if checked_items:
                for item in checked_items:
                    st.write(f"- ✓ {item}")
            else:
                st.write("ไม่มีรายการที่เลือกไว้")
            st.caption("ค่าระดับจากแบบจำลองภูมิประเทศไม่ใช่ระดับพื้นถนน/พื้นโกดังที่สำรวจจริง และไม่สามารถยืนยันส่วนต่างระดับ 10–50 ซม. ได้")

with tab_how:
    st.markdown("""
1. เปิดลิงก์ผ่าน Safari/Chrome และอนุญาต Location
2. ที่จุด A ถนนใหญ่ กดขอตำแหน่ง แล้วกดบันทึก A
3. ทำซ้ำที่ B ถนนภายใน และ C พื้นโกดัง
4. ติ๊กสัญญาณน้ำท่วมที่พบจริง แล้วบันทึกลงประวัติส่วนกลาง
5. เปิดแท็บประวัติร่วมเพื่อเปรียบเทียบโกดังที่ทุกคนบันทึก

**ข้อควรระวัง:** คะแนนเป็นตัวช่วยจัดลำดับการตรวจ ไม่ใช่ความน่าจะเป็นน้ำท่วม หากต้องการความต่างระดับ 10–50 ซม. ต้องใช้การถ่ายระดับหน้างานที่เหมาะสมและตรวจประวัติน้ำท่วมจริง
""")
