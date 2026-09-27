# Indigent-visuals

Architecture diagrams for this repository, generated with the **Archify** skill.
Each diagram is a standalone HTML file — no server, no network, no build step. Open it
directly in a browser.

| File | What it is |
| --- | --- |
| `indigent-architecture.html` | **The deliverable.** Component map of the air-gapped backend. |
| `indigent-architecture.architecture.json` | Editable source specification (the thing to change). |
| `indigent-architecture.visual-check.json` | Machine validation receipt for the render. |
| `indigent-architecture.visual-check.html` | Contact sheet of all captures. |
| `*.visual-check.*.png` | Rendered captures, light and dark, at 1440x900 and 2048x1320. |

## What the diagram asserts

It is grounded in this checkout, not in prose. Every node carries up to three `sources`
citations (`path` + `line` + `label`), and the renderer verified all **15** of them against
the working tree at the pinned revision before writing the HTML.

Claims worth spot-checking, because they are the ones that carry the security argument:

- `app/runtime/executor.py:20` and `:23` — the tool runtime independently re-checks the
  policy decision and the allow-list. Model output proposes a tool; it never authorizes one.
- `app/runtime/sandbox.py:46` — `network_mode="none"`, in both local and groq mode.
- `app/main.py:58` — the process-wide egress guard is installed once at startup.
- `app/agent/router.py:30` — the model router, not Ollama, is what reads `INFERENCE_MODE`
  and chooses a provider. That is why the Groq edge leaves the orchestrator.
- `app/core/audit.py:33` and `app/net/sovereignty.py:52` — append-only evidence and the
  sovereignty snapshot.

## Regenerating after a code change

The JSON is the source of truth. Edit it, then re-validate and re-render:

```powershell
$a = "C:\Users\SOHAM\.agents\skills\archify\bin\archify.mjs"
node $a validate architecture "Indigent-visuals\indigent-architecture.architecture.json" --quality showcase --repo-root . --json
node $a deliver   architecture "Indigent-visuals\indigent-architecture.architecture.json" "Indigent-visuals\indigent-architecture.html" --quality showcase --repo-root . --json
node $a visual-check "Indigent-visuals\indigent-architecture.html" --json
```

`--repo-root .` is what makes the tool verify the `sources` citations against real files.
Drop it and the citations are rendered but unchecked.

Do not skip `validate`. Layout is machine-checked here and it is strict: it caught labels
sitting on top of nodes, an edge routed through three unrelated components, and a page that
overflowed a 1440x900 viewport by 139px. All three were invisible in the JSON.

## Known state

`visualReview` is `pending` in the receipt. The automated browser check passes at all four
viewports in both themes, but nobody has eyeballed the render yet — worth doing once before
this is shown to anyone.
