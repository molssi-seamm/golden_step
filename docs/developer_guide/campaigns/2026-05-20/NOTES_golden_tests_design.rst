==============================================
 Golden Tests for SEAMM Plug-ins: Design Notes
==============================================

:Status: Draft
:Date: 2026-05-20
:Scope: Initial focus on ``packmol_step``; intended to generalize.


Purpose
=======

Two related but distinct goals share infrastructure but are managed
separately:

1. **Golden tests.** A small, curated set of (flowchart, reference output)
   pairs that runs in CI and catches regressions. Each test is a maintenance
   commitment.

2. **ML training corpus.** A larger set of (natural-language query, flowchart)
   pairs used to train a model that maps queries to flowcharts. Every example
   must be *correct* (its flowchart actually does what the query says), but
   not every example becomes a permanent golden test.

The golden test set anchors correctness. The training corpus reuses the
same flowchart format, the same Golden Test step, and the same comparator
for spot-checking, but is regenerable rather than maintained-in-place when
implementations drift.

This document covers the golden test infrastructure. The training corpus
workflow is a future extension.


Scope plan
==========

Build in this order:

1. The Golden Test step (generic, plug-in agnostic).
2. One Packmol golden test end-to-end (water box).
3. The comparator library (used by both the step and the pytest harness).
4. The Packmol corpus: ~15 cases covering the feature matrix, plus one
   ``From SMILES`` + Packmol case (exercises ``source: "configuration"``)
   and one forcefield-assignment case.
5. Apply to one more plug-in (likely MOPAC) to discover where the schema
   actually needs to flex. Expect one schema refinement here.
6. ML training corpus workflow.


Directory layout
================

Tests live with the plug-in they exercise. For ``packmol_step``::

    packmol_step/
        tests/
            golden/
                water_box/
                    query.txt              # one-paragraph NL description
                    flowchart.flow         # the SEAMM flowchart
                    golden_expected.json   # reference metrics + tolerances
                    inputs/                # structures, forcefields, etc.
                    README.rst             # what is being tested, by whom, when
                lipf6_ec_dmc_1M/
                    ...
                test_golden.py             # pytest entry that walks cases

The pytest entry is one file per plug-in; it iterates the ``golden/``
subdirectories, runs each flowchart, and compares.

Later, when flowcharts span multiple plug-ins (real workflows), the same
layout applies to whichever repository owns the integration test. The
case may contain several Golden Test steps in the flowchart, or just one
at the end; either is fine.


The Golden Test step
====================

Name
----

- Python package: ``golden_step``
- User-facing name in the SEAMM GUI: "Golden Test"
- Files written:

  - ``golden_output.json`` — what the step actually observed (always)
  - ``golden_result.json`` — comparison report (verify mode only)

The reference file the test author commits is ``golden_expected.json``.
All three filenames share the ``golden_`` prefix so they sort together
in a directory listing and their purpose is obvious to developers.

Picking "Golden Test" as the GUI name over "Metrics" avoids confusion
with performance metrics, telemetry, or property metrics.

Modes
-----

The step has one parameter ``mode`` with three values:

``record``
    Compute the metrics for the current system + selected properties.
    Write ``golden_output.json`` to the job directory. Always succeed
    unless a metric cannot be computed.

``verify``
    Do everything ``record`` does. Then load ``golden_expected.json``
    from the path given by the ``expected file`` parameter (default:
    ``golden_expected.json`` in the flowchart directory). Compare.
    Write a diff report to ``golden_result.json``. Optionally fail the
    flowchart if the ``on failure`` parameter is set to ``stop``.

``skip``
    Do nothing. Useful for keeping the step in a flowchart that is
    being run for non-test purposes.

Behavior in verify mode is identical between in-flowchart and
out-of-flowchart use: in both cases the step writes ``golden_output.json``
and the comparator (a library) consumes it. The only difference is who
calls the comparator (the step itself vs. the pytest harness).

Parameters
----------

- ``mode``: one of ``record``, ``verify``, ``skip``. Default ``record``.
- ``expected file``: path to ``golden_expected.json``. Default
  ``golden_expected.json`` in the flowchart directory.
- ``output file``: path for ``golden_output.json``. Default
  ``golden_output.json`` in the job directory.
- ``include``: list of section names to include in metrics. Default all
  of ``system``, ``components``, ``derived``.
