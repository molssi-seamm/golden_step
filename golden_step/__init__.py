# -*- coding: utf-8 -*-

"""
golden_step
A SEAMM plug-in for Golden
"""

# Bring up the classes so that they appear to be directly in
# the golden_step package.

from .golden import Golden  # noqa: F401, E501
from .golden_parameters import GoldenParameters  # noqa: F401, E501
from .golden_step import GoldenStep  # noqa: F401, E501
from .tk_golden import TkGolden  # noqa: F401, E501

from .metadata import metadata  # noqa: F401

# Handle versioneer
from ._version import get_versions

__author__ = "Paul Saxe"
__email__ = "psaxe@molssi.org"
versions = get_versions()
__version__ = versions["version"]
__git_revision__ = versions["full-revisionid"]
del get_versions, versions
