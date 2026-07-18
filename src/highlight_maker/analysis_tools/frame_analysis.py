"""
frame_analysis.py

Moduł 1 (część obraz) - Analizator Highlightów.
Wyciąga klatki z wideo (1/sekundę) i ocenia każdą z nich modelem VLM
(Moondream2) pod kątem dynamiki/akcji w skali 1-10.

UWAGA: to jedyny moduł korzystający z GPU w tym etapie. Pamiętaj, żeby
po użyciu zwolnić model z VRAM (funkcja unload_model) przed montażem wideo.
"""

import json
import re
import shutil
from pathlib import Path
from dataclasses import dataclass

import numpy as np
import torch
from PIL import Image
from transformers import Qwen2_5_VLForConditionalGeneration, AutoProcessor
from qwen_vl_utils import process_vision_info
import ffmpeg

# Moondream2 (1.9B) okazał się za słaby do tego zadania - halucynował treści
# nieobecne w kadrze i ignorował instrukcję formatu JSON. Qwen2.5-VL-3B ma
# dużo lepsze grounding (opisuje to co faktycznie widzi) i instruction-following.
# fp16 bez kwantyzacji (~6-7GB VRAM) - celowo bez bitsandbytes (niestabilny na
# Windows), mieści się bez problemu w budżecie 12GB.
MODEL_ID = "Qwen/Qwen2.5-VL-3B-Instruct"

PROMPT = (
    "You are shown ONE image made of two video frames placed side by side, "
    "separated by a thin vertical line.\n"
    "The LEFT half is an earlier frame. The RIGHT half is the current frame, "
    "taken 1 second later.\n"
    "\n"
    "Rate how much movement/action/change happened between the LEFT and RIGHT "
    "frame, from 1 to 10:\n"
    "1-2  = almost no change: the two frames look nearly identical, no visible motion.\n"
    "3-4  = minor change: small movement, slight camera pan, minor object shift.\n"
    "5-6  = moderate change: clearly visible movement, someone walking/running, "
    "active but ordinary gameplay motion.\n"
    "7-8  = large sudden change: fast movement, a hit or collision, sudden camera "
    "shake, a clear highlight-worthy event (kill, goal, trick, big reaction).\n"
    "9-10 = extreme change: explosion, crash, dramatic climax, chaotic fast action "
    "completely different scene composition between the two halves.\n"
    "\n"
    "Respond with ONLY a JSON object, no other text, no markdown, no code fences, "
    "no explanation. The JSON must match exactly this schema:\n"
    '{"dynamism_score": <integer 1-10>}\n'
    "\n"
    "Example valid response:\n"
    '{"dynamism_score": 7}'
)


@dataclass
class FrameScore:
    timestamp_sec: float
    score: float  # 1-10, wynik oceny VLM
    frame_path: str


