import streamlit as st
import numpy as np
from datetime import datetime, timedelta
import socket
import os
import sys
import re
import base64
import streamlit.components.v1 as components

# Custom Modules
import data
import analysis
import inout
import EMR
import utils
import ui_components as ui
import plot
import simulator as sim


# -----------------------------------------------------------------------------
# 0. 오프라인/온라인 환경 확인
# -----------------------------------------------------------------------------
def is_local_environment():
    # 1) 명시적 설정값(환경변수) 우선
    #    - true: 1, true, yes, on
    #    - false: 0, false, no, off
    for env_key in ("ESTROFRAME_FORCE_OFFLINE", "FORCE_OFFLINE_MODE"):
        raw = os.getenv(env_key)
        if raw is None:
            continue
        val = str(raw).strip().lower()
        if val in ("1", "true", "yes", "on"):
            return True
        if val in ("0", "false", "no", "off"):
            return False

    # 2) fallback: 네트워크 힌트 기반 추정
    try:
        hostname = socket.gethostname()
        ip_addr = socket.gethostbyname(hostname)
        if "localhost" in hostname.lower():
            return True
        return ip_addr.startswith("127.") or ip_addr.startswith("10.") or ip_addr.startswith("192.168.")
    except OSError:
        # stlite/브라우저 런타임 등에서 소켓 조회가 제한될 수 있음
        return True

IS_OFFLINE = is_local_environment()


def _offline_onboarding_flag_path():
    """오프라인 랜딩 완료 상태를 영구 저장할 파일 경로"""
    if getattr(sys, "frozen", False):
        base_dir = os.path.dirname(sys.executable)
    else:
        base_dir = os.path.abspath(".")
    return os.path.join(base_dir, ".estroframe_offline_onboarding_done")


def _load_offline_onboarding_done():
    try:
        with open(_offline_onboarding_flag_path(), "r", encoding="utf-8") as f:
            return f.read().strip() == "1"
    except OSError:
        return False


def _save_offline_onboarding_done():
    try:
        with open(_offline_onboarding_flag_path(), "w", encoding="utf-8") as f:
            f.write("1")
    except OSError:
        pass


def _mark_offline_onboarding_seen(stage):
    """오프라인에서 랜딩 2종 모두 본 경우 영구 스킵 처리"""
    if not IS_OFFLINE:
        return
    if stage == "disclaimer":
        st.session_state.offline_landing_seen_disclaimer = True
    elif stage == "welcome":
        st.session_state.offline_landing_seen_welcome = True

    if (
        st.session_state.get("offline_landing_seen_disclaimer", False)
        and st.session_state.get("offline_landing_seen_welcome", False)
        and not st.session_state.get("offline_onboarding_done", False)
    ):
        st.session_state.offline_onboarding_done = True
        _save_offline_onboarding_done()

# -----------------------------------------------------------------------------
# 1. 페이지 설정 (Page Configuration)
# -----------------------------------------------------------------------------
st.set_page_config(
    page_title="EstroFrame",
    page_icon="🧬",
    layout="wide",
    initial_sidebar_state="expanded"
)

# 커스텀 테마 CSS 적용
ui.apply_custom_theme()

# -----------------------------------------------------------------------------
# 2. 초기 로딩 및 세션 상태 초기화 (Splash Screen & Session Init)
# -----------------------------------------------------------------------------
# 앱이 처음 로드될 때 빈 화면 대신 로딩 애니메이션을 보여줍니다.
if "initialized" not in st.session_state:
    splash = st.empty()
    with splash.container():
        splash_html = """
            <div style="display: flex; flex-direction: column; align-items: center; justify-content: center; height: 80vh;">
                <div class="st-loader"></div>
                <h2 style="color: #FF69B4; margin-top: 20px; font-family: sans-serif; font-weight: bold;">EstroFrame</h2>
                <p style="color: #666; font-family: sans-serif; font-size: 0.9em;">__SPLASH_MSG__</p>
            </div>
            <style>
                .st-loader {
                    width: 50px;
                    height: 50px;
                    border: 5px solid #f3f3f3;
                    border-top: 5px solid #FF69B4;
                    border-radius: 50%;
                    animation: spin 1s linear infinite;
                }
                @keyframes spin { 0% { transform: rotate(0deg); } 100% { transform: rotate(360deg); } }
            </style>
        """
        st.markdown(splash_html.replace("__SPLASH_MSG__", utils.t("splash_msg")), unsafe_allow_html=True)

