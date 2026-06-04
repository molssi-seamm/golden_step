# -*- coding: utf-8 -*-
"""Pure-function builders for the Golden Test step's metrics JSON.

These functions take a `molsystem.Configuration` and return JSON-serializable
dicts. They have no side effects, do not write to disk, and have no SEAMM
dependencies beyond ``molsystem`` and RDKit, so they can be unit tested
without instantiating a flowchart.

The schema produced here is described in NOTES_golden_tests_design.rst.
Bump ``SCHEMA_VERSION`` when making a backwards-incompatible change to the
shape of the output.
"""

from collections import defaultdict

from rdkit import Chem
from rdkit.Chem import Descriptors, rdMolDescriptors

SCHEMA_VERSION = 1

# Avogadro's number (CODATA 2018, exact by definition since the 2019 SI
# redefinition). 1/mol.
N_A = 6.02214076e23


def build_metrics(configuration, step_name="golden", schema_version=SCHEMA_VERSION):
    """Build a metrics dict from a molsystem Configuration.

    Parameters
    ----------
    configuration : molsystem.Configuration
        The current system/configuration.
    step_name : str
        Name of the step producing these metrics. Recorded in the output as
        the ``step`` field. The Golden Test step itself passes ``"golden"``;
        a hypothetical plug-in-internal use could pass its own name.
    schema_version : int
        Schema version to tag the output with. Callers normally use the
        default; the parameter exists so tests can pin a version.

    Returns
    -------
    dict
        A JSON-serializable dict with keys ``schema_version``, ``step``,
        ``system``, ``components``, ``derived``.
    """
    system = _build_system(configuration)
    components = _build_components(configuration)
    derived = _build_derived(system, components)
    return {
        "schema_version": schema_version,
        "step": step_name,
        "system": system,
        "components": components,
        "derived": derived,
    }


def _build_system(configuration):
    """Build the ``system`` block: aggregate properties of the whole cell."""
    periodicity = configuration.periodicity

    system = {
        "periodic": periodicity > 0,
        "dimensionality": periodicity,
        "n_atoms": configuration.n_atoms,
        "n_bonds": configuration.n_bonds,
        "charge": configuration.charge,
        "spin_multiplicity": configuration.spin_multiplicity,
    }

    if periodicity == 3:
        cell = configuration.cell
        a, b, c, alpha, beta, gamma = cell.parameters
        system["cell"] = {
            "a": a,
            "b": b,
            "c": c,
            "alpha": alpha,
            "beta": beta,
            "gamma": gamma,
            "volume": cell.volume,
            "lengths_units": "Å",
            "angles_units": "degree",
            "volume_units": "Å^3",
        }
    elif periodicity == 0:
        # Non-periodic: use a bounding box. Note that this is not a
        # rotation-invariant descriptor; for golden testing of clusters it
        # should be compared with a loose tolerance (or omitted from
        # golden_expected.json entirely).
        xyz = configuration.atoms.coordinates
        if xyz:
            xs = [c[0] for c in xyz]
            ys = [c[1] for c in xyz]
            zs = [c[2] for c in xyz]
            system["bounding_box"] = {
                "a": max(xs) - min(xs),
                "b": max(ys) - min(ys),
                "c": max(zs) - min(zs),
                "units": "Å",
            }
    # periodicity 1 or 2: not handled in v1. Cell is partially defined and
    # would need its own representation. Leave 'cell' absent for now.

    return system


def _build_components(configuration):
    """Build the ``components`` list: one entry per chemically distinct molecule.

    The configuration is converted to a single RDKit molecule and split into
    its connected fragments. Each fragment is canonicalized to its isomeric
    canonical SMILES. Fragments with identical SMILES are grouped, and the
    component's ``count`` is the size of the group.

    Mass and formula are computed by RDKit on a representative fragment from
    each group. They are therefore based on RDKit's standard atomic weights,
    which may differ in the 4th or 5th decimal from molsystem's; for golden
    testing this is well below the default tolerance.
    """
    rdk_mol = configuration.to_RDKMol()

    # Split the configuration into connected molecules. asMols=True returns
    # a tuple of Mol objects, one per connected fragment.
    frags = Chem.GetMolFrags(rdk_mol, asMols=True)

    smiles_groups = defaultdict(list)
    for frag in frags:
        smi = Chem.MolToSmiles(frag, isomericSmiles=True, canonical=True)
        smiles_groups[smi].append(frag)

    components = []
    for smi, group in smiles_groups.items():
        representative = group[0]
        formula = rdMolDescriptors.CalcMolFormula(representative)
        mass = Descriptors.MolWt(representative)
        components.append(
            {
                "smiles": smi,
                "formula": formula,
                "count": len(group),
                "mass_g_per_mol": mass,
            }
        )

    # Sort for stable, human-friendly output. The comparator matches by
    # SMILES, so order does not affect verification.
    components.sort(key=lambda c: (-c["count"], c["smiles"]))

    return components


def _build_derived(system, components):
    """Build the ``derived`` block: aggregate quantities computed from the above.

    Fields are omitted (rather than set to ``null``) when they are not
    applicable: density and molarities require a periodic cell with a
    defined volume; fractions require at least one component with mass.
    """
    derived = {}

    if not components:
        return derived

    counts = [c["count"] for c in components]
    masses = [c["mass_g_per_mol"] for c in components]

    # Total mass: sum over components of count * mass_per_molecule (g/mol-cell)
    total_mass = sum(n * m for n, m in zip(counts, masses))
    derived["total_mass_g_per_mol"] = total_mass

    # Composition ratios. These are well-defined as long as the cell is
    # non-empty (handled by the early return above).
    min_count = min(counts)
    derived["molar_ratios"] = [n / min_count for n in counts]

    total_count = sum(counts)
    if total_count > 0:
        derived["mole_fractions"] = [n / total_count for n in counts]

    if total_mass > 0:
        derived["wt_fractions"] = [
            (counts[i] * masses[i]) / total_mass for i in range(len(components))
        ]

    # Density and molarities only make sense in a periodic cell. For
    # density: mass of the cell in grams divided by volume in mL.
    # The cell contains exactly one copy of each count, so cell mass in
    # grams is total_mass[g/mol] / N_A.
    if system.get("periodic") and "cell" in system:
        volume_A3 = system["cell"]["volume"]
        if volume_A3 > 0 and total_mass > 0:
            cell_mass_g = total_mass / N_A
            volume_mL = volume_A3 * 1.0e-24  # 1 Å^3 = 1e-24 mL
            derived["density_g_per_mL"] = cell_mass_g / volume_mL

            volume_L = volume_A3 * 1.0e-27  # 1 Å^3 = 1e-27 L
            derived["molarities_M"] = [n / N_A / volume_L for n in counts]

    return derived
