# SQLAlchemy JOIN Cheat Sheet (Hinglish) 🚀

## 🧠 1. Basic Types of JOIN

### 🔹 INNER JOIN (default)

Sirf matching records laata hai

```python
select(Trains).join(TrainStations)
```

👉 Equivalent SQL:

```sql
INNER JOIN train_stations ON ...
```

✔ Jab dono tables mein match hona zaroori ho

---

### 🔹 LEFT JOIN (OUTER JOIN)

Left table ka sab data + matching right table

```python
select(Trains).outerjoin(TrainStations)
```

👉 Equivalent SQL:

```sql
LEFT OUTER JOIN train_stations ON ...
```

✔ Jab train chahiye even if stations na ho

---

### 🔹 RIGHT JOIN

SQLAlchemy mein directly rarely use hota hai
(usually reverse LEFT JOIN se handle karte hain)

---

### 🔹 FULL OUTER JOIN

```python
from sqlalchemy import join

join(Trains, TrainStations, isouter=True, full=True)
```

✔ Dono side ka data, even if no match

---

## 🧩 2. Different JOIN Scenarios

---

### ✅ Scenario 1: Sirf relation load karna (NO JOIN needed)

```python
from sqlalchemy.orm import selectinload

select(Trains).options(selectinload(Trains.train_stations))
```

✔ Best practice
✔ No duplication
✔ NestJS `relations` jaisa behavior

---

### ✅ Scenario 2: Filter using child table

```python
select(Trains)\
.join(TrainStations)\
.where(TrainStations.station_name == "Delhi")
```

✔ JOIN required
✔ Filtering child table se

---

### ✅ Scenario 3: Parent + child dono chahiye (JOIN + data)

```python
result = await db.execute(
    select(Trains)
    .join(TrainStations)
)

trains = result.scalars().unique().all()
```

✔ `.unique()` mandatory
✔ Duplicate parent objects remove karta hai

---

### ✅ Scenario 4: Single record chahiye (JOIN ke baad)

```python
train = result.scalars().unique().one_or_none()
```

✔ `.unique()` lagana zaroori hai
❌ warna `MultipleResultsFound`

---

### ✅ Scenario 5: LEFT JOIN (optional relation)

```python
select(Trains).outerjoin(TrainStations)
```

✔ Jab kuch trains ke paas stations nahi ho sakte

---

### ✅ Scenario 6: JOIN + eager loading (advanced)

```python
from sqlalchemy.orm import contains_eager

select(Trains)\
.join(TrainStations)\
.options(contains_eager(Trains.train_stations))
```

✔ Ek hi query mein data + mapping
✔ Performance tuning ke liye

---

### ✅ Scenario 7: Multiple JOINs

```python
select(Trains)\
.join(TrainStations)\
.join(AnotherTable)
```

✔ Multiple relations chain kar sakte ho

---

### ✅ Scenario 8: Explicit ON condition

```python
select(Trains).join(
    TrainStations,
    Trains.id == TrainStations.train_id
)
```

✔ Jab relationship defined nahi ho

---

## ⚠️ Common Mistakes

### ❌ Mistake 1:

```python
.join(...).one_or_none()
```

💥 Error: MultipleResultsFound

---

### ❌ Mistake 2:

JOIN use karna when sirf relation load karna hai

👉 Use `selectinload` instead

---

### ❌ Mistake 3:

`.unique()` bhool jaana

👉 Always use after JOIN when fetching ORM objects

---

## 🧠 Golden Rules

```text
1. Relation chahiye → selectinload ✅
2. Filtering chahiye → join ✅
3. JOIN + ORM objects → unique() lagao ✅
4. One record expect → one_or_none() + unique()
```

---

## ⚡ Quick Decision Table

| Situation                  | Use This      |
| -------------------------- | ------------- |
| Train + stations chahiye   | selectinload  |
| Station ke basis pe filter | join          |
| Optional relation          | outerjoin     |
| Duplicate aa rahe          | unique()      |
| Single record              | one_or_none() |

---

## 💬 Final Line

👉 SQLAlchemy mein JOIN powerful hai, but samajh ke use karna padta hai
👉 Galat combo = duplicate rows = errors

Once samajh aa gaya:
🔥 You control SQL completely
