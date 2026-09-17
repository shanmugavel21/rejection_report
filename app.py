import streamlit as st
import pandas as pd
import psycopg2
from datetime import date


# =========================================================
# PAGE CONFIG
# =========================================================

st.set_page_config(
    page_title="Fault Report",
    page_icon="📋",
    layout="wide"
)


# =========================================================
# DATABASE CONNECTION
# =========================================================

def get_connection():
    return psycopg2.connect(
        host=st.secrets["DB_HOST"],
        port=st.secrets["DB_PORT"],
        database=st.secrets["DB_NAME"],
        user=st.secrets["DB_USER"],
        password=st.secrets["DB_PASSWORD"],
        sslmode="require"
    )   


# =========================================================
# FAULT LIST
# =========================================================

FAULTS = [
    ("Conveyor", "Frame Coating Fault - MS"),
    ("Conveyor", "Leg / patti spot broken"),
    ("Conveyor", "Frame Dent"),
    ("Conveyor", "Rubber Leg Fault"),
    ("Conveyor", "Dial Plate Sticker Damage"),
    ("Conveyor", "Dial Plate Scratches / printing issues"),
    ("Conveyor", "Knob Scratches / printing issues"),
    ("Conveyor", "Glass Broken"),
    ("Conveyor", "Glass Acid mark / Printing issue"),
    ("Conveyor", "O Ring Fault"),
    ("Conveyor", "Fixed Tray - Small"),
    ("Conveyor", "Fixed Tray - Big"),
    ("Conveyor", "Fixed Tray - Jumbo"),
    ("Conveyor", "Bundy Tube Damage"),
    ("Conveyor", "Bundy Tube Leak"),
    ("Conveyor", "Mixing Tube Fault - Small"),
    ("Conveyor", "Mixing Tube Fault - Big"),
    ("Conveyor", "Mixing Tube Fault - Jumbo"),

    ("Process", "Mixing Tube Broken"),
    ("Process", "Sim OFF"),
    ("Process", "Sim HIGH"),
    ("Process", "Function Tight"),
    ("Process", "Flame LOW"),
    ("Process", "Flame HIGH"),
    ("Process", "Jet Block"),
    ("Process", "Pipe Block"),
    ("Process", "Burner Fault (W/O Pin)"),
    ("Process", "Burner Fault (I/O Flame)"),
    ("Process", "Burner Coating Fault"),
    ("Process", "Panstand Rejection - Seating / Bend"),
    ("Process", "Panstand Rejection - Coating fault"),
    ("Process", "Panstand Rejection - Pin removed"),
    ("Process", "PC Box Damage"),
    ("Process", "PC Box Vendor Rejection"),
    ("Process", "Dry Air Leak Testing")
]


# Fault → Section
FAULT_TO_SECTION = {
    fault: section
    for section, fault in FAULTS
}


# =========================================================
# LOAD CURRENT SHIFT DATA
# =========================================================

@st.cache_data(ttl=5)
def load_shift_data(report_date, shift):

    conn = get_connection()

    query = """
        SELECT
            fault_name,
            supplier_rejection,
            process_rejection
        FROM rejection_register
        WHERE report_date = %s
        AND shift = %s
    """

    df = pd.read_sql_query(
        query,
        conn,
        params=(report_date, shift)
    )

    conn.close()

    return df


# =========================================================
# LOAD DAILY TOTAL
# =========================================================

@st.cache_data(ttl=5)
def load_daily_data(report_date):

    conn = get_connection()

    query = """
        SELECT
            fault_name,
            COALESCE(SUM(supplier_rejection), 0)
            +
            COALESCE(SUM(process_rejection), 0)
            AS daily_total
        FROM rejection_register
        WHERE report_date = %s
        GROUP BY fault_name
    """

    df = pd.read_sql_query(
        query,
        conn,
        params=(report_date,)
    )

    conn.close()

    return df


# =========================================================
# SAVE DATA
# =========================================================

def save_data(report_date, shift, data):

    conn = get_connection()
    cursor = conn.cursor()

    try:

        # Remove old records for same date + shift
        cursor.execute(
            """
            DELETE FROM rejection_register
            WHERE report_date = %s
            AND shift = %s
            """,
            (report_date, shift)
        )

        insert_query = """
            INSERT INTO rejection_register
            (
                report_date,
                shift,
                section,
                fault_name,
                supplier_rejection,
                process_rejection
            )
            VALUES (%s, %s, %s, %s, %s, %s)
        """

        rows = []

        for _, row in data.iterrows():

            fault = row["Fault"]

            supplier = (
                0
                if pd.isna(row["Supplier"])
                else int(row["Supplier"])
            )

            process = (
                0
                if pd.isna(row["Process"])
                else int(row["Process"])
            )

            # Empty row → don't save
            if supplier == 0 and process == 0:
                continue

            section = FAULT_TO_SECTION[fault]

            rows.append(
                (
                    report_date,
                    shift,
                    section,
                    fault,
                    supplier,
                    process
                )
            )

        if rows:

            cursor.executemany(
                insert_query,
                rows
            )

        conn.commit()

    except Exception:

        conn.rollback()
        raise

    finally:

        cursor.close()
        conn.close()

    # Clear cache
    load_shift_data.clear()
    load_daily_data.clear()


