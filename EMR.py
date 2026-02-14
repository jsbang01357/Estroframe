import streamlit as st
import json
import hashlib
from datetime import datetime
import inout
import utils


def _uploader_signature(files):
    """업로드 목록 시그니처 생성 (내용 해시 기반, 동일 업로드 재적용 방지)"""
    if not files:
        return ""
    parts = []
    for i, f in enumerate(files):
        name = getattr(f, "name", f"unnamed_{i}")
        size = getattr(f, "size", -1)
        digest = "nohash"
        try:
            if hasattr(f, "getvalue"):
                content = f.getvalue()
                if isinstance(content, bytes):
                    digest = hashlib.sha256(content).hexdigest()
                else:
                    digest = hashlib.sha256(str(content).encode("utf-8", errors="ignore")).hexdigest()
            elif hasattr(f, "read"):
                pos = f.tell() if hasattr(f, "tell") else None
                raw = f.read()
                if isinstance(raw, str):
                    raw = raw.encode("utf-8", errors="ignore")
                digest = hashlib.sha256(raw or b"").hexdigest()
                if pos is not None and hasattr(f, "seek"):
                    f.seek(pos)
        except (OSError, ValueError, TypeError):
            # 해시 계산 실패 시 최소 식별자 fallback
            digest = f"{name}:{size}"
        parts.append(f"{i}:{name}:{size}:{digest}")
    return "|".join(parts)


def _normalize_patient_payload(raw):
    """EMR 로드 데이터의 최소 필수 구조를 보정합니다."""
    if not isinstance(raw, dict):
        return None

    profile = raw.get("profile")
    if not isinstance(profile, dict):
        profile = {}

    # 최소 필수값 보정
    profile.setdefault("name", utils.t("default_user"))
    profile.setdefault("weight", 60.0)
    profile.setdefault("height", 170.0)
    profile.setdefault("age", 25)
    profile.setdefault("ast", 20.0)
    profile.setdefault("alt", 20.0)
    profile.setdefault("body_fat", 22.0)

    normalized = {
        "profile": profile,
        "schedule": raw.get("schedule") if isinstance(raw.get("schedule"), list) else [],
        "schedule_b": raw.get("schedule_b") if isinstance(raw.get("schedule_b"), list) else [],
        "compare_mode": bool(raw.get("compare_mode", False)),
        "calibration_factors": raw.get("calibration_factors") if isinstance(raw.get("calibration_factors"), dict) else {},
        "lab_history": raw.get("lab_history") if isinstance(raw.get("lab_history"), dict) else {},
    }
    return normalized

def init_session():
    """EMR 관련 세션 상태 초기화"""
    if 'patient_db' not in st.session_state:
        st.session_state.patient_db = {}
    if "db_uploader_last_sig" not in st.session_state:
        st.session_state.db_uploader_last_sig = ""
    if "db_mount_mode" not in st.session_state:
        st.session_state.db_mount_mode = "merge"
    if "db_mount_apply" not in st.session_state:
        st.session_state.db_mount_apply = False

def handle_mounting():
    """리포트 탭의 업로더와 연동하여 환자 데이터를 세션 DB에 마운트"""
    files = st.session_state.get("db_uploader")
    if files:
        current_sig = _uploader_signature(files)
        force_apply = bool(st.session_state.pop("db_mount_apply", False))
        mount_mode = st.session_state.get("db_mount_mode", "merge")

        # 같은 업로드 파일이면 재적용하지 않음 (데이터 되돌림 방지)
        if not force_apply and current_sig == st.session_state.get("db_uploader_last_sig", ""):
            return

        new_db = {}
        failed_files = []
        for f in files:
            try:
                if f.name.endswith('.json'):
                    f.seek(0)
                    content = json.load(f)
                    # DB 파일인지 단일 환자 파일인지 판별
                    if isinstance(content, dict) and content.get("version") == "DB_1.0":
                        new_db.update(content.get("patients", {}))
                    else:
                        p = content.get("profile", {})
                        if p:
                            label = f"{p.get('name', 'Unknown')} ({p.get('patient_id', 'No ID')})"
                            new_db[label] = content
                elif f.name.endswith('.csv'):
                    f.seek(0)
                    csv_db = inout.DataManager.load_db_from_csv(f)
                    new_db.update(csv_db)
            except (json.JSONDecodeError, UnicodeDecodeError, ValueError, KeyError, TypeError, OSError) as e:
                err_type = type(e).__name__
                failed_files.append(f.name)
                st.warning(f"[EMR] 파일 로드 실패: {f.name} | {err_type}: {e}")
                continue
        if new_db:
            if mount_mode == "replace":
                st.session_state.patient_db = dict(new_db)
            else:
                merged_db = dict(st.session_state.get("patient_db", {}))
                merged_db.update(new_db)
                st.session_state.patient_db = merged_db

            st.toast(
                utils.t("db_mount_mode_applied").format(mode=mount_mode.upper(), count=len(new_db)),
                icon="🗂️",
            )

        st.session_state.db_uploader_last_sig = current_sig
        st.session_state.db_mount_mode = "merge"

        if failed_files:
            st.caption(f"[EMR] 실패 파일 {len(failed_files)}개: {', '.join(failed_files)}")

