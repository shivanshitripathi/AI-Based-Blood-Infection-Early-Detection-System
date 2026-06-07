import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
import os
import base64
import random
import string
from datetime import datetime
from auth import init_db, create_user, authenticate_user, save_prediction, get_user_history, delete_prediction, get_history_count, search_history, get_risk_distribution, bulk_delete_predictions, check_duplicate_entry, update_prediction_gender, bulk_update_gender_by_name, get_next_serial_number
from data_processing import validate_and_preprocess, get_predictions, generate_insights, SELECTED_FEATURES, get_parameter_statuses
from pdf_generator import generate_report
import math
import streamlit.components.v1 as components
import time
import uuid
import gender_guesser.detector as gender_detector
import json

# ── Gender Cache Management ────────────────────────────────────────────────
GENDER_CACHE_FILE = "name_gender_cache.json"

def load_gender_cache():
    if os.path.exists(GENDER_CACHE_FILE):
        try:
            with open(GENDER_CACHE_FILE, "r") as f:
                return json.load(f)
        except:
            return {}
    return {}

def save_to_gender_cache(name, gender):
    if not name or gender not in ["Male", "Female"]: return
    cache = load_gender_cache()
    cache[str(name).strip().lower()] = gender
    try:
        with open(GENDER_CACHE_FILE, "w") as f:
            json.dump(cache, f)
    except: pass

# ── Gender Detection Helper ──────────────────────────────────────────────────
_gender_d = gender_detector.Detector(case_sensitive=False)

def detect_gender_from_name(full_name: str) -> str:
    """Auto-detect gender from patient name using first name lookup or cache."""
    if not full_name: return "Unknown"
    
    # 1. Check persistent cache first
    clean_name = str(full_name).strip().lower()
    cache = load_gender_cache()
    if clean_name in cache:
        return cache[clean_name]

    # 2. Otherwise use the detector
    try:
        first_name = str(full_name).strip().split()[0]  # Take first word
        result = _gender_d.get_gender(first_name)
        if result in ('male', 'mostly_male'):
            return 'Male'
        elif result in ('female', 'mostly_female'):
            return 'Female'
        else:
            return 'Unknown'
    except:
        return 'Unknown'

# Shared Pagination Helper to avoid SessionState conflicts
def nav_page(key, delta, total):
    st.session_state[key] = max(1, min(total, st.session_state.get(key, 1) + delta))

def get_max_session_serial():
    """Finds the highest serial number currently visible globally (DB + Session)"""
    # 1. Start with database max
    max_id = get_next_serial_number() - 1
    
    # 2. Check current_results in dashboard
    if 'current_results' in st.session_state and st.session_state['current_results'] is not None:
        df = st.session_state['current_results']
        for col in ['Serial Number', 'Record ID']:
            if col in df.columns:
                try:
                    # Clean '#' and find max integer
                    cur_max = df[col].astype(str).str.replace("#", "").str.extract(r'(\d+)').astype(float).max().values[0]
                    if pd.notnull(cur_max): max_id = max(max_id, int(cur_max))
                except: pass
                
    # 3. Check manual logs not yet merged
    if 'manual_logs' in st.session_state and st.session_state['manual_logs']:
        for log in st.session_state['manual_logs']:
            s_no = log.get('Serial No.', '')
            if s_no:
                try:
                    num = int(str(s_no).replace("#", ""))
                    max_id = max(max_id, num)
                except: pass
    return max_id

st.set_page_config(page_title="Blood Infection Detection", layout="wide", page_icon="🩸")

@st.cache_data
def get_base64_of_bin_file(bin_file):
    try:
        with open(bin_file, 'rb') as f:
            data = f.read()
        return base64.b64encode(data).decode()
    except:
        return ""

@st.cache_data
def cached_to_data(df, format='csv'):
    """Caches the file conversion to prevent redundant work on every rerun."""
    if format == 'csv':
        return df.to_csv(index=False).encode('utf-8')
    else:
        from io import BytesIO
        output = BytesIO()
        df.to_excel(output, index=False, engine='openpyxl')
        return output.getvalue()

def apply_common_plotly_layout(fig, title_text):
    """Standardizes Plotly chart styling for a premium look and better performance."""
    fig.update_layout(
        title=dict(text=f"<b>{title_text}</b>", font=dict(size=18)),
        margin=dict(t=50, b=40, l=10, r=40),
        legend=dict(orientation="h", yanchor="bottom", y=-0.2, xanchor="center", x=0.5),
        font=dict(family="Inter, sans-serif", size=12),
        paper_bgcolor='rgba(0,0,0,0)',
        plot_bgcolor='rgba(0,0,0,0)'
    )
    return fig

def main():
    # Inject Custom CSS for Navbar, Footer, and beautiful components
    st.markdown("""
    <style>
        /* Hide default Streamlit footer */
        footer {visibility: hidden;}
        
        /* REDUCE TOP PADDING FOR COMPACT LOOK & PREVENT BOTTOM CUTOFF */
        .block-container {
            padding-top: 1.5rem !important;
            padding-bottom: 8rem !important;
            padding-left: 3rem !important;
            padding-right: 3rem !important;
        }

        /* ADVANCED PREMIUM DARK NAVBAR (SIDEBAR) STYLING */
        [data-testid="stSidebar"] {
            background: linear-gradient(180deg, #020617 0%, #0f172a 100%) !important;
            border-right: 1px solid rgba(56, 189, 248, 0.15);
            box-shadow: 10px 0 30px rgba(0,0,0,0.5);
        }
        
        /* Professional Sidebar nav buttons - Forced Dark Contrast */
        .stRadio > div[role="radiogroup"] > label {
            background-color: rgba(255, 255, 255, 0.05) !important;
            border: 1px solid rgba(255, 255, 255, 0.05) !important;
            border-radius: 12px !important;
            padding: 12px 20px !important;
            margin-bottom: 12px !important;
            transition: all 0.4s cubic-bezier(0.175, 0.885, 0.32, 1.275) !important;
            color: #94a3b8 !important;
            font-weight: 500 !important;
        }
        .stRadio > div[role="radiogroup"] > label:hover {
            background-color: rgba(56, 189, 248, 0.1) !important;
            border-color: rgba(56, 189, 248, 0.4) !important;
            transform: scale(1.02) translateX(8px) !important;
            color: #38bdf8 !important;
            box-shadow: 0 10px 20px rgba(0,0,0,0.2) !important;
        }
        
        /* Custom Sticky Footer - Forced Dark */
        .custom-footer {
            position: fixed;
            bottom: 0px;
            left: 0;
            width: 100%;
            background-color: #0c111d;
            color: #94a3b8;
            text-align: center;
            padding: 12px 20px 12px 320px; /* Offset to center text in main area, away from sidebar */
            font-size: 13px;
            font-weight: 500;
            z-index: 1000;
            box-shadow: 0 -4px 15px rgba(0,0,0,0.5);
            border-top: 1px solid rgba(255,255,255,0.05);
            box-sizing: border-box;
        }
        
        /* Premium File uploader */
        [data-testid="stFileUploadDropzone"] {
            border-radius: 12px;
            border: 2px dashed #1e293b;
            background-color: #0f172a !important;
            transition: all 0.3s ease;
        }
        [data-testid="stFileUploadDropzone"]:hover {
            border-color: #38bdf8;
            background-color: #1e293b !important;
        }
    </style>
    """, unsafe_allow_html=True)
    
    # Initialize DB safely mapping all columns
    init_db()

    # --- CLINICAL SESSION RECOVERY (Ensure analytics persist) ---
    if 'logged_in' not in st.session_state:
        st.session_state['logged_in'] = False
        st.session_state['username'] = None
        st.session_state['user_id'] = None
        
    if st.session_state.get('logged_in', False):
        if 'login_time' not in st.session_state or st.session_state['login_time'] == "N/A":
            st.session_state['login_time'] = datetime.now().strftime("%I:%M:%S %p")
        if 'session_start_dt' not in st.session_state:
            st.session_state['session_start_dt'] = datetime.now()
    if 'show_logout_confirm' not in st.session_state:
        st.session_state['show_logout_confirm'] = False
    if 'gender_tool_expanded' not in st.session_state:
        st.session_state['gender_tool_expanded'] = False

    if not st.session_state['logged_in']:
        unauthenticated_app()
    else:
        app_dashboard()
        
    # Render FOOTER globally at the end for stability
    st.markdown('''
        <div class="custom-footer">
            <span style="color: #fbbf24; font-weight: 700; margin-right: 15px;">⚠️ CLINICAL DISCLAIMER:</span> 
            This AI tool is for diagnostic support only. Professional medical judgment by a qualified doctor always takes precedence. Consult a doctor for any medical decisions.
            <br>
            <span style="font-size: 12px; margin-top: 5px; display: block; color: #475569;">
               🏥 AI-Based Blood Infection Early Detection System © 2026 | NexData Medical AI
            </span>
        </div>
    ''', unsafe_allow_html=True)

def unauthenticated_app():
    # A simple top navigation for unauthenticated users
    with st.sidebar:
        st.markdown('''
            <div style="text-align: center; padding: 30px 0;">
                <div style="font-size: 3rem; text-shadow: 0 0 20px rgba(56,189,248,0.8);">🧬</div>
                <h2 style="color: #38bdf8; margin: 10px 0 0 0; font-size: 2.2rem; text-transform: uppercase; letter-spacing: 2px;">NexData</h2>
                <p style="color: #94a3b8; font-size: 0.85rem; letter-spacing: 1px;">Medical AI Engine</p>
            </div>
            <hr style="border-color: rgba(255,255,255,0.1); margin-bottom: 30px;">
        ''', unsafe_allow_html=True)
        st.markdown("<p style='color: #64748b; font-size: 0.75rem; text-transform: uppercase; letter-spacing: 2px; margin-top: 20px;'>PORTAL ACCESS</p>", unsafe_allow_html=True)
        choice = st.radio("Go to", ["Home", "Login / Signup"], label_visibility="collapsed")
    
    if choice == "Home":
        landing_page()
    else:
        login_page()

