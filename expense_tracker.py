import streamlit as st
import pandas as pd
from datetime import date
from google.oauth2.service_account import Credentials
import gspread

CATEGORIES = [
    "Groceries",
    "Food & Dining",
    "Snacks",
    "Transportation",
    "Housing & Rent",
    "Utilities",
    "Entertainment",
    "Shopping",
    "Healthcare",
    "Hair & Skin Care",
    "Education",
    "Travel",
    "Subscriptions",
    "Other",
]

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

SHEET_NAME = "Expenses"


@st.cache_resource
def get_gsheet_connection():
    creds = Credentials.from_service_account_info(
        st.secrets["gcp_service_account"], scopes=SCOPES
    )
    client = gspread.authorize(creds)
    return client


def get_worksheet():
    client = get_gsheet_connection()
    sh = client.open(SHEET_NAME)
    return sh.sheet1


def load_data() -> pd.DataFrame:
    ws = get_worksheet()
    data = ws.get_all_records()
    if not data:
        return pd.DataFrame(columns=["Date", "Category", "Description", "Amount"])
    df = pd.DataFrame(data)
    df["Date"] = pd.to_datetime(df["Date"])
    df["Amount"] = pd.to_numeric(df["Amount"], errors="coerce")
    return df


def add_expense(expense_date, category, description, amount):
    ws = get_worksheet()
    ws.append_row([str(expense_date), category, description, float(amount)])


def delete_expense(row_index):
    ws = get_worksheet()
    ws.delete_rows(int(row_index) + 2)  # +2 for header row and 0-indexing


def main():
    st.set_page_config(page_title="Expense Tracker", page_icon="💰", layout="wide")
    st.title("💰 Monthly Expense Tracker")

    try:
        df = load_data()
    except Exception as e:
        st.error(
            f"Could not connect to Google Sheets. Make sure your secrets are configured correctly.\n\nError: {e}"
        )
        st.stop()

    # --- Add Expense Form ---
    with st.form("add_expense", clear_on_submit=True):
        st.subheader("Add New Expense")
        col1, col2, col3, col4 = st.columns([2, 2, 3, 1])
        with col1:
            expense_date = st.date_input("Date", value=date.today())
        with col2:
            category = st.selectbox("Category", CATEGORIES)
        with col3:
            description = st.text_input("Description")
        with col4:
            amount = st.number_input("Amount", min_value=0.0, step=0.01, format="%.2f")

        submitted = st.form_submit_button("Add Expense")
        if submitted:
            if amount <= 0:
                st.error("Amount must be greater than zero.")
            else:
                add_expense(expense_date, category, description, amount)
                st.success(f"Added: {category} — ${amount:.2f}")
                st.cache_resource.clear()
                st.rerun()

    if df.empty:
        st.info("No expenses yet. Add one above to get started.")
        return

    # --- Filters ---
    st.subheader("📊 Summary & History")
    col_f1, col_f2 = st.columns(2)
    with col_f1:
        months = sorted(df["Date"].dt.to_period("M").unique(), reverse=True)
        month_strs = [str(m) for m in months]
        selected_month = st.selectbox("Filter by Month", ["All"] + month_strs)
    with col_f2:
        selected_cat = st.selectbox("Filter by Category", ["All"] + CATEGORIES)

    filtered = df.copy()
    if selected_month != "All":
        filtered = filtered[filtered["Date"].dt.to_period("M").astype(str) == selected_month]
    if selected_cat != "All":
        filtered = filtered[filtered["Category"] == selected_cat]

    # --- Metrics ---
    total = filtered["Amount"].sum()
    count = len(filtered)
    avg = total / count if count else 0

    m1, m2, m3 = st.columns(3)
    m1.metric("Total Expenses", f"${total:,.2f}")
    m2.metric("Number of Entries", count)
    m3.metric("Average per Entry", f"${avg:,.2f}")

    # --- Charts ---
    c1, c2 = st.columns(2)
    with c1:
        by_cat = filtered.groupby("Category")["Amount"].sum().sort_values(ascending=False)
        if not by_cat.empty:
            st.bar_chart(by_cat)
    with c2:
        by_date = filtered.groupby(filtered["Date"].dt.date)["Amount"].sum()
        if not by_date.empty:
            st.line_chart(by_date)

    # --- Table ---
    st.subheader("📋 Expense Records")
    display = filtered.sort_values("Date", ascending=False).reset_index()
    st.dataframe(
        display[["Date", "Category", "Description", "Amount"]].style.format({"Amount": "${:,.2f}"}),
        use_container_width=True,
    )

    # --- Delete ---
    with st.expander("🗑️ Delete an Expense"):
        if not display.empty:
            idx_to_delete = st.number_input(
                "Row number to delete (from table above, 0-indexed)",
                min_value=0,
                max_value=len(display) - 1,
                step=1,
            )
            if st.button("Delete"):
                original_idx = display.loc[idx_to_delete, "index"]
                delete_expense(original_idx)
                st.success("Deleted.")
                st.cache_resource.clear()
                st.rerun()

    # --- Monthly Report ---
    st.subheader("📅 Monthly Report")
    df["Month"] = df["Date"].dt.to_period("M").astype(str)
    monthly_totals = df.groupby("Month")["Amount"].sum().sort_index()

    if len(monthly_totals) < 1:
        st.info("Not enough data for a monthly report yet.")
    else:
        report = df.groupby("Month").agg(
            Total=("Amount", "sum"),
            Count=("Amount", "count"),
            Average=("Amount", "mean"),
            Max=("Amount", "max"),
        ).sort_index(ascending=False)

        report["Change"] = report["Total"].diff(-1)
        report["Change %"] = (report["Change"] / report["Total"].shift(-1) * 100).round(1)

        st.dataframe(
            report.style.format({
                "Total": "${:,.2f}",
                "Average": "${:,.2f}",
                "Max": "${:,.2f}",
                "Change": "${:,.2f}",
                "Change %": "{:+.1f}%",
            }),
            use_container_width=True,
        )

        st.line_chart(monthly_totals)

        st.subheader("📂 Category Breakdown by Month")
        pivot = df.pivot_table(values="Amount", index="Month", columns="Category", aggfunc="sum", fill_value=0)
        pivot = pivot.sort_index(ascending=False)
        st.dataframe(pivot.style.format("${:,.2f}"), use_container_width=True)
        st.bar_chart(pivot.sort_index())


if __name__ == "__main__":
    main()
