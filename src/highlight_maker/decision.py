"""
decision.py

Moduł decyzyjny - Analizator Highlightów.

Łączy dwa niezależne, tanie sygnały:
  - audio_analysis.compute_energy_timeline (głośność, per sekunda, 0-1)
  - motion_analysis.analyze_motion         (ruch/optical flow, per sekunda, 0-1)

...w jeden złożony sygnał "interesujące", segmentuje go metodą histerezy
(ten sam mechanizm co w frame_analysis.find_dynamic_segments - celowo, bo
łapie zarówno nagłe skoki, jak i przedziały utrzymującej się wysokiej
aktywności aż do zaniku).

Na końcu, dla każdego wykrytego przedziału, wyciąga 3 reprezentatywne klatki
(start/środek/koniec) i wysyła je do VLM (Moondream2) żeby otagować moment
kategorią (highlight/normal/boring) + krótkim opisem.

Zwraca ostateczną listę przedziałów czasowych highlightów (start -> koniec).
"""

from pathlib import Path
from dataclasses import dataclass

import numpy as np

from analysis_tools.audio_analysis import compute_energy_timeline
from analysis_tools.motion_analysis import analyze_motion
from analysis_tools.frame_analysis import extract_frame_at, load_model, unload_model, tag_segment


@dataclass
class Highlight:
    start_sec: float
    end_sec: float
    composite_peak: float
    tag: str = "untagged"
    label: str = ""

    @property
    def duration_sec(self) -> float:
        return self.end_sec - self.start_sec


def _combine_signals(
    audio_points: list,
    motion_points: list,
    audio_weight: float = 0.4,
    motion_weight: float = 0.6,
) -> list[tuple[float, float]]:
    """
    Łączy audio i motion w jeden sygnał per sekunda. Motion ma wyższą wagę
    domyślnie, bo to on niesie główny sygnał "coś się dzieje wizualnie";
    audio dobija tam, gdzie ruch obrazu mógł nie złapać (np. nagły krzyk/wybuch
    dźwiękowy przy relatywnie stabilnym kadrze).

    Sygnały mogą mieć nieco inną długość/próbkowanie (różne moduły, różne
    zaokrąglenia) - łączymy po wspólnych sekundach, brakujące traktujemy jako 0.
    """
    audio_map = {int(p.timestamp_sec): p.energy for p in audio_points}
    motion_map = {int(p.timestamp_sec): p.score for p in motion_points}

    all_seconds = sorted(set(audio_map.keys()) | set(motion_map.keys()))

    combined = []
    for sec in all_seconds:
        a = audio_map.get(sec, 0.0)
        m = motion_map.get(sec, 0.0)
        composite = audio_weight * a + motion_weight * m
        combined.append((float(sec), composite))

    return combined


def _find_segments_hysteresis(
    scores: list[tuple[float, float]],
    high_percentile: float = 85.0,
    low_percentile: float = 50.0,
    max_lookback_sec: int = 5,
    merge_gap_sec: float = 2.0,
) -> list[Highlight]:
    """
    Ten sam algorytm co frame_analysis.find_dynamic_segments, ale działający na
    generycznych parach (timestamp, score) zamiast na FrameScore - żeby nie
    duplikować typów między modułami. Świadomie trzymany jako osobna, prosta
    implementacja zamiast dziedziczenia/importu przez dataclassy.
    """
    scores = sorted(scores, key=lambda s: s[0])
    n = len(scores)

    values = np.array([s[1] for s in scores])
    high_threshold = float(np.percentile(values, high_percentile))
    low_threshold = float(np.percentile(values, low_percentile))

    print(
        f"Progi histerezy (sygnał złożony): high={high_threshold:.3f} (p{high_percentile:.0f}), "
        f"low={low_threshold:.3f} (p{low_percentile:.0f}) "
        f"[min={values.min():.3f}, max={values.max():.3f}, mean={values.mean():.3f}]"
    )

    raw_segments: list[Highlight] = []
    in_segment = False
    seg_start_idx = 0
    peak_score = 0.0

    i = 0
    while i < n:
        timestamp, score = scores[i]
        if not in_segment:
            if score >= high_threshold:
                start_idx = i
                lookback = 0
                j = i - 1
                while j >= 0 and lookback < max_lookback_sec and scores[j][1] < high_threshold:
                    start_idx = j
                    lookback += 1
                    j -= 1
                seg_start_idx = start_idx
                peak_score = score
                in_segment = True
        else:
            peak_score = max(peak_score, score)
            if score < low_threshold:
                raw_segments.append(
                    Highlight(
                        start_sec=scores[seg_start_idx][0],
                        end_sec=timestamp,
                        composite_peak=peak_score,
                    )
                )
                in_segment = False
        i += 1

    if in_segment:
        raw_segments.append(
            Highlight(
                start_sec=scores[seg_start_idx][0],
                end_sec=scores[-1][0],
                composite_peak=peak_score,
            )
        )

    return _merge_close_highlights(raw_segments, merge_gap_sec)


