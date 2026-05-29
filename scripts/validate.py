"""Module metadata and assessment validation.

Validates the structure of an organisation teaching repo:
- module.yaml schema (Pydantic)
- assessment.yaml structure (if present)
- Image file references
- Directory naming conventions

Usage:
    python scripts/validate.py /path/to/modules/

Exit codes:
    0 — all modules valid
    1 — one or more validation errors
"""

from __future__ import annotations

import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

import yaml
from pydantic import BaseModel, field_validator

# ------------------------------------------------------------------
# Schemas
# ------------------------------------------------------------------

KEBAB_CASE_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
QUESTION_DIR_RE = re.compile(r"^question_(\d+)$")
ALLOWED_IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp"}


class ModuleYaml(BaseModel):
    """Schema for module.yaml."""

    moduleId: str
    title: str
    order: int
    status: str
    renewalMonths: int | None = None

    @field_validator("moduleId")
    @classmethod
    def validate_module_id(cls, v: str) -> str:
        if not KEBAB_CASE_RE.match(v):
            msg = f"moduleId must be kebab-case, got '{v}'"
            raise ValueError(msg)
        return v

    @field_validator("status")
    @classmethod
    def validate_status(cls, v: str) -> str:
        if v not in ("draft", "live", "retired"):
            msg = f"status must be 'draft', 'live', or 'retired', got '{v}'"
            raise ValueError(msg)
        return v

    @field_validator("renewalMonths")
    @classmethod
    def validate_renewal_months(cls, v: int | None) -> int | None:
        if v is not None and v <= 0:
            msg = "renewalMonths must be positive or null"
            raise ValueError(msg)
        return v


REQUIRED_ASSESSMENT_FIELDS = {"version", "title", "type"}
VALID_ASSESSMENT_TYPES = {"uniform", "variable"}


# ------------------------------------------------------------------
# Result types
# ------------------------------------------------------------------


@dataclass
class ValidationError:
    """A single validation error."""

    path: str
    message: str

    def __str__(self) -> str:
        return f"  ERROR [{self.path}]: {self.message}"


@dataclass
class ValidationResult:
    """Aggregate validation result for a modules directory."""

    errors: list[ValidationError] = field(default_factory=list)
    modules_checked: int = 0

    @property
    def is_valid(self) -> bool:
        return len(self.errors) == 0

    def add_error(self, path: str, message: str) -> None:
        self.errors.append(ValidationError(path=path, message=message))

    def summary(self) -> str:
        lines = [f"Checked {self.modules_checked} module(s)."]
        if self.is_valid:
            lines.append("All valid.")
        else:
            lines.append(f"{len(self.errors)} error(s) found:")
            for err in self.errors:
                lines.append(str(err))
        return "\n".join(lines)


# ------------------------------------------------------------------
# Validators
# ------------------------------------------------------------------


def _validate_module_yaml(
    module_dir: Path, result: ValidationResult
) -> ModuleYaml | None:
    """Validate module.yaml exists and conforms to schema."""
    yaml_path = module_dir / "module.yaml"
    rel = str(yaml_path.relative_to(module_dir.parent.parent))

    if not yaml_path.is_file():
        result.add_error(rel, "module.yaml is missing")
        return None

    try:
        with open(yaml_path) as f:
            data = yaml.safe_load(f)
    except yaml.YAMLError as e:
        result.add_error(rel, f"invalid YAML: {e}")
        return None

    if not isinstance(data, dict):
        result.add_error(rel, "module.yaml must be a YAML mapping")
        return None

    try:
        module = ModuleYaml(**data)
    except Exception as e:
        result.add_error(rel, str(e))
        return None

    # moduleId must match directory name
    if module.moduleId != module_dir.name:
        result.add_error(
            rel,
            f"moduleId '{module.moduleId}' does not match "
            f"directory name '{module_dir.name}'",
        )

    return module


def _validate_assessment_dir(
    assessment_dir: Path, result: ValidationResult
) -> None:
    """Validate assessment directory structure."""
    rel_base = str(
        assessment_dir.relative_to(assessment_dir.parent.parent.parent)
    )

    # Must have assessment.yaml or config.yaml
    config_path = None
    for name in ("assessment.yaml", "config.yaml"):
        candidate = assessment_dir / name
        if candidate.is_file():
            config_path = candidate
            break

    if config_path is None:
        result.add_error(
            rel_base, "assessment/ exists but has no assessment.yaml"
        )
        return

    try:
        with open(config_path) as f:
            config = yaml.safe_load(f)
    except yaml.YAMLError as e:
        result.add_error(
            f"{rel_base}/{config_path.name}", f"invalid YAML: {e}"
        )
        return

    if not isinstance(config, dict):
        result.add_error(
            f"{rel_base}/{config_path.name}", "must be a YAML mapping"
        )
        return

    for field_name in REQUIRED_ASSESSMENT_FIELDS:
        if field_name not in config:
            result.add_error(
                f"{rel_base}/{config_path.name}",
                f"missing required field '{field_name}'",
            )

    bank_type = config.get("type")
    if bank_type and bank_type not in VALID_ASSESSMENT_TYPES:
        result.add_error(
            f"{rel_base}/{config_path.name}",
            f"invalid type '{bank_type}' — must be one of "
            f"{VALID_ASSESSMENT_TYPES}",
        )

    # Check question directories exist
    question_dirs = sorted(
        d
        for d in assessment_dir.iterdir()
        if d.is_dir() and QUESTION_DIR_RE.match(d.name)
    )
    if not question_dirs:
        result.add_error(rel_base, "no question_NNN directories found")
        return

    # Validate images in question directories
    if bank_type == "uniform":
        _validate_uniform_images(
            config, question_dirs, rel_base, config_path, result
        )
    elif bank_type == "variable":
        _validate_variable_images(question_dirs, rel_base, result)