def landing_page():
    # Use the local image for reliability reliably from the app script folder
    script_dir = os.path.dirname(os.path.abspath(__file__))
    img_path = os.path.join(script_dir, "medical_ai_bg_1773802025216.png")
    img_base64 = get_base64_of_bin_file(img_path)
    
    
    h_col1, h_col2 = st.columns([1.2, 1], gap="large")
    
    with h_col1:
        st.markdown(
            '''
            <h1 style="color: #38bdf8; font-size: 3rem; font-weight: 800; line-height: 1.2; margin-bottom: 20px;">
                AI-Based Blood Infection Early Detection
            </h1>
            <p style="font-size: 1.15rem; color: #cbd5e1; line-height: 1.6; margin-bottom: 30px;">
                Empower your clinical decision-making with real-time, AI-driven diagnostics. Instantly stratify patient risk using baseline Complete Blood Count (CBC) datasets and core vital signs to catch sepsis hours before critical deterioration.
            </p>
            <div style="display: flex; flex-wrap: wrap; gap: 10px; margin-bottom: 20px;">
                <span style="background-color: rgba(56, 189, 248, 0.1); border: 1px solid rgba(56, 189, 248, 0.3); color: #38bdf8; padding: 6px 12px; border-radius: 20px; font-size: 0.85rem; font-weight: 600;">🔬 XGBoost ML Engine</span>
                <span style="background-color: rgba(34, 197, 94, 0.1); border: 1px solid rgba(34, 197, 94, 0.3); color: #22c55e; padding: 6px 12px; border-radius: 20px; font-size: 0.85rem; font-weight: 600;">🛡️ HIPAA-Grade Local Security</span>
                <span style="background-color: rgba(168, 85, 247, 0.1); border: 1px solid rgba(168, 85, 247, 0.3); color: #a855f7; padding: 6px 12px; border-radius: 20px; font-size: 0.85rem; font-weight: 600;">📊 Multi-Format Batch (CSV/Excel)</span>
                <span style="background-color: rgba(249, 115, 22, 0.1); border: 1px solid rgba(249, 115, 22, 0.3); color: #f97316; padding: 6px 12px; border-radius: 20px; font-size: 0.85rem; font-weight: 600;">📡 Live Parameter Mapping</span>
            </div>
            <p style="font-size: 0.95rem; color: #94a3b8;">
                <em>* Standard parameters analyzed: White Blood Cells, Red Blood Cells, Hemoglobin, Platelets, and Body Temperature.</em>
            </p>
            ''', unsafe_allow_html=True
        )
        
    with h_col2:
        if img_base64:
            st.markdown(
                f'''
                <div style="display: flex; justify-content: center; align-items: center; height: 100%;">
                    <img src="data:image/png;base64,{img_base64}" 
                         style="width: 100%; max-width: 600px; border-radius: 16px; 
                                border: 1px solid rgba(255,255,255,0.05); 
                                box-shadow: 0 20px 40px rgba(0,0,0,0.5); 
                                filter: brightness(1.05) contrast(1.05);" alt="Medical AI System Dashboard Preview" />
                </div>
                ''', unsafe_allow_html=True
            )
        else:
            st.error("⚠️ Primary dashboard visualization banner could not be loaded from local files.")

    st.markdown("<br><hr style='border-color: rgba(255,255,255,0.05);'>", unsafe_allow_html=True)
    st.markdown("<h2 style='text-align: center; margin-bottom: 30px;'>🏥 Core System Capabilities</h2>", unsafe_allow_html=True)
    
    def render_core_card(title, text):
        return f"""
        <div style="background-color: rgba(30, 41, 59, 0.4); border: 1px solid rgba(255,255,255,0.08); 
                    border-radius: 12px; padding: 25px 20px; height: 190px; 
                    display: flex; flex-direction: column; justify-content: flex-start;
                    box-shadow: 0 10px 25px rgba(0,0,0,0.2);">
            <div style="font-weight: 700; font-size: 1.15rem; margin-bottom: 12px; color: #38bdf8;">
                {title}
            </div>
            <div style="color: #cbd5e1; font-size: 0.95rem; line-height: 1.6;">
                {text}
            </div>
        </div>
        """
        
    col1, col2, col3 = st.columns(3)
    with col1:
        st.markdown(render_core_card("⚡ Fast & Accurate", "Powered by XGBoost algorithms trained on clinical datasets to reliably predict sepsis and bloodstream infections hours before critical deterioration."), unsafe_allow_html=True)
    with col2:
        st.markdown(render_core_card("📊 Comprehensive Analytics", "Generate interactive visualization charts and extract automated medical insights. Instantly highlights abnormal parameter levels."), unsafe_allow_html=True)
    with col3:
        st.markdown(render_core_card("🔒 Secure & Private", "Your patient records operate in heavily secured local environments. Access is strictly restricted to properly authenticated medical personnel."), unsafe_allow_html=True)

    st.markdown("---")
    
    st.markdown("<h2 style='text-align: center; margin-bottom: 30px;'>🔍 How It Works</h2>", unsafe_allow_html=True)
    def render_step_card(bg, border, title, text):
        return f"""
        <div style="background-color: {bg}; border: 1px solid {border}; 
                    border-radius: 12px; padding: 22px 18px; height: 190px; 
                    display: flex; flex-direction: column; justify-content: flex-start;
                    box-shadow: 0 4px 15px rgba(0,0,0,0.2);">
            <div style="font-weight: 700; font-size: 1.05rem; margin-bottom: 12px; color: #f8fafc;">
                {title}
            </div>
            <div style="color: #94a3b8; font-size: 0.92rem; line-height: 1.6;">
                {text}
            </div>
        </div>
        """
        
    step1, step2, step3, step4 = st.columns(4)
    with step1:
        st.markdown(render_step_card("rgba(56, 189, 248, 0.05)", "rgba(56, 189, 248, 0.2)", "1️⃣ Data Input", "Upload batch CSV or Excel datasets of CBC results or manually type in single patient vitals for instant checks."), unsafe_allow_html=True)
    with step2:
        st.markdown(render_step_card("rgba(249, 115, 22, 0.05)", "rgba(249, 115, 22, 0.2)", "2️⃣ AI Processing", "Our ML engine evaluates blood cells, hemoglobin, and temperature against thousands of trained parameters."), unsafe_allow_html=True)
    with step3:
        st.markdown(render_step_card("rgba(239, 68, 68, 0.05)", "rgba(239, 68, 68, 0.2)", "3️⃣ Risk Profiling", "Patients are intelligently stratified into <b>High</b>, <b>Medium</b>, or <b>Normal</b> susceptibility categories."), unsafe_allow_html=True)
    with step4:
        st.markdown(render_step_card("rgba(34, 197, 94, 0.05)", "rgba(34, 197, 94, 0.2)", "4️⃣ Clinical Strategy", "Review algorithmically generated preventive care strategies and mitigate long-term patient risks."), unsafe_allow_html=True)

    st.markdown("---")
    
    st.markdown("<h2 style='text-align: center; margin-top: 40px; margin-bottom: 30px;'>🧬 Key Biomarkers & Hematological Features Analyzed</h2>", unsafe_allow_html=True)
    
    st.write("Our predictive system relies on fundamental Complete Blood Count (CBC) metrics and essential physiological vitals:")
    st.markdown("""
    - **White Blood Cells (WBC):** Elevated levels indicate an active immune response fighting infection; severe lows indicate dangerous immunosuppression.
    - **Red Blood Cells (RBC) & Hemoglobin:** Measures oxygen-carrying capacity which critically drops during severe sepsis episodes.
    - **Platelets:** Essential for blood clotting. Rapid depletion (thrombocytopenia) is a hallmark sign of systemic bloodstream infections.
    - **Body Temperature:** Tracks acute febrile responses to active bacterial presence.
    
    *By tracking statistical correlations between these precise markers, NexData AI provides an extraordinarily reliable early warning surveillance network.*
    """)
        
    st.markdown("<br>", unsafe_allow_html=True)
    st.info("👈 **Ready to begin? Click 'Login / Signup' on the left sidebar to authenticate and access the diagnostics dashboard!**")

def login_page():
    st.markdown("""
        <div style='text-align: center; margin-bottom: 30px;'>
            <h1 style='color: #38bdf8; font-size: 3rem;'>Welcome to NexData AI 🧬</h1>
            <p style='font-size: 1.2rem; color: #94a3b8;'>Secure Diagnostic Portal for Healthcare Professionals</p>
        </div>
    """, unsafe_allow_html=True)

    col_info, col_login = st.columns([1.2, 1], gap="large")
    
    with col_info:
        st.markdown("### 🌟 Enterprise Features")
        st.info("🤖 **AI-Powered Diagnostics:** Instantly detect Sepsis and Blood Infection risks with high accuracy using our XGBoost engine.")
        st.success("🔒 **Patient Safety First:** All biometric logs are heavily secured and strictly accessible only by authorized medical staff.")
        st.warning("⚡ **Actionable Insights:** Generate personalized, condition-specific preventive care plans dynamically.")
        
        st.markdown("<br>🛡️ Security Requirements", unsafe_allow_html=True)
        st.markdown("""
        <div style='background-color: rgba(239, 68, 68, 0.05); border-left: 4px solid #ef4444; padding: 15px; border-radius: 4px;'>
            <p style='color: #f8fafc; font-size: 0.95rem; margin-bottom: 10px;'>For system compliance and data protection, all new accounts must fulfill strict guidelines:</p>
            <ul style='color: #cbd5e1; font-size: 0.85rem;'>
                <li><b>Username:</b> Minimum 4 characters (letters & numbers only, no spaces).</li>
                <li><b>Password Length:</b> Minimum 8 characters.</li>
                <li><b>Password Structure:</b> Must contain at least one uppercase letter (A-Z), one lowercase letter (a-z), one number (0-9), and one special symbol (@, #, !, etc.).</li>
            </ul>
        </div>
        """, unsafe_allow_html=True)

    with col_login:
        st.markdown("### Access Dashboard")
        tab1, tab2 = st.tabs(["🔐 Secure Login", "📝 Create Account"])

    with tab1:
        st.subheader("Login to Your Account")
        with st.form("login_form", clear_on_submit=True):
            username_l = st.text_input("Username")
            password_l = st.text_input("Password", type="password")
            submitted = st.form_submit_button("Login")
            
            if submitted:
                u_cleaned = username_l.strip()
                p_cleaned = password_l.strip()
                if not u_cleaned or not p_cleaned:
                    st.error("⚠️ Please fill all fields.")
                else:
                    success, user_id = authenticate_user(u_cleaned, p_cleaned)
                    if success:
                        st.session_state['logged_in'] = True
                        st.session_state['username'] = u_cleaned
                        st.session_state['user_id'] = user_id
                        st.session_state['login_time'] = datetime.now().strftime("%I:%M:%S %p")
                        st.session_state['session_start_dt'] = datetime.now()
                        st.rerun()
                    else:
                        st.error("❌ Invalid user and password")

    with tab2:
        st.subheader("Register New Account")
        with st.form("signup_form", clear_on_submit=True):
            username_s = st.text_input("New Username")
            password_s = st.text_input("New Password", type="password")
            pass_confirm = st.text_input("Confirm Password", type="password")
            submitted = st.form_submit_button("Sign Up")
            
            if submitted:
                u_s_cleaned = username_s.strip()
                p_s_cleaned = password_s.strip()
                pc_cleaned = pass_confirm.strip()
                
                if not u_s_cleaned or not p_s_cleaned or not pc_cleaned:
                    st.error("⚠️ Please fill all fields.")
                elif len(u_s_cleaned) < 4:
                    st.error("⚠️ Username must be at least 4 characters long.")
                elif not u_s_cleaned.isalnum():
                    st.error("⚠️ Username can only contain letters and numbers (no spaces or special symbols).")
                elif len(p_s_cleaned) < 8 or not any(c.islower() for c in p_s_cleaned) or not any(c.isupper() for c in p_s_cleaned) or not any(c.isdigit() for c in p_s_cleaned) or not any(not c.isalnum() for c in p_s_cleaned):
                    st.error("⚠️ Password must be at least 8 characters long and contain at least one uppercase letter, one lowercase letter, one number, and one symbol.")
                elif p_s_cleaned != pc_cleaned:
                    st.error("❌ Passwords do not match!")
                else:
                    success, msg = create_user(u_s_cleaned, p_s_cleaned)
                    if success:
                        st.success(f"✅ {msg} You can now log in using the Login tab.")
                    else:
                        st.error(f"❌ {msg}")



