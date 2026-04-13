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

# ━━━ 地形・自然に溶け込む超高級・大規模建築パターン ━━━
SCENARIOS = [
    {
        "name": "Amalfi Cliff Mega-Villa",
        "desc": "イタリア・アマルフィ海岸の断崖に水平に張り出した6層・全長120mのコンクリートとガラスの超大型ヴィラ複合体。各フロアがテラスとプールを持ち、崖の岩盤から直接生えた階段状のヴォリュームが海へ向かって降りていく。夕日に照らされた崖面とコバルトブルーの海が背景。Bjarke Ingels設計イメージ。"
    },
    {
        "name": "Norwegian Fjord Lodge Complex",
        "desc": "ノルウェーの峡湾沿いに100m以上にわたって横断する、黒いコルテン鋼と粗い花崗岩の大型リゾート複合施設。水面から直接立ち上がる岸壁に張り付き、キャンチレバーのウィングが水面上に突き出す。フィヨルドの深い緑の水面が正面に広がり、背後に雪を抱いた絶壁。Snøhetta設計イメージ。"
    },
    {
        "name": "Patagonia Mountain Resort",
        "desc": "パタゴニアのトレス・デル・パイネの麓、氷河湖を見下ろす丘陵に広がる石と黒鉄と大ガラスの大型山岳リゾート。複数の棟が岩盤の地形に沿って展開し、総延長200m。荒天の空と氷河湖のターコイズブルーが対比する。David Chipperfield設計イメージ。"
    },
    {
        "name": "Utah Canyon Estate",
        "desc": "アメリカ・ユタ州の赤砂岩渓谷を見渡す台地に建つ、砂岩と打ち放しコンクリートの大型邸宅群。メインハウスとゲストウィング・プールハウスが渓谷の縁に沿って配置され、全体が岩盤の色に溶け込む。夕日で全体が赤く燃え上がる。Rick Joy設計イメージ。"
    },
    {
        "name": "Maldives Over-Water Estate",
        "desc": "モルディブの環礁に建てられた、珊瑚礁の海上に桟橋で繋がれた大型水上ヴィラ群。白いコンクリートと熱帯木材の複数棟が透明度40mのインド洋の上に張り出し、無限大のラグーンと空が建物を包む。Jean Nouvel設計イメージ。"
    },
    {
        "name": "Japanese Volcanic Spa Resort",
        "desc": "日本・九州の火山地帯、硫黄噴気が立ち上る溶岩台地に建つ大型温泉リゾート。黒い玄武岩と薄い鉄板屋根の建物群が等高線に沿って段々に展開。温泉の湯気と霧が建物を包み、背後に活火山がそびえる。隈研吾設計イメージ。"
    },
    {
        "name": "Scottish Highlands Castle-Hotel",
        "desc": "スコットランドの荒野、ロッホ（湖）の畔に建つ現代的な大型城郭ホテル。地元産砂岩と鉄骨ガラスを組み合わせた100室規模の施設が、ヒースの荒野と灰色の空を背景に堂々とそびえる。長い石積みの壁が湖岸線に沿って続く。Zaha Hadid設計イメージ。"
    },
    {
        "name": "Santorini Caldera Mega-Villa",
        "desc": "サントリーニ島のカルデラ崖に掘り込まれた、白漆喰ではなく黒い火山岩と白大理石だけで構成された大型崖面ヴィラ複合体。崖の垂直面から水平ヴォリュームが何層にも張り出し、各層に無辺縁プールを持つ。エーゲ海のカルデラが眼下360度に広がる。"
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
                    contents=f"""You are a world-class architectural photographer. Your work appears on @amazing.architecture, @stylarc, @minimal_architectures, Dezeen, and Wallpaper*. You are known for capturing how extraordinary buildings emerge FROM their landscape — the terrain is always the co-star.

Create a photorealistic exterior image generation prompt for this building:
"{scenario['desc']}"

RULES — exterior landscape shot:
- EXTERIOR view showing full building or large portion in context with its dramatic natural landscape — no interior shots
- Building must feel LARGE and expensive — multi-wing compounds, resort scale, landmark architecture are welcome
- The terrain, geology, sky, water, or vegetation must be the emotional core — building grows FROM the land
- Architecture obeys gravity, physically possible, no floating
- EXACT camera specs: body, lens (wide 16-24mm preferred), aperture, time of day, natural light angle
- Specific geology and materials: exact rock type, concrete texture, wood species, patina, weathering
- Specific sky and atmosphere: cloud type, haze, humidity, wind effect on vegetation
- One human-scale detail to show scale (a parked car half-visible, a single lounger, a person silhouette)
- Color restrained and natural — no oversaturation, muted earthy palette
- NO adjectives like "stunning", "dramatic", "breathtaking" — describe what the camera SEES
- End with: "editorial architectural photograph, Iwan Baan style, photorealistic, natural film grain, 8K"

Output ONLY the prompt. ~120 words."""
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
        "num_inference_steps": 28,
        "guidance_scale": 3.5,
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
        "Exterior — Storm & Drama",
        "same building exterior in stormy or snowy weather, dark brooding sky, warm interior glow visible through glass, moody atmosphere",
        "dramatic weather, moody, medium shot"
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
        "vast double-height living room, 6-meter ceilings, entire wall of floor-to-ceiling glass opening to dramatic landscape, Minotti sectional sofa in bouclé, Patagonia quartzite floor, mature indoor olive tree 3m tall in stone planter, custom bronze shelving, afternoon light casting long shadows, abstract sculpture on stone plinth, extreme sense of space and silence",
        "ultra-wide 16mm, afternoon light raking across floor, billionaire residence"
    ),
    (
        "Interior — Master Suite at Dawn",
        "enormous master bedroom, 5-meter ceilings, full glass wall with misty dawn landscape beyond, floating platform king bed with Dedar linen and cashmere throw, warm aged walnut floor, mature 3m fiddle-leaf fig in corner, recessed warm lighting, silk curtains drifting, sheepskin bench, everything whispers extreme wealth and restraint",
        "wide 24mm, soft diffused dawn light, negative space, calm luxury"
    ),
    (
        "Interior — Chef's Kitchen & Dining",
        "vast open-plan kitchen and 12-seat dining, 5m ceilings, Poliform island in Calacatta marble, Gaggenau appliances concealed behind flush stone panels, Bocci chandelier hanging 4m, full glass wall to terrace, enormous bird-of-paradise in concrete planter, warm oak and bronze, evening light, sense of a private gallery",
        "wide 24mm, warm layered lighting, lush indoor plant, museum-like scale"
    ),
    (
        "Interior — Spa Bathroom",
        "enormous private spa bathroom, 5m ceiling, entire glass wall facing untouched nature, 2m freestanding stone bath centred like a sculpture, Nero Marquina marble walls, private hammam visible behind glass, hanging eucalyptus, single tall beeswax candle, morning mist outside, absolute silence and luxury",
        "wide 20mm, soft spa light, misty nature beyond glass, indoor botanicals"
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
    contents = f"""You are a professional architectural photographer shooting for @stylarc, @minimal_architectures, @matitectura. Your work looks like REAL photographs — not AI, not renders. Editors at Wallpaper* and Dezeen publish your shots.

Original building (keep SAME architectural style, materials, exterior form):
\"\"\"{original_prompt[:350]}\"\"\"

Create a prompt for: "{angle_name}"
Scene direction: {angle_hint}
Camera note: {camera_note}

RULES FOR PHOTOREALISM (critical):
- SAME building and materials — consistency across all views
- EXACT camera specs: body (Hasselblad X2D or Phase One XF), lens mm, aperture, time of day, natural light direction
- Specific imperfect real-world details: a water glass on a side table, a linen throw slightly crumpled, a candle half-burned, slight dust on a beam — makes it feel lived-in and real
- Interiors: VAST proportions (5–6m ceilings), named furniture (Minotti, Poliform, B&B Italia, Cassina), honed stone (travertine, Calacatta, Nero Marquina), mature indoor plants as sculpture, warm layered light
- Color: restrained, natural — warm beige, raw concrete grey, aged oak, muted stone — NO oversaturation
- NO words like "stunning", "dramatic", "breathtaking" — describe visually instead
- End with: "editorial architectural photograph, photorealistic, natural film grain, 8K"

Output ONLY the prompt, ~110 words."""
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
