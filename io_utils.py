"""
io_utils.py – Lecture robuste CSV ERP + export CSV final.
Tout est lu en texte pour préserver les GLN 13 chiffres.
"""
import io
import chardet


# ─────────────────────────────────────────────────────────────────────────────
# LECTURE
# ─────────────────────────────────────────────────────────────────────────────

def detect_encoding(raw_bytes: bytes) -> str:
    """Détecte l'encodage du fichier."""
    result = chardet.detect(raw_bytes[:50_000])
    enc = result.get("encoding") or "utf-8"
    # Normalisation courante
    if enc.lower() in ("ascii", "iso-8859-1", "windows-1252"):
        return enc
    return enc


def detect_separator(text: str) -> str:
    """Détecte le séparateur parmi ; , \\t en regardant la 1ère ligne."""
    first_line = text.split("\n")[0] if "\n" in text else text[:500]
    counts = {
        ";": first_line.count(";"),
        ",": first_line.count(","),
        "\t": first_line.count("\t"),
    }
    best = max(counts, key=counts.get)
    return best if counts[best] > 0 else ";"


def read_csv_raw(uploaded_file, forced_sep: str | None = None) -> tuple[list[list[str]], str, str]:
    """
    Lit le CSV/TXT uploadé.
    Renvoie (rows, sep, encoding) où rows = liste de listes de strings.
    - Préserve tout en texte pur.
    - Ignore les lignes vides.
    - Gère CRLF/LF.
    """
    raw_bytes = uploaded_file.read()
    enc = detect_encoding(raw_bytes)

    try:
        text = raw_bytes.decode(enc, errors="replace")
    except Exception:
        text = raw_bytes.decode("utf-8", errors="replace")

    # Supprime BOM éventuel
    text = text.lstrip("\ufeff")

    sep = forced_sep if forced_sep else detect_separator(text)

    rows = []
    for line in text.splitlines():
        line = line.rstrip("\r")
        if not line.strip():
            continue
        cells = line.split(sep)
        rows.append(cells)

    return rows, sep, enc


# ─────────────────────────────────────────────────────────────────────────────
# EXPORT
# ─────────────────────────────────────────────────────────────────────────────

def export_csv(rows: list[list[str]], sep: str = ";") -> bytes:
    """
    Exporte les lignes en CSV final :
    - sep=";" (point-virgule)
    - encoding utf-8-sig (compatible Excel FR)
    - Pas de modification de valeurs
    - Supprime les colonnes vides en fin de ligne pour alléger
    """
    output = io.StringIO()
    for row in rows:
        # Supprime les cellules vides en fin de ligne
        while row and row[-1] == "":
            row = row[:-1]
        line = sep.join(row)
        output.write(line + "\r\n")

    return output.getvalue().encode("utf-8-sig")
