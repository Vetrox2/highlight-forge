"""
motion_analysis.py

Moduł 1 (część obraz, wersja 2) - Analizator Highlightów.

Zamiast pytać VLM "jak bardzo klatka jest dynamiczna" (zadanie, do którego małe
modele jak Moondream2 nie są przystosowane - patrz commit history/dyskusja),
liczymy ruch bezpośrednio metodą optical flow (Farneback, OpenCV). To dużo
tańsze (brak GPU/VLM), deterministyczne i daje gęsty, dobrze różnicujący
sygnał w każdej sekundzie filmu.

VLM wraca do gry dopiero na poziomie już wykrytych kandydatów (patrz decision.py),
jako filtr semantyczny odpowiadający na proste pytanie kategoryczne, nie liczbowe.
"""

from pathlib import Path
from dataclasses import dataclass

import cv2
import numpy as np


@dataclass
class MotionScore:
    timestamp_sec: float
    score: float  # znormalizowana wartość 0-1 względem maksimum w całym filmie


def analyze_motion(
    video_path: str,
    sample_fps: float = 5.0,
    resize_width: int = 320,
) -> list[MotionScore]:
    """
    Liczy ruch między kolejnymi próbkowanymi klatkami metodą dense optical flow
    (Farneback). Zwraca jeden wynik na sekundę (uśredniony z próbek w danej sekundzie).

    sample_fps: ile klatek na sekundę filmu analizujemy (5 to dobry kompromis -
                wystarczająco gęsto, żeby złapać krótkie akcje, wystarczająco
                rzadko, żeby było szybkie nawet na długich filmach).
    resize_width: klatki są skalowane w dół przed liczeniem flow (mniejszy obraz
                  = dużo szybciej, a dokładność dla samej detekcji "ile się dzieje"
                  praktycznie nie cierpi).
    """
    video_path = Path(video_path)
    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        raise ValueError(f"Nie mogę otworzyć wideo: {video_path}")

    native_fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    frame_step = max(1, round(native_fps / sample_fps))

    raw_scores: list[tuple[float, float]] = []  # (timestamp_sec, magnitude)
    prev_gray = None
    frame_idx = 0

    while True:
        ret, frame = cap.read()
        if not ret:
            break

        if frame_idx % frame_step == 0:
            h, w = frame.shape[:2]
            scale = resize_width / w
            resized = cv2.resize(frame, (resize_width, int(h * scale)))
            gray = cv2.cvtColor(resized, cv2.COLOR_BGR2GRAY)

            if prev_gray is not None:
                flow = cv2.calcOpticalFlowFarneback(
                    prev_gray, gray, None,
                    pyr_scale=0.5, levels=3, winsize=15,
                    iterations=3, poly_n=5, poly_sigma=1.2, flags=0,
                )
                magnitude = np.sqrt(flow[..., 0] ** 2 + flow[..., 1] ** 2).mean()
                timestamp = frame_idx / native_fps
                raw_scores.append((timestamp, float(magnitude)))

            prev_gray = gray

        frame_idx += 1

    cap.release()

    if not raw_scores:
        return []

    # normalizacja 0-1 względem maksimum w całym filmie
    max_magnitude = max(s for _, s in raw_scores) or 1.0
    per_sample = [MotionScore(timestamp_sec=t, score=m / max_magnitude) for t, m in raw_scores]

    return _aggregate_per_second(per_sample)


def _aggregate_per_second(scores: list[MotionScore]) -> list[MotionScore]:
    """Uśrednia próbki (kilka na sekundę przy sample_fps>1) do jednego wyniku/sekundę."""
    buckets: dict[int, list[float]] = {}
    for s in scores:
        second = int(s.timestamp_sec)
        buckets.setdefault(second, []).append(s.score)

    return [
        MotionScore(timestamp_sec=float(second), score=float(np.mean(values)))
        for second, values in sorted(buckets.items())
    ]


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Użycie: python motion_analysis.py sciezka_do_wideo.mp4")
        sys.exit(1)

    video_path = sys.argv[1]
    print(f"Analizuję ruch: {video_path}")

    scores = analyze_motion(video_path)

    values = np.array([s.score for s in scores])
    print(
        f"\nRozkład wyników ruchu: min={values.min():.2f}, max={values.max():.2f}, "
        f"mean={values.mean():.2f}, median={np.median(values):.2f}\n"
    )

    for s in scores:
        mins, secs = divmod(s.timestamp_sec, 60)
        bar = "#" * int(s.score * 40)
        print(f"  {int(mins):02d}:{secs:05.2f}  {s.score:.2f}  {bar}")
