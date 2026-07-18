"""
audio_analysis.py

Moduł 1 (część audio) - Analizator Highlightów.
Wyciąga ścieżkę audio z wideo i wykrywa momenty nagłego wzrostu głośności
(RMS energy) - kandydatów na highlighty. Nie używa GPU.
"""

from pathlib import Path
from dataclasses import dataclass

import numpy as np
import librosa
import moviepy.editor as mp


@dataclass
class AudioPeak:
    timestamp_sec: float
    energy: float  # znormalizowana wartość RMS w tym momencie (0-1 względem max w pliku)


def extract_audio(video_path: str, out_wav_path: str) -> str:
    """Wyciąga ścieżkę audio z wideo do pliku .wav (potrzebne dla librosa)."""
    video_path = Path(video_path)
    out_wav_path = Path(out_wav_path)
    out_wav_path.parent.mkdir(parents=True, exist_ok=True)

    clip = mp.VideoFileClip(str(video_path))
    if clip.audio is None:
        raise ValueError(f"Plik {video_path} nie ma ścieżki audio.")

    clip.audio.write_audiofile(str(out_wav_path), fps=22050, logger=None)
    clip.close()
    return str(out_wav_path)


def compute_rms_energy(wav_path: str, hop_length: int = 512) -> tuple[np.ndarray, np.ndarray]:
    """
    Liczy RMS energy w oknach czasowych całego pliku audio.

    Zwraca:
        times  - tablica sekund odpowiadająca każdej próbce RMS
        rms    - tablica wartości RMS (głośności) w tych momentach
    """
    y, sr = librosa.load(wav_path, sr=None)
    rms = librosa.feature.rms(y=y, hop_length=hop_length)[0]
    times = librosa.frames_to_time(np.arange(len(rms)), sr=sr, hop_length=hop_length)
    return times, rms


def find_volume_peaks(
    times: np.ndarray,
    rms: np.ndarray,
    threshold_percentile: float = 90.0,
    min_gap_sec: float = 3.0,
) -> list[AudioPeak]:
    """
    Znajduje momenty, gdzie głośność przekracza zadany percentyl (domyślnie top 10%
    najgłośniejszych momentów w pliku), z minimalnym odstępem między wykrytymi
    peakami (żeby nie łapać 10 sekund tego samego wybuchu jako 10 highlightów).
    """
    threshold = np.percentile(rms, threshold_percentile)
    peak_mask = rms >= threshold

    peaks: list[AudioPeak] = []
    last_peak_time = -min_gap_sec  # żeby pierwszy peak zawsze przeszedł

    # normalizacja energii do 0-1 względem maksimum w pliku
    max_rms = rms.max() if rms.max() > 0 else 1.0

    for t, r, is_peak in zip(times, rms, peak_mask):
        if is_peak and (t - last_peak_time) >= min_gap_sec:
            peaks.append(AudioPeak(timestamp_sec=float(t), energy=float(r / max_rms)))
            last_peak_time = t

    return peaks


@dataclass
class AudioEnergyPoint:
    timestamp_sec: float
    energy: float  # znormalizowana wartość 0-1 względem maksimum w całym pliku


def compute_energy_timeline(
    video_path: str,
    tmp_wav_path: str = "tmp/audio_tmp.wav",
) -> list[AudioEnergyPoint]:
    """
    Ciągły sygnał głośności, jeden wynik na sekundę, znormalizowany 0-1.
    W przeciwieństwie do find_volume_peaks (który zwraca tylko wybrane szczyty),
    to zwraca pełną oś czasu - potrzebne do łączenia z sygnałem ruchu w decision.py.
    """
    wav_path = extract_audio(video_path, tmp_wav_path)
    times, rms = compute_rms_energy(wav_path)

    max_rms = rms.max() if rms.max() > 0 else 1.0
    normalized = rms / max_rms

    buckets: dict[int, list[float]] = {}
    for t, v in zip(times, normalized):
        buckets.setdefault(int(t), []).append(float(v))

    return [
        AudioEnergyPoint(timestamp_sec=float(second), energy=float(np.mean(vals)))
        for second, vals in sorted(buckets.items())
    ]


def analyze_audio(
    video_path: str,
    tmp_wav_path: str = "tmp/audio_tmp.wav",
    threshold_percentile: float = 90.0,
    min_gap_sec: float = 3.0,
) -> list[AudioPeak]:
    """Funkcja wysokopoziomowa: wideo -> lista wykrytych peaków głośności."""
    wav_path = extract_audio(video_path, tmp_wav_path)
    times, rms = compute_rms_energy(wav_path)
    peaks = find_volume_peaks(times, rms, threshold_percentile, min_gap_sec)
    return peaks


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Użycie: python audio_analysis.py sciezka_do_wideo.mp4")
        sys.exit(1)

    video_path = sys.argv[1]
    print(f"Analizuję audio: {video_path}")

    peaks = analyze_audio(video_path)

    if not peaks:
        print("Nie znaleziono wyraźnych peaków głośności.")
    else:
        print(f"Znaleziono {len(peaks)} kandydatów na highlight (audio):")
        for p in peaks:
            mins, secs = divmod(p.timestamp_sec, 60)
            print(f"  {int(mins):02d}:{secs:05.2f}  (energia: {p.energy:.2f})")