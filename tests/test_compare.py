# -*- coding: utf-8 -*-
"""Unit tests for ``golden_step.compare``.

These tests are pure data-in/data-out: no SEAMM, no molsystem, no RDKit.
They exercise the comparator against the eight cases enumerated in the
design notes (NOTES_golden_tests_design.rst).
"""

import copy

import pytest

from golden_step.compare import compare

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def baseline():
    """A minimal-but-realistic metrics dict shaped like the 1 M LiPF6 case.

    Two components rather than four, so the assertions stay readable; the
    behaviour the comparator implements is independent of how many
    components are in the list.
    """
    return {
        "schema_version": 1,
        "step": "golden",
        "system": {
            "periodic": True,
            "dimensionality": 3,
            "n_atoms": 152,
            "charge": 0,
            "cell": {"a": 33.02, "volume": 35993.0},
        },
        "components": [
            {"smiles": "[Li+]", "count": 22, "mass_g_per_mol": 6.941},
            {"smiles": "O=C1OCCO1", "count": 130, "mass_g_per_mol": 88.062},
        ],
        "derived": {
            "density_g_per_mL": 1.210,
            "molarities_M": [1.015, 5.997],
        },
    }


# ---------------------------------------------------------------------------
# The eight cases
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_case_1_identical(baseline):
    """Identical dicts: every field passes, no failures."""
    actual = copy.deepcopy(baseline)
    report = compare(baseline, actual)

    assert report["passed"] is True
    assert report["n_failures"] == 0
    assert report["failures"] == []
    assert report["n_passes"] > 0
    assert report["schema_version"] == 1


@pytest.mark.unit
def test_case_2_float_within_default_tolerance(baseline):
    """A float that differs by less than the default rtol (1e-3) passes."""
    actual = copy.deepcopy(baseline)
    # 1.210 -> 1.2105 is 4e-4 relative, well inside rtol=1e-3.
    actual["derived"]["density_g_per_mL"] = 1.2105

    report = compare(baseline, actual)

    assert report["passed"] is True
    assert report["n_failures"] == 0


@pytest.mark.unit
def test_case_3_float_outside_default_tolerance(baseline):
    """A float that differs by more than the default rtol fails, and the
    failure entry names the offending path and records the tolerance used.
    """
    actual = copy.deepcopy(baseline)
    # 1.210 -> 1.220 is ~8e-3 relative, well outside rtol=1e-3.
    actual["derived"]["density_g_per_mL"] = 1.220

    report = compare(baseline, actual)

    assert report["passed"] is False
    assert report["n_failures"] == 1

    failure = report["failures"][0]
    assert failure["path"] == "derived.density_g_per_mL"
    assert failure["expected"] == 1.210
    assert failure["actual"] == 1.220
    assert failure["tolerance"] == {"rtol": 1.0e-3, "atol": 0.0}
    assert "abs_diff" in failure
    assert "rel_diff" in failure


@pytest.mark.unit
def test_case_4_component_reorder_and_extra_in_actual(baseline):
    """Components are matched by SMILES, not position; extra components in
    ``actual`` are ignored (forward compatibility)."""
    actual = copy.deepcopy(baseline)
    actual["components"] = list(reversed(actual["components"]))
    actual["components"].append({"smiles": "CCO", "count": 5, "mass_g_per_mol": 46.07})

    report = compare(baseline, actual)

    assert report["passed"] is True
    assert report["n_failures"] == 0


@pytest.mark.unit
def test_case_5_component_missing_in_actual(baseline):
    """If a component required by ``expected`` is absent from ``actual``,
    the comparator reports a failure naming the missing identifier."""
    actual = copy.deepcopy(baseline)
    # Drop the EC component.
    actual["components"] = [
        c for c in actual["components"] if c["smiles"] != "O=C1OCCO1"
    ]
    # Also drop the corresponding molarity entry so the array length still
    # matches; otherwise this test would conflate two failures.
    actual["derived"]["molarities_M"] = [actual["derived"]["molarities_M"][0]]

    report = compare(baseline, actual)

    assert report["passed"] is False
    failure_paths = [f["path"] for f in report["failures"]]
    assert "components[id=O=C1OCCO1]" in failure_paths


@pytest.mark.unit
def test_case_6_tolerance_wrapper_override(baseline):
    """A ``{"value": X, "tol": {...}}`` wrapper on a field in ``expected``
    overrides the default tolerance for that field only."""
    expected = copy.deepcopy(baseline)
    expected["derived"]["density_g_per_mL"] = {
        "value": 1.210,
        "tol": {"rtol": 0.05},
    }

    actual = copy.deepcopy(baseline)
    # ~1.7% off: would fail default rtol=1e-3, passes the 5% override.
    actual["derived"]["density_g_per_mL"] = 1.230

    report = compare(expected, actual)

    assert report["passed"] is True
    assert report["n_failures"] == 0


@pytest.mark.unit
def test_case_7_integer_must_match_exactly(baseline):
    """Integer fields (counts, charge, atom counts) require exact match;
    no tolerance applies."""
    actual = copy.deepcopy(baseline)
    actual["components"][0]["count"] = 23  # was 22

    report = compare(baseline, actual)

    assert report["passed"] is False
    assert report["n_failures"] == 1

    failure = report["failures"][0]
    assert failure["path"] == "components[id=[Li+]].count"
    assert failure["expected"] == 22
    assert failure["actual"] == 23
    # No tolerance is reported for integer mismatches.
    assert "tolerance" not in failure


@pytest.mark.unit
def test_case_8_array_elementwise_tolerance(baseline):
    """Lists of floats compare element-wise with the same tolerance rules
    that apply to scalar floats."""
    actual = copy.deepcopy(baseline)
    # Both elements within default rtol=1e-3 (~1e-4 relative).
    actual["derived"]["molarities_M"] = [1.0151, 5.9970001]

    report = compare(baseline, actual)

    assert report["passed"] is True
    assert report["n_failures"] == 0

    # Confirm the converse: bumping one element outside tolerance fails on
    # that element specifically, not the whole array.
    actual["derived"]["molarities_M"] = [1.0151, 6.5]  # second element 8% off
    report = compare(baseline, actual)

    assert report["passed"] is False
    assert report["n_failures"] == 1
    assert report["failures"][0]["path"] == "derived.molarities_M[1]"
