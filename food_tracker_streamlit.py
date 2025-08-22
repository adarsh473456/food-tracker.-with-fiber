# food_tracker_streamlit.py
# ---------------------------
# Food Tracker with Fiber tracking

import sqlite3
from datetime import date, timedelta
from typing import Tuple

import pandas as pd
import streamlit as st

DB_PATH = "food_tracker.db"

# ---------------------------
# Database helpers
# ---------------------------

def get_conn():
    return sqlite3.connect(DB_PATH, check_same_thread=False)


def init_db():
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS foods (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE NOT NULL,
                unit TEXT NOT NULL CHECK(unit IN ('per100g','per_piece','per_serving')),
                protein REAL NOT NULL DEFAULT 0,
                carbs REAL NOT NULL DEFAULT 0,
                fat REAL NOT NULL DEFAULT 0,
                fiber REAL NOT NULL DEFAULT 0,
                calories REAL NOT NULL DEFAULT 0
            );
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS entries (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                d TEXT NOT NULL,
                food_id INTEGER NOT NULL,
                qty REAL NOT NULL,
                note TEXT DEFAULT '',
                FOREIGN KEY(food_id) REFERENCES foods(id)
            );
            """
        )
        conn.commit()


def add_food(name: str, unit: str, protein: float, carbs: float, fat: float, fiber: float, calories: float):
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute(
            "INSERT OR REPLACE INTO foods(name, unit, protein, carbs, fat, fiber, calories) VALUES (?,?,?,?,?,?,?)",
            (name.strip(), unit, float(protein), float(carbs), float(fat), float(fiber), float(calories)),
        )
        conn.commit()


def get_foods_df() -> pd.DataFrame:
    with get_conn() as conn:
        df = pd.read_sql_query(
            "SELECT id, name, unit, protein, carbs, fat, fiber, calories FROM foods ORDER BY name", conn
        )
    return df


def add_entry(d: date, food_id: int, qty: float, note: str = ""):
    d_str = d.strftime("%Y-%m-%d")
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO entries(d, food_id, qty, note) VALUES (?,?,?,?)",
            (d_str, food_id, float(qty), note.strip()),
        )
        conn.commit()


def get_entries_by_date(d: date) -> pd.DataFrame:
    d_str = d.strftime("%Y-%m-%d")
    with get_conn() as conn:
        query = """
            SELECT e.id, e.d, f.name, f.unit, e.qty, f.protein, f.carbs, f.fat, f.fiber, f.calories, e.note,
                   f.id as food_id
            FROM entries e
            JOIN foods f ON e.food_id = f.id
            WHERE e.d = ?
            ORDER BY e.id DESC
        """
        df = pd.read_sql_query(query, conn, params=(d_str,))
    return df


def get_entries_between_dates(start_d: date, end_d: date) -> pd.DataFrame:
    with get_conn() as conn:
        query = """
            SELECT e.id, e.d, f.name, f.unit, e.qty, f.protein, f.carbs, f.fat, f.fiber, f.calories, e.note
            FROM entries e
            JOIN foods f ON e.food_id = f.id
            WHERE e.d BETWEEN ? AND ?
            ORDER BY e.d DESC, e.id DESC
        """
        df = pd.read_sql_query(query, conn, params=(start_d.strftime('%Y-%m-%d'), end_d.strftime('%Y-%m-%d')))
    return df


# ---------------------------
# Calculations
# ---------------------------

def compute_row_totals(row: pd.Series) -> Tuple[float, float, float, float, float]:
    unit = row["unit"]
    qty = float(row["qty"]) if pd.notna(row["qty"]) else 0.0
    p = float(row["protein"]) if pd.notna(row["protein"]) else 0.0
    c = float(row["carbs"]) if pd.notna(row["carbs"]) else 0.0
    f = float(row["fat"]) if pd.notna(row["fat"]) else 0.0
    fi = float(row["fiber"]) if pd.notna(row["fiber"]) else 0.0
    cal = float(row["calories"]) if pd.notna(row["calories"]) else 0.0

    if unit == "per100g":
        factor = qty / 100.0
    else:
        factor = qty

    tp = p * factor
    tc = c * factor
    tf = f * factor
    tfi = fi * factor
    tcal = cal * factor if cal > 0 else tp*4 + tc*4 + tf*9
    return tp, tc, tf, tfi, tcal


def summarize(df: pd.DataFrame) -> Tuple[float, float, float, float, float]:
    if df.empty:
        return 0.0, 0.0, 0.0, 0.0, 0.0
    totals = df.apply(compute_row_totals, axis=1, result_type='expand')
    df[["total_protein", "total_carbs", "total_fat", "total_fiber", "total_calories"]] = totals
    return (
        float(df["total_protein"].sum()),
        float(df["total_carbs"].sum()),
        float(df["total_fat"].sum()),
        float(df["total_fiber"].sum()),
        float(df["total_calories"].sum()),
    )


# ---------------------------
# Starter foods (with fiber)
# ---------------------------
STARTER_FOODS = [
    ("Egg (whole)", "per_piece", 6.0, 0.6, 5.0, 0.0, 70.0),
    ("Chicken breast (cooked)", "per100g", 31.0, 0.0, 3.6, 0.0, 165.0),
    ("Paneer", "per100g", 18.0, 3.4, 20.0, 0.0, 265.0),
    ("Milk (cow)", "per100g", 3.4, 5.0, 3.3, 0.0, 61.0),
    ("Rice (cooked)", "per100g", 2.7, 28.0, 0.3, 0.4, 130.0),
    ("Roti/Chapati", "per_piece", 3.0, 18.0, 3.0, 2.0, 120.0),
    ("Dal (cooked)", "per100g", 9.0, 20.0, 0.4, 8.0, 116.0),
    ("Banana", "per_piece", 1.3, 27.0, 0.3, 3.0, 105.0),
    ("Peanut butter", "per100g", 25.0, 20.0, 50.0, 6.0, 588.0),
    ("Whey protein scoop", "per_serving", 24.0, 3.0, 2.0, 1.0, 120.0),
]


# ---------------------------
# UI
# ---------------------------
st.set_page_config(page_title="Food Tracker with Fiber", layout="centered")
init_db()

st.title("🍽️ Food Tracker — Protein/Carbs/Fat/Fiber")

# Tabs
log_tab, foods_tab, summary_tab, history_tab = st.tabs([
    "🧾 Log Today", "🥗 Foods", "📊 Summary", "🗂️ History"
])

# --- Log Today ---
with log_tab:
    today = st.date_input("Date", value=date.today())
    foods_df = get_foods_df()

    if not foods_df.empty:
        food_name_to_id = {row["name"]: int(row["id"]) for _, row in foods_df.iterrows()}
        chosen_name = st.selectbox("Food", options=list(food_name_to_id.keys()))
        chosen_food = foods_df[foods_df["name"] == chosen_name].iloc[0]

        qty = st.number_input("Quantity", min_value=0.0, step=0.5, value=1.0)
        note = st.text_input("Note (optional)")

        preview_df = pd.DataFrame([{
            "unit": chosen_food["unit"],
            "qty": qty,
            "protein": float(chosen_food["protein"]),
            "carbs": float(chosen_food["carbs"]),
            "fat": float(chosen_food["fat"]),
            "fiber": float(chosen_food["fiber"]),
            "calories": float(chosen_food["calories"]),
        }])
        tp, tc, tf, tfi, tcal = compute_row_totals(preview_df.iloc[0])
        st.caption("This entry will add:")
        col1, col2, col3, col4, col5 = st.columns(5)
        col1.metric("Protein (g)", f"{tp:.1f}")
        col2.metric("Carbs (g)", f"{tc:.1f}")
        col3.metric("Fat (g)", f"{tf:.1f}")
        col4.metric("Fiber (g)", f"{tfi:.1f}")
        col5.metric("Calories", f"{tcal:.0f}")

        if st.button("➕ Add to log"):
            add_entry(today, int(chosen_food["id"]), qty, note)
            st.success("Added!")

    # Show today's log
    day_df = get_entries_by_date(today)
    if not day_df.empty:
        totals = day_df.apply(compute_row_totals, axis=1, result_type='expand')
        day_df[["total_protein", "total_carbs", "total_fat", "total_fiber", "total_calories"]] = totals
        P, C, F, Fi, K = summarize(day_df)

        st.markdown("### Daily totals")
        tcol1, tcol2, tcol3, tcol4, tcol5 = st.columns(5)
        tcol1.metric("Protein", f"{P:.1f} g")
        tcol2.metric("Carbs", f"{C:.1f} g")
        tcol3.metric("Fat", f"{F:.1f} g")
        tcol4.metric("Fiber", f"{Fi:.1f} g")
        tcol5.metric("Calories", f"{K:.0f}")

# --- Foods ---
with foods_tab:
    with st.form("add_food_form", clear_on_submit=True):
        name = st.text_input("Name")
        unit = st.selectbox("Unit type", options=["per100g", "per_piece", "per_serving"]) 
        c1, c2, c3, c4, c5 = st.columns(5)
        protein = c1.number_input("Protein (g)", min_value=0.0, value=0.0)
        carbs = c2.number_input("Carbs (g)", min_value=0.0, value=0.0)
        fat = c3.number_input("Fat (g)", min_value=0.0, value=0.0)
        fiber = c4.number_input("Fiber (g)", min_value=0.0, value=0.0)
        calories = c5.number_input("Calories", min_value=0.0, value=0.0)
        submitted = st.form_submit_button("➕ Add/Update food")
        if submitted:
            add_food(name, unit, protein, carbs, fat, fiber, calories)
            st.success(f"Saved food: {name}")

    foods_df = get_foods_df()
    if not foods_df.empty:
        st.dataframe(foods_df.drop(columns=["id"]), use_container_width=True, hide_index=True)

# --- Summary ---
with summary_tab:
    d = st.date_input("Pick a date", value=date.today(), key="summary_date")
    day_df = get_entries_by_date(d)
    if not day_df.empty:
        P, C, F, Fi, K = summarize(day_df)
        st.markdown(f"**Totals for {d.strftime('%Y-%m-%d')}**")
        col1, col2, col3, col4, col5 = st.columns(5)
        col1.metric("Protein", f"{P:.1f} g")
        col2.metric("Carbs", f"{C:.1f} g")
        col3.metric("Fat", f"{F:.1f} g")
        col4.metric("Fiber", f"{Fi:.1f} g")
        col5.metric("Calories", f"{K:.0f}")

        # Pie chart
        pie_df = pd.DataFrame({
            "Macro": ["Protein", "Carbs", "Fat", "Fiber"],
            "Grams": [P, C, F, Fi]
        })
        import altair as alt
        chart = alt.Chart(pie_df).mark_arc().encode(theta="Grams", color="Macro").properties(width=300, height=300)
        st.altair_chart(chart, use_container_width=False)

# --- History ---
with history_tab:
    days_back = st.slider("Show last N days", 7, 60, 14)
    end_d = date.today()
    start_d = end_d - timedelta(days=days_back - 1)
    hist_df = get_entries_between_dates(start_d, end_d)

    if not hist_df.empty:
        totals = hist_df.apply(compute_row_totals, axis=1, result_type='expand')
        hist_df[["total_protein", "total_carbs", "total_fat", "total_fiber", "total_calories"]] = totals
        daily = hist_df.groupby("d", as_index=False)[["total_protein","total_carbs","total_fat","total_fiber","total_calories"]].sum()
        daily = daily.sort_values("d")
        st.dataframe(daily.rename(columns={
            "d": "Date",
            "total_protein": "Protein (g)",
            "total_carbs": "Carbs (g)",
            "total_fat": "Fat (g)",
            "total_fiber": "Fiber (g)",
            "total_calories": "Calories",
        }), use_container_width=True, hide_index=True)

        # Charts
        st.line_chart(daily.set_index("d")["total_calories"], height=240)
        st.bar_chart(daily.set_index("d")["total_fiber"], height=240)
