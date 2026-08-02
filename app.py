import os
import json
import logging
from pathlib import Path
from flask import Flask, render_template, request, jsonify, send_from_directory
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

from extractors import gemini, groq

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 16 * 1024 * 1024  # 16 MB max upload
UPLOAD_FOLDER = Path("uploads")
UPLOAD_FOLDER.mkdir(exist_ok=True)
IMAGES_FOLDER = Path("images")
RESULTS_FOLDER = Path("results")

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def load_cached_data():
    gemini_data = {}
    groq_data = {}
    
    gemini_file = RESULTS_FOLDER / "gemini.json"
    groq_file = RESULTS_FOLDER / "groq.json"
    
    if gemini_file.exists():
        try:
            with open(gemini_file, "r", encoding="utf-8") as f:
                gemini_data = json.load(f)
        except Exception as e:
            logger.error("Error reading gemini.json: %s", e)
            
    if groq_file.exists():
        try:
            with open(groq_file, "r", encoding="utf-8") as f:
                groq_data = json.load(f)
        except Exception as e:
            logger.error("Error reading groq.json: %s", e)
            
    return gemini_data, groq_data


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/samples")
def get_samples():
    """List available sample bills in images/ directory."""
    if not IMAGES_FOLDER.exists():
        return jsonify([])
    
    valid_exts = {".jpg", ".jpeg", ".png"}
    samples = []
    gemini_data, groq_data = load_cached_data()
    
    for p in sorted(IMAGES_FOLDER.iterdir()):
        if p.suffix.lower() in valid_exts:
            stem = p.stem
            samples.append({
                "id": stem,
                "filename": p.name,
                "url": f"/images/{p.name}",
                "has_cached": stem in gemini_data or stem in groq_data
            })
            
    return jsonify(samples)


@app.route("/images/<filename>")
def serve_image(filename):
    return send_from_directory(IMAGES_FOLDER, filename)


@app.route("/uploads/<filename>")
def serve_upload(filename):
    return send_from_directory(UPLOAD_FOLDER, filename)


@app.route("/api/compare/<img_id>")
def get_cached_comparison(img_id):
    """Return pre-computed extractions for sample bills."""
    gemini_data, groq_data = load_cached_data()
    
    return jsonify({
        "image_id": img_id,
        "gemini": gemini_data.get(img_id),
        "groq": groq_data.get(img_id)
    })


@app.route("/api/extract", methods=["POST"])
def extract_live():
    """Run live extractions on uploaded or sample image."""
    img_path = None
    img_url = None
    
    if "file" in request.files and request.files["file"].filename != "":
        file = request.files["file"]
        filename = file.filename
        dest = UPLOAD_FOLDER / filename
        file.save(dest)
        img_path = str(dest)
        img_url = f"/uploads/{filename}"
    elif request.is_json and request.json.get("sample_id"):
        sample_id = request.json.get("sample_id")
        for ext in [".jpg", ".jpeg", ".png"]:
            candidate = IMAGES_FOLDER / f"{sample_id}{ext}"
            if candidate.exists():
                img_path = str(candidate)
                img_url = f"/images/{candidate.name}"
                break

    if not img_path or not os.path.exists(img_path):
        return jsonify({"error": "No valid image provided"}), 400

    results = {}
    
    # Run Gemini extraction
    try:
        results["gemini"] = gemini.extract_bill(img_path)
    except Exception as e:
        logger.error("Live Gemini extraction failed: %s", e)
        results["gemini"] = {"error": str(e)}

    # Run Groq extraction
    try:
        results["groq"] = groq.extract_bill(img_path)
    except Exception as e:
        logger.error("Live Groq extraction failed: %s", e)
        results["groq"] = {"error": str(e)}

    results["image_url"] = img_url
    return jsonify(results)


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
