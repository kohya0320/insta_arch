from flask import Flask, render_template, jsonify, request
from google import genai
from google.genai import types as genai_types
import os, uuid, requests, random, re, json, threading

app = Flask(__name__)

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
IG_ACCESS_TOKEN = os.environ.get("IG_ACCESS_TOKEN", "")
IG_USER_ID = os.environ.get("IG_USER_ID", "")

client = genai.Client(api_key=GEMINI_API_KEY)

# static/images ディレクトリを確実に作成（gunicorn起動時も対応）
_base_dir = os.path.dirname(os.path.abspath(__file__))
os.makedirs(os.path.join(_base_dir, "static", "images"), exist_ok=True)

# ジョブ管理
jobs = {}

def generate_concept_and_prompt(index):
    """Geminiが建物コンセプトをゼロから発明し、プロンプトまで生成"""
    import time

    climates = [
        "Arctic tundra", "tropical rainforest", "Sahara desert", "Norwegian fjord",
        "Japanese cedar forest", "Scottish highland", "Patagonian steppe", "Icelandic lava field",
        "Maldivian atoll", "Swiss alpine", "Amazon river delta", "Mongolian steppe",
        "New Zealand volcanic coast", "Chilean Atacama", "Canadian Rockies",
        "Indonesian jungle", "Moroccan atlas mountains", "Australian outback",
        "Finnish lake district", "Tibetan plateau"
    ]
    forms = [
        "a single monolithic concrete slab elevated on pilotis", "stacked shifted rectangular volumes",
        "carved directly into cliff face", "a ring encircling a void",
        "a bridge spanning two rock faces", "terraced platforms descending a hillside",
        "a buried bunker with only skylights above ground", "a transparent glass box on a plinth",
        "folded concrete planes like origami", "a helix of interconnected levels",
        "a series of parallel walls offset in depth", "a monolithic black stone mass with carved voids",
        "a crescent-shaped plan following the terrain contour", "mirrored surfaces that dissolve into landscape",
        "a cluster of towers connected by aerial walkways", "a single long horizontal bar elevated above terrain"
    ]
    weathers = [
        "deep saturated cobalt blue sky, harsh direct sun, razor-sharp shadows, absolutely zero clouds",
        "heavy snowfall, thick snowflakes mid-air, deep saturated navy blue sky, warm amber glow from windows",
        "blazing golden sunset, sky deep saturated orange-magenta gradient, zero clouds, vivid warm light",
        "forest rain, diagonal rain streaks visible, every surface wet and glistening, rich saturated deep greens, low mist",
        "pre-dawn blue hour, deep saturated indigo sky, thin line of warm light on horizon, amber interior glow",
        "golden sunrise, deep saturated cerulean blue sky, long hard shadows, vivid warm light from one side",
    ]

    climate = random.choice(climates)
    form = random.choice(forms)
    weather = random.choice(weathers)

    for model in ["gemini-2.5-flash", "gemini-1.5-flash-latest"]:
        for attempt in range(3):
            try:
                response = client.models.generate_content(
                    model=model,
                    contents=f"""You are simultaneously a radical architect and a world-class architectural photographer. Your job: INVENT a completely original building and write a photorealistic image generation prompt for it.

INVENTION BRIEF:
- Climate/Location seed: {climate}
- Architectural form seed: {form}
- Weather: {weather}

STEP 1 — Invent the building:
- Name it (3-5 words, evocative)
- Design a building with the aesthetic of a world-class museum, cultural institution, or art gallery — monumental, brutalist or minimalist, institutional gravitas. NOT a house, NOT a hotel, NOT a villa.
- Inspired by @matitectura: raw concrete, bold geometric volumes, massive scale, severe beauty, the building looks like it belongs in MoMA or on the cover of Wallpaper*.
- The building CANNOT EXIST anywhere else on earth — terrain and architecture are inseparable.
- PHYSICS: every element must be visibly supported. Cantilevers must have visible structural logic. NO floating. NO impossible structures.
- Scale: large enough for 15 people, multiple wings, sprawling footprint.
- Materials echo the landscape.

STEP 2 — Write the photorealistic image prompt:
Core idea: CONTRAST AND HARMONY — precise man-made geometry against wild vast nature. Neither dominates.

STRICT VISUAL RULES:
- ABSOLUTELY NO clouds, NO overcast sky, NO grey sky, NO haze — only the exact weather specified above
- PHYSICS: the building must visibly sit on, into, or emerge from the ground — every volume has structural logic
- Maximum 1-2 tiny human figures, very far away as scale reference only — NOT groups, NOT crowds
- Landscape fills 50%+ of frame — epic, untamed, vast
- One strong directional light — hard shadows, deep blacks
- RICH SATURATED COLORS — full tonal range, vivid, properly exposed, no blown-out whites
- Describe the building's exact shape and mass — how it meets the terrain
- Real material textures: raw concrete grain, stone surface, weathered corten steel, aged timber
- One small imperfection: moss on concrete, water stain on facade
- Wide establishing shot, 16-24mm

OUTPUT FORMAT (exactly):
NAME: [building name]
PROMPT: [200-250 word photorealistic image prompt ending with: "editorial architectural photograph, Hasselblad X2D, 24mm f/8, correct exposure, rich saturated colors, ultra-sharp focus, natural film grain, NOT a 3D render NOT AI art, NOT a painting, photorealistic 8K"]"""
                )
                text = response.text.strip()
                name_match = re.search(r'NAME:\s*(.+)', text)
                prompt_match = re.search(r'PROMPT:\s*([\s\S]+)', text)
                name = name_match.group(1).strip() if name_match else f"Architecture {index+1}"
                prompt = prompt_match.group(1).strip() if prompt_match else text
                return name, prompt
            except Exception as e:
                print(f"[Gemini] {model} attempt {attempt+1} failed: {e}")
                time.sleep(5)
    return f"Architecture {index+1}", "Museum-like brutalist architecture, raw concrete, natural landscape, photorealistic 8K"