def app_dashboard():
    # Refresh Logic
    if st.session_state.get('is_refreshing', False):
        st.session_state['is_refreshing'] = False
        st.rerun()

    # Sidebar Navigation for Authenticated Users
    if 'nav_menu' not in st.session_state:
        st.session_state['nav_menu'] = "Dashboard & Prediction"
    # --- SESSION STATE INITIALIZATION (Enhanced with Migration) ---
    if 'manual_logs' not in st.session_state:
        st.session_state['manual_logs'] = []
    else:
        # Migration: Ensure all legacy logs have a unique ID
        for log in st.session_state['manual_logs']:
            if 'id' not in log:
                log['id'] = str(uuid.uuid4())

    if 'current_results' not in st.session_state:
        st.session_state['current_results'] = None
    if 'results_page' not in st.session_state:
        st.session_state['results_page'] = 1
    # Ensure nav state is ready
    if 'nav_menu' not in st.session_state:
        st.session_state['nav_menu'] = "Dashboard & Prediction"

    if st.session_state.get('nav_revert_trigger', False):
        st.session_state['nav_revert_trigger'] = False
        st.session_state['nav_menu'] = "Dashboard & Prediction"
        st.session_state['navigation_manager_widget'] = "Dashboard & Prediction"
        st.rerun()
        
    if st.session_state.get('logout_trigger', False):
        st.session_state['logout_trigger'] = False
        st.session_state['logged_in'] = False
        st.session_state['username'] = None
        st.session_state['user_id'] = None
        st.session_state['nav_menu'] = "Dashboard & Prediction"
        st.session_state['navigation_manager_widget'] = "Dashboard & Prediction"
        if 'current_results' in st.session_state: del st.session_state['current_results']
        if 'manual_logs' in st.session_state: st.session_state['manual_logs'] = []
        st.rerun()
    with st.sidebar:
        # --- USER PROFILE & IDENTITY ---
        st.markdown(f'''
            <div style="text-align: center; padding: 15px 0; background: linear-gradient(180deg, rgba(14, 165, 233, 0.1), transparent); border-radius: 15px; border: 1px solid rgba(56, 189, 248, 0.1); margin-bottom: 15px;">
                <div style="margin: 0 auto; width: 75px; height: 75px; background: linear-gradient(135deg, #0ea5e9, #2563eb); border-radius: 50%; display: flex; align-items: center; justify-content: center; box-shadow: 0 5px 15px rgba(14, 165, 233, 0.4); border: 2px solid #1e293b;">
                    <span style="font-size: 2.2rem;">👨‍⚕️</span>
                </div>
                <p style="color: #94a3b8; margin: 12px 0 2px 0; font-size: 0.8rem; letter-spacing: 1px; font-weight: 500;">ACTIVE SESSION FOR</p>
                <h2 style="color: #f8fafc; margin: 0; font-size: 1.6rem; font-weight: 700; text-shadow: 0 2px 4px rgba(0,0,0,0.5);">{st.session_state['username']}</h2>
            </div>
        ''', unsafe_allow_html=True)

        # --- SESSION ANALYTICS & LIVE CLOCK (High Reliability Iframe) ---
        start_dt = st.session_state.get('session_start_dt', datetime.now())
        
        analytics_html = f"""
            <style>
                @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');
                body {{
                    margin: 0;
                    padding: 0;
                    background: transparent;
                    font-family: 'Inter', sans-serif;
                    overflow: hidden;
                }}
                .card {{
                    background: rgba(15, 23, 42, 0.95); 
                    border: 1px solid rgba(56, 189, 248, 0.3); 
                    border-radius: 10px; 
                    padding: 8px; 
                    box-shadow: 0 4px 15px rgba(0,0,0,0.4);
                    color: white;
                }}
                .row {{
                    display: flex;
                    justify-content: space-between;
                    align-items: center;
                    margin-bottom: 4px;
                }}
                .row:last-child {{ margin-bottom: 0; }}
                .label {{ color: #64748b; font-size: 0.85rem; font-weight: 700; text-transform: uppercase; letter-spacing: 0.3px; }}
                .value {{ font-size: 0.95rem; font-weight: 600; }}
                #clock {{ color: #38bdf8; }}
                #duration {{ color: #fbbf24; }}
                .status-active {{ color: #22c55e; display: flex; align-items: center; gap: 6px; font-weight: 800; letter-spacing: 0.5px; }}
                .dot {{ width: 8px; height: 8px; background: #22c55e; border-radius: 50%; box-shadow: 0 0 6px #22c55e; animation: pulse 1.5s infinite; }}
                @keyframes pulse {{ 
                    0% {{ transform: scale(1); opacity: 1; }} 
                    50% {{ transform: scale(1.3); opacity: 0.6; }} 
                    100% {{ transform: scale(1); opacity: 1; }} 
                }}
            </style>
            
            <div class="card">
                <div class="row" style="margin-bottom: 4px;">
                    <span class="status-active" style="font-size: 0.9rem;">
                        <div class="dot"></div> ENGINE ONLINE
                    </span>
                </div>
                <div style="color: #94a3b8; font-size: 0.75rem; margin-bottom: 8px; font-weight: 500;">Real-time Clinical Stream</div>
                
                <div style="border-top: 1px solid rgba(56, 189, 248, 0.1); margin-bottom: 8px;"></div>

                <div class="row">
                    <span class="label">TIME</span>
                    <span id="clock" class="value">00:00:00 AM</span>
                </div>
                <div class="row">
                    <span class="label">LIVE</span>
                    <span id="duration" class="value">0m 0s</span>
                </div>
            </div>
            
            <script>
                const sStart = {start_dt.timestamp() * 1000};
                function update() {{
                    const now = new Date();
                    document.getElementById('clock').innerText = now.toLocaleTimeString('en-US', {{ hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: true }});
                    
                    const diff = Math.floor((now.getTime() - sStart) / 1000);
                    const h = Math.floor(diff / 3600);
                    const m = Math.floor((diff % 3600) / 60);
                    const s = diff % 60;
                    document.getElementById('duration').innerText = (h > 0 ? h + "h " : "") + m + "m " + s + "s";
                }}
                setInterval(update, 1000);
                update();
            </script>
        """
        components.html(analytics_html, height=125)

        # --- UNIFIED NAVIGATION & TOOLS ---
        # --- ULTRA-RESPONSIVE SIDEBAR OVERRIDES ---
        st.markdown("""
            <style>
            [data-testid="stSidebar"] button {
                height: 36px !important;
                display: flex !important;
                align-items: center !important;
                justify-content: center !important;
                font-size: 0.7rem !important;
                padding: 0 4px !important;
                white-space: nowrap !important;
                overflow: hidden !important;
            }
            [data-testid="stSidebar"] div[data-testid="stExpander"] p {
                font-size: 0.75rem !important;
                white-space: nowrap !important;
                overflow: hidden !important;
                text-overflow: ellipsis !important;
            }
            [data-testid="stSidebar"] label {
                font-size: 0.7rem !important;
            }
            .qa-card-v3 {
                background: rgba(30, 41, 59, 0.4); 
                border: 1px solid rgba(148, 163, 184, 0.1); 
                border-radius: 8px; 
                padding: 10px; 
                margin-bottom: 10px;
            }
            /* Fix radio buttons side-by-side wrapping in Gender Tool */
            [data-testid="stSidebar"] div[data-testid="stExpander"] div[role="radiogroup"] {
                display: flex !important;
                flex-direction: row !important;
                flex-wrap: nowrap !important;
                gap: 5px !important;
                width: 100% !important;
            }
            [data-testid="stSidebar"] div[data-testid="stExpander"] div[role="radiogroup"] > label {
                flex: 1 1 50% !important;
                margin: 0 !important;
                min-width: 0 !important;
                justify-content: center !important;
                padding: 6px !important;
            }
            [data-testid="stSidebar"] div[data-testid="stExpander"] div[role="radiogroup"] label p {
                font-size: 0.75rem !important;
                line-height: 1.1 !important;
                white-space: nowrap !important;
            }
            }
            </style>
            <p style='color: #64748b; font-size: 0.65rem; text-transform: uppercase; letter-spacing: 2px; margin-bottom: 8px; margin-top: 5px; font-weight: 700;'>🧭 APP MENU</p>
        """, unsafe_allow_html=True)
        
        primary_nav_options = {
            "Dashboard & Prediction": "🩸 Start New Test",
            "My Past Reports": "📋 History & Logs",
            "Logout": "🚪 Sign Out"
        }
        
        # Sync navigation options and set correct index based on session state
        nav_keys = list(primary_nav_options.keys())
        current_idx = nav_keys.index(st.session_state['nav_menu']) if st.session_state['nav_menu'] in nav_keys else 0
        
        routing_selection = st.radio(
            "App Routing",
            options=nav_keys,
            format_func=lambda x: primary_nav_options[x],
            index=current_idx,
            key="navigation_manager_widget",
            label_visibility="collapsed"
        )
        # Update shared state
        st.session_state['nav_menu'] = routing_selection
        
        st.markdown("<hr style='margin: 12px 0; border: none; border-top: 1px solid rgba(56, 189, 248, 0.1);'>", unsafe_allow_html=True)
        
        st.markdown("<p style='color: #64748b; font-size: 0.65rem; text-transform: uppercase; letter-spacing: 2px; margin-bottom: 8px; font-weight: 700;'>⚙️ QUICK ACTIONS</p>", unsafe_allow_html=True)
        
        if not st.session_state.get('show_qa_reset_confirm', False):
            col_q1, col_q2 = st.columns(2)
            with col_q1:
                if st.button("🔄 Refresh", width='stretch', key="btn_q_refresh"): 
                    st.rerun()
            with col_q2:
                if st.button("🗑️ Reset", width='stretch', key="btn_q_reset"):
                    st.session_state['show_qa_reset_confirm'] = True
                    st.rerun()
        else:
            st.markdown("<p style='color:#ef4444; font-size:0.65rem; font-weight:700; text-align:center; margin-bottom:4px;'>CONFIRM RESET?</p>", unsafe_allow_html=True)
            rc1, rc2 = st.columns(2)
            with rc1:
                if st.button("✅ Yes", width='stretch', key="btn_q_yes"):
                    st.session_state['current_results'] = None
                    st.session_state['manual_logs'] = []
                    if 'g_search_all' in st.session_state: st.session_state['g_search_all'] = ""
                    st.session_state['upload_version'] = st.session_state.get('upload_version', 0) + 1
                    st.session_state['show_qa_reset_confirm'] = False
                    st.rerun()
            with rc2:
                if st.button("❌ No", width='stretch', key="btn_q_no"):
                    st.session_state['show_qa_reset_confirm'] = False
                    st.rerun()

        # --- GENDER MANAGEMENT TOOL (Unified) ---
        st.markdown("<hr style='margin: 12px 0; border: none; border-top: 1px dashed rgba(56, 189, 248, 0.2);'>", unsafe_allow_html=True)
        # Use session state to keep expander open after updates
        with st.expander("🚻 Gender Correction Tool", expanded=st.session_state.get('gender_tool_expanded', False)):
            st.markdown("""
                <div style='background: rgba(56, 189, 248, 0.05); border-radius: 8px; padding: 10px; border: 1px solid rgba(14, 165, 233, 0.2); margin-bottom: 8px;'>
                    <p style='color: #38bdf8; font-size: 0.7rem; font-weight: 700; margin-bottom: 3px;'>🔍 FIND PATIENT</p>
                    <p style='color: #94a3b8; font-size: 0.6rem; margin: 0;'>Search Name or #ID to fix gender errors.</p>
                </div>
            """, unsafe_allow_html=True)
            search_query = st.text_input("Find Patient:", key="g_search_all", placeholder="Type name or #ID...", label_visibility="collapsed")
            
            if search_query.strip():
                # 1. Look for records in DB
                db_results = search_history(st.session_state['user_id'], search_name=search_query if not search_query.startswith("#") else None)
                if search_query.startswith("#"):
                    try:
                        s_id = int(search_query.replace("#", ""))
                        db_results = [r for r in db_results if r[0] == s_id] or search_history(st.session_state['user_id']) # simplistic fallback
                        # Actually just search by ID if it's #... later logic below handles selection
                    except: pass

                # 2. Look for records in session current_results (Dashboard)
                session_records = []
                if 'current_results' in st.session_state and st.session_state['current_results'] is not None:
                    df_r = st.session_state['current_results']
                    
                    # Identify the Serial/Record ID column (it might be renamed to 'Serial Number' in the dashboard)
                    id_col = 'Serial Number' if 'Serial Number' in df_r.columns else 'Record ID'
                    name_col = 'Patient Name' if 'Patient Name' in df_r.columns else df_r.columns[1] # fallback

                    # Perform the search
                    mask = (df_r[name_col].astype(str).str.contains(search_query, case=False, na=False)) | \
                           (df_r[id_col].astype(str).str.replace("#", "") == search_query.replace("#", ""))
                    session_records = df_r[mask].to_dict('records')

                # Combine options for user selection
                options = []
                # Formats: "Session Item: [ID] Name (G)" vs "History Record: [#ID] Name (G)"
                for r in session_records:
                    # Get ID value safely
                    cur_id = r.get('Serial Number', r.get('Record ID', '?'))
                    cur_name = r.get('Patient Name', '?')
                    cur_gender = r.get('Gender', 'Unknown')
                    options.append(f"Session Item: {cur_id} - {cur_name} ({cur_gender})")
                for r in db_results:
                    # check if already in session to avoid double display if user just saved
                    options.append(f"History Record: #{r[0]} - {r[1]} ({r[-1]})")
                
                if options:
                    st.markdown("<p style='color: #64748b; font-size: 0.73rem; font-weight: 700; margin-top: 8px; margin-bottom: 2px;'>TARGET RECORD</p>", unsafe_allow_html=True)
                    target_sel = st.selectbox("match:", options, label_visibility="collapsed")
                    
                    st.markdown("<p style='color: #22c55e; font-size: 0.73rem; font-weight: 700; margin-top: 10px; margin-bottom: 6px;'>CHOOSE GENDER</p>", unsafe_allow_html=True)
                    new_g = st.radio("Correct gender to:", ["Male", "Female"], horizontal=True, key="fix_g_target_v3", label_visibility="collapsed")
                    
                    col_f1, col_f2 = st.columns(2)
                    with col_f1:
                        if st.button("🔧 Fix ID", width='stretch', key="btn_g_single"):
                            try:
                                # Standard ID parsing
                                raw_id_part = target_sel.split(": ")[1].split(" - ")[0]
                                id_str = raw_id_part.replace("#", "")
                                
                                # 1. Update DB only if numeric ID (History)
                                if id_str.isdigit():
                                    update_prediction_gender(int(id_str), new_g)
                                
                                # 2. Update Session Results (Dashboard)
                                if 'current_results' in st.session_state and st.session_state['current_results'] is not None:
                                    df_curr = st.session_state['current_results']
                                    # Target ID might be prefixed with # - clean it for match
                                    clean_id = id_str.replace("#", "")
                                    
                                    # Check for either name
                                    for col_name in ['Record ID', 'Serial Number']:
                                        if col_name in df_curr.columns:
                                            df_curr.loc[df_curr[col_name].astype(str).str.replace("#", "") == clean_id, 'Gender'] = new_g
                                    
                                    st.session_state['current_results'] = df_curr.copy()
                                
                                # 3. Special: Check manual logs if UUID matches (for Manual Entry logs)
                                for log in st.session_state.get('manual_logs', []):
                                    if log.get('id') == id_str:
                                        log['Gender'] = new_g
                                        if 'RawData' in log: log['RawData']['Gender'] = new_g

                                st.toast(f"✅ Record fixed successfully!")
                                st.session_state['gender_tool_expanded'] = True
                                time.sleep(1)
                                st.rerun()
                            except Exception as e:
                                st.error(f"Error updating database: {str(e)}")
                    with col_f2:
                        name_to_bulk = target_sel.split(" - ")[1].split(" (")[0]
                        if st.button("🌐 Fix ALL", width='stretch', key="btn_g_bulk"):
                            # Bulk name update
                            save_to_gender_cache(name_to_bulk, new_g)
                            bulk_update_gender_by_name(st.session_state['user_id'], name_to_bulk, new_g)
                            
                            # Clean up current results
                            if 'current_results' in st.session_state and st.session_state['current_results'] is not None:
                                df_res = st.session_state['current_results']
                                df_res.loc[df_res['Patient Name'] == name_to_bulk, 'Gender'] = new_g
                                st.session_state['current_results'] = df_res.copy()
                            
                            # Clean up manual logs
                            for log in st.session_state.get('manual_logs', []):
                                if log.get('Patient Name') == name_to_bulk: log['Gender'] = new_g

                            st.toast(f"✅ All records for '{name_to_bulk}' updated!")
                            st.session_state['gender_tool_expanded'] = True
                            time.sleep(1)
                            st.rerun()
                else:
                    st.info("No records found matching that query.")
            else:
                st.info("Type a Serial # (like #12) or Patient Name to start.")
                
        # st.markdown('</div>', unsafe_allow_html=True) # REMOVED: End of gender tool

        st.markdown("---")
        
    # --- INTERNAL APP ROUTING CONTROLLER ---
    if st.session_state['nav_menu'] == "Dashboard & Prediction":
        st.session_state['show_logout_confirm'] = False
        show_upload_dashboard()
    elif st.session_state['nav_menu'] == "My Past Reports":
        st.session_state['show_logout_confirm'] = False
        show_reports()
    elif st.session_state['nav_menu'] == "Logout":
        show_logout()

def show_logout():
    st.markdown("""
        <div style='text-align: center; margin-bottom: 40px;'>
            <h1 style='font-size: 3.5rem;'>🛡️</h1>
            <h2 style='color: #f8fafc; font-size: 2.2rem;'>Session Termination Protocol</h2>
            <p style='color: #94a3b8; font-size: 1rem;'>Authorized clinical session ending...</p>
        </div>
    """, unsafe_allow_html=True)
    
    st.info("💡 **Session Summary:** All analyzed records for this session have been securely synchronized with the central database. Terminatiing this session will clear local workspace memory.")
    
    # Add some 'things that work' - session statistics
    if st.session_state.get('current_results') is not None:
        recs = len(st.session_state['current_results'])
        st.write(f"📊 **Session Statistics:** {recs} patient records analyzed in this session.")

    col1, col2 = st.columns(2)
    with col1:
        if st.button("🔴 YES, TERMINATE SESSION", width='stretch'):
            st.session_state['logout_trigger'] = True
            st.rerun()
    with col2:
        if st.button("🔙 NO, RETURN TO DASHBOARD", width='stretch'):
            st.session_state['nav_revert_trigger'] = True
            st.rerun()


   