# =========================================================
# DELETE SPECIFIC DATE + SHIFT
# =========================================================

def delete_shift_data(report_date, shift):

    conn = get_connection()
    cursor = conn.cursor()

    try:

        cursor.execute(
            """
            DELETE FROM rejection_register
            WHERE report_date = %s
            AND shift = %s
            """,
            (report_date, shift)
        )

        deleted_rows = cursor.rowcount

        conn.commit()

        load_shift_data.clear()
        load_daily_data.clear()

        return deleted_rows

    except Exception:

        conn.rollback()
        raise

    finally:

        cursor.close()
        conn.close()


# =========================================================
# TITLE
# =========================================================

st.title("📋 Daily Rejection Report")


# =========================================================
# DATE + SHIFT
# =========================================================

col1, col2 = st.columns(2)

with col1:

    report_date = st.date_input(
        "Date",
        value=date.today()
    )

with col2:

    shift = st.selectbox(
        "Shift",
        [
            "1st Shift",
            "2nd Shift",
            "3rd Shift"
        ]
    )


# =========================================================
# SHOW DAILY TOTAL OPTION
# =========================================================

show_daily_total = st.checkbox(
    "Show Daily Total",
    value=False
)


# =========================================================
# LOAD DATA
# =========================================================

shift_data = load_shift_data(
    report_date,
    shift
)

daily_data = load_daily_data(
    report_date
)


# =========================================================
# LOOKUP CURRENT SHIFT DATA
# =========================================================

shift_lookup = {
    row["fault_name"]: (
        row["supplier_rejection"],
        row["process_rejection"]
    )
    for _, row in shift_data.iterrows()
}


# =========================================================
# DAILY TOTAL LOOKUP
# =========================================================

daily_lookup = {
    row["fault_name"]: int(row["daily_total"])
    for _, row in daily_data.iterrows()
}


# =========================================================
# DAILY TOTAL MODE
# =========================================================

if show_daily_total:

    # -----------------------------------------------------
    # SHOW ONLY FAULT + DAILY TOTAL
    # -----------------------------------------------------

    daily_table = []

    for section, fault in FAULTS:

        total = daily_lookup.get(
            fault,
            0
        )

        daily_table.append(
            {
                "Fault": fault,
                "Daily Total": total
            }
        )

    daily_df = pd.DataFrame(
        daily_table
    )

    st.subheader(
        f"📊 Daily Total — {report_date}"
    )

    st.dataframe(
        daily_df,
        hide_index=True,
        use_container_width=True
    )

    total_rejection = int(
        daily_df["Daily Total"].sum()
    )

    st.metric(
        "Total Daily Rejection",
        total_rejection
    )


# =========================================================
# DATA ENTRY MODE
# =========================================================

else:

    # -----------------------------------------------------
    # CREATE ENTRY TABLE
    # -----------------------------------------------------

    table_data = []

    for section, fault in FAULTS:

        supplier = None
        process = None

        if fault in shift_lookup:

            supplier = shift_lookup[fault][0]
            process = shift_lookup[fault][1]

        table_data.append(
            {
                "Fault": fault,
                "Supplier": supplier,
                "Process": process
            }
        )

    df = pd.DataFrame(
        table_data
    )

    st.subheader(
        f"✏️ Enter Rejection — {shift}"
    )

    # -----------------------------------------------------
    # FORM
    # -----------------------------------------------------

    with st.form(
        "rejection_form",
        clear_on_submit=False
    ):

        edited_df = st.data_editor(
            df,

            hide_index=True,

            use_container_width=True,

            num_rows="fixed",

            column_config={

                "Fault": st.column_config.TextColumn(
                    "Fault",
                    disabled=True
                ),

                "Supplier": st.column_config.NumberColumn(
                    "Supplier",
                    min_value=0,
                    step=1,
                    format="%d"
                ),

                "Process": st.column_config.NumberColumn(
                    "Process",
                    min_value=0,
                    step=1,
                    format="%d"
                )
            },

            disabled=[
                "Fault"
            ],

            key="rejection_table"
        )

        save_button = st.form_submit_button(
            "💾 Save Rejection Data",
            type="primary",
            use_container_width=True
        )

    # -----------------------------------------------------
    # SAVE
    # -----------------------------------------------------

    if save_button:

        try:

            save_data(
                report_date,
                shift,
                edited_df
            )

            st.success(
                f"Saved successfully — "
                f"{report_date} | {shift}"
            )

            st.rerun()

        except Exception as e:

            st.error(
                f"Error while saving: {e}"
            )


# =========================================================
# DELETE SECTION
# =========================================================

st.divider()

st.subheader("🗑️ Delete Saved Data")

st.warning(
    f"This will permanently delete all records for "
    f"{report_date} | {shift}"
)


if st.button(
    f"🗑️ Delete {report_date} - {shift} Data",
    use_container_width=True
):

    try:

        deleted_rows = delete_shift_data(
            report_date,
            shift
        )

        if deleted_rows > 0:

            st.success(
                f"{deleted_rows} records deleted successfully."
            )

            st.rerun()

        else:

            st.info(
                "No saved data found for this Date and Shift."
            )

    except Exception as e:

        st.error(
            f"Delete error: {e}"
        )