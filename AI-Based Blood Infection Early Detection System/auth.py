import sqlite3
import streamlit as st
from datetime import datetime

DB_NAME = "database.db"

@st.cache_resource
def init_db():
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    # Users table
    c.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL
        )
    ''')


    # History table (We recreate it if we need to add columns. Since this is local, we'll try to alter it or recreate if empty)
    try:
        c.execute('''
            CREATE TABLE IF NOT EXISTS history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                patient_name TEXT,
                age REAL,
                wbc REAL,
                rbc REAL,
                hgb REAL,
                platelets REAL,
                temp REAL,
                risk_score REAL,
                risk_level TEXT,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id)
            )
        ''')
        # Check if new columns exist; if not, add them via ALTER TABLE
        c.execute("PRAGMA table_info(history)")
        columns = [col[1] for col in c.fetchall()]
        
        new_columns = {
            'wbc': 'REAL', 'rbc': 'REAL', 'hgb': 'REAL', 
            'platelets': 'REAL', 'temp': 'REAL',
            'gender': 'TEXT'
        }
        for col, dtype in new_columns.items():
            if col not in columns:
                c.execute(f"ALTER TABLE history ADD COLUMN {col} {dtype}")
                
    except Exception as e:
        print(f"Error updating DB: {e}")
        
    conn.commit()
    conn.close()



def create_user(username, password):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    try:
        c.execute('INSERT INTO users (username, password) VALUES (?, ?)', (username, password))
        conn.commit()
        return True, "User created successfully."
    except sqlite3.IntegrityError:
        return False, "Username already exists."
    finally:
        conn.close()

def authenticate_user(username, password):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute('SELECT id, password FROM users WHERE username = ?', (username,))
    record = c.fetchone()
    conn.close()
    
    if record and record[1] == password:
        return True, record[0]
    return False, None


def save_prediction(user_id, patient_name, age, wbc, rbc, hgb, platelets, temp, risk_score, risk_level, timestamp=None, gender='Unknown'):
    local_time = timestamp if timestamp else datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute('''
        INSERT INTO history (user_id, patient_name, age, wbc, rbc, hgb, platelets, temp, risk_score, risk_level, timestamp, gender)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (user_id, patient_name, age, wbc, rbc, hgb, platelets, temp, risk_score, risk_level, local_time, gender))
    new_id = c.lastrowid
    conn.commit()
    conn.close()
    return new_id

def check_duplicate_entry(user_id, patient_name, age, wbc, rbc, hgb, platelets, temp):
    """
    Checks if a record with the exact same name and medical parameters 
    already exists in the history for this user.
    """
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    # Using SQL to check for exact clinical match with tolerance for floating point and case
    c.execute('''
        SELECT id FROM history 
        WHERE user_id = ? 
        AND LOWER(TRIM(patient_name)) = LOWER(TRIM(?))
        AND age = ? 
        AND ABS(wbc - ?) < 0.1 
        AND ABS(rbc - ?) < 0.1 
        AND ABS(hgb - ?) < 0.1 
        AND ABS(platelets - ?) < 0.1 
        AND ABS(temp - ?) < 0.1
    ''', (user_id, patient_name, age, wbc, rbc, hgb, platelets, temp))
    record = c.fetchone()
    conn.close()
    return record is not None

def get_user_history(user_id, limit=None, offset=None):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    query = '''
        SELECT id, patient_name, age, wbc, rbc, hgb, platelets, temp, risk_score, risk_level, timestamp,
               COALESCE(gender, 'Unknown') as gender
        FROM history WHERE user_id = ? ORDER BY id ASC
    '''
    params = [user_id]
    if limit is not None:
        query += " LIMIT ?"
        params.append(limit)
    if offset is not None:
        query += " OFFSET ?"
        params.append(offset)
        
    c.execute(query, params)
    records = c.fetchall()
    conn.close()
    return records

