def run_emr_module():
    import streamlit as st
    import pandas as pd
    from io import BytesIO
    from uuid import uuid4
    import plotly.express as px
    from datetime import datetime, time as dt_time
    
    # Konfigurasi Halaman
    st.set_page_config(page_title="EMR Adoption Rate Dashboard", layout="wide", initial_sidebar_state="expanded")
    
    # Styling CSS untuk Tampilan
    st.markdown(
        """
        <style>
        .welcome {font-size: 26px; font-weight: bold; color: #2c3e50; margin-bottom: 20px;}
        .section-header {font-size: 20px; color: #34495e; margin-top: 20px; margin-bottom: 10px; border-bottom: 1px solid #ddd; padding-bottom: 5px;}
        .action-btn {background-color: #007bff; color: white; padding: 8px 12px; border: none; border-radius: 4px; cursor: pointer; margin-right: 10px;}
        .action-btn:hover {background-color: #0069d9;}
        .session-card {padding: 8px; margin-bottom: 8px; background-color: #ffffff; border: 1px solid #ddd; border-radius: 5px;}
        .delete-btn {background-color: transparent; border: none; color: red; font-weight: bold; cursor: pointer;}
        </style>
        """,
        unsafe_allow_html=True,
    )
    
    # Inisialisasi Session State
    if 'tabs' not in st.session_state:
        st.session_state.tabs = []
    if 'tab_data' not in st.session_state:
        st.session_state.tab_data = {}
    if 'show_summary' not in st.session_state:
        st.session_state.show_summary = False
    if 'summary_calculated' not in st.session_state:
        st.session_state.summary_calculated = False
    
    # Fungsi Pengolahan Data
    @st.cache_data(show_spinner=False)
    def load_data(uploaded_file):
        """Memuat data dari file CSV atau Excel dengan penanganan error."""
        try:
            if uploaded_file.name.endswith("csv"):
                df = pd.read_csv(uploaded_file)
                return {"sheets": {"Sheet1": df}, "multiple": False}
            else:
                xlsx = pd.ExcelFile(uploaded_file)
                sheets = {sheet_name: pd.read_excel(xlsx, sheet_name=sheet_name) for sheet_name in xlsx.sheet_names}
                return {"sheets": sheets, "multiple": len(sheets) > 1}
        except Exception as e:
            st.error(f"Gagal membaca file: {e}")
            return None
    
    def convert_date_columns(df, columns=["created_date", "admission_date"]):
        """Mengonversi kolom tanggal ke format datetime dengan error handling."""
        for col in columns:
            if col in df.columns:
                df[col] = pd.to_datetime(df[col], errors="coerce")
        return df
    
    def data_overview(df):
        """Menampilkan ringkasan data."""
        st.write("**Jumlah Kolom:**", df.shape[1])
        st.write("**Jumlah Baris:**", df.shape[0])
        st.write("**Missing Values per Kolom:**")
        st.write(df.isnull().sum())
    
    def detect_duplicates(df):
        """Mendeteksi duplikat berdasarkan admission_no dan created_date."""
        dup_epa = df[df.duplicated(subset=["admission_no"], keep=False) & df["admission_no"].notnull()] if "admission_no" in df.columns else pd.DataFrame()
        dup_created = df[df.duplicated(subset=["created_date"], keep=False)] if "created_date" in df.columns else pd.DataFrame()
        df_no_epa = df[df["admission_no"].isnull()] if "admission_no" in df.columns else pd.DataFrame()
        combined = pd.DataFrame()
        if not dup_epa.empty or not dup_created.empty:
            cond = pd.Series(False, index=df.index)
            if "admission_no" in df.columns:
                cond |= (df.duplicated(subset=["admission_no"], keep=False) & df["admission_no"].notnull())
            if "created_date" in df.columns:
                cond |= df.duplicated(subset=["created_date"], keep=False)
            combined = df[cond].sort_values(by="created_date") if "created_date" in df.columns else df[cond]
        return dup_epa, dup_created, combined, df_no_epa
    
    def detect_dup_admission_diff_created(df):
        """Mendeteksi admission_no duplikat dengan created_date berbeda."""
        if "admission_no" not in df.columns or "created_date" not in df.columns:
            return pd.DataFrame()
        df_filled = df[df["admission_no"].notnull()]
        dup_diff = df_filled.groupby("admission_no").filter(lambda g: g["created_date"].nunique() > 1)
        if "created_date" in dup_diff.columns:
            dup_diff = dup_diff.sort_values(by="created_date")
        return dup_diff
    
    def clean_duplicates(df, remove_no_epa=False):
        """Membersihkan duplikat dan menghapus baris tanpa admission_no jika diinginkan."""
        before = df.shape[0]
        df_cleaned = df.drop_duplicates(subset=["admission_no", "created_date"], keep="first") if "admission_no" in df.columns and "created_date" in df.columns else df.copy()
        removed_dup = before - df_cleaned.shape[0]
        removed_no_epa_count = 0
        if remove_no_epa and "admission_no" in df_cleaned.columns:
            removed_no_epa_count = df_cleaned["admission_no"].isnull().sum()
            df_cleaned = df_cleaned[df_cleaned["admission_no"].notnull()]
        total_removed = before - df_cleaned.shape[0]
        msg = (f"<b>Pembersihan Selesai:</b><br>"
               f"Duplikat dihapus: {removed_dup} baris.<br>"
               f"Baris tanpa admission dihapus: {removed_no_epa_count} baris.<br>"
               f"Total baris dihapus: {total_removed}.<br>"
               f"Sisa data: {df_cleaned.shape[0]} baris.")
        return df_cleaned, msg
    
    def filter_data_by_date(df, start_dt, end_dt, date_col="admission_date"):
        """Memfilter data berdasarkan rentang tanggal."""
        if date_col not in df.columns:
            st.error(f"Kolom {date_col} tidak ditemukan untuk filtering.")
            return df
        mask = (df[date_col] >= start_dt) & (df[date_col] <= end_dt)
        return df.loc[mask]
    
    def create_summary(df):
        """Membuat ringkasan adopsi EMR berdasarkan admission_date."""
        if "admission_date" not in df.columns:
            st.error("Kolom admission_date tidak ditemukan.")
            return pd.DataFrame()
        summary = df.groupby(df["admission_date"].dt.date).agg(
            Total_Triage=("admission_date", "count"),
            Link_EPA=("admission_no", lambda x: x.notnull().sum()),
            NurseAssessment=("nurse_assessor", lambda x: x.notnull().sum()),
            InitAssessment=("assigned_doctor_name", lambda x: x.notnull().sum()),
            HOME=("ed_discharge_plan", lambda x: (x == "HOME").sum()),
            IPD=("ed_discharge_plan", lambda x: (x == "IPD").sum()),
            PASSAWAY=("ed_discharge_plan", lambda x: (x == "PASSAWAY").sum()),
            Reviewed_Medical_Equipment=("reviewed_medical_equipment", lambda x: (x == "Ya").sum()),
            Discharge_Approved=("status_discharge", lambda x: (x == "APPROVED").sum())
        )
        summary.index = pd.to_datetime(summary.index).strftime("%d-%b-%Y")
        summary = summary.sort_index(key=lambda x: pd.to_datetime(x, format="%d-%b-%Y"))
        return summary
    
    def generate_excel_download(df_cleaned, summary, filename):
        """Membuat file Excel untuk diunduh."""
        to_excel = BytesIO()
        with pd.ExcelWriter(to_excel, engine='openpyxl') as writer:
            df_cleaned.to_excel(writer, index=False, sheet_name='Cleaned_Data')
            summary.to_excel(writer, index=True, sheet_name='Summary')
            # Hitung persentase per hari
            perc_per_hari = summary.copy()
            perc_per_hari["EPA_Percentage"] = (perc_per_hari["Link_EPA"] / perc_per_hari["Total_Triage"] * 100).round(1)
            perc_per_hari["Review_Percentage"] = (perc_per_hari["Reviewed_Medical_Equipment"] / perc_per_hari["Total_Triage"] * 100).round(1)
            perc_per_hari[["EPA_Percentage", "Review_Percentage"]].to_excel(writer, index=True, sheet_name='Persentase_Per_Hari')
            # Hitung persentase keseluruhan
            total = summary.sum(numeric_only=True)
            total_perc = pd.DataFrame({
                "EPA_Percentage": [(total["Link_EPA"] / total["Total_Triage"] * 100).round(1)],
                "Review_Percentage": [(total["Reviewed_Medical_Equipment"] / total["Total_Triage"] * 100).round(1)]
            }, index=["Total"])
            total_perc.to_excel(writer, index=True, sheet_name='Persentase_Keseluruhan')
        return to_excel.getvalue()
    
    def plot_trends(summary, selected_metrics):
        """Membuat grafik tren berdasarkan metrik yang dipilih."""
        fig = px.line(summary.reset_index(), x="index", y=selected_metrics,
                      markers=True, title="Tren Metrik per Tanggal")
        fig.update_layout(hovermode="x unified", template="plotly_white")
        return fig
    
    def parse_time_input(time_str):
        """Mengonversi input waktu ke format time dengan validasi."""
        try:
            return datetime.strptime(time_str.strip(), "%H:%M").time()
        except ValueError:
            st.error("Format waktu harus HH:MM (misalnya, 23:59).")
            return None
    
    # Sidebar untuk Manajemen Session
    st.sidebar.header("📊 Sessions")
    if st.session_state.tabs:
        for tab in st.session_state.tabs:
            with st.sidebar.container():
                cols = st.columns([0.8, 0.2])
                new_name = cols[0].text_input("", value=tab["name"], key=f"edit_{tab['id']}")
                if new_name and new_name not in [t["name"] for t in st.session_state.tabs if t["id"] != tab["id"]]:
                    tab["name"] = new_name
                if cols[1].button("✕", key=f"delete_{tab['id']}"):
                    st.session_state.tabs = [t for t in st.session_state.tabs if t["id"] != tab["id"]]
                    if tab["id"] in st.session_state.tab_data:
                        del st.session_state.tab_data[tab["id"]]
                    st.experimental_rerun()
    
    session_names = [tab["name"] for tab in st.session_state.tabs]
    selected_session_name = st.sidebar.radio("Pilih Session", session_names) if session_names else None
    selected_tab = next((tab for tab in st.session_state.tabs if tab["name"] == selected_session_name), None)
    
    new_tab_name = st.sidebar.text_input("Tambah Session Baru", key="new_tab")
    if st.sidebar.button("Tambah Session"):
        if new_tab_name and new_tab_name not in session_names:
            new_id = str(uuid4())
            st.session_state.tabs.append({"id": new_id, "name": new_tab_name})
            st.session_state.tab_data[new_id] = {"raw": None, "cleaned": None, "log": [], "sheets": None, "selected_sheet": None}
            st.experimental_rerun()
    
    # Tampilan Utama
    st.markdown('<div class="welcome">Selamat datang, Rafi!</div>', unsafe_allow_html=True)
    if not selected_tab:
        st.info("Belum ada session. Silakan tambahkan session di sidebar.")
    else:
        st.markdown(f"## Session: {selected_tab['name']}")
    
        # 1. Upload File
        st.markdown('<div class="section-header">1. Upload File Data</div>', unsafe_allow_html=True)
        uploaded_file = st.file_uploader("Upload CSV/XLSX", type=["csv", "xlsx"], key=f"file_{selected_tab['id']}")
        if uploaded_file:
            file_data = load_data(uploaded_file)
            if file_data:
                st.session_state.tab_data[selected_tab["id"]]["sheets"] = file_data["sheets"]
                st.session_state.tab_data[selected_tab["id"]]["raw"] = None
                st.session_state.tab_data[selected_tab["id"]]["selected_sheet"] = None
    
        sheets = st.session_state.tab_data[selected_tab["id"]]["sheets"]
        if sheets:
            if len(sheets) > 1:
                selected_sheet = st.selectbox("Pilih Sheet", options=list(sheets.keys()), key=f"sheet_{selected_tab['id']}")
                if selected_sheet:
                    st.session_state.tab_data[selected_tab["id"]]["selected_sheet"] = selected_sheet
                    df = sheets[selected_sheet].copy()
                    df = convert_date_columns(df)
                    if "created_date" in df.columns and "admission_date" in df.columns:
                        st.session_state.tab_data[selected_tab["id"]]["raw"] = df
                        st.dataframe(df.head())
                        with st.expander("Tampilkan Data Overview"):
                            data_overview(df)
                    else:
                        st.error("Kolom 'created_date' atau 'admission_date' tidak ditemukan.")
            else:
                df = list(sheets.values())[0].copy()
                df = convert_date_columns(df)
                if "created_date" in df.columns and "admission_date" in df.columns:
                    st.session_state.tab_data[selected_tab["id"]]["raw"] = df
                    st.session_state.tab_data[selected_tab["id"]]["selected_sheet"] = list(sheets.keys())[0]
                    st.dataframe(df.head())
                    with st.expander("Tampilkan Data Overview"):
                        data_overview(df)
                else:
                    st.error("Kolom 'created_date' atau 'admission_date' tidak ditemukan.")
    
        df = st.session_state.tab_data[selected_tab["id"]]["raw"]
        if df is None:
            st.stop()
    
        # 2. Deteksi Duplikat
        st.markdown('<div class="section-header">2. Deteksi Duplikat</div>', unsafe_allow_html=True)
        dup_epa, dup_created, combined_duplicates, df_no_epa = detect_duplicates(df)
        st.info(f"Baris tanpa admission_no: {df_no_epa.shape[0]}")
        if st.button("Tampilkan Duplikat (Created Date)"):
            if not dup_created.empty:
                st.dataframe(dup_created.sort_values(by="created_date"))
            else:
                st.success("Tidak ada duplikat berdasarkan created_date.")
        if st.button("Tampilkan Duplikat (Admission No dengan created_date berbeda)"):
            dup_adm_diff = detect_dup_admission_diff_created(df)
            if not dup_adm_diff.empty:
                st.dataframe(dup_adm_diff)
            else:
                st.success("Tidak ada duplikat admission_no dengan created_date berbeda.")
    
        # 3. Pembersihan Duplikat
        st.markdown('<div class="section-header">3. Pembersihan Duplikat</div>', unsafe_allow_html=True)
        remove_no_epa = st.checkbox("Hapus baris tanpa admission_no")
        if st.button("🧹 Bersihkan Duplikat"):
            df_cleaned, msg = clean_duplicates(df, remove_no_epa)
            st.session_state.tab_data[selected_tab["id"]]["cleaned"] = df_cleaned
            st.markdown(msg, unsafe_allow_html=True)
            st.session_state.show_summary = False
            st.session_state.summary_calculated = False  # Reset summary calculation flag
    
        # 4. Summary Adopsi EMR
        st.markdown('<div class="section-header">4. Summary Adopsi EMR</div>', unsafe_allow_html=True)
        df_cleaned = st.session_state.tab_data[selected_tab["id"]]["cleaned"]
        if df_cleaned is not None:
            use_filter = st.checkbox("Aktifkan Filter Tanggal untuk Summary")
            df_filtered = df_cleaned.copy()
            if use_filter:
                if "admission_date" in df_cleaned.columns:
                    min_date = df_cleaned["admission_date"].min().to_pydatetime()
                    max_date = df_cleaned["admission_date"].max().to_pydatetime()
                    start_date = st.date_input("Tanggal Mulai Summary", min_date.date(), min_value=min_date.date(), max_value=max_date.date())
                    end_date = st.date_input("Tanggal Selesai Summary", max_date.date(), min_value=min_date.date(), max_value=max_date.date())
                    start_time_str = st.text_input("Waktu Mulai Summary (HH:MM)", min_date.strftime("%H:%M"))
                    end_time_str = st.text_input("Waktu Selesai Summary (HH:MM)", max_date.strftime("%H:%M"))
                    start_time = parse_time_input(start_time_str)
                    end_time = parse_time_input(end_time_str)
                    if start_time and end_time:
                        start_dt = datetime.combine(start_date, start_time)
                        end_dt = datetime.combine(end_date, end_time)
                        df_filtered = filter_data_by_date(df_cleaned, start_dt, end_dt)
                        st.markdown("**Summary telah difilter berdasarkan rentang tanggal dan waktu yang dipilih.**")
                else:
                    st.error("Kolom admission_date tidak ditemukan untuk filtering summary.")
    
            if st.button("Hitung Summary"):
                summary = create_summary(df_filtered)
                if not summary.empty:
                    st.session_state.summary_calculated = True
                    st.session_state.summary_data = summary  # Simpan summary di session state
    
            if st.session_state.summary_calculated:
                summary = st.session_state.summary_data
                st.markdown("### Summary Per Hari")
                st.dataframe(summary)
                total = summary.sum(numeric_only=True)
                total_df = total.to_frame().T
                total_df.index = ["Total"]
                st.markdown("### Total Summary")
                st.dataframe(total_df)
    
                perc_mode = st.radio("Pilih Tampilan Persentase Total", options=["Per Hari", "Keseluruhan"], index=0)
                if perc_mode == "Per Hari":
                    perc_table = summary.copy()
                    perc_table["EPA_Percentage"] = (perc_table["Link_EPA"] / perc_table["Total_Triage"] * 100).round(1)
                    perc_table["Review_Percentage"] = (perc_table["Reviewed_Medical_Equipment"] / perc_table["Total_Triage"] * 100).round(1)
                    st.markdown("### Tabel Persentase (Per Hari)")
                    st.dataframe(perc_table[["EPA_Percentage", "Review_Percentage"]])
                else:
                    total_perc = pd.DataFrame({
                        "EPA_Percentage": [(total["Link_EPA"] / total["Total_Triage"] * 100).round(1)],
                        "Review_Percentage": [(total["Reviewed_Medical_Equipment"] / total["Total_Triage"] * 100).round(1)]
                    }, index=["Total"])
                    st.markdown("### Tabel Persentase (Keseluruhan)")
                    st.dataframe(total_perc)
    
                metrics = ["Total_Triage", "Link_EPA", "Reviewed_Medical_Equipment", "NurseAssessment", "InitAssessment", "HOME", "IPD", "PASSAWAY", "Discharge_Approved"]
                selected_metrics = st.multiselect("Pilih Metrik untuk Grafik", metrics, default=["Total_Triage", "Discharge_Approved"])
                if selected_metrics:
                    st.plotly_chart(plot_trends(summary, selected_metrics), use_container_width=True)
    
        # 5. Download Hasil
        st.markdown('<div class="section-header">5. Download Hasil</div>', unsafe_allow_html=True)
        if st.button("Download Hasil Utama"):
            if df_cleaned is not None:
                summary = create_summary(df_cleaned)
                filename = f"EMR_Adoption_{selected_tab['name']}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
                excel_data = generate_excel_download(df_cleaned, summary, filename)
                st.download_button("Unduh File Excel Utama", excel_data, filename, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    
        # Download Duplikat berdasarkan created_date
        if st.button("Download Duplikat (Created Date)"):
            dup_created = detect_duplicates(df)[1]  # Ambil duplikat created_date
            if not dup_created.empty:
                to_excel = BytesIO()
                dup_created.to_excel(to_excel, index=False)
                st.download_button("Unduh Duplikat Created Date", to_excel.getvalue(), "duplikat_created_date.xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
            else:
                st.info("Tidak ada duplikat berdasarkan created_date.")
    
        # Download Duplikat admission_no dengan created_date berbeda
        if st.button("Download Duplikat (Admission No)"):
            dup_adm_diff = detect_dup_admission_diff_created(df)
            if not dup_adm_diff.empty:
                to_excel = BytesIO()
                dup_adm_diff.to_excel(to_excel, index=False)
                st.download_button("Unduh Duplikat Admission No", to_excel.getvalue(), "duplikat_admission_no.xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
            else:
                st.info("Tidak ada duplikat admission_no dengan created_date berbeda.")
    
        # Download Preview Data
        if st.button("Download Preview Data"):
            preview_data = df.head(100)  # Ambil 100 baris pertama
            to_excel = BytesIO()
            preview_data.to_excel(to_excel, index=False)
            st.download_button("Unduh Preview Data", to_excel.getvalue(), "preview_data.xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

def run_hope_module():
    import streamlit as st
    import pandas as pd
    from io import BytesIO
    
    # Konfigurasi Halaman
    st.set_page_config(page_title="HOPE Data Dashboard", layout="wide")
    st.title("📊 HOPE Data Dashboard")
    
    # Tombol Reset Sesi: Menghapus session state agar proses dapat dimulai ulang
    if st.button("Reset Sesi"):
        st.session_state.clear()
        st.experimental_rerun()
    
    # ------------------------------ #
    # Section 1: Pilih Unit & Upload #
    # ------------------------------ #
    st.header("1️⃣ Pilih Unit & Upload Data HOPE")
    unit_options = ["SHDP", "SHSB", "SHLV", "SHKJ", "SHKD", "SHYG", "MRCCC"]
    selected_unit = st.selectbox("Pilih Unit", options=unit_options)
    
    file = st.file_uploader("Unggah file HOPE (.xlsx)", type=["xlsx"], accept_multiple_files=False)
    if file:
        try:
            df = pd.read_excel(file)
            st.success("File berhasil diunggah!")
        except Exception as e:
            st.error(f"Terjadi error saat membaca file: {e}")
            st.stop()
    else:
        st.info("Silakan unggah file HOPE (.xlsx) terlebih dahulu.")
    
    # Lanjutkan hanya jika file sudah diupload
    if file:
        # ------------------------------ #
        # Section 2: Bersihkan Kolom     #
        # ------------------------------ #
        st.header("2️⃣ Bersihkan Kolom")
        important_cols = ["Reg. / Adm. Date", "Reg. / Adm. No", "Name", "Status"]
        missing_cols = [col for col in important_cols if col not in df.columns]
        
        if missing_cols:
            st.error(f"Kolom berikut tidak ditemukan dalam data: {', '.join(missing_cols)}")
            st.stop()
        
        # Simpan data kolom bersih ke dalam session_state (hanya kolom yang dipilih)
        if "cleaned_data" not in st.session_state:
            st.session_state.cleaned_data = None
    
        if st.button("Bersihkan Kolom"):
            df_cleaned = df[important_cols].copy()
            st.session_state.cleaned_data = df_cleaned
            st.success("Kolom telah dibersihkan! Hanya menyisakan 4 kolom penting.")
    
        # Lanjutkan hanya jika data kolom sudah dibersihkan
        if st.session_state.cleaned_data is not None:
            # ------------------------------ #
            # Section 3: Cek Duplikat        #
            # ------------------------------ #
            st.header("3️⃣ Cek Duplikat")
            df_cleaned = st.session_state.cleaned_data.copy()
            # Konversi kolom tanggal
            df_cleaned["Reg. / Adm. Date"] = pd.to_datetime(df_cleaned["Reg. / Adm. Date"], errors="coerce")
            
            # Duplikat berdasarkan Admission No
            dup_adm = df_cleaned[df_cleaned.duplicated(subset=["Reg. / Adm. No"], keep=False)]
            # Duplikat berdasarkan Name
            dup_name = df_cleaned[df_cleaned.duplicated(subset=["Name"], keep=False)]
            # Duplikat: pasien dengan nama yang sama pada hari yang sama
            df_cleaned["Date"] = df_cleaned["Reg. / Adm. Date"].dt.date
            dup_same_day = df_cleaned.groupby(["Date", "Name"]).filter(lambda g: len(g) > 1)
            
            st.write(f"Jumlah baris dengan duplikat Reg. / Adm. No: {dup_adm.shape[0]}")
            st.write(f"Jumlah baris dengan duplikat Name: {dup_name.shape[0]}")
            st.write(f"Jumlah baris dengan pasien yang memiliki nama sama pada hari yang sama: {dup_same_day.shape[0]}")
            
            with st.expander("Tampilkan Detail Duplikat"):
                if not dup_adm.empty:
                    st.subheader("Duplikat Reg. / Adm. No")
                    st.dataframe(dup_adm)
                else:
                    st.write("Tidak ada duplikat Reg. / Adm. No.")
                
                if not dup_name.empty:
                    st.subheader("Duplikat Name")
                    st.dataframe(dup_name)
                else:
                    st.write("Tidak ada duplikat Name.")
                
                if not dup_same_day.empty:
                    st.subheader("Duplikat Name pada Hari yang Sama")
                    st.dataframe(dup_same_day)
                else:
                    st.write("Tidak ada pasien dengan nama yang sama pada hari yang sama.")
    
            # ------------------------------ #
            # Section 4: Hapus Data dengan Status 'Cancelled'
            # ------------------------------ #
            st.header("4️⃣ Hapus Data dengan Status 'Cancelled'")
            # Hanya lakukan assignment jika final_df belum ada di session_state
            if "final_df" not in st.session_state:
                if st.button("Hapus Baris dengan Status 'Cancelled'"):
                    initial_rows = df_cleaned.shape[0]
                    df_no_cancelled = df_cleaned[df_cleaned["Status"].str.lower() != "cancelled"].copy()
                    removed_rows = initial_rows - df_no_cancelled.shape[0]
                    st.success(f"Baris dengan status 'Cancelled' dihapus. Total dihapus: {removed_rows}.")
                    st.session_state.final_df = df_no_cancelled
                else:
                    st.info("Tekan tombol untuk menghapus baris dengan status 'Cancelled'.")
            else:
                st.success("Data tanpa baris 'Cancelled' telah tersedia.")
            
            # Tetapkan final_df untuk proses selanjutnya
            if "final_df" in st.session_state:
                final_df = st.session_state.final_df.copy()
            else:
                final_df = df_cleaned.copy()
            
            # Pastikan data tidak mengandung baris 'Cancelled'
            if final_df["Status"].str.lower().eq("cancelled").any():
                st.error("Masih terdapat baris dengan status 'Cancelled'. Harap hapus terlebih dahulu di Section 4 sebelum melanjutkan.")
                st.stop()
    
            # ------------------------------ #
            # Section 5: Preview Data Bersih #
            # ------------------------------ #
            st.header("5️⃣ Preview Data Bersih")
            st.dataframe(final_df)
            st.write(f"Total baris data: {final_df.shape[0]}")
    
            # ------------------------------ #
            # Section 6: Filter Data Berdasarkan Tanggal
            # ------------------------------ #
            st.header("6️⃣ Filter Data Berdasarkan Tanggal")
            try:
                final_df["Reg. / Adm. Date"] = pd.to_datetime(final_df["Reg. / Adm. Date"], errors="coerce")
            except Exception as e:
                st.error(f"Error saat konversi tanggal: {e}")
            
            if final_df["Reg. / Adm. Date"].notnull().any():
                min_date = final_df["Reg. / Adm. Date"].min().date()
                max_date = final_df["Reg. / Adm. Date"].max().date()
                st.write(f"Range tanggal dalam data: {min_date} s/d {max_date}")
                if st.checkbox("Aktifkan Filter Tanggal"):
                    start_date = st.date_input("Tanggal Mulai", min_value=min_date, max_value=max_date, value=min_date)
                    end_date = st.date_input("Tanggal Selesai", min_value=min_date, max_value=max_date, value=max_date)
                    
                    if start_date > end_date:
                        st.error("Tanggal mulai harus sebelum tanggal selesai.")
                        filtered_df = final_df
                    else:
                        filtered_df = final_df[(final_df["Reg. / Adm. Date"].dt.date >= start_date) & 
                                                 (final_df["Reg. / Adm. Date"].dt.date <= end_date)]
                        st.success(f"Data berhasil difilter. Sisa baris: {filtered_df.shape[0]}")
                else:
                    filtered_df = final_df
                    st.info("Filter tanggal tidak diaktifkan.")
            else:
                st.error("Data tanggal tidak tersedia untuk filtering.")
                filtered_df = final_df
            
            # Tombol untuk lanjut ke Section 7
            if "proceed_section7" not in st.session_state:
                st.session_state.proceed_section7 = False
    
            if st.button("Lanjut ke Section 7: Tabel Adopsi Pasien per Hari"):
                st.session_state.proceed_section7 = True
    
            # ------------------------------ #
            # Section 7: Tabel Adopsi Pasien per Hari
            # ------------------------------ #
            if st.session_state.get("proceed_section7", False):
                st.header("7️⃣ Tabel Adopsi Pasien per Hari")
                # Pastikan kolom tanggal sudah ada
                filtered_df["Date"] = filtered_df["Reg. / Adm. Date"].dt.date
                adoption_table = filtered_df.groupby("Date").size().reset_index(name="Jumlah Pasien")
                # Format tanggal menjadi dd-Mmm (contoh: 12-Feb, 15-Jan)
                adoption_table["Date"] = pd.to_datetime(adoption_table["Date"]).dt.strftime('%d-%b')
                
                if st.button("Tampilkan Adopsi"):
                    st.dataframe(adoption_table)
                    
                    # Fungsi untuk mengonversi DataFrame ke Excel menggunakan openpyxl
                    def convert_df_to_excel(dataframe):
                        output = BytesIO()
                        writer = pd.ExcelWriter(output, engine='openpyxl')
                        dataframe.to_excel(writer, index=False, sheet_name='Adopsi')
                        writer.save()
                        processed_data = output.getvalue()
                        return processed_data
                    
                    excel_data = convert_df_to_excel(adoption_table)
                    # Penamaan file berdasarkan range tanggal, tipe data (HOPE), dan unit
                    if 'start_date' in locals() and 'end_date' in locals():
                        filename = f"HOPE_{selected_unit}_{start_date}_{end_date}.xlsx"
                    else:
                        filename = f"HOPE_{selected_unit}_full.xlsx"
                    
                    st.download_button("Download Tabel Adopsi (Excel)",
                                       data=excel_data,
                                       file_name=filename,
                                       mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
                else:
                    st.info("Tekan tombol 'Tampilkan Adopsi' untuk melihat tabel adopsi pasien per hari.")

if __name__ == "__main__":
    st.set_page_config(page_title="EMR & HOPE Dashboard", layout="wide")
    mode = st.sidebar.radio("Pilih tipe data:", ["EMR", "HOPE"])
    if mode == "EMR":
        run_emr_module()
    else:
        run_hope_module()
