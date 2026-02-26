"""
processor.py – Logique métier : détection PCB, protection HH, calculs, validation.
"""
import re
from typing import Optional

# ─────────────────────────────────────────────────────────────────────────────
# CONSTANTES COLONNES (index 0-based)
# ─────────────────────────────────────────────────────────────────────────────
COL_TYPE    = 0   # HH / LL
COL_LIBELLE = 5   # F – libellé article
COL_QTY_CART = 6  # G – quantité cartons
COL_PU_CART  = 7  # H – prix unitaire carton
COL_PCB      = 12  # M
COL_UNITE    = 13  # N
COL_QTY_U   = 14  # O
COL_PU_U     = 15  # P

# Nombre de colonnes cible (aligné sur HH = 33)
TARGET_COLS = 33

# ─────────────────────────────────────────────────────────────────────────────
# DÉTECTION PCB DEPUIS LIBELLÉ
# ─────────────────────────────────────────────────────────────────────────────

def detect_pcb_from_label(libelle: str) -> tuple[Optional[float], str, str, bool]:
    """
    Analyse le libellé et retourne (pcb_value, unite, methode, is_certain).
    - pcb_value : float ou None si non trouvé
    - unite     : 'KGM' ou 'PCE'
    - methode   : description humaine de la règle appliquée
    - is_certain: True = détection fiable, False = vérification manuelle requise
    """
    lib = libelle.upper().strip()

    # Règle 1 : 18,5KG / 18.5KG / 18,5 KG
    if re.search(r"18[,.]5\s*KG", lib):
        return 18.5, "KGM", "18,5KG → KGM", True

    # Règle 2 : 6,5KG / 6.5KG / 6,5 KG
    if re.search(r"6[,.]5\s*KG", lib):
        return 6.5, "KGM", "6,5KG → KGM", True

    # Règle 3 : N MAINS ou N SACHETS
    match_mains = re.search(r"(\d+)\s*MAINS", lib)
    match_sachets = re.search(r"(\d+)\s*SACHETS", lib)

    if match_sachets:
        n = int(match_sachets.group(1))
        return float(n), "PCE", f"{n} SACHETS → PCE (vérifier)", False

    if match_mains:
        n = int(match_mains.group(1))
        # Pour les libellés "Nx MAINS" le chiffre n'est pas toujours le PCB réel
        return float(n), "PCE", f"{n} MAINS → PCE (vérifier)", False

    # Règle de dernier recours : tout nombre suivi de KG
    match_kg = re.search(r"(\d+[,.]?\d*)\s*KG", lib)
    if match_kg:
        val_str = match_kg.group(1).replace(",", ".")
        try:
            val = float(val_str)
            return val, "KGM", f"{val} KG → KGM (incertain)", False
        except ValueError:
            pass

    return None, "", "Aucun pattern détecté", False


# ─────────────────────────────────────────────────────────────────────────────
# NORMALISATION LIGNES
# ─────────────────────────────────────────────────────────────────────────────

def normalize_rows(rows: list[list[str]]) -> list[list[str]]:
    """
    S'assure que toutes les lignes ont exactement TARGET_COLS cellules.
    HH : complétées si < TARGET_COLS (ne devraient pas l'être).
    LL : étendues de 12 à 33 avec des chaînes vides.
    """
    result = []
    for row in rows:
        extended = list(row)
        while len(extended) < TARGET_COLS:
            extended.append("")
        # Tronque si plus de colonnes (ne devrait pas arriver)
        extended = extended[:TARGET_COLS]
        result.append(extended)
    return result


# ─────────────────────────────────────────────────────────────────────────────
# AUTO-REMPLISSAGE PCB / UNITÉ
# ─────────────────────────────────────────────────────────────────────────────

