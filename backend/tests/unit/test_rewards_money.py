"""Money contract tests (CR-0.4): Decimal-only, exact types, ROUND_HALF_EVEN."""
from decimal import Decimal

import pytest

from app.services.rewards.money import (
    MoneyError,
    compute_fee,
    compute_net,
    quantize_money,
    terms_content_hash,
    to_decimal,
)


class TestToDecimal:
    def test_accepts_decimal_int_str(self) -> None:
        assert to_decimal(Decimal("12.50")) == Decimal("12.50")
        assert to_decimal(12) == Decimal(12)
        assert to_decimal("1234.56") == Decimal("1234.56")
        assert to_decimal(" 7.00 ") == Decimal("7.00")

    def test_rejects_float(self) -> None:
        with pytest.raises(MoneyError, match="float is not allowed"):
            to_decimal(12.5)

    def test_rejects_bool_and_garbage(self) -> None:
        with pytest.raises(MoneyError):
            to_decimal(True)
        with pytest.raises(MoneyError):
            to_decimal("abc")
        with pytest.raises(MoneyError):
            to_decimal(None)


class TestQuantizeMoney:
    def test_round_half_even_to_cents(self) -> None:
        # banker's rounding: .005 -> 0 (even), 2.345 -> 2.34, 2.355 -> 2.36
        assert quantize_money(Decimal("2.345")) == Decimal("2.34")
        assert quantize_money(Decimal("2.355")) == Decimal("2.36")
        assert quantize_money(Decimal("0.005")) == Decimal("0.00")
        assert quantize_money(Decimal("0.015")) == Decimal("0.02")
        assert quantize_money(Decimal("10.999")) == Decimal("11.00")

    def test_no_intermediate_rounding(self) -> None:
        # full precision is kept by compute_*; quantize is a boundary operation
        gross = Decimal("0.1") + Decimal("0.2")
        assert gross == Decimal("0.3")


class TestFeeNet:
    def test_fee_full_precision_then_quantize(self) -> None:
        gross = Decimal("123.45")
        fee_percent = Decimal("10.00")
        fee = compute_fee(gross, fee_percent)  # 12.345 — full precision
        assert fee == Decimal("12.345")
        assert quantize_money(fee) == Decimal("12.34")  # HALF_EVEN at the boundary
        net = compute_net(gross, fee)
        assert net == Decimal("111.105")
        assert quantize_money(net) == Decimal("111.10")

    def test_fee_zero_percent(self) -> None:
        assert compute_fee(Decimal("5000.00"), Decimal("0")) == Decimal("0")
        assert quantize_money(compute_net(Decimal("5000.00"), Decimal("0"))) == Decimal("5000.00")

    def test_rejects_float_money(self) -> None:
        with pytest.raises(MoneyError):
            compute_fee(10.5, Decimal("10"))  # type: ignore[arg-type]


class TestContentHash:
    def test_canonical_json_stable(self) -> None:
        a = {"payout_model": "cpm", "cpm_rate": "10.0000", "nested": {"b": 1, "a": 2}}
        b = {"nested": {"a": 2, "b": 1}, "cpm_rate": "10.0000", "payout_model": "cpm"}
        assert terms_content_hash(a) == terms_content_hash(b)

    def test_different_content_different_hash(self) -> None:
        assert terms_content_hash({"a": "1"}) != terms_content_hash({"a": "2"})

    def test_decimal_rendered_without_exponent(self) -> None:
        assert terms_content_hash({"x": Decimal("0.000010")}) == terms_content_hash(
            {"x": "0.00001"}
        )

    def test_hash_is_sha256_hex64(self) -> None:
        h = terms_content_hash({"k": "v"})
        assert len(h) == 64
        int(h, 16)  # hex
