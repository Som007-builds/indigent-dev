from app.contracts.models import ArtifactManifest, ValidationReport


class StubArtifactValidator:
    async def validate(self, m: ArtifactManifest) -> ValidationReport:
        return ValidationReport(
            passed=True, checks=[{"name": "stub", "passed": True, "detail": "valid"}]
        )