def _merge_close_highlights(segments: list[Highlight], merge_gap_sec: float) -> list[Highlight]:
    if not segments:
        return []

    merged = [segments[0]]
    for seg in segments[1:]:
        last = merged[-1]
        if seg.start_sec - last.end_sec <= merge_gap_sec:
            merged[-1] = Highlight(
                start_sec=last.start_sec,
                end_sec=seg.end_sec,
                composite_peak=max(last.composite_peak, seg.composite_peak),
            )
        else:
            merged.append(seg)

    return merged


def _split_long_highlights(
    highlights: list[Highlight],
    combined_scores: list[tuple[float, float]],
    max_segment_sec: float,
) -> list[Highlight]:
    """
    Dzieli segmenty dłuższe niż max_segment_sec na kilka krótszych, wycentrowanych
    na lokalnych szczytach sygnału złożonego (metoda peak-picking / non-max
    suppression): bierzemy najwyższy nieużyty jeszcze punkt w przedziale, budujemy
    wokół niego okno o długości max_segment_sec, oznaczamy pokryte punkty jako
    zużyte, powtarzamy aż cały oryginalny przedział zostanie pokryty.

    Dzięki temu z jednego 60-sekundowego "wielkiego" highlightu robi się kilka
    krótszych klipów wyśrodkowanych dokładnie na najciekawszych momentach,
    zamiast arbitralnego cięcia co N sekund.
    """
    result: list[Highlight] = []

    for h in highlights:
        if h.duration_sec <= max_segment_sec:
            result.append(h)
            continue

        points_in_range = [
            (t, s) for t, s in combined_scores if h.start_sec <= t <= h.end_sec
        ]
        if not points_in_range:
            result.append(h)
            continue

        used = [False] * len(points_in_range)
        sub_segments: list[Highlight] = []
        half_window = max_segment_sec / 2

        while not all(used):
            best_idx = max(
                (i for i in range(len(points_in_range)) if not used[i]),
                key=lambda i: points_in_range[i][1],
            )
            peak_time, peak_score = points_in_range[best_idx]

            win_start = max(h.start_sec, peak_time - half_window)
            win_end = min(h.end_sec, peak_time + half_window)
            # jeśli okno przycięte przy krawędzi segmentu, dosuwamy je do pełnej
            # długości max_segment_sec (o ile mieści się w granicach oryginału)
            if win_end - win_start < max_segment_sec:
                if win_start == h.start_sec:
                    win_end = min(h.end_sec, win_start + max_segment_sec)
                elif win_end == h.end_sec:
                    win_start = max(h.start_sec, win_end - max_segment_sec)

            sub_segments.append(
                Highlight(start_sec=win_start, end_sec=win_end, composite_peak=peak_score)
            )

            for i, (t, _) in enumerate(points_in_range):
                if win_start <= t <= win_end:
                    used[i] = True

        sub_segments.sort(key=lambda seg: seg.start_sec)
        result.extend(sub_segments)

    return result


def _tag_highlights(video_path: str, highlights: list[Highlight], tmp_dir: str = "tmp/tag_frames") -> None:
    """Modyfikuje highlights in-place, dopisując tag + label z VLM."""
    if not highlights:
        return

    model, processor = load_model()
    tmp_dir_p = Path(tmp_dir)

    try:
        for idx, h in enumerate(highlights):
            mid_sec = (h.start_sec + h.end_sec) / 2
            frame_paths = [
                extract_frame_at(video_path, h.start_sec, str(tmp_dir_p / f"seg{idx}_start.jpg")),
                extract_frame_at(video_path, mid_sec, str(tmp_dir_p / f"seg{idx}_mid.jpg")),
                extract_frame_at(video_path, h.end_sec, str(tmp_dir_p / f"seg{idx}_end.jpg")),
            ]
            result = tag_segment(model, processor, frame_paths)
            h.tag = result["tag"]
            h.label = result["label"]

            mins, secs = divmod(h.start_sec, 60)
            print(f"  [{idx + 1}/{len(highlights)}] {int(mins):02d}:{secs:05.2f}  "
                  f"tag={h.tag:9s}  label=\"{h.label}\"")
    finally:
        unload_model(model)