def generate_image(prompt):
    """Imagen 4 で画像生成"""
    import time
    clean = re.sub(r'--ar \S+', '', prompt).strip()

    for attempt in range(3):
        try:
            print(f"[Image] Imagen 4 attempt {attempt+1}")
            response = client.models.generate_images(
                model="imagen-4.0-generate-001",
                prompt=clean,
                config=genai_types.GenerateImagesConfig(
                    number_of_images=1,
                    aspect_ratio="3:4",
                )
            )
            img_bytes = response.generated_images[0].image.image_bytes
            base_dir = os.path.dirname(os.path.abspath(__file__))
            filename = f"{uuid.uuid4().hex}.jpg"
            path = os.path.join(base_dir, "static", "images", filename)
            with open(path, "wb") as f:
                f.write(img_bytes)
            print(f"[Image OK] {filename}")
            return filename
        except Exception as e:
            print(f"[Image Error] attempt {attempt+1}: {e}")
            time.sleep(10)
    raise RuntimeError("generate_image failed after 3 attempts")


def generate_caption(name, prompt):
    """英語キャプション生成"""
    import time
    for model in ["gemini-2.5-flash", "gemini-1.5-flash-latest"]:
        for attempt in range(2):
            try:
                response = client.models.generate_content(
                    model=model,
                    contents=f"""Write a short Instagram caption in English for this architectural image.
Concept: {name}
Visual: {prompt[:150]}

Rules:
- 2-3 sentences, cinematic and evocative
- Mention the relationship between the building and its natural setting
- NO hashtags in the body text
- Add 6 relevant hashtags on a new line at the end

Output only caption + hashtags."""
                )
                return response.text.strip()
            except Exception as e:
                print(f"[Caption] {model} attempt {attempt+1} failed: {e}")
                time.sleep(3)
    return f"Where architecture meets nature.\n\n#architecture #brutalism #design #architecturephotography #minimal #concrete"


def process_one(job_id, i):
    """1枚を処理してjobsに追加"""
    try:
        name, prompt = generate_concept_and_prompt(i)
        print(f"[Job {job_id}] {i+1}/5 concept: {name}")
        filename = generate_image(prompt)
        caption = generate_caption(name, prompt)
        if filename:
            jobs[job_id]["results"].append({
                "style": name,
                "prompt": prompt,
                "image": filename,
                "caption": caption,
            })
            print(f"[Job {job_id}] {i+1}/5 DONE: {name}")
        else:
            print(f"[Job {job_id}] {i+1}/5 FAILED")
    except Exception as e:
        print(f"[Job {job_id}] {i+1} error: {e}")
        jobs[job_id].setdefault("errors", []).append(str(e))


def run_job(job_id):
    """5枚を順番に生成"""
    import time
    jobs[job_id]["status"] = "running"
    jobs[job_id]["started_at"] = time.time()
    jobs[job_id]["current"] = 0
    durations = []
    for i in range(5):
        jobs[job_id]["current"] = i + 1
        t0 = time.time()
        process_one(job_id, i)
        durations.append(time.time() - t0)
        jobs[job_id]["avg_duration"] = sum(durations) / len(durations)
    jobs[job_id]["status"] = "done"
    print(f"[Job {job_id}] All done: {len(jobs[job_id]['results'])}/5")


