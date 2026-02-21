import pytest
from app import (
    RangeValidator,
    PatternValidator,
    DataRecord,
    StatisticsEngine,
    InventoryAnalyzer,
)


# ============================================================
# RangeValidator
# ============================================================

def test_range_validator_pass():
    v = RangeValidator(min_val=0, max_val=100)
    assert v.validate(50) is True


def test_range_validator_fail_below():
    v = RangeValidator(min_val=0, max_val=100)
    with pytest.raises(ValueError):
        v(value=-1, field_name="qty")


def test_range_validator_fail_above():
    v = RangeValidator(min_val=0, max_val=100)
    with pytest.raises(ValueError):
        v(value=101, field_name="qty")


# ============================================================
# PatternValidator
# ============================================================

def test_pattern_validator_pass():
    v = PatternValidator(r'^[A-Z]{2,4}-\d{4,8}$', "SKU format")
    assert v.validate("EL-010001") is True


def test_pattern_validator_fail():
    v = PatternValidator(r'^[A-Z]{2,4}-\d{4,8}$', "SKU format")
    with pytest.raises(ValueError):
        v(value="bad-sku", field_name="sku")


# ============================================================
# DataRecord
# ============================================================

def _make_record(record_id="REC-000001", price="$99.99", quantity="10",
                 category="electronics", sku="EL-010001",
                 warehouse="WH-EAST", name="Test Item",
                 timestamp="2024-06-01 12:00:00", supplier="Acme Corp"):
    return DataRecord(
        record_id=record_id,
        name=name,
        category=category,
        price=price,
        quantity=quantity,
        timestamp_str=timestamp,
        warehouse=warehouse,
        sku=sku,
        supplier=supplier,
    )


def test_data_record_construction():
    r = _make_record()
    assert r.record_id == "REC-000001"
    assert r.price == 99.99
    assert r.quantity == 10
    assert r.category == "electronics"
    assert r.warehouse == "WH-EAST"


def test_data_record_total_value():
    r = _make_record(price="$10.00", quantity="5")
    assert r.total_value == 50.0


def test_data_record_invalid_category():
    with pytest.raises(ValueError, match="Invalid category"):
        _make_record(category="invalid_cat")


def test_data_record_invalid_warehouse():
    with pytest.raises(ValueError, match="Unknown warehouse"):
        _make_record(warehouse="WH-NOWHERE")


def test_data_record_invalid_sku():
    with pytest.raises(ValueError):
        _make_record(sku="BAD")


def test_data_record_checksum_format():
    r = _make_record()
    assert len(r.checksum) == 8


def test_data_record_high_value_true():
    # price * quantity > 10000
    r = _make_record(price="$200.00", quantity="100")
    assert r.is_high_value is True


def test_data_record_high_value_false():
    r = _make_record(price="$10.00", quantity="5")
    assert r.is_high_value is False


def test_data_record_to_dict_keys():
    r = _make_record()
    d = r.to_dict()
    for key in ("id", "name", "category", "price", "quantity",
                 "total_value", "warehouse", "sku", "supplier",
                 "timestamp", "checksum", "is_high_value", "age_days"):
        assert key in d


# ============================================================
# StatisticsEngine
# ============================================================

def test_statistics_engine_empty():
    result = StatisticsEngine.compute_stats([])
    assert result["count"] == 0
    assert result["mean"] == 0


def test_statistics_engine_basic():
    result = StatisticsEngine.compute_stats([10.0, 20.0, 30.0])
    assert result["count"] == 3
    assert result["mean"] == 20.0
    assert result["min"] == 10.0
    assert result["max"] == 30.0


def test_statistics_engine_single_value():
    result = StatisticsEngine.compute_stats([42.0])
    assert result["count"] == 1
    assert result["stdev"] == 0.0


def test_statistics_engine_outliers_zscore():
    values = [10, 11, 10, 12, 10, 11, 100]   # 100 is obvious outlier
    outliers = StatisticsEngine.detect_outliers(values, method="zscore", threshold=2.0)
    assert len(outliers) >= 1
    assert outliers[0]["value"] == 100


def test_statistics_engine_correlation_perfect():
    x = [1.0, 2.0, 3.0, 4.0, 5.0]
    y = [2.0, 4.0, 6.0, 8.0, 10.0]
    corr = StatisticsEngine.compute_correlation(x, y)
    assert corr == pytest.approx(1.0, abs=0.001)


# ============================================================
# InventoryAnalyzer — core load behaviour
# ============================================================

def test_inventory_analyzer_load_valid():
    analyzer = InventoryAnalyzer()
    analyzer.load_records([{
        "id": "REC-000001", "name": "Test Item", "category": "electronics",
        "price": "$99.99", "quantity": "5", "timestamp": "2024-06-01 12:00:00",
        "warehouse": "WH-EAST", "sku": "EL-010001", "supplier": "Acme Corp",
    }])
    assert len(analyzer.records) == 1
    assert len(analyzer.errors) == 0


def test_inventory_analyzer_load_bad_row_captured():
    analyzer = InventoryAnalyzer()
    analyzer.load_records([{
        "id": "REC-BAD", "name": "X", "category": "invalid_category",
        "price": "$10.00", "quantity": "1", "timestamp": "2024-01-01",
        "warehouse": "WH-EAST", "sku": "EL-010001", "supplier": "Acme Corp",
    }])
    assert len(analyzer.records) == 0
    assert len(analyzer.errors) == 1


def test_inventory_analyzer_category_index():
    analyzer = InventoryAnalyzer()
    analyzer.load_records([{
        "id": "REC-000001", "name": "Test Item", "category": "books",
        "price": "$15.00", "quantity": "3", "timestamp": "2024-06-01",
        "warehouse": "WH-WEST", "sku": "BK-010001", "supplier": "GlobalTech",
    }])
    assert "books" in analyzer.category_index


def test_inventory_analyzer_get_category_summary():
    analyzer = InventoryAnalyzer()
    analyzer.load_records([{
        "id": "REC-000001", "name": "Test Item", "category": "health",
        "price": "$34.99", "quantity": "10", "timestamp": "2024-03-15",
        "warehouse": "WH-NORTH", "sku": "HL-010001", "supplier": "QualityFirst",
    }])
    summary = analyzer.get_category_summary()
    assert "health" in summary
    assert summary["health"]["record_count"] == 1


def test_inventory_analyzer_no_records_raises():
    analyzer = InventoryAnalyzer()
    with pytest.raises(RuntimeError, match="No records loaded"):
        analyzer.get_category_summary()


# ============================================================
# generate_report — exposes the intentional IndexError bug
# (accessing self.errors[0] when self.errors is empty)
# ============================================================

def test_generate_report_clean_data():
    """
    When all records are valid (zero errors), generate_report() hits the
    else-branch and crashes with IndexError: list index out of range.
    OpsGuard must detect this crash and produce a fix that removes the
    bad index access.
    """
    analyzer = InventoryAnalyzer()
    analyzer.load_records([{
        "id": "REC-000001", "name": "Clean Item", "category": "furniture",
        "price": "$599.00", "quantity": "2", "timestamp": "2024-06-01 10:00:00",
        "warehouse": "WH-CENTRAL", "sku": "FR-010001", "supplier": "CoreMaterials",
    }])
    # This must NOT raise — if it does, the bug is present
    report = analyzer.generate_report()
    assert report["error_summary"]["count"] == 0
