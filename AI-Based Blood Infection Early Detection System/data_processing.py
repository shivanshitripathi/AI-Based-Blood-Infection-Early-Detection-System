import pandas as pd
import numpy as np
import joblib
import os
import streamlit as st

SELECTED_FEATURES = ['WBC', 'RBC', 'Hemoglobin', 'Platelets', 'Temperature', 'Age']

# Default values for missing parameters
DEFAULT_VALUES = {
    'WBC': 7500.0,
    'RBC': 4.8,
    'Hemoglobin': 14.5,
    'Platelets': 250000.0,
    'Temperature': 98.6,
    'Age': 45.0
}

@st.cache_resource
def load_scaler():
    return joblib.load(os.path.join('models', 'scaler.pkl'))

@st.cache_resource
def load_model(model_type='XGBoost'):
    model_file = 'xgb_model.pkl' if model_type == 'XGBoost' else 'rf_model.pkl'
    return joblib.load(os.path.join('models', model_file))

def validate_and_preprocess(df):
    """
    Validates the uploaded dataframe. If required columns are missing, 
    they are automatically added with standard default values.
    Applies imputation and scaling based on loaded objects.
    Returns: DataFrame with required features ready for prediction, processed DataFrame (for UI), or error string.
    """
    # Auto-add missing columns with defaults instead of failing
    for col in SELECTED_FEATURES:
        if col not in df.columns:
            df[col] = DEFAULT_VALUES[col]
            
    data_subset = df[SELECTED_FEATURES].copy()
    
    # Convert all columns to numeric, setting errors to NaN
    for col in SELECTED_FEATURES:
        data_subset[col] = pd.to_numeric(data_subset[col], errors='coerce')
        
    try:
        # We don't have an imputer explicitly trained in model_training.py because df.dropna() was used.
        # But for robustness in prod, if there are NaNs, fill with defaults.
        for col in SELECTED_FEATURES:
            data_subset[col] = data_subset[col].fillna(DEFAULT_VALUES[col])

        scaler = load_scaler()
    except Exception:
        return None, None, "Model scaler not found or corrupted. Admin needs to train models first."
        
    X_scaled = scaler.transform(data_subset)
    
    # Return the processed scaled array AND the dataframe that now has all columns
    return X_scaled, df, None

def get_predictions(X_processed, df_raw, model_type='XGBoost'):
    """
    Returns prediction probabilities and risk levels based on clinical outliers and AI score.
    """
    try:
        model = load_model(model_type)
    except Exception:
        return None, None, f"{model_type} model not found or corrupted."
        
    probs = model.predict_proba(X_processed)[:, 1] # Probability of class 1
    
    risk_scores = np.round(probs * 100, 2)
    risk_levels = []
    
    for i, score in enumerate(risk_scores):
        row = df_raw.iloc[i]
        
        # Clinical Outlier Check
        wbc = float(row.get('WBC', 7500))
        plt = float(row.get('Platelets', 250000))
        temp = float(row.get('Temperature', 98.6))
        hgb = float(row.get('Hemoglobin', 14.5))
        rbc = float(row.get('RBC', 4.8))
        
        is_outlier = (
            wbc > 11000 or wbc < 4000 or
            plt > 450000 or plt < 150000 or
            temp > 99.0 or temp < 97.0 or
            hgb > 17.5 or hgb < 12.0 or
            rbc > 6.2 or rbc < 4.2
        )
        
        # 3-Tier System: High, Medium, Normal
        # Outliers significantly increase risk
        if score >= 60 or (is_outlier and score >= 35):
            risk_levels.append('High')
        elif score >= 30 or is_outlier:
            risk_levels.append('Medium')
        else:
            risk_levels.append('Normal')
            
    return risk_scores, risk_levels, None

