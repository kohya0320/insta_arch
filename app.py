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

# ━━━ 20人規模・奇抜な形状・自然融合建築パターン ━━━
SCENARIOS = [
    {
        "name": "Cliff-Hanging Bridge Resort",
        "desc": "ノルウェーの峡湾を横断するように岩壁と岩壁の間に架けられた橋状の巨大リゾート建築。長さ150m・幅30mの橋型の建物が水面100m上に宙吊りになり、両端が崖に食い込む。ガラス床、吊り橋構造。WEATHER: heavy snowfall, snowflakes visible mid-air, pristine white snow on the bridge deck, deep blue fjord far below.",
        "weather": "heavy snowfall, thick snow on surfaces, snowflakes in the air, no clouds — deep saturated navy blue sky above the snow, properly exposed, no white blown-out sky"
    },
    {
        "name": "Volcanic Crater Retreat",
        "desc": "休火山のクレーター内壁に沿って螺旋状に配置されたリング型リゾート。らせん状に降りていく有機的な曲線形の建物群がクレーターの内側をぐるりと囲み、中央の火口湖を見下ろす。黒い溶岩石と錆鉄の外壁。各棟が弧を描くように連結。20棟。WEATHER: blazing clear blue sky, intense tropical sun, steam vents rising from the crater floor.",
        "weather": "deep saturated cobalt blue sky, harsh direct sun, razor-sharp shadows, zero clouds, rich vivid colors, properly exposed"
    },
    {
        "name": "Underwater-Cliff Glass Resort",
        "desc": "地中海の海岸断崖に半分埋め込まれ、半分が海面上に突き出た巨大なガラスと白コンクリートのリゾート。S字カーブを描く平面形状、各フロアが海に向かって前に張り出すカンチレバー構造。大型プール、20室規模。WEATHER: fiery sunset, sky burning orange and deep magenta, reflections on the calm sea.",
        "weather": "blazing golden sunset, sky deep saturated orange and magenta gradient, no clouds, vivid warm golden light saturating all surfaces, rich colors, properly exposed, no white blown-out sky"
    },
    {
        "name": "Forest Canopy Mega-Treehouse",
        "desc": "スウェーデンの針葉樹林、樹高25mの樹冠レベルに網目状の歩道橋で繋がれた20棟のキャビン群。各棟は樹木の幹に絡みつくような有機的な卵形・雫形のフォルムで、木の皮のような外壁。WEATHER: steady forest rain, rain visible as diagonal streaks, wet glistening bark, mist rising between trees.",
        "weather": "steady forest rain, diagonal rain streaks visible in air, every surface wet and glistening, rich deep greens of wet foliage, low mist between the trees, no open sky — only dense saturated green forest canopy, vivid colors"
    },
    {
        "name": "Desert Rock-Carved Complex",
        "desc": "ヨルダン・ペトラの砂岩渓谷に、岩盤を直接彫り込んで作られた現代的な大型リゾート。建物の半分が地下の洞窟、半分が砂岩の崖から突き出た大胆なコンクリートとガラスのヴォリューム。20室以上。WEATHER: golden hour morning sun, sandstone glowing deep amber and crimson, sharp shadows.",
        "weather": "golden hour sunrise, sandstone glowing deep saturated amber-red, razor-sharp shadows, deep saturated cerulean blue sky, vivid rich colors, properly exposed"
    },
    {
        "name": "Arctic Ice-Edge Lodge",
        "desc": "グリーンランドの氷河末端、氷と海の境界線上に建てられた黒い鉄とガラスの大型ロッジ。菱形・多角形を組み合わせた結晶のような幾何学フォルム、一切の直角なし。氷河の青白い壁面が建物の背後に迫り、前面は北極海。20人収容。WEATHER: blizzard with heavy snow, snowflakes thick in the air, warm amber glow from every window.",
        "weather": "blizzard, thick snowfall driven sideways, warm amber light glowing from windows, dramatic contrast of cold blue-white snow and warm amber interior glow, deep saturated navy sky above the storm, properly exposed, vivid color contrast"
    },
    {
        "name": "Cascading Waterfall Villa",
        "desc": "アイスランドの滝の横、玄武岩の柱状節理の崖面に段々に張り付いた白いコンクリートの大型別荘群。各フロアが滝と平行に斜めに傾いたカンチレバーで張り出し、水平ではなく傾斜した屋根面が重なる。Frank Lloyd Wrightのカウフマン邸を10倍スケールに。WEATHER: crisp clear sunny day, bright blue sky, waterfall mist catching sunlight as rainbows.",
        "weather": "brilliant clear sunny sky, deep saturated azure blue, waterfall mist catching sunlight as vivid rainbows, bright midday light, rich saturated greens and blues, properly exposed"
    },
    {
        "name": "Floating Lagoon Resort",
        "desc": "タヒチのターコイズブルーのラグーンに、水上に浮かぶ花びら形の大型リゾート島。花弁状に広がる5つのウィングが放射状に伸び、各ウィングが曲線を描きながら水面上に張り出す。20棟以上の水上ヴィラ。WEATHER: golden sunset, sky blazing orange fading to deep violet, perfect mirror reflection in the lagoon.",
        "weather": "burning sunset, sky deep saturated orange fading to vivid violet, perfect glassy reflection in the rich turquoise lagoon, zero clouds, maximum color saturation, properly exposed, no blown-out whites"
    },
]

