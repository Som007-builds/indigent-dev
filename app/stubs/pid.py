from app.contracts.models import PIDGraph


class StubPid:
    def extract_pid_graph(self, image_path: str) -> PIDGraph:
        return PIDGraph(
            nodes=[],
            edges=[],
            overlay_image_path=image_path,
            narrative="Stub P&ID graph",
            confidence_summary={"confidence": 1.0},
        )
