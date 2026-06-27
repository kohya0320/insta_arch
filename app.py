from flask import Flask, render_template, jsonify, request
from google import genai
from google.genai import types as genai_types
from PIL import Image, ImageFilter
import io, os, uuid, requests, random, re, json, threading

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

# ━━━ スタイルコンボ ━━━
# 「建築家×写真家」のDNAをハイブリッドさせる方式。
# パラメータを細かく指定するのをやめ、AIが自律的に解釈できる「巨匠たちのスタイル」を渡す。
STYLE_COMBOS = [
    {
        "name_hint": "Ando × Barragán",
        "architects": "Tadao Ando",
        "photographer": "Luis Barragán",
        "architect_style": "brutalist board-formed concrete masses, raw grey surface, deep shadow recesses, monastic silence, precision geometric cuts, reflective water features",
        "photo_style": "vivid saturated color plane walls — hot pink, sulphur yellow, or magenta — blazing Mexican sun, emotional chromatic contrast between concrete and color",
        "mood": "silence meets color explosion — the most austere concrete architecture colliding with the most emotionally charged color",
    },
    {
        "name_hint": "Bofill × Shulman",
        "architects": "Ricardo Bofill",
        "photographer": "Julius Shulman",
        "architect_style": "postmodern monumental neoclassical — grand arched colonnades, symmetrical layered facades, theatrical public scale, La Muralla Roja grandeur",
        "photo_style": "golden-age architectural photography — crisp modernism, strong diagonal compositions, dramatic mid-century California light, deep shadows under a cobalt sky",
        "mood": "theatrical architectural grandeur captured with documentary precision — monumental form under cinematic light",
    },
    {
        "name_hint": "Calatrava × matitectura",
        "architects": "Santiago Calatrava",
        "photographer": "@matitectura Instagram aesthetic",
        "architect_style": "skeletal organic structural beauty — white bone-like ribbed forms, sweeping arches, engineering as sculpture, overwhelming structural expressionism",
        "photo_style": "epic contrast between architecture and raw nature, ultra-wide dramatic compositions, maximum tonal range, building erupting from or dissolving into wilderness",
        "mood": "structural sculpture emerging from a primordial landscape — man-made precision vs geological violence",
    },
    {
        "name_hint": "Herzog & de Meuron × Iwan Baan",
        "architects": "Herzog & de Meuron",
        "photographer": "Iwan Baan",
        "architect_style": "material alchemy — corten steel, oxidized copper, pixelated ceramic, raw industrial honesty, reductive severe beauty, facades that are entirely about surface and texture",
        "photo_style": "documentary architectural photography — wide establishing shots, natural available light, buildings in their true landscape context, no glamour",
        "mood": "material poetry documented with honest light — all substance, no spectacle",
    },
    {
        "name_hint": "Zumthor × Hélène Binet",
        "architects": "Peter Zumthor",
        "photographer": "Hélène Binet",
        "architect_style": "phenomenological minimalism — dark slate, poured concrete, thermal baths, absolute material honesty, buildings that exist purely to be experienced",
        "photo_style": "extreme shadow contrast, light as architectural material, atmospheric chiaroscuro — sensory and existential over informational",
        "mood": "the architecture of silence — darkness, weight, and the presence of materials under sacred directional light",
    },
    {
        "name_hint": "Siza × Guerra",
        "architects": "Álvaro Siza",
        "photographer": "Fernando Guerra",
        "architect_style": "white sculptural modernism — pure whitewashed stucco, flowing curved walls, deep incised openings, form shaped by Atlantic Portuguese light",
        "photo_style": "sharp Mediterranean light — deep saturated blue sky, harsh hard shadows on white surfaces, documentary realism, crisp geometry",
        "mood": "white architecture carved by southern European light — pure geometry defined by sun and shadow",
    },
    {
        "name_hint": "Kengo Kuma × Daici Ano",
        "architects": "Kengo Kuma",
        "photographer": "Daici Ano",
        "architect_style": "material dissolution — stone, timber, bamboo, and glass layered so the building de-materializes into its landscape, Japanese craft precision, extreme textural detail",
        "photo_style": "quiet precision photography — soft diffused light, materials photographed at their most revealing, Japanese restraint and stillness",
        "mood": "the building disappears into its landscape — architecture as a frame for nature, not its rival",
    },
    {
        "name_hint": "SANAA × Delfino Legnani",
        "architects": "SANAA (Sejima + Nishizawa)",
        "photographer": "Delfino Sisto Legnani",
        "architect_style": "ephemeral lightness — ultra-thin steel columns, translucent glass volumes, floating roofs, buildings with no apparent weight or thickness, pure geometric restraint",
        "photo_style": "ultra-clean minimal photography — flat even light, pure geometry, the architecture IS the subject, every line matters",
        "mood": "maximum lightness against maximum heaviness of landscape — gravity-defying precision on geological terrain",
    },
    {
        "name_hint": "Scarpa × Ghirri",
        "architects": "Carlo Scarpa",
        "photographer": "Luigi Ghirri",
        "architect_style": "craft-obsessed Italian modernism — exposed concrete inlaid with marble fragments, oxidized bronze, water channels, mosaic details, every joint a design decision",
        "photo_style": "melancholic poetic photography — soft hazy Mediterranean light, pastel tones, quiet compositions, the beauty of impermanence and decay",
        "mood": "architecture as accumulated craftsmanship, bathed in a light that makes everything look ancient and precious",
    },
    {
        "name_hint": "Legorreta × Villaverde",
        "architects": "Ricardo Legorreta",
        "photographer": "Ramón Ramírez Villaverde",
        "architect_style": "Mexican bold color modernism — massive deep-purple or cobalt-blue stucco walls, massive scale, jacaranda-yellow accents, deep shadow loggias, Luis Barragán legacy",
        "photo_style": "saturated high-contrast Latin American light — deep sky, vivid shadow, the building reads as pure chromatic impact",
        "mood": "pure color as architecture — the building IS a palette of emotional chromatic mass under an unforgiving sun",
    },
]

