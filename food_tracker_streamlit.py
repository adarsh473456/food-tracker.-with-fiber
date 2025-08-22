# food_tracker_streamlit.py
# ---------------------------
# A simple, beginner‑friendly food tracker you can run locally.
# Tech: Python + Streamlit + SQLite (no internet required once installed)
# Features
# - Add your foods once (per 100g, per piece, or per serving)
# - Log what you ate each day by quantity
# - Auto‑calculate totals (protein, carbs, fat, fiber, calories)
# - See daily summary and history + simple charts
# - Import a starter set of common Indian foods

import sqlite3
from datetime import date, datetime, timedelta
from typing import List, Tuple

import pandas as pd
import streamlit as st

DB_PATH = "food_tracker.db"

# ---------------------------
# Database helpers
# ---------------------------

def get_conn():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    try:
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA journal_mode = WAL")
        conn.execute("PRAGMA synchronous = NORMAL")
    except Exception:
        pass
    return conn


def init_db():
    with get_conn() as conn:
        cur = conn.cursor()
        # Base tables (include fiber from start for fresh DBs)
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
                d TEXT NOT NULL,              -- YYYY-MM-DD
                food_id INTEGER NOT NULL,
                qty REAL NOT NULL,            -- grams for per100g; count for piece/serving
                note TEXT DEFAULT '',
                FOREIGN KEY(food_id) REFERENCES foods(id)
            );
            """
        )
        # Migration: add fiber if missing (for existing DBs created before fiber)
        try:
            cur.execute("ALTER TABLE foods ADD COLUMN fiber REAL NOT NULL DEFAULT 0;")
        except Exception:
            pass

        # Helpful indexes
        try:
            cur.execute("CREATE INDEX IF NOT EXISTS idx_entries_d ON entries(d);")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_entries_food ON entries(food_id);")
        except Exception:
            pass

        conn.commit()


def add_food(name: str, unit: str, protein: float, carbs: float, fat: float, calories: float, fiber: float = 0.0):
    # Safe UPSERT that preserves existing IDs (no REPLACE)
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO foods(name, unit, protein, carbs, fat, fiber, calories)
            VALUES (?,?,?,?,?,?,?)
            ON CONFLICT(name) DO UPDATE SET
                unit=excluded.unit,
                protein=excluded.protein,
                carbs=excluded.carbs,
                fat=excluded.fat,
                fiber=excluded.fiber,
                calories=excluded.calories
            """,
            (name.strip(), unit, float(protein), float(carbs), float(fat), float(fiber), float(calories)),
        )
        conn.commit()


def delete_food(food_id: int):
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute("DELETE FROM foods WHERE id=?", (food_id,))
        conn.commit()