# ━━━ 10アングル展開 ━━━
EXPAND_ANGLES = [
    (
        "Wide Exterior — Golden Hour",
        "full building exterior, wide angle, golden hour, long hard shadows, deep saturated orange sky, zero clouds, same facade materials as original",
        "wide-angle 16mm exterior, f/8, golden hour, rich saturated colors"
    ),
    (
        "Exterior — Snow & Glow",
        "same building exterior in heavy snowfall, thick snowflakes falling mid-air, snow on every surface, warm amber interior glow through glass, deep saturated navy blue sky — absolutely NO grey clouds",
        "snowfall 35mm, warm vs cold color contrast, deep blue sky"
    ),
    (
        "Night Exterior — Illuminated",
        "same building at night, warm amber light from every window, reflected in pool or wet stone, deep blue-black sky, stars visible, zero clouds",
        "blue-black night, long exposure, warm glow against dark sky"
    ),
    (
        "Aerial Overview",
        "aerial drone view, same building seen from above at 45 degrees, surrounded by epic natural landscape — coast, forest, desert, or mountain — deep saturated blue sky, zero clouds, shows massive scale",
        "bird's eye 45-degree, deep blue sky, landscape context"
    ),
    (
        "Interior — Grand Hall",
        "vast triple-height gallery hall, 8-meter raw concrete ceilings, 25-meter long room, entire wall of floor-to-ceiling glass opening to dramatic landscape, @matitectura aesthetic — raw concrete walls and floor, minimal furniture, one oblique shaft of sunlight cutting across the space, deep shadow in corners, ultra-sharp material detail: every concrete pour line visible, every reflection precise",
        "ultra-wide 14mm, one strong oblique light shaft, museum scale, ultra-sharp"
    ),
    (
        "Interior — Master Suite at Dawn",
        "enormous master suite, 6-meter raw concrete ceilings, full glass wall with dawn landscape beyond, platform bed centred, warm aged walnut floor, one oblique beam of dawn light across floor, ultra-sharp material textures: concrete grain visible, wood grain visible, glass reflections precise",
        "wide 20mm, dawn light shaft, ultra-sharp detail, museum-like severity"
    ),
    (
        "Interior — Dining & Kitchen",
        "vast open-plan kitchen and dining, 7m concrete ceilings, 20-meter long room, stone island, full glass wall to landscape, cluster of pendant lights, warm oak and stone, evening light, ultra-sharp every detail: stone grain, wood texture, glass reflection",
        "wide 20mm, warm layered light, ultra-sharp material detail"
    ),
    (
        "Interior — Spa",
        "monumental spa, 7m raw concrete ceiling, entire glass wall facing untamed nature, two stone baths centred, marble walls, plunge pool, morning mist outside, soft diffused light, ultra-sharp material textures: stone veining, concrete grain, water surface",
        "wide 18mm, soft diffused light, ultra-sharp stone and concrete detail"
    ),
    (
        "Terrace & Pool — Dusk",
        "terrace with infinity pool, same architectural style, dusk sky deep saturated purple to orange gradient, zero clouds, pool water perfectly still mirror reflection, outdoor minimal furniture, ultra-sharp reflections and material detail",
        "low angle at pool level, dusk, deep saturated sky, ultra-sharp reflection"
    ),
    (
        "Detail — Light & Material",
        "architectural close-up detail, same building materials — raw concrete, stone, aged timber, glass — single dramatic shaft of natural light cutting across surface, every texture hyper-visible: concrete aggregate, wood grain, stone veining, sharp shadow edge",
        "50mm macro-like detail, chiaroscuro, ultra-sharp texture"
    ),
]


def generate_expand_prompt(original_prompt, angle_name, angle_hint, camera_note):
    """アングルごとの詳細プロンプトを生成"""
    import time
    contents = f"""You are a world-class architectural photographer. Your images look like REAL photographs — never AI, never renders.

Original building (keep SAME style, materials, exterior form):
\"\"\"{original_prompt[:350]}\"\"\"

Create a prompt for: "{angle_name}"
Scene direction: {angle_hint}
Camera note: {camera_note}

STRICT RULES:
- SAME building — same materials, same character, new angle only
- ABSOLUTELY NO clouds, NO overcast, NO grey sky — only clear sky / snow / golden sunset / forest rain / night
- PHYSICS: building must obey gravity — every element visibly supported, no floating
- Maximum 1-2 tiny human figures as scale reference only — NOT groups
- INTERIORS: @matitectura aesthetic — raw concrete or stone, floor-to-ceiling glass framing wild landscape, one strong oblique light shaft, ultra-sharp material detail (every pour line in concrete, every grain in wood, every vein in stone must be visible)
- MASSIVE SCALE — 7-8m ceilings, 20m+ rooms, museum/gallery proportions
- Quality furniture at grand scale (Minotti, Poliform, Cassina), honed stone (travertine, Calacatta, Nero Marquina), mature indoor trees
- Lived-in imperfections: a half-burned candle, a crumpled linen throw — NOT sterile showroom
- RICH SATURATED COLORS — full tonal range, correct exposure, no blown-out whites
- End: "editorial architectural photograph, Hasselblad X2D, {camera_note}, correct exposure, rich saturated colors, ultra-sharp focus, natural film grain, NOT a 3D render NOT AI art, NOT a painting, photorealistic 8K"

Output ONLY the prompt. 200-250 words."""
    for model in ["gemini-2.5-flash", "gemini-1.5-flash-latest"]:
        for attempt in range(2):
            try:
                response = client.models.generate_content(model=model, contents=contents)
                return response.text.strip()
            except Exception as e:
                print(f"[ExpandPrompt] {model} attempt {attempt+1} failed: {e}")
                time.sleep(5)
    return f"{angle_name} of museum-like brutalist architecture, photorealistic 8K"