def autofill_pcb(rows: list[list[str]], protect_hh: bool = True) -> tuple[list[list[str]], list[dict]]:
    """
    Applique la détection PCB sur toutes les lignes LL.
    Retourne (rows_modifiées, warnings).
    Si protect_hh=True, ne touche pas M,N,O,P des lignes HH.
    """
    warnings = []
    for i, row in enumerate(rows):
        if len(row) <= COL_TYPE:
            continue
        row_type = row[COL_TYPE].strip().upper()

        if row_type == "HH" and protect_hh:
            continue  # Ne jamais toucher HH

        if row_type == "LL":
            libelle = row[COL_LIBELLE] if len(row) > COL_LIBELLE else ""
            pcb, unite, methode, certain = detect_pcb_from_label(libelle)

            if pcb is not None:
                # Stocker sans décimale si c'est un entier (ex: 22 et non 22.0)
                row[COL_PCB] = str(int(pcb)) if pcb == int(pcb) else str(pcb)
                row[COL_UNITE] = unite
                if not certain:
                    warnings.append({
                        "ligne": i + 1,
                        "libelle": libelle[:50],
                        "pcb_suggere": pcb,
                        "methode": methode,
                        "type": "PCB_incertain",
                    })
            else:
                row[COL_PCB] = ""
                row[COL_UNITE] = ""
                warnings.append({
                    "ligne": i + 1,
                    "libelle": libelle[:50],
                    "pcb_suggere": None,
                    "methode": methode,
                    "type": "PCB_introuvable",
                })

    return rows, warnings


# ─────────────────────────────────────────────────────────────────────────────
# CALCULS QTY_UNITÉ / PU_UNITÉ
# ─────────────────────────────────────────────────────────────────────────────

def _safe_float(val: str) -> Optional[float]:
    """Convertit une string en float, accepte virgule ou point."""
    if not val or not val.strip():
        return None
    try:
        return float(val.strip().replace(",", "."))
    except ValueError:
        return None


def recalculate(rows: list[list[str]], decimals: int = 6,
                protect_hh: bool = True) -> tuple[list[list[str]], list[dict]]:
    """
    Calcule col O (QTY_U) = qty_cartons * PCB
             col P (PU_U)  = pu_carton / PCB
    sur les lignes LL uniquement.
    Retourne (rows, erreurs).
    """
    errors = []
    for i, row in enumerate(rows):
        if len(row) <= COL_TYPE:
            continue
        row_type = row[COL_TYPE].strip().upper()

        if row_type == "HH" and protect_hh:
            continue

        if row_type == "LL":
            qty_cart = _safe_float(row[COL_QTY_CART] if len(row) > COL_QTY_CART else "")
            pu_cart  = _safe_float(row[COL_PU_CART]  if len(row) > COL_PU_CART  else "")
            pcb      = _safe_float(row[COL_PCB]       if len(row) > COL_PCB      else "")
            libelle  = row[COL_LIBELLE][:40] if len(row) > COL_LIBELLE else ""

            # PCB manquant ou nul
            if pcb is None or pcb == 0:
                row[COL_QTY_U] = ""
                row[COL_PU_U]  = ""
                errors.append({
                    "ligne": i + 1,
                    "libelle": libelle,
                    "type": "PCB_manquant_ou_zero",
                    "detail": f"PCB='{row[COL_PCB] if len(row)>COL_PCB else ''}'"
                })
                continue

            # Quantité unité
            if qty_cart is not None:
                qty_u = qty_cart * pcb
                # Arrondi entier si pas de décimales significatives
                if qty_u == int(qty_u):
                    row[COL_QTY_U] = str(int(qty_u))
                else:
                    row[COL_QTY_U] = f"{qty_u:.{decimals}f}"
            else:
                row[COL_QTY_U] = ""
                errors.append({
                    "ligne": i + 1,
                    "libelle": libelle,
                    "type": "QTY_CART_manquante",
                    "detail": ""
                })

            # Prix unitaire
            if pu_cart is not None:
                pu_u = pu_cart / pcb
                if not (pu_u != pu_u) and abs(pu_u) < 1e15:  # pas NaN ni Inf
                    row[COL_PU_U] = f"{pu_u:.{decimals}f}"
                else:
                    row[COL_PU_U] = ""
                    errors.append({
                        "ligne": i + 1,
                        "libelle": libelle,
                        "type": "PU_infini",
                        "detail": f"PU_cart={pu_cart}, PCB={pcb}"
                    })
            else:
                row[COL_PU_U] = ""
                errors.append({
                    "ligne": i + 1,
                    "libelle": libelle,
                    "type": "PU_CART_manquant",
                    "detail": ""
                })

    return rows, errors


# ─────────────────────────────────────────────────────────────────────────────
# VALIDATION GLOBALE
# ─────────────────────────────────────────────────────────────────────────────

