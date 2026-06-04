# -*- coding: utf-8 -*-
"""Pure-function comparator for Golden Test step output.

Compares an ``expected`` metrics dict (the reference, loaded from
``golden_expected.json``) against an ``actual`` metrics dict (what the run
produced, loaded from ``golden_output.json``) and returns a structured
report.

This module has no SEAMM dependencies and no I/O of its own, so it can be
unit tested as pure data-in/data-out.

Comparison rules (see NOTES_golden_tests_design.rst for the design):

1. Walk ``expected``; look up the matching node in ``actual``.
2. Fields present in ``actual`` but not in ``expected`` are silently
   ignored (forward compatibility — new metrics never break old tests).
3. Fields present in ``expected`` but missing in ``actual`` are failures.
4. Lists named ``components`` match entries by ``smiles`` (or ``formula``
   if ``smiles`` is null), not by position.
5. Booleans, integers and strings: exact match required.
6. Floats: tolerance-based. Defaults ``rtol = 1e-3``, ``atol = 0.0``.
7. Per-field tolerance overrides via a wrapper::

       "density_g_per_mL": {"value": 1.21, "tol": {"rtol": 0.02}}

8. Lists of numbers: element-wise with the same tolerance rules.
"""

DEFAULT_RTOL = 1.0e-3
DEFAULT_ATOL = 0.0


def compare(expected, actual):
    """Compare two metrics dicts.

    Parameters
    ----------
    expected : dict
        The reference metrics (loaded from ``golden_expected.json``).
    actual : dict
        The metrics produced by the run (loaded from ``golden_output.json``).

    Returns
    -------
    dict
        A report with keys ``passed`` (bool), ``schema_version``,
        ``n_passes``, ``n_failures``, ``summary`` (human-readable string),
        and ``failures`` (list of per-failure dicts).
    """
    state = _State()
    _walk(expected, actual, path="", state=state)

    n_passes = state.n_passes
    n_failures = len(state.failures)
    passed = n_failures == 0
    if passed:
        summary = "{n} pass{s}".format(n=n_passes, s="" if n_passes == 1 else "es")
    else:
        summary = "{nf} failure{sf}, {np} pass{sp}".format(
            nf=n_failures,
            sf="" if n_failures == 1 else "s",
            np=n_passes,
            sp="" if n_passes == 1 else "es",
        )

    return {
        "passed": passed,
        "schema_version": (
            expected.get("schema_version") if isinstance(expected, dict) else None
        ),
        "n_passes": n_passes,
        "n_failures": n_failures,
        "summary": summary,
        "failures": state.failures,
    }


# ---------------------------------------------------------------------------
# Internals
# ---------------------------------------------------------------------------


class _State(object):
    """Mutable accumulator threaded through the recursive walk."""

    def __init__(self):
        self.n_passes = 0
        self.failures = []

    def pass_(self):
        self.n_passes += 1

    def fail(self, path, expected, actual, reason, tolerance=None):
        entry = {
            "path": path,
            "expected": expected,
            "actual": actual,
            "reason": reason,
        }
        if tolerance is not None:
            entry["tolerance"] = tolerance
            try:
                entry["abs_diff"] = abs(actual - expected)
                if expected != 0:
                    entry["rel_diff"] = abs(actual - expected) / abs(expected)
            except (TypeError, ValueError):
                pass
        self.failures.append(entry)


def _is_tol_wrapper(d):
    """A tolerance wrapper is a dict ``{"value": X, "tol": {...}}``.

    We require ``tol`` to be present to identify the wrapper unambiguously;
    a bare ``{"value": X}`` is not a wrapper (the user would just write X
    directly).
    """
    return (
        isinstance(d, dict)
        and "value" in d
        and "tol" in d
        and set(d.keys()) <= {"value", "tol"}
    )


