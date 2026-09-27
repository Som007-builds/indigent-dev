from __future__ import annotations

import logging
from typing import Any

from app.config import Settings, get_settings

logger = logging.getLogger(__name__)

DEFAULT_GROQ_MODELS = [
    {
        "id": "openai/gpt-oss-120b",
        "name": "GPT-OSS 120B (OpenAI / Groq)",
        "role": "reasoning",
        "paramCount": "120B",
        "authorOrOrg": "OpenAI on Groq LPU",
        "architecture": "GPT-OSS-120B-MoE",
        "tasks": ["Frontier Reasoning", "SOP Clause Matching", "Deterministic Decision Logic"],
        "contextLength": 131072,
        "quantization": "BF16 Native LPU",
        "vramGb": 0.0,
        "isResident": True,
        "priority": 1,
        "speedTokSec": 120.0,
        "firstTokenMs": 85,
        "engineBackend": "Groq LPU Hardware Inference",
        "status": "resident",
    },
    {
        "id": "openai/gpt-oss-20b",
        "name": "GPT-OSS 20B (OpenAI / Groq)",
        "role": "coding",
        "paramCount": "20B",
        "authorOrOrg": "OpenAI on Groq LPU",
        "architecture": "GPT-OSS-20B-Dense",
        "tasks": ["Fast Code Generation", "Mathematical Verification", "Tool Execution"],
        "contextLength": 131072,
        "quantization": "BF16 Native LPU",
        "vramGb": 0.0,
        "isResident": False,
        "priority": 1,
        "speedTokSec": 260.0,
        "firstTokenMs": 45,
        "engineBackend": "Groq LPU Hardware Inference",
        "status": "available",
    },
    {
        "id": "qwen/qwen3.8-27b",
        "name": "Qwen 3.8 27B (Alibaba Cloud / Groq)",
        "role": "coding",
        "paramCount": "27B",
        "authorOrOrg": "Alibaba Cloud on Groq LPU",
        "architecture": "Qwen3.8-27B-Instruct",
        "tasks": ["Python Sandbox Logic", "Algorithm Repair", "Data Structuring"],
        "contextLength": 131072,
        "quantization": "BF16 Native LPU",
        "vramGb": 0.0,
        "isResident": False,
        "priority": 2,
        "speedTokSec": 195.0,
        "firstTokenMs": 60,
        "engineBackend": "Groq LPU Hardware Inference",
        "status": "available",
    },
    {
        "id": "allam-2-7b",
        "name": "ALLAM 2 7B (SDAIA / Groq)",
        "role": "general",
        "paramCount": "7B",
        "authorOrOrg": "SDAIA on Groq LPU",
        "architecture": "ALLAM-2-7B-Base",
        "tasks": ["Fast Policy Lookup", "Bilingual Synthesis", "Text Extraction"],
        "contextLength": 4096,
        "quantization": "BF16 Native LPU",
        "vramGb": 0.0,
        "isResident": False,
        "priority": 3,
        "speedTokSec": 320.0,
        "firstTokenMs": 30,
        "engineBackend": "Groq LPU Hardware Inference",
        "status": "available",
    },
    {
        "id": "openai/gpt-oss-safeguard-20b",
        "name": "GPT-OSS Safeguard 20B",
        "role": "reasoning",
        "paramCount": "20B",
        "authorOrOrg": "OpenAI on Groq LPU",
        "architecture": "GPT-OSS-Safeguard-20B",
        "tasks": ["Safety Policy Guardrails", "Security Egress Verification", "Toxicity Check"],
        "contextLength": 131072,
        "quantization": "BF16 Native LPU",
        "vramGb": 0.0,
        "isResident": False,
        "priority": 4,
        "speedTokSec": 280.0,
        "firstTokenMs": 40,
        "engineBackend": "Groq LPU Hardware Inference",
        "status": "available",
    },
]

DEFAULT_LOCAL_MODELS = [
    {
        "id": "qwen2.5-coder:7b",
        "name": "Qwen 2.5 Coder 7B",
        "role": "coding",
        "paramCount": "7B",
        "authorOrOrg": "Alibaba Cloud",
        "architecture": "Qwen2.5-Coder-7B-Instruct",
        "tasks": ["Python Sandbox", "Mathematical Verification", "Auto-Repair Loop"],
        "contextLength": 32768,
        "quantization": "Q4_K_M",
        "vramGb": 5.2,
        "isResident": True,
        "priority": 1,
        "speedTokSec": 42.0,
        "firstTokenMs": 95,
        "engineBackend": "llama.cpp v0.4 (Local)",
        "status": "resident",
    },
    {
        "id": "qwen3:8b",
        "name": "Qwen 3 8B Instruct",
        "role": "reasoning",
        "paramCount": "8B",
        "authorOrOrg": "Alibaba Cloud",
        "architecture": "Qwen3-8B-Instruct",
        "tasks": ["SOP Verification", "Chain-of-Thought Reasoning", "Regulatory Compliance"],
        "contextLength": 32768,
        "quantization": "Q4_K_M",
        "vramGb": 5.8,
        "isResident": False,
        "priority": 1,
        "speedTokSec": 38.5,
        "firstTokenMs": 110,
        "engineBackend": "llama.cpp v0.4 (Local)",
        "status": "standby",
    },
    {
        "id": "deepseek-r1-distill-qwen:8b",
        "name": "DeepSeek R1 Distill Qwen 8B",
        "role": "reasoning",
        "paramCount": "8B",
        "authorOrOrg": "DeepSeek AI",
        "architecture": "DeepSeek-R1-Distill-Qwen-8B",
        "tasks": ["Frontier Local Reasoning", "Technical Synthesis", "Legal Audit"],
        "contextLength": 32768,
        "quantization": "Q4_K_M",
        "vramGb": 5.9,
        "isResident": False,
        "priority": 2,
        "speedTokSec": 32.0,
        "firstTokenMs": 130,
        "engineBackend": "llama.cpp v0.4 (Local)",
        "status": "available",
    },
]


class StubModelsStatus:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.active_model_id: str = (
            "openai/gpt-oss-120b"
            if self.settings.inference_mode == "groq"
            else "qwen2.5-coder:7b"
        )
        self.custom_models: list[dict[str, Any]] = []

    def set_active_model(self, model_id: str) -> None:
        self.active_model_id = model_id
        logger.info("Active model switched to %s", model_id)

    def get_active_model(self) -> str:
        return self.active_model_id

    def add_custom_model(self, model: dict[str, Any]) -> None:
        self.custom_models.append(model)

    def status(self) -> dict:
        is_groq = self.settings.inference_mode == "groq"
        base_models = [dict(m) for m in (DEFAULT_GROQ_MODELS if is_groq else DEFAULT_LOCAL_MODELS)]
        all_models = base_models + self.custom_models

        # Sync resident status based on active_model_id
        for m in all_models:
            if m["id"] == self.active_model_id:
                m["isResident"] = True
                m["status"] = "resident"
            else:
                m["isResident"] = False
                m["status"] = "standby"

        return {
            "active_inference_mode": self.settings.inference_mode,
            "hardware_profile": "groq_cloud_lpu" if is_groq else self.settings.local_hardware_profile,
            "active_model_id": self.active_model_id,
            "models": all_models,
            "resident_models": [self.active_model_id],
            "resources": {
                "vram_mb_free": 0 if is_groq else 24576,
                "ram_mb_free": 65536,
                "disk_mb_free": 262144,
                "max_concurrency": 4,
            },
        }
