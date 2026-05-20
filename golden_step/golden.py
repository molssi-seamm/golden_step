# -*- coding: utf-8 -*-

"""Non-graphical part of the Golden Test step in a SEAMM flowchart"""

import json
import logging
from pathlib import Path

import golden_step
import seamm
from seamm_util import ureg, Q_  # noqa: F401
import seamm_util.printing as printing
from seamm_util.printing import FormattedText as __

# In addition to the normal logger, two logger-like printing facilities are
# defined: "job" and "printer". "job" send output to the main job.out file for
# the job, and should be used very sparingly, typically to echo what this step
# will do in the initial summary of the job.
#
# "printer" sends output to the file "step.out" in this steps working
# directory, and is used for all normal output from this step.

logger = logging.getLogger(__name__)
job = printing.getPrinter()
printer = printing.getPrinter("Golden Test")


class Golden(seamm.Node):
    """
    The non-graphical part of a Golden Test step in a flowchart.

    Attributes
    ----------
    parameters : GoldenParameters
        The control parameters for the Golden Test step.

    See Also
    --------
    TkGolden, GoldenParameters
    """

    def __init__(
        self, flowchart=None, title="Golden Test", extension=None, logger=logger
    ):
        """A Golden Test step in a SEAMM flowchart.

        Parameters
        ----------
        flowchart: seamm.Flowchart
            The non-graphical flowchart that contains this step.

        title: str
            The name displayed in the flowchart.
        extension: None
            Not yet implemented
        logger : Logger = logger
            The logger to use and pass to parent classes

        Returns
        -------
        None
        """
        logger.debug(f"Creating Golden Test step {self}")

        super().__init__(
            flowchart=flowchart,
            title="Golden Test",
            extension=extension,
            module=__name__,
            logger=logger,
        )  # yapf: disable

        self._metadata = golden_step.metadata
        self.parameters = golden_step.GoldenParameters()

    @property
    def version(self):
        """The semantic version of this module."""
        return golden_step.__version__

    @property
    def git_revision(self):
        """The git version of this module."""
        return golden_step.__git_revision__

    def description_text(self, P=None):
        """Create the text description of what this step will do.
        The dictionary of control values is passed in as P so that
        the code can test values, etc.

        Parameters
        ----------
        P: dict
            An optional dictionary of the current values of the control
            parameters.
        Returns
        -------
        str
            A description of the current step.
        """
        if not P:
            P = self.parameters.values_to_dict()

        mode = P["mode"]
        if mode == "skip":
            text = "Skip the Golden Test step (no output written)."
        elif mode == "record":
            text = ("Snapshot the current system to '{output_file}'.").format(
                output_file=P["output file"]
            )
        elif mode == "verify":
            text = (
                "Snapshot the current system to '{output_file}' and compare "
                "against the reference '{expected_file}'. On a mismatch, "
                "'{on_failure}'."
            ).format(
                output_file=P["output file"],
                expected_file=P["expected file"],
                on_failure=P["on failure"],
            )
        else:
            text = "Unrecognised mode '{}'.".format(mode)

        return self.header + "\n" + __(text, **P, indent=4 * " ").__str__()

    def run(self):
        """Run a Golden Test step.

        Parameters
        ----------
        None

        Returns
        -------
        seamm.Node
            The next node object in the flowchart.
        """
        next_node = super().run(printer)
        # Get the values of the parameters, dereferencing any variables
        P = self.parameters.current_values_to_dict(
            context=seamm.flowchart_variables._data
        )

        # Print what we are doing
        printer.important(__(self.description_text(P), indent=self.indent))

        mode = P["mode"]
        if mode == "skip":
            printer.normal(__("Skipping (mode='skip').", indent=4 * " ", wrap=False))
            return next_node

        directory = Path(self.directory)
        directory.mkdir(parents=True, exist_ok=True)

        # Get the current system and configuration
        _, configuration = self.get_system_configuration(None)

        # Build the metrics dictionary (pure function; see metrics.py)
        from .metrics import build_metrics

        metrics = build_metrics(configuration, step_name="golden")

        # Write golden_output.json
        output_path = directory / P["output file"]
        output_path.write_text(json.dumps(metrics, indent=2))
        printer.normal(
            __(
                "Wrote metrics to {path}",
                path=output_path,
                indent=4 * " ",
                wrap=False,
            )
        )

        if mode == "verify":
            # Locate golden_expected.json relative to the flowchart directory
            expected_path = Path(P["expected file"])
            if not expected_path.is_absolute():
                expected_path = Path(self.flowchart.path).parent / expected_path

            if not expected_path.exists():
                msg = "Expected file not found: {}".format(expected_path)
                printer.important(__(msg, indent=4 * " ", wrap=False))
                if P["on failure"] == "stop":
                    raise FileNotFoundError(msg)
                return next_node

            expected = json.loads(expected_path.read_text())

            from .compare import compare

            report = compare(expected, metrics)

            result_path = directory / "golden_result.json"
            result_path.write_text(json.dumps(report, indent=2))

            if report["passed"]:
                printer.important(
                    __(
                        "Golden test PASSED ({summary}).",
                        summary=report["summary"],
                        indent=4 * " ",
                        wrap=False,
                    )
                )
            else:
                printer.important(
                    __(
                        "Golden test FAILED ({summary}). See {path}.",
                        summary=report["summary"],
                        path=result_path,
                        indent=4 * " ",
                        wrap=False,
                    )
                )
                if P["on failure"] == "stop":
                    raise AssertionError("Golden test failed: " + report["summary"])

        return next_node
