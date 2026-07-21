# IGES → Tubes T Converter

A tiny web app: drop Onshape IGS/STEP files in the browser, get back **legacy
trimmed-surface IGES** that Tubes T (and other older tube-CAM) can import.

## Why this exists

Around **18 July 2026** Onshape swapped its IGES export translator from Siemens'
Parasolid translator to **Tech Soft 3D HOOPS Exchange 26.4.0**. The new engine
writes a manifold-solid B-Rep — IGES entity **186** plus analytic surfaces
(**190**/**192**) and topology (502/504/508/510/514). Legacy tube-CAM can't parse
those entities, so imports started failing with no change on our side.

The old engine wrote **trimmed parametric surfaces (entity 144)**, which import
fine. This app reproduces that: it reads the shape with OpenCASCADE and writes
IGES with `write.iges.brep.mode = Faces`, turning each face into a 144 trimmed
surface. Output matches the flavor SolidWorks/Parasolid produced.

## How it works

- `converter.py` — the OpenCASCADE conversion (`convert_to_legacy_iges`).
- `app.py` — Flask; `POST /convert` streams one uploaded file to a temp file,
  converts it, returns the download. `GET /health` for Render health checks.
- `templates/index.html` — drag-and-drop UI; converts multiple files one at a
  time (keeps server memory low) and auto-downloads each result.

Supported inputs: `.igs`, `.iges`, `.step`, `.stp`. Output: `<name>_tubesT.igs`.

## Run locally

Requires Python 3.11 (for the cadquery-ocp wheels).

```bash
python -m venv .venv && .venv/Scripts/activate   # Windows
pip install -r requirements.txt
python app.py          # http://localhost:8000
```

## Deploy to Render

Dashboard-based (no CLI needed):

1. Push this folder to a new GitHub repo.
2. Render dashboard → **New +** → **Blueprint** → pick the repo (it reads
   `render.yaml`). Or **New + → Web Service** and set:
   - Build: `pip install -r requirements.txt`
   - Start: `gunicorn app:app --workers 1 --threads 2 --timeout 180 --bind 0.0.0.0:$PORT`
   - Env: `PYTHON_VERSION = 3.11.9`
3. Deploy. First build is slow (downloads OpenCASCADE wheels).

### Memory

A conversion peaks at ~200 MB RSS, so it fits Render's 512 MB instance. It's a
**separate** service on purpose — keeping OpenCASCADE out of `accora-fab-exporter`
so it can't push that app over its own 512 MB ceiling. One sync worker; files are
converted sequentially.

### Slimming later (optional)

`cadquery-ocp` declares `vtk` and `matplotlib` as deps; they're installed but not
imported at runtime (verified: peak RSS unaffected). If build time/image size
matters, try `pip install --no-deps cadquery-ocp numpy` and confirm
`from OCP.IGESControl import IGESControl_Writer` still imports.