# 参照画像ベース生成で使う光条件
WEATHERS = [
    "deep saturated cobalt blue sky, harsh direct sun, razor-sharp shadows, absolutely zero clouds",
    "heavy snowfall, thick snowflakes mid-air, deep saturated navy blue sky, dry snow on surfaces",
    "blazing golden sunset, sky deep saturated orange-magenta gradient, zero clouds, vivid warm light",
    "pre-dawn blue hour, deep saturated indigo sky, thin line of warm light on horizon, amber interior glow",
    "golden sunrise, deep saturated cerulean blue sky, long hard shadows, vivid warm light from one side",
    "midday sun, deep saturated blue sky, stark hard shadows, zero clouds, intense light",
    "misty dusk, low mist pooling in valleys, silhouetted building forms against deep amber-violet sky, no direct rain, dry mist only",
]


def generate_concept_and_prompt(index, custom_hint=""):
    """建築家×写真家のスタイルコンボからダイレクトにプロンプトを生成"""
    import time

    combo = random.choice(STYLE_COMBOS)
    extra = f"\n- ADDITIONAL VISUAL REQUIREMENT (mandatory): {custom_hint}" if custom_hint else ""
    base = "A grand monumental residential museum architecture, integrated into an epic raw nature, captured with high-contrast architectural photography. Wide shot, 16-24mm lens."

    for model in ["gemini-2.5-flash", "gemini-1.5-flash-latest"]:
        for attempt in range(3):
            try:
                response = client.models.generate_content(
                    model=model,
                    contents=f"""You are a world-class architectural image director. Your task: write a photorealistic image generation prompt that fuses two master styles into one striking image.

BASE CONCEPT: {base}

STYLE FUSION — execute both DNAs simultaneously:
- Architect DNA: {combo['architects']} — {combo['architect_style']}
- Photography DNA: {combo['photographer']} — {combo['photo_style']}
- Core mood: {combo['mood']}{extra}

STEP 1 — Name the building (3-5 evocative words that capture the style fusion).

STEP 2 — Write the image prompt (200-250 words):

ARCHITECTURE:
- Embody the architect's signature vocabulary: their specific forms, materials, proportions, and structural logic
- Monumental scale: museum, cultural institution, or arts pavilion — never a simple house
- The building has ALWAYS existed here — born from this specific landscape
- Large openings or glass walls — not a windowless bunker
- One small imperfection: lichen patch, oxide streak, weathering stain, or hairline crack

PHOTOGRAPHY:
- Apply the photographer's exact visual style: their specific lighting quality, composition logic, and tonal treatment
- Wide establishing shot, 16-24mm lens
- Strong directional light creating hard shadows and deep blacks
- NO clouds, NO overcast, NO rain — clear dramatic sky only
- NO humans, NO people, NO figures — zero human presence

LANDSCAPE:
- Choose a raw untouched wilderness that amplifies the architectural contrast — earthy, ancient, documentary
- Strong tonal or color contrast between building and landscape
- Landscape fills 60%+ of frame — foreground detail → building mid-ground → vast horizon

End the prompt with: "editorial architectural photograph, Hasselblad X2D, 24mm f/8, correct exposure, rich saturated colors, ultra-sharp focus, natural film grain, NOT a 3D render NOT AI art, NOT a painting, photorealistic 8K"

OUTPUT FORMAT (exactly):
NAME: [building name]
PROMPT: [200-250 word photorealistic image prompt]"""
                )
                text = response.text.strip()
                name_match = re.search(r'NAME:\s*(.+)', text)
                prompt_match = re.search(r'PROMPT:\s*([\s\S]+)', text)
                name = name_match.group(1).strip() if name_match else combo["name_hint"]
                prompt = prompt_match.group(1).strip() if prompt_match else text
                return name, prompt
            except Exception as e:
                print(f"[Gemini] {model} attempt {attempt+1} failed: {e}")
                time.sleep(5)
    return combo["name_hint"], base + f" in the style of {combo['architects']} and {combo['photographer']}, photorealistic 8K"