if 'lang' not in st.session_state:
    # URL 파라미터에서 언어 설정 확인 (링크 공유 시 언어 유지)
    url_lang = st.query_params.get("lang", "KO")
    if url_lang in ["KO", "EN"]:
        st.session_state.lang = url_lang
    else:
        st.session_state.lang = "KO"

# 세션 상태 초기화: 새로고침 시에도 데이터가 유지되도록 기본값 설정
if 'user_name' not in st.session_state:
    st.session_state.user_name = utils.t("default_user")
if 'drug_schedule' not in st.session_state:
    st.session_state.drug_schedule = []
if 'drug_schedule_b' not in st.session_state:
    st.session_state.drug_schedule_b = []
if 'compare_mode' not in st.session_state:
    st.session_state.compare_mode = False
if 'user_profile' not in st.session_state:
    st.session_state.user_profile = {
        "name": utils.t("default_user"),
        "weight": 60.0, "height": 170.0, "age": 25, "ast": 20.0, "alt": 20.0, "body_fat": 22.0,
        "first_hrt_date": datetime.now().date()
    }
if 'calibration_factors' not in st.session_state:
    # 경로별 기본값 1.0
    st.session_state.calibration_factors = {
        "Injection": 1.0, "Oral": 1.0, "Transdermal": 1.0, "Sublingual": 1.0
    }
if 'lab_history' not in st.session_state:
    st.session_state.lab_history = {} # 구조: { "Injection": [{"day": 14, "value": 150}, ...], ... }
if 'surgery_mode' not in st.session_state:
    st.session_state.surgery_mode = False
if 'stop_day' not in st.session_state:
    st.session_state.stop_day = 30
if 'is_smoker' not in st.session_state:
    st.session_state.is_smoker = False
if 'history_vte' not in st.session_state:
    st.session_state.history_vte = False
if 'start_date' not in st.session_state:
    # 서버 시간(UTC)에 9시간을 더해 한국/아시아권 사용자들이
    # '오늘 날짜'를 볼 확률을 높여줍니다. (단순 편의성)
    st.session_state.start_date = (datetime.utcnow() + timedelta(hours=9)).date()
if 'anesthesia_type' not in st.session_state:
    st.session_state.anesthesia_type = utils.t("anesthesia_gen")
if 'stop_date' not in st.session_state:
    st.session_state.stop_date = st.session_state.start_date + timedelta(days=30)
if 'resume_date' not in st.session_state:
    st.session_state.resume_date = st.session_state.start_date + timedelta(days=50)
if 'surgery_date' not in st.session_state:
    st.session_state.surgery_date = st.session_state.start_date + timedelta(days=44)
if 'has_spiro' not in st.session_state: st.session_state.has_spiro = False
if 'has_cpa' not in st.session_state: st.session_state.has_cpa = False
if 'has_p4' not in st.session_state: st.session_state.has_p4 = False
if 'has_gnrh' not in st.session_state: st.session_state.has_gnrh = False
if 'selected_interactors' not in st.session_state: st.session_state.selected_interactors = []
if 'resume_day' not in st.session_state:
    st.session_state.resume_day = 50
if 'surg_sim_duration' not in st.session_state:
    st.session_state.surg_sim_duration = max(30, int(st.session_state.resume_day + 30))
if 'unit_choice' not in st.session_state:
    st.session_state.unit_choice = "pg/mL"
if "disclaimer_agreed" not in st.session_state:
    st.session_state.disclaimer_agreed = False
if "offline_landing_seen_disclaimer" not in st.session_state:
    st.session_state.offline_landing_seen_disclaimer = False
if "offline_landing_seen_welcome" not in st.session_state:
    st.session_state.offline_landing_seen_welcome = False
if "offline_onboarding_done" not in st.session_state:
    st.session_state.offline_onboarding_done = IS_OFFLINE and _load_offline_onboarding_done()

# EMR 업로더 로직이 rerun을 유발하므로 탭 생성 전 처리
EMR.init_session()
EMR.handle_mounting()
inout.DataManager.handle_import_session()

# -----------------------------------------------------------------------------
# 3. 캐싱 함수 (Caching Functions for Optimization)
# -----------------------------------------------------------------------------
@st.cache_resource
def get_analyzer(weight, age, ast, alt, body_fat, height):
    """Analyzer 객체 생성 캐싱: 사용자 프로필이 변경되지 않으면 객체를 재사용"""
    return analysis.HormoneAnalyzer(
        user_weight=weight, user_age=age, ast=ast, alt=alt, body_fat=body_fat, user_height=height
    )