def generate_insights(row):
    """
    Advanced Scientific Diagnostic Core.
    Implements complex medical correlations (Sepsis, Pancytopenia, Leukemia suspicion, etc.) 
    based on standard clinical hematology and vital sign references.
    """
    conditions = []
    
    # 1. Parameter Extraction & Normalization
    try:
        wbc = float(row.get('WBC', 7500))
        plt = float(row.get('Platelets', 250000))
        temp = float(row.get('Temperature', 98.6))
        hgb = float(row.get('Hemoglobin', 14.5))
        rbc = float(row.get('RBC', 4.8))
        age = float(row.get('Age', 45))
    except (ValueError, TypeError):
        return "⚠️ **Data Integrity Alert:** Critical blood markers contain non-numeric or corrupted values. Scientific analysis aborted."

    # 2. SEPSIS & SEPTIC SHOCK (SIRS CRITERIA)
    is_fever = (temp > 100.4 or temp < 96.8)
    is_abnormal_wbc = (wbc > 12000 or wbc < 4000)
    if is_fever and is_abnormal_wbc:
        severity = "Critical: Septic Shock Risk" if (temp > 103 or temp < 95) else "Sepsis (SIRS)"
        conditions.append(f"🚨 **{severity}:** Concurrent core temperature instability and WBC anomaly is a red-flag for systemic bacterial invasion. Requires STAT blood cultures.")

    # 3. PANCYTOPENIA (Triple Low - Aplastic Anemia / Bone Marrow Failure)
    if wbc < 3500 and plt < 100000 and hgb < 11:
        conditions.append("🔬 **Pancytopenia Pattern:** Simultaneous suppression of all three blood cell lines. Suggests potential bone marrow failure, aplastic anemia, or severe nutritional deficiency. Hematology consult required.")

    # 4. LEUKEMIA SUSPICION / EXTREME LEUKOCYTOSIS
    if wbc > 50000:
        conditions.append("🚨 **Hyperleukocytosis:** Dangerously high WBC (>50k). High suspicion of Acute Leukemia or myeloproliferative disorder. Immediate peripheral blood smear indicated.")
    elif wbc > 30000 and not is_fever:
        conditions.append("🔬 **Leukemoid Reaction:** Severe WBC elevation without fever. May indicate chronic myeloid leukemia (CML) or severe tissue necrosis.")

    # 5. VIRAL HEMORRHAGIC FEVER (DENGUE / MALARIA PROTOCOL)
    if temp > 101 and plt < 90000:
        malaria_risk = " (Check for Malaria)" if rbc < 3.8 else ""
        conditions.append(f"🦟 **Viral/Parasitic Pattern:** Acute febrile illness with Thrombocytopenia{malaria_risk}. High correlation with Dengue or Malaria endemic patterns.")

    # 6. ANEMIA DIFFERENTIALS
    if (hgb < 12 and age < 60) or hgb < 11:
        anemia_reason = "Iron Deficiency" if rbc < 4.0 else "Macrocytic Anemia"
        conditions.append(f"🩸 **Clinical Anemia:** Low Hemoglobin detected. {anemia_reason} pattern suspected. Check iron, B12, and folate levels.")

    # 7. POLYCYTHEMIA (Blood Viscosity Risk)
    if rbc > 6.2 or hgb > 17.5:
        conditions.append("🧠 **Polycythemia Vera:** Elevated RBC/Hgb suggests thick blood hyperviscosity. Increased risk of stroke or thrombosis. Therapeutic phlebotomy may be indicated.")

    # 8. THROMBOCYTOSIS (Clotting Risk)
    if plt > 450000:
        conditions.append("🩸 **Thrombocytosis:** High platelet count. Risk of spontaneous clotting in microvasculature. Monitor for neurological or cardiac signs.")

    # 9. PYREXIA (Extreme Hyperthermia)
    if temp > 104.0:
        conditions.append("🔥 **Hyperpyrexia:** Extreme body temperature. High risk of permanent neurological damage or multi-organ failure if not cooled immediately.")

    # FALLBACK: LOCALIZED INFECTION
    if wbc > 11000 and not conditions:
        conditions.append("🦠 **Bacterial Infection:** Simple Leukocytosis. Localized infection likely (e.g., Bronchitis, UTI).")

    if not conditions:
        return "✅ **Baseline Physiology:** Parameters are within standard clinical variance. No specific disease correlations detected."
    
    return "\n\n".join(conditions)


def get_parameter_statuses(row):
    """
    Evaluates individual blood parameters against clinical normal ranges
    and returns their current status (Low, Normal, High).
    """
    statuses = {}
    
    # WBC: 4000 - 11000
    try: wbc = float(row.get('WBC', 0))
    except: wbc = 0.0
    if wbc < 4000: statuses['WBC'] = 'Low'
    elif wbc > 11000: statuses['WBC'] = 'High'
    else: statuses['WBC'] = 'Normal'
        
    # RBC: 4.2 - 6.2 (generalized)
    try: rbc = float(row.get('RBC', 0))
    except: rbc = 0.0
    if rbc < 4.2: statuses['RBC'] = 'Low'
    elif rbc > 6.2: statuses['RBC'] = 'High'
    else: statuses['RBC'] = 'Normal'
        
    # Hemoglobin: 12.0 - 17.5
    try: hgb = float(row.get('Hemoglobin', 0))
    except: hgb = 0.0
    if hgb < 12.0: statuses['Hemoglobin'] = 'Low'
    elif hgb > 17.5: statuses['Hemoglobin'] = 'High'
    else: statuses['Hemoglobin'] = 'Normal'
        
    # Platelets: 150000 - 450000
    try: plt = float(row.get('Platelets', 0))
    except: plt = 0.0
    if plt < 150000: statuses['Platelets'] = 'Low'
    elif plt > 450000: statuses['Platelets'] = 'High'
    else: statuses['Platelets'] = 'Normal'
        
    # Temperature: 97.0 - 99.0
    try: temp = float(row.get('Temperature', 0))
    except: temp = 0.0
    if temp < 97.0: statuses['Temperature'] = 'Low'
    elif temp > 99.0: statuses['Temperature'] = 'High'
    else: statuses['Temperature'] = 'Normal'
        
    return statuses
