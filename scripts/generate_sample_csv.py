"""產生一份符合 Kaggle Supermarket Sales schema 的「合成樣本」CSV。

注意: 這不是真實的 Kaggle 資料,僅為了讓專案在未下載真實資料時
也能離線端到端運行與通過測試。欄位、型別、值域皆對齊試題規格。
真實資料請見 README 的下載說明後覆蓋 data/SuperMarket Analysis.csv。
"""
import csv
import os
import random
from datetime import datetime, timedelta

random.seed(42)  # 固定種子 → 可重現

N = 1000
OUT = os.path.join(os.path.dirname(__file__), "..", "data", "SuperMarket Analysis.csv")

BRANCH_CITY = {"Alex": "Yangon", "Giza": "Naypyitaw", "Cairo": "Mandalay"}
BRANCHES = list(BRANCH_CITY.keys())
CUSTOMER_TYPES = ["Member", "Normal"]
GENDERS = ["Male", "Female"]
PRODUCT_LINES = [
    "Health and beauty",
    "Electronic accessories",
    "Home and lifestyle",
    "Sports and travel",
    "Food and beverages",
    "Fashion accessories",
]
PAYMENTS = ["Ewallet", "Cash", "Credit card"]

HEADER = [
    "Invoice ID", "Branch", "City", "Customer type", "Gender", "Product line",
    "Unit price", "Quantity", "Tax 5%", "Sales", "Date", "Time", "Payment",
    "cogs", "gross margin percentage", "gross income", "Rating",
]

GROSS_MARGIN_PCT = 4.761904762
start_date = datetime(2019, 1, 1)


def rand_invoice_id():
    a = random.randint(100, 999)
    b = random.randint(10, 99)
    c = random.randint(1000, 9999)
    return f"{a}-{b}-{c}"


def rand_time():
    hour = random.randint(10, 20)  # 營業時段 10:00-20:59
    minute = random.randint(0, 59)
    dt = datetime(2019, 1, 1, hour, minute, 0)
    return dt.strftime("%I:%M:%S %p").lstrip("0")


rows = []
for _ in range(N):
    branch = random.choice(BRANCHES)
    city = BRANCH_CITY[branch]
    unit_price = round(random.uniform(10, 100), 2)
    quantity = random.randint(1, 10)
    cogs = round(unit_price * quantity, 4)
    tax = round(cogs * 0.05, 4)
    sales = round(cogs + tax, 4)
    gross_income = tax  # 依規格,毛利 = 稅額(5% 毛利率結構)
    date = start_date + timedelta(days=random.randint(0, 89))  # 2019/1-3
    rows.append([
        rand_invoice_id(), branch, city,
        random.choice(CUSTOMER_TYPES), random.choice(GENDERS),
        random.choice(PRODUCT_LINES),
        f"{unit_price:.2f}", quantity, f"{tax:.4f}", f"{sales:.4f}",
        date.strftime("%m/%d/%Y").lstrip("0").replace("/0", "/"),
        rand_time(), random.choice(PAYMENTS),
        f"{cogs:.4f}", f"{GROSS_MARGIN_PCT:.9f}", f"{gross_income:.4f}",
        round(random.uniform(4.0, 10.0), 1),
    ])

os.makedirs(os.path.dirname(OUT), exist_ok=True)
with open(OUT, "w", newline="", encoding="utf-8") as f:
    w = csv.writer(f)
    w.writerow(HEADER)
    w.writerows(rows)

print(f"Wrote {len(rows)} synthetic rows to {os.path.abspath(OUT)}")
