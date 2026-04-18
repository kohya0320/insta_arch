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

LANDSCAPE STYLE — @gorpcore.jpeg aesthetic for the nature/background:
- Raw, untouched wilderness at a scale that makes humans feel irrelevant
- Earthy, muted-but-rich color palette: weathered rock, moss-covered stone, deep forest green, raw soil, lichen grey
- Terrain feels REAL and documentary — not a postcard, not a fantasy — authentic textures, worn surfaces, organic imperfections
- The landscape has weight and permanence — ancient, indifferent to the building beside it
- Depth: foreground rocks or vegetation, mid-ground building, distant mountain or ocean or forest stretching to horizon

STRICT VISUAL RULES:
- ABSOLUTELY NO clouds, NO overcast sky, NO grey sky — only the exact weather specified above
- PHYSICS: the building must visibly sit on, into, or emerge from the ground — every volume has structural logic
- Maximum 1-2 tiny human figures, very far away as scale reference only — NOT groups, NOT crowds
- Landscape fills 50%+ of frame — vast, ancient, untamed
- One strong directional light — hard shadows, deep blacks
- RICH but EARTHY COLORS — muted natural tones for the landscape, strong saturated light for sky and shadows
- Describe the building's exact shape and mass — how it meets the terrain
- Real material textures: raw concrete grain, stone surface, weathered corten steel, aged timber
- One small imperfection: moss on concrete, water stain on facade, lichen on stone
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


# ━━━ 10インテリア展開（@matitectura スタイル）━━━
EXPAND_ANGLES = [
    (
        "Grand Entry Hall",
        "monumental entrance hall, 9-meter raw concrete ceiling, 30-meter long axis, floor-to-ceiling glass wall at far end framing the wild landscape beyond, polished concrete floor reflecting the shaft of light, single oblique beam of sunlight cutting diagonally across the space, deep shadow in corners, one minimal concrete bench, two tiny human silhouettes show the colossal scale",
        "ultra-wide 14mm, one oblique light shaft, museum entry scale"
    ),
    (
        "Main Living Hall",
        "vast triple-height living hall, 8-meter raw concrete ceilings, 25-meter long room, entire wall of floor-to-ceiling glass facing dramatic landscape, raw concrete walls and polished stone floor, Minotti sectional in bouclé placed as a single island in the vast space, one 4-meter mature olive tree in a raw concrete planter, afternoon light shaft raking the floor at a low angle, deep shadow at ceiling",
        "ultra-wide 14mm, afternoon raking light, gallery scale"
    ),
    (
        "Library & Study",
        "double-height library, 6-meter raw concrete walls floor to ceiling lined with books, one full glass wall facing untamed landscape, a single long raw timber reading table centred, Arco floor lamp casting warm pool of light, late afternoon oblique sunlight cutting across the book spines, dust particles visible in the light beam, deep silence",
        "wide 20mm, warm oblique light, intimate within monumental scale"
    ),
    (
        "Master Bedroom",
        "enormous master suite, 6-meter raw concrete ceilings, 16-meter wide room, full glass wall spanning entire width with dawn landscape beyond — the wilderness is the headboard, platform bed of aged walnut centred in the vast space, a single shaft of pale dawn light across the floor, Dedar linen slightly crumpled, one mature fiddle-leaf fig 4m tall in corner, deep silence and restraint",
        "wide 20mm, soft dawn light shaft, vast negative space"
    ),
    (
        "Bathroom — Stone & Water",
        "monumental bathroom, 6-meter raw concrete ceiling, 14-meter long room, entire glass wall facing untouched wild landscape, single freestanding stone bath centred like a sculpture, Nero Marquina marble walls, shallow water on the floor reflecting ceiling, morning mist visible outside, one beeswax candle half-burned on stone ledge, absolute silence",
        "wide 20mm, soft diffused light, stone and water reflection"
    ),
    (
        "Kitchen & Dining",
        "vast kitchen and dining hall, 7-meter concrete ceilings, 22-meter long space, Poliform stone island running 6 meters, 16-seat raw timber dining table under cluster of Bocci pendants, full glass wall to landscape, evening light warm on stone surfaces, shadow deep at ceiling, ultra-sharp: stone grain, wood texture, pendant reflections",
        "wide 20mm, warm evening light, Michelin kitchen scale"
    ),
    (
        "Meditation & Spa",
        "monumental spa hall, 7-meter raw concrete ceiling, 20-meter long room, full glass wall facing ancient untamed wilderness, two stone basins centred 6 meters apart, private hammam chamber behind frosted glass, plunge pool inset flush with floor, hanging dried eucalyptus, morning mist pressing against the glass outside, one candle, absolute stillness",
        "wide 18mm, soft diffused spa light, ancient stone and concrete"
    ),
    (
        "Corridor & Circulation",
        "long circulation corridor, 5-meter raw concrete ceiling, 30-meter length, one continuous slot skylight running full length casting a narrow blade of sunlight along the floor, rough concrete walls both sides, polished concrete floor as mirror, at the far end a full glass wall opening to wild landscape — light at the end of the tunnel composition",
        "35mm, blade of skylight, long perspective compression"
    ),
    (
        "Terrace — Interior Edge",
        "covered terrace at the boundary between inside and outside, 4-meter raw concrete soffit, the floor continuing seamlessly from interior to exterior, infinity edge dissolving into the vast landscape below, two minimal outdoor loungers in weathered teak, deep saturated blue sky or golden sunset beyond — no clouds, one glass of water on a stone ledge, the building and wilderness meet here",
        "wide 20mm, interior-exterior threshold, deep saturated sky"
    ),
    (
        "Material Detail — Light & Texture",
        "extreme close-up architectural detail inside the building, same raw concrete or stone or aged timber, a single dramatic shaft of natural light raking across the surface at a low angle — every pour line in concrete hyper-visible, every grain in wood, every crystal in stone, deep sharp shadow edge, a small imperfection: a crack, a stain, a mineral deposit — the material is the subject",
        "50mm, raking light, hyper-sharp material texture"
    ),
    (
        "Wide Exterior — Full Context",
        "ultra-wide establishing shot, full building visible in its landscape, @gorpcore.jpeg wilderness — ancient weathered terrain, earthy muted tones, foreground rock or vegetation in sharp focus, building in mid-ground, distant horizon stretching vast, deep saturated blue sky or golden sunset or snow — zero clouds, 2 tiny human silhouettes at entrance prove massive scale, building obeys physics — sits on or into the terrain",
        "ultra-wide 14-16mm, full landscape context, @gorpcore.jpeg terrain"
    ),
    (
        "Aerial — Bird's Eye",
        "aerial drone shot from directly above at 45 degrees, same building seen from high altitude, surrounded by its epic landscape — coast, forest, desert, mountain — @gorpcore.jpeg wilderness scale, earthy terrain, deep saturated blue sky zero clouds, building's form and footprint fully revealed from above, tiny human silhouettes show enormous scale",
        "aerial 45-degree, bird's eye, landscape scale, deep blue sky"
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
- LANDSCAPE (@gorpcore.jpeg aesthetic): raw untouched wilderness, earthy muted-but-rich palette (weathered rock, moss, lichen, deep forest green, raw soil), terrain feels ancient and documentary — authentic organic textures, NOT a postcard. Foreground terrain detail, distant horizon.
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
