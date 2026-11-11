"""Compatibility shim: all metadata lives in pyproject.toml.

Kept so `python setup.py develop` and older tooling still work.
Preferred install: `pip install -e ".[dev]"`.
"""

from setuptools import setup

setup()
