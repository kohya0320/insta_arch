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
        "a single razor-thin horizontal slab cantilevered over a cliff edge, supported by one diagonal steel pillar",
        "a perfect black sphere half-buried in the earth, only the upper hemisphere visible",
        "a crescent-shaped curve that follows the contour of a hillside, one continuous flowing wall",
        "a ring — a circular building with a courtyard void at its centre open to the sky",
        "a bridge spanning two rock faces — the entire building IS the bridge, habitable interior within the span",
        "a series of stacked shifting discs that rotate slightly at each level like a twisted stack of coins",
        "a buried structure — only a cluster of triangular skylights protrude above ground level",
        "a mirrored box that reflects the landscape so perfectly the building almost disappears",
        "two massive parallel walls 40 meters apart, connected only by a glass ceiling — a canyon of architecture",
        "a helix — a continuous ramp spiralling upward around a central void open to the sky",
        "a single monolithic dark mass with deep carved voids — the negative space is the architecture",
        "a cluster of irregular towers of different heights connected by slender glass bridges at various levels",
        "folded planes like a crumpled sheet of metal, angular facets catching light differently on each face",
        "a long low horizontal bar elevated 8 meters above terrain on a forest of thin pillars",
        "terraced platforms cascading down a steep hillside like geological strata",
        "a transparent glass volume so pure and simple it seems to exist only as light and reflection"
    ]
    materials = [
        "entirely clad in weathered corten steel — deep rust orange-brown surface, oxidized texture",
        "entirely in raw board-formed concrete — every formwork plank line visible, grey and mineral",
        "entirely in black basalt stone — dark volcanic rock, matte and ancient",
        "entirely in white hand-packed rammed earth — layered horizontal strata, warm ivory",
        "entirely in dark oxidized zinc — matte charcoal grey, slightly iridescent in raking light",
        "entirely in warm golden travertine — book-matched stone slabs, fossil-rich surface",
        "entirely in weathered untreated cedar timber — silver-grey from exposure, grain hyper-visible",
        "entirely in polished black granite — deep reflective surface mirroring sky and landscape",
        "entirely in pale white limestone — rough-hewn blocks, carved texture, chalk-white",
        "glass and exposed black steel — structural grid fully visible, transparent volume",
        "entirely in hand-laid dark slate — horizontal layers of thin stone, slate-grey and charcoal",
        "entirely in rusted patinated copper — deep brown-green surface, verdigris patches"
    ]
    weathers = [
        "deep saturated cobalt blue sky, harsh direct sun, razor-sharp shadows, absolutely zero clouds",
        "heavy snowfall, thick snowflakes mid-air, deep saturated navy blue sky, dry snow on surfaces",
        "blazing golden sunset, sky deep saturated orange-magenta gradient, zero clouds, vivid warm light",
        "pre-dawn blue hour, deep saturated indigo sky, thin line of warm light on horizon, amber interior glow",
        "golden sunrise, deep saturated cerulean blue sky, long hard shadows, vivid warm light from one side",
        "midday sun, deep saturated blue sky, stark hard shadows, zero clouds, intense light",
    ]

    climate = random.choice(climates)
    form = random.choice(forms)
    material = random.choice(materials)
    weather = random.choice(weathers)

    for model in ["gemini-2.5-flash", "gemini-1.5-flash-latest"]:
        for attempt in range(3):
            try:
                response = client.models.generate_content(
                    model=model,
                    contents=f"""You are simultaneously a radical architect and a world-class architectural photographer. Your job: INVENT a completely original building and write a photorealistic image generation prompt for it.

INVENTION BRIEF — follow these seeds EXACTLY, do NOT substitute or default to grey concrete:
- Climate/Location: {climate}
- Architectural form: {form}
- Primary material: {material} — THIS IS MANDATORY. The building MUST be made of this material. Do NOT change it to concrete unless the material seed says concrete.
- Weather: {weather}

STEP 1 — Invent the building:
- Name it (3-5 words, evocative)
- Monumental cultural institution scale — museum, arts centre, research pavilion. NOT a house.
- The building CANNOT EXIST anywhere else on earth — terrain and architecture are inseparable.
- PHYSICS: every element visibly supported, cantilevers have structural logic, NO floating.
- Scale: sprawling, multiple wings, large enough for 15+ people.
- The material seed above IS the building's surface — describe it in detail.

STEP 2 — Write the photorealistic image prompt:
Core idea: CONTRAST AND HARMONY — precise man-made geometry against wild vast nature.

LANDSCAPE (@gorpcore.jpeg):
- Raw untouched wilderness, documentary feel, authentic textures
- Earthy muted-rich palette: weathered rock, moss, lichen, deep forest, raw soil
- Ancient, indifferent to the building — depth: foreground rocks/vegetation, building mid-ground, vast horizon

STRICT RULES:
- ABSOLUTELY NO clouds, NO overcast, NO grey sky, NO rain, NO wet surfaces — exact weather above only
- NO humans, NO people — zero human presence
- PHYSICS: building sits on, into, or emerges from the ground
- Landscape 50%+ of frame
- One strong directional light, hard shadows, deep blacks
- Describe the building material texture in extreme photographic detail
- One small imperfection on the facade: lichen, oxide streak, weathering mark

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
    return f"Architecture {index+1}", "Museum-like architecture, natural landscape, photorealistic 8K"


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
                    negative_prompt="clouds, overcast sky, grey sky, cloudy, storm clouds, rain, fog, mist, wet surfaces, puddles, people, humans, figures",
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
    """バズる英語キャプション生成"""
    import time
    for model in ["gemini-2.5-flash", "gemini-1.5-flash-latest"]:
        for attempt in range(2):
            try:
                response = client.models.generate_content(
                    model=model,
                    contents=f"""Write a viral Instagram caption in English for this architectural image. The account posts AI-generated brutalist/minimalist architecture in dramatic natural landscapes.

Concept: {name}
Visual: {prompt[:200]}

CAPTION RULES:
- Line 1: A single punchy hook — a question, a bold statement, or a poetic observation that stops the scroll. Max 10 words.
- Lines 2-3: 1-2 short evocative sentences. Cinematic. The tension between man-made precision and wild nature. No clichés.
- Optional line 4: A short question that invites comments (e.g. "Would you spend a week here?")
- NO hashtags in the body text
- Tone: aspirational, quiet confidence — not hype, not corporate

HASHTAGS (new line after caption):
Mix high-volume discovery tags with niche architecture tags. Use exactly these 15 tags:
#architecture #modernarchitecture #architecturephotography #brutalism #brutalistarchitecture #architecturelovers #minimal #minimalism #concretedesign #contemporaryarchitecture #archilovers #dezeen #architecturedaily #luxurydesign #aiarchitecture

Output only: caption text, one blank line, then the 15 hashtags on one line."""
                )
                return response.text.strip()
            except Exception as e:
                print(f"[Caption] {model} attempt {attempt+1} failed: {e}")
                time.sleep(3)
    return "Built where the world ends.\n\nRaw concrete against ancient stone. The silence here has weight.\n\nWould you stay?\n\n#architecture #modernarchitecture #architecturephotography #brutalism #brutalistarchitecture #architecturelovers #minimal #minimalism #concretedesign #contemporaryarchitecture #archilovers #dezeen #architecturedaily #luxurydesign #aiarchitecture"


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
        "monumental entrance hall, 9-meter raw concrete ceiling, 30-meter long axis, floor-to-ceiling glass wall at far end framing wild landscape, honed limestone floor with visible fossil grain, single oblique beam of sunlight slicing diagonally — warm amber tone against cool concrete, at the entry: a single curved hand-plastered wall in warm sand plaster, one oversized hand-thrown ceramic vessel on a low travertine plinth, dried botanicals, deep shadow in far corners, NO people NO humans",
        "ultra-wide 14mm, one oblique warm light shaft, museum entry scale"
    ),
    (
        "Main Living Hall",
        "vast triple-height living hall, 8-meter raw concrete ceiling, 25-meter long room, full glass wall facing dramatic landscape, floor of honed travertine with book-matched veining, a curved organic bouclé sectional as a warm island in the vast space, one sculptural travertine coffee table, a 4-meter mature olive tree in a raw concrete planter, afternoon raking light warm amber on the stone floor — the collision of brutal concrete and organic warmth is the subject",
        "ultra-wide 14mm, warm afternoon raking light, gallery scale"
    ),
    (
        "Library & Study",
        "double-height library, 6-meter raw concrete walls lined floor-to-ceiling with books, one full glass wall facing untamed landscape, a single 5-meter raw oak reading table — surface worn and warm, two sculptural aged brass pendants casting warm amber pools, late afternoon oblique sunlight raking across book spines — dust particles visible, a hand-thrown ceramic mug, a crumpled linen cloth, one open book, deep silence and warmth",
        "wide 20mm, warm amber oblique light, intimate within monumental scale"
    ),
    (
        "Master Bedroom",
        "enormous master suite, 6-meter raw concrete ceilings, full glass wall spanning entire width — the wilderness is the headboard, a low platform bed in aged walnut with organic curved headboard in hand-plastered sand plaster, Dedar linen in warm ivory crumpled naturally, a sheepskin draped over a low curved chair, two sculptural ceramic bedside vessels, a single shaft of pale dawn light raking across the linen, one mature olive tree 3m tall, deep silence",
        "wide 20mm, soft dawn raking light, warm organic against brutal concrete"
    ),
    (
        "Bathroom — Stone & Water",
        "monumental bathroom, 6-meter raw concrete ceiling, 14-meter long room, full glass wall facing wild landscape, single freestanding sculptural stone bath in warm travertine — curved organic form, book-matched travertine walls with visible warm veining, honed limestone floor, shallow water reflecting the ceiling, a low oak stool with a folded linen towel, two half-burned beeswax candles on a stone ledge, morning light soft and diffused, absolute stillness",
        "wide 20mm, soft diffused warm light, travertine and water reflection"
    ),
    (
        "Kitchen & Dining",
        "vast kitchen and dining hall, 7-meter raw concrete ceiling, 22-meter long space, a 6-meter island in warm Calacatta Viola marble with waterfall edge, 14-seat dining table in solid aged oak — surface marked and lived-in, cluster of hand-blown amber glass pendants casting warm light, full glass wall to landscape, evening light warm gold on stone and wood, an open cookbook, a ceramic bowl of fruit, shadow deep at the concrete ceiling",
        "wide 20mm, warm amber evening light, Michelin kitchen scale"
    ),
    (
        "Meditation & Spa",
        "monumental spa, 7-meter raw concrete ceiling, 20-meter room, full glass wall facing ancient wilderness, a single deep soaking tub carved from a single block of warm travertine, plunge pool inset flush with honed limestone floor, walls in hand-applied sand plaster — warm and textured, hanging dried eucalyptus and pampas grass bundles, two low ceramic oil burners with soft flame, morning light diffused and golden, absolute stillness, warm vs raw concrete collision",
        "wide 18mm, soft warm diffused light, organic warmth against raw concrete"
    ),
    (
        "Corridor & Circulation",
        "long circulation corridor, 5-meter raw concrete ceiling, 30-meter length, continuous slot skylight casting a single blade of warm amber light along the honed limestone floor, rough concrete walls both sides, at intervals: one curved hand-plastered alcove with a single ceramic sculpture, at the far end a full glass wall opening to wild landscape — warm light in a brutalist tunnel, the contrast is the subject",
        "35mm, blade of warm skylight, long perspective compression"
    ),
    (
        "Terrace — Interior Edge",
        "covered terrace at the threshold between inside and outside, 4-meter raw concrete soffit, floor in large-format honed travertine continuing seamlessly interior to exterior, two low organic curved loungers in weathered teak with warm linen cushions, a single sculptural side table in raw stone, deep saturated blue sky or golden sunset beyond — zero clouds, one ceramic glass of water on stone ledge, the building and wilderness meet here in warmth",
        "wide 20mm, interior-exterior threshold, warm materials against epic landscape"
    ),
    (
        "Material Detail — Light & Texture",
        "extreme macro close-up of an interior surface — book-matched travertine wall with visible fossil and vein, OR aged oak with every grain hyper-visible, OR hand-plastered sand wall with every trowel mark — a single dramatic shaft of warm amber natural light raking across the surface at a very low angle, deep crisp shadow edge, a small imperfection: a hairline crack, a mineral deposit, a knot in the wood — the material is the entire subject",
        "50mm macro, raking warm amber light, hyper-sharp material texture"
    ),
    (
        "Wide Exterior — Full Context",
        "ultra-wide establishing shot, full building visible in its landscape, @gorpcore.jpeg wilderness — ancient weathered terrain, earthy muted tones, foreground rock or vegetation in sharp focus, building in mid-ground, distant horizon stretching vast, deep saturated blue sky or golden sunset or snow — zero clouds, NO humans NO people, building obeys physics — sits on or into the terrain",
        "ultra-wide 14-16mm, full landscape context, @gorpcore.jpeg terrain"
    ),
    (
        "Aerial — Bird's Eye",
        "aerial drone shot from directly above at 45 degrees, same building seen from high altitude, surrounded by its epic landscape — coast, forest, desert, mountain — @gorpcore.jpeg wilderness scale, earthy terrain, deep saturated blue sky zero clouds, building's form and footprint fully revealed from above, NO humans NO people",
        "aerial 45-degree, bird's eye, landscape scale, deep blue sky"
    ),
]


def generate_expand_prompt(original_prompt, angle_name, angle_hint, camera_note, is_interior=True):
    """アングルごとの詳細プロンプトを生成"""
    import time

    if is_interior:
        style_rules = """INTERIOR AESTHETIC — fusion of @matitectura architecture + @design.only styling:
- ARCHITECTURE (@matitectura): same building shell — massive ceilings 7-8m, floor-to-ceiling glass walls, museum/gallery proportions
- INTERIOR STYLING (@design.only): warm organic materials layered against the raw architecture — book-matched travertine, warm aged oak, hand-plastered walls in sand/cream, honed limestone floors
- FURNITURE: sculptural curved organic forms — a curved bouclé sofa, organic travertine coffee table, low platform bed in aged walnut — NOT sterile box furniture
- LIGHTING: warm amber glow from low sculptural pendants PLUS one oblique shaft of natural daylight — two light sources, depth and warmth
- TEXTILES: linen throws slightly crumpled, a sheepskin over a chair arm, woven wool rug — tactile, lived-in
- OBJECTS: hand-thrown ceramic vessels, dried botanicals, an open art book — curated imperfection, NOT a showroom
- PALETTE: warm cream, raw sand, travertine ivory, aged oak honey, deep charcoal shadow
- The collision: brutal architecture shell vs warm organic interior — that tension is the subject
- Ultra-sharp: every grain in wood, every vein in stone, every thread in fabric
- RICH SATURATED COLORS — full tonal range, correct exposure, deep shadows, no blown-out whites
- End: "editorial interior photograph, Hasselblad X2D, {camera_note}, correct exposure, rich saturated colors, ultra-sharp focus, natural film grain, NOT a 3D render NOT AI art, NOT a painting, photorealistic 8K\""""
    else:
        style_rules = """EXTERIOR RULES:
- SAME building — same materials, same form, exterior view only
- LANDSCAPE (@gorpcore.jpeg): raw untouched wilderness, earthy muted-rich palette (weathered rock, moss, lichen, deep forest green, raw soil), ancient and documentary, NOT a postcard
- Foreground terrain detail, building mid-ground, vast horizon
- One strong directional light, hard shadows, deep blacks
- Describe exact building material texture in detail
- RICH but EARTHY COLORS — natural tones for landscape, saturated light for sky
- End: "editorial architectural photograph, Hasselblad X2D, {camera_note}, correct exposure, rich saturated colors, ultra-sharp focus, natural film grain, NOT a 3D render NOT AI art, NOT a painting, photorealistic 8K\""""

    contents = f"""You are a world-class architectural photographer. Your images look like REAL photographs — never AI, never renders.

ORIGINAL BUILDING — extract and strictly follow these details:
\"\"\"{original_prompt[:800]}\"\"\"

From the above, identify and carry over EXACTLY:
- The primary facade material and its texture (corten, basalt, concrete, timber, glass, etc.)
- The window/opening type and proportion (small slits, floor-to-ceiling glass, punched openings, no windows, etc.)
- The overall form and silhouette
- The scale (number of levels, footprint)
- Any unique structural elements (pilotis, cantilevers, arches, etc.)

Create a prompt for: "{angle_name}"
Scene direction: {angle_hint}
Camera note: {camera_note}

STRICT RULES (all shots):
- SAME building — the window sizes, opening proportions, material textures, and scale MUST match the original exactly
- If the original has small punched windows, interior views show small punched windows — NOT floor-to-ceiling glass
- If the original has floor-to-ceiling glass walls, interiors show full glass walls framing the landscape
- ABSOLUTELY NO clouds, NO overcast, NO grey sky, NO rain, NO wet surfaces, NO wet walls
- NO humans, NO people, NO figures anywhere — zero human presence
- PHYSICS: building must obey gravity — every element visibly supported, no floating

{style_rules}

Output ONLY the prompt. 200-250 words."""

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
            is_interior = i < (total - 2)  # 最後の2枚（Wide Exterior, Aerial）は外観
            prompt = generate_expand_prompt(original_prompt, angle_name, angle_hint, camera_note, is_interior)
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

def upload_to_catbox(image_path):
    """catbox.moe に匿名アップロードしてpublic URLを返す（登録不要）"""
    try:
        with open(image_path, 'rb') as f:
            r = requests.post(
                "https://catbox.moe/user/api.php",
                data={"reqtype": "fileupload"},
                files={"fileToUpload": f},
                timeout=30
            )
        url = r.text.strip()
        if url.startswith("https://"):
            return url
    except Exception as e:
        print(f"[catbox] upload failed: {e}")
    return None


def resolve_public_url(img_url):
    """Instagram用のpublic URLを取得（catbox.moe経由）"""
    filename = img_url.split('/static/images/')[-1]
    base_dir = os.path.dirname(os.path.abspath(__file__))
    local_path = os.path.join(base_dir, "static", "images", filename)
    cdn_url = upload_to_catbox(local_path)
    return cdn_url if cdn_url else img_url


@app.route("/api/post", methods=["POST"])
def post():
    import time
    data = request.json
    caption = data.get("caption", "")
    images = data.get("images", [])  # list of public URLs

    if not images:
        return jsonify({"error": "no images provided"}), 400
    if not IG_ACCESS_TOKEN or not IG_USER_ID:
        return jsonify({"error": "Instagram credentials not configured"}), 400

    base = f"https://graph.instagram.com/v21.0"
    token = IG_ACCESS_TOKEN
    uid = IG_USER_ID

    try:
        # Cloudinary経由でpublic URLに変換
        public_images = [resolve_public_url(u) for u in images]

        if len(public_images) == 1:
            # Single image post
            r = requests.post(f"{base}/{uid}/media",
                params={"image_url": public_images[0], "caption": caption, "access_token": token})
            cdata = r.json()
            if "id" not in cdata:
                return jsonify({"error": str(cdata)}), 500
            time.sleep(5)
            pub = requests.post(f"{base}/{uid}/media_publish",
                params={"creation_id": cdata["id"], "access_token": token})
            pdata = pub.json()
            if "id" not in pdata:
                return jsonify({"error": str(pdata)}), 500
            return jsonify({"success": True, "post_id": pdata["id"]})
        else:
            # Carousel post
            child_ids = []
            for img_url in public_images:
                r = requests.post(f"{base}/{uid}/media",
                    params={"image_url": img_url, "is_carousel_item": "true", "access_token": token})
                cdata = r.json()
                if "id" not in cdata:
                    return jsonify({"error": f"carousel item failed: {cdata}"}), 500
                child_ids.append(cdata["id"])
                time.sleep(2)

            # Create carousel container
            r = requests.post(f"{base}/{uid}/media",
                params={
                    "media_type": "CAROUSEL",
                    "children": ",".join(child_ids),
                    "caption": caption,
                    "access_token": token
                })
            carousel = r.json()
            if "id" not in carousel:
                return jsonify({"error": f"carousel container failed: {carousel}"}), 500

            time.sleep(5)
            pub = requests.post(f"{base}/{uid}/media_publish",
                params={"creation_id": carousel["id"], "access_token": token})
            pdata = pub.json()
            if "id" not in pdata:
                return jsonify({"error": str(pdata)}), 500
            return jsonify({"success": True, "post_id": pdata["id"]})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    base_dir = os.path.dirname(os.path.abspath(__file__))
    os.makedirs(os.path.join(base_dir, "static", "images"), exist_ok=True)
    app.run(debug=False, port=5002, threaded=True)