def generate_concept_from_ref(analysis, index):
    """参照画像の分析結果から新しい建物コンセプトを生成"""
    import time
    weather = random.choice(WEATHERS)
    for model in ["gemini-2.5-flash", "gemini-1.5-flash-latest"]:
        for attempt in range(3):
            try:
                response = client.models.generate_content(
                    model=model,
                    contents=f"""You are a radical architect and world-class architectural photographer.

A reference image has been analyzed. Here is its analysis:
{analysis}

Your job: INVENT a completely NEW building INSPIRED by the reference — not a copy. Keep the same spirit, atmosphere, material palette, and landscape feeling, but design something original.

Weather for this image: {weather}

STEP 1 — Invent the building:
- Name it (3-5 words, evocative)
- Channel the same material honesty, relationship to landscape, and monumental scale as the reference
- Monumental cultural institution — museum, arts pavilion, research centre. NOT a house, NOT a hotel.
- The building CANNOT EXIST anywhere else on earth — form born from terrain.
- PHYSICS: every element visibly supported, no floating.
- Scale: sprawling, multiple wings, massive presence.

STEP 2 — Write the photorealistic image prompt:
- Same material palette and texture spirit as the reference
- Same landscape type and atmosphere as the reference
- Weather: {weather}
- BUILDING: bold uncompromising geometry, raw material honesty, severe beauty
- LANDSCAPE: raw untouched wilderness, earthy muted-rich palette, ancient and documentary
- STRICT RULES: NO clouds (unless weather specifies snow/mist), NO humans, building sits on or into terrain, landscape 50%+ of frame
- End with: "editorial architectural photograph, Hasselblad X2D, 24mm f/8, correct exposure, rich saturated colors, ultra-sharp focus, natural film grain, NOT a 3D render NOT AI art, NOT a painting, photorealistic 8K"

OUTPUT FORMAT (exactly):
NAME: [building name]
PROMPT: [200-250 word photorealistic image prompt]"""
                )
                text = response.text.strip()
                name_match = re.search(r'NAME:\s*(.+)', text)
                prompt_match = re.search(r'PROMPT:\s*([\s\S]+)', text)
                name = name_match.group(1).strip() if name_match else f"Architecture {index+1}"
                prompt = prompt_match.group(1).strip() if prompt_match else text
                return name, prompt
            except Exception as e:
                print(f"[RefGen] {model} attempt {attempt+1} failed: {e}")
                time.sleep(5)
    return f"Architecture {index+1}", "Museum-like architecture, natural landscape, photorealistic 8K"


