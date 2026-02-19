"""
Enterprise Data Pipeline - Inventory Management System
Handles data ingestion, validation, transformation, statistical analysis,
anomaly detection, and report generation for multi-warehouse inventory.
"""

import csv
import statistics
import json
import hashlib
import re
from datetime import datetime, timedelta
from collections import defaultdict, Counter
from functools import wraps
from abc import ABC, abstractmethod


# ============================================================
# Decorators
# ============================================================

def log_execution(func):
    """Decorator that logs function entry/exit with timing."""
    @wraps(func)
    def wrapper(*args, **kwargs):
        start = datetime.utcnow()
        result = func(*args, **kwargs)
        elapsed = (datetime.utcnow() - start).total_seconds()
        return result
    return wrapper


def validate_non_empty(func):
    """Decorator that ensures the first collection argument is non-empty."""
    @wraps(func)
    def wrapper(self, *args, **kwargs):
        if hasattr(self, 'records') and not self.records:
            raise RuntimeError(f"{func.__name__}: No records loaded.")
        return func(self, *args, **kwargs)
    return wrapper


# ============================================================
# Base Classes
# ============================================================

class Validator(ABC):
    """Abstract base class for data validators."""

    @abstractmethod
    def validate(self, value, field_name=""):
        pass

    @abstractmethod
    def error_message(self, value, field_name=""):
        pass

    def __call__(self, value, field_name=""):
        if not self.validate(value, field_name):
            raise ValueError(self.error_message(value, field_name))
        return value


class RangeValidator(Validator):
    """Validates that a numeric value falls within a specified range."""

    def __init__(self, min_val=None, max_val=None):
        self.min_val = min_val
        self.max_val = max_val

    def validate(self, value, field_name=""):
        if self.min_val is not None and value < self.min_val:
            return False
        if self.max_val is not None and value > self.max_val:
            return False
        return True

    def error_message(self, value, field_name=""):
        return (
            f"{field_name}: {value} out of range "
            f"[{self.min_val}, {self.max_val}]"
        )


class PatternValidator(Validator):
    """Validates that a string matches a regex pattern."""

    def __init__(self, pattern, description=""):
        self.pattern = re.compile(pattern)
        self.description = description

    def validate(self, value, field_name=""):
        return bool(self.pattern.match(str(value)))

    def error_message(self, value, field_name=""):
        return (
            f"{field_name}: '{value}' does not match "
            f"pattern {self.description or self.pattern.pattern}"
        )


# ============================================================
# Data Models
# ============================================================