def process_manual_entry(df_source):
    """Processes a single manual entry, shows localized results, and explicitly saves to DB."""
    try:
        # Extract patient name for clearer messaging
        p_name_candidate = df_source.iloc[0].get('Patient Name', "Unknown Patient")
        
        # --- PRE-VALIDATION: DUPLICATE DETECTION ---
        # 1. Check against Permanent History (Database)
        is_db_duplicate = check_duplicate_entry(
            user_id=st.session_state['user_id'],
            patient_name=p_name_candidate,
            age=int(df_source.iloc[0].get('Age', 0)),
            wbc=float(df_source.iloc[0].get('WBC', 0)),
            rbc=float(df_source.iloc[0].get('RBC', 0)),
            hgb=float(df_source.iloc[0].get('Hemoglobin', 0)),
            platelets=float(df_source.iloc[0].get('Platelets', 0)),
            temp=float(df_source.iloc[0].get('Temperature', 0))
        )
        
        if is_db_duplicate:
            st.error(f"🛑 Duplicate Record Detected: A patient named '**{p_name_candidate}**' with exact same data already exists in the central medical history. Entry rejected.")
            return

        # 2. Check against Current Session Workspace (manual_logs)
        for existing_log in st.session_state.get('manual_logs', []):
            if (str(existing_log.get('Patient Name', '')).strip().lower() == str(p_name_candidate).strip().lower() and
                int(existing_log.get('Age', 0)) == int(df_source.iloc[0].get('Age', 0)) and
                abs(float(existing_log.get('WBC', 0)) - float(df_source.iloc[0].get('WBC', 0))) < 0.1 and
                abs(float(existing_log.get('RBC', 0)) - float(df_source.iloc[0].get('RBC', 0))) < 0.1 and
                abs(float(existing_log.get('Hgb', 0)) - float(df_source.iloc[0].get('Hemoglobin', 0))) < 0.1 and
                abs(float(existing_log.get('Plt', 0)) - float(df_source.iloc[0].get('Platelets', 0))) < 0.1 and
                abs(float(existing_log.get('Temp', 0)) - float(df_source.iloc[0].get('Temperature', 0))) < 0.1):
                st.warning(f"⚠️ Workspace Duplicate: You have already processed '**{p_name_candidate}**' with these parameters in this session. Scroll down to see results.")
                return

        with st.spinner("Analyzing manual patient data..."):
            X_processed, df_filled, error = validate_and_preprocess(df_source)
            if error:
                st.error(f"Validation Error: {error}")
                return
                
            scores, levels, pred_error = get_predictions(X_processed, df_source, model_type='XGBoost')
            if pred_error:
                st.error(pred_error)
                return
                
            score = scores[0]
            level = levels[0]
            
            df = df_filled.copy()
            if 'Age' in df.columns:
                df['Age'] = df['Age'].astype(int)
                
            df['Risk Level'] = level
            df['Risk Score (%)'] = score
            insights = generate_insights(df.iloc[0])
            
            row = df.iloc[0]
            p_name = row.get('Patient Name', "Unknown Patient")
            
            # Auto-detect gender from patient name
            detected_gender = detect_gender_from_name(p_name)
            
            # NOTE: Auto-save to Database is DISABLED here as requested.
            # Manual entries only save to DB when explicitly 'MERGED' by the user.
            
            # Format insights for the log table
            insights_str = " | ".join(insights) if isinstance(insights, list) else str(insights)
            score_formatted = round(float(score), 1)
            
            # Calculate temporary Serial No based on absolute highest ID currently in memory
            temp_serial = get_max_session_serial() + 1

            log_entry = {
                'id': str(uuid.uuid4()),
                'Serial No.': f"#{temp_serial}",
                'Time': datetime.now().strftime("%I:%M %p"),
                'Patient Name': p_name,
                'Gender': detected_gender,
                'Age': int(row.get('Age', 0)),
                'Temp': round(float(row.get('Temperature', 0)), 1),
                'WBC': round(float(row.get('WBC', 0)), 1),
                'RBC': round(float(row.get('RBC', 0)), 1),
                'Hgb': round(float(row.get('Hemoglobin', 0)), 1),
                'Plt': round(float(row.get('Platelets', 0)), 1),
                'Risk Score': f"{score_formatted}%",
                'Risk Level': level,
                'Diagnostic Insights': insights_str,
                'RawData': df.copy() 
            }
            # Prepend to top
            st.session_state['manual_logs'].insert(0, log_entry)
            
            # Simplified instant feedback to avoid "overlapping" clutter
            st.success(f"✅ Success: **{p_name}** ({level} Risk: {score_formatted}%) has been analyzed into the recent logs below.")
            
    except Exception as e:
        st.error(f"Error saving manual entry: {e}")

def render_static_table(styler, height=400):
    try: styler = styler.hide(axis="index")
    except: 
        try: styler = styler.hide_index()
        except: pass
    
    html = styler.to_html()
    return f"""
    <div style="height: {height}px; overflow: auto; border: 1px solid rgba(128,128,128,0.2); border-radius: 5px; margin-bottom: 1rem;">
        <style>
            .cust-tbl table {{ width: auto; min-width: 100%; border-collapse: collapse; text-align: left; font-size: 1rem; table-layout: auto; }}
            .cust-tbl th {{ position: sticky; top: 0; background-color: #1E1E1E; color: #cbd5e1; padding: 4px 6px; border-bottom: 2px solid rgba(128,128,128,0.3); z-index: 10; white-space: nowrap; }}
            .cust-tbl td {{ padding: 3px 6px; border-bottom: 1px solid rgba(128,128,128,0.1); white-space: nowrap; color: #f8fafc; }}
        </style>
        <div class="cust-tbl">{html}</div>
    </div>
    """

def self_heal_data(df, force_refresh=False):
    """Detects and repairs missing risk metadata in datasets without full reprocessing."""
    valid_ls = ["High", "Medium", "Normal"]
    missing_mask = df['Risk Level'].isnull() | (df['Risk Level'] == "None") | (~df['Risk Level'].isin(valid_ls))
    
    if missing_mask.any() or force_refresh:
        to_proc = df[missing_mask | force_refresh]
        if not to_proc.empty:
            X_p, df_f, _ = validate_and_preprocess(to_proc)
            if X_p is not None:
                sc, lv, _ = get_predictions(X_p, df_f)
                df.loc[to_proc.index, 'Risk Score'] = sc
                df.loc[to_proc.index, 'Risk Level'] = lv
    return df

def process_and_display_results(df):
    """Refactored logic to process dataframe, get predictions and display table/charts"""
    with st.spinner("Analyzing patient data in real-time..."):
        X_processed, df_filled, error = validate_and_preprocess(df)
        if error:
            st.error(f"Validation Error: {error}")
            return
            
        scores, levels, pred_error = get_predictions(X_processed, df_filled, model_type='XGBoost')
        if pred_error:
            st.error(pred_error)
            return
        
        # Use the auto-filled dataframe for downstream tasks
        df = df_filled.copy()
        if 'Age' in df.columns:
            df['Age'] = df['Age'].astype(int)
            
        df['Risk Level'] = levels
        # Standardize naming to "Risk Score" to match history
        df['Risk Score'] = scores
        df['Insights'] = df.apply(generate_insights, axis=1)
        
        # Auto-detect gender from patient names for ALL batch records
        name_col = next((c for c in df.columns if 'name' in str(c).lower()), None)
        if name_col:
            df['Gender'] = df[name_col].apply(detect_gender_from_name)
        elif 'Gender' not in df.columns:
            df['Gender'] = 'Unknown'
        
        # Add Record ID and Date placeholders to match history board
        if 'Record ID' not in df.columns:
            # Predict the next available Serial Number from the memory/session
            current_max = get_max_session_serial()
            df.insert(0, 'Record ID', [f"#{current_max + i + 1}" for i in range(len(df))])
        # Prioritize original Date column if present in the source data
        if 'Date' in df.columns:
            # Ensure it's string format for database consistency
            df['Date'] = df['Date'].astype(str)
        else:
            df['Date'] = datetime.now().strftime("%Y-%m-%d %I:%M %p")
        
        # Replace existing results so only the NEW data is shown (per user request)
        st.session_state['current_results'] = df.copy()
        st.session_state['results_page'] = 1
        
        # Batch Save to Database with Duplicate Filtering
        records_saved = 0
        records_skipped = 0
        for i, row in df.iterrows():
            record_time = row['Date']
            p_name = row.get('Patient Name', row.get('PatientName', f"Patient {i+1}"))
            
            # --- DATABASE DUPLICATE CHECK ---
            if check_duplicate_entry(
                user_id=int(st.session_state['user_id']),
                patient_name=str(p_name),
                age=int(row.get('Age', 0)),
                wbc=float(row.get('WBC', 0)),
                rbc=float(row.get('RBC', 0)),
                hgb=float(row.get('Hemoglobin', 0)),
                platelets=float(row.get('Platelets', 0)),
                temp=float(row.get('Temperature', 0))
            ):
                records_skipped += 1
                continue
                
            saved_id = save_prediction(
                user_id=int(st.session_state['user_id']),
                patient_name=str(p_name),
                age=int(row.get('Age', 0)),
                wbc=float(row.get('WBC', 0)),
                rbc=float(row.get('RBC', 0)),
                hgb=float(row.get('Hemoglobin', 0)),
                platelets=float(row.get('Platelets', 0)),
                temp=float(row.get('Temperature', 0)),
                risk_score=float(row.get('Risk Score', 0)),
                risk_level=str(row.get('Risk Level', 'Unknown')),
                timestamp=record_time,
                gender=str(row.get('Gender', detect_gender_from_name(str(p_name))))
            )
            df.at[i, 'Record ID'] = f"#{saved_id}"
            records_saved += 1
            
        if records_skipped > 0:
            st.session_state['batch_msg'] = ("info", f"📊 Summary: {records_saved} new records saved. {records_skipped} duplicate records were identified and skipped.")
        elif records_saved > 0:
            st.session_state['batch_msg'] = ("success", f"✅ Success: All {records_saved} patient records have been analyzed and saved to history.")
            
    # The display of results is handles downstream by show_results_dashboard in the main UI flow based on session state