def run_ref_job(job_id, analysis):
    """参照画像ベースで5枚を生成"""
    import time
    jobs[job_id]["status"] = "running"
    jobs[job_id]["started_at"] = time.time()
    durations = []
    for i in range(5):
        jobs[job_id]["current"] = i + 1
        t0 = time.time()
        try:
            name, prompt = generate_concept_from_ref(analysis, i)
            print(f"[RefJob {job_id}] {i+1}/5 concept: {name}")
            filename = generate_image(prompt)
            caption = generate_caption(name, prompt)
            if filename:
                jobs[job_id]["results"].append({
                    "style": name, "prompt": prompt,
                    "image": filename, "caption": caption,
                })
                print(f"[RefJob {job_id}] {i+1}/5 DONE: {name}")
        except Exception as e:
            print(f"[RefJob {job_id}] {i+1} error: {e}")
            jobs[job_id].setdefault("errors", []).append(str(e))
        durations.append(time.time() - t0)
        jobs[job_id]["avg_duration"] = sum(durations) / len(durations)
    jobs[job_id]["status"] = "done"
    print(f"[RefJob {job_id}] All done: {len(jobs[job_id]['results'])}/5")


def generate_image(prompt):
    """Imagen 4 で画像生成"""
    import time
    clean = re.sub(r'--ar \S+', '', prompt).strip()
    # 曇り・雨・人物を強制除外（negative_promptが使えないためプロンプトに明示）
    clean = "ZERO clouds, clear sky only, NO overcast, NO rain, NO fog, NO wet surfaces, NO people, NO humans. " + clean

    # Imagen 4 Ultra → 通常モデルの順で試す
    IMAGE_MODELS = ["imagen-4.0-ultra-001", "imagen-4.0-generate-001"]

    for attempt in range(3):
        model_idx = min(attempt, len(IMAGE_MODELS) - 1)
        imagen_model = IMAGE_MODELS[model_idx]
        try:
            print(f"[Image] {imagen_model} attempt {attempt+1}")
            response = client.models.generate_images(
                model=imagen_model,
                prompt=clean,
                config=genai_types.GenerateImagesConfig(
                    number_of_images=1,
                    aspect_ratio="3:4",
                    output_mime_type="image/png",
                )
            )
            img_bytes = response.generated_images[0].image.image_bytes
            base_dir = os.path.dirname(os.path.abspath(__file__))
            filename = f"{uuid.uuid4().hex}.png"
            path = os.path.join(base_dir, "static", "images", filename)
            img = Image.open(io.BytesIO(img_bytes))
            native_w, native_h = img.size
            print(f"[Image native] {native_w}x{native_h} from {imagen_model}")

            # Instagram最大サイズ 1440×1800 (4:5) を目標に
            TARGET_W, TARGET_H = 1440, 1800
            scale = max(TARGET_W / native_w, TARGET_H / native_h)
            if scale > 1.0:
                # アップスケールが必要: オーバーサンプリングしてから縮小
                up_w = max(int(native_w * scale * 1.5), TARGET_W)
                up_h = max(int(native_h * scale * 1.5), TARGET_H)
                img = img.resize((up_w, up_h), Image.LANCZOS)
                scale2 = max(TARGET_W / up_w, TARGET_H / up_h)
                img = img.resize((int(up_w * scale2), int(up_h * scale2)), Image.LANCZOS)
            else:
                img = img.resize((int(native_w * scale), int(native_h * scale)), Image.LANCZOS)

            # センタークロップ
            left = (img.width - TARGET_W) // 2
            top = (img.height - TARGET_H) // 2
            img = img.crop((left, top, left + TARGET_W, top + TARGET_H))

            # アンシャープマスクで精細感を強化
            img = img.filter(ImageFilter.UnsharpMask(radius=0.8, percent=120, threshold=2))

            img.save(path, "PNG", optimize=False, compress_level=0)
            print(f"[Image OK] {filename} → {TARGET_W}x{TARGET_H} (native: {native_w}x{native_h}, scale: {scale:.3f})")
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


def process_one(job_id, i, custom_hint=""):
    """1枚を処理してjobsに追加"""
    try:
        name, prompt = generate_concept_and_prompt(i, custom_hint)
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


