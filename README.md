# 🍌 CSV EDI – Fruidor Vandame

Webapp Streamlit locale pour transformer les exports CSV ERP Vandame en fichiers EDI
conformes (ajout colonnes M·N·O·P : PCB, Unité, Qté unité, PU unité).

---

## ⚡ Démarrage rapide

### 1. Prérequis
- Python 3.10+ installé ([python.org](https://python.org))
- Terminal / Invite de commandes

### 2. Installation (une seule fois)
```bash
# Cloner / copier le dossier, puis :
pip install -r requirements.txt
```

### 3. Lancement
```bash
streamlit run app.py
```
L'application s'ouvre automatiquement dans votre navigateur (http://localhost:8501).

---

## 📋 Guide d'utilisation

### Étape 1 – Charger le fichier
- Déposez le CSV (ou TXT) issu de l'ERP Vandame.
- Le séparateur est détecté automatiquement (`;` par défaut).
- **Tous les champs sont lus en texte** → pas de conversion des GLN 13 chiffres.

### Étape 2 – Traitements automatiques
Cliquez sur **"▶️ Tout en une fois"** pour :
- Auto-détecter le PCB depuis le libellé (col F) :
  - `18,5KG` → PCB = 18.5, Unité = **KGM**
  - `6,5 KG` → PCB = 6.5, Unité = **KGM**
  - `N MAINS` / `N SACHETS` → PCB = N suggéré, Unité = **PCE** *(à vérifier !)*
- Calculer col O = Qté cartons × PCB
- Calculer col P = PU carton ÷ PCB (6 décimales par défaut)

> ⚠️ Les libellés de type "22 MAINS 5 DOIGTS" : le nombre dans le libellé
> n'est **pas toujours** le PCB réel (peut être 19, 20 ou 22 selon la livraison).
> Ces lignes sont **signalées en orange** et doivent être vérifiées manuellement.

### Étape 3 – Vérification et édition
Le tableau éditable affiche toutes les lignes LL.
- Colonnes modifiables : **PCB**, **Unité**, **Qté unité**, **PU unité**
- Après correction d'un PCB → cliquez **"Recalculer"** pour mettre à jour O et P.
- Cliquez **"Appliquer les modifications du tableau"** pour valider vos saisies.

> 🛡️ Les lignes **HH** ne sont **jamais modifiées** sur M, N, O, P
> (toggle "Protéger HH" activé par défaut dans la sidebar).

### Étape 4 – Export
- **"⬇️ Télécharger le CSV final"** → fichier `;`-séparé, encodage UTF-8-BOM.
- **"📋 Rapport d'erreurs"** → CSV listant les problèmes restants.

---

## ⚙️ Paramètres sidebar

| Paramètre | Défaut | Description |
|-----------|--------|-------------|
| Protéger HH | ✅ ON | Ne jamais toucher M,N,O,P des lignes HH |
| Décimales PU unité | 6 | Précision du PU (6 rec. pour éviter GENRAL) |
| Séparateur | Auto | Détection auto ou forçage manuel |

---

## 📁 Structure fichiers

```
app.py          # Interface Streamlit
processor.py    # Logique métier (détection PCB, calculs, validation)
io_utils.py     # Lecture/export CSV robuste
requirements.txt
README.md
```

---

## 🔢 Règles métier appliquées

| Libellé contient | PCB | Unité | Fiabilité |
|------------------|-----|-------|-----------|
| `18,5KG` | 18.5 | KGM | ✅ Certaine |
| `6,5 KG` | 6.5 | KGM | ✅ Certaine |
| `N MAINS` | N (extrait) | PCE | ⚠️ À vérifier |
| `N SACHETS` | N (extrait) | PCE | ⚠️ À vérifier |
| Autre | vide | vide | ❌ Manuel |

**Formules :**
- `Col O (Qté unité)` = Col G (Qté cartons) × Col M (PCB)
- `Col P (PU unité)` = Col H (PU carton) ÷ Col M (PCB)

**Protection HH :** les colonnes M, N, O, P des lignes HH contiennent des données
critiques (dates, GLN, références) qui ne doivent **jamais** être écrasées.
