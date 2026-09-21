"""Vaani backend package.

Holds the single source of the application version. The version is a plain
string here (mirrored by `version` in pyproject.toml) so that importing the
package never depends on the package being installed first — useful in tests
and in tooling that imports before an editable install exists.
"""

# Bump this together with `version` in pyproject.toml on every release.
__version__ = "0.1.0"
