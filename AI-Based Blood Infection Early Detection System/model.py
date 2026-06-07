import pandas as pd
import numpy as np
import os
import joblib
from sklearn.model_selection import train_test_split
from sklearn.ensemble import RandomForestClassifier
from sklearn.impute import SimpleImputer
from sklearn.preprocessing import StandardScaler
from xgboost import XGBClassifier

# Use a subset of features that are mostly related to CBC and basic vitals
SELECTED_FEATURES = ['Temp', 'HR', 'O2Sat', 'WBC', 'Platelets', 'Hgb', 'Hct', 'Age', 'Gender']
TARGET = 'SepsisLabel'

def train_and_save_models(data_path='data/sepsis.csv', models_dir='models'):
    print(f"Loading data from {data_path}...")
    df = pd.read_csv(data_path)
    
    # Filter only needed columns + target
    df = df[SELECTED_FEATURES + [TARGET]]
    
    # Drop rows where target is missing
    df = df.dropna(subset=[TARGET])
    
    X = df[SELECTED_FEATURES]
    y = df[TARGET]
    
    # Impute missing values with median
    print("Imputing missing values...")
    imputer = SimpleImputer(strategy='median')
    X_imputed = imputer.fit_transform(X)
    
    # Scale features
    print("Scaling features...")
    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X_imputed)
    
    # Train-test split
    X_train, X_test, y_train, y_test = train_test_split(X_scaled, y, test_size=0.2, random_state=42, stratify=y)
    
    # Train Random Forest
    print("Training Random Forest...")
    rf_model = RandomForestClassifier(n_estimators=100, max_depth=10, random_state=42, class_weight='balanced')
    rf_model.fit(X_train, y_train)
    rf_acc = rf_model.score(X_test, y_test)
    print(f"Random Forest Accuracy: {rf_acc:.4f}")
    
    # Train XGBoost
    print("Training XGBoost...")
    # XGBoost handles scale_pos_weight for imbalanced classes
    scale_pos_weight = sum(y_train == 0) / sum(y_train == 1)
    xgb_model = XGBClassifier(
        n_estimators=100, 
        max_depth=6, 
        learning_rate=0.1, 
        scale_pos_weight=scale_pos_weight, 
        random_state=42,
        use_label_encoder=False,
        eval_metric='logloss'
    )
    xgb_model.fit(X_train, y_train)
    xgb_acc = xgb_model.score(X_test, y_test)
    print(f"XGBoost Accuracy: {xgb_acc:.4f}")
    
    # Save models and preprocessors
    os.makedirs(models_dir, exist_ok=True)
    joblib.dump(imputer, os.path.join(models_dir, 'imputer.pkl'))
    joblib.dump(scaler, os.path.join(models_dir, 'scaler.pkl'))
    joblib.dump(rf_model, os.path.join(models_dir, 'rf_model.pkl'))
    joblib.dump(xgb_model, os.path.join(models_dir, 'xgb_model.pkl'))
    print(f"Models saved to {models_dir} successfully.")

if __name__ == "__main__":
    train_and_save_models()