# -----------------------------------------------------------------------------
# 4. 사이드바 렌더링 (Sidebar Rendering)
# -----------------------------------------------------------------------------
allow_app_without_landing = IS_OFFLINE and st.session_state.get("offline_onboarding_done", False)
with st.sidebar:
    # 동의 전 랜딩 화면에서는 lang 위젯 충돌 방지를 위해
    # 전체 사이드바(UI의 key="lang" 포함)를 렌더링하지 않습니다.
    if st.session_state.get("disclaimer_agreed", False) or allow_app_without_landing:
        IS_OFFLINE = ui.render_sidebar(IS_OFFLINE)
    else:
        st.title("🧬 EstroFrame")
        st.caption("Architecting Your Biology")

# -----------------------------------------------------------------------------
# 5. 로딩 화면 종료 (Clear Splash Screen)
# -----------------------------------------------------------------------------
if "initialized" not in st.session_state:
    st.session_state.initialized = True
    splash.empty()

# -----------------------------------------------------------------------------
# 6. Global Landing Page (사용 동의 -> 사용 설명 -> 약물 입력)
# -----------------------------------------------------------------------------
def _set_landing_lang(lang):
    st.session_state.lang = lang
    st.query_params["lang"] = lang
    defaults = {
        "KO": utils.TRANSLATIONS.get("KO", {}).get("default_user", "사용자"),
        "EN": utils.TRANSLATIONS.get("EN", {}).get("default_user", "user"),
    }
    current_name = st.session_state.user_profile.get("name")
    if current_name in defaults.values():
        new_default = defaults.get(lang, "user")
        st.session_state.user_profile["name"] = new_default
        st.session_state.user_name = new_default

st.title(utils.t("dashboard_title"))
if not st.session_state.disclaimer_agreed and not allow_app_without_landing:
    with st.container():
        _mark_offline_onboarding_seen("disclaimer")
        landing_lang = st.radio(
            utils.t("landing_lang_label"),
            ["KO", "EN"],
            horizontal=True,
            index=0 if st.session_state.lang == "KO" else 1,
            key="landing_lang_selector"
        )
        if landing_lang != st.session_state.lang:
            _set_landing_lang(landing_lang)
            st.rerun()

        st.warning(utils.t("landing_disclaimer_title"))
        st.markdown(f"""
        {utils.t("landing_disclaimer_intro")}
        
        {utils.t("landing_disclaimer_item_1")}
        {utils.t("landing_disclaimer_item_2")}
        {utils.t("landing_disclaimer_item_3")}
        
        {utils.t("landing_disclaimer_question")}
        """)
        
        if st.button(utils.t("landing_agree_btn"), type="primary"):
            st.session_state.disclaimer_agreed = True
            st.rerun()
    
    # 동의 안 하면 여기서 멈춤 (앱 내용 안 보여줌)
    st.stop()

if not st.session_state.drug_schedule and not allow_app_without_landing:
    with st.container():
        _mark_offline_onboarding_seen("welcome")
        st.info(utils.t("landing_welcome_title"))
        st.markdown(f"""
        {utils.t("landing_steps_title")}
        {utils.t("landing_step_1")}
        {utils.t("landing_step_2")}
        {utils.t("landing_step_3")}
        """)
        
        # 데모 버튼 (선택사항)
        if st.button(utils.t("landing_demo_btn"), type="primary"):
            st.session_state.drug_schedule = [
                {"name": "Estradiol Valerate (Progynon Depot)", "type": "Injection", "dose": 10.0, "interval": 14.0, "id": "demo1"}
            ]
            st.rerun()

    ui.render_footer()
    st.stop()

# -----------------------------------------------------------------------------
# 7. 메인 콘텐츠 (Main Content)
# -----------------------------------------------------------------------------
# 탭 구성 정의 (동적 생성)
tabs_config = [
    {"title": utils.t("tab_sim"), "key": "sim"},
    {"title": utils.t("tab_safe"), "key": "safe"},
    {"title": utils.t("tab_cal"), "key": "cal"},
    {"title": utils.t("tab_surg"), "key": "surg"},
    {"title": utils.t("tab_rep"), "key": "rep"},
    {"title": utils.t("tab_faq"), "key": "faq"}
]

# 탭 객체 생성 및 매핑
tab_objs = st.tabs([t["title"] for t in tabs_config])
tabs = {config["key"]: obj for config, obj in zip(tabs_config, tab_objs)}

