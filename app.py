"""
Flask front-end for the IGES -> Tubes T converter.

One endpoint does the work: POST /convert with a single file; it streams the
upload to a temp file, converts it to legacy trimmed-surface IGES, and returns
the result as a download. The browser UI converts multiple dropped files by
calling /convert once per file (sequentially), which keeps peak memory low on
the 512 MB instance.
"""
from __future__ import annotations

import gc
import io
import tempfile
from pathlib import Path

from flask import Flask, jsonify, render_template, request, send_file
from werkzeug.utils import secure_filename

from converter import SUPPORTED_EXTS, ConversionError, convert_to_legacy_iges

app = Flask(__name__)
# Tube parts are small; cap uploads so a stray huge file can't blow the box.
app.config["MAX_CONTENT_LENGTH"] = 50 * 1024 * 1024  # 50 MB


@app.get("/")
def index():
    return render_template("index.html")


@app.get("/health")
def health():
    return jsonify(status="ok")


@app.post("/convert")
def convert():
    uploaded = request.files.get("file")
    if uploaded is None or not uploaded.filename:
        return jsonify(error="No file was uploaded."), 400

    safe_name = secure_filename(uploaded.filename) or "part.igs"
    stem = Path(safe_name).stem
    ext = Path(safe_name).suffix.lower()
    if ext not in SUPPORTED_EXTS:
        return (
            jsonify(error=f"Unsupported file type '{ext}'. Use IGS/IGES or STEP."),
            400,
        )

    out_name = f"{stem}_tubesT.igs"
    with tempfile.TemporaryDirectory() as tmp:
        src = Path(tmp) / safe_name
        dst = Path(tmp) / out_name
        uploaded.save(src)  # stream to disk — never hold the upload in memory
        try:
            convert_to_legacy_iges(src, dst)
        except ConversionError as exc:
            return jsonify(error=str(exc)), 422
        except Exception as exc:  # pragma: no cover - unexpected kernel failure
            return jsonify(error=f"Conversion failed: {exc}"), 500
        # Read the (small) result into memory so the temp dir can be cleaned up
        # before Flask streams the response.
        data = dst.read_bytes()

    gc.collect()
    return send_file(
        io.BytesIO(data),
        as_attachment=True,
        download_name=out_name,
        mimetype="application/octet-stream",
    )


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000, debug=True, use_reloader=False)
