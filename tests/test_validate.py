"""Tests for scripts/validate.py."""

import sys
from pathlib import Path

# Add scripts/ to path so we can import validate
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from validate import ModuleYaml, validate_modules_dir  # noqa: E402


FIXTURES = Path(__file__).parent / "fixtures"


class TestModuleYamlSchema:
    """Test Pydantic schema validation."""

    def test_valid_module_yaml(self) -> None:
        module = ModuleYaml(
            moduleId="test-module",
            title="Test Module",
            order=1,
            status="live",
            renewalMonths=36,
        )
        assert module.moduleId == "test-module"
        assert module.renewalMonths == 36

    def test_null_renewal_months(self) -> None:
        module = ModuleYaml(
            moduleId="test-module",
            title="Test Module",
            order=1,
            status="draft",
            renewalMonths=None,
        )
        assert module.renewalMonths is None

    def test_invalid_module_id_uppercase(self) -> None:
        import pytest

        with pytest.raises(Exception):
            ModuleYaml(
                moduleId="TestModule",
                title="Test",
                order=1,
                status="live",
            )

    def test_invalid_status(self) -> None:
        import pytest

        with pytest.raises(Exception):
            ModuleYaml(
                moduleId="test-module",
                title="Test",
                order=1,
                status="published",
            )

    def test_negative_renewal_months(self) -> None:
        import pytest

        with pytest.raises(Exception):
            ModuleYaml(
                moduleId="test-module",
                title="Test",
                order=1,
                status="live",
                renewalMonths=-1,
            )


class TestValidateModulesDir:
    """Test full directory validation."""

    def test_nonexistent_directory(self) -> None:
        result = validate_modules_dir(Path("/nonexistent"))
        assert not result.is_valid

    def test_valid_fixture(self) -> None:
        # Create a temporary modules dir structure pointing at fixture
        # The fixture starts with . so it's skipped by default
        # We test the validation function directly with the fixture path
        valid_module = FIXTURES / ".valid-module"
        # Validate individual module components
        from validate import _validate_module_yaml

        from validate import ValidationResult

        result = ValidationResult()
        module = _validate_module_yaml(valid_module, result)
        # moduleId won't match dir name (.valid-module != valid-module)
        # but the schema itself should parse
        assert module is not None
        assert module.title == "Valid Test Module"

    def test_invalid_fixture(self) -> None:
        from validate import ValidationResult, _validate_module_yaml

        invalid_module = FIXTURES / ".invalid-module"
        result = ValidationResult()
        module = _validate_module_yaml(invalid_module, result)
        # Should fail — missing moduleId field, invalid status
        assert module is None or not result.is_valid