def generate_prompt_with_gemini(scenario):
    """Geminiで超詳細なプロンプトを生成"""
    import time
    for model in ["gemini-2.5-flash", "gemini-1.5-flash-latest"]:
        for attempt in range(3):
            try:
                response = client.models.generate_content(
                    model=model,
                    contents=f"""You are a world-class architectural photographer known for one thing: capturing the conversation between a building and its landscape — not copying either, but finding the tension and harmony between them.

The core visual idea: CONTRAST AND HARMONY
- CONTRAST: the building is man-made, precise, intentional — the landscape is wild, vast, indifferent. This opposition creates visual electricity.
- HARMONY: yet the building belongs there. It shares materials with the ground beneath it, its geometry echoes the horizon line, its openings frame exactly the right view. It could not exist anywhere else.
- Never let one dominate — nature and architecture are equals in the frame.

Create a photorealistic exterior prompt for this building:
"{scenario['desc']}"

WEATHER (do not change): {scenario.get('weather', 'clear blue sky, golden light')}

VISUAL RULES:
- Landscape fills at least 50% of the frame — sky, terrain, water, forest — epic and untamed (@peaktylerr scale)
- One strong directional light source — hard shadows, deep blacks — NO flat overcast, NO grey sky, NO white blown-out sky ever
- RICH SATURATED COLORS: deep blue sky, vivid warm sunlight, saturated greens — full tonal range, no washed-out or faded look
- Describe the building's SHAPE and MASS precisely: how it sits on, into, or above the terrain
- Raw real materials visible: concrete texture, stone grain, weathered metal, aged timber
- Small imperfection makes it real: a moss patch, a water stain on the facade, one window with warm light on inside
- 2-3 tiny human silhouettes at the entrance — prove the enormous scale
- MASSIVE resort scale — 15 people, multiple wings visible, wide establishing shot 16-24mm
- End: "editorial architectural photograph, Hasselblad X2D, 24mm f/8, correct exposure, rich saturated colors, ultra-sharp focus, natural film grain, NOT a 3D render NOT AI art, NOT a painting NOT an illustration, photorealistic 8K"

Output ONLY the prompt. 200-250 words. More detail = more realism."""
                )
                return response.text.strip()
            except Exception as e:
                print(f"[Gemini] {model} attempt {attempt+1} failed: {e}")
                time.sleep(5)
    return f"Luxury architectural exterior, concrete and glass, natural landscape, professional photography, 8K photorealistic"


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

def process_one(job_id, i, scenario):
    """1枚を処理してjobsに追加"""
    try:
        prompt = generate_prompt_with_gemini(scenario)
        print(f"[Job {job_id}] {i+1}/5 prompt ready")
        filename = generate_image(prompt)
        caption = generate_caption(scenario["name"], prompt)
        if filename:
            jobs[job_id]["results"].append({
                "style": scenario["name"],
                "prompt": prompt,
                "image": filename,
                "caption": caption,
            })
            print(f"[Job {job_id}] {i+1}/5 DONE")
        else:
            print(f"[Job {job_id}] {i+1}/5 FAILED")
    except Exception as e:
        print(f"[Job {job_id}] {i+1} error: {e}")
        jobs[job_id].setdefault("errors", []).append(str(e))

def run_job(job_id, scenarios):
    """5枚を順番に生成"""
    import time
    jobs[job_id]["status"] = "running"
    jobs[job_id]["started_at"] = time.time()
    jobs[job_id]["current"] = 0
    durations = []
    for i, scenario in enumerate(scenarios):
        jobs[job_id]["current"] = i + 1
        t0 = time.time()
        process_one(job_id, i, scenario)
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
    scenarios = random.sample(SCENARIOS, 5)
    jobs[job_id] = {"status": "running", "results": [], "current": 0, "started_at": 0, "avg_duration": 0}
    t = threading.Thread(target=run_job, args=(job_id, scenarios), daemon=True)
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
