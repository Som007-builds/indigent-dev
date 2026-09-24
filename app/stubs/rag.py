from app.contracts.models import FileRecord, IngestResult


class StubRag:
    async def ingest(self, file: FileRecord) -> IngestResult:
        return IngestResult(file_id=file.file_id, status="ok", chunks=1)