class DataRecord:
    """Represents a single inventory data record with full validation."""

    VALID_CATEGORIES = [
        "electronics", "clothing", "food", "furniture", "books",
        "automotive", "health", "toys", "sports", "garden"
    ]

    WAREHOUSE_CODES = ["WH-EAST", "WH-WEST", "WH-NORTH", "WH-SOUTH", "WH-CENTRAL"]

    price_validator = RangeValidator(min_val=0.01, max_val=999999.99)
    quantity_validator = RangeValidator(min_val=0, max_val=100000)
    sku_validator = PatternValidator(r'^[A-Z]{2,4}-\d{4,8}$', "SKU format XX-0000")

    def __init__(self, record_id, name, category, price, quantity,
                 timestamp_str, warehouse, sku, supplier):
        self.record_id = record_id
        self.name = self._sanitize_name(name)
        self.category = self._validate_category(category)
        self.price = self._parse_price(price)
        self.quantity = self._parse_quantity(quantity)
        self.timestamp = self._parse_timestamp(timestamp_str)
        self.warehouse = self._validate_warehouse(warehouse)
        self.sku = self._validate_sku(sku)
        self.supplier = supplier
        self.checksum = self._compute_checksum()

    def _sanitize_name(self, name):
        cleaned = str(name).strip()
        cleaned = re.sub(r'\s+', ' ', cleaned)
        if len(cleaned) < 2:
            raise ValueError(f"Record {self.record_id}: Name too short: '{cleaned}'")
        if len(cleaned) > 200:
            cleaned = cleaned[:200]
        return cleaned

    def _validate_category(self, category):
        cat_lower = str(category).lower().strip()
        if cat_lower not in self.VALID_CATEGORIES:
            raise ValueError(
                f"Record {self.record_id}: Invalid category '{category}'. "
                f"Must be one of: {', '.join(self.VALID_CATEGORIES)}"
            )
        return cat_lower

    def _parse_price(self, price):
        cleaned = str(price).replace("$", "").replace(",", "").strip()
        value = float(cleaned)
        self.price_validator(value, f"Record {self.record_id} price")
        return round(value, 2)

    def _parse_quantity(self, quantity):
        value = int(str(quantity).strip())
        self.quantity_validator(value, f"Record {self.record_id} quantity")
        return value

    def _parse_timestamp(self, timestamp_str):
        formats = [
            "%Y-%m-%d %H:%M:%S",
            "%Y-%m-%dT%H:%M:%S",
            "%Y-%m-%d",
            "%m/%d/%Y",
            "%d-%m-%Y",
            "%Y/%m/%d %H:%M",
        ]
        for fmt in formats:
            try:
                return datetime.strptime(str(timestamp_str).strip(), fmt)
            except ValueError:
                continue
        raise ValueError(
            f"Record {self.record_id}: Unparseable timestamp '{timestamp_str}'"
        )

    def _validate_warehouse(self, warehouse):
        wh = str(warehouse).upper().strip()
        if wh not in self.WAREHOUSE_CODES:
            raise ValueError(
                f"Record {self.record_id}: Unknown warehouse '{warehouse}'"
            )
        return wh

    def _validate_sku(self, sku):
        self.sku_validator(str(sku).strip(), f"Record {self.record_id} SKU")
        return str(sku).strip()

    def _compute_checksum(self):
        raw = f"{self.record_id}:{self.sku}:{self.price}:{self.quantity}"
        return hashlib.md5(raw.encode()).hexdigest()[:8]

    @property
    def total_value(self):
        return round(self.price * self.quantity, 2)

    @property
    def is_high_value(self):
        return self.total_value > 10000

    @property
    def age_days(self):
        return (datetime.utcnow() - self.timestamp).days

    def is_valid_category(self):
        return self.category in self.VALID_CATEGORIES

    def to_dict(self):
        return {
            "id": self.record_id,
            "name": self.name,
            "category": self.category,
            "price": self.price,
            "quantity": self.quantity,
            "total_value": self.total_value,
            "warehouse": self.warehouse,
            "sku": self.sku,
            "supplier": self.supplier,
            "timestamp": self.timestamp.isoformat(),
            "checksum": self.checksum,
            "is_high_value": self.is_high_value,
            "age_days": self.age_days,
        }


# ============================================================
# Analytics Engine
# ============================================================

