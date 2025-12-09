# app.py
# Jalankan: streamlit run app.py

import streamlit as st
import pandas as pd
import sqlite3
from sqlite3 import Connection
import plotly.express as px
from datetime import datetime
import io

# ----------------- HELPERS -----------------
DB_PATH = "akademik.db"

def get_connection() -> Connection:
    return sqlite3.connect(DB_PATH, check_same_thread=False)

def init_db():
    conn = get_connection()
    cur = conn.cursor()
    # users table (simple demo auth)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE,
        password TEXT,
        full_name TEXT
    )
    """)
    # grades table
    cur.execute("""
    CREATE TABLE IF NOT EXISTS grades (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        semester INTEGER,
        course_code TEXT,
        course_name TEXT,
        sks INTEGER,
        grade REAL,
        created_at TEXT
    )
    """)
    # attendance table
    cur.execute("""
    CREATE TABLE IF NOT EXISTS attendance (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        course_code TEXT,
        course_name TEXT,
        percent REAL,
        updated_at TEXT
    )
    """)

    # insert demo user if not exists
    cur.execute("SELECT COUNT(*) FROM users")
    if cur.fetchone()[0] == 0:
        cur.execute("INSERT INTO users (username, password, full_name) VALUES (?,?,?)",
                    ("demo", "demo123", "Mahasiswa Demo"))
    conn.commit()
    conn.close()

# ----------------- AUTH -----------------

def authenticate(username, password):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT id, full_name FROM users WHERE username=? AND password=?", (username, password))
    row = cur.fetchone()
    conn.close()
    if row:
        return {"id": row[0], "full_name": row[1]}
    return None

# ----------------- CRUD & IO -----------------

def insert_grades(df: pd.DataFrame):
    conn = get_connection()
    df = df.copy()
    df['created_at'] = datetime.now().isoformat()
    df.to_sql('grades', conn, if_exists='append', index=False)
    conn.close()

def get_grades():
    conn = get_connection()
    df = pd.read_sql_query('SELECT * FROM grades ORDER BY semester, course_code', conn)
    conn.close()
    return df

def get_attendance():
    conn = get_connection()
    df = pd.read_sql_query('SELECT * FROM attendance ORDER BY course_code', conn)
    conn.close()
    return df

def export_excel(df: pd.DataFrame, name: str):
    towrite = io.BytesIO()
    df.to_excel(towrite, index=False, engine='openpyxl')
    towrite.seek(0)
    return towrite

# ----------------- APP -----------------
init_db()

st.set_page_config(page_title="Dashboard Akademik Mahasiswa", layout='wide')

st.sidebar.title("🔐 Login")
if 'user' not in st.session_state:
    st.session_state['user'] = None

if st.session_state['user'] is None:
    username = st.sidebar.text_input('Username')
    password = st.sidebar.text_input('Password', type='password')
    if st.sidebar.button('Login'):
        user = authenticate(username, password)
        if user:
            st.session_state['user'] = user
            st.success(f"Selamat datang, {user['full_name']}")
        else:
            st.sidebar.error('Username / password salah (demo: demo / demo123)')
    st.sidebar.markdown("---")
    st.sidebar.markdown("**Belum punya akun?** kontak admin untuk pembuatan akun demo.")
    st.stop()

# If logged in
user = st.session_state['user']

st.sidebar.title("Menu")
menu = st.sidebar.radio("Pilih Menu", ["Dashboard", "Input Data", "Nilai & IPK", "Kehadiran", "Notifikasi & Export", "Admin"])

# ---------------- Dashboard ----------------
if menu == 'Dashboard':
    st.header("📊 Dashboard Akademik — Ringkasan")

    grades = get_grades()
    attendance = get_attendance()

    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric('Jumlah Mata Kuliah', int(len(grades['course_code'].unique())) if not grades.empty else 0)
    with col2:
        avg_ip = None
        if not grades.empty:
            # Hitung IP per semester lalu rata-rata (IPK)
            gp = grades.copy()
            gp['weighted'] = gp['grade'] * gp['sks']
            ip_per_sem = gp.groupby('semester').agg({'weighted':'sum','sks':'sum'})
            ip_per_sem['ip'] = ip_per_sem['weighted']/ip_per_sem['sks']
            ipk = (ip_per_sem['ip'] * ip_per_sem['sks']).sum() / ip_per_sem['sks'].sum()
            avg_ip = round(ipk,2)
            st.metric('IPK (estimasi)', f"{avg_ip}")
        else:
            st.metric('IPK (estimasi)', "-")
    with col3:
        avg_att = round(attendance['percent'].mean(),2) if not attendance.empty else 0
        st.metric('Rata-rata Kehadiran (%)', f"{avg_att}")

    st.subheader('IP per Semester')
    if not grades.empty:
        gp['weighted'] = gp['grade'] * gp['sks']
        ip_sem = gp.groupby('semester').agg({'weighted':'sum','sks':'sum'})
        ip_sem['ip'] = ip_sem['weighted']/ip_sem['sks']
        ip_sem = ip_sem.reset_index()
        fig = px.line(ip_sem, x='semester', y='ip', markers=True, title='Perkembangan IP per Semester')
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info('Belum ada data nilai. Silakan upload di menu Input Data.')

# ---------------- Input Data ----------------
elif menu == 'Input Data':
    st.header('📥 Input / Upload Data')
    st.subheader('Upload file nilai (CSV)')
    st.markdown('Format CSV: semester,course_code,course_name,sks,grade')
    uploaded = st.file_uploader('Pilih CSV nilai', type=['csv'])
    if uploaded:
        df = pd.read_csv(uploaded)
        st.dataframe(df.head())
        if st.button('Simpan ke database'):
            insert_grades(df)
            st.success('Data nilai berhasil disimpan ke database.')

    st.subheader('Upload file kehadiran (CSV)')
    st.markdown('Format CSV: course_code,course_name,percent')
    uploaded2 = st.file_uploader('Pilih CSV kehadiran', type=['csv'], key='att')
    if uploaded2:
        df2 = pd.read_csv(uploaded2)
        st.dataframe(df2.head())
        if st.button('Simpan ke database (kehadiran)'):
            conn = get_connection()
            df2.to_sql('attendance', conn, if_exists='replace', index=False)
            conn.close()
            st.success('Data kehadiran tersimpan.')

# ---------------- Nilai & IPK ----------------
elif menu == 'Nilai & IPK':
    st.header('🎯 Nilai & Penghitungan IP/IPK')
    grades = get_grades()
    st.dataframe(grades)

    if not grades.empty:
        grades['weighted'] = grades['grade'] * grades['sks']
        ip_sem = grades.groupby('semester').agg({'weighted':'sum','sks':'sum'})
        ip_sem['ip'] = ip_sem['weighted']/ip_sem['sks']
        ip_sem = ip_sem.reset_index()
        st.subheader('IP per Semester')
        st.dataframe(ip_sem[['semester','ip']])
        fig = px.bar(ip_sem, x='semester', y='ip', title='IP per Semester')
        st.plotly_chart(fig, use_container_width=True)

        # Analisis kenaikan/penurunan
        ip_sem['change'] = ip_sem['ip'].diff()
        st.subheader('Analisis Kenaikan / Penurunan')
        st.dataframe(ip_sem[['semester','ip','change']])

        # Export
        towrite = export_excel(grades, 'grades.xlsx')
        st.download_button(label='Download data nilai (.xlsx)', data=towrite, file_name='grades.xlsx')

# ---------------- Kehadiran ----------------
elif menu == 'Kehadiran':
    st.header('📅 Kehadiran Mata Kuliah')
    att = get_attendance()
    if not att.empty:
        st.dataframe(att)
        fig = px.bar(att, x='course_name', y='percent', title='Kehadiran per Mata Kuliah')
        st.plotly_chart(fig, use_container_width=True)
        towrite = export_excel(att, 'attendance.xlsx')
        st.download_button('Download Kehadiran (.xlsx)', towrite, file_name='attendance.xlsx')
    else:
        st.info('Belum ada data kehadiran.')

# ---------------- Notifikasi & Export ----------------
elif menu == 'Notifikasi & Export':
    st.header('🔔 Notifikasi & Pengingat')
    st.info('• Jangan lupa submit tugas tepat waktu.')
    st.info('• Cek kehadiran dan nilai setiap minggu.')

    st.header('📤 Export Semua Data')
    grades = get_grades()
    att = get_attendance()
    if not grades.empty:
        gfile = export_excel(grades, 'grades_all.xlsx')
        st.download_button('Download Semua Nilai', gfile, file_name='grades_all.xlsx')
    if not att.empty:
        afile = export_excel(att, 'attendance_all.xlsx')
        st.download_button('Download Semua Kehadiran', afile, file_name='attendance_all.xlsx')

# ---------------- Admin ----------------
elif menu == 'Admin':
    st.header('⚙️ Admin (Demo)')
    st.subheader('Reset Database (hati-hati)')
    if st.button('Reset semua data (grades & attendance) -- DEMO'):
        conn = get_connection()
        cur = conn.cursor()
        cur.execute('DELETE FROM grades')
        cur.execute('DELETE FROM attendance')
        conn.commit()
        conn.close()
        st.success('Data dihapus.')