def _validate_uniform_images(
    config: dict,
    question_dirs: list[Path],
    rel_base: str,
    config_path: Path,
    result: ValidationResult,
) -> None:
    """Validate image files in uniform assessment question directories.

    Uniform assessments define images at the assessment level. Each
    question directory must contain files matching the keys.
    """
    images = config.get("images")
    if not images:
        return

    if not isinstance(images, list):
        result.add_error(
            f"{rel_base}/{config_path.name}",
            "images must be a list of {key, label} objects",
        )
        return

    expected_keys: list[str] = []
    for i, img in enumerate(images):
        if not isinstance(img, dict) or "key" not in img:
            result.add_error(
                f"{rel_base}/{config_path.name}",
                f"images[{i}] must have a 'key' field",
            )
            return
        expected_keys.append(img["key"])

    expected_set = set(expected_keys)

    for qdir in question_dirs:
        rel_q = f"{rel_base}/{qdir.name}"
        existing_files = {f.name for f in qdir.iterdir() if f.is_file()}
        for key in expected_keys:
            if key not in existing_files:
                result.add_error(
                    rel_q, f"missing image '{key}' (defined in images[])"
                )
        # Check for undeclared image files
        image_files = {
            f
            for f in existing_files
            if Path(f).suffix.lower() in ALLOWED_IMAGE_EXTENSIONS
        }
        undeclared = image_files - expected_set
        for name in sorted(undeclared):
            result.add_error(
                rel_q,
                f"undeclared image '{name}' not in assessment.yaml images[]",
            )


def _validate_variable_images(
    question_dirs: list[Path],
    rel_base: str,
    result: ValidationResult,
) -> None:
    """Validate image files in variable assessment question directories.

    Variable assessments define images per question. Each referenced
    key must exist as a file in the question directory.
    """
    for qdir in question_dirs:
        rel_q = f"{rel_base}/{qdir.name}"
        question_yaml = qdir / "question.yaml"
        if not question_yaml.is_file():
            result.add_error(rel_q, "missing question.yaml")
            continue

        try:
            with open(question_yaml) as f:
                qdata = yaml.safe_load(f)
        except yaml.YAMLError:
            continue  # YAML errors caught elsewhere

        if not isinstance(qdata, dict):
            continue

        images = qdata.get("images")
        if not images:
            continue

        existing_files = {f.name for f in qdir.iterdir() if f.is_file()}
        declared_keys: set[str] = set()
        for i, img in enumerate(images):
            if not isinstance(img, dict) or "key" not in img:
                result.add_error(
                    rel_q, f"images[{i}] must have a 'key' field"
                )
                continue
            declared_keys.add(img["key"])
            if img["key"] not in existing_files:
                result.add_error(
                    rel_q,
                    f"missing image '{img['key']}' "
                    f"(referenced in question.yaml images[{i}])",
                )
        # Check for undeclared image files
        image_files = {
            f
            for f in existing_files
            if Path(f).suffix.lower() in ALLOWED_IMAGE_EXTENSIONS
        }
        undeclared = image_files - declared_keys
        for name in sorted(undeclared):
            result.add_error(
                rel_q,
                f"undeclared image '{name}' not in "
                f"question.yaml images[]",
            )


def _validate_learning_dir(
    learning_dir: Path, result: ValidationResult
) -> None:
    """Validate learning directory has content.mdx."""
    rel_base = str(learning_dir.relative_to(learning_dir.parent.parent.parent))

    content_path = learning_dir / "content.mdx"
    if not content_path.is_file():
        result.add_error(rel_base, "learning/ exists but has no content.mdx")
        return

    # Check file is non-empty
    if content_path.stat().st_size == 0:
        result.add_error(f"{rel_base}/content.mdx", "file is empty")


def _validate_module(module_dir: Path, result: ValidationResult) -> None:
    """Validate a single module directory."""
    result.modules_checked += 1

    _validate_module_yaml(module_dir, result)

    learning_dir = module_dir / "learning"
    assessment_dir = module_dir / "assessment"

    # Must have at least one of learning/ or assessment/
    if not learning_dir.is_dir() and not assessment_dir.is_dir():
        rel = str(module_dir.relative_to(module_dir.parent.parent))
        result.add_error(
            rel, "module must have at least one of learning/ or assessment/"
        )
        return

    if learning_dir.is_dir():
        _validate_learning_dir(learning_dir, result)

    if assessment_dir.is_dir():
        _validate_assessment_dir(assessment_dir, result)


def validate_modules_dir(modules_dir: Path) -> ValidationResult:
    """Validate all modules in a modules/ directory.

    Args:
        modules_dir: Path to the top-level modules/ directory.

    Returns:
        ValidationResult with any errors found.
    """
    result = ValidationResult()

    if not modules_dir.is_dir():
        result.add_error(str(modules_dir), "modules/ directory not found")
        return result

    module_dirs = sorted(
        d
        for d in modules_dir.iterdir()
        if d.is_dir() and not d.name.startswith(".")
    )

    if not module_dirs:
        result.add_error(str(modules_dir), "no module directories found")
        return result

    for module_dir in module_dirs:
        _validate_module(module_dir, result)

    return result


# ------------------------------------------------------------------
# CLI entry point
# ------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    """CLI entry point. Returns 0 on success, 1 on validation errors."""
    args = argv if argv is not None else sys.argv[1:]

    if not args:
        print("Usage: python scripts/validate.py <modules-directory>")
        return 1

    modules_path = Path(args[0])
    result = validate_modules_dir(modules_path)
    print(result.summary())
    return 0 if result.is_valid else 1


if __name__ == "__main__":
    sys.exit(main())
