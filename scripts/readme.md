Here’s a short and clean `README.md`:

---

# 🚆 Train Data Seeder

Simple script to load Indian Railways CSV data into `railmind_db`.

---

## 📦 Requirements

* Python 3.10+
* PostgreSQL
* Install deps:

```bash
pip install pandas sqlalchemy asyncpg
```

---

## ▶️ Usage

### Run seeder

```bash
python scripts/seed_train_data.py --csv data/Train_details_22122017.csv
```

### With custom batch size

```bash
python scripts/seed_train_data.py --csv data/Train_details_22122017.csv --batch-size 500
```

### Dry run (no DB writes)

```bash
python scripts/seed_train_data.py --csv data/Train_details_22122017.csv --dry-run
```

---

## ⚙️ Setup

Configure DB in:

```
app/db/base.py
```

---

## 📊 What it does

* Inserts **stations**
* Inserts/updates **trains**
* Inserts **train stops**
* Safe to re-run (no duplicates)

---

## ⚠️ Notes

* Put CSV inside `data/` folder (or pass full path)
* Batch size default = 500
* Takes ~30–60 seconds

---

Done ✅