def validate(rows: list[list[str]]) -> list[dict]:
    """
    Vérifie toutes les lignes LL et retourne la liste des problèmes trouvés.
    """
    issues = []
    for i, row in enumerate(rows):
        if len(row) <= COL_TYPE:
            continue
        if row[COL_TYPE].strip().upper() != "LL":
            continue

        libelle = row[COL_LIBELLE][:40] if len(row) > COL_LIBELLE else ""

        # PCB
        pcb_raw = row[COL_PCB] if len(row) > COL_PCB else ""
        pcb = _safe_float(pcb_raw)
        if not pcb_raw.strip():
            issues.append({"ligne": i+1, "libelle": libelle, "type": "PCB_vide"})
        elif pcb is None:
            issues.append({"ligne": i+1, "libelle": libelle, "type": "PCB_non_numerique", "valeur": pcb_raw})

        # Unité
        unite = row[COL_UNITE].strip() if len(row) > COL_UNITE else ""
        if not unite:
            issues.append({"ligne": i+1, "libelle": libelle, "type": "Unité_vide"})

        # Qty_U
        qty_u_raw = row[COL_QTY_U] if len(row) > COL_QTY_U else ""
        if not qty_u_raw.strip():
            issues.append({"ligne": i+1, "libelle": libelle, "type": "QTY_U_vide"})

        # PU_U
        pu_u_raw = row[COL_PU_U] if len(row) > COL_PU_U else ""
        if not pu_u_raw.strip():
            issues.append({"ligne": i+1, "libelle": libelle, "type": "PU_U_vide"})
        else:
            try:
                v = float(pu_u_raw.replace(",", "."))
                if abs(v) > 1e12:
                    issues.append({"ligne": i+1, "libelle": libelle, "type": "PU_U_suspect", "valeur": pu_u_raw})
            except ValueError:
                issues.append({"ligne": i+1, "libelle": libelle, "type": "PU_U_non_numerique", "valeur": pu_u_raw})

    return issues


# ─────────────────────────────────────────────────────────────────────────────
# EXTRACTION TABLEAU ÉDITABLE (LL seulement)
# ─────────────────────────────────────────────────────────────────────────────

def rows_to_display(rows: list[list[str]]) -> list[dict]:
    """
    Convertit les rows en liste de dicts pour affichage/édition Streamlit.
    Inclut l'index d'origine pour réécriture.
    """
    result = []
    for i, row in enumerate(rows):
        if len(row) <= COL_TYPE:
            continue
        if row[COL_TYPE].strip().upper() != "LL":
            continue
        result.append({
            "_idx": i,
            "Type": row[COL_TYPE],
            "Ligne ERP": row[1] if len(row) > 1 else "",
            "Réf": row[2] if len(row) > 2 else "",
            "GLN": row[4] if len(row) > 4 else "",
            "Libellé": row[COL_LIBELLE] if len(row) > COL_LIBELLE else "",
            "Qté cartons": row[COL_QTY_CART] if len(row) > COL_QTY_CART else "",
            "PU carton": row[COL_PU_CART] if len(row) > COL_PU_CART else "",
            "PCB": row[COL_PCB] if len(row) > COL_PCB else "",
            "Unité": row[COL_UNITE] if len(row) > COL_UNITE else "",
            "Qté unité": row[COL_QTY_U] if len(row) > COL_QTY_U else "",
            "PU unité": row[COL_PU_U] if len(row) > COL_PU_U else "",
        })
    return result


def apply_edits(rows: list[list[str]], edited: list[dict]) -> list[list[str]]:
    """
    Réinjecte les valeurs éditées dans rows à partir de la liste de dicts.
    Seules PCB, Unité, Qté unité, PU unité sont modifiables.
    """
    idx_map = {d["_idx"]: d for d in edited}
    for i, row in enumerate(rows):
        if i in idx_map:
            d = idx_map[i]
            if len(row) > COL_PCB:
                row[COL_PCB]   = str(d.get("PCB", ""))
                row[COL_UNITE] = str(d.get("Unité", ""))
                row[COL_QTY_U] = str(d.get("Qté unité", ""))
                row[COL_PU_U]  = str(d.get("PU unité", ""))
    return rows