def get_history_count(user_id, search_name=None, search_risk=None):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    query = "SELECT COUNT(*) FROM history WHERE user_id = ?"
    params = [user_id]
    
    if search_name:
        query += " AND patient_name LIKE ?"
        params.append(f"%{search_name}%")
    if search_risk and search_risk != "All":
        query += " AND risk_level = ?"
        params.append(search_risk)
        
    c.execute(query, params)
    count = c.fetchone()[0]
    conn.close()
    return count

def search_history(user_id, search_name=None, search_risk=None, limit=None, offset=None):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    query = '''
        SELECT id, patient_name, age, wbc, rbc, hgb, platelets, temp, risk_score, risk_level, timestamp,
               COALESCE(gender, 'Unknown') as gender
        FROM history WHERE user_id = ?
    '''
    params = [user_id]
    
    if search_name:
        query += " AND patient_name LIKE ?"
        params.append(f"%{search_name}%")
    if search_risk and search_risk != "All":
        query += " AND risk_level = ?"
        params.append(search_risk)
        
    query += " ORDER BY id ASC"
    
    if limit is not None:
        query += " LIMIT ?"
        params.append(limit)
    if offset is not None:
        query += " OFFSET ?"
        params.append(offset)
        
    c.execute(query, params)
    records = c.fetchall()
    conn.close()
    return records

def get_risk_distribution(user_id, search_name=None, search_risk=None):
    """Efficiently aggregates risk levels across the entire dataset via SQL."""
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    query = "SELECT risk_level, COUNT(*) FROM history WHERE user_id = ?"
    params = [user_id]
    
    if search_name:
        query += " AND patient_name LIKE ?"
        params.append(f"%{search_name}%")
    if search_risk and search_risk != "All":
        query += " AND risk_level = ?"
        params.append(search_risk)
        
    query += " GROUP BY risk_level"
    
    c.execute(query, params)
    data = c.fetchall()
    conn.close()
    return data

def delete_prediction(record_id):
    """Deletes a single record by ID."""
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute('DELETE FROM history WHERE id = ?', (record_id,))
    conn.commit()
    conn.close()

def bulk_delete_predictions(user_id, ids=None, search_name=None, search_risk=None):
    """
    Deletes multiple records based on either a list of IDs or search filters.
    """
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    
    if ids and len(ids) > 0:
        # Batch delete by ID
        query = f"DELETE FROM history WHERE user_id = ? AND id IN ({','.join(['?']*len(ids))})"
        c.execute(query, [user_id] + list(ids))
    elif search_name or (search_risk and search_risk != "All"):
        # Delete by search criteria
        query = "DELETE FROM history WHERE user_id = ?"
        params = [user_id]
        if search_name:
            query += " AND patient_name LIKE ?"
            params.append(f"%{search_name}%")
        if search_risk and search_risk != "All":
            query += " AND risk_level = ?"
            params.append(search_risk)
        c.execute(query, params)
    else:
        # Unfiltered full purge requests
        c.execute("DELETE FROM history WHERE user_id = ?", [user_id])
    
    conn.commit()
    conn.close()

def update_prediction_risk(record_id, new_level, new_score):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute('''
        UPDATE history 
        SET risk_level = ?, risk_score = ?
        WHERE id = ?
    ''', (new_level, new_score, record_id))
    conn.commit()
    conn.close()

def update_prediction_gender(record_id, new_gender):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute('''
        UPDATE history 
        SET gender = ?
        WHERE id = ?
    ''', (new_gender, record_id))
    conn.commit()
    conn.close()

def bulk_update_gender_by_name(user_id, patient_name, new_gender):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute('''
        UPDATE history 
        SET gender = ?
        WHERE user_id = ? AND LOWER(TRIM(patient_name)) = LOWER(TRIM(?))
    ''', (new_gender, user_id, patient_name))
    conn.commit()
    conn.close()

def get_next_serial_number():
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute('SELECT MAX(id) FROM history')
    max_id = c.fetchone()[0]
    conn.close()
    return (max_id or 0) + 1
