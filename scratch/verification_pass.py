import asyncio
import io
import json
import os
import time
from pathlib import Path

# Ensure env vars are strictly set
os.environ["INFERENCE_MODE"] = "local"
os.environ["JOY_MODULES"] = "stub"
if "GROQ_API_KEY" in os.environ:
    del os.environ["GROQ_API_KEY"]

import httpx
from PIL import Image

from app.config import Settings
from app.main import create_app

tmp_dir = Path(f"./scratch/test_env_{int(time.time())}")
tmp_dir.mkdir(parents=True, exist_ok=True)

settings = Settings(
    data_dir=tmp_dir,
    inference_mode="local",
    joy_modules="stub",
)
app = create_app(settings)

async def main():
    endpoints_results = []

    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            print("=== STEP 4: ENDPOINT CHECKS ===")

            # 1. GET /healthz
            r = await client.get("/healthz")
            endpoints_results.append(("GET", "/healthz", r.status_code, r.json()))

            # 2. GET /readyz
            r = await client.get("/readyz")
            endpoints_results.append(("GET", "/readyz", r.status_code, r.json()))

            # 3. GET /api/models
            r = await client.get("/api/models")
            endpoints_results.append(("GET", "/api/models", r.status_code, r.json()))

            # 4. GET /api/monitoring/sovereignty
            r = await client.get("/api/monitoring/sovereignty")
            sovereignty_initial = r.json()
            endpoints_results.append(("GET", "/api/monitoring/sovereignty", r.status_code, sovereignty_initial))

            # 5. POST /api/chat (stub:happy) launched as a background async task
            chat_task = asyncio.create_task(client.post("/api/chat", json={"message": "stub:happy"}))

            # Poll repository for the created task_id
            task_id = None
            for _ in range(50):
                await asyncio.sleep(0.05)
                async with app.state.repository.db.connection() as conn:
                    async with conn.execute("SELECT task_id FROM tasks ORDER BY created_at DESC LIMIT 1") as cursor:
                        row = await cursor.fetchone()
                        if row:
                            task_id = row[0]
                            break

            endpoints_results.append(("POST", "/api/chat", 200, f"X-Task-Id: {task_id}"))

            # Wait for task to hit APPROVAL
            for _ in range(50):
                await asyncio.sleep(0.05)
                task_data = await app.state.repository.get_task(task_id)
                if task_data and task_data.get("current_state") == "APPROVAL":
                    break

            # 6. GET /api/tasks/{id}
            r = await client.get(f"/api/tasks/{task_id}")
            task_data = r.json()
            endpoints_results.append(("GET", f"/api/tasks/{task_id}", r.status_code, f"state: {task_data.get('current_state')}"))

            # 7. GET /api/tasks/{id}/timeline
            r = await client.get(f"/api/tasks/{task_id}/timeline")
            timeline_data = r.json()
            endpoints_results.append(("GET", f"/api/tasks/{task_id}/timeline", r.status_code, f"{len(timeline_data['entries'])} audit entries"))

            # 8. POST /api/tasks/{id}/approve
            r = await client.post(f"/api/tasks/{task_id}/approve", json={"approver": "Soham", "decision": "approve", "note": "All good"})
            approve_data = r.json()
            endpoints_results.append(("POST", f"/api/tasks/{task_id}/approve", r.status_code, approve_data))

            # Wait for chat stream task to complete
            chat_res = await chat_task
            assert chat_res.status_code == 200

            # Verify task reaches COMPLETE
            await asyncio.sleep(0.1)
            r = await client.get(f"/api/tasks/{task_id}")
            task_completed_data = r.json()

            # 9. POST /api/files/upload
            file_content = b"sample upload text file for testing"
            r = await client.post("/api/files/upload", files={"file": ("test_upload.txt", file_content, "text/plain")})
            upload_data = r.json()
            endpoints_results.append(("POST", "/api/files/upload", r.status_code, upload_data))

            # 10. POST /api/knowledge/upload
            pdf_content = b"%PDF-1.4\n1 0 obj\n<<>>\nendobj\ntrailer\n<< /Root 1 0 R >>\n%%EOF"
            r = await client.post("/api/knowledge/upload", files={"file": ("manual.pdf", pdf_content, "application/pdf")})
            knowledge_data = r.json()
            endpoints_results.append(("POST", "/api/knowledge/upload", r.status_code, knowledge_data))

            # 11. GET /api/artifacts/{id}
            artifact_id = task_completed_data["artifacts"][0]["artifact_id"] if task_completed_data.get("artifacts") else None
            if artifact_id:
                r = await client.get(f"/api/artifacts/{artifact_id}")
                artifact_meta = r.json()
                endpoints_results.append(("GET", f"/api/artifacts/{artifact_id}", r.status_code, f"type: {artifact_meta.get('artifact_type')}"))
            else:
                endpoints_results.append(("GET", "/api/artifacts/{id}", 404, "No artifact created"))

            # 12. POST /api/pid/analyze (use real PNG image via Pillow)
            buf = io.BytesIO()
            Image.new("RGB", (100, 100), color="white").save(buf, format="PNG")
            png_bytes = buf.getvalue()
            r = await client.post("/api/pid/analyze", files={"file": ("pid_test.png", png_bytes, "image/png")})
            pid_data = r.json()
            endpoints_results.append(("POST", "/api/pid/analyze", r.status_code, f"task_id: {pid_data.get('task_id')}"))

            print("\n=== STEP 5: SOVEREIGNTY CHECK ===")
            r = await client.get("/api/monitoring/sovereignty")
            sov = r.json()
            print("Sovereignty state:", json.dumps(sov, indent=2))

            print("\n=== STEP 8: END-TO-END STUB WORKFLOW VERIFICATION ===")
            print("Task ID:", task_id)
            print("Final Current State:", task_completed_data.get("current_state"))
            print("Final Result:", task_completed_data.get("final_result"))
            print("Artifact ID:", artifact_id)
            print("Artifact Manifest:", task_completed_data.get("artifacts"))

            if artifact_id:
                art_path = Path(task_completed_data["artifacts"][0]["path"])
                print("Artifact File Path:", art_path)
                print("File Exists:", art_path.exists())
                print("File Size (bytes):", art_path.stat().st_size if art_path.exists() else 0)

            print("\n=== STEP 9: ZERO-EGRESS & AUDIT CHECK ===")
            audit_rows = await app.state.repository.list_audit()
            egress_denied_rows = [row for row in audit_rows if row.get("category") == "EGRESS_DENIED"]
            provider_call_rows = [row for row in audit_rows if row.get("category") == "PROVIDER_CALL"]
            print(f"Total Audit Rows: {len(audit_rows)}")
            print(f"EGRESS_DENIED Rows: {len(egress_denied_rows)}")
            print(f"PROVIDER_CALL Rows: {len(provider_call_rows)}")

        print("\nEndpoint results summary:")
        for method, path, status, note in endpoints_results:
            print(f"{method:4s} {path:40s} -> Status {status} | {note}")

if __name__ == "__main__":
    asyncio.run(main())