def show_upload_dashboard():
    st.title("Blood Infection Analysis Panel")
    
    # We provide two tabs again: CSV Upload and Manual Input
    t_batch, t_manual = st.tabs(["📂 Batch Upload (CSV/Excel)", "✍️ Manual Entry (Full Check)"])
    
    with t_batch:
        st.subheader("Batch File Analysis")
        st.write("Upload a dataset containing CBC parameters and vitals. Download a sample format below if you're unsure.")
        
        # Give a small sample format table
        st.markdown("**Expected data format snippet (CSV/Excel):**")
        sample_df = pd.DataFrame([
            {"Patient Name": "Arjun Sharma",  "Gender": "Male",   "WBC": "6500",  "RBC": "4.8", "Hemoglobin": "14.2", "Platelets": "250000", "Temperature": "98.6",  "Age": "45"},
            {"Patient Name": "Priya Patel",   "Gender": "Female", "WBC": "12500", "RBC": "4.2", "Hemoglobin": "11.5", "Platelets": "95000",  "Temperature": "101.5", "Age": "65"},
        ])
        st.table(sample_df)
        

        if 'upload_version' not in st.session_state:
            st.session_state['upload_version'] = 0
            
        uploaded_file = st.file_uploader("Upload CSV or Excel", type=["csv", "xlsx", "xls"], 
                                         key=f"batch_upload_{st.session_state['upload_version']}")

        if uploaded_file is not None:
            try:
                if uploaded_file.name.endswith('.csv'):
                    df = pd.read_csv(uploaded_file)
                else:
                    df = pd.read_excel(uploaded_file)
                
                # Standardize: Rename any column containing 'name' to 'Patient Name'
                name_cols = [c for c in df.columns if 'name' in str(c).lower()]
                if name_cols:
                    df = df.rename(columns={name_cols[0]: 'Patient Name'})
                
                # If still no name column, generate random ones
                if 'Patient Name' not in df.columns:
                    df.insert(0, 'Patient Name', [f"Patient-{random.choice(string.ascii_uppercase)}{random.randint(100,999)}" for _ in range(len(df))])
                    
                # Validate based on medical topics
                col_str = " ".join(df.columns).lower()
                
                medical_keywords = ['wbc', 'rbc', 'hemoglobin', 'platelet', 'temperature', 'age', 'patient', 'infection', 'blood', 'heart', 'glucose', 'sugar', 'pressure', 'disease', 'diagnosis', 'pulse', 'vital', 'doctor', 'hospital', 'clinic', 'symptom']
                non_medical_keywords = ['sales', 'profit', 'employee', 'product', 'order', 'customer', 'fabric', 'revenue', 'cost', 'discount', 'invoice', 'salary', 'retail', 'market', 'saree']
                
                has_medical = any(kw in col_str for kw in medical_keywords)
                has_non_medical = any(kw in col_str for kw in non_medical_keywords)
                
                if has_non_medical or not has_medical:
                    st.error("⚠️ Invalid File Uploaded! The uploaded file does not appear to contain relevant medical data.")
                    st.warning("Please upload a file that belongs to the medical field (e.g., Blood Tests, Vitals, Patient Records).")
                else:
                    st.success("Medical Data parsed successfully!")
                    
                    # Show summary
                    total_patients = len(df)
                    st.markdown(f"**Total Patients Detected:** {total_patients}")
                    
                    df_to_analyze = df.copy()
                    st.markdown(f"**Selected for Analysis:** {len(df_to_analyze)} patients")
                    
                    with st.expander("Preview Selected Data"):
                        st.markdown(render_static_table(df_to_analyze.style, height=400), unsafe_allow_html=True)
                    
                    if st.button("🚀 Run Batch Analysis", width='stretch'):
                        process_and_display_results(df_to_analyze)
                        st.session_state['upload_version'] += 1
                        st.rerun()
                    
            except Exception as e:
                st.error(f"Error reading file: {e}")
                

        # Always handle the display of results inside the Batch tab
        # (Actually, moving it outside tabs for better visibility as per user feedback)
                
    with t_manual:
        st.markdown(f"### 🩺 Single Patient Diagnostic Form")
        st.write("Enter parameters for a single patient to get instant diagnostic insights without affecting the main dashboard batch.")
        
        # Guide section
        with st.expander("ℹ️ Clinical Reference Guide", expanded=False):
            st.markdown("""
| Parameter | Low Range | Normal Range | High Range |
| :--- | :--- | :--- | :--- |
| **Temperature** | < 97 F *(Hypothermia)* | 97 F - 99 F | > 99 F *(Fever)* |
| **WBC Count** | < 4,000 /uL | 4,000 - 11,000 /uL | > 11,000 /uL *(Infection risk)*|
| **RBC (Male)** | < 4.7 million/uL | 4.7 - 6.1 million/uL | > 6.1 million/uL |
| **RBC (Female)** | < 4.2 million/uL | 4.2 - 5.4 million/uL | > 5.4 million/uL |
| **Hemoglobin (Male)**| < 13 g/dL | 13 - 17 g/dL | > 17 g/dL |
| **Hemoglobin (Female)**| < 12 g/dL | 12 - 15 g/dL | > 15 g/dL |
| **Platelets** | < 150,000 /uL | 150,000 - 450,000 /uL| > 450,000 /uL |
            """)

        with st.form("manual_entry_form", clear_on_submit=True):
            colA, colB = st.columns(2)
            with colA:
                st.markdown("#### Demographics")
                p_name = st.text_input("Full Patient Name", "")
                age = st.number_input("Age (Years)", min_value=0, max_value=120, value=None)
                temp = st.number_input("Core Temperature (°F)", min_value=0.0, max_value=110.0, value=None, step=0.1)
            with colB:
                st.markdown("#### Lab Results")
                wbc = st.number_input("WBC Count (/µL)", min_value=0, max_value=300000, value=None, step=100)
                rbc = st.number_input("RBC Count (Mln/µL)", min_value=0.0, max_value=25.0, value=None, step=0.1)
                hgb = st.number_input("Hemoglobin (g/dL)", min_value=0.0, max_value=30.0, value=None, step=0.1)
                plt = st.number_input("Platelets (/µL)", min_value=0, max_value=3000000, value=None, step=5000)
            
            submitted = st.form_submit_button("🩺 RUN INSTANT DIAGNOSTIC")
            
            if submitted:
                # Basic validation
                if not p_name or any(v is None for v in [age, temp, wbc, rbc, hgb, plt]):
                    st.error("⚠️ All fields are mandatory for clinical accuracy.")
                else:
                    manual_df = pd.DataFrame([{
                        'Patient Name': p_name, 'WBC': wbc, 'RBC': rbc, 
                        'Hemoglobin': hgb, 'Platelets': plt, 'Temperature': temp, 'Age': age
                    }])
                    process_manual_entry(manual_df)
        
        # Display Manual Logs with Selective Merge
        if 'manual_logs' in st.session_state and len(st.session_state['manual_logs']) > 0:
            def handle_delete_callback(sel_indices):
                if sel_indices:
                    st.session_state['manual_logs'] = [l for i, l in enumerate(st.session_state['manual_logs']) if i not in sel_indices]
                st.session_state['active_action'] = None
                if "manual_log_editor_top" in st.session_state:
                    st.session_state["manual_log_editor_top"]["edited_rows"] = {}

            def handle_duplicate_callback(sel_indices):
                """Clones selected record into the main dashboard after checking for duplicates."""
                if sel_indices:
                        selected_data_dfs = []
                        existing_uids = []
                        if 'current_results' in st.session_state and st.session_state['current_results'] is not None and 'uid' in st.session_state['current_results'].columns:
                            existing_uids = st.session_state['current_results']['uid'].tolist()
                        
                        duplicate_found = False
                        newly_added = 0
                        
                        for i, log in enumerate(st.session_state['manual_logs']):
                            if i in sel_indices:
                                log_id = log.get('id', str(uuid.uuid4()))
                                
                                # --- COMPREHENSIVE DUPLICATE CHECK (SESSIONS + DB) ---
                                is_in_session = log_id in existing_uids
                                is_in_history = check_duplicate_entry(
                                    user_id=int(st.session_state['user_id']),
                                    patient_name=log['Patient Name'],
                                    age=log['Age'],
                                    wbc=log['WBC'],
                                    rbc=log['RBC'],
                                    hgb=log['Hgb'],
                                    platelets=log['Plt'],
                                    temp=log['Temp']
                                )
                                
                                if is_in_session or is_in_history:
                                    duplicate_found = True
                                else:
                                    df_raw = log['RawData'].copy()
                                    df_raw['uid'] = log_id
                                    # Transfer the predicted Serial No to the dashboard result
                                    df_raw['Record ID'] = log.get('Serial No.', 'NEW')
                                    selected_data_dfs.append(df_raw)
                                    newly_added += 1
                        
                        if duplicate_found and newly_added == 0:
                            return "duplicate"
                            
                        if selected_data_dfs:
                            merged_df_raw = pd.concat(selected_data_dfs, ignore_index=True)
                            X_p, df_f, _ = validate_and_preprocess(merged_df_raw)
                            sc, lv, _ = get_predictions(X_p, df_f)
                            df_f['Risk Score'] = sc
                            df_f['Risk Level'] = lv
                            df_f['Insights'] = df_f.apply(generate_insights, axis=1)
                            if 'Record ID' not in df_f.columns and 'Record ID' in merged_df_raw.columns:
                                df_f.insert(0, 'Record ID', merged_df_raw['Record ID'].values)
                            elif 'Record ID' not in df_f.columns:
                                df_f.insert(0, 'Record ID', 'NEW')
                            if 'Date' not in df_f.columns: df_f['Date'] = datetime.now().strftime("%Y-%m-%d %I:%M:%S %p")
                            
                            # --- COLUMN SYNCHRONIZATION (Prevents NaNs during concat) ---
                            if 'current_results' in st.session_state and st.session_state['current_results'] is not None:
                                # If dash uses 'Serial Number', ensure we match before merge
                                if 'Serial Number' in st.session_state['current_results'].columns and 'Record ID' in df_f.columns:
                                    df_f = df_f.rename(columns={'Record ID': 'Serial Number'})
                                
                                st.session_state['current_results'] = pd.concat([df_f, st.session_state['current_results']], ignore_index=True)
                            else:
                                st.session_state['current_results'] = df_f
                            
                            # Re-map ID column for DB update loop
                            id_col_sync = 'Serial Number' if 'Serial Number' in df_f.columns else 'Record ID'
                                
                            for i, f_row in df_f.iterrows():
                                s_id = save_prediction(int(st.session_state['user_id']), str(f_row.get('Patient Name')), int(f_row.get('Age')), 
                                                 float(f_row.get('WBC')), float(f_row.get('RBC')), float(f_row.get('Hemoglobin')), 
                                                 float(f_row.get('Platelets')), float(f_row.get('Temperature')), float(f_row.get('Risk Score')), 
                                                 str(f_row.get('Risk Level')), timestamp=f_row['Date'],
                                                 gender=str(f_row.get('Gender', detect_gender_from_name(str(f_row.get('Patient Name', ''))))))
                                df_f.at[i, id_col_sync] = f"#{s_id}"
                            
                            if "manual_log_editor_top" in st.session_state:
                                st.session_state["manual_log_editor_top"]["edited_rows"] = {}
                            return "success"
                return "empty"
            st.markdown("---")
            
            # Placeholder for Top Action Bar (Allows buttons to use edited_df results after editor defines it)
            header_placeholder = st.container()
            
            # --- GENDER CLARIFICATION for Manual Logs ---
            unknown_manual = [l for l in st.session_state.get('manual_logs', []) if l.get('Gender', 'Unknown') == 'Unknown']
            if unknown_manual:
                with st.expander(f"🔍 Clarify Gender for {len(unknown_manual)} Recent Check(s)", expanded=True):
                    for m_log in unknown_manual:
                        m_key = f"clarify_m_{m_log['id']}"
                        m_chosen = st.selectbox(f"👤 **{m_log['Patient Name']}**:", ["Unknown", "Male", "Female"], key=m_key)
                        if m_chosen != "Unknown":
                            save_to_gender_cache(m_log['Patient Name'], m_chosen)
                            m_log['Gender'] = m_chosen
                            if 'RawData' in m_log: m_log['RawData']['Gender'] = m_chosen
                            st.rerun()

            log_df_raw = pd.DataFrame(st.session_state['manual_logs']).drop(columns=['RawData'], errors='ignore')
            if 'Serial No.' in log_df_raw.columns:
                try:
                    # Sort numerically (Ascending - counting order: 1, 2, 3...)
                    log_df_raw['sort_key'] = log_df_raw['Serial No.'].astype(str).str.replace("#", "").str.extract(r'(\d+)').astype(float)
                    log_df_raw = log_df_raw.sort_values(by='sort_key', ascending=True).drop(columns=['sort_key'])
                except: pass
            
            # Standardization & Type Safety
            def fmt_no_trail(x):
                try: return f"{float(x):g}" if pd.notnull(x) else x
                except: return x

            for col in log_df_raw.columns:
                if col in ['Age', 'WBC', 'RBC', 'Hemoglobin', 'Platelets', 'Temperature', 'Temp', 'Hgb', 'Plt']:
                    log_df_raw[col] = log_df_raw[col].apply(fmt_no_trail)
                else:
                    log_df_raw[col] = log_df_raw[col].apply(lambda x: " | ".join(x) if isinstance(x, list) else str(x))
            
            col_sel1, col_sel2 = st.columns([8, 2])
            with col_sel2:
                select_all = st.checkbox("Select All", key="select_all_logs")
                
            if "Select" not in log_df_raw.columns:
                log_df_raw.insert(0, "Select", select_all)
            else:
                log_df_raw["Select"] = select_all
            log_df_raw = log_df_raw.rename(columns={'Level': 'Risk Level', 'Risk %': 'Risk Score'})
            log_df_display = log_df_raw.drop(columns=['Diagnostic Insights'])
            
            edited_df = st.data_editor(
                log_df_display,
                column_config={
                    "Select": st.column_config.CheckboxColumn("Select", default=False),
                    "Serial No.": st.column_config.TextColumn("Serial No.", width="small"),
                    "Patient Name": st.column_config.TextColumn("Patient Name", width="medium"),
                    "Gender": st.column_config.TextColumn("Gender", width="small"),
                    "Risk Level": st.column_config.TextColumn("Risk Level", width="small")
                },
                disabled=[col for col in log_df_display.columns if col != "Select"],
                width='stretch',
                hide_index=True,
                key="manual_log_editor_top"
            )

            # Populating Header & Action Buttons in the top container
            with header_placeholder:
                h_c1, h_c2, h_c3 = st.columns([2, 1, 1])
                with h_c1:
                    st.markdown("### 📋 Recent Manual Checks")
                
                # --- COMPACT ACTION STATUS MESSAGE ---
                if 'ui_msg' in st.session_state:
                    m_type, m_text = st.session_state['ui_msg']
                    bg = "#e6fffa" if m_type == "success" else "#fff5f5"
                    tc = "#234e52" if m_type == "success" else "#c53030"
                    bc = "#b2f5ea" if m_type == "success" else "#feb2b2"
                    st.markdown(f'<div style="background-color:{bg}; color:{tc}; padding:8px 12px; border-radius:8px; border:1px solid {bc}; font-size: 1rem; font-weight:600; display:inline-block; margin-bottom:10px;">{m_text}</div>', unsafe_allow_html=True)
                    time.sleep(2)
                    del st.session_state['ui_msg']
                    st.rerun()
            
            # State Initialization for Contextual Actions
            if 'active_action' not in st.session_state: st.session_state['active_action'] = None
            
            with h_c2:
                if st.button("🔀 MERGE", width='stretch', key="top_merge_btn"):
                    selected_indices = edited_df[edited_df['Select'] == True].index.tolist()
                    if not selected_indices:
                        msg = st.empty()
                        msg.warning("⚠️ Select records!")
                        time.sleep(2)
                        msg.empty()
                    elif len(selected_indices) > 1:
                        msg = st.empty()
                        msg.error("⚠️ Please select only 1 record at a time!")
                        time.sleep(2)
                        msg.empty()
                    elif st.session_state['active_action'] in ['delete']:
                        msg = st.empty()
                        msg.error("⚠️ Please complete the current action first.")
                        time.sleep(2)
                        msg.empty()
                    else:
                        st.session_state['active_action'] = 'merge'
                        st.rerun()

                if st.session_state.get('active_action') == 'merge':
                    st.markdown("<style>div.stButton > button p { font-size: 1rem !important; font-weight: bold; }</style>", unsafe_allow_html=True)
                    st.markdown("<p style='font-size: 1rem; font-weight:bold; margin-bottom:5px;'>🏥 Are you sure you want to merge this data?</p>", unsafe_allow_html=True)
                    m_yes, m_no = st.columns([1,1])
                    if m_yes.button("YES", key="top_conf_merge_yes", width='stretch'):
                        # DUPLICATE ACTION Logic (Triggered after confirmation)
                        current_selection = edited_df[edited_df['Select'] == True].index.tolist()
                        result = handle_duplicate_callback(current_selection)
                        if result == "duplicate":
                            msg = st.empty()
                            msg.error("❌data already exists.")
                            time.sleep(2)
                            msg.empty()
                        elif result == "success":
                            st.session_state['ui_msg'] = ("success", "✅ Data merged successfully.")
                        
                        st.session_state['active_action'] = None
                        st.rerun()
                    if m_no.button("NO", key="top_cancel_merge", width='stretch'):
                        st.session_state['active_action'] = None
                        st.rerun()

            with h_c3:
                if st.button("🗑️ DELETE", width='stretch', key="top_delete_btn"):
                    selected_indices = edited_df[edited_df['Select'] == True].index.tolist()
                    if not selected_indices:
                        msg = st.empty()
                        msg.warning("⚠️ Select records!")
                        time.sleep(2)
                        msg.empty()
                    elif st.session_state['active_action'] in ['duplicate', 'merge']:
                        msg = st.empty()
                        msg.error("⚠️ Please complete the current action first.")
                        time.sleep(2)
                        msg.empty()
                    else:
                        st.session_state['active_action'] = 'delete'
                        st.rerun()
                
                if st.session_state.get('active_action') == 'delete':
                    st.markdown("<style>div.stButton > button p { font-size: 1rem !important; font-weight: bold; }</style>", unsafe_allow_html=True)
                    st.markdown("<p style='font-size: 1rem; font-weight:bold; margin-bottom:5px;'>⚠️ Are you sure you want to delete this data?</p>", unsafe_allow_html=True)
                    d_yes, d_no = st.columns([1, 1])
                    if d_yes.button("YES", key="top_conf_del_yes", width='stretch'):
                        current_selection = edited_df[edited_df['Select'] == True].index.tolist()
                        handle_delete_callback(current_selection)
                        st.session_state['ui_msg'] = ("success", "✅ Data deleted successfully.")
                        st.rerun()
                    if d_no.button("NO", key="top_cancel_del", width='stretch'):
                        st.session_state['active_action'] = None
                        st.rerun()
            
            # Diagnostic Report Search Section
            st.markdown("#### 🩺 In-Depth Clinical Evaluation")
            patient_names_in_logs = log_df_raw['Patient Name'].tolist()
            selected_patient_for_report = st.selectbox(
                "Select patient profile for comprehensive diagnostic analysis:", 
                patient_names_in_logs, 
                index=None, 
                placeholder="🔍 Type patient name to search...",
                key="report_viewer_select"
            )
            
            if selected_patient_for_report:
                selected_row = log_df_raw[log_df_raw['Patient Name'] == selected_patient_for_report].iloc[0]
                insights_str = selected_row['Diagnostic Insights']
                with st.expander(f"🩺 Diagnostic Insights for {selected_patient_for_report}", expanded=True):
                    statuses = get_parameter_statuses(selected_row)
                    st.markdown("**Parameter Status Breakdown:**")
                    cols = st.columns(len(statuses))
                    for i, (param, status) in enumerate(statuses.items()):
                        color = "#ef4444" if status in ["High", "Low"] else "#22c55e"
                        icon = "🔺" if status == "High" else "🔻" if status == "Low" else "✅"
                        cols[i].markdown(f"<div style='text-align:center; padding:5px; background-color:rgba(128,128,128,0.1); border-radius:5px; margin-bottom:10px;'><b>{param}</b><br><span style='color:{color}; font-weight:bold;'>{icon} {status}</span></div>", unsafe_allow_html=True)
                    st.markdown("---")
                    st.markdown(insights_str.replace(" | ", "\n\n"))
        
    # Always handle the display of results at the end of dashboard for visibility
    if 'current_results' in st.session_state:
        show_results_dashboard()

