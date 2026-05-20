# -*- coding: utf-8 -*-
"""
Control parameters for the Golden Test step in a SEAMM flowchart
"""

import logging
import seamm
import pprint  # noqa: F401

logger = logging.getLogger(__name__)


class GoldenParameters(seamm.Parameters):
    """
    The control parameters for the Golden Test step.

    See Also
    --------
    Golden, TkGolden, GoldenStep
    """

    parameters = {
        "mode": {
            "default": "record",
            "kind": "enum",
            "default_units": "",
            "enumeration": ("record", "verify", "skip"),
            "format_string": "",
            "description": "Mode:",
            "help_text": (
                "What the Golden Test step should do. 'record' writes a "
                "metrics snapshot of the current system to a JSON file. "
                "'verify' does the same and then compares the snapshot "
                "against a reference file. 'skip' does nothing."
            ),
        },
        "expected file": {
            "default": "golden_expected.json",
            "kind": "string",
            "default_units": "",
            "enumeration": ("golden_expected.json",),
            "format_string": "",
            "description": "Expected file:",
            "help_text": (
                "Path to the reference JSON file used in 'verify' mode. "
                "If the path is relative it is resolved against the "
                "flowchart's directory."
            ),
        },
        "output file": {
            "default": "golden_output.json",
            "kind": "string",
            "default_units": "",
            "enumeration": ("golden_output.json",),
            "format_string": "",
            "description": "Output file:",
            "help_text": (
                "Filename for the metrics snapshot written by this step "
                "in the step's working directory."
            ),
        },
        "on failure": {
            "default": "continue",
            "kind": "enum",
            "default_units": "",
            "enumeration": ("continue", "stop"),
            "format_string": "",
            "description": "On verify failure:",
            "help_text": (
                "What to do if a 'verify'-mode comparison fails. 'continue' "
                "writes the result file and lets the flowchart proceed. "
                "'stop' raises an error and halts the flowchart."
            ),
        },
        "case name": {
            "default": "",
            "kind": "string",
            "default_units": "",
            "enumeration": tuple(),
            "format_string": "",
            "description": "Case name:",
            "help_text": (
                "Identifier for this test case, recorded in the results so it can "
                "be put into a table when many tests run in one flowchart. "
                "If left empty, the step's title is used."
            ),
        },
        "results": {
            "default": {},
            "kind": "dictionary",
            "default_units": "",
            "enumeration": tuple(),
            "format_string": "",
            "description": "results",
            "help_text": "The results to save to variables or in tables.",
        },
    }

    def __init__(self, defaults={}, data=None):
        """
        Initialize the parameters, by default with the parameters defined above

        Parameters
        ----------
        defaults: dict
            A dictionary of parameters to initialize. The parameters
            above are used first and any given will override/add to them.
        data: dict
            A dictionary of keys and a subdictionary with value and units
            for updating the current, default values.

        Returns
        -------
        None
        """

        logger.debug("GoldenParameters.__init__")

        super().__init__(
            defaults={**GoldenParameters.parameters, **defaults}, data=data
        )
