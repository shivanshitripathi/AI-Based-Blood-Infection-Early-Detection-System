# 🩸 AI-Based Blood Infection Early Detection System (NexData AI)

## 📋 Project Overview
NexData AI is a high-performance, clinical-grade diagnostic support tool designed for the early detection of blood infections and sepsis. By leveraging machine learning (XGBoost) and standard hematological parameters, the system provides real-time risk stratification for patients, allowing medical professionals to intervene hours before critical deterioration.

---

## 🛠️ Key Features (A to Z)

### 📊 Advanced Analytics
The system generates interactive Plotly visualizations for patient blood parameters (WBC, RBC, Platelets, etc.) and provides a risk distribution summary across the entire dataset.

### 🔐 Authentication System
Secure portal access with a local SQLite-backed login and signup system to protect sensitive patient records.

### 📂 Batch Data Ingestion
Support for high-volume analysis via CSV and Excel file uploads. The system automatically maps columns and handles missing data via medical-grade imputation.

### 🏥 Clinical Insights Engine
Automated generation of medical recommendations based on clinical SIRS criteria and hematological patterns (e.g., Anemia, Thrombocytopenia, Sepsis risks).

### ⚙️ Gender Correction Tool
An integrated sidebar tool that allows clinicians to manually fix or update patient gender records using the Name-Gender Cache system.

### 📋 History & Logs
A robust record management system with pagination and multi-page navigation. It supports data persistence across sessions.

### ✍️ Manual Patient Check
A dedicated interface for typing in single patient vitals for instant, on-the-spot diagnostic checks.

### 🔬 Multi-Model ML Architecture
Utilizes **XGBoost** as the primary engine, but includes Random Forest and Logistic Regression as alternative evaluators, reaching high clinical accuracy.

### 🩺 PDF Report Generation
Downloadable, professional diagnostic reports containing patient information, risk scores, and clinical strategies.

---

## 🏗️ Technical Architecture

### **Core Frameworks**
*   **Frontend/UI:** Streamlit (Custom CSS-injected for premium dark-mode aesthetics).
*   **Machine Learning:** Scikit-Learn (Preprocessing), XGBoost (Primary Model Architecture).
*   **Database:** SQLite3 (Local, secure persistence).
*   **PDF Generation:** FPDF Engine.

### **Medical Indicators Tracked**
1.  **WBC (White Blood Cells):** For infection detection.
2.  **RBC (Red Blood Cells):** For oxygen capacity analysis.
3.  **Hemoglobin:** For anemia screening.
4.  **Platelets:** For clotting and viral fever patterns.
5.  **Temperature:** Essential vital for SIRS/Sepsis screening.
6.  **Age:** Demographic risk weighting.

---

## 📂 File Structure Overview

*   `app.py`: The central application engine and UI layout.
*   `auth.py`: Handles secure database operations, hashing, and user sessions.
*   `data_processing.py`: The scientific core for preprocessing, medical insights, and model inference.
*   `pdf_generator.py`: Logic for generating professional medical reports.
*   `model_training.py`: Script used to train models from local datasets.
*   `models/`: Directory containing serialized `.pkl` files (Scaler, XGBoost, RF, etc.).
*   `requirements.txt`: List of all necessary Python dependencies.

---

## 🚀 Deployment & Installation

1.  **Clone the project** into a local directory.
2.  **Install dependencies**:
    ```bash
    pip install -r requirements.txt
    ```
3.  **Run the application**:
    ```bash
    streamlit run app.py
    ```

---

*Note: This system is a diagnostic support tool and should be used alongside professional medical judgment.*
