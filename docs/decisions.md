# Decisions

- Step 10: Joy-owned real modules are absent from this checkout, so the 22-case `needs_models` acceptance matrix is intentionally gated and reports the missing merge as a Joy-owned blocker; stubs are never used to claim integration coverage.

- Step 9: Compose runs only `qdrant/qdrant:v1.19.1` (resolved pinned tag; Docker Hub listed it at implementation time) with its REST port bound to 127.0.0.1; host firewall controls remain documented, manual deployment actions.

- Step 0: `JOY_MODULES=real` fails explicitly until Joy's owned modules are supplied.
- Step 1: persistence uses one short-lived SQLite connection per operation with WAL and a 5-second busy timeout.
- Step 4: uploads stream in 1 MiB chunks; Office validation checks ZIP magic without loading upload content into memory.
- Step 5: generator specs are bounded to 1 MiB and 200 DOCX sections to prevent unbounded artifact construction.
- Step 6: executable code and tests run only through a Docker container with the locked sandbox controls; Docker/image failures return `SANDBOX_UNAVAILABLE` without host fallback.
- Step 7: sovereignty mode is derived exclusively from settings; the process egress guard is defense-in-depth and does not replace OS or container network controls.
- Step 8: readiness checks use only configured loopback Ollama/Qdrant URLs with a two-second timeout; their status is informational while SQLite, Docker, and the sandbox image gate readiness.
2026-09-25 — Step 2: task lifecycle is detached with `asyncio.create_task`; persisted EventBus is the source of truth for SSE replay.
2026-09-25 — Phase 1 Joy: providers use HTTP contracts through `httpx`; Ollama/Groq SDKs are intentionally not imported, matching the repository security rule.
