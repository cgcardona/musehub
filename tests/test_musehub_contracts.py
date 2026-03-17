"""Unit tests for musehub/contracts/hash_utils.py.

The contract hashing module enforces deterministic SHA-256 fingerprinting of
music generation contracts.  These tests lock down:

- canonical_contract_dict field exclusions
- _normalize_value handling of nested types
- hash stability across runs
- contract_hash exclusion prevents circular dependency
"""
from __future__ import annotations

import dataclasses
import hashlib
import json

import pytest

from musehub.contracts.hash_utils import (
    _HASH_EXCLUDED_FIELDS,
    _normalize_value,
    canonical_contract_dict,
)


# ---------------------------------------------------------------------------
# Minimal dataclass fixtures
# ---------------------------------------------------------------------------

@dataclasses.dataclass(frozen=True)
class SimpleContract:
    tempo: int = 120
    key: str = "C major"
    # advisory fields that should be excluded from hashes
    contract_hash: str = ""
    contract_version: str = "1.0"
    region_name: str = ""


@dataclasses.dataclass(frozen=True)
class NestedContract:
    name: str = "outer"
    inner: SimpleContract = dataclasses.field(default_factory=SimpleContract)


# ---------------------------------------------------------------------------
# _HASH_EXCLUDED_FIELDS
# ---------------------------------------------------------------------------

class TestHashExcludedFields:
    def test_advisory_fields_excluded(self) -> None:
        for field in (
            "contract_hash",
            "parent_contract_hash",
            "contract_version",
            "execution_hash",
            "l2_generate_prompt",
            "region_name",
            "gm_guidance",
            "assigned_color",
            "existing_track_id",
        ):
            assert field in _HASH_EXCLUDED_FIELDS, f"{field!r} should be excluded"


# ---------------------------------------------------------------------------
# _normalize_value
# ---------------------------------------------------------------------------

class TestNormalizeValue:
    def test_primitives_passthrough(self) -> None:
        assert _normalize_value(42) == 42
        assert _normalize_value(3.14) == 3.14
        assert _normalize_value("hello") == "hello"
        assert _normalize_value(True) is True
        assert _normalize_value(None) is None

    def test_list_normalized(self) -> None:
        result = _normalize_value([3, 1, 2])
        assert result == [3, 1, 2]

    def test_tuple_becomes_list(self) -> None:
        result = _normalize_value((1, 2, 3))
        assert result == [1, 2, 3]

    def test_dict_keys_sorted(self) -> None:
        result = _normalize_value({"z": 1, "a": 2})
        assert list(result.keys()) == ["a", "z"]  # type: ignore[union-attr]

    def test_dataclass_converted_to_dict(self) -> None:
        obj = SimpleContract(tempo=90, key="D minor")
        result = _normalize_value(obj)
        assert isinstance(result, dict)
        assert "tempo" in result
        assert "key" in result
        # Excluded fields should not appear
        assert "contract_hash" not in result

    def test_unknown_type_stringified(self) -> None:
        class Weird:
            def __str__(self) -> str:
                return "weird-value"
        result = _normalize_value(Weird())
        assert result == "weird-value"


# ---------------------------------------------------------------------------
# canonical_contract_dict
# ---------------------------------------------------------------------------

class TestCanonicalContractDict:
    def test_excluded_fields_absent(self) -> None:
        obj = SimpleContract(tempo=120, key="G major")
        d = canonical_contract_dict(obj)
        for excluded in _HASH_EXCLUDED_FIELDS:
            assert excluded not in d, f"{excluded!r} should not appear in canonical dict"

    def test_included_fields_present(self) -> None:
        obj = SimpleContract(tempo=120, key="A minor")
        d = canonical_contract_dict(obj)
        assert "tempo" in d
        assert "key" in d
        assert d["tempo"] == 120
        assert d["key"] == "A minor"

    def test_deterministic_across_calls(self) -> None:
        obj = SimpleContract(tempo=100, key="F major")
        d1 = canonical_contract_dict(obj)
        d2 = canonical_contract_dict(obj)
        assert d1 == d2

    def test_same_data_same_json(self) -> None:
        obj = SimpleContract(tempo=140, key="B♭ major")
        d = canonical_contract_dict(obj)
        j1 = json.dumps(d, sort_keys=True)
        j2 = json.dumps(canonical_contract_dict(obj), sort_keys=True)
        assert j1 == j2

    def test_nested_dataclass_recursed(self) -> None:
        obj = NestedContract(name="outer", inner=SimpleContract(tempo=70))
        d = canonical_contract_dict(obj)
        assert "name" in d
        assert "inner" in d
        assert isinstance(d["inner"], dict)
        assert d["inner"]["tempo"] == 70  # type: ignore[index]
        assert "contract_hash" not in d.get("inner", {})  # type: ignore[operator]

    def test_different_values_different_hash(self) -> None:
        obj1 = SimpleContract(tempo=120)
        obj2 = SimpleContract(tempo=140)
        d1 = canonical_contract_dict(obj1)
        d2 = canonical_contract_dict(obj2)
        j1 = json.dumps(d1, sort_keys=True)
        j2 = json.dumps(d2, sort_keys=True)
        h1 = hashlib.sha256(j1.encode()).hexdigest()
        h2 = hashlib.sha256(j2.encode()).hexdigest()
        assert h1 != h2
