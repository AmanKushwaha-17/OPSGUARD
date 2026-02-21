from app import parse_input, safe_divide, compute


def test_parse_input_valid():
    assert parse_input("42") == 42


def test_parse_input_zero():
    assert parse_input("0") == 0


def test_safe_divide_basic():
    assert safe_divide(10, 2) == 5.0


def test_safe_divide_float():
    assert safe_divide(7, 2) == 3.5


def test_compute_clean_data():
    result = compute(["10", "20", "30"])
    assert result == 20.0