- ``properties``: list of named properties from the SEAMM property
  database to include in ``step_specific``. Default empty.
- ``on failure``: one of ``continue`` (default), ``stop``. Whether a
  verify failure halts the flowchart.

SMILES policy
-------------

- All SMILES in ``golden_*.json`` are *isomeric, canonical* SMILES
  produced by RDKit
  (``Chem.MolToSmiles(mol, isomericSmiles=True, canonical=True)``).
- The Golden Test step canonicalizes internally on output, regardless of
  what the rest of SEAMM produced. This keeps the test artifact stable
  even if SEAMM's default SMILES output changes.
- Whether to change SEAMM's *general* default to canonical SMILES is a
  separate question; it does not block golden tests.
- For systems where SMILES is unreliable (organometallics, some
  zwitterions) or undefined (crystals, periodic non-molecular systems),
  the ``smiles`` field is ``null`` and identification falls back to
  ``formula`` plus any other distinguishing fields (spacegroup, cell
  parameters, residue name).


Metrics schema
==============

Top-level
---------

Every ``golden_output.json`` has these top-level keys::

    {
      "schema_version": 1,
      "step": "<plugin name, e.g. 'packmol'>",
      "system": { ... },
      "components": [ ... ],
      "derived": { ... },
      "step_specific": { ... }    # optional
    }

``schema_version`` is incremented when a backwards-incompatible change
is made. The comparator dispatches on this field.

``system``
----------

Properties of the resulting system as a whole::

    "system": {
      "periodic": true,
      "dimensionality": 3,
      "n_atoms": 3000,
      "n_bonds": 2954,
      "n_residues": 301,
      "charge": 0,
      "spin_multiplicity": 1,
      "cell": {
        "a": 33.02, "b": 33.02, "c": 33.02,
        "alpha": 90.0, "beta": 90.0, "gamma": 90.0,
        "volume": 35993.0,
        "lengths_units": "Å",
        "angles_units": "degree",
        "volume_units": "Å^3"
      }
    }

For non-periodic systems, ``cell`` is replaced by ``bounding_box`` (a/b/c
only, no angles). For 0D systems (a single cluster), this still gives
something useful.

``components``
--------------

A list, one entry per chemically distinct component::

    "components": [
      {
        "smiles": "[Li+]",
        "formula": "Li",
        "count": 22,
        "mass_g_per_mol": 6.941,
        "role": "fluid"
      },
      ...
    ]

Order in the list matters only for human readability; the comparator
matches entries by ``smiles`` (or ``formula`` if ``smiles`` is null).
A given identifier must appear exactly once. If two components in
``golden_expected.json`` have the same SMILES, that is an authoring
error; the comparator should reject it.

``role`` mirrors what the originating step called the component:
``solute``, ``fluid``, ``solvent``, ``solid``, etc. Plug-ins may extend
the vocabulary; the comparator treats it as a string.

``derived``
-----------

Aggregate quantities computable from ``system`` + ``components``::

    "derived": {
      "total_mass_g_per_mol": 26229.8,
      "density_g_per_mL": 1.210,
      "molar_ratios":   [1.0,    1.0,    5.909, 5.773],
      "mole_fractions": [0.0731, 0.0731, 0.4319, 0.4219],
      "wt_fractions":   [0.0582, 0.1216, 0.4365, 0.4361],
      "molarities_M":   [1.015,  1.015,  5.997,  5.859]
    }