def render_sidebar_selector():
    """사이드바 최상단 환자 검색 및 선택 UI"""
    if not st.session_state.patient_db:
        return

    st.header(utils.t("sidebar_patient"))
    selected_p = st.selectbox(
        utils.t("search_patient"), 
        options=[utils.t("db_select_default")] + list(st.session_state.patient_db.keys()),
        help="리포트 탭에서 업로드한 환자 목록입니다."
    )
    
    if selected_p != utils.t("db_select_default"):
        if st.button(utils.t("load_data_btn"), type="primary", width="stretch"):
            raw_data = st.session_state.patient_db[selected_p]
            data_to_load = _normalize_patient_payload(raw_data)
            if data_to_load is None:
                st.error(f"[EMR] 환자 데이터 형식이 올바르지 않습니다: {selected_p}")
                return
            
            # 세션 데이터 복원
            st.session_state.user_profile = data_to_load.get("profile")
            st.session_state.user_name = st.session_state.user_profile.get("name", "사용자")
            st.session_state.drug_schedule = data_to_load.get("schedule")
            st.session_state.drug_schedule_b = data_to_load.get("schedule_b", [])
            st.session_state.compare_mode = data_to_load.get("compare_mode", False)
            
            calib = data_to_load.get("calibration_factors")
            st.session_state.calibration_factors = calib if calib else {
                "Injection": 1.0, "Oral": 1.0, "Transdermal": 1.0, "Sublingual": 1.0
            }
            st.session_state.lab_history = data_to_load.get("lab_history", {})
            
            st.toast(utils.t("load_success_toast").format(name=selected_p), icon="✅")
            st.rerun()
    st.markdown("---")

def render_tab_management():
    """리포트 탭의 DB 관리 UI"""
    st.subheader(utils.t("update_db_header"))
    if st.button(utils.t("update_db_btn"), width="stretch"):
        p = st.session_state.user_profile
        label = f"{p.get('name', 'Unknown')} ({p.get('patient_id', 'No ID')})"
        
        current_data = {
            "profile": st.session_state.user_profile,
            "schedule": st.session_state.drug_schedule,
            "schedule_b": st.session_state.drug_schedule_b,
            "compare_mode": st.session_state.compare_mode,
            "calibration_factors": st.session_state.calibration_factors,
            "lab_history": st.session_state.lab_history
        }
        st.session_state.patient_db[label] = current_data
        st.success(utils.t("patient_updated_msg").format(label=label))
        st.rerun()

    st.markdown("---")
    st.subheader(utils.t("mount_db_header"))
    st.caption(utils.t("mount_db_caption"))
    
    # 업로더 UI (로직은 handle_mounting에서 처리)
    st.file_uploader(utils.t("db_uploader_label"), type=["json", "csv"], accept_multiple_files=True, key="db_uploader")
    if st.session_state.get("db_uploader"):
        st.caption(utils.t("db_mount_merge_default_note"))
        if st.button(utils.t("db_mount_replace_btn"), width="stretch"):
            st.session_state.db_mount_mode = "replace"
            st.session_state.db_mount_apply = True
            st.rerun()
    
    if st.session_state.patient_db:
        st.success(utils.t("mount_success_msg").format(count=len(st.session_state.patient_db)))
        
        # 통합 DB 다운로드
        db_csv = inout.DataManager.export_db_to_csv(st.session_state.patient_db)
        db_filename = f"Hospital_{datetime.now().strftime('%Y%m%d')}_DB.csv"
        st.download_button(
            utils.t("download_db_btn"), 
            db_csv, 
            db_filename, 
            "text/csv", 
            width="stretch",
            help="마운트된 모든 환자 정보를 엑셀에서 열 수 있는 CSV 파일로 저장합니다.",
            key="emr_csv_download_btn"
        )
