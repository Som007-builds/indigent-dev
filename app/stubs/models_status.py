class StubModelsStatus:
    def status(self) -> dict:
        return {
            "active_inference_mode": "local",
            "hardware_profile": "stub",
            "models": [],
            "resident_models": [],
            "resources": {
                "vram_mb_free": 0,
                "ram_mb_free": 0,
                "disk_mb_free": 0,
                "max_concurrency": 2,
            },
        }
