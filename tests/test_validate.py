"""Tests for scripts/validate.py."""

import sys
from pathlib import Path

# Add scripts/ to path so we can import validate
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from validate import (  # noqa: E402
    ModuleYaml,
    ValidationResult,
    _validate_assessment_dir,
    validate_modules_dir,
)

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


class TestUniformImageValidation:
    """Test image validation for uniform assessments."""

    def test_valid_uniform_images(self) -> None:
        """All declared image keys exist in every question dir."""
        assessment_dir = FIXTURES / ".uniform-images-valid" / "assessment"
        result = ValidationResult()
        _validate_assessment_dir(assessment_dir, result)
        assert result.is_valid, result.summary()

    def test_missing_uniform_image(self) -> None:
        """Missing image file is reported as an error."""
        assessment_dir = FIXTURES / ".uniform-images-missing" / "assessment"
        result = ValidationResult()
        _validate_assessment_dir(assessment_dir, result)
        assert not result.is_valid
        # Should mention the missing file name
        error_messages = [e.message for e in result.errors]
        assert any("nbi.png" in m for m in error_messages)

    def test_undeclared_uniform_image(self) -> None:
        """Image file not declared in assessment.yaml is reported."""
        assessment_dir = FIXTURES / ".uniform-images-extra" / "assessment"
        result = ValidationResult()
        _validate_assessment_dir(assessment_dir, result)
        assert not result.is_valid
        error_messages = [e.message for e in result.errors]
        assert any(
            "old-image.png" in m and "undeclared" in m for m in error_messages
        )


class TestVariableImageValidation:
    """Test image validation for variable assessments."""

    def test_valid_variable_images(self) -> None:
        """All per-question image keys exist in the question dir."""
        assessment_dir = FIXTURES / ".variable-images-valid" / "assessment"
        result = ValidationResult()
        _validate_assessment_dir(assessment_dir, result)
        assert result.is_valid, result.summary()

    def test_missing_variable_image(self) -> None:
        """Missing image referenced in question.yaml is reported."""
        assessment_dir = FIXTURES / ".variable-images-missing" / "assessment"
        result = ValidationResult()
        _validate_assessment_dir(assessment_dir, result)
        assert not result.is_valid
        error_messages = [e.message for e in result.errors]
        assert any("pa-chest-xray.png" in m for m in error_messages)

    def test_undeclared_variable_image(self) -> None:
        """Image file not declared in question.yaml is reported."""
        assessment_dir = FIXTURES / ".variable-images-extra" / "assessment"
        result = ValidationResult()
        _validate_assessment_dir(assessment_dir, result)
        assert not result.is_valid
        error_messages = [e.message for e in result.errors]
        assert any(
            "leftover.jpg" in m and "undeclared" in m for m in error_messages
        )
