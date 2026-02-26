"""
app.py – Interface Streamlit pour le traitement des CSV Vandame → EDI Socomo.
"""
import copy
import json
import streamlit as st
import pandas as pd

from io_utils import read_csv_raw, export_csv, detect_separator
from processor import (
    normalize_rows,
    autofill_pcb,
    recalculate,
    validate,
    rows_to_display,
    apply_edits,
    detect_pcb_from_label,
    COL_TYPE, COL_LIBELLE, COL_QTY_CART, COL_PU_CART,
    COL_PCB, COL_UNITE, COL_QTY_U, COL_PU_U, TARGET_COLS,
)

# ─────────────────────────────────────────────────────────────────────────────
# CONFIG PAGE
# ─────────────────────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="CSV EDI – Fruidor Vandame",
    page_icon="🍌",
    layout="wide",
)

st.title("🍌 Traitement CSV Vandame → EDI Socomo")
st.caption("Ajout automatique PCB / Unité / Qté unité / PU unité (colonnes M·N·O·P) sur les lignes LL.")

# ─────────────────────────────────────────────────────────────────────────────
# SESSION STATE
# ─────────────────────────────────────────────────────────────────────────────
if "rows" not in st.session_state:
    st.session_state.rows = None          # list[list[str]]
if "warnings" not in st.session_state:
    st.session_state.warnings = []
if "errors" not in st.session_state:
    st.session_state.errors = []
if "filename" not in st.session_state:
    st.session_state.filename = "export_final.csv"

# ─────────────────────────────────────────────────────────────────────────────
# SIDEBAR – PARAMÈTRES
# ─────────────────────────────────────────────────────────────────────────────
with st.sidebar:
    st.header("⚙️ Paramètres")

    protect_hh = st.toggle(
        "🛡️ Protéger les lignes HH",
        value=True,
        help="Aucune modification sur M, N, O, P pour les lignes HH.",
    )

    decimals = st.slider(
        "Décimales PU unité",
        min_value=2, max_value=8, value=6,
        help="6 décimales recommandées (évite les rejets GENRAL).",
    )

    sep_override = st.selectbox(
        "Séparateur (auto-détecté)",
        options=["Auto", ";", ",", "Tabulation"],
        index=0,
        help="Laisser sur Auto sauf problème de lecture.",
    )
    forced_sep = None if sep_override == "Auto" else (
        "\t" if sep_override == "Tabulation" else sep_override
    )

    st.divider()
    st.markdown("**Colonnes cibles (index 0)**")
    st.markdown(f"- M (12) = PCB\n- N (13) = Unité\n- O (14) = Qté unité\n- P (15) = PU unité")
    st.markdown("*Les lignes HH ne seront jamais modifiées.*")

# ─────────────────────────────────────────────────────────────────────────────
# ÉTAPE 1 – UPLOAD
# ─────────────────────────────────────────────────────────────────────────────
st.header("1️⃣ Charger le fichier CSV ERP")

uploaded = st.file_uploader(
    "Déposez votre fichier CSV ou TXT (export ERP Vandame)",
    type=["csv", "txt"],
    help="Le fichier est lu entièrement en texte pour préserver les GLN 13 chiffres.",
)

if uploaded is not None:
    with st.spinner("Lecture du fichier…"):
        try:
            rows_raw, detected_sep, encoding = read_csv_raw(uploaded, forced_sep)
            rows_norm = normalize_rows(rows_raw)
            st.session_state.rows = rows_norm
            st.session_state.filename = uploaded.name.rsplit(".", 1)[0] + "_EDI.csv"
            st.session_state.warnings = []
            st.session_state.errors = []

            n_hh = sum(1 for r in rows_norm if r[COL_TYPE].strip().upper() == "HH")
            n_ll = sum(1 for r in rows_norm if r[COL_TYPE].strip().upper() == "LL")
            col1, col2, col3 = st.columns(3)
            col1.metric("Lignes HH (factures)", n_hh)
            col2.metric("Lignes LL (articles)", n_ll)
            col3.metric("Séparateur détecté", repr(detected_sep))
            st.success(f"Fichier chargé : {len(rows_norm)} lignes · encodage {encoding}")
        except Exception as e:
            st.error(f"Erreur de lecture : {e}")