class StatisticsEngine:
    """Performs statistical calculations on numeric datasets."""

    @staticmethod
    def compute_stats(values):
        if not values:
            return {"count": 0, "mean": 0, "median": 0, "stdev": 0,
                    "min": 0, "max": 0, "q1": 0, "q3": 0, "iqr": 0}

        sorted_vals = sorted(values)
        n = len(sorted_vals)
        q1_idx = n // 4
        q3_idx = (3 * n) // 4

        return {
            "count": n,
            "mean": round(statistics.mean(values), 2),
            "median": round(statistics.median(values), 2),
            "stdev": round(statistics.stdev(values), 2) if n > 1 else 0.0,
            "min": round(min(values), 2),
            "max": round(max(values), 2),
            "q1": round(sorted_vals[q1_idx], 2),
            "q3": round(sorted_vals[q3_idx], 2),
            "iqr": round(sorted_vals[q3_idx] - sorted_vals[q1_idx], 2),
        }

    @staticmethod
    def compute_correlation(x_values, y_values):
        if len(x_values) != len(y_values) or len(x_values) < 2:
            return 0.0

        n = len(x_values)
        mean_x = statistics.mean(x_values)
        mean_y = statistics.mean(y_values)

        numerator = sum(
            (x - mean_x) * (y - mean_y) for x, y in zip(x_values, y_values)
        )
        denom_x = sum((x - mean_x) ** 2 for x in x_values) ** 0.5
        denom_y = sum((y - mean_y) ** 2 for y in y_values) ** 0.5

        if denom_x == 0 or denom_y == 0:
            return 0.0

        return round(numerator / (denom_x * denom_y), 4)

    @staticmethod
    def detect_outliers(values, method="zscore", threshold=2.5):
        if len(values) < 3:
            return []

        if method == "zscore":
            mean_val = statistics.mean(values)
            stdev_val = statistics.stdev(values)
            if stdev_val == 0:
                return []
            return [
                {"index": i, "value": v,
                 "z_score": round((v - mean_val) / stdev_val, 2)}
                for i, v in enumerate(values)
                if abs((v - mean_val) / stdev_val) > threshold
            ]
        elif method == "iqr":
            sorted_vals = sorted(values)
            n = len(sorted_vals)
            q1 = sorted_vals[n // 4]
            q3 = sorted_vals[(3 * n) // 4]
            iqr = q3 - q1
            lower = q1 - 1.5 * iqr
            upper = q3 + 1.5 * iqr
            return [
                {"index": i, "value": v, "bounds": (round(lower, 2), round(upper, 2))}
                for i, v in enumerate(values)
                if v < lower or v > upper
            ]
        return []


# ============================================================
# Main Analyzer
# ============================================================

class InventoryAnalyzer:
    """Full inventory analysis pipeline with multi-warehouse support."""

    def __init__(self):
        self.records = []
        self.errors = []
        self.category_index = defaultdict(list)
        self.warehouse_index = defaultdict(list)
        self.supplier_index = defaultdict(list)
        self.stats_engine = StatisticsEngine()

    @log_execution
    def load_records(self, raw_data):
        for i, row in enumerate(raw_data):
            try:
                record = DataRecord(
                    record_id=row["id"],
                    name=row["name"],
                    category=row["category"],
                    price=row["price"],
                    quantity=row["quantity"],
                    timestamp_str=row["timestamp"],
                    warehouse=row["warehouse"],
                    sku=row["sku"],
                    supplier=row["supplier"],
                )
                self.records.append(record)
                self.category_index[record.category].append(record)
                self.warehouse_index[record.warehouse].append(record)
                self.supplier_index[record.supplier].append(record)
            except (ValueError, KeyError) as e:
                self.errors.append({
                    "row_index": i,
                    "record_id": row.get("id", f"unknown-{i}"),
                    "error": str(e),
                    "timestamp": datetime.utcnow().isoformat(),
                })

    @validate_non_empty
    def get_category_summary(self):
        summary = {}
        for category, records in self.category_index.items():
            prices = [r.price for r in records]
            quantities = [r.quantity for r in records]

            price_stats = self.stats_engine.compute_stats(prices)
            qty_stats = self.stats_engine.compute_stats(quantities)

            summary[category] = {
                "record_count": len(records),
                "price_stats": price_stats,
                "quantity_stats": qty_stats,
                "total_value": round(sum(r.total_value for r in records), 2),
                "high_value_count": sum(1 for r in records if r.is_high_value),
                "avg_age_days": round(
                    statistics.mean([r.age_days for r in records]), 1
                ),
                "unique_suppliers": len(set(r.supplier for r in records)),
                "warehouse_distribution": dict(Counter(
                    r.warehouse for r in records
                )),
            }
        return summary

    @validate_non_empty
    def get_warehouse_summary(self):
        summary = {}
        for warehouse, records in self.warehouse_index.items():
            values = [r.total_value for r in records]
            summary[warehouse] = {
                "record_count": len(records),
                "total_value": round(sum(values), 2),
                "avg_value": round(statistics.mean(values), 2),
                "category_breakdown": dict(Counter(
                    r.category for r in records
                )),
                "top_suppliers": self._get_top_items(
                    [r.supplier for r in records], limit=5
                ),
                "high_value_items": sum(1 for r in records if r.is_high_value),
            }
        return summary

    @validate_non_empty
    def find_price_outliers(self):
        all_outliers = []
        for category, records in self.category_index.items():
            prices = [r.price for r in records]
            outliers = self.stats_engine.detect_outliers(prices, method="zscore")
            for outlier in outliers:
                record = records[outlier["index"]]
                all_outliers.append({
                    "record_id": record.record_id,
                    "sku": record.sku,
                    "category": category,
                    "warehouse": record.warehouse,
                    "price": record.price,
                    "z_score": outlier["z_score"],
                    "supplier": record.supplier,
                })
        return sorted(all_outliers, key=lambda x: abs(x["z_score"]), reverse=True)

    @validate_non_empty
    def get_price_quantity_correlation(self):
        correlations = {}
        for category, records in self.category_index.items():
            if len(records) < 5:
                continue
            prices = [r.price for r in records]
            quantities = [r.quantity for r in records]
            correlations[category] = self.stats_engine.compute_correlation(
                prices, quantities
            )
        return correlations

    @validate_non_empty
    def get_time_series_breakdown(self, period="monthly"):
        breakdown = defaultdict(lambda: {
            "count": 0, "total_value": 0.0,
            "categories": Counter(), "warehouses": Counter()
        })

        for record in self.records:
            if period == "monthly":
                key = record.timestamp.strftime("%Y-%m")
            elif period == "weekly":
                iso_year, iso_week, _ = record.timestamp.isocalendar()
                key = f"{iso_year}-W{iso_week:02d}"
            elif period == "quarterly":
                quarter = (record.timestamp.month - 1) // 3 + 1
                key = f"{record.timestamp.year}-Q{quarter}"
            else:
                key = record.timestamp.strftime("%Y-%m-%d")

            breakdown[key]["count"] += 1
            breakdown[key]["total_value"] += record.total_value
            breakdown[key]["categories"][record.category] += 1
            breakdown[key]["warehouses"][record.warehouse] += 1

        result = {}
        for key in sorted(breakdown.keys()):
            entry = breakdown[key]
            result[key] = {
                "count": entry["count"],
                "total_value": round(entry["total_value"], 2),
                "top_category": entry["categories"].most_common(1)[0][0]
                    if entry["categories"] else None,
                "warehouse_spread": len(entry["warehouses"]),
            }
        return result

    @validate_non_empty
    def find_duplicate_skus(self):
        sku_map = defaultdict(list)
        for record in self.records:
            sku_map[record.sku].append(record)

        duplicates = []
        for sku, records in sku_map.items():
            if len(records) > 1:
                duplicates.append({
                    "sku": sku,
                    "count": len(records),
                    "warehouses": list(set(r.warehouse for r in records)),
                    "total_quantity": sum(r.quantity for r in records),
                    "record_ids": [r.record_id for r in records],
                })
        return sorted(duplicates, key=lambda x: x["count"], reverse=True)

    @validate_non_empty
    def get_supplier_performance(self):
        performance = {}
        for supplier, records in self.supplier_index.items():
            values = [r.total_value for r in records]
            performance[supplier] = {
                "record_count": len(records),
                "total_value": round(sum(values), 2),
                "avg_value": round(statistics.mean(values), 2),
                "categories": list(set(r.category for r in records)),
                "warehouses": list(set(r.warehouse for r in records)),
                "error_rate": self._compute_supplier_error_rate(supplier),
            }
        return dict(sorted(
            performance.items(),
            key=lambda x: x[1]["total_value"],
            reverse=True
        ))

    def _compute_supplier_error_rate(self, supplier):
        supplier_errors = [
            e for e in self.errors
            if supplier.lower() in e.get("error", "").lower()
        ]
        total = len(self.supplier_index.get(supplier, [])) + len(supplier_errors)
        if total == 0:
            return 0.0
        return round(len(supplier_errors) / total * 100, 2)

    @staticmethod
    def _get_top_items(items, limit=5):
        return [item for item, _ in Counter(items).most_common(limit)]

    @log_execution
    @validate_non_empty
    def generate_report(self):
        valid_records = [r for r in self.records if r.is_valid_category()]
        invalid_records = [r for r in self.records if not r.is_valid_category()]

        report = {
            "metadata": {
                "generated_at": datetime.utcnow().isoformat(),
                "pipeline_version": "2.1.0",
                "total_records_processed": len(self.records),
                "total_errors": len(self.errors),
            },
            "summary": {
                "valid_records": len(valid_records),
                "invalid_records": len(invalid_records),
                "total_inventory_value": round(
                    sum(r.total_value for r in self.records), 2
                ),
                "high_value_items": sum(
                    1 for r in self.records if r.is_high_value
                ),
                "unique_categories": len(self.category_index),
                "unique_warehouses": len(self.warehouse_index),
                "unique_suppliers": len(self.supplier_index),
            },
            "category_analysis": self.get_category_summary(),
            "warehouse_analysis": self.get_warehouse_summary(),
            "price_outliers": self.find_price_outliers()[:20],
            "correlations": self.get_price_quantity_correlation(),
            "time_series": self.get_time_series_breakdown("monthly"),
            "duplicate_skus": self.find_duplicate_skus()[:10],
            "supplier_performance": self.get_supplier_performance(),
        }

        # BUG: Accessing index on empty list when no errors exist
        # Works when there are errors, crashes on clean data
        if self.errors:
            report["error_summary"] = {
                "count": len(self.errors),
                "first_error": self.errors[0]["error"],
                "last_error": self.errors[-1]["error"],
                "sample_errors": self.errors[:5],
            }
        else:
            report["error_summary"] = {
                "count": 0,
                "first_error": self.errors[0]["error"],
                "last_error": None,
                "sample_errors": [],
            }

        return report


# ============================================================
# Dataset Generator
# ============================================================

def build_dataset(num_records=1000):
    """Generate a large realistic synthetic inventory dataset."""
    import random

    categories = DataRecord.VALID_CATEGORIES
    warehouses = DataRecord.WAREHOUSE_CODES
    suppliers = [
        "Acme Corp", "GlobalTech", "PrimeParts", "SwiftSupply",
        "MegaDistro", "QualityFirst", "ValueChain", "DirectSource",
        "ApexGoods", "CoreMaterials"
    ]

    base_prices = {
        "electronics": 299.99, "clothing": 49.99, "food": 12.50,
        "furniture": 599.00, "books": 19.99, "automotive": 189.99,
        "health": 34.99, "toys": 24.99, "sports": 79.99, "garden": 44.99,
    }

    sku_prefixes = {
        "electronics": "EL", "clothing": "CL", "food": "FD",
        "furniture": "FR", "books": "BK", "automotive": "AU",
        "health": "HL", "toys": "TY", "sports": "SP", "garden": "GD",
    }

    dataset = []
    start_date = datetime(2024, 1, 1)

    for i in range(num_records):
        category = random.choice(categories)
        base = base_prices[category]
        price = round(base + random.uniform(-base * 0.4, base * 0.6), 2)
        quantity = random.randint(1, 200)
        warehouse = random.choice(warehouses)
        supplier = random.choice(suppliers)
        prefix = sku_prefixes[category]

        day_offset = random.randint(0, 365)
        timestamp = (start_date + timedelta(days=day_offset)).strftime(
            "%Y-%m-%d %H:%M:%S"
        )

        sku = f"{prefix}-{10000 + i:06d}"

        dataset.append({
            "id": f"REC-{i + 1:06d}",
            "name": f"{category.title()} {supplier.split()[0]} Item #{i + 1}",
            "category": category,
            "price": f"${price}",
            "quantity": str(quantity),
            "timestamp": timestamp,
            "warehouse": warehouse,
            "sku": sku,
            "supplier": supplier,
        })

    return dataset


# ============================================================
# Entry Point
# ============================================================

def main():
    print("=" * 70)
    print("  ENTERPRISE INVENTORY PIPELINE v2.1.0")
    print("=" * 70)

    print("\n[1/4] Building synthetic dataset (1000 records)...")
    data = build_dataset(1000)
    print(f"       Dataset ready: {len(data)} records")

    print("[2/4] Loading records into analyzer...")
    analyzer = InventoryAnalyzer()
    analyzer.load_records(data)
    print(f"       Loaded: {len(analyzer.records)} OK, {len(analyzer.errors)} errors")

    print("[3/4] Running analysis pipeline...")
    report = analyzer.generate_report()

    print("[4/4] Generating output...\n")

    print("-" * 70)
    print("  REPORT SUMMARY")
    print("-" * 70)
    meta = report["metadata"]
    summary = report["summary"]
    print(f"  Generated At       : {meta['generated_at']}")
    print(f"  Pipeline Version   : {meta['pipeline_version']}")
    print(f"  Total Records      : {summary['valid_records']}")
    print(f"  Total Value        : ${summary['total_inventory_value']:,.2f}")
    print(f"  High-Value Items   : {summary['high_value_items']}")
    print(f"  Categories         : {summary['unique_categories']}")
    print(f"  Warehouses         : {summary['unique_warehouses']}")
    print(f"  Suppliers          : {summary['unique_suppliers']}")
    print(f"  Errors             : {meta['total_errors']}")

    print("\n" + "-" * 70)
    print("  CATEGORY BREAKDOWN")
    print("-" * 70)
    for cat, stats in report["category_analysis"].items():
        ps = stats["price_stats"]
        print(
            f"  {cat:15s} | {stats['record_count']:4d} items "
            f"| avg ${ps['mean']:8.2f} "
            f"| total ${stats['total_value']:12,.2f} "
            f"| {stats['high_value_count']:3d} high-val"
        )

    print("\n" + "-" * 70)
    print("  WAREHOUSE BREAKDOWN")
    print("-" * 70)
    for wh, stats in report["warehouse_analysis"].items():
        print(
            f"  {wh:12s} | {stats['record_count']:4d} items "
            f"| total ${stats['total_value']:12,.2f} "
            f"| {stats['high_value_items']:3d} high-val"
        )

    outliers = report["price_outliers"]
    print(f"\n  Price Outliers      : {len(outliers)} detected")
    for o in outliers[:5]:
        print(
            f"    {o['record_id']} [{o['sku']}] "
            f"({o['category']}) ${o['price']:.2f} z={o['z_score']}"
        )

    corrs = report["correlations"]
    print(f"\n  Price-Qty Correlations:")
    for cat, corr in corrs.items():
        bar = "+" * int(abs(corr) * 20) if corr > 0 else "-" * int(abs(corr) * 20)
        print(f"    {cat:15s}: {corr:+.4f} {bar}")

    dupes = report["duplicate_skus"]
    print(f"\n  Duplicate SKUs     : {len(dupes)} found")
    for d in dupes[:3]:
        print(f"    {d['sku']}: {d['count']}x across {d['warehouses']}")

    ts = report["time_series"]
    print(f"\n  Monthly Timeline   : {len(ts)} periods")
    for period, data in list(ts.items())[:6]:
        print(
            f"    {period}: {data['count']:4d} records "
            f"| ${data['total_value']:12,.2f} "
            f"| top: {data['top_category']}"
        )

    error_sum = report["error_summary"]
    print(f"\n  Error Summary      : {error_sum['count']} total")
    if error_sum["first_error"]:
        print(f"    First: {error_sum['first_error']}")

    print("\n" + "=" * 70)
    print("  Pipeline complete.")
    print("=" * 70)


if __name__ == "__main__":
    main()