def run_job(job_id, custom_hint=""):
    """5枚を順番に生成"""
    import time
    jobs[job_id]["status"] = "running"
    jobs[job_id]["started_at"] = time.time()
    jobs[job_id]["current"] = 0
    durations = []
    for i in range(5):
        jobs[job_id]["current"] = i + 1
        t0 = time.time()
        process_one(job_id, i, custom_hint)
        durations.append(time.time() - t0)
        jobs[job_id]["avg_duration"] = sum(durations) / len(durations)
    jobs[job_id]["status"] = "done"
    print(f"[Job {job_id}] All done: {len(jobs[job_id]['results'])}/5")


# ━━━ インテリアプール（毎回10室をランダム選択）━━━
INTERIOR_ANGLES_POOL = [
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
        "Private Screening Room",
        "intimate screening room, 4-meter raw concrete ceiling, 18-meter long room, entire far wall is a seamless 8-meter projection screen glowing soft white, floor-to-ceiling acoustic panels in hand-woven dark linen, three rows of wide curved lounge chairs in warm cognac leather — deep and reclined, a single low travertine shelf running the side wall with two ceramic vessels, warm amber floor-wash lighting at the base of walls, absolute darkness above, cinematic silence",
        "wide 24mm, dramatic low ambient light, cinema scale"
    ),
    (
        "Indoor Lap Pool",
        "monumental indoor pool hall, 7-meter raw concrete ceiling, 25-meter lap pool inset flush with honed black granite floor, still water surface reflecting the concrete ceiling perfectly — the reflection doubles the space, one full glass wall at the far end framing wild landscape, natural light entering from a continuous slot skylight raking across the water surface, two raw oak benches with folded linen towels, absolute silence and stillness, NO people",
        "ultra-wide 14mm, water reflection doubling the space, slot skylight"
    ),
    (
        "Wine Cellar & Vault",
        "underground wine vault, 4-meter raw concrete barrel-vaulted ceiling, 20-meter long tunnel, floor-to-ceiling wine storage in aged oak and raw steel racks — thousands of bottles, a single long rough-hewn oak table at centre with two ceramic wine glasses, pendant lighting — single warm amber bulb on a long cord casting a dramatic pool of light, deep shadow in the arched ceiling, aged stone floor, the silence and gravity of an ancient cellar",
        "35mm, single pendant warm light, barrel vault compression"
    ),
    (
        "Atrium & Indoor Garden",
        "soaring central atrium, 12-meter raw concrete walls rising to a full glass roof — sky and clouds above, interior garden below: ancient olive trees 6 meters tall in raw concrete planters, jasmine climbing a concrete wall, a shallow water channel cutting through honed limestone floor, warm golden sunlight falling vertically through the glass roof creating pools of light and shadow, a single curved bench in aged oak, the smell of earth and light implied in every detail",
        "ultra-wide 14mm, vertical light from glass roof, atrium scale"
    ),
    (
        "Artist Studio & Workshop",
        "vast studio, 6-meter raw concrete ceiling, north-facing full glass wall — flat diffused daylight, no shadows, floor in raw grey epoxy — marked with years of creative work, a massive 4-meter oak work table with scattered architectural drawings, clay maquettes, open reference books, two industrial task lights on articulated arms, a wall of raw steel shelving with art books and ceramic vessels, controlled daylight and creative chaos",
        "wide 20mm, flat north light, creative workspace scale"
    ),
    (
        "Fireplace Lounge",
        "intimate lounge, 5-meter raw concrete ceiling, one full glass wall to dark landscape at night, centrepiece: a monumental fireplace carved from a single block of warm travertine — 2 meters wide, fire burning low and warm, two deep curved bouclé armchairs pulled close, a sheepskin on the floor, a low travertine side table with a ceramic whisky glass, warm amber firelight against cool concrete walls, deep shadows beyond, absolute intimacy within monumental space",
        "35mm, warm firelight as primary source, intimate within brutal shell"
    ),
    (
        "Rooftop Sky Terrace",
        "rooftop terrace at altitude, raw concrete parapet walls, large-format travertine floor continuing from interior, two low organic teak daybeds with warm linen, a single raw stone fire pit, vast 360-degree landscape panorama — mountain range or coastline stretching to horizon, deep saturated blue sky zero clouds or blazing sunset, the building's roof as a room open to the sky, one ceramic vessel on the parapet edge, NO humans",
        "wide 18mm, sky as ceiling, panoramic landscape edge"
    ),
    (
        "Monumental Staircase",
        "a single monumental staircase as architectural sculpture, raw concrete treads cantilevered from a concrete wall — no visible support, 6-meter void rising through 3 floors, a slot skylight at the top casting a blade of warm amber light down the full height of the void, honed limestone landing at base, the staircase is the entire subject — pure geometry, light, and shadow, deep shadow in recesses, NO people",
        "24mm, vertical void, cantilevered concrete geometry"
    ),
    (
        "Guest Suite",
        "serene guest suite, 5-meter raw concrete ceiling, full glass wall framing a private landscape view, a low platform bed in aged walnut with organic linen in warm ivory, a single curved reading chair in weathered linen, one floor-to-ceiling bookshelf in raw oak against a concrete wall, morning light soft and directional through the glass, a single hand-thrown ceramic vase on a low stone shelf, quiet and complete, deep restful shadow",
        "wide 20mm, soft morning light, quiet intimate scale"
    ),
    (
        "Home Office — Command Room",
        "dramatic home office, 5-meter raw concrete ceiling, full glass wall as the desk backdrop — wild landscape beyond, a single 4-meter floating desk in polished black granite cantilevered from the concrete wall, one precise task light in aged brass casting warm amber, floor in honed dark slate, walls raw concrete — no decoration, no distraction, one architectural model on the desk, a stack of drawings, total focus and severity",
        "wide 20mm, single task light warmth against concrete severity"
    ),
]

