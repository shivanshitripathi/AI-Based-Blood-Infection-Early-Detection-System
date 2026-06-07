import pandas as pd
import numpy as np
import os
import joblib
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import StandardScaler
from sklearn.linear_model import LogisticRegression
from sklearn.ensemble import RandomForestClassifier
try:
    from xgboost import XGBClassifier
except ImportError:
    print("XGBoost not installed. Please install it using 'pip install xgboost'")
    exit(1)
from sklearn.metrics import accuracy_score, precision_score, recall_score, f1_score, confusion_matrix

def train_models():
    # Load Data
    csv_path = "blood_infection_dataset.csv"
    if not os.path.exists(csv_path):
        print(f"Dataset {csv_path} not found. Please run data_generation.py first.")
        return
        
    df = pd.read_csv(csv_path)
    
    # Handle missing values (if any)
    df = df.dropna()
    
    # Split features and target
    X = df.drop(columns=['Infection_Label'])
    y = df['Infection_Label']
    
    # Train/Test Split (80/20)
    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42, stratify=y)
    
    # Normalize/Scale Features
    scaler = StandardScaler()
    X_train_scaled = scaler.fit_transform(X_train)
    X_test_scaled = scaler.transform(X_test)
    
    # Ensure models directory exists
    os.makedirs('models', exist_ok=True)
    joblib.dump(scaler, os.path.join('models', 'scaler.pkl'))
    
    # Train Models
    print("Training Logistic Regression...")
    lr = LogisticRegression(random_state=42, max_iter=1000)
    lr.fit(X_train_scaled, y_train)
    joblib.dump(lr, os.path.join('models', 'lr_model.pkl'))
    
    print("Training Random Forest...")
    rf = RandomForestClassifier(n_estimators=100, random_state=42)
    rf.fit(X_train_scaled, y_train)
    joblib.dump(rf, os.path.join('models', 'rf_model.pkl'))
    
    print("Training XGBoost (Main Model)...")
    xgb = XGBClassifier(use_label_encoder=False, eval_metric='logloss', random_state=42)
    xgb.fit(X_train_scaled, y_train)
    joblib.dump(xgb, os.path.join('models', 'xgb_model.pkl'))
    
    # Evaluate Models
    print("\n--- Model Evaluation ---")
    models = {
        'Logistic Regression': lr,
        'Random Forest': rf,
        'XGBoost': xgb
    }
    
    for name, model in models.items():
        y_pred = model.predict(X_test_scaled)
        
        acc = accuracy_score(y_test, y_pred)
        prec = precision_score(y_test, y_pred, zero_division=0)
        rec = recall_score(y_test, y_pred, zero_division=0)
        f1 = f1_score(y_test, y_pred, zero_division=0)
        cm = confusion_matrix(y_test, y_pred)
        
        print(f"\n[{name}]")
        print(f"Accuracy:  {acc:.4f}")
        print(f"Precision: {prec:.4f}")
        print(f"Recall:    {rec:.4f}")
        print(f"F1-score:  {f1:.4f}")
        print("Confusion Matrix:")
        print(cm)
        
if __name__ == "__main__":
    train_models()