# Analyzer 인스턴스 생성 (analysis.py)
# [최적화] 캐싱된 인스턴스를 사용하여 불필요한 객체 생성 방지
analyzer = get_analyzer(
    st.session_state.user_profile['weight'],
    st.session_state.user_profile['age'],
    st.session_state.user_profile.get('ast', 20.0),
    st.session_state.user_profile.get('alt', 20.0),
    st.session_state.user_profile.get('body_fat', 22.0),
    st.session_state.user_profile.get('height', 170.0)
)

# 전역 변수로 fig 선언 (리포트 탭 등에서 재사용하기 위함)
fig = None 

# -----------------------------------------------------------------------------
# 8. 각 탭 내부 로직 (엄격한 들여쓰기 확인)
# -----------------------------------------------------------------------------

# [Tab 1: Simulation]
with tabs["sim"]:
    sim_stats = sim.render_simulator_tab(analyzer)

# [Tab 2: Safety Center]
with tabs["safe"]:
    st.header(utils.t("safe_center_title"))
    
    # Missed Dose 계산기
    ui.render_missed_dose_checker()
    st.markdown("---")

    st.subheader(utils.t("emergency_self_check_title"))
    st.caption(utils.t("emergency_self_check_caption"))

    with st.container(border=True):
        st.markdown(utils.t("dvt_title"))
        st.markdown(utils.t("dvt_symptoms"))
    
    with st.container(border=True):
        st.error(utils.t("pe_title"))
        st.markdown(utils.t("pe_symptoms"))

    # 하단 팁
    st.markdown("---")
    st.info(utils.t("safe_center_tip"))

# [Tab 3: Calibration]
with tabs["cal"]:
    ui.render_calibration_tab(analyzer)