# ─────────────────────────────────────────────────────────────────────────────
# ÉTAPE 2 – ACTIONS AUTOMATIQUES
# ─────────────────────────────────────────────────────────────────────────────
if st.session_state.rows is not None:
    st.header("2️⃣ Traitements automatiques")
    col_a, col_b, col_c = st.columns(3)

    with col_a:
        if st.button("🔍 Auto-remplir PCB & Unité depuis libellé", use_container_width=True):
            rows_copy = copy.deepcopy(st.session_state.rows)
            rows_copy, warns = autofill_pcb(rows_copy, protect_hh=protect_hh)
            st.session_state.rows = rows_copy
            st.session_state.warnings = warns
            if warns:
                st.warning(f"{len(warns)} ligne(s) avec PCB incertain ou introuvable — voir panneau Alertes.")
            else:
                st.success("PCB et Unité remplis pour toutes les lignes LL.")

    with col_b:
        if st.button("🧮 Recalculer Qté unité & PU unité", use_container_width=True):
            rows_copy = copy.deepcopy(st.session_state.rows)
            rows_copy, errs = recalculate(rows_copy, decimals=decimals, protect_hh=protect_hh)
            st.session_state.rows = rows_copy
            st.session_state.errors = errs
            if errs:
                st.error(f"{len(errs)} erreur(s) de calcul — voir panneau Alertes.")
            else:
                st.success("Qté unité et PU unité calculés.")

    with col_c:
        if st.button("▶️ Tout en une fois (auto-remplir + recalculer)", use_container_width=True, type="primary"):
            rows_copy = copy.deepcopy(st.session_state.rows)
            rows_copy, warns = autofill_pcb(rows_copy, protect_hh=protect_hh)
            rows_copy, errs = recalculate(rows_copy, decimals=decimals, protect_hh=protect_hh)
            st.session_state.rows = rows_copy
            st.session_state.warnings = warns
            st.session_state.errors = errs
            total = len(warns) + len(errs)
            if total:
                st.warning(f"{total} alerte(s) — voir panneau ci-dessous.")
            else:
                st.success("Traitement complet sans erreur !")

    # ─── PANNEAU ALERTES ───────────────────────────────────────────────────
    all_alerts = st.session_state.warnings + st.session_state.errors
    if all_alerts:
        with st.expander(f"⚠️ {len(all_alerts)} alerte(s) — cliquez pour voir le détail", expanded=True):
            # Grouper par type
            incertains = [a for a in all_alerts if a["type"] in ("PCB_incertain",)]
            introuvables = [a for a in all_alerts if a["type"] == "PCB_introuvable"]
            calc_errors = [a for a in all_alerts if a["type"] not in ("PCB_incertain", "PCB_introuvable")]

            if introuvables:
                st.error("**PCB introuvable** – remplir manuellement dans le tableau :")
                df_i = pd.DataFrame(introuvables)[["ligne", "libelle", "methode"]]
                st.dataframe(df_i, use_container_width=True, hide_index=True)

            if incertains:
                st.warning("**PCB incertain** – vérifier la valeur suggérée dans le tableau :")
                df_w = pd.DataFrame(incertains)[["ligne", "libelle", "pcb_suggere", "methode"]]
                st.dataframe(df_w, use_container_width=True, hide_index=True)

            if calc_errors:
                st.error("**Erreurs de calcul** :")
                df_e = pd.DataFrame(calc_errors)
                cols_e = [c for c in ["ligne", "libelle", "type", "detail"] if c in df_e.columns]
                st.dataframe(df_e[cols_e], use_container_width=True, hide_index=True)

    # ─────────────────────────────────────────────────────────────────────────
    # ÉTAPE 3 – TABLEAU ÉDITABLE
    # ─────────────────────────────────────────────────────────────────────────
    st.header("3️⃣ Vérification et édition manuelle")

    view_mode = st.radio(
        "Afficher",
        ["Lignes LL uniquement", "Toutes les lignes (lecture seule)"],
        horizontal=True,
    )

    if view_mode == "Lignes LL uniquement":
        display_data = rows_to_display(st.session_state.rows)

        if display_data:
            df_edit = pd.DataFrame(display_data)
            idx_col = "_idx"
            df_display = df_edit.drop(columns=[idx_col])

            # Colonnes éditables
            editable_cols = ["PCB", "Unité", "Qté unité", "PU unité"]
            column_config = {
                "Libellé": st.column_config.TextColumn(width="large"),
                "PCB": st.column_config.TextColumn(
                    "PCB (M)",
                    help="Modifier si la valeur suggérée est incorrecte. Ex: 19, 20, 22",
                    width="small",
                ),
                "Unité": st.column_config.SelectboxColumn(
                    "Unité (N)",
                    options=["KGM", "PCE"],
                    width="small",
                ),
                "Qté unité": st.column_config.TextColumn("Qté unité (O)", width="small"),
                "PU unité": st.column_config.TextColumn("PU unité (P)", width="small"),
                "Qté cartons": st.column_config.TextColumn(disabled=True),
                "PU carton": st.column_config.TextColumn(disabled=True),
                "GLN": st.column_config.TextColumn(disabled=True),
                "Réf": st.column_config.TextColumn(disabled=True),
                "Ligne ERP": st.column_config.TextColumn(disabled=True),
                "Type": st.column_config.TextColumn(disabled=True),
            }

            edited_df = st.data_editor(
                df_display,
                use_container_width=True,
                num_rows="fixed",
                column_config=column_config,
                disabled=["Type", "Ligne ERP", "Réf", "GLN", "Libellé", "Qté cartons", "PU carton"],
                key="data_editor_ll",
            )

            # Réconcilier les index originaux
            edited_df["_idx"] = df_edit["_idx"].values
            edited_list = edited_df.to_dict("records")

            if st.button("💾 Appliquer les modifications du tableau"):
                rows_copy = copy.deepcopy(st.session_state.rows)
                rows_copy = apply_edits(rows_copy, edited_list)
                st.session_state.rows = rows_copy
                st.success("Modifications appliquées ! Pensez à recalculer si vous avez changé des PCB.")
        else:
            st.info("Aucune ligne LL trouvée dans le fichier.")

    else:  # Vue complète
        all_data = []
        for row in st.session_state.rows:
            d = {f"col_{i:02d}": v for i, v in enumerate(row)}
            all_data.append(d)
        if all_data:
            df_all = pd.DataFrame(all_data)
            df_all.columns = [f"col_{i:02d}" for i in range(len(df_all.columns))]
            st.dataframe(df_all, use_container_width=True, height=400)

    # ─────────────────────────────────────────────────────────────────────────
    # ÉTAPE 4 – VALIDATION & EXPORT
    # ─────────────────────────────────────────────────────────────────────────
    st.header("4️⃣ Validation & Téléchargement")

    issues = validate(st.session_state.rows)
    if issues:
        st.error(f"🚨 {len(issues)} problème(s) détecté(s) avant export :")
        df_issues = pd.DataFrame(issues)
        cols_i = [c for c in ["ligne", "libelle", "type", "valeur"] if c in df_issues.columns]
        st.dataframe(df_issues[cols_i], use_container_width=True, hide_index=True)
        export_disabled = False  # On permet quand même l'export pour correction post
        st.warning("Vous pouvez exporter malgré les erreurs, mais le fichier risque d'être rejeté par Socomo.")
    else:
        st.success("✅ Toutes les lignes LL sont complètes. Prêt pour l'export.")

    col_dl1, col_dl2 = st.columns(2)

    with col_dl1:
        csv_bytes = export_csv(copy.deepcopy(st.session_state.rows), sep=";")
        st.download_button(
            label="⬇️ Télécharger le CSV final",
            data=csv_bytes,
            file_name=st.session_state.filename,
            mime="text/csv",
            type="primary",
            use_container_width=True,
        )

    with col_dl2:
        if issues:
            # Rapport de contrôle
            rapport_rows = [{"ligne": iss["ligne"],
                             "libelle": iss.get("libelle", ""),
                             "problème": iss["type"],
                             "valeur": iss.get("valeur", "")}
                            for iss in issues]
            df_rapport = pd.DataFrame(rapport_rows)
            rapport_csv = df_rapport.to_csv(sep=";", index=False, encoding="utf-8-sig").encode("utf-8-sig")
            st.download_button(
                label="📋 Télécharger le rapport d'erreurs",
                data=rapport_csv,
                file_name=st.session_state.filename.replace(".csv", "_rapport.csv"),
                mime="text/csv",
                use_container_width=True,
            )

    # ─── APERÇU BRUT ─────────────────────────────────────────────────────────
    with st.expander("🔎 Aperçu du CSV final (10 premières lignes)"):
        preview_bytes = export_csv(copy.deepcopy(st.session_state.rows[:10]), sep=";")
        st.code(preview_bytes.decode("utf-8-sig"), language=None)