def get_foods_df() -> pd.DataFrame:
    with get_conn() as conn:
        df = pd.read_sql_query(
            "SELECT id, name, unit, protein, carbs, fat, fiber, calories FROM foods ORDER BY name",
            conn
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
        query = (
            """
            SELECT e.id, e.d, f.name, f.unit, e.qty,
                   f.protein, f.carbs, f.fat, f.fiber, f.calories,
                   e.note, f.id as food_id
            FROM entries e
            JOIN foods f ON e.food_id = f.id
            WHERE e.d = ?
            ORDER BY e.id DESC
            """
        )
        df = pd.read_sql_query(query, conn, params=(d_str,))
    return df


def get_entries_between_dates(start_d: date, end_d: date) -> pd.DataFrame:
    with get_conn() as conn:
        query = (
            """
            SELECT e.id, e.d, f.name, f.unit, e.qty,
                   f.protein, f.carbs, f.fat, f.fiber, f.calories,
                   e.note
            FROM entries e
            JOIN foods f ON e.food_id = f.id
            WHERE e.d BETWEEN ? AND ?
            ORDER BY e.d DESC, e.id DESC
            """
        )
        df = pd.read_sql_query(query, conn, params=(start_d.strftime('%Y-%m-%d'), end_d.strftime('%Y-%m-%d')))
    return df


def delete_entry(entry_id: int):
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute("DELETE FROM entries WHERE id=?", (entry_id,))
        conn.commit()


# ---------------------------
# Calculations
# ---------------------------

def calories_from_macros(p: float, c: float, f: float) -> float:
    return p * 4 + c * 4 + f * 9


def compute_row_totals(row: pd.Series) -> Tuple[float, float, float, float, float]:
    unit = row["unit"]
    qty = float(row["qty"]) if pd.notna(row["qty"]) else 0.0
    p = float(row["protein"]) if pd.notna(row["protein"]) else 0.0
    c = float(row["carbs"]) if pd.notna(row["carbs"]) else 0.0
    f = float(row["fat"]) if pd.notna(row["fat"]) else 0.0
    fi = float(row.get("fiber", 0.0)) if pd.notna(row.get("fiber", 0.0)) else 0.0
    cal = float(row["calories"]) if pd.notna(row["calories"]) else 0.0

    factor = qty / 100.0 if unit == "per100g" else qty
    tp = p * factor
    tc = c * factor
    tf = f * factor
    tfi = fi * factor
    tcal = cal * factor if cal > 0 else calories_from_macros(tp, tc, tf)
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
# Starter foods (approx macros incl. fiber)
# ---------------------------
STARTER_FOODS = [
    # name, unit, protein, carbs, fat, fiber, calories
    ("Egg (whole)", "per_piece", 6.0, 0.6, 5.0, 0.0, 70.0),
    ("Chicken breast (cooked)", "per100g", 31.0, 0.0, 3.6, 0.0, 165.0),
    ("Paneer", "per100g", 18.0, 3.4, 20.0, 0.0, 265.0),
    ("Milk (cow)", "per100g", 3.4, 5.0, 3.3, 0.0, 61.0),
    ("Rice (cooked)", "per100g", 2.7, 28.0, 0.3, 0.4, 130.0),
    ("Roti/Chapati", "per_piece", 3.0, 18.0, 3.0, 2.0, 120.0),
    ("Dal (cooked)", "per100g", 9.0, 20.0, 0.4, 8.0, 116.0),
    ("Banana", "per_piece", 1.3, 27.0, 0.3, 3.1, 105.0),
    ("Peanut butter", "per100g", 25.0, 20.0, 50.0, 6.0, 588.0),
    ("Whey protein scoop", "per_serving", 24.0, 3.0, 2.0, 0.0, 120.0),
]


# ---------------------------
# UI
# ---------------------------
st.set_page_config(page_title="Food Tracker (Protein/Carbs/Fat/Fiber)", layout="centered")
init_db()

st.title("🍽 Food Tracker — Protein/Carbs/Fat/Fiber")
st.caption("Add foods once → Log quantities daily → See totals and history")

with st.sidebar:
    st.header("⚙ Quick actions")
    if st.button("Import starter foods"):
        added = 0
        for name, unit, p, c, f, fi, cal in STARTER_FOODS:
            try:
                add_food(name, unit, p, c, f, cal, fi)
                added += 1
            except Exception:
                pass
        st.success(f"Imported {added} foods.")

    st.markdown("---")
    st.write("Backup/Export")
    if st.button("Export foods to CSV"):
        df_foods = get_foods_df()
        csv = df_foods.to_csv(index=False).encode("utf-8")
        st.download_button("Download foods.csv", data=csv, file_name="foods.csv", mime="text/csv")
    df_all = get_entries_between_dates(date(1970,1,1), date.today())
    if not df_all.empty:
        csv2 = df_all.to_csv(index=False).encode("utf-8")
        st.download_button("Download entries.csv", data=csv2, file_name="entries.csv", mime="text/csv")


# Tabs
log_tab, foods_tab, summary_tab, history_tab = st.tabs([
    "🧾 Log Today", "🥗 Foods", "📊 Summary", "🗂 History"
])

# --------------- Log Today ---------------
with log_tab:
    st.subheader("Log what you ate")
    today = st.date_input("Date", value=date.today())

    foods_df = get_foods_df()
    if foods_df.empty:
        st.info("No foods yet. Go to the *Foods* tab to add, or use *Import starter foods* in the sidebar.")
    else:
        # Select food
        food_name_to_id = {row["name"]: int(row["id"]) for _, row in foods_df.iterrows()}
        chosen_name = st.selectbox("Food", options=list(food_name_to_id.keys()))
        chosen_food = foods_df[foods_df["name"] == chosen_name].iloc[0]

        # Unit hint
        unit = chosen_food["unit"]
        if unit == "per100g":
            qty_label = "Quantity (grams)"
            default_qty = 100.0
            help_txt = "Macros are per 100g; enter grams you ate."
        elif unit == "per_piece":
            qty_label = "Quantity (pieces)"
            default_qty = 1.0
            help_txt = "Macros are per 1 piece; enter how many pieces."
        else:
            qty_label = "Quantity (servings)"
            default_qty = 1.0
            help_txt = "Macros are per 1 serving; enter how many servings."

        qty = st.number_input(qty_label, min_value=0.0, step=0.5, value=default_qty, help=help_txt)
        note = st.text_input("Note (optional)", placeholder="e.g., post‑workout, dinner, etc.")

        # Preview totals for this item
        preview_df = pd.DataFrame([{
            "unit": unit,
            "qty": qty,
            "protein": float(chosen_food["protein"]),
            "carbs": float(chosen_food["carbs"]),
            "fat": float(chosen_food["fat"]),
            "fiber": float(chosen_food.get("fiber", 0.0)),
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
    st.markdown("---")
    st.subheader("Today's log")
    day_df = get_entries_by_date(today)
    if day_df.empty:
        st.write("Nothing logged yet today.")
    else:
        # Per‑row totals
        totals = day_df.apply(compute_row_totals, axis=1, result_type='expand')
        day_df[["total_protein", "total_carbs", "total_fat", "total_fiber", "total_calories"]] = totals
        show_df = day_df[["name", "unit", "qty", "total_protein", "total_carbs", "total_fat", "total_fiber", "total_calories", "note", "id"]]
        show_df = show_df.rename(columns={
            "name": "Food",
            "unit": "Unit",
            "qty": "Qty",
            "total_protein": "Protein (g)",
            "total_carbs": "Carbs (g)",
            "total_fat": "Fat (g)",
            "total_fiber": "Fiber (g)",
            "total_calories": "Calories",
            "note": "Note",
            "id": "Entry ID",
        })
        st.dataframe(show_df, use_container_width=True, hide_index=True)

        # Totals for the day
        P, C, F, FI, K = summarize(day_df)
        st.markdown("### Daily totals")
        tcol1, tcol2, tcol3, tcol4, tcol5 = st.columns(5)
        tcol1.metric("Protein", f"{P:.1f} g")
        tcol2.metric("Carbs", f"{C:.1f} g")
        tcol3.metric("Fat", f"{F:.1f} g")
        tcol4.metric("Fiber", f"{FI:.1f} g")
        tcol5.metric("Calories", f"{K:.0f}")

        # Delete entry
        with st.expander("Delete an entry"):
            entry_ids = day_df["id"].tolist()
            if entry_ids:
                entry_to_delete = st.selectbox("Choose Entry ID to delete", options=entry_ids, format_func=lambda i: f"ID {i}")
                if st.button("🗑 Delete selected entry"):
                    delete_entry(int(entry_to_delete))
                    st.success("Entry deleted. Use the refresh button in the toolbar or switch tabs to refresh.")

# --------------- Foods ---------------
with foods_tab:
    st.subheader("Manage foods")

    with st.form("add_food_form", clear_on_submit=True):
        st.write("Add new food:")
        name = st.text_input("Name", placeholder="e.g., Chicken breast")
        unit = st.selectbox("Unit type of macros", options=["per100g", "per_piece", "per_serving"]) 
        c1, c2, c3, c4, c5 = st.columns(5)
        with c1:
            protein = st.number_input("Protein per unit (g)", min_value=0.0, value=0.0)
        with c2:
            carbs = st.number_input("Carbs per unit (g)", min_value=0.0, value=0.0)
        with c3:
            fat = st.number_input("Fat per unit (g)", min_value=0.0, value=0.0)
        with c4:
            fiber = st.number_input("Fiber per unit (g)", min_value=0.0, value=0.0)
        with c5:
            calories = st.number_input("Calories per unit", min_value=0.0, value=0.0, help="Optional; computed from macros if left 0")
        submitted = st.form_submit_button("➕ Add/Update food")
        if submitted:
            if name.strip():
                add_food(name, unit, protein, carbs, fat, calories, fiber)
                st.success(f"Saved food: {name}")
            else:
                st.error("Name is required")

    st.markdown("---")
    st.write("Your foods:")
    foods_df = get_foods_df()
    if foods_df.empty:
        st.info("No foods yet. Use the form above to add some, or the sidebar to import starter foods.")
    else:
        show = foods_df.rename(columns={
            "name": "Food",
            "unit": "Unit",
            "protein": "Protein/Unit (g)",
            "carbs": "Carbs/Unit (g)",
            "fat": "Fat/Unit (g)",
            "fiber": "Fiber/Unit (g)",
            "calories": "Cal/Unit",
        })
        st.dataframe(show.drop(columns=["id"]), use_container_width=True, hide_index=True)

        with st.expander("Delete a food"):
            pick = st.selectbox("Choose food to delete", options=foods_df["name"].tolist())
            if st.button("🗑 Delete selected food"):
                fid = int(foods_df.loc[foods_df["name"] == pick, "id"].iloc[0])
                delete_food(fid)
                st.success(f"Deleted {pick}. Note: existing entries referencing it will no longer show up in views.")

# --------------- Summary ---------------
with summary_tab:
    st.subheader("Daily summary & chart")
    d = st.date_input("Pick a date", value=date.today(), key="summary_date")
    day_df = get_entries_by_date(d)
    if day_df.empty:
        st.info("No entries for this date.")
    else:
        P, C, F, FI, K = summarize(day_df)
        st.markdown(f"*Totals for {d.strftime('%Y-%m-%d')}*")
        col1, col2, col3, col4, col5 = st.columns(5)
        col1.metric("Protein", f"{P:.1f} g")
        col2.metric("Carbs", f"{C:.1f} g")
        col3.metric("Fat", f"{F:.1f} g")
        col4.metric("Fiber", f"{FI:.1f} g")
        col5.metric("Calories", f"{K:.0f}")

        # Macro ratio pie (Altair) - P/C/F only for clarity
        pie_df = pd.DataFrame({
            "Macro": ["Protein", "Carbs", "Fat"],
            "Grams": [P, C, F]
        })
        try:
            import altair as alt
            chart = alt.Chart(pie_df).mark_arc().encode(theta="Grams", color="Macro").properties(width=300, height=300)
            st.altair_chart(chart, use_container_width=False)
        except Exception:
            st.write("Install altair for pie chart: pip install altair")

# --------------- History ---------------
with history_tab:
    st.subheader("History & trends")

    days_back = st.slider("Show last N days", 7, 60, 14)
    end_d = date.today()
    start_d = end_d - timedelta(days=days_back - 1)
    hist_df = get_entries_between_dates(start_d, end_d)

    if hist_df.empty:
        st.info("No history yet.")
    else:
        # Per row totals then group by day
        totals = hist_df.apply(compute_row_totals, axis=1, result_type='expand')
        hist_df[["total_protein", "total_carbs", "total_fat", "total_fiber", "total_calories"]] = totals
        daily = hist_df.groupby("d", as_index=False)[
            ["total_protein","total_carbs","total_fat","total_fiber","total_calories"]
        ].sum()
        daily = daily.sort_values("d")

        st.dataframe(daily.rename(columns={
            "d": "Date",
            "total_protein": "Protein (g)",
            "total_carbs": "Carbs (g)",
            "total_fat": "Fat (g)",
            "total_fiber": "Fiber (g)",
            "total_calories": "Calories",
        }), use_container_width=True, hide_index=True)

        st.line_chart(daily.set_index("d")["total_calories"], height=240)
        st.bar_chart(daily.set_index("d")["total_protein"], height=240)
        st.bar_chart(daily.set_index("d")["total_fiber"], height=240)

st.caption("Tip: Right‑click → Inspect → Clear cache if the UI looks stuck after many edits. Your data lives in food_tracker.db in this folder.")