def extract_frames(video_path: str, out_dir: str, fps: int = 1) -> list[tuple[float, str]]:
    """
    Wycina klatki z wideo co 1/fps sekundy (domyślnie 1 kl./s) przez FFmpeg.
    Zwraca listę (timestamp_sec, sciezka_do_pliku_klatki).
    """
    out_dir = Path(out_dir)
    if out_dir.exists():
        shutil.rmtree(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    pattern = str(out_dir / "frame_%06d.jpg")

    (
        ffmpeg
        .input(video_path)
        .filter("fps", fps=fps)
        .output(pattern, start_number=0, **{"qscale:v": 2})
        .overwrite_output()
        .run(quiet=True)
    )

    frame_files = sorted(out_dir.glob("frame_*.jpg"))
    # klatka numer N odpowiada sekundzie N/fps
    return [(i / fps, str(f)) for i, f in enumerate(frame_files)]


def build_comparison_image(prev_frame_path: str, curr_frame_path: str, target_height: int = 384) -> Image.Image:
    """
    Skleja dwie klatki (poprzednią i bieżącą) w jeden obraz side-by-side,
    z cienką separującą linią pomiędzy nimi. Obie klatki są skalowane do tej
    samej wysokości (zachowując proporcje), żeby model dostał czytelny obraz.
    """
    prev_img = Image.open(prev_frame_path).convert("RGB")
    curr_img = Image.open(curr_frame_path).convert("RGB")

    def resize_to_height(img: Image.Image, height: int) -> Image.Image:
        ratio = height / img.height
        return img.resize((max(1, int(img.width * ratio)), height))

    prev_img = resize_to_height(prev_img, target_height)
    curr_img = resize_to_height(curr_img, target_height)

    separator_width = 4
    total_width = prev_img.width + separator_width + curr_img.width

    canvas = Image.new("RGB", (total_width, target_height), color=(255, 0, 0))
    canvas.paste(prev_img, (0, 0))
    canvas.paste(curr_img, (prev_img.width + separator_width, 0))

    return canvas


def extract_frame_at(video_path: str, timestamp_sec: float, out_path: str) -> str:
    """Wyciąga pojedynczą klatkę z wideo w zadanym momencie (do tagowania segmentów)."""
    out_path_p = Path(out_path)
    out_path_p.parent.mkdir(parents=True, exist_ok=True)

    (
        ffmpeg
        .input(video_path, ss=timestamp_sec)
        .output(str(out_path_p), vframes=1, **{"qscale:v": 2})
        .overwrite_output()
        .run(quiet=True)
    )
    return str(out_path_p)


def build_strip_image(frame_paths: list[str], target_height: int = 320) -> Image.Image:
    """Skleja N klatek poziomo w jeden pasek (np. początek/środek/koniec segmentu)."""
    images = [Image.open(p).convert("RGB") for p in frame_paths]

    def resize_to_height(img: Image.Image, height: int) -> Image.Image:
        ratio = height / img.height
        return img.resize((max(1, int(img.width * ratio)), height))

    images = [resize_to_height(img, target_height) for img in images]
    separator_width = 4
    total_width = sum(img.width for img in images) + separator_width * (len(images) - 1)

    canvas = Image.new("RGB", (total_width, target_height), color=(255, 0, 0))
    x = 0
    for img in images:
        canvas.paste(img, (x, 0))
        x += img.width + separator_width

    return canvas


TAG_PROMPT = (
    "You are shown an image made of frames from a moment in a video timeline, "
    "placed side by side in order (earliest on the LEFT to latest on the RIGHT), "
    "separated by thin vertical lines.\n"
    "\n"
    "Classify this moment into exactly one category:\n"
    '- "highlight": clear exciting/high-action moment - fast movement, impact, '
    "sudden event, something clearly noteworthy is happening.\n"
    '- "normal": ordinary activity, moderate movement, nothing special.\n'
    '- "boring": static or near-static, transition, idle, nothing happening.\n'
    "\n"
    "Also write a short label describing what's happening, max 6 words.\n"
    "\n"
    "Respond with ONLY a JSON object, no other text, no markdown, no code fences:\n"
    '{"tag": "highlight"|"normal"|"boring", "label": "<short description>"}\n'
    "\n"
    "Example valid response:\n"
    '{"tag": "highlight", "label": "player scores a goal"}'
)


def tag_segment(model, processor, frame_paths: list[str]) -> dict:
    """
    Ocenia jakościowo (kategoria + krótki opis) już wykryty przedział czasowy,
    na bazie kilku reprezentatywnych klatek (np. start/środek/koniec).
    Zwraca kategorię, nie liczbę - to zadanie małe VLM-y wykonują dużo pewniej
    niż numeryczne skalowanie (patrz frame_analysis.py, wcześniejsze podejście).
    """
    strip = build_strip_image(frame_paths)
    raw_answer = _run_vlm(model, processor, strip, TAG_PROMPT)
    return _parse_tag_response(raw_answer)


def _parse_tag_response(raw_answer: str) -> dict:
    """
    Parsuje odpowiedź tagującą z tym samym trzypoziomowym fallbackiem co
    _parse_score: czysty JSON -> wyciągnięcie obiektu JSON regexem z tekstu ->
    wyszukanie słowa kluczowego kategorii w surowym tekście.
    """
    raw = raw_answer.strip()

    # próba 1: czysty JSON
    try:
        data = json.loads(raw)
        tag = data.get("tag", "normal")
        label = data.get("label", "")
        if tag in ("highlight", "normal", "boring"):
            return {"tag": tag, "label": label}
    except (json.JSONDecodeError, AttributeError):
        pass

    # próba 2: wyciągnij obiekt JSON z tekstu (np. gdy model doda code fence/komentarz)
    match = re.search(r"\{[^{}]*\"tag\"[^{}]*\}", raw)
    if match:
        try:
            data = json.loads(match.group())
            tag = data.get("tag", "normal")
            label = data.get("label", "")
            if tag in ("highlight", "normal", "boring"):
                return {"tag": tag, "label": label}
        except (json.JSONDecodeError, AttributeError):
            pass

    # próba 3: samo słowo kluczowe gdzieś w tekście, bez poprawnego JSON-a
    lowered = raw.lower()
    for candidate in ("highlight", "boring", "normal"):
        if candidate in lowered:
            print(f"    [debug] nie udało się sparsować JSON, ale znaleziono słowo '{candidate}'. Surowa odpowiedź: {raw[:200]!r}")
            return {"tag": candidate, "label": "(sparsowano z tekstu, nie JSON)"}

    # ostateczny fallback - pokazujemy surową odpowiedź, żeby było widać co model realnie zwrócił
    print(f"    [debug] nie udało się sparsować odpowiedzi VLM. Surowa odpowiedź: {raw[:200]!r}")
    return {"tag": "normal", "label": "(nie udało się otagować)"}


def load_model():
    """Ładuje Qwen2.5-VL-3B-Instruct do GPU (jeśli dostępne). Zwraca (model, processor)."""
    device = "cuda" if torch.cuda.is_available() else "cpu"
    print(f"Ładowanie {MODEL_ID} na {device}...")

    model = Qwen2_5_VLForConditionalGeneration.from_pretrained(
        MODEL_ID,
        torch_dtype=torch.float16 if device == "cuda" else torch.float32,
        device_map=device,
    )
    processor = AutoProcessor.from_pretrained(MODEL_ID)

    return model, processor


def unload_model(model) -> None:
    """Zwalnia model z VRAM - wołaj po zakończeniu analizy klatek."""
    del model
    if torch.cuda.is_available():
        torch.cuda.empty_cache()
    print("Model zwolniony z VRAM.")


def _run_vlm(model, processor, image: Image.Image, prompt: str, max_new_tokens: int = 100) -> str:
    """Odpytuje Qwen2.5-VL o pojedynczy obraz + prompt tekstowy. Zwraca surową odpowiedź."""
    messages = [
        {
            "role": "user",
            "content": [
                {"type": "image", "image": image},
                {"type": "text", "text": prompt},
            ],
        }
    ]

    chat_text = processor.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
    image_inputs, video_inputs = process_vision_info(messages)
    inputs = processor(
        text=[chat_text],
        images=image_inputs,
        videos=video_inputs,
        padding=True,
        return_tensors="pt",
    ).to(model.device)

    with torch.no_grad():
        generated_ids = model.generate(**inputs, max_new_tokens=max_new_tokens)

    trimmed_ids = [out[len(inp):] for inp, out in zip(inputs.input_ids, generated_ids)]
    output_text = processor.batch_decode(
        trimmed_ids, skip_special_tokens=True, clean_up_tokenization_spaces=False
    )[0]

    return output_text


def _parse_score(raw_answer: str) -> float:
    """
    Parsuje odpowiedź modelu jako JSON zgodny ze schematem {"dynamism_score": <1-10>}.
    Model teoretycznie ma zwracać czysty JSON, ale w praktyce VLM-y czasem i tak
    dokleją markdown code fence albo pojedyncze zdanie obok - dlatego najpierw
    próbujemy czystego json.loads, a dopiero potem wyciągamy pierwszy obiekt JSON
    z tekstu jako fallback. Ostateczny fallback: 1.0.
    """
    raw_answer = raw_answer.strip()

    # próba 1: czysty JSON
    try:
        data = json.loads(raw_answer)
        return _clamp_score(data["dynamism_score"])
    except (json.JSONDecodeError, KeyError, TypeError):
        pass

    # próba 2: wyciągnij pierwszy obiekt JSON z tekstu (np. gdy model doda code fence)
    match = re.search(r"\{[^{}]*\"dynamism_score\"\s*:\s*[\d.]+[^{}]*\}", raw_answer)
    if match:
        try:
            data = json.loads(match.group())
            return _clamp_score(data["dynamism_score"])
        except (json.JSONDecodeError, KeyError, TypeError):
            pass

    # próba 3: ostatnia deska ratunku - pierwsza liczba w tekście
    number_match = re.search(r"\d+(\.\d+)?", raw_answer)
    if number_match:
        return _clamp_score(float(number_match.group()))

    return 1.0


def _clamp_score(value) -> float:
    return max(1.0, min(10.0, float(value)))


def score_frame(model, processor, prev_frame_path: str, curr_frame_path: str) -> float:
    """
    Ocena zmiany między dwiema kolejnymi klatkami (poprzednią i bieżącą).
    Zwraca wynik 1-10 - im wyższy, tym większa zmiana/ruch/akcja między nimi.
    """
    comparison_image = build_comparison_image(prev_frame_path, curr_frame_path)
    raw_answer = _run_vlm(model, processor, comparison_image, PROMPT)
    return _parse_score(raw_answer)


def analyze_frames(
    video_path: str,
    tmp_frames_dir: str = "tmp/frames",
    fps: int = 1,
) -> list[FrameScore]:
    """Funkcja wysokopoziomowa: wideo -> lista ocen dynamiki klatek."""
    frames = extract_frames(video_path, tmp_frames_dir, fps=fps)
    print(f"Wyciągnięto {len(frames)} klatek.")

    model, processor = load_model()
    results: list[FrameScore] = []

    try:
        for i, (timestamp, frame_path) in enumerate(frames):
            if i == 0:
                # pierwsza klatka nie ma punktu odniesienia - brak ruchu do zmierzenia
                score = 1.0
            else:
                prev_frame_path = frames[i - 1][1]
                score = score_frame(model, processor, prev_frame_path, frame_path)

            results.append(FrameScore(timestamp_sec=timestamp, score=score, frame_path=frame_path))
            mins, secs = divmod(timestamp, 60)
            print(f"  [{i + 1}/{len(frames)}] {int(mins):02d}:{secs:05.2f}  wynik LLM: {score:.1f}/10")
    finally:
        unload_model(model)

    return results


@dataclass
class DynamicSegment:
    start_sec: float
    end_sec: float
    peak_score: float

    @property
    def duration_sec(self) -> float:
        return self.end_sec - self.start_sec


def find_dynamic_segments(
    scores: list[FrameScore],
    high_threshold: float | None = None,
    low_threshold: float | None = None,
    high_percentile: float = 85.0,
    low_percentile: float = 50.0,
    max_lookback_frames: int = 5,
    merge_gap_sec: float = 2.0,
) -> list[DynamicSegment]:
    """
    Zamienia sekwencję ocen klatek na przedziały czasowe (highlighty), zamiast
    pojedynczych szczytowych klatek. Używa progowania z histerezą:

    - przedział STARTUJE, gdy wynik przekroczy `high_threshold`,
    - cofamy początek przedziału o maks. `max_lookback_frames` klatek wstecz,
      żeby złapać narastanie akcji przed samym szczytem,
    - przedział TRWA dopóki wynik nie spadnie poniżej `low_threshold`
      (nie poniżej high_threshold - to celowe, zapobiega "urywaniu" przedziału
      przy chwilowych, jednoklatkowych spadkach w środku akcji),
    - przedziały leżące bliżej siebie niż `merge_gap_sec` są sklejane w jeden.

    WAŻNE: jeśli `high_threshold`/`low_threshold` nie są podane jawnie, są liczone
    automatycznie jako percentyle rozkładu wyników W TYM KONKRETNYM wideo
    (domyślnie: high = top 15%, low = mediana). To ważne, bo model VLM nie ocenia
    w skali bezwzględnej porównywalnej między różnymi filmami - dynamiczny gameplay
    może mieć wszystkie klatki w okolicach 5-8, a spokojny vlog w okolicach 1-3.
    Progi stałe (np. zawsze 7/4) w skrajnych przypadkach mogą zakwalifikować całe
    wideo jako jeden highlight (za wysoka baza) albo nie znaleźć nic (za niska).
    Progi absolutne wciąż możesz podać jawnie, jeśli wolisz pełną kontrolę.

    Zakłada, że `scores` są posortowane rosnąco po czasie (tak jak zwraca je
    analyze_frames przy stałym fps).
    """
    scores = sorted(scores, key=lambda s: s.timestamp_sec)
    n = len(scores)

    values = np.array([s.score for s in scores])
    if high_threshold is None:
        high_threshold = float(np.percentile(values, high_percentile))
    if low_threshold is None:
        low_threshold = float(np.percentile(values, low_percentile))

    print(
        f"Progi histerezy: high={high_threshold:.2f} (p{high_percentile:.0f}), "
        f"low={low_threshold:.2f} (p{low_percentile:.0f}) "
        f"[rozkład wyników: min={values.min():.1f}, max={values.max():.1f}, "
        f"mean={values.mean():.1f}, median={np.median(values):.1f}]"
    )

    raw_segments: list[DynamicSegment] = []
    in_segment = False
    seg_start_idx = 0
    peak_score = 0.0

    i = 0
    while i < n:
        if not in_segment:
            if scores[i].score >= high_threshold:
                # start przedziału - cofamy się, dopóki wynik rośnie/jest wysoki
                start_idx = i
                lookback = 0
                j = i - 1
                while j >= 0 and lookback < max_lookback_frames and scores[j].score < high_threshold:
                    start_idx = j
                    lookback += 1
                    j -= 1

                seg_start_idx = start_idx
                peak_score = scores[i].score
                in_segment = True
        else:
            peak_score = max(peak_score, scores[i].score)
            if scores[i].score < low_threshold:
                raw_segments.append(
                    DynamicSegment(
                        start_sec=scores[seg_start_idx].timestamp_sec,
                        end_sec=scores[i].timestamp_sec,
                        peak_score=peak_score,
                    )
                )
                in_segment = False
        i += 1

    if in_segment:
        raw_segments.append(
            DynamicSegment(
                start_sec=scores[seg_start_idx].timestamp_sec,
                end_sec=scores[-1].timestamp_sec,
                peak_score=peak_score,
            )
        )

    return _merge_close_segments(raw_segments, merge_gap_sec)


def _merge_close_segments(
    segments: list[DynamicSegment], merge_gap_sec: float
) -> list[DynamicSegment]:
    """Skleja przedziały, między którymi jest przerwa krótsza niż merge_gap_sec."""
    if not segments:
        return []

    merged = [segments[0]]
    for seg in segments[1:]:
        last = merged[-1]
        if seg.start_sec - last.end_sec <= merge_gap_sec:
            merged[-1] = DynamicSegment(
                start_sec=last.start_sec,
                end_sec=seg.end_sec,
                peak_score=max(last.peak_score, seg.peak_score),
            )
        else:
            merged.append(seg)

    return merged


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Użycie: python frame_analysis.py sciezka_do_wideo.mp4")
        sys.exit(1)

    video_path = sys.argv[1]
    print(f"Analizuję klatki: {video_path}")

    scores = analyze_frames(video_path)
    segments = find_dynamic_segments(scores)

    print(f"\nWykryto {len(segments)} przedziałów dynamicznych:")
    for seg in segments:
        start_m, start_s = divmod(seg.start_sec, 60)
        end_m, end_s = divmod(seg.end_sec, 60)
        print(
            f"  {int(start_m):02d}:{start_s:05.2f} -> {int(end_m):02d}:{end_s:05.2f} "
            f"(dł. {seg.duration_sec:.1f}s, peak: {seg.peak_score:.1f}/10)"
        )