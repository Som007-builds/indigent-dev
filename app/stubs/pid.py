from app.contracts.models import PIDGraph


class StubPid:
    """Stub P&ID pipeline matching the async contract in app/contracts/interfaces.py."""

    async def extract_pid_graph(self, image_path: str) -> PIDGraph:
        return PIDGraph(
            nodes=[],
            edges=[],
            overlay_image_path=image_path,
            narrative="Stub P&ID graph",
            confidence_summary={"confidence": 1.0},
        )