def analyze_video(
    video_path: str,
    audio_weight: float = 0.4,
    motion_weight: float = 0.6,
    high_percentile: float = 85.0,
    low_percentile: float = 50.0,
    max_segment_sec: float | None = 20.0,
    tag_with_llm: bool = True,
    drop_boring: bool = True,
) -> list[Highlight]:
    """
    Funkcja wysokopoziomowa: wideo -> lista przedziałów czasowych highlightów.

    1. liczy audio energy timeline,
    2. liczy motion timeline (optical flow),
    3. łączy w jeden sygnał złożony,
    4. segmentuje histerezą (nagłe skoki + utrzymująca się aktywność),
    5. dzieli zbyt długie segmenty na krótsze, wycentrowane na lokalnych szczytach,
    6. (opcjonalnie) taguje każdy przedział LLM-em i odrzuca te oznaczone "boring".
    """
    print("== 1/5: Analiza audio ==")
    audio_points = compute_energy_timeline(video_path)

    print("== 2/5: Analiza ruchu ==")
    motion_points = analyze_motion(video_path)

    print("== 3/5: Łączenie sygnałów i segmentacja ==")
    combined = _combine_signals(audio_points, motion_points, audio_weight, motion_weight)
    highlights = _find_segments_hysteresis(combined, high_percentile, low_percentile)
    print(f"Wykryto {len(highlights)} kandydatów na highlight (przed podziałem długich).")

    print("== 4/5: Podział zbyt długich segmentów ==")
    if max_segment_sec is not None:
        before = len(highlights)
        highlights = _split_long_highlights(highlights, combined, max_segment_sec)
        if len(highlights) != before:
            print(f"Podzielono długie segmenty: {before} -> {len(highlights)} kandydatów.")
    else:
        print("Pominięte (max_segment_sec=None).")

    if tag_with_llm and highlights:
        print("== 5/5: Tagowanie kandydatów (VLM) ==")
        _tag_highlights(video_path, highlights)

        if drop_boring:
            before = len(highlights)
            highlights = [h for h in highlights if h.tag != "boring"]
            print(f"Odrzucono {before - len(highlights)} kandydatów oznaczonych jako 'boring'.")
    else:
        print("== 5/5: pominięte (tag_with_llm=False) ==")

    return highlights


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Analizator highlightów - łączy audio + ruch (optical flow), "
                     "segmentuje momenty akcji i taguje je LLM-em.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )

    parser.add_argument(
        "video_path",
        help="Ścieżka do pliku wideo do analizy.",
    )
    parser.add_argument(
        "--audio-weight",
        type=float,
        default=0.4,
        help="Waga sygnału audio (głośność) w sygnale złożonym. "
             "Zwiększ, jeśli highlighty to głównie głośne momenty "
             "(krzyki, wybuchy) przy relatywnie stabilnym obrazie.",
    )
    parser.add_argument(
        "--motion-weight",
        type=float,
        default=0.6,
        help="Waga sygnału ruchu (optical flow) w sygnale złożonym. "
             "Zwiększ, jeśli highlighty to głównie wizualna akcja "
             "niekoniecznie głośna (np. szybki montaż, szybki ruch kamery).",
    )
    parser.add_argument(
        "--high-percentile",
        type=float,
        default=85.0,
        help="Percentyl sygnału złożonego, powyżej którego STARTUJE przedział "
             "highlightu. Wyższy = mniej, ale bardziej wyraźnych highlightów. "
             "Obniż, jeśli za mało kandydatów; podnieś, jeśli za dużo/za czułe.",
    )
    parser.add_argument(
        "--low-percentile",
        type=float,
        default=50.0,
        help="Percentyl sygnału złożonego, poniżej którego KOŃCZY SIĘ przedział "
             "highlightu (histereza - musi być niższy niż high-percentile). "
             "Wyższy = krótsze, ciaśniej przycięte highlighty; niższy = dłuższe, "
             "bo przedział 'trzyma się' dopóki sygnał wyraźnie nie opadnie.",
    )
    parser.add_argument(
        "--max-segment-sec",
        type=float,
        default=20.0,
        help="Maksymalna długość pojedynczego highlightu w sekundach. Dłuższe "
             "segmenty są dzielone na kilka krótszych, wycentrowanych na "
             "lokalnych szczytach sygnału. Ustaw 0 lub użyj --no-max-segment, "
             "żeby wyłączyć dzielenie i zostawić segmenty w oryginalnej długości.",
    )
    parser.add_argument(
        "--no-max-segment",
        action="store_true",
        help="Wyłącza dzielenie długich segmentów (ignoruje --max-segment-sec).",
    )
    parser.add_argument(
        "--no-tag",
        action="store_true",
        help="Pomija tagowanie LLM-em (krok 5/5) - szybsze, ale bez kategorii "
             "highlight/normal/boring i bez opisu. Wszystkie znalezione "
             "kandydaty trafiają na wyjście bez filtrowania.",
    )
    parser.add_argument(
        "--keep-boring",
        action="store_true",
        help="Nie odrzuca kandydatów otagowanych przez LLM jako 'boring'. "
             "Przydatne do debugowania, żeby zobaczyć wszystko co zostało wykryte.",
    )

    args = parser.parse_args()

    highlights = analyze_video(
        video_path=args.video_path,
        audio_weight=args.audio_weight,
        motion_weight=args.motion_weight,
        high_percentile=args.high_percentile,
        low_percentile=args.low_percentile,
        max_segment_sec=None if args.no_max_segment else args.max_segment_sec,
        tag_with_llm=not args.no_tag,
        drop_boring=not args.keep_boring,
    )

    print(f"\n=== WYNIK: {len(highlights)} highlightów ===")
    for h in sorted(highlights, key=lambda x: x.start_sec):
        start_m, start_s = divmod(h.start_sec, 60)
        end_m, end_s = divmod(h.end_sec, 60)
        print(
            f"  {int(start_m):02d}:{start_s:05.2f} -> {int(end_m):02d}:{end_s:05.2f} "
            f"(dł. {h.duration_sec:.1f}s, peak: {h.composite_peak:.2f}, "
            f"tag: {h.tag}, \"{h.label}\")"
        )