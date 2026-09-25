from __future__ import annotations


from pydantic import BaseModel, Field, field_validator, model_validator


class PIDNode(BaseModel):
    node_id: str
    category: str
    label: str | None = None
    bbox: tuple[float, float, float, float] | None = None
    confidence: float | None = None
    image_id: str | None = None

    @field_validator("node_id", "category")
    @classmethod
    def required_text(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("must not be empty")
        return value

    @field_validator("confidence")
    @classmethod
    def confidence_range(cls, value: float | None) -> float | None:
        if value is not None and not 0 <= value <= 1:
            raise ValueError("confidence must be between 0 and 1")
        return value


class PIDEdge(BaseModel):
    edge_id: str
    source_node_id: str
    target_node_id: str
    relationship: str
    confidence: float | None = None
    image_id: str | None = None

    @field_validator("edge_id", "source_node_id", "target_node_id", "relationship")
    @classmethod
    def required_text(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("must not be empty")
        return value

    @field_validator("confidence")
    @classmethod
    def confidence_range(cls, value: float | None) -> float | None:
        if value is not None and not 0 <= value <= 1:
            raise ValueError("confidence must be between 0 and 1")
        return value


class StructuredPIDGraph(BaseModel):
    nodes: list[PIDNode] = Field(default_factory=list)
    edges: list[PIDEdge] = Field(default_factory=list)
    overlay_image_path: str
    narrative: str = ""
    confidence_summary: dict = Field(default_factory=dict)

    @model_validator(mode="after")
    def edge_references_nodes(self) -> "StructuredPIDGraph":
        node_ids = {node.node_id for node in self.nodes}
        if len(node_ids) != len(self.nodes):
            raise ValueError("node IDs must be stable and unique")
        if len({edge.edge_id for edge in self.edges}) != len(self.edges):
            raise ValueError("edge IDs must be stable and unique")
        if any(edge.source_node_id not in node_ids or edge.target_node_id not in node_ids for edge in self.edges):
            raise ValueError("edges must reference graph nodes")
        return self

    def contract_payload(self) -> dict:
        return {
            "nodes": [node.model_dump() for node in self.nodes],
            "edges": [edge.model_dump() for edge in self.edges],
            "overlay_image_path": self.overlay_image_path,
            "narrative": self.narrative,
            "confidence_summary": self.confidence_summary,
        }