For non-periodic or non-fluid systems, the concentration-like fields are
omitted (``null`` is reserved for "data missing"; absence means "not
applicable").

The arrays in ``derived`` are aligned with the order of ``components``,
which is the only place positional ordering matters. The comparator
preserves the SMILES-to-index mapping when comparing.

``step_specific``
-----------------

A free-form dict for plug-in-specific quantities pulled from the
property database (or computed by the plug-in directly)::

    "step_specific": {
      "dimensions_mode": "calculated from the density",
      "fluid_amount_mode": "rounding this number of atoms",
      "requested_density_g_per_mL": 1.21,
      "requested_n_atoms": 3000
    }

Keys here are not part of the schema; they're whatever the test author
asked for via the ``properties`` parameter.


Comparator
==========

A standalone Python library (``golden_step.compare`` or its own package,
``seamm-golden-compare``), called by:

- the Golden Test step itself in verify mode,
- the pytest harness for out-of-flowchart testing,
- a CLI for regeneration and ad-hoc comparison.

Comparison rules
----------------

1. Walk ``expected``, looking up the matching node in ``actual``.
2. Fields present in ``actual`` but not in ``expected`` are silently
   ignored. **Forward compatibility:** new metrics never break old
   tests.
3. Fields present in ``expected`` but not in ``actual`` are failures.
4. Lists in ``components`` match by ``smiles`` (or ``formula``), not
   position. Order differences are not failures.
5. Integers, booleans, and strings: exact match required.
6. Floats: tolerance-based. Defaults: ``rtol = 1e-3``, ``atol = 0.0``.
7. Per-field tolerance overrides via a wrapper::

       "density_g_per_mL": {"value": 1.210, "tol": {"rtol": 0.02}}

   A bare number uses defaults; the wrapper form overrides.
8. Arrays of floats: element-wise, with the same tolerance rules.

Failure report
--------------

``golden_result.json`` (written in verify mode) looks like::

    {
      "passed": false,
      "schema_version": 1,
      "summary": "2 failures, 47 passes",
      "failures": [
        {
          "path": "system.cell.volume",
          "expected": 35993.0,
          "actual": 37200.5,
          "tolerance": {"rtol": 0.001},
          "abs_diff": 1207.5,
          "rel_diff": 0.0335
        },
        ...
      ]
    }

For pytest, the harness reads this file and converts to assertion
errors with the same content.


In-flowchart vs. out-of-flowchart testing
=========================================

Both work the same way under the hood; the difference is who initiates
the run.

**In-flowchart (verify mode in the Golden Test step):** User opens the
SEAMM GUI, loads ``flowchart.flow``, runs it. The Golden Test step at
the end reports pass/fail in the GUI. Useful for: a user trying a test
locally, manual debugging, demonstrating a case.

**Out-of-flowchart (pytest harness):** ``pytest tests/`` walks the
``golden/`` tree, runs each flowchart programmatically through the
SEAMM job runner, reads ``golden_output.json``, and runs the comparator
directly. The Golden Test step can be in ``record`` mode in this path
(the harness owns the comparison) or ``verify`` mode (the harness just
checks the result file). Recommended: ``record`` mode in CI, so the
harness has full control.

The flowchart files in ``golden/`` should be authored with the Golden
Test step in ``verify`` mode by default, so a user running the flowchart
in the GUI gets pass/fail immediately. The pytest harness can override
the mode at run time if it wants.

Harness pattern
---------------

The pytest harness reuses the pattern already established by
``packmol_step/tests/test_flowcharts.py``: ``seamm_exec.run`` is called
with ``sys.argv`` monkey-patched to point at the flowchart, and with a
``tmp_path`` working directory. The golden version adds case staging
(copying ``inputs/`` into ``tmp_path``) and the comparison step::

    import json
    import shutil
    from pathlib import Path

    import pytest
    from seamm_exec import run

    from golden_step.compare import compare

    test_dir = Path(__file__).resolve().parent
    golden_dir = test_dir / "golden"
    cases = sorted(p for p in golden_dir.iterdir() if p.is_dir())


    @pytest.mark.golden
    @pytest.mark.parametrize("case_dir", cases, ids=lambda p: p.name)
    def test_golden(monkeypatch, tmp_path, case_dir):
        flowchart = case_dir / "flowchart.flow"
        if (case_dir / "inputs").is_dir():
            shutil.copytree(case_dir / "inputs", tmp_path / "inputs")

        monkeypatch.setattr(
            "sys.argv",
            ["testing", str(flowchart), "--standalone"],
        )
        run(wdir=str(tmp_path))

        actual = json.loads((tmp_path / "golden_output.json").read_text())
        expected = json.loads((case_dir / "golden_expected.json").read_text())
        report = compare(expected, actual)

        if not report["passed"]:
            (tmp_path / "golden_result.json").write_text(
                json.dumps(report, indent=2)
            )
            pytest.fail(
                report["summary"]
                + "\n"
                + json.dumps(report["failures"], indent=2)
            )

The structure mirrors ``test_flowcharts.py`` deliberately so anyone
familiar with the existing pattern can read the new tests at sight.


Regeneration and update policy
==============================

When a ``golden_expected.json`` no longer matches and the new behavior
is correct, regenerate with::

    seamm-golden regenerate <case-path>

This runs the flowchart, copies the resulting ``golden_output.json`` to
``golden_expected.json``, preserving any tolerance wrappers (the
regenerator edits values in place rather than overwriting the file).
The user must then update the case's ``README.rst`` with what changed
and why.

CI never regenerates automatically. A failing CI run produces a diff;
a developer makes the call to either fix the code or run the
regeneration command and commit the update.


SMILES caveats and fallbacks
============================

RDKit's canonical isomeric SMILES is the primary identifier, but it has
known soft spots:

- **Hypervalent anions** (PF6-, SF6, etc.): RDKit handles the SMILES,
  but Open Babel cannot generate a reasonable 3D structure for them;
  the test flowchart should read such species from a prebuilt
  configuration file rather than building from SMILES. Pin the RDKit
  version in the test environment so canonical-SMILES output is stable.
- **Organometallics**: SMILES often loses bond-order information.
  Use ``formula`` and any structural fingerprint (residue name, source
  filename hash) as the identifier; set ``smiles: null`` if not safe.
- **Crystals and periodic non-molecular systems**: no SMILES at all.
  Identification is by ``formula`` + cell + spacegroup. The schema's
  ``components`` block becomes per-element rather than per-molecule;
  this is a schema extension we will deal with when applying golden
  tests to a crystal-producing plug-in.
- **Tautomers and protonation states**: canonical SMILES picks one;
  if the test should be tolerant of tautomers, the test author needs
  to normalize before comparison. This is rare enough to handle case
  by case rather than in the comparator.


Tolerance defaults (Packmol-specific starting points)
=====================================================

These are starting suggestions; refine after the first few cases run.

- Integer counts: exact.
- Charge: exact.
- Cell lengths and volume: ``rtol = 5e-3`` (Packmol packing has small
  run-to-run variation even with a fixed seed when input file order or
  filesystem behavior differs).
- Density: ``rtol = 5e-3``.
- Molarities, mole fractions, weight fractions: ``rtol = 1e-2`` (these
  inherit the count rounding plus the cell-volume noise).
- Bond counts: ``atol = 2`` (bond perception from coordinates can flip
  a small number of bonds on/off near cutoffs).

For QM plug-ins, defaults will be much tighter on energies (``rtol``
of ``1e-6`` to ``1e-5`` is realistic on a single machine) but looser
on derived geometric quantities.


Decisions (resolved)
====================

1. **Package name**: ``golden_step`` (matches ``<thing>_step`` convention,
   short enough).
2. **GUI step name**: "Golden Test".
3. **File names**: ``golden_output.json`` (what was observed),
   ``golden_expected.json`` (reference), ``golden_result.json``
   (comparison report). All three share the ``golden_`` prefix so they
   sort together and their role is obvious.
4. **Do not write golden-test data to the SEAMM property database.**
   The property store is for chemical science, not test bookkeeping.
   JSON files in the job directory are the only artifact. A separate,
   broader SEAMM enhancement could add a "testing-only" metadata flag
   on properties to keep specialised entries out of default UI views,
   but that is independent of this work.
5. **pytest harness**: extend the pattern in
   ``packmol_step/tests/test_flowcharts.py`` (``seamm_exec.run`` with
   monkey-patched ``sys.argv``). No new infrastructure needed.


Open questions
==============

1. **Cross-platform reproducibility of Packmol.** What rtol works on
   both Linux and macOS with the same Packmol version? Determine
   empirically on case 1 before locking defaults.
2. **Should canonical SMILES become the SEAMM default?** Not blocking
   golden tests, but worth a separate discussion. Tests will work
   either way because the Golden Test step canonicalizes locally.
3. **One step per plug-in, or one generic step?** Currently planned as
   one generic step that snapshots the system + named properties.
   Plug-in-specific richness comes from naming properties at the test
   site, not from subclasses. Revisit after step 5 of the scope plan.


Implementation notes for step 1 (the Golden Test step itself)
=============================================================

- Model the package on ``geometry_analysis_step`` rather than
  ``packmol_step``; it's a simpler reference for a step that reads the
  current configuration and writes a file.
- The metrics computation is pure (system in, dict out). Implement it
  as a free function or a small class with no SEAMM dependencies, so
  it can be unit-tested without instantiating a flowchart.
- The comparator is also pure (two dicts in, report dict out). Same
  testability argument.
- The actual SEAMM step is then a thin wrapper that gets the
  configuration, calls the pure functions, and writes files.
