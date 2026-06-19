import sqlite3
import hashlib
import os
from datetime import datetime

# =====================================================================
# 1. DATABASE INIT & SCHEMAS
# =====================================================================

def init_db():
    """Sets up our tables. Standard SQLite stuff, but forcing foreign keys."""
    conn = sqlite3.connect('hospital.db')
    db = conn.cursor()
    
    # SQLite drops foreign key enforcement by default. Need this line every time.
    db.execute("PRAGMA foreign_keys = ON;")

    # RBAC Core User Table
    db.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            salt TEXT NOT NULL,
            role TEXT CHECK(role IN ('Admin', 'Doctor', 'Patient')) NOT NULL
        )
    ''')

    # Medical Profiles
    db.execute('''
        CREATE TABLE IF NOT EXISTS doctors (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER UNIQUE,
            name TEXT NOT NULL,
            specialty TEXT NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        )
    ''')

    db.execute('''
        CREATE TABLE IF NOT EXISTS patients (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER UNIQUE,
            name TEXT NOT NULL,
            dob DATE NOT NULL,
            medical_history TEXT,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        )
    ''')

    # The Scheduling Layer
    db.execute('''
        CREATE TABLE IF NOT EXISTS appointments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            doctor_id INTEGER,
            patient_id INTEGER,
            app_date DATE NOT NULL,
            app_time TEXT NOT NULL,
            FOREIGN KEY (doctor_id) REFERENCES doctors(id),
            FOREIGN KEY (patient_id) REFERENCES patients(id),
            
            -- This unique constraint is what prevents double-booking a doctor
            UNIQUE(doctor_id, app_date, app_time) 
        )
    ''')

    conn.commit()
    return conn


# =====================================================================
# 2. SECURITY & AUTH WORKFLOWS
# =====================================================================

def generate_hash(password):
    """Basic salting and hashing using standard library tools."""
    salt = os.urandom(16).hex()
    hashed = hashlib.sha256((password + salt).encode('utf-8')).hexdigest()
    return hashed, salt

def check_password(stored_hash, salt, entered_password):
    """Compares incoming plain text with the database record."""
    check_hash = hashlib.sha256((entered_password + salt).encode('utf-8')).hexdigest()
    return check_hash == stored_hash

def register_new_account(conn, username, password, role, fullname, extra_data=""):
    """Creates a user record and links it to a role profile automatically."""
    db = conn.cursor()
    pwd_hash, salt = generate_hash(password)
    
    try:
        db.execute('''
            INSERT INTO users (username, password_hash, salt, role) 
            VALUES (?, ?, ?, ?)
        ''', (username, pwd_hash, salt, role))
        user_uuid = db.lastrowid

        if role == 'Doctor':
            db.execute('INSERT INTO doctors (user_id, name, specialty) VALUES (?, ?, ?)', 
                       (user_uuid, fullname, extra_data))
        elif role == 'Patient':
            db.execute('INSERT INTO patients (user_id, name, dob, medical_history) VALUES (?, ?, ?, ?)', 
                       (user_uuid, fullname, extra_data, "No pre-existing conditions recorded."))
        
        conn.commit()
        print(f"[SUCCESS] Added {username} as a {role}.")
    except sqlite3.IntegrityError:
        print("[ERROR] That username is already taken. Try another one.")


def seed_database_defaults(conn):
    """Populates fallback data so the dashboard doesn't boot up empty."""
    db = conn.cursor()
    db.execute("SELECT COUNT(*) FROM users")
    if db.fetchone()[0] == 0:
        # Generate default system root admin
        pwd_hash, salt = generate_hash("admin123")
        db.execute("INSERT INTO users (username, password_hash, salt, role) VALUES ('admin', ?, ?, 'Admin')", (pwd_hash, salt))
        
        # Add basic test staff/clients
        register_new_account(conn, "dr_house", "doc123", "Doctor", "Dr. Gregory House", "Diagnostics")
        register_new_account(conn, "john_doe", "patient123", "Patient", "John Doe", "1990-05-12")
        conn.commit()


# =====================================================================
# 3. INTERACTION LOGIC & SYSTEM HOOKS
# =====================================================================

def schedule_appointment(conn, doc_id, patient_id, date_str, time_str):
    """Tries to insert an appointment. Rejects automatically if doctor is busy."""
    db = conn.cursor()
    try:
        db.execute('''
            INSERT INTO appointments (doctor_id, patient_id, app_date, app_time)
            VALUES (?, ?, ?, ?)
        ''', (doc_id, patient_id, date_str, time_str))
        conn.commit()
        print("✅ Appointment successfully confirmed!")
    except sqlite3.IntegrityError:
        print("❌ Scheduling Conflict: This doctor is already booked at that specific date and time.")


def get_doctor_schedule(conn, user_id):
    """Fetches upcoming assignments for the logged-in doctor."""
    db = conn.cursor()
    db.execute('''
        SELECT p.name, a.app_date, a.app_time, p.medical_history 
        FROM appointments a
        JOIN patients p ON a.patient_id = p.id
        JOIN doctors d ON a.doctor_id = d.id
        WHERE d.user_id = ?
    ''', (user_id,))
    rows = db.fetchall()
    
    print("\n--- YOUR SCHEDULED APPOINTMENTS ---")
    if not rows:
        print("No patient appointments found.")
    for row in rows:
        print(f"Patient: {row[0]} | Date: {row[1]} @ {row[2]} | Notes: {row[3]}")


def get_patient_schedule(conn, user_id):
    """Limits view queries to the logged-in user's data only."""
    db = conn.cursor()
    db.execute('''
        SELECT d.name, a.app_date, a.app_time 
        FROM appointments a
        JOIN doctors d ON a.doctor_id = d.id
        JOIN patients p ON a.patient_id = p.id
        WHERE p.user_id = ?
    ''', (user_id,))
    rows = db.fetchall()
    
    print("\n--- YOUR UPCOMING APPOINTMENTS ---")
    if not rows:
        print("You have no scheduled appointments.")
    for row in rows:
        print(f"Doctor: {row[0]} | Date: {row[1]} @ {row[2]}")


def run_system_audit(conn):
    """Admin tool to view system state metrics."""
    db = conn.cursor()
    print("\n--- SYSTEM ACCESS AUDIT LOG ---")
    db.execute("SELECT id, username, role FROM users")
    for row in db.fetchall():
        print(f"User ID: {row[0]} | Username: {row[1]} | Access Role: {row[2]}")


# =====================================================================
# 4. MAIN PROGRAM RUNTIME
# =====================================================================

if __name__ == "__main__":
    connection = init_db()
    seed_database_defaults(connection)
    
    session_user = None
    
    while True:
        # Login loop wrapper
        if not session_user:
            print("\n===============================")
            print("  HOSPITAL PORTAL SYSTEM LOGIN ")
            print("===============================")
            username_input = input("Username: ").strip()
            password_input = input("Password: ").strip()
            
            db_cursor = connection.cursor()
            db_cursor.execute("SELECT id, password_hash, salt, role FROM users WHERE username = ?", (username_input,))
            user_record = db_cursor.fetchone()
            
            if user_record and check_password(user_record[1], user_record[2], password_input):
                session_user = {"id": user_record[0], "username": username_input, "role": user_record[3]}
                print(f"\nWelcome back, {username_input}! [{user_record[3]} Session]")
            else:
                print("❌ Authentication failed. Try again.")
                continue

        # Authenticated UI Layout
        print(f"\n[{session_user['role']} Panel]")
        
        if session_user['role'] == 'Admin':
            print("1. View Active System Users\n2. Register New User\n3. Logout")
            action = input("Select operation: ")
            
            if action == '1': 
                run_system_audit(connection)
            elif action == '2':
                u = input("Username: ")
                p = input("Password: ")
                r = input("Role (Doctor/Patient): ")
                n = input("Full Name: ")
                ex = input("Specialty (if Doc) OR DOB YYYY-MM-DD (if Patient): ")
                register_new_account(connection, u, p, r, n, ex)
            elif action == '3': 
                session_user = None

        elif session_user['role'] == 'Doctor':
            print("1. View My Patient Appointments\n2. Book an Appointment\n3. Logout")
            action = input("Select operation: ")
            
            if action == '1': 
                get_doctor_schedule(connection, session_user['id'])
            elif action == '2':
                # Map user_id back down to core doctor relational table index
                doc_idx = connection.cursor().execute("SELECT id FROM doctors WHERE user_id=?", (session_user['id'],)).fetchone()[0]
                pat_id = int(input("Target Patient Database ID: "))
                d_str = input("Date (YYYY-MM-DD): ")
                t_str = input("Time Slot (e.g., 11:30 AM): ")
                schedule_appointment(connection, doc_idx, pat_id, d_str, t_str)
            elif action == '3': 
                session_user = None

        elif session_user['role'] == 'Patient':
            print("1. View My Personal Appointments\n2. Logout")
            action = input("Select operation: ")
            
            if action == '1': 
                get_patient_schedule(connection, session_user['id'])
            elif action == '2': 
                session_user = None