def show_results_dashboard():
    if 'current_results' in st.session_state and st.session_state['current_results'] is not None:
        df_res = st.session_state['current_results']
        
        st.markdown("---")
        
        if 'batch_msg' in st.session_state:
            m_type, m_text = st.session_state['batch_msg']
            if m_type == "info":
                st.info(m_text)
            else:
                st.success(m_text)
            del st.session_state['batch_msg']
            
        # Premium Filter Section
        with st.expander("🔍 Advanced Filters", expanded=True):
            f1, f2, f3 = st.columns(3)
            with f1:
                search_name = st.text_input("Search Patient Name", "")
                has_name_col = any('name' in str(c).lower() for c in df_res.columns)
                if search_name and not has_name_col:
                    st.warning("⚠️ No 'Name' column found in this dataset.")
            with f2:
                f_risk = st.multiselect("Risk Level", ["High", "Medium", "Normal"], default=[])
            with f3:
                has_age = 'Age' in df_res.columns
                f_age_min = st.number_input("Min Age", 0, 120, 0) if has_age else 0
                f_age_max = st.number_input("Max Age", 0, 120, 120) if has_age else 120
        # --- GLOBAL HEALTH CHECK & STANDARDIZATION ---
        # Rename mapping to ensure Consistency
        rename_map = {
            'Risk Score (%)': 'Risk Score',
            'Risk %': 'Risk Score',
            'Level': 'Risk Level',
            'Record ID': 'Serial Number'
        }
        
        # Apply renaming safely avoiding duplicate columns
        for old_col, new_col in rename_map.items():
            if old_col in df_res.columns:
                if new_col in df_res.columns and old_col != new_col:
                    # Drop existing or temporary if it conflicts to prevent 2 columns of same name
                    df_res = df_res.drop(columns=[new_col], errors='ignore')
                df_res = df_res.rename(columns={old_col: new_col})
        
        # Deduplicate column names (Absolute insurance for export)
        df_res = df_res.loc[:, ~df_res.columns.duplicated()]
        
        # Ensure mandatory columns exist
        for col in ['Risk Level', 'Risk Score', 'Patient Name', 'Age', 'WBC']:
            if col not in df_res.columns:
                df_res[col] = "N/A"
        
        # Specific Drop for redundant 'Level' before export if it exists alongside 'Risk Level'
        if 'Level' in df_res.columns and 'Risk Level' in df_res.columns:
            df_res = df_res.drop(columns=['Level'])
        
        # Optimized History Sync / Self-Healing
        df_res = self_heal_data(df_res, st.session_state.get('force_risk_refresh', False))
        
        # --- SEQUENTIAL SORTING (Counting Manner - Newest First) ---
        id_col_sort = 'Serial Number' if 'Serial Number' in df_res.columns else 'Record ID'
        if id_col_sort in df_res.columns:
            try:
                # Extract numbers correctly and sort ASCENDING (Counting Manner: 1, 2, 3...)
                df_res['sort_key'] = df_res[id_col_sort].astype(str).str.replace("#", "").str.extract(r'(\d+)').astype(float)
                df_res = df_res.sort_values(by='sort_key', ascending=True).drop(columns=['sort_key'])
            except: pass

        st.session_state['current_results'] = df_res
        st.session_state['force_risk_refresh'] = False

        # --- GENDER CLARIFICATION for Unknown names ---
        if 'Gender' in df_res.columns:
            unknown_gender_mask = df_res['Gender'].isin(['Unknown', '', None]) | df_res['Gender'].isnull()
            unknown_gender_rows = df_res[unknown_gender_mask]
            if not unknown_gender_rows.empty:
                st.markdown(f"<h2 style='color: #fbbf24; margin-bottom: 0;'>🚻 Gender Correction Tool</h2>", unsafe_allow_html=True)
                with st.expander(f"🔍 Clarification Needed for {len(unknown_gender_rows)} patient(s)", expanded=True):
                    st.caption("Names below could not be auto-detected. Please select gender to continue:")
                    changed = False
                    for idx, row in unknown_gender_rows.iterrows():
                        p_name = row.get('Patient Name', f'Patient-{idx+1}')
                        key = f"res_gender_{idx}"
                        chosen = st.selectbox(
                            f"👤 **{p_name}** — Select Gender:",
                            ["Unknown", "Male", "Female"],
                            key=key
                        )
                        if chosen != 'Unknown':
                            # Persist the choice and rerun to clear the prompt
                            save_to_gender_cache(p_name, chosen)
                            df_res.at[idx, 'Gender'] = chosen
                            
                            # Update DB if record already exists
                            rec_id = row.get('Record ID')
                            if rec_id and rec_id != 'NEW':
                                try: update_prediction_gender(rec_id, chosen)
                                except: pass
                                
                            st.session_state['current_results'] = df_res.copy()
                            st.rerun()
                
        # Apply Filters
        mask = pd.Series([True] * len(df_res), index=df_res.index)
        
        if f_risk:
            mask &= df_res['Risk Level'].isin(f_risk)
            
        if search_name.strip():
            term = search_name.strip()
            # Perform a GLOBAL search across all columns for maximum reliability
            search_mask = pd.Series([False] * len(df_res), index=df_res.index)
            for col in df_res.columns:
                search_mask |= df_res[col].astype(str).str.contains(term, case=False, na=False)
            mask &= search_mask
                
        if has_age:
            mask &= (df_res['Age'] >= f_age_min) & (df_res['Age'] <= f_age_max)
            
        filtered_df = df_res[mask].copy()
        
        # Restrict decimal precision to 1 globally for medical accuracy
        num_cols = filtered_df.select_dtypes(include=[np.number]).columns
        for c in num_cols:
            filtered_df[c] = filtered_df[c].round(1)
            
        # Safe-guard for metrics display to prevent KeyError
        for col_req in ['Risk Level', 'Risk Score', 'Age', 'WBC']:
            if col_req not in filtered_df.columns:
                filtered_df[col_req] = "N/A"
        
        # Pagination Logic for Batch Results
        results_per_page = 50
        total_filtered = len(filtered_df)
        total_results_pages = max(1, math.ceil(total_filtered / results_per_page))
        
        # Ensure current page is within bounds
        if st.session_state.results_page > total_results_pages:
            st.session_state.results_page = total_results_pages

        st.markdown("""
            <style>
                /* Hide spin-buttons for number inputs */
                input[type=number]::-webkit-inner-spin-button, 
                input[type=number]::-webkit-outer-spin-button { 
                    -webkit-appearance: none;
                    margin: 0; 
                }
                input[type=number] { -moz-appearance: textfield; }
            </style>
        """, unsafe_allow_html=True)
        # Slice the dataframe for the current page
        start_idx = (st.session_state.results_page - 1) * results_per_page
        end_idx = start_idx + results_per_page
        df_page = filtered_df.iloc[start_idx:end_idx]

        # -- Data preparation for Quick Insights bar --
        high_risk_count = len(filtered_df[filtered_df['Risk Level'] == 'High'])
        medium_risk_count = len(filtered_df[filtered_df['Risk Level'] == 'Medium'])
        normal_risk_count = len(filtered_df[filtered_df['Risk Level'] == 'Normal'])
        avg_risk_score = filtered_df['Risk Score'].mean() if not filtered_df.empty else 0

        m1, m2, m3, m4, m5, m6 = st.columns([1, 1, 1, 1, 1, 1.2])
        with m1:
            st.markdown(f"""
                <div style='background: rgba(34, 197, 94, 0.03); border: 1px solid rgba(34, 197, 94, 0.1); border-radius: 6px; padding: 4px; text-align: center;'>
                    <p style='color: #94a3b8; font-size: 1rem; margin: 0; text-transform: uppercase;'>Total</p>
                    <p style='color: #22c55e; font-size: 1rem; font-weight: 600; margin: 0;'>{total_filtered}</p>
                </div>
            """, unsafe_allow_html=True)
        with m2:
            st.markdown(f"""
                <div style='background: rgba(249, 115, 22, 0.03); border: 1px solid rgba(249, 115, 22, 0.1); border-radius: 6px; padding: 4px; text-align: center;'>
                    <p style='color: #94a3b8; font-size: 1rem; margin: 0; text-transform: uppercase;'>Patients</p>
                    <p style='color: #f97316; font-size: 1rem; font-weight: 600; margin: 0;'>{len(df_page)}</p>
                </div>
            """, unsafe_allow_html=True)
        with m3:
            st.markdown(f"""
                <div style='background: rgba(239, 68, 68, 0.03); border: 1px solid rgba(239, 68, 68, 0.1); border-radius: 6px; padding: 4px; text-align: center;'>
                    <p style='color: #94a3b8; font-size: 1rem; margin: 0; text-transform: uppercase;'>High</p>
                    <p style='color: #ef4444; font-size: 1rem; font-weight: 600; margin: 0;'>{high_risk_count}</p>
                </div>
            """, unsafe_allow_html=True)
        with m4:
            st.markdown(f"""
                <div style='background: rgba(249, 115, 22, 0.03); border: 1px solid rgba(249, 115, 22, 0.1); border-radius: 6px; padding: 4px; text-align: center;'>
                    <p style='color: #94a3b8; font-size: 1rem; margin: 0; text-transform: uppercase;'>Med</p>
                    <p style='color: #f97316; font-size: 1rem; font-weight: 600; margin: 0;'>{medium_risk_count}</p>
                </div>
            """, unsafe_allow_html=True)
        with m5:
            st.markdown(f"""
                <div style='background: rgba(34, 197, 94, 0.03); border: 1px solid rgba(34, 197, 94, 0.1); border-radius: 6px; padding: 4px; text-align: center;'>
                    <p style='color: #94a3b8; font-size: 1rem; margin: 0; text-transform: uppercase;'>Normal</p>
                    <p style='color: #22c55e; font-size: 1rem; font-weight: 600; margin: 0;'>{normal_risk_count}</p>
                </div>
            """, unsafe_allow_html=True)
        with m6:
            st.markdown(f"""
                <div style='background: rgba(56, 189, 248, 0.03); border: 1px solid rgba(56, 189, 248, 0.1); border-radius: 6px; padding: 4px; text-align: center;'>
                    <p style='color: #94a3b8; font-size: 1rem; margin: 0; text-transform: uppercase;'>Avg Risk</p>
                    <p style='color: #38bdf8; font-size: 1rem; font-weight: 600; margin: 0;'>{avg_risk_score:.1f}%</p>
                </div>
            """, unsafe_allow_html=True)

        st.markdown("<br>", unsafe_allow_html=True)
        
        # Results Navigation UI (Page Selection Only)
        _, r_nav_center, _ = st.columns([1.5, 1, 1.5])
        with r_nav_center:
            st.markdown(f"<div style='text-align:center; font-weight:bold; padding-top:2px; font-size: 1rem;'>PAGE {st.session_state.results_page}/{total_results_pages}</div>", unsafe_allow_html=True)
            # Unified input: changing this box directly searches/updates the page state
            st.number_input("Go to Page", 1, total_results_pages, key="results_page", label_visibility="collapsed")

        st.markdown("<br>", unsafe_allow_html=True)

        # Data View Tabs
        tab_data, tab_charts, tab_tips = st.tabs(["📋 Data Records", "📊 Visual Analytics", "💡 Diagnosis & Preventive Care"])
        
        with tab_data:
            # Match the exact column order of the History board (including Record IDs)
            candidate_cols = ['Record ID', 'Serial Number', 'Patient Name', 'Gender', 'Age', 'WBC', 'RBC', 'Hemoglobin', 'Platelets', 'Temperature', 'Risk Level', 'Date']
            # Only use columns that exist in the dataframe
            disp_cols = [c for c in candidate_cols if c in df_page.columns]
            
            # If no name column found in candidates, try to find any column containing 'name'
            if 'Patient Name' not in disp_cols:
                n_cols = [c for c in df_page.columns if 'name' in str(c).lower()]
                if n_cols: disp_cols.insert(1, n_cols[0])
            
            def highlight_risk(row):
                lv = row.get('Risk Level', '')
                if lv == 'High': return ['background-color: rgba(239, 68, 68, 0.12)'] * len(row)
                if lv == 'Medium': return ['background-color: rgba(249, 115, 22, 0.12)'] * len(row)
                if lv == 'Normal': return ['background-color: rgba(34, 197, 94, 0.08)'] * len(row)
                return [''] * len(row)
                
            formatter = {}
            for c in disp_cols:
                if c in ['Age', 'WBC', 'RBC', 'Hemoglobin', 'Platelets', 'Temperature']:
                    formatter[c] = lambda x: f"{float(x):g}" if pd.notnull(x) else x

            if disp_cols:
                st.markdown(render_static_table(df_page[disp_cols].style.apply(highlight_risk, axis=1).format(formatter), height=500), unsafe_allow_html=True)
            else:
                st.info("No matching data columns found to display.")
            
            # View Detailed Report Section
            st.markdown("#### 🩺 In-Depth Clinical Evaluation")
            
            # Identify name column safely
            name_cols = [c for c in filtered_df.columns if 'name' in str(c).lower()]
            found_name_col = name_cols[0] if name_cols else None
            
            if found_name_col and 'Insights' in filtered_df.columns:
                patient_names_in_data = filtered_df[found_name_col].tolist()
                selected_data_patient = st.selectbox(
                    "Select patient profile for comprehensive diagnostic analysis:", 
                    patient_names_in_data, 
                    index=None, 
                    placeholder="🔍 Type patient name to search...",
                    key="data_report_select"
                )
                
                if selected_data_patient:
                    selected_row = filtered_df[filtered_df[found_name_col] == selected_data_patient].iloc[0]
                    insights_data = selected_row.get('Insights', [])
                    
                    with st.expander(f"🩺 Diagnostic Insights for {selected_data_patient}", expanded=True):
                        # Parameter Status Indicators
                        statuses = get_parameter_statuses(selected_row)
                        st.markdown("**Parameter Status Breakdown:**")
                        cols = st.columns(len(statuses))
                        for i, (param, status) in enumerate(statuses.items()):
                            color = "#ef4444" if status in ["High", "Low"] else "#22c55e"
                            icon = "🔺" if status == "High" else "🔻" if status == "Low" else "✅"
                            cols[i].markdown(f"<div style='text-align:center; padding:5px; background-color:rgba(128,128,128,0.1); border-radius:5px; margin-bottom:10px;'><b>{param}</b><br><span style='color:{color}; font-weight:bold;'>{icon} {status}</span></div>", unsafe_allow_html=True)
                        st.markdown("---")

                        if isinstance(insights_data, list):
                            formatted_insights = "\n\n".join(insights_data)
                        else:
                            formatted_insights = str(insights_data).replace(" | ", "\n\n")
                        st.markdown(formatted_insights)
            
            # Export Data
            if not filtered_df.empty:
                col_exp1, col_exp2 = st.columns(2)
                with col_exp1:
                    csv_data = cached_to_data(filtered_df, 'csv')
                    st.download_button("📥 Download Filtered Records (CSV)", csv_data, "blood_infection_results.csv", "text/csv", width='stretch')
                with col_exp2:
                    excel_data = cached_to_data(filtered_df, 'excel')
                    st.download_button("📥 Download Filtered Records (Excel)", excel_data, "blood_infection_results.xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", width='stretch')
                
        with tab_charts:
            if len(filtered_df) > 0:
                # 1. Global View
                st.markdown(f"### 🌏 Global Risk Distribution (Across {total_filtered} Records)")
                fig_pie = px.pie(filtered_df, names='Risk Level', color='Risk Level', hole=0.4,
                             color_discrete_map={'High':'#ef4444', 'Medium':'#f97316', 'Normal':'#22c55e'})
                fig_pie = apply_common_plotly_layout(fig_pie, "Global Risk Breakdown")
                st.plotly_chart(fig_pie, width='stretch')
                
                # 2. Synchronized Page View
                st.markdown(f"### 🔬 Page Analytics (Comparing Records {start_idx + 1}-{min(end_idx, total_filtered)})")
                # Identify name column safely for hover
                name_cols = [c for c in df_page.columns if 'name' in str(c).lower()]
                found_name = name_cols[0] if name_cols else None
                
                h_data = {
                    'Age': True, 'Risk Level': True,
                    'WBC': ':.1f', 'RBC': ':.2f', 'Hemoglobin': ':.1f', 'Temperature': ':.1f'
                }
                h_data = {k: v for k, v in h_data.items() if k in df_page.columns}

                fig_scatter = px.scatter(
                    df_page, x='WBC', y='Age', color='Risk Level',
                    hover_name=found_name if found_name else None,
                    color_discrete_map={'High':'#ef4444', 'Medium':'#f97316', 'Normal':'#22c55e'},
                    hover_data=h_data,
                    render_mode='webgl'
                )
                fig_scatter = apply_common_plotly_layout(fig_scatter, f"Clinical Trend (Current Page Results)")
                st.plotly_chart(fig_scatter, width='stretch')
                st.caption("💡 This graph shows patients from the current page of your results. Change the page in 'Data Records' to see different data.")
            else:
                st.warning("No data matches the current filters for visualization.")
                
        with tab_tips:
            st.markdown("### 🩺 Clinical AI Insights & Preventive Measures")
            st.write("Based on the **filtered patients** currently viewed, here are targeted disease probabilities and medical advice.")
            
            if len(filtered_df) == 0:
                st.info("No records loaded to generate tips.")
            else:
                for idx, row in filtered_df.iterrows():
                    p_name = row.get('Patient Name', f"Patient-{idx+1}")
                    
                    with st.expander(f"🔬 Analysis for {p_name} - Risk: {row['Risk Level']}"):
                        tc1, tc2 = st.columns(2)
                        with tc1:
                            st.markdown("#### 🦠 Possible Conditions Detected")
                            # Extract parameters for both tc1 and tc2 blocks
                            wbc, plt, temp, hgb = row.get('WBC', 0), row.get('Platelets', 0), row.get('Temperature', 0), row.get('Hemoglobin', 0)
                            
                            analysis_text = generate_insights(row)
                            st.markdown(analysis_text)
                                
                        with tc2:
                            st.markdown("#### 🛡️ Preventive Tips & Action")
                            age = float(row.get('Age', 30))
                            risk = row['Risk Level']
                            
                            tips = []
                            if risk == 'High':
                                tips.append("🚨 **High Risk Warning:** Admit patient for monitoring and IV antibiotics. Draw blood cultures instantly.")
                            elif risk == 'Medium':
                                if age > 65:
                                    tips.append("⚠️ **Senior Care Caution:** Close at-home monitoring recommended. Look out for confusion or sudden weakness.")
                                else:
                                    tips.append("⚠️ **Caution Advised:** Schedule a follow-up in 48 hours. Stay hydrated and avoid strenuous exertion.")
                            else:
                                tips.append("✅ **Baseline Physiology / Normal:** Maintain standard hygiene, take daily multivitamins, and keep a healthy routine.")

                            # Add parameter-specific tips
                            if temp > 100.4:
                                if age < 12:
                                    tips.append("🌡️ **Fever Management:** Use tepid sponging. Avoid aspirin. Monitor for febrile seizures.")
                                else:
                                    tips.append("🌡️ **Fever Management:** Administer prescribed antipyretics and maintain significant fluid intake.")
                            elif temp < 95.0:
                                tips.append("❄️ **Hypothermia Warning:** Provide warm blankets and warm beverages. Cover head and extremities.")
                                
                            if wbc < 4000:
                                tips.append("🦠 **Immunity Precaution:** Low WBC. Patient should wear a mask and avoid crowded or unhygienic places.")
                            
                            if hgb < 12.0:
                                tips.append("🥩 **Dietary Advice:** Low Hemoglobin. Increase intake of iron-rich foods (spinach, beans, red meat) or consider supplements.")
                                
                            if plt < 150000:
                                tips.append("🩸 **Bleeding Risk:** Low platelets. Avoid NSAIDs, use a soft toothbrush, and avoid injury-prone activities.")

                            # Output the stacked tips
                            combined_tips = "\n\n".join(tips)
                            if risk == 'Critical': st.error(combined_tips)
                            elif risk == 'High': st.error(combined_tips)
                            elif risk == 'Medium': st.warning(combined_tips)
                            else: st.success(combined_tips)

