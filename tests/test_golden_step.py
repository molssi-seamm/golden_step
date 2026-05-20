#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""Tests for `golden_step` package."""

import pytest  # noqa: F401
import golden_step  # noqa: F401


def test_construction():
    """Just create an object and test its type."""
    result = golden_step.Golden()
    assert str(type(result)) == "<class 'golden_step.golden.Golden'>"