# [Tab 4: Surgery Planning]
with tabs["surg"]:
    st.header(utils.t("tab_surg"))

    # 1. 호르몬 시작일 입력 (Moved from Sidebar)
    st.subheader(utils.t("first_hrt_date_label"))
    first_date = st.date_input(
        utils.t("first_hrt_date_label"),
        value=st.session_state.user_profile.get("first_hrt_date", datetime.now().date()),
        help=utils.t("first_hrt_date_help"),
        label_visibility="collapsed"
    )
    st.session_state.user_profile["first_hrt_date"] = first_date

    # -------------------------------------------------------------------------
    # 🌸 여성화 단계 예측 (Feminization Stage)
    # -------------------------------------------------------------------------
    st.markdown("---")
    st.subheader(utils.t("feminization_progress_title"))
    total_days = (datetime.now().date() - st.session_state.user_profile["first_hrt_date"]).days
    total_months = max(0, total_days) / 30.44

    if sim_stats:
        avg_pg = sim_stats['avg'] if st.session_state.unit_choice == "pg/mL" else utils.convert_back_from_pmol(sim_stats['avg'])
    else:
        avg_pg = 0.0
    stage_name, stage_desc = utils.predict_feminization_stage(total_months, avg_pg)

    st.success(utils.t("feminization_current_status").format(stage=stage_name))
    st.write(f"_{stage_desc}_")
    st.markdown("---")

    # -------------------------------------------------------------------------
    # 🌸 수술 관리
    # -------------------------------------------------------------------------
    st.subheader(utils.t("surg_title"))
    st.markdown(utils.t("surg_intro"))
   
    
    # [추가 기능] 수술 종류별 가이드라인 선택
    # 키는 데이터 로직용으로 유지하고, 표시는 번역된 문자열로 처리
    surg_options = list(data.SURGERY_TYPES.keys())
    selected_surg = st.selectbox(utils.t("surg_type_label"), surg_options, format_func=lambda x: utils.t(x))
    st.session_state.selected_surgery_type = selected_surg
    
    surg_info = data.SURGERY_TYPES[selected_surg]
    
    # [위치 이동 및 로직 추가] VTE 위험 점수를 먼저 계산하여 가이드라인에 반영
    has_oral = any(str(d.get("type", "")).startswith("Oral") for d in st.session_state.drug_schedule)
    vte_score, vte_label, vte_color = utils.calculate_vte_risk_score(
        st.session_state.user_profile,
        st.session_state.is_smoker,
        st.session_state.history_vte,
        surg_info["risk"],
        has_oral
    )

    # 위험도에 따른 권장 중단 기간 자동 연장 로직
    base_cessation = surg_info["cessation_weeks"]
    # 영문 모드일 경우 '주'를 'weeks'로 변환 (단순 치환)
    if st.session_state.lang == "EN":
        base_cessation = base_cessation.replace("주", " weeks")
        
    is_high_risk = vte_score >= 5
    display_cessation = base_cessation
    
    if is_high_risk:
        # 고위험군의 경우 기존 권장 기간에 1~2주 추가 권고
        ext_text = "+1~2 weeks" if st.session_state.lang == "EN" else "+1~2주"
        display_cessation = f"{base_cessation} ({ext_text})"

    # 가이드라인 카드 표시
    with st.container(border=True):
        st.markdown(f"#### 📋 {utils.t(selected_surg)}")
        sg_col1, sg_col2 = st.columns([1, 3])
        with sg_col1:
            st.metric(utils.t("rec_cessation"), display_cessation, 
                      delta=utils.t("risk_extension") if is_high_risk else None, delta_color="inverse")
        with sg_col2:
            risk_badge = utils.get_risk_badge(surg_info["risk"])
            st.markdown(f"**{utils.t('risk_label')}:** {risk_badge}", unsafe_allow_html=True)
            st.write(utils.get_localized_surg_desc(surg_info))
            
            # [추가 기능] HRT 기간 충족 여부 확인 (WPATH SOC 8 반영)
            min_req = surg_info.get("min_hrt_months", 0)
            if min_req > 0:
                # 첫 시작일부터 수술 예정일까지의 실제 기간 계산
                actual_hrt_days = (st.session_state.surgery_date - st.session_state.user_profile.get("first_hrt_date", datetime.now().date())).days
                actual_hrt_months = actual_hrt_days / 30.44
                
                if actual_hrt_months < min_req:
                    st.error(utils.t("wpath_fail_msg").format(min=min_req, curr=int(actual_hrt_months)))
                else:
                    st.success(utils.t("wpath_pass_msg").format(curr=int(actual_hrt_months)))

            if is_high_risk:
                st.warning(utils.t("high_risk_warn").format(level=vte_label))

    with st.expander(utils.t("vte_eval_title"), expanded=True):
        vcol1, vcol2 = st.columns([1, 2])
        vcol1.metric(utils.t("vte_score"), f"{vte_score} pts")
        vcol2.markdown(f"{utils.t('vte_level')}: <span style='color:{vte_color}; font-weight:bold; font-size:1.2em;'>{vte_label}</span>", unsafe_allow_html=True)
        
        # 위험 요인 요약
        factors = []
        if st.session_state.user_profile['weight'] / ((st.session_state.user_profile['height']/100)**2) >= 25: factors.append(utils.t("bmi_high"))
        if st.session_state.is_smoker: factors.append(utils.t("smoker"))
        if st.session_state.history_vte: factors.append(utils.t("vte_history"))
        if has_oral: factors.append(utils.t("oral_estrogen"))
        
        if factors:
            st.caption(utils.t("risk_factors").format(factors=', '.join(factors)))

    def _parse_cessation_weeks_to_days(cessation_weeks_text):
        nums = [int(n) for n in re.findall(r"\d+", str(cessation_weeks_text))]
        if not nums:
            return 14
        # 범위(예: 2-4주)일 경우 보수적으로 최대값 사용
        return max(nums) * 7

    if "surgery_auto_recommend" not in st.session_state:
        st.session_state.surgery_auto_recommend = True

    st.session_state.surgery_mode = st.toggle(utils.t("surg_toggle"), value=st.session_state.surgery_mode)
    if st.session_state.surgery_mode:
        # Normalize previously saved anesthesia labels across languages.
        if st.session_state.anesthesia_type in ("전신마취 (General)", "General Anesthesia"):
            st.session_state.anesthesia_type = utils.t("anesthesia_gen")
        elif st.session_state.anesthesia_type in ("국소마취 (Local)", "Local Anesthesia"):
            st.session_state.anesthesia_type = utils.t("anesthesia_local")

        col_s1, col_s2, col_s3 = st.columns(3)
        with col_s1:
            st.session_state.anesthesia_type = st.selectbox(
                utils.t("anesthesia_label"), [utils.t("anesthesia_gen"), utils.t("anesthesia_local")],
                index=0 if st.session_state.anesthesia_type == utils.t("anesthesia_gen") else 1,
                help=utils.t("anesthesia_help")
            )
        with col_s2:
            st.session_state.surgery_date = st.date_input(utils.t("date_surg_label"), value=st.session_state.surgery_date)
        with col_s3:
            st.session_state.surgery_auto_recommend = st.toggle(
                utils.t("surg_auto_recommend_label"),
                value=st.session_state.surgery_auto_recommend,
            )

        # 수술일 기반 자동 추천
        base_stop_days = _parse_cessation_weeks_to_days(surg_info.get("cessation_weeks", "2주"))
        if is_high_risk:
            base_stop_days += 7  # 고위험군 보수적 연장

        resume_days = 14 if st.session_state.anesthesia_type == utils.t("anesthesia_gen") else 7
        if is_high_risk:
            resume_days += 7

        rec_stop_date = st.session_state.surgery_date - timedelta(days=base_stop_days)
        rec_resume_date = st.session_state.surgery_date + timedelta(days=resume_days)

        # 시뮬레이션 기준 시작일 이전으로 내려가지 않도록 보정
        if rec_stop_date < st.session_state.start_date:
            rec_stop_date = st.session_state.start_date

        st.caption(
            utils.t("surg_recommendation_msg").format(
                stop=rec_stop_date.strftime("%Y-%m-%d"),
                resume=rec_resume_date.strftime("%Y-%m-%d"),
            )
        )

        if st.session_state.surgery_auto_recommend:
            st.session_state.stop_date = rec_stop_date
            st.session_state.resume_date = rec_resume_date

        col_d1, col_d2 = st.columns(2)
        with col_d1:
            st.session_state.stop_date = st.date_input(
                utils.t("date_stop_label"),
                value=st.session_state.stop_date,
                disabled=st.session_state.surgery_auto_recommend,
            )
        with col_d2:
            st.session_state.resume_date = st.date_input(
                utils.t("date_resume_label"),
                value=st.session_state.resume_date,
                help=utils.t("resume_date_help"),
                disabled=st.session_state.surgery_auto_recommend,
            )

        # 세션 업데이트 및 상대적 일수 계산
        st.session_state.stop_day = (st.session_state.stop_date - st.session_state.start_date).days
        st.session_state.resume_day = (st.session_state.resume_date - st.session_state.start_date).days
        
        st.markdown("---")
        st.subheader(utils.t("surg_analysis_title"))
        
        # 분석을 위한 시뮬레이션 재실행 (현재 설정 기준)
        t_surg, y_surg = analyzer.simulate_schedule(
            st.session_state.drug_schedule, 
            days=int(st.session_state.surg_sim_duration),
            calibration_factors=st.session_state.calibration_factors,
            stop_day=st.session_state.stop_day,
            resume_day=st.session_state.resume_day
        )
        
        # 안전 기준선 설정 (pg/mL 기준)
        s_threshold = 50.0
        after_stop_mask = t_surg >= st.session_state.stop_day
        safe_points = (y_surg <= s_threshold) & after_stop_mask
        
        if any(safe_points):
            safe_day = t_surg[safe_points][0]
            safe_date = datetime.combine(st.session_state.start_date, datetime.min.time()) + timedelta(days=float(safe_day))
            days_to_wait = safe_day - st.session_state.stop_day
            
            if safe_date.date() <= st.session_state.surgery_date:
                st.success(utils.t("safe_msg"))
                st.write(utils.t("safe_date_msg").format(date=safe_date.strftime('%Y-%m-%d')))
                st.write(utils.t("safe_wait_msg").format(days=days_to_wait))
            else:
                st.error(utils.t("unsafe_msg"))
                st.write(utils.t("unsafe_date_msg").format(date=safe_date.strftime('%Y-%m-%d')))
                st.info(utils.t("unsafe_advice"))
        else:
            st.warning(utils.t("sim_fail_msg"))
            
        # 재개 가이드라인
        st.info(utils.t("resume_guide").format(surg_name=utils.t(selected_surg), weeks=display_cessation))

        # [추가 기능] 수술 계획 시각화 그래프
        st.markdown("---")
        st.markdown(f"#### 📉 {utils.t('graph_title')} ({utils.t('surg_title')})")
        
        # [장기 계획 탭 전용] 단위/기간 선택 (시뮬레이션 탭과 유사한 배치)
        default_surg_days = max(30, int(st.session_state.resume_day + 30))
        if st.session_state.surg_sim_duration < 30:
            st.session_state.surg_sim_duration = default_surg_days
        col_u1, col_u2 = st.columns([1, 2])
        with col_u1:
            surg_unit_choice = st.radio(utils.t("unit_choice"), ["pg/mL", "pmol/L"], horizontal=True, key="surg_unit_choice")
        with col_u2:
            st.session_state.surg_sim_duration = st.slider(
                utils.t("surg_graph_duration_label"),
                min_value=30,
                max_value=365,
                value=min(365, max(default_surg_days, int(st.session_state.surg_sim_duration))),
                help=utils.t("surg_graph_duration_help")
            )

        # 날짜 변환
        start_dt = datetime.combine(st.session_state.start_date, datetime.min.time())
        t_dates_surg = [start_dt + timedelta(days=float(t)) for t in t_surg]
        
        # 단위 변환
        y_surg_plot = y_surg.copy()
        
        if surg_unit_choice == "pmol/L":
            y_surg_plot = utils.convert_e2_unit(y_surg_plot, "pmol/L")
            
        fig_surg = plot.create_hormone_chart(
            t_dates=t_dates_surg,
            t_days=t_surg,
            y_conc=y_surg_plot,
            unit_choice=surg_unit_choice,
            compare_mode=False,
            surgery_mode=True,
            stop_day=st.session_state.stop_day,
            resume_day=st.session_state.resume_day,
            surgery_date=st.session_state.surgery_date,
            start_date=st.session_state.start_date,
            anesthesia_type=st.session_state.anesthesia_type,
            sim_duration=int(st.session_state.surg_sim_duration)
        )
        st.plotly_chart(fig_surg, width="stretch")
    else:
        st.info(utils.t("surg_inactive_msg"))
    
