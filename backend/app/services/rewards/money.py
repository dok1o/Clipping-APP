"""Content Rewards domain: money helpers (CONTRACTS CR-0.4).

- Python money values are `Decimal` ONLY; floats are rejected (audit rule).
- All amounts NUMERIC(14,2), CPM rates NUMERIC(10,4), percents NUMERIC(5,2).
- Intermediate math keeps full Decimal precision; quantizing to cents with
  ROUND_HALF_EVEN happens ONLY at write boundaries (expected/actual payout, fee).
"""
from decimal import Decimal, InvalidOperation, ROUND_HALF_EVEN

CENT = Decimal("0.01")


class MoneyError(ValueError):
    """Raised when a money value cannot be represented exactly as Decimal."""


def to_decimal(value: Decimal | int | str, *, field: str = "money") -> Decimal:
    """Convert a money input to Decimal without ever going through float math.

    Floats are rejected: JSON parsers that yield floats must be fed through
    Pydantic Decimal fields (pydantic-core parses JSON numbers into Decimal
    directly); raw floats arriving here are a bug.
    """
    if isinstance(value, float):
        raise MoneyError(f"{field}: float is not allowed for money; use Decimal or str")
    if isinstance(value, Decimal):
        return value
    if isinstance(value, bool):
        raise MoneyError(f"{field}: bool is not money")
    if isinstance(value, int):
        return Decimal(value)
    if isinstance(value, str):
        try:
            return Decimal(value.strip())
        except InvalidOperation as exc:
            raise MoneyError(f"{field}: invalid decimal string {value!r}") from exc
    raise MoneyError(f"{field}: unsupported money type {type(value).__name__}")


def quantize_money(value: Decimal | int | str) -> Decimal:
    """Write-boundary rounding: to cents, ROUND_HALF_EVEN (banker's)."""
    return to_decimal(value).quantize(CENT, rounding=ROUND_HALF_EVEN)


def compute_fee(gross: Decimal, fee_percent: Decimal) -> Decimal:
    """Creator fee for a gross amount (full precision; quantize at write boundary)."""
    gross = to_decimal(gross, field="gross")
    fee_percent = to_decimal(fee_percent, field="fee_percent")
    return gross * fee_percent / Decimal(100)


def compute_net(gross: Decimal, fee_amount: Decimal) -> Decimal:
    """Net = gross - fee (full precision; quantize at write boundary)."""
    gross = to_decimal(gross, field="gross")
    fee_amount = to_decimal(fee_amount, field="fee_amount")
    return gross - fee_amount


def terms_content_hash(terms: dict) -> str:
    """SHA-256 of the canonical JSON of a terms payload (immutability control).

    Canonical form: sorted keys, compact separators, ensure_ascii=False;
    money values MUST be passed as str/int/Decimal-rendered strings (never floats).
    """
    import hashlib
    import json

    def _canon(obj):
        if isinstance(obj, Decimal):
            return format(obj.normalize(), "f")
        if isinstance(obj, dict):
            return {k: _canon(v) for k, v in sorted(obj.items())}
        if isinstance(obj, (list, tuple)):
            return [_canon(v) for v in obj]
        return obj

    payload = json.dumps(_canon(terms), sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()