def show_reports():
    st.title("My Past Reports & Dashboard Logs")
    st.write("Complete history of analyzed patients. Optimized for bulk data handling.")
    
    # --- SEARCH & FILTER SECTION ---
    with st.expander("🔍 Search & Filter History", expanded=True):
        sc1, sc2 = st.columns(2)
        with sc1:
            search_name = st.text_input("Enter Patient Name:", key="hist_search_name")
        with sc2:
            search_risk = st.selectbox("Select Risk Level filter:", ["All", "High", "Medium", "Normal"], key="hist_search_risk")

    # Fetch Total Count for Pagination (based on search)
    total_records = get_history_count(st.session_state['user_id'], search_name, search_risk)
    
    if total_records == 0:
        st.info("No reports found matching your criteria.")
        return

    # Pagination Settings
    page_size = 50
    total_pages = (total_records + page_size - 1) // page_size
    
    # Reset page if search criteria change
    search_key = f"{search_name}_{search_risk}"
    if st.session_state.get('last_search_key') != search_key:
        st.session_state['hist_page'] = 1
        st.session_state['last_search_key'] = search_key

    # Ensure hist_page exists in session state
    if 'hist_page' not in st.session_state:
        st.session_state['hist_page'] = 1
        
    # Clamp page to valid range
    if st.session_state['hist_page'] > total_pages:
        st.session_state['hist_page'] = total_pages
    if st.session_state['hist_page'] < 1:
        st.session_state['hist_page'] = 1
        
    # 1. Data Retrieval (Prioritized before UI for state safety)
    offset = (st.session_state['hist_page'] - 1) * page_size
    records = search_history(st.session_state['user_id'], search_name, search_risk, limit=page_size, offset=offset)
    
    # Create df_page early for metrics
    df_page = pd.DataFrame(records, columns=[
        'Serial Number', 'Patient Name', 'Age', 'WBC', 'RBC', 'Hemoglobin', 'Platelets', 'Temperature', 'Risk Score', 'Risk Level', 'Date', 'Gender'
    ])
    # Auto-detect gender from name; for already-stored gender use DB value, fill Unknown via name
    df_page['Gender'] = df_page.apply(
        lambda r: r['Gender'] if r['Gender'] not in ('Unknown', None, '') else detect_gender_from_name(r['Patient Name']),
        axis=1
    )
    # Round numeric columns
    num_cols = ['Age', 'WBC', 'RBC', 'Hemoglobin', 'Platelets', 'Temperature', 'Risk Score']
    df_page[num_cols] = df_page[num_cols].round(1)
    # Self-heal ONLY the current page (fast)
    df_page = self_heal_data(df_page)

    # 2. Metrics & Page Info
    # Format the Last Analysis timestamp to remove seconds if present
    last_analysis = records[0][-1] if records else "N/A"
    if isinstance(last_analysis, str) and ":" in last_analysis:
        try:
            parts = last_analysis.split(":")
            if len(parts) >= 3:
                suffix = parts[2].split(" ")[1] if " " in parts[2] else ""
                last_analysis = f"{parts[0]}:{parts[1]} {suffix}".strip()
        except: pass

    # -- Fetch page-specific insights for reports --
    page_avg_risk = df_page['Risk Score'].mean() if not df_page.empty else 0
    high_risk_page = len(df_page[df_page['Risk Level'] == 'High'])
    medium_risk_page = len(df_page[df_page['Risk Level'] == 'Medium'])
    normal_risk_page = len(df_page[df_page['Risk Level'] == 'Normal'])

    m_col1, m_col2, m_col3, m_col4, m_col5, m_col6, m_col7 = st.columns([1, 1, 1.6, 1, 1, 1, 1.2])
    
    with m_col1:
        st.markdown(f"""
            <div style='background: rgba(34, 197, 94, 0.03); border: 1px solid rgba(34, 197, 94, 0.1); border-radius: 6px; padding: 4px; text-align: center;'>
                <p style='color: #94a3b8; font-size: 1rem; margin: 0; text-transform: uppercase;'>Total</p>
                <p style='color: #22c55e; font-size: 1rem; font-weight: 600; margin: 0;'>{total_records}</p>
            </div>
        """, unsafe_allow_html=True)

    with m_col2:
        st.markdown(f"""
            <div style='background: rgba(249, 115, 22, 0.03); border: 1px solid rgba(249, 115, 22, 0.1); border-radius: 6px; padding: 4px; text-align: center;'>
                <p style='color: #94a3b8; font-size: 1rem; margin: 0; text-transform: uppercase;'>Patients</p>
                <p style='color: #f97316; font-size: 1rem; font-weight: 600; margin: 0;'>{len(records)}</p>
            </div>
        """, unsafe_allow_html=True)
    
    with m_col3:
        st.markdown(f"""
            <div style='background: rgba(56, 189, 248, 0.03); border: 1px solid rgba(56, 189, 248, 0.1); border-radius: 6px; padding: 4px; text-align: center;'>
                <p style='color: #94a3b8; font-size: 1rem; margin: 0; text-transform: uppercase;'>Last Analysis</p>
                <p style='color: #38bdf8; font-size: 1rem; font-weight: 600; margin: 0;'>{last_analysis}</p>
            </div>
        """, unsafe_allow_html=True)

    with m_col4:
        st.markdown(f"""
            <div style='background: rgba(239, 68, 68, 0.03); border: 1px solid rgba(239, 68, 68, 0.1); border-radius: 6px; padding: 4px; text-align: center;'>
                <p style='color: #94a3b8; font-size: 1rem; margin: 0; text-transform: uppercase;'>High</p>
                <p style='color: #ef4444; font-size: 1rem; font-weight: 600; margin: 0;'>{high_risk_page}</p>
            </div>
        """, unsafe_allow_html=True)

    with m_col5:
        st.markdown(f"""
            <div style='background: rgba(249, 115, 22, 0.03); border: 1px solid rgba(249, 115, 22, 0.1); border-radius: 6px; padding: 4px; text-align: center;'>
                <p style='color: #94a3b8; font-size: 1rem; margin: 0; text-transform: uppercase;'>Med</p>
                <p style='color: #f97316; font-size: 1rem; font-weight: 600; margin: 0;'>{medium_risk_page}</p>
            </div>
        """, unsafe_allow_html=True)

    with m_col6:
        st.markdown(f"""
            <div style='background: rgba(34, 197, 94, 0.03); border: 1px solid rgba(34, 197, 94, 0.1); border-radius: 6px; padding: 4px; text-align: center;'>
                <p style='color: #94a3b8; font-size: 1rem; margin: 0; text-transform: uppercase;'>Normal</p>
                <p style='color: #22c55e; font-size: 1rem; font-weight: 600; margin: 0;'>{normal_risk_page}</p>
            </div>
        """, unsafe_allow_html=True)

    with m_col7:
        st.markdown(f"""
            <div style='background: rgba(168, 85, 247, 0.03); border: 1px solid rgba(168, 85, 247, 0.1); border-radius: 6px; padding: 4px; text-align: center;'>
                <p style='color: #94a3b8; font-size: 1rem; margin: 0; text-transform: uppercase;'>Avg Risk</p>
                <p style='color: #a855f7; font-size: 1rem; font-weight: 600; margin: 0;'>{page_avg_risk:.1f}%</p>
            </div>
        """, unsafe_allow_html=True)
    
    st.markdown("---")
    
    # 2. Centralized Navigation (Page Selection Only)
    _, n_center, _ = st.columns([1.5, 1, 1.5])
        
    with n_center:
        st.markdown(f"<div style='text-align: center; margin-bottom: 2px; color: #94a3b8; font-size: 1rem;'>PAGE <b>{st.session_state['hist_page']}</b>/{total_pages}</div>", unsafe_allow_html=True)
        # Unified input: changing this box directly searches/updates the page state
        st.number_input("Go to:", min_value=1, max_value=total_pages, key="hist_page", label_visibility="collapsed")
        
    st.markdown(f"<p style='text-align: center; color: #64748b;'>Showing {offset + 1} to {min(offset + page_size, total_records)} of {total_records} records</p>", unsafe_allow_html=True)
    
    # Fetch only CURRENT PAGE records (with visual feedback for bulk handling)
    
    df_page = pd.DataFrame(records, columns=[
        'Serial Number', 'Patient Name', 'Age', 'WBC', 'RBC', 'Hemoglobin', 'Platelets', 'Temperature', 'Risk Score', 'Risk Level', 'Date', 'Gender'
    ])
    
    # Auto-detect / fill gender
    df_page['Gender'] = df_page.apply(
        lambda r: r['Gender'] if r['Gender'] not in ('Unknown', None, '') else detect_gender_from_name(r['Patient Name']),
        axis=1
    )
    
    # --- ASK USER to clarify Unknown gender names ---
    unknown_rows = df_page[df_page['Gender'] == 'Unknown']
    if not unknown_rows.empty:
        st.markdown("#### 🔍 Gender Clarification Needed")
        st.caption("The following patient names could not be auto-detected. Please select gender:")
        for idx, row in unknown_rows.iterrows():
            key = f"gender_override_{row['Serial Number']}"
            chosen = st.selectbox(
                f"👤 **{row['Patient Name']}** — Select Gender:",
                ["Unknown", "Male", "Female"],
                key=key
            )
            if chosen != 'Unknown':
                save_to_gender_cache(row['Patient Name'], chosen)
                
                # Update DB immediately
                rec_id = row.get('Serial Number') # In reports it is Serial Number
                if rec_id:
                    try: update_prediction_gender(rec_id, chosen)
                    except: pass
                    
                st.rerun()
    # ── Disease Prediction Helper ──────────────────────────────────────────────