def _walk(expected, actual, path, state):
    """Recurse over ``expected`` and compare matching nodes in ``actual``."""
    # Tolerance wrapper unwraps to a leaf comparison with overridden tol.
    if _is_tol_wrapper(expected):
        _compare_leaf(expected["value"], actual, path, state, tol=expected["tol"])
        return

    if isinstance(expected, dict):
        if not isinstance(actual, dict):
            state.fail(
                path or "<root>",
                expected,
                actual,
                reason="expected dict, got {}".format(type(actual).__name__),
            )
            return
        for key, sub_expected in expected.items():
            sub_path = "{}.{}".format(path, key) if path else key
            if key not in actual:
                state.fail(
                    sub_path,
                    sub_expected,
                    None,
                    reason="missing in actual",
                )
                continue
            _walk(sub_expected, actual[key], sub_path, state)
        return

    if isinstance(expected, list):
        # Special case: components are matched by SMILES (or formula).
        # We identify it positionally: the parent path ends in "components".
        if path.endswith("components"):
            _compare_components(expected, actual, path, state)
            return

        if not isinstance(actual, list):
            state.fail(
                path,
                expected,
                actual,
                reason="expected list, got {}".format(type(actual).__name__),
            )
            return
        if len(expected) != len(actual):
            state.fail(
                path,
                "length {}".format(len(expected)),
                "length {}".format(len(actual)),
                reason="list length mismatch",
            )
            return
        for i, (e, a) in enumerate(zip(expected, actual)):
            _walk(e, a, "{}[{}]".format(path, i), state)
        return

    # Leaf: scalar comparison.
    _compare_leaf(expected, actual, path, state, tol=None)


def _compare_components(expected, actual, path, state):
    """Match expected components to actual by SMILES (fallback: formula).

    Each entry in ``expected`` is looked up in ``actual`` by its identifier;
    matched pairs are then walked field by field. An expected component that
    has no match in ``actual`` is a failure. Extra components in ``actual``
    are ignored (forward compatibility).
    """
    if not isinstance(actual, list):
        state.fail(
            path,
            expected,
            actual,
            reason="expected list of components, got {}".format(type(actual).__name__),
        )
        return

    actual_by_id = {}
    for entry in actual:
        if not isinstance(entry, dict):
            continue
        ident = entry.get("smiles") or entry.get("formula")
        if ident is not None:
            actual_by_id[ident] = entry

    for entry in expected:
        if not isinstance(entry, dict):
            state.fail(
                path,
                entry,
                None,
                reason="component entry is not a dict",
            )
            continue
        ident = entry.get("smiles") or entry.get("formula")
        if ident is None:
            state.fail(
                path,
                entry,
                None,
                reason="component entry has neither 'smiles' nor 'formula'",
            )
            continue
        if ident not in actual_by_id:
            state.fail(
                "{}[id={}]".format(path, ident),
                entry,
                None,
                reason="component missing in actual",
            )
            continue
        _walk(entry, actual_by_id[ident], "{}[id={}]".format(path, ident), state)


def _compare_leaf(expected, actual, path, state, tol):
    """Compare two scalar values with type-appropriate semantics."""
    # None: exact match (None means "explicitly absent").
    if expected is None:
        if actual is None:
            state.pass_()
        else:
            state.fail(path, expected, actual, reason="expected None")
        return

    # Bool first, since bool is a subclass of int in Python.
    if isinstance(expected, bool):
        if isinstance(actual, bool) and expected == actual:
            state.pass_()
        else:
            state.fail(path, expected, actual, reason="boolean mismatch")
        return

    if isinstance(expected, int):
        if (
            isinstance(actual, int)
            and not isinstance(actual, bool)
            and expected == actual
        ):
            state.pass_()
        else:
            state.fail(path, expected, actual, reason="integer mismatch")
        return

    if isinstance(expected, str):
        if isinstance(actual, str) and expected == actual:
            state.pass_()
        else:
            state.fail(path, expected, actual, reason="string mismatch")
        return

    if isinstance(expected, float):
        if not isinstance(actual, (int, float)) or isinstance(actual, bool):
            state.fail(path, expected, actual, reason="numeric type mismatch")
            return
        tol_dict = tol if tol is not None else {}
        rtol = tol_dict.get("rtol", DEFAULT_RTOL)
        atol = tol_dict.get("atol", DEFAULT_ATOL)
        diff = abs(float(actual) - float(expected))
        tolerance = atol + rtol * abs(float(expected))
        if diff <= tolerance:
            state.pass_()
        else:
            state.fail(
                path,
                expected,
                actual,
                reason="float mismatch (diff {:g} > tolerance {:g})".format(
                    diff, tolerance
                ),
                tolerance={"rtol": rtol, "atol": atol},
            )
        return

    # Fallback: equality.
    if expected == actual:
        state.pass_()
    else:
        state.fail(
            path,
            expected,
            actual,
            reason="value mismatch (type {})".format(type(expected).__name__),
        )