# [Tab 5: Report & Export]
with tabs["rep"]:
    
    # [오프라인 전용] 병원 EMR 데이터베이스 관리 섹션
    if IS_OFFLINE:
        st.header(utils.t("emr_tab_title"))
        EMR.render_tab_management()
        st.markdown("---")
    
    # [공통] 개인용 리포트 및 데이터 내보내기 섹션
    st.header(utils.t("report_header"))
    c_rep1, c_rep2 = st.columns(2)
        
    with c_rep1:
        st.subheader(utils.t("pdf_section"))
        st.caption(utils.t("pdf_caption"))
        
        # PDF 생성은 Kaleido 설치 여부에 따라 에러가 날 수 있으므로 예외처리
        if st.button(utils.t("pdf_gen_btn")):
            try:
                if 'last_sim_data' not in st.session_state or st.session_state.last_sim_data is None:
                    st.warning(utils.t("pdf_warn_sim"))
                else:
                    surgery_plan_payload = None
                    surgery_graph_payload = None
                    if st.session_state.surgery_mode:
                        default_surg_key = next(iter(data.SURGERY_TYPES.keys()), "")
                        selected_surg_key = st.session_state.get("selected_surgery_type", default_surg_key)
                        selected_surg_label = utils.t(selected_surg_key) if selected_surg_key else "-"
                        recommendation_text = (
                            f"{utils.t('date_stop_label')}: {st.session_state.stop_date} / "
                            f"{utils.t('date_resume_label')}: {st.session_state.resume_date}"
                        )

                        surgery_plan_payload = {
                            "surgery_mode": True,
                            "surgery_type_label": selected_surg_label,
                            "anesthesia_type": st.session_state.anesthesia_type,
                            "stop_date": str(st.session_state.stop_date),
                            "surgery_date": str(st.session_state.surgery_date),
                            "resume_date": str(st.session_state.resume_date),
                            "recommendation": recommendation_text,
                        }

                        surg_days = int(st.session_state.get("surg_sim_duration", 90))
                        t_surg_pdf, y_surg_pdf = analyzer.simulate_schedule(
                            st.session_state.drug_schedule,
                            days=surg_days,
                            calibration_factors=st.session_state.calibration_factors,
                            stop_day=st.session_state.stop_day,
                            resume_day=st.session_state.resume_day,
                        )
                        surg_unit_choice = st.session_state.get("surg_unit_choice", "pg/mL")
                        if surg_unit_choice == "pmol/L":
                            y_surg_pdf = utils.convert_e2_unit(y_surg_pdf, "pmol/L")

                        start_dt_pdf = datetime.combine(st.session_state.start_date, datetime.min.time())
                        t_dates_surg_pdf = [start_dt_pdf + timedelta(days=float(t)) for t in t_surg_pdf]
                        surgery_graph_payload = {
                            "t_dates": t_dates_surg_pdf,
                            "t_days": t_surg_pdf,
                            "y_conc": y_surg_pdf,
                            "unit_choice": surg_unit_choice,
                            "compare_mode": False,
                            "y_conc_b": None,
                            "surgery_mode": True,
                            "stop_day": st.session_state.stop_day,
                            "resume_day": st.session_state.resume_day,
                            "surgery_date": st.session_state.surgery_date,
                            "start_date": st.session_state.start_date,
                            "anesthesia_type": st.session_state.anesthesia_type,
                            "lab_data": None,
                            "stats": None,
                            "sim_duration": surg_days,
                        }

                    pdf_buffer = inout.create_pdf(
                        st.session_state.user_profile,
                        st.session_state.drug_schedule,
                        st.session_state.last_sim_data,
                        schedule_b=st.session_state.drug_schedule_b,
                        compare_mode=st.session_state.compare_mode,
                        calibration_factors=st.session_state.calibration_factors,
                        lab_history=st.session_state.lab_history,
                        surgery_plan=surgery_plan_payload,
                        surgery_graph_data=surgery_graph_payload,
                    )
                    pdf_bytes = pdf_buffer.getvalue()
                    pdf_filename = "EstroFrame_Report.pdf"
                    b64_pdf = base64.b64encode(pdf_bytes).decode("utf-8")
                    auto_id = "auto_pdf_download_link"
                    components.html(
                        f"""
                        <a id="{auto_id}" href="data:application/pdf;base64,{b64_pdf}" download="{pdf_filename}"></a>
                        <script>
                          const a = document.getElementById("{auto_id}");
                          if (a) a.click();
                        </script>
                        """,
                        height=0,
                    )
                    st.download_button(
                        utils.t("pdf_download_btn"), 
                        pdf_bytes,
                        pdf_filename,
                        "application/pdf",
                        key="pdf_download_btn"
                    )
            except (RuntimeError, OSError, ValueError, TypeError) as e:
                st.error(f"PDF Generation Failed: {e}")
                st.info(utils.t("kaleido_install_hint"))

    with c_rep2:
        st.subheader(utils.t("ics_section"))
        st.caption(utils.t("ics_caption"))
        
        if st.session_state.drug_schedule:
            ics_data = inout.DataManager.generate_ics(
                st.session_state.drug_schedule,
                start_date=st.session_state.start_date,
                schedule_b=st.session_state.drug_schedule_b,
                compare_mode=st.session_state.compare_mode,
                surgery_mode=st.session_state.surgery_mode,
                stop_date=st.session_state.stop_date,
                surgery_date=st.session_state.surgery_date,
                resume_date=st.session_state.resume_date,
                anesthesia_type=st.session_state.anesthesia_type,
            )
            st.download_button(
                utils.t("ics_download_btn"),
                ics_data,
                "HRT_Schedule.ics",
                "text/calendar",
                key="ics_download_btn"
            )
        else:
            st.warning(utils.t("ics_warn_empty"))

    st.markdown("---")
    c_rep3, c_rep4 = st.columns(2)

    with c_rep3:
        st.subheader(utils.t("json_section"))
        st.caption(utils.t("json_caption"))
        
        # Export
        json_str = inout.DataManager.export_to_json(
            st.session_state.user_profile, 
            st.session_state.drug_schedule,
            st.session_state.calibration_factors,
            st.session_state.lab_history,
            st.session_state.drug_schedule_b,
            st.session_state.compare_mode
        )
        # 파일 이름에 초 단위를 제거하여 렌더링 시마다 ID가 바뀌는 것을 방지 (MediaFileStorageError 해결)
        export_date = datetime.now().strftime('%Y%m%d')
        file_name = f"{st.session_state.user_name}_{export_date}.json"
        st.download_button(utils.t("json_export_btn"), json_str, file_name, "application/json", width="stretch", key="json_export_btn")
        
    with c_rep4:
        st.subheader(utils.t("json_import_label"))
        st.caption(" ")
        # Import
        # handle_import_session에서 처리되므로 여기서는 UI만 표시
        # 키는 handle_import_session에서 관리하는 동적 키 사용
        st.file_uploader(
            utils.t("json_import_label"), 
            type="json", 
            key=st.session_state.get("import_uploader_key", "json_import_uploader_init")
        )

# [Tab 6: FAQ]
with tabs["faq"]:
    ui.render_faq() 

# -----------------------------------------------------------------------------
# 9. 푸터 (Footer)
# -----------------------------------------------------------------------------
ui.render_footer()