def predict_possible_disease(row):
    try:
        wbc = float(row.get('WBC', 0))
        platelets = float(row.get('Platelets', 0))
        hgb = float(row.get('Hemoglobin', 0))
        temp = float(row.get('Temperature', 0))
        rbc = float(row.get('RBC', 0))

        diseases = []

        # Dengue
        if platelets < 100000 and temp >= 100:
            diseases.append("Possible Dengue")

        # Bacterial Infection
        if wbc > 11000 and temp >= 100:
            diseases.append("Possible Bacterial Infection")

        # Viral Infection
        if wbc < 4000 and temp >= 99:
            diseases.append("Possible Viral Infection")

        # Anemia
        if hgb < 10:
            diseases.append("Possible Anemia")

        # Leukemia Risk
        if wbc > 50000:
            diseases.append("Possible Leukemia Risk")

        # Thrombocytopenia
        if platelets < 150000:
            diseases.append("Possible Thrombocytopenia")

        # Sepsis Risk
        if wbc > 15000 and temp > 101 and platelets < 150000:
            diseases.append("Possible Sepsis Risk")

        if not diseases:
            return "No Major Disease Pattern Detected"

        return ", ".join(diseases)

    except:
        return "Unable to Predict"
    
    # Round numeric columns
    num_cols = ['Age', 'WBC', 'RBC', 'Hemoglobin', 'Platelets', 'Temperature', 'Risk Score']
    df_page[num_cols] = df_page[num_cols].round(1)
    
    # Self-heal ONLY the current page (fast)
    df_page = self_heal_data(df_page)
    
    # --- METRICS (requires full data summary, but we can do this fast in SQL if needed, 
    # for now we'll just show the total count from the search) ---

    # Data View Tabs
    tab_h_logs, tab_h_charts = st.tabs(["📋 Patient Logs / History", "📊 Historical Analytics"])
    
    with tab_h_logs:
        
        def highlight_row(r):
            lv = r.get('Risk Level', '')
            if lv == 'High': return ['background-color: rgba(239, 68, 68, 0.12)'] * len(r)
            if lv == 'Medium': return ['background-color: rgba(249, 115, 22, 0.12)'] * len(r)
            if lv == 'Normal': return ['background-color: rgba(34, 197, 94, 0.08)'] * len(r)
            return [''] * len(r)
            
        st.markdown("""
            <style>
                /* Hide spin-buttons for number inputs */
                input[type=number]::-webkit-inner-spin-button, 
                input[type=number]::-webkit-outer-spin-button { 
                    -webkit-appearance: none;
                    margin: 0; 
                }
                input[type=number] { -moz-appearance: textfield; }
            </style>
        """, unsafe_allow_html=True)
        st.markdown("---")
        h_disp_cols = ['Serial Number', 'Patient Name', 'Gender', 'Age', 'WBC', 'RBC', 'Hemoglobin', 'Platelets', 'Temperature', 'Risk Level', 'Date']
        df_display = df_page[[c for c in h_disp_cols if c in df_page.columns]]
        
        formatter_h = {}
        for c in h_disp_cols:
            if c in ['Age', 'WBC', 'RBC', 'Hemoglobin', 'Platelets', 'Temperature']:
                formatter_h[c] = lambda x: f"{float(x):g}" if pd.notnull(x) else x
        
        st.markdown(render_static_table(df_display.style.apply(highlight_row, axis=1).format(formatter_h), height=600), unsafe_allow_html=True)
        
        # --- CLINICAL RECORD MANAGEMENT CONTROLLER (Deletion) ---
        st.markdown("---")
        st.markdown("#### 🗑️ Data Management Operations")
        del_c1, del_c2, del_c3 = st.columns([1.5, 2, 1])
        
        with del_c1:
            management_scope = st.selectbox(
                "Select Deletion Scope:",
                ["Select Action...", "Specific Individual Record", "Entire Current Page", "Full Search Results Match"],
                key="hist_del_scope"
            )
            
        with del_c2:
            target_ids = []
            display_msg = ""
            
            if management_scope == "Specific Individual Record":
                record_list = df_page['Serial Number'].tolist()
                del_id = st.selectbox(
                    "Choose Patient Identification (from current page):",
                    options=[None] + record_list,
                    format_func=lambda x: f"Select..." if x is None else f"ID {x} - {df_page.loc[df_page['Serial Number'] == x, 'Patient Name'].values[0]}",
                    key="hist_del_id_tgt"
                )
                if del_id:
                    target_ids = [del_id]
            elif management_scope == "Entire Current Page":
                target_ids = df_page['Serial Number'].tolist()
                st.info(f"Targeting all {len(target_ids)} records currently visible on this page.")
            elif management_scope == "Full Search Results Match":
                st.warning(f"Targeting ALL {total_records} records matching current search filters and criteria.")
                # We don't need IDs for this, backend handles search
                target_ids = "SEARCH_MATCH"
            else:
                st.write("Ready for management operations.")

        with del_c3:
            st.markdown("<br>", unsafe_allow_html=True)
            # Only enable button if a scope is selected and it's not the placeholder
            can_delete = management_scope != "Select Action..." and (target_ids or target_ids == "SEARCH_MATCH")
            
            if st.button("🗑️ EXECUTE DELETE", type="primary", width='stretch', disabled=not can_delete):
                st.session_state['confirm_management_action'] = {
                    'scope': management_scope,
                    'targets': target_ids
                }
            
        # Confirmation Overlay
        if st.session_state.get('confirm_management_action'):
            action = st.session_state['confirm_management_action']
            st.error(f"⚠️ **CRITICAL ACTION WARNING:** You are about to permanently remove records under the scope: **{action['scope']}**.")
            
            mc1, mc2 = st.columns(2)
            if mc1.button("✅ CONFIRM AND REMOVE", type="primary", width='stretch'):
                # Professional Internal Execution
                if action['targets'] == "SEARCH_MATCH":
                    bulk_delete_predictions(st.session_state['user_id'], search_name=search_name, search_risk=search_risk)
                elif action['targets']:
                    bulk_delete_predictions(st.session_state['user_id'], ids=action['targets'])
                
                st.session_state['confirm_management_action'] = None
                st.success("Selected data has been purged from history successfully.")
                st.rerun()
            if mc2.button("❌ CANCEL OPERATION", width='stretch'):
                st.session_state['confirm_management_action'] = None
                st.rerun()
                
        # Export Data
        col_exp_h1, col_exp_h2 = st.columns(2)
        with col_exp_h1:
            h_csv_data = cached_to_data(df_display, 'csv')
            st.download_button(f"📥 Download Page {st.session_state['hist_page']} (CSV)", h_csv_data, f"patient_history_p{st.session_state['hist_page']}.csv", "text/csv", width='stretch')
        with col_exp_h2:
            h_excel_data = cached_to_data(df_display, 'excel')
            st.download_button(f"📥 Download Page {st.session_state['hist_page']} (Excel)", h_excel_data, f"patient_history_p{st.session_state['hist_page']}.xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", width='stretch')

    with tab_h_charts:
        if total_records > 0:
            # 1. Global View
            st.markdown(f"### 🌏 Global Health Overview (Across {total_records} Records)")
            dist_data = get_risk_distribution(st.session_state['user_id'], search_name, search_risk)
            df_pie = pd.DataFrame(dist_data, columns=['Risk Level', 'Count'])
            h_color_map = {'High': '#ef4444', 'Medium': '#f97316', 'Normal': '#22c55e'}
            
            fig_h_pie = px.pie(df_pie, values='Count', names='Risk Level', color='Risk Level', hole=0.4, color_discrete_map=h_color_map)
            fig_h_pie = apply_common_plotly_layout(fig_h_pie, f"Global Population Risk ({total_records} Patients)")
            st.plotly_chart(fig_h_pie, width='stretch')

            st.markdown("---")
            
            # 2. Synchronized Page View
            # Use 'records' fetched earlier for the current page
            offset = (st.session_state['hist_page'] - 1) * page_size
            curr_start = offset + 1
            curr_end = min(offset + page_size, total_records)
            st.markdown(f"### 🔬 Page Analytics (Comparing Records {curr_start}-{curr_end})")
            
            df_charts = pd.DataFrame(records, columns=['Serial Number', 'Patient Name', 'Age', 'WBC', 'RBC', 'Hemoglobin', 'Platelets', 'Temperature', 'Risk Score', 'Risk Level', 'Date', 'Gender'])
            
            h_data = {'Patient Name': True, 'Age': True, 'Risk Level': True, 'WBC': ':.2f', 'RBC': ':.2f', 'Hemoglobin': ':.2f', 'Platelets': ':.0f', 'Temperature': ':.2f', 'Date': True}
            
            fig_h_scatter = px.scatter(df_charts, x='WBC', y='Age', color='Risk Level', color_discrete_map=h_color_map, hover_data=h_data)
            fig_h_scatter = apply_common_plotly_layout(fig_h_scatter, f"Clinical Trend: Page {st.session_state.hist_page} ({len(df_charts)} Patients)")
            st.plotly_chart(fig_h_scatter, width='stretch')
            st.caption(f"💡 This graph shows patients from the current page of your log. Use the page buttons in 'Data Records' to browse more.")
        else:
            st.info("No historical data available for visualization matching your filters.")

if __name__ == "__main__":
    main()
