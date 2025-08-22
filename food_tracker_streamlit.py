# food_tracker_streamlit.py
# ---------------------------
# Food Tracker App with Fiber Tracking
# Tech: Python + Streamlit + SQLite
# Features:
# - Add foods (per 100g, per serving, etc.)
# - Log what you ate each day
# - Auto-calculates totals (protein, carbs, fat, fiber, calories)
# - Daily summary and charts
# ---------------------------

import streamlit as st
import sqlite3
import pandas as pd
import datetime
import matplotlib.pyplot as plt

DB_NAME = "food_tracker.db"

# ---------------------------
# DB Setup
# ---------------------------
def init_db():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    
    # Create foods table (with fiber)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS foods (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT UNIQUE,
        unit TEXT,
        protein REAL,
        carbs REAL,
        fat REAL,
        fiber REAL DEFAULT 0,
        calories REAL
    )
    """)
    
    # Ensure fiber column exists (for old DBs)
    try:
        cursor.execute("ALTER TABLE foods ADD COLUMN fiber REAL DEFAULT 0")
    except sqlite3.OperationalError:
        pass

    # Create log table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS log (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        date TEXT,
        food_id INTEGER,
        quantity REAL,
        FOREIGN KEY(food_id) REFERENCES foods(id)
    )
    """)
    
    conn.commit()
    conn.close()

init_db()

# ---------------------------
# Helper functions
# ---------------------------
def get_foods_df():
    conn = sqlite3.connect(DB_NAME)
    df = pd.read_sql_query(
        "SELECT id, name, unit, protein, carbs, fat, fiber, calories FROM foods ORDER BY name", conn
    )
    conn.close()
    return df

def add_food(name, unit, protein, carbs, fat, fiber, calories):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute(
        "INSERT OR REPLACE INTO foods (name, unit, protein, carbs, fat, fiber, calories) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (name, unit, protein, carbs, fat, fiber, calories),
    )
    conn.commit()
    conn.close()

def log_food(date, food_id, quantity):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO log (date, food_id, quantity) VALUES (?, ?, ?)",
        (date, food_id, quantity),
    )
    conn.commit()
    conn.close()

def get_daily_log(date):
    conn = sqlite3.connect(DB_NAME)
    query = """
    SELECT f.name, l.quantity, f.unit,
           f.protein*l.quantity as protein,
           f.carbs*l.quantity as carbs,
           f.fat*l.quantity as fat,
           f.fiber*l.quantity as fiber,
           f.calories*l.quantity as calories
    FROM log l
    JOIN foods f ON l.food_id=f.id
    WHERE l.date=?
    """
    df = pd.read_sql_query(query, conn, params=(date,))
    conn.close()
    return df

# ---------------------------
# Streamlit UI
# ---------------------------
st.title("🥗 Food Tracker with Fiber")

tab1, tab2, tab3 = st.tabs(["Add Food", "Log Food", "Daily Summary"])

# ---------------------------
# Tab 1: Add Food
# ---------------------------
with tab1:
    st.header("Add a new food")
    with st.form("add_food_form"):
        name = st.text_input("Food name")
        unit = st.text_input("Unit (e.g., 100g, 1 piece)", "100g")
        protein = st.number_input("Protein (g)", 0.0)
        carbs = st.number_input("Carbs (g)", 0.0)
        fat = st.number_input("Fat (g)", 0.0)
        fiber = st.number_input("Fiber (g)", 0.0)
        calories = st.number_input("Calories (kcal)", 0.0)
        submitted = st.form_submit_button("Add Food")
        if submitted and name:
            add_food(name, unit, protein, carbs, fat, fiber, calories)
            st.success(f"Added {name}")

    st.subheader("Foods in Database")
    st.dataframe(get_foods_df())

# ---------------------------
# Tab 2: Log Food
# ---------------------------
with tab2:
    st.header("Log food eaten")
    foods_df = get_foods_df()
    if not foods_df.empty:
        with st.form("log_food_form"):
            date = st.date_input("Date", datetime.date.today())
            food_choice = st.selectbox("Food", foods_df["name"])
            quantity = st.number_input("Quantity", 1.0, 1000.0, 1.0)
            submitted = st.form_submit_button("Log Food")
            if submitted:
                food_id = int(foods_df.loc[foods_df["name"] == food_choice, "id"].values[0])
                log_food(date.isoformat(), food_id, quantity)
                st.success(f"Logged {quantity} × {food_choice}")
    else:
        st.warning("Please add some foods first.")

# ---------------------------
# Tab 3: Daily Summary
# ---------------------------
with tab3:
    st.header("Daily Summary")
    date = st.date_input("Select date", datetime.date.today(), key="summary_date")
    log_df = get_daily_log(date.isoformat())
    
    if not log_df.empty:
        st.subheader("Foods eaten")
        st.dataframe(log_df)

        totals = log_df[["protein", "carbs", "fat", "fiber", "calories"]].sum()
        st.subheader("Daily Totals")
        st.write(totals)

        # Plot
        st.subheader("Macronutrient Breakdown")
        fig, ax = plt.subplots()
        totals[["protein", "carbs", "fat", "fiber"]].plot(kind="bar", ax=ax)
        ax.set_ylabel("Grams")
        st.pyplot(fig)
    else:
        st.info("No foods logged for this date.")