def run_expand_job(job_id, original_prompt, total):
    """10アングルを順番に生成"""
    import time
    jobs[job_id]["status"] = "running"
    jobs[job_id]["started_at"] = time.time()
    jobs[job_id]["current"] = 0
    durations = []
    for i, (angle_name, angle_hint, camera_note) in enumerate(EXPAND_ANGLES):
        jobs[job_id]["current"] = i + 1
        t0 = time.time()
        try:
            prompt = generate_expand_prompt(original_prompt, angle_name, angle_hint, camera_note)
            print(f"[Expand {job_id}] {i+1}/{total} prompt ready")
            filename = generate_image(prompt)
            if filename:
                jobs[job_id]["results"].append({
                    "style": angle_name,
                    "prompt": prompt,
                    "image": filename,
                    "caption": "",
                })
                print(f"[Expand {job_id}] {i+1}/{total} DONE")
        except Exception as e:
            print(f"[Expand {job_id}] {i+1} error: {e}")
        durations.append(time.time() - t0)
        jobs[job_id]["avg_duration"] = sum(durations) / len(durations)
    jobs[job_id]["status"] = "done"
    print(f"[Expand {job_id}] All done: {len(jobs[job_id]['results'])}/{total}")


@app.route("/")
def index():
    return render_template("index.html")

@app.route("/api/generate", methods=["POST"])
def generate():
    job_id = uuid.uuid4().hex
    jobs[job_id] = {"status": "running", "results": [], "current": 0, "started_at": 0, "avg_duration": 0}
    t = threading.Thread(target=run_job, args=(job_id,), daemon=True)
    t.start()
    return jsonify({"job_id": job_id})

@app.route("/api/status/<job_id>")
def status(job_id):
    if job_id not in jobs:
        return jsonify({"error": "not found"}), 404
    job = jobs[job_id]
    return jsonify({
        "status": job["status"],
        "results": job["results"],
        "count": len(job["results"]),
        "current": job.get("current", 0),
        "avg_duration": job.get("avg_duration", 0),
        "started_at": job.get("started_at", 0),
        "errors": job.get("errors", []),
    })

@app.route("/api/expand", methods=["POST"])
def expand():
    data = request.json
    original_prompt = data.get("prompt", "")
    total = len(EXPAND_ANGLES)
    job_id = uuid.uuid4().hex
    jobs[job_id] = {"status": "running", "results": [], "current": 0, "started_at": 0, "avg_duration": 0, "total": total}
    t = threading.Thread(target=run_expand_job, args=(job_id, original_prompt, total), daemon=True)
    t.start()
    return jsonify({"job_id": job_id, "total": total})

@app.route("/api/post", methods=["POST"])
def post():
    data = request.json
    caption = data.get("caption")
    image_url = data.get("image_url")

    if not IG_ACCESS_TOKEN or not IG_USER_ID:
        return jsonify({"error": "Instagram credentials not configured"}), 400

    try:
        import time
        container_res = requests.post(
            f"https://graph.instagram.com/v21.0/{IG_USER_ID}/media",
            params={"image_url": image_url, "caption": caption, "access_token": IG_ACCESS_TOKEN}
        )
        cdata = container_res.json()
        if "id" not in cdata:
            return jsonify({"error": str(cdata)}), 500
        time.sleep(5)
        pub_res = requests.post(
            f"https://graph.instagram.com/v21.0/{IG_USER_ID}/media_publish",
            params={"creation_id": cdata["id"], "access_token": IG_ACCESS_TOKEN}
        )
        pdata = pub_res.json()
        if "id" not in pdata:
            return jsonify({"error": str(pdata)}), 500
        return jsonify({"success": True, "post_id": pdata["id"]})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    base_dir = os.path.dirname(os.path.abspath(__file__))
    os.makedirs(os.path.join(base_dir, "static", "images"), exist_ok=True)
    app.run(debug=False, port=5002, threaded=True)
