from flask import Flask, render_template, jsonify, request
from google import genai
import os, uuid, requests, random, re, json, threading

app = Flask(__name__)

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
FAL_KEY = os.environ.get("FAL_KEY", "")
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

    # 多様性のためのランダムシード要素
    climates = ["Arctic tundra", "tropical rainforest", "Sahara desert", "Norwegian fjord", "Japanese cedar forest",
                "Scottish highland", "Patagonian steppe", "Icelandic lava field", "Maldivian atoll", "Swiss alpine",
                "Amazon river delta", "Mongolian steppe", "New Zealand volcanic coast", "Chilean Atacama", "Canadian Rockies",
                "Indonesian jungle", "Moroccan atlas mountains", "Australian outback", "Finnish lake district", "Tibetan plateau"]
    forms = ["a continuous spiral ramp", "stacked shifted boxes", "a single massive cantilever", "a ring or torus shape",
             "carved directly into rock", "suspended by cables", "floating on water", "buried underground with only skylights",
             "a bridge spanning a void", "a cluster of pods connected by walkways", "a helix tower", "folded planes of concrete",
             "a series of arches", "mirrored glass that disappears into landscape", "a crescent moon shape",
             "terraced into a hillside", "a monolithic black block", "transparent glass cube", "a series of tilted walls"]
    weathers = [
        "deep saturated cobalt blue sky, harsh direct sun, razor-sharp shadows, no clouds, vivid colors, properly exposed",
        "heavy snowfall, thick snowflakes mid-air, deep saturated navy sky, warm amber glow from windows, vivid color contrast",
        "blazing golden sunset, sky deep saturated orange-magenta gradient, no clouds, vivid warm light, properly exposed",
        "forest rain, diagonal rain streaks, every surface wet glistening, rich saturated deep greens, low mist between trees",
        "pre-dawn blue hour, deep saturated indigo sky, first light on horizon, warm lights inside building glowing amber",
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

INVENTION BRIEF (use these as creative seeds, not constraints):
- Climate/Location seed: {climate}
- Architectural form seed: {form}
- Weather: {weather}

STEP 1 — Invent the building:
- Name it (3-5 words, evocative)
- Design something that has NEVER been built before. Push the concept far.
- The building must feel like it COULD NOT EXIST anywhere else on earth — terrain, climate, and architecture are inseparable.
- Scale: resort for 15 people. Large, sprawling, multiple wings or units.
- Materials must come from or echo the landscape.

STEP 2 — Write the photorealistic image prompt:
Core idea: CONTRAST AND HARMONY — the building is precise and man-made, the landscape is wild and vast. Neither dominates. They are in conversation.

VISUAL RULES:
- Landscape fills 50%+ of frame — epic, untamed, vast
- One strong directional light — hard shadows, deep blacks — NO flat light, NO grey sky, NO white blown-out sky
- RICH SATURATED COLORS — full tonal range, vivid, properly exposed
- Describe the building's exact shape, mass, and how it meets the terrain
- Real material textures: concrete grain, stone surface, weathered metal, aged timber
- One small imperfection: moss on concrete, water stain, one lit window
- 2-3 tiny human silhouettes to prove massive scale
- Wide establishing shot, 16-24mm

OUTPUT FORMAT (exactly):
NAME: [building name]
PROMPT: [200-250 word photorealistic image prompt ending with: "editorial architectural photograph, Hasselblad X2D, 24mm f/8, correct exposure, rich saturated colors, ultra-sharp focus, natural film grain, NOT a 3D render NOT AI art, NOT a painting, photorealistic 8K"]"""
                )
                text = response.text.strip()
                # NAME と PROMPT を分離
                name_match = re.search(r'NAME:\s*(.+)', text)
                prompt_match = re.search(r'PROMPT:\s*([\s\S]+)', text)
                name = name_match.group(1).strip() if name_match else f"Architecture {index+1}"
                prompt = prompt_match.group(1).strip() if prompt_match else text
                return name, prompt
            except Exception as e:
                print(f"[Gemini] {model} attempt {attempt+1} failed: {e}")
                time.sleep(5)
    return f"Architecture {index+1}", "Luxury architectural exterior, concrete and glass, natural landscape, photorealistic 8K"


def generate_image(prompt):
    """fal.ai FLUX.1-dev で画像生成"""
    import time
    clean = re.sub(r'--ar \S+', '', prompt).strip()
    headers = {
        "Authorization": f"Key {FAL_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "prompt": clean,
        "image_size": {"width": 832, "height": 1040},
        "num_inference_steps": 35,
        "guidance_scale": 7.5,
        "num_images": 1,
        "enable_safety_checker": False,
    }
    api_url = "https://fal.run/fal-ai/flux/dev"

    for attempt in range(3):
        try:
            print(f"[Image] attempt {attempt+1}")
            res = requests.post(api_url, headers=headers, json=payload, timeout=180)
            print(f"[Image] status={res.status_code}")
            if res.status_code == 200:
                data = res.json()
                img_url = data["images"][0]["url"]
                img_res = requests.get(img_url, timeout=60)
                base_dir = os.path.dirname(os.path.abspath(__file__))
                filename = f"{uuid.uuid4().hex}.jpg"
                path = os.path.join(base_dir, "static", "images", filename)
                with open(path, "wb") as f:
                    f.write(img_res.content)
                print(f"[Image OK] {filename}")
                return filename
            else:
                print(f"[Image] error: {res.text[:300]}")
                time.sleep(10)
        except Exception as e:
            print(f"[Image Error] {e}")
            time.sleep(10)
    raise RuntimeError(f"generate_image failed after 3 attempts")

def generate_caption(name, prompt):
    """英語キャプション生成"""
    import time
    for model in ["gemini-2.5-flash", "gemini-1.5-flash-latest"]:
        for attempt in range(2):
            try:
                response = client.models.generate_content(
                    model=model,
                    contents=f"""Write a short Instagram caption in English for this AI architecture image.
Concept: {name}
Visual: {prompt[:150]}

Rules:
- 2-3 sentences, cinematic and evocative
- Mention the dramatic relationship between the building and its natural setting
- NO hashtags in the body text
- Add 6 relevant hashtags on a new line at the end

Output only caption + hashtags."""
                )
                return response.text.strip()
            except Exception as e:
                print(f"[Caption] {model} attempt {attempt+1} failed: {e}")
                time.sleep(3)
    return f"Where architecture meets nature in perfect harmony.\n\n#aiarchitecture #architecture #luxurydesign #architecturephotography #design #interiordesign"

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
        "full building exterior, wide angle, golden hour, long shadows, sky ablaze orange and pink, same facade materials as original",
        "wide-angle exterior, f/8, golden hour, dramatic sky"
    ),
    (
        "Exterior — Snow & Glow",
        "same building exterior in heavy snowfall, thick snowflakes falling mid-air, snow blanketing every surface, warm amber interior glow visible through glass, deep navy blue sky — NO grey overcast clouds",
        "snowfall medium shot, warm vs cold contrast, Hasselblad X2D, 35mm"
    ),
    (
        "Night Exterior — Illuminated",
        "same building at night, warm amber light glows from every window, reflected in pool or wet stone, stars or moonlight above",
        "blue hour to night, long exposure feel, warm glow"
    ),
    (
        "Aerial Overview",
        "aerial drone, same building seen from above, surrounded by its natural landscape — coast, forest, desert, or mountain — shows scale",
        "bird's eye, 45-degree angle, landscape context"
    ),
    (
        "Interior — Grand Living Room",
        "vast triple-height grand living hall, 8-meter ceilings, 25-meter long room, entire wall of floor-to-ceiling glass opening to dramatic landscape, multiple Minotti sectional sofas in bouclé arranged in clusters, Patagonia quartzite floor, two mature indoor olive trees 4m tall in stone planters, custom bronze shelving spanning full wall, afternoon light casting long diagonal shadows across the enormous floor, abstract sculpture on stone plinth, 15 people could gather here with space to spare",
        "ultra-wide 14mm, afternoon light raking across enormous floor, private resort scale"
    ),
    (
        "Interior — Master Suite at Dawn",
        "enormous master suite, 6-meter ceilings, 15-meter wide room, full glass wall spanning the entire width with misty dawn landscape beyond, floating platform king bed centred in the vast space with Dedar linen and cashmere throw, warm aged walnut floor stretching 12 meters, mature 4m fiddle-leaf fig in corner, recessed warm lighting, silk curtains drifting, a daybed and seating area at the far end of the room, everything whispers extreme wealth and restraint",
        "wide 20mm, soft diffused dawn light, vast negative space, private resort scale"
    ),
    (
        "Interior — Chef's Kitchen & Dining",
        "vast open-plan kitchen and 20-seat dining hall, 7m ceilings, 20-meter long room, Poliform island in Calacatta marble large enough for 6 chefs, Gaggenau appliances concealed behind flush stone panels, cluster of Bocci pendants hanging 5m over the dining table, full glass wall spanning the entire length to terrace, two enormous bird-of-paradise plants in concrete planters flanking the table, warm oak and bronze, evening light, sense of a private Michelin-starred restaurant",
        "wide 20mm, warm layered lighting, massive indoor plants, restaurant-in-a-private-estate scale"
    ),
    (
        "Interior — Spa Bathroom",
        "monumental private spa, 7m ceiling, 18-meter long room, entire glass wall facing untouched nature, two freestanding Nero Marquina stone baths centred like sculptures 5 meters apart, marble walls floor to ceiling, private hammam for 8 people visible through glass partition, plunge pool inset in the floor, hanging eucalyptus bundles and 3m palm, morning mist visible outside, two beeswax candles half-burned on stone ledge, absolute silence and extreme luxury",
        "wide 18mm, soft spa light, misty nature beyond glass, grand hotel spa scale"
    ),
    (
        "Terrace & Pool — Dusk",
        "terrace with infinity pool, same architectural style, dusk sky gradient purple to orange, pool water perfectly still, outdoor loungers, potted agave plants, reflections",
        "low angle at pool level, dusk, reflection shot"
    ),
    (
        "Interior Detail — Light & Material",
        "architectural detail shot inside, same building materials — concrete, stone, wood, glass — dramatic shaft of natural light cutting across, a single sculptural plant or object",
        "close-up detail, 50mm or 35mm, chiaroscuro lighting"
    ),
]

def generate_expand_prompt(original_prompt, angle_name, angle_hint, camera_note):
    """アングルごとの詳細プロンプトを生成"""
    import time
    contents = f"""You are a world-class architectural photographer. Your images look like REAL photographs — never AI, never renders. Your signature: every shot shows the conversation between a building and its landscape.

Core concept — CONTRAST AND HARMONY:
- The building is precise, intentional, man-made. The landscape is wild, vast, indifferent. That tension is the shot.
- Yet they belong together — materials echo the ground, geometry mirrors the horizon, openings frame the exact right view.
- Neither dominates. They are equals.

Original building (keep SAME style, materials, exterior form):
\"\"\"{original_prompt[:350]}\"\"\"

Create a prompt for: "{angle_name}"
Scene direction: {angle_hint}
Camera note: {camera_note}

RULES:
- SAME building — same materials, same character, new angle only
- EXTERIOR: landscape fills 50%+ of frame, epic and untamed. ONLY clear sky / snow / golden sunset / forest rain — NO grey overcast ever
- INTERIORS: floor-to-ceiling glass frames the wild landscape outside — nature is always visible, always present. One strong oblique light shaft cuts across the room. Raw material textures: concrete grain, stone surface, aged wood.
- MASSIVE SCALE for 15 people — 7-8m ceilings, 20m+ rooms, multiple zones, gallery proportions
- Quality furniture at grand scale (Minotti, Poliform, Cassina), honed stone (travertine, Calacatta, Nero Marquina), mature indoor trees
- Lived-in imperfections: a half-burned candle, a crumpled linen throw, a book face-down — NOT sterile
- EXTERIOR colors: rich and saturated — deep blue sky, vivid warm light, no blown-out white sky, correct exposure
- INTERIOR colors: warm and rich — amber wood tones, warm stone, deep shadow — but never flat or washed out
- End: "editorial architectural photograph, Hasselblad X2D, 35mm f/5.6, correct exposure, rich saturated colors, ultra-sharp focus, natural film grain, NOT a 3D render NOT AI art, NOT a painting NOT an illustration, photorealistic 8K"

Output ONLY the prompt. 200-250 words. More detail = more realism."""
    for model in ["gemini-2.5-flash", "gemini-1.5-flash-latest"]:
        for attempt in range(2):
            try:
                response = client.models.generate_content(model=model, contents=contents)
                return response.text.strip()
            except Exception as e:
                print(f"[ExpandPrompt] {model} attempt {attempt+1} failed: {e}")
                time.sleep(5)
    return f"{angle_name} of luxury architectural building, photorealistic, 8K"

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
            else:
                print(f"[Expand {job_id}] {i+1}/{total} FAILED")
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