# 外観は常に固定（最後の2枚）
EXTERIOR_ANGLES = [
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


def generate_building_spec(original_prompt, image_path=None):
    """選択した建物の仕様書を1回だけ生成 — 12枚全部で共有する
    image_pathがあればGemini Visionで実際の画像を直接分析（テキスト分析より高精度）"""
    import time

    vision_instruction = """You are analyzing an architectural photograph to extract an ultra-precise building specification.
This spec will be used to generate 12 different interior and exterior views of THIS EXACT SAME BUILDING — so every detail must be captured with ruthless precision.

Extract and list EVERY visual detail:
- FACADE MATERIAL: exact material, precise color (e.g. "deep rust orange corten steel, heavily oxidized, coarse texture"), surface finish, aging/weathering patterns
- WINDOW TYPE: exact proportions (narrow horizontal slits / tall vertical slots / large punched squares / floor-to-ceiling glass walls / no windows), grid pattern, mullion thickness, glass tint
- STRUCTURAL FORM: precise silhouette — is it a single monolith / L-shape / cantilevered slab / buried mass / curved wall? How does it meet the ground?
- ROOF: flat / slightly pitched / invisible / green roof / stone?
- SCALE: approximate number of floors, estimated ceiling heights, total width vs height ratio
- UNIQUE FEATURES: any cantilevers (which direction, how far), carved voids, arches, water elements, bridges, protruding volumes
- HOW IT MEETS GROUND: sits directly on rock / partially buried / on a plinth / emerging from hillside
- LANDSCAPE: terrain (rocky / forested / desert / snowy / coastal), specific vegetation visible, ground material
- LIGHT & TIME: direction of sunlight, approximate time of day, shadow direction and length
- COLOR PALETTE: list 4-6 dominant colors with precise descriptions (building + landscape)
- INTERIOR HINT: based on the exterior, what materials would the interior structural shell be? (same facade material inside, or different?)

Output as bullet points only. Be exhaustively specific — a future AI must be able to recreate this building identically from your description alone.

At the very end, add exactly one line in this format:
FINGERPRINT: [facade material ≤8 words] | [structural form ≤8 words] | [window type ≤8 words] | [X floors, ~Ym wide]
Example: FINGERPRINT: heavily oxidized corten steel, rust orange | cantilevered horizontal slab over cliff | narrow horizontal slits, no mullions | 3 floors, ~60m wide"""

    for model in ["gemini-2.5-flash", "gemini-1.5-flash-latest"]:
        for attempt in range(2):
            try:
                if image_path and os.path.exists(image_path):
                    with open(image_path, "rb") as f:
                        img_bytes = f.read()
                    contents = [
                        genai_types.Part.from_bytes(data=img_bytes, mime_type="image/png"),
                        vision_instruction,
                    ]
                    print(f"[BuildingSpec] Using Gemini Vision on actual image: {image_path}")
                else:
                    contents = f"""Analyze this architectural image prompt and extract a precise building specification.

PROMPT:
\"\"\"{original_prompt}\"\"\"

{vision_instruction}"""

                response = client.models.generate_content(model=model, contents=contents)
                return response.text.strip()
            except Exception as e:
                print(f"[BuildingSpec] {model} attempt {attempt+1} failed: {e}")
                time.sleep(3)
    return ""


def generate_expand_prompt(building_spec, fingerprint, original_prompt, angle_name, angle_hint, camera_note, is_interior=True):
    """アングルごとの詳細プロンプトを生成"""
    import time

    if is_interior:
        style_rules = f"""INTERIOR AESTHETIC — @matitectura shell + @design.only warmth:
- The CEILING, WALLS, and STRUCTURAL SHELL must reflect the building spec above — if facade is corten steel, interior walls show raw corten or same material; if glass, full glass walls frame the landscape
- WINDOW/OPENINGS: match the spec exactly — same size, same proportions as the exterior
- INTERIOR STYLING (@design.only): warm organic furnishings layered against the raw shell — travertine, warm oak, hand-plastered sand walls, honed stone floors
- FURNITURE: curved organic forms — bouclé sofa, travertine coffee table, walnut bed — lived-in, NOT a showroom
- LIGHTING: warm amber pendants + one oblique natural daylight shaft
- TEXTILES: crumpled linen, sheepskin, woven rug — tactile warmth
- OBJECTS: hand-thrown ceramics, dried botanicals, open art book
- End: "editorial interior photograph, Hasselblad X2D, {camera_note}, correct exposure, rich saturated colors, ultra-sharp focus, natural film grain, NOT a 3D render NOT AI art, NOT a painting, photorealistic 8K\""""
    else:
        style_rules = f"""EXTERIOR RULES:
- Show the SAME building as specified above — exact same materials, form, window pattern
- LANDSCAPE (@gorpcore.jpeg): raw untouched wilderness, earthy muted-rich palette, ancient and documentary
- Foreground terrain detail, building mid-ground, vast horizon
- One strong directional light, hard shadows, deep blacks
- End: "editorial architectural photograph, Hasselblad X2D, {camera_note}, correct exposure, rich saturated colors, ultra-sharp focus, natural film grain, NOT a 3D render NOT AI art, NOT a painting, photorealistic 8K\""""

    contents = f"""You are a world-class architectural photographer. Your images look like REAL photographs — never AI, never renders.

THIS IS THE BUILDING — follow this spec exactly for every detail:
{building_spec}

You are photographing THIS specific building from a new angle. Every visual detail (material, window size, scale, structural form) must be consistent with the spec above.

Shot to create: "{angle_name}"
Direction: {angle_hint}
Camera: {camera_note}

STRICT RULES:
- Window sizes and proportions MUST match the spec — do NOT invent new openings
- Facade material MUST match the spec — do NOT substitute concrete if spec says corten/timber/glass
- Scale MUST match — same floor heights, same footprint proportions
- ABSOLUTELY NO clouds, NO overcast, NO grey sky, NO rain, NO wet surfaces, NO wet walls
- NO humans, NO people, NO figures — zero human presence
- PHYSICS: all elements visibly supported

{style_rules}

Output ONLY the prompt. 200-250 words."""
    for model in ["gemini-2.5-flash", "gemini-1.5-flash-latest"]:
        for attempt in range(2):
            try:
                response = client.models.generate_content(model=model, contents=contents)
                result = response.text.strip()
                # FINGERPRINT を先頭に強制埋め込み（Geminiの解釈ズレを防ぐ）
                if fingerprint:
                    result = f"EXACT SAME BUILDING — {fingerprint}. " + result
                return result
            except Exception as e:
                print(f"[ExpandPrompt] {model} attempt {attempt+1} failed: {e}")
                time.sleep(5)
    return f"{angle_name} of the building, photorealistic 8K"


def run_expand_job(job_id, original_prompt, total, image_filename=None):
    """12アングルを順番に生成（インテリア10室はランダム選択）"""
    import time
    jobs[job_id]["status"] = "running"
    jobs[job_id]["started_at"] = time.time()
    jobs[job_id]["current"] = 0
    durations = []

    # インテリアプールから10室をランダム選択 + 外観2枚を固定で追加
    selected_interiors = random.sample(INTERIOR_ANGLES_POOL, 10)
    angles = selected_interiors + EXTERIOR_ANGLES
    total = len(angles)
    jobs[job_id]["total"] = total

    # 実際の画像パスを解決
    image_path = None
    if image_filename:
        base_dir = os.path.dirname(os.path.abspath(__file__))
        image_path = os.path.join(base_dir, "static", "images", image_filename)

    # 建物仕様書を1回だけ生成して全12枚で共有（実画像をVisionで分析）
    print(f"[Expand {job_id}] Generating building spec...")
    building_spec = generate_building_spec(original_prompt, image_path=image_path)
    print(f"[Expand {job_id}] Building spec ready:\n{building_spec[:200]}")

    # FINGERPRINT を抽出（仕様書末尾の1行）
    fingerprint = ""
    for line in building_spec.split('\n'):
        if line.strip().startswith('FINGERPRINT:'):
            fingerprint = line.strip().replace('FINGERPRINT:', '').strip()
            break
    print(f"[Expand {job_id}] Fingerprint: {fingerprint}")

    for i, (angle_name, angle_hint, camera_note) in enumerate(angles):
        jobs[job_id]["current"] = i + 1
        t0 = time.time()
        try:
            is_interior = i < (total - 2)  # 最後の2枚（Wide Exterior, Aerial）は外観
            prompt = generate_expand_prompt(building_spec, fingerprint, original_prompt, angle_name, angle_hint, camera_note, is_interior)
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
    data = request.json or {}
    custom_hint = data.get("custom_hint", "")
    job_id = uuid.uuid4().hex
    jobs[job_id] = {"status": "running", "results": [], "current": 0, "started_at": 0, "avg_duration": 0}
    t = threading.Thread(target=run_job, args=(job_id, custom_hint), daemon=True)
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

@app.route("/api/analyze", methods=["POST"])
def analyze_image_route():
    """アップロード画像をGemini Visionで分析"""
    import time
    if 'image' not in request.files:
        return jsonify({"error": "no image"}), 400
    file = request.files['image']
    img_bytes = file.read()
    mime_type = file.content_type or "image/jpeg"
    for model in ["gemini-2.5-flash", "gemini-1.5-flash-latest"]:
        try:
            response = client.models.generate_content(
                model=model,
                contents=[
                    genai_types.Part.from_bytes(data=img_bytes, mime_type=mime_type),
                    """Analyze this architectural/landscape image as a design reference. Extract:
- ARCHITECTURAL STYLE: overall aesthetic, influences, era
- MATERIALS: facade materials, exact colors, textures (very specific)
- FORM & GEOMETRY: building shape, silhouette, structural elements
- SCALE: approximate size, floor count, proportions
- LANDSCAPE/SETTING: terrain type, vegetation, climate, geography
- ATMOSPHERE: time of day, weather, lighting quality, mood
- KEY DETAILS: window style, openings, unique features

Be extremely specific and visual. This will be used to generate new buildings inspired by this image."""
                ]
            )
            return jsonify({"analysis": response.text.strip()})
        except Exception as e:
            print(f"[Analyze] {model} failed: {e}")
            time.sleep(3)
    return jsonify({"error": "analysis failed"}), 500


@app.route("/api/generate-from-ref", methods=["POST"])
def generate_from_ref():
    data = request.json
    analysis = data.get("analysis", "")
    if not analysis:
        return jsonify({"error": "no analysis"}), 400
    job_id = uuid.uuid4().hex
    jobs[job_id] = {"status": "running", "results": [], "current": 0, "started_at": 0, "avg_duration": 0}
    t = threading.Thread(target=run_ref_job, args=(job_id, analysis), daemon=True)
    t.start()
    return jsonify({"job_id": job_id})


@app.route("/api/expand", methods=["POST"])
def expand():
    data = request.json
    original_prompt = data.get("prompt", "")
    image_filename = data.get("image", None)  # 選択した外観画像のファイル名
    total = 12  # 10 interiors (random) + 2 exteriors (fixed)
    job_id = uuid.uuid4().hex
    jobs[job_id] = {"status": "running", "results": [], "current": 0, "started_at": 0, "avg_duration": 0, "total": total}
    t = threading.Thread(target=run_expand_job, args=(job_id, original_prompt, total, image_filename), daemon=True)
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
    app.run(debug=False, port=5004, threaded=True)
