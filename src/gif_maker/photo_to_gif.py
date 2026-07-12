"""
photo_to_gif.py - Konwerter zdjęć na animowane GIF-y

================================================================================
OPIS
================================================================================

Tworzy animowany GIF z wybranych zdjęć (JPG, PNG, TIFF, BMP, WEBP oraz DNG i inne
formaty RAW obsługiwane przez rawpy: CR2, CR3, NEF, ARW, RAF, ORF, RW2).

Wybór zdjęć odbywa się przez natywne okno dialogowe Windows (tkinter.filedialog).
Kolejność, w jakiej zaznaczysz pliki w oknie, jest domyślnie kolejnością klatek
w GIF-ie (chyba że użyjesz flagi --sort).

================================================================================
INSTALACJA
================================================================================

1. Wymagane biblioteki Python:
   pipenv install pillow numpy
   pipenv install rawpy      # obsługa DNG/RAW (opcjonalnie)

2. Wymagane narzędzie externe (tylko jeśli wczytasz problem. DNG z telefonów):
   winget install --id OliverBetz.ExifTool -e

3. Opcjonalnie, tylko dla --lossy (BEZ instalacji systemowej):
   Pobierz gifsicle.exe (paczka win64) z https://eternallybored.org/misc/gifsicle/
   i wrzuć plik gifsicle.exe do tego samego folderu co ten skrypt.
   Skrypt znajdzie go automatycznie - nie trzeba nic instalować ani zmieniać PATH.

================================================================================
URUCHOMIENIE
================================================================================

Podstawowe (bez parametrów):
    pipenv run python photo_to_gif.py

Z parametrami:
    pipenv run python photo_to_gif.py --fps 8 --frames-per-photo 3 --loop 0

================================================================================
PARAMETRY CLI - SZCZEGÓŁOWY OPIS
================================================================================

--fps <liczba>
    Bazowa szybkość animacji w klatkach na sekundę (default: 10.0)
    Czas wyświetlania jednej klatki = 1000 / fps milisekund.
    Przykłady:
      10.0 fps  → 100 ms na klatkę (wolna animacja)
      15.0 fps  → 67 ms na klatkę
      30.0 fps  → 33 ms na klatkę (szybka animacja)
    Uwaga: Some GIF viewers ignorują bardzo małe wartości; praktycznie min ~8 fps.

--frames-per-photo <liczba>
    Ile razy powielić każdą klatkę (default: 1)
    Każde zdjęcie będzie wyświetlane N razy z rzędu, co wydłuża jego czas ekspozycji.
    Przykłady:
      --frames-per-photo 1  → każde zdjęcie 1 raz
      --frames-per-photo 3  → każde zdjęcie 3 razy (3x dłużej)
      --frames-per-photo 5  → każde zdjęcie 5 razy
    Efekt: połączenie z --fps kontroluje finalny czas wyświetlania każdego zdjęcia.
    Przykład: --fps 10 --frames-per-photo 3 → każde zdjęcie 300 ms.

--loop <liczba>
    Liczba powtórzeń animacji (default: 0)
      0    → animacja pętli w nieskończoność (standardowe dla GIF-ów)
      1    → animacja odtwarzana raz (bez pętli)
      N>1  → animacja odtwarzana N razy

--output <ścieżka>
    Ścieżka zapisu pliku .gif (default: interaktywne okno SaveAs)
    Przykład: --output "D:\filmy\animation.gif"
    Jeśli pominięty, pojawi się okno systemowe do wyboru folderu i nazwy.

--sort {selection|name|date}
    Kolejność klatek w GIF-ie (default: selection)
      selection  → kolejność zaznaczenia w oknie wyboru plików
      name       → alfabetycznie (A→Z) wg nazwy pliku
      date       → wg daty modyfikacji pliku (stare→nowe)
    Kombinuje się z --reverse.

--reverse
    Odwraca kolejność klatek (domyślnie nie).
    Przykład: --sort name --reverse
      Alfabetycznie odwrotnie (Z→A).

--canvas {first|max}
    Rozmiar płótna GIF-a (default: max)
      first  → rozmiar pierwszego wczytanego zdjęcia
               Pozostałe zdjęcia (jeśli większe) będą przycięte/zmniejszone.
      max    → największy wymiar spośród wszystkich zdjęć
               Pozostałe zdjęcia zostają dopasowane bez przycinania (letterbox).
               Mniejsze obrazy są wysrodkowywane z czarnym tłem.
    Użyteczne gdy zdjęcia mają różne wymiary.

--require-same-size
    Zamiast dopasowywać rozmiary, przerywa działanie jeśli zdjęcia mają różne wymiary.
    Przydatne do pełnej kontroli — gwarantuje, że wszystkie piksele pochodzą ze
    zdjęć o dokładnie tej samej rozdzielczości (zero skalowania/letterboxu).
    Błąd: "Zdjęcia mają różne wymiary (...), a podano --require-same-size. Przerywam."

--dither {none|floyd-steinberg}
    Dithering przy konwersji do palety 256 kolorów (default: floyd-steinberg)
      none              → bez ditheringu (szybko, ale mogą być widoczne artefakty kolorów)
      floyd-steinberg   → Floyd-Steinberg dithering (wolniej, ale lepsza jakość wizualna)
    Format GIF obsługuje max 256 kolorów — to twarde ograniczenie. Dithering to
    technika simulacji większej ilości kolorów przez rozmieszczanie pikseli.

--quantize {median-cut|fast-octree|libimagequant}
    Metoda doboru palety 256 kolorów (default: median-cut)
      median-cut        → medianą; szybka, uniwersalna (zawsze dostępna)
      fast-octree       → octree; szybka, dobra dla syntetycznych obrazów
      libimagequant     → najlepsza jakość, ale wymaga zainstalowanej biblioteki
                         libimagequant w systemie (rzadko dostępna)
    Jeśli wybrana metoda jest niedostępna, skrypt automatycznie wraca na median-cut.

--------------------------------------------------------------------------------
KOMPRESJA (OPCJONALNE - redukcja jakości w celu zmniejszenia rozmiaru pliku)
--------------------------------------------------------------------------------
Domyślnie skrypt nie robi żadnej dodatkowej kompresji ponad twarde ograniczenia
formatu GIF. Poniższe parametry są opcjonalne i świadomie obniżają jakość, żeby
zmniejszyć plik i/lub poprawić płynność odtwarzania w słabszych przeglądarkach/
aplikacjach.

--scale <procent>
    Skaluje wszystkie zdjęcia do podanego procentu oryginalnego rozmiaru (default: 100.0)
    100.0 → brak zmian, pełna rozdzielczość (domyślne zachowanie)
    Przykłady:
      --scale 100   → bez zmian (jak dotychczas)
      --scale 75    → 75% wymiarów (plik ~2x mniejszy)
      --scale 50    → połowa wymiarów (plik ~4x mniejszy, bo piksele w dwóch wymiarach)
      --scale 25    → ćwiartka wymiarów (plik ~16x mniejszy, mocno widoczna utrata detali)
    Najskuteczniejszy sposób na zmniejszenie pliku i poprawę płynności odtwarzania.

--colors <liczba 2-256>
    Liczba kolorów w palecie GIF-a (default: 256 - maksimum formatu)
    Przykłady:
      --colors 256  → pełna paleta (domyślne, najlepsza jakość koloru)
      --colors 128  → połowa palety (mniejszy plik, delikatnie gorsze gradienty)
      --colors 64   → wyraźnie mniejsza paleta (zauważalna utrata jakości koloru)
      --colors 32   → mocno ograniczona paleta (widoczne "pasy" na gradientach/niebie)

--palette-mode {per-frame|shared}
    Sposób doboru palety kolorów dla klatek (default: per-frame)
      per-frame → każda klatka ma własną, dobraną indywidualnie paletę (najlepsza
                  jakość koloru pojedynczej klatki, ale odtwarzacz musi przeładować
                  paletę na każdej klatce - może powodować zacinanie się animacji
                  przy dużych, pełnorozdzielczościowych zdjęciach)
      shared    → jedna wspólna paleta dla całego GIF-a, wyliczona z próbek
                  wszystkich klatek (mniejszy plik, płynniejsze odtwarzanie w
                  większości aplikacji, kosztem nieco gorszego doboru kolorów dla
                  pojedynczych bardzo różnokolorowych klatek)
    Jeśli GIF się "zacina" na niektórych klatkach mimo poprawnych czasów trwania,
    to zwykle wina przeładowywania palety per klatka - spróbuj --palette-mode shared.

--lossy <0-200>
    Stratna kompresja LZW przez zewnętrzne narzędzie gifsicle (default: 0 - wyłączona)
    NIE zmienia rozdzielczości ani liczby kolorów - działa na poziomie samego
    strumienia LZW, pozwalając na drobne, kontrolowane odchylenia pikseli między
    ramkami, żeby lepiej się kompresowały (dokładnie ta technika, o którą prosiłeś:
    zmniejsza rozmiar pliku bez zauważalnej zmiany wyglądu/rozdzielczości, w
    przeciwieństwie do --scale, który realnie zmniejsza obraz).
    Przykłady:
      --lossy 0    → wyłączone (domyślne, plik największy, zero utraty jakości)
      --lossy 30   → bardzo lekka kompresja, praktycznie niezauważalna
      --lossy 65   → dobry kompromis rozmiar/jakość (rekomendowane na start)
      --lossy 100  → zauważalny, ale akceptowalny szum na gradientach
      --lossy 200  → maksymalna kompresja gifsicle, widoczny dithering/szum
    Wymaga gifsicle - najprościej: pobierz .exe z eternallybored.org i wrzuć obok
    tego skryptu (bez instalacji systemowej, patrz sekcja INSTALACJA na górze pliku).
    Redukcja rozmiaru pliku rzędu 30-50% jest typowa przy --lossy 65-80.

================================================================================
UWAGI O JAKOŚCI
================================================================================

1. Format GIF ma TWARDY LIMIT 256 kolorów w palecie — to ograniczenie samego
   formatu GIF, nie dodatkowa kompresja. Skrypt nie robi żadnej dodatkowej
   kompresji ponad ten wymóg (optimize=False w Pillow).

2. Skalowanie obrazów (jeśli --canvas max): Uses LANCZOS resampling (najwyższa
   jakość dostępna w Pillow, lepsza niż BICUBIC czy bilinear).

3. Orientacja EXIF: Zdjęcia z telefonów (JPG, DNG) są automatycznie korygowane
   wg tagu EXIF orientation — bez tego byłyby obrócone.

4. PROBLEM Z NOWSZYMI DNG Z TELEFONÓW:
   Część telefonów (Samsung, Pixel) zapisuje DNG z kompresją (DNG 1.7 / JPEG-XL).
   LibRaw (silnik pod rawpy) tego nie obsługuje. Skrypt automatycznie wyciąga
   osadzony w pliku podgląd JPEG przez ExifTool (jedyny scenariusz, gdzie klatka
   ma kompresję stratną JPEG). O tym będzie wyraźny komunikat na końcu.

================================================================================
PRZYKŁADY UŻYCIA
================================================================================

Wolna, łatwa do śledzenia animacja:
    pipenv run python photo_to_gif.py --fps 5 --frames-per-photo 4 --loop 0

Szybka, jazzowa animacja:
    pipenv run python photo_to_gif.py --fps 20 --frames-per-photo 1 --loop 0

Pojedyncze odtworzenie (bez pętli), wysoka jakość ditheringu:
    pipenv run python photo_to_gif.py --loop 1 --dither floyd-steinberg --quantize median-cut

Alfabetycznie z fallbackiem pierwszego zdjęcia jako rozmiar:
    pipenv run python photo_to_gif.py --sort name --canvas first

Bez ditheringu (szybciej), z eksplicitnym wyjściem:
    pipenv run python photo_to_gif.py --dither none --output "C:\\Users\\Me\\anim.gif"

Mały plik do wysłania na Discord/WhatsApp (kompresja jakości, nie rozdzielczości):
    pipenv run python photo_to_gif.py --lossy 80

Naprawa zacinania się animacji bez utraty rozdzielczości (wspólna paleta):
    pipenv run python photo_to_gif.py --palette-mode shared

Maksymalna kompresja (najmniejszy plik, zauważalna utrata jakości):
    pipenv run python photo_to_gif.py --scale 40 --colors 64 --palette-mode shared --lossy 150

================================================================================
BŁĘDY I ROZWIĄZYWANIE
================================================================================

"rawpy nie potrafi zdekodować tego pliku"
    → To DNG z nowszą kompresją. Zainstaluj ExifTool. Skrypt użyje fallbacku JPEG.

"ExifTool (fallback) nie jest zainstalowany"
    → winget install --id OliverBetz.ExifTool -e
    → Po instalacji możesz potrzebować nowego okna PowerShell.

"nie znaleziono gifsicle"
    → Pobierz gifsicle.exe z https://eternallybored.org/misc/gifsicle/ i wrzuć go
      do tego samego folderu co skrypt (bez instalacji, bez zmiany PATH).
    → Skrypt zapisze GIF bez kompresji --lossy, jeśli gifsicle się nie znajdzie.

"Zdjęcia mają różne wymiary (...) a podano --require-same-size"
    → Usuń --require-same-size LUB użyj zdjęć o tym samym rozmiarze.

Obrazy są obrócone w GIF-ie
    → Skrypt koryguje EXIF orientation; jeśli problem nadal występuje, to niezwykłe.

================================================================================
"""

import argparse
import io
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from PIL import Image, ImageOps

try:
    import rawpy
    RAWPY_AVAILABLE = True
except ImportError:
    RAWPY_AVAILABLE = False

import tkinter as tk
from tkinter import filedialog

RAW_EXTENSIONS = {".dng", ".cr2", ".cr3", ".nef", ".arw", ".raf", ".orf", ".rw2"}

# --- Kompatybilność z różnymi wersjami Pillow (starsze/nowsze stałe) ---
RESAMPLE_LANCZOS = getattr(getattr(Image, "Resampling", Image), "LANCZOS")
DITHER_NONE = getattr(getattr(Image, "Dither", Image), "NONE")
DITHER_FS = getattr(getattr(Image, "Dither", Image), "FLOYDSTEINBERG")
QUANTIZE_MEDIANCUT = getattr(getattr(Image, "Quantize", Image), "MEDIANCUT")
QUANTIZE_FASTOCTREE = getattr(getattr(Image, "Quantize", Image), "FASTOCTREE")
QUANTIZE_LIBIMAGEQUANT = getattr(getattr(Image, "Quantize", Image), "LIBIMAGEQUANT", None)


def parse_args():
    parser = argparse.ArgumentParser(
        description="Tworzy animowany GIF z wybranych zdjęć (z obsługą DNG/RAW)."
    )
    parser.add_argument(
        "--fps", type=float, default=10.0,
        help="Bazowa liczba klatek na sekundę (czas trwania jednej klatki = 1000/fps ms). Domyślnie 10."
    )
    parser.add_argument(
        "--frames-per-photo", type=int, default=1,
        help="Ile razy powielić klatkę danego zdjęcia (wydłuża czas jego wyświetlania). Domyślnie 1."
    )
    parser.add_argument(
        "--loop", type=int, default=0,
        help="Liczba powtórzeń animacji. 0 = w nieskończoność. Domyślnie 0."
    )
    parser.add_argument(
        "--output", type=str, default=None,
        help="Ścieżka pliku wyjściowego .gif. Jeśli pominięte, pojawi się okno zapisu."
    )
    parser.add_argument(
        "--sort", choices=["selection", "name", "date"], default="selection",
        help="Kolejność klatek: 'selection' (kolejność wyboru w oknie), 'name' (alfabetycznie), "
             "'date' (wg daty modyfikacji pliku). Domyślnie 'selection'."
    )
    parser.add_argument(
        "--reverse", action="store_true",
        help="Odwraca kolejność klatek."
    )
    parser.add_argument(
        "--canvas", choices=["first", "max"], default="max",
        help="Rozmiar płótna: 'first' = rozmiar pierwszego zdjęcia, 'max' = największy wymiar "
             "spośród zdjęć (pozostałe dopasowywane bez przycinania, letterbox). Domyślnie 'max'."
    )
    parser.add_argument(
        "--require-same-size", action="store_true",
        help="Zamiast dopasowywać rozmiary, przerywa działanie, jeśli zdjęcia mają różne wymiary "
             "(pełna kontrola, zero skalowania)."
    )
    parser.add_argument(
        "--dither", choices=["none", "floyd-steinberg"], default="floyd-steinberg",
        help="Dithering przy konwersji do palety 256 kolorów. Domyślnie floyd-steinberg (lepsza jakość wizualna)."
    )
    parser.add_argument(
        "--quantize", choices=["median-cut", "fast-octree", "libimagequant"], default="median-cut",
        help="Metoda doboru palety 256 kolorów. 'libimagequant' daje najlepszą jakość, ale wymaga "
             "biblioteki libimagequant zainstalowanej w systemie. Domyślnie 'median-cut'."
    )
    parser.add_argument(
        "--scale", type=float, default=100.0,
        help="Procent oryginalnego rozmiaru zdjęć (kompresja przez zmniejszenie rozdzielczości). "
             "100 = brak zmian (pełna rozdzielczość, domyślne zachowanie). "
             "Np. --scale 50 zmniejsza wymiary o połowę (plik ~4x mniejszy, szybsze odtwarzanie)."
    )
    parser.add_argument(
        "--colors", type=int, default=256,
        help="Liczba kolorów w palecie GIF-a, od 2 do 256 (kompresja przez ograniczenie palety). "
             "256 = maksimum obsługiwane przez format GIF (domyślne, najlepsza jakość koloru). "
             "Mniejsze wartości (np. 64, 128) zmniejszają rozmiar pliku kosztem gradientów kolorów."
    )
    parser.add_argument(
        "--palette-mode", choices=["per-frame", "shared"], default="per-frame",
        help="'per-frame' = każda klatka ma własną, optymalną paletę (domyślne, najlepsza jakość "
             "koloru pojedynczej klatki, ale większy plik i możliwe zacinanie przy odtwarzaniu, bo "
             "odtwarzacz przeładowuje paletę na każdej klatce). 'shared' = jedna wspólna paleta dla "
             "całego GIF-a (mniejszy plik, płynniejsze odtwarzanie, kosztem lekko gorszego doboru "
             "kolorów dla pojedynczych, bardzo różnokolorowych klatek)."
    )
    parser.add_argument(
        "--lossy", type=int, default=0,
        help="Stratna kompresja LZW przez gifsicle, 0-200 (kompresja rozmiaru pliku BEZ zmiany "
             "rozdzielczości/liczby kolorów). 0 = wyłączona (domyślne). Typowe wartości: 30 (bardzo "
             "lekka, prawie niezauważalna), 65-80 (dobry kompromis), 150-200 (mocna, może być widoczny "
             "szum/dithering). Wymaga zainstalowanego gifsicle w PATH."
    )
    return parser.parse_args()


def select_photos() -> list[Path]:
    """Otwiera natywne okno wyboru plików Windows, zwraca ścieżki w kolejności zaznaczenia."""
    root = tk.Tk()
    root.withdraw()
    root.attributes("-topmost", True)

    filetypes = [
        ("Wszystkie obsługiwane zdjęcia",
         "*.jpg *.jpeg *.png *.bmp *.tif *.tiff *.webp *.dng *.cr2 *.cr3 *.nef *.arw *.raf *.orf *.rw2"),
        ("Zdjęcia standardowe", "*.jpg *.jpeg *.png *.bmp *.tif *.tiff *.webp"),
        ("Pliki RAW/DNG", "*.dng *.cr2 *.cr3 *.nef *.arw *.raf *.orf *.rw2"),
        ("Wszystkie pliki", "*.*"),
    ]

    paths = filedialog.askopenfilenames(
        title="Wybierz zdjęcia do GIF-a (kolejność zaznaczenia = kolejność klatek)",
        filetypes=filetypes,
    )
    root.destroy()

    if not paths:
        print("Nie wybrano żadnych zdjęć. Zakończono.")
        sys.exit(0)

    return [Path(p) for p in paths]


def select_output_path() -> Path:
    root = tk.Tk()
    root.withdraw()
    root.attributes("-topmost", True)

    path = filedialog.asksaveasfilename(
        title="Zapisz GIF jako...",
        defaultextension=".gif",
        filetypes=[("Plik GIF", "*.gif")],
    )
    root.destroy()

    if not path:
        print("Nie wybrano lokalizacji zapisu. Zakończono.")
        sys.exit(0)

    return Path(path)


def extract_embedded_preview(path: Path) -> Image.Image:
    """Fallback: wyciąga osadzony w pliku RAW/DNG podgląd JPEG przez ExifTool.
    Używane TYLKO gdy rawpy/LibRaw nie potrafi zdekodować danych RAW (typowe dla
    nowszych DNG z telefonów). To jedyne miejsce w skrypcie, gdzie do gifa trafiają
    dane skompresowane stratnie (JPEG) - bo alternatywą jest brak obrazu w ogóle."""
    exiftool_path = shutil.which("exiftool")
    if not exiftool_path:
        raise RuntimeError(
            "rawpy nie potrafi zdekodować tego pliku, a ExifTool (fallback) nie jest "
            "zainstalowany lub niedostępny w PATH.\n"
            "Zainstaluj: winget install --id OliverBetz.ExifTool -e\n"
            "(po instalacji może być potrzebne nowe okno PowerShell, żeby PATH się odświeżył)"
        )

    for tag in ("-JpgFromRaw", "-PreviewImage"):
        result = subprocess.run(
            [exiftool_path, "-b", tag, str(path)],
            capture_output=True,
        )
        if result.returncode == 0 and result.stdout:
            img = Image.open(io.BytesIO(result.stdout))
            img.load()
            return img

    raise RuntimeError(
        f"Nie znaleziono osadzonego podglądu JPEG w {path.name} (sprawdzono JpgFromRaw i PreviewImage)."
    )


def load_raw_as_image(path: Path) -> tuple[Image.Image, bool]:
    """Konwertuje plik RAW/DNG do obrazu PIL. output_bps=8, bo GIF i tak obsługuje max
    8-bit/256 kolorów - to ograniczenie formatu docelowego, nie dodatkowa kompresja RAW-a.
    Zwraca (obraz, czy_uzyto_fallbacku_jpeg)."""
    if not RAWPY_AVAILABLE:
        raise RuntimeError(
            f"Plik {path.name} jest w formacie RAW/DNG, ale biblioteka 'rawpy' nie jest zainstalowana.\n"
            f"Zainstaluj: pipenv install rawpy"
        )

    try:
        with rawpy.imread(str(path)) as raw:
            rgb = raw.postprocess(
                use_camera_wb=True,
                no_auto_bright=True,
                output_bps=8,
                demosaic_algorithm=rawpy.DemosaicAlgorithm.AHD,
            )
        return Image.fromarray(rgb), False
    except Exception as e:
        print(f"     [!] rawpy nie potrafi zdekodować danych RAW ({e}).")
        print(f"         Prawdopodobnie nowszy wariant kompresji DNG (typowe dla telefonów).")
        print(f"         Wyciągam osadzony podgląd JPEG przez ExifTool (fallback)...")
        return extract_embedded_preview(path), True


def load_image(path: Path) -> tuple[Image.Image, bool]:
    """Zwraca (obraz, czy_uzyto_fallbacku_jpeg). Koryguje orientację wg tagu EXIF
    (telefony zapisują piksele "surowo" + flagę obrotu; bez tego GIF wychodzi obrócony)."""
    ext = path.suffix.lower()
    if ext in RAW_EXTENSIONS:
        img, used_fallback = load_raw_as_image(path)
    else:
        img, used_fallback = Image.open(path), False
    img.load()
    img = ImageOps.exif_transpose(img)  # no-op jeśli obraz nie ma tagu orientacji
    if img.mode != "RGB":
        img = img.convert("RGB")
    return img, used_fallback


def sort_paths(paths: list[Path], mode: str) -> list[Path]:
    if mode == "name":
        return sorted(paths, key=lambda p: p.name.lower())
    if mode == "date":
        return sorted(paths, key=lambda p: p.stat().st_mtime)
    return paths  # "selection" - bez zmian


def find_gifsicle() -> str | None:
    """Szuka gifsicle w kolejności: 1) obok skryptu, 2) w podfolderze bin/ obok skryptu,
    3) w systemowym PATH. Dzięki temu wystarczy pobrać gifsicle.exe i wrzucić go obok
    skryptu - bez instalacji systemowej, uprawnień administratora czy zmiany PATH."""
    script_dir = Path(__file__).resolve().parent
    exe_name = "gifsicle.exe" if sys.platform == "win32" else "gifsicle"

    candidates = [
        script_dir / exe_name,
        script_dir / "bin" / exe_name,
    ]
    for candidate in candidates:
        if candidate.is_file():
            return str(candidate)

    return shutil.which("gifsicle")


def apply_gifsicle_lossy(gif_path: Path, lossy_level: int) -> None:
    """Kompresuje istniejący GIF przez gifsicle --lossy (stratna kompresja LZW, dopasowana
    do natury formatu GIF - nie zmienia rozdzielczości ani liczby kolorów, tylko pozwala
    kodowaniu LZW na drobne, niemal niewidoczne odchylenia pikseli, żeby lepiej kompresować)."""
    gifsicle_path = find_gifsicle()
    if not gifsicle_path:
        script_dir = Path(__file__).resolve().parent
        raise RuntimeError(
            "Podano --lossy, ale nie znaleziono gifsicle.\n"
            f"Najprostsze rozwiązanie (bez instalacji systemowej): pobierz gifsicle.exe z\n"
            f"https://eternallybored.org/misc/gifsicle/ (paczka win64) i wrzuć plik gifsicle.exe\n"
            f"bezpośrednio do folderu: {script_dir}\n"
            f"Alternatywnie: choco install gifsicle (jeśli masz Chocolatey)."
        )

    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_output = Path(tmp_dir) / "compressed.gif"
        result = subprocess.run(
            [gifsicle_path, "-O3", f"--lossy={lossy_level}", str(gif_path), "-o", str(tmp_output)],
            capture_output=True, text=True,
        )
        if result.returncode != 0:
            raise RuntimeError(f"gifsicle zwrócił błąd: {result.stderr}")
        shutil.move(str(tmp_output), str(gif_path))


def scale_image(img: Image.Image, percent: float) -> Image.Image:
    """Skaluje obraz o podany procent oryginalnego rozmiaru (kompresja przez rozdzielczość).
    Używa LANCZOS - najwyższej jakości resamplingu dostępnego w Pillow."""
    if percent >= 100:
        return img
    new_w = max(1, round(img.width * percent / 100))
    new_h = max(1, round(img.height * percent / 100))
    return img.resize((new_w, new_h), RESAMPLE_LANCZOS)


def build_shared_palette(images: list[Image.Image], colors: int, quantize_method) -> Image.Image:
    """Buduje jedną wspólną paletę kolorów na podstawie próbek ze wszystkich klatek.
    Używana w trybie --palette-mode shared, żeby cały GIF miał jedną Global Color Table
    zamiast osobnej palety per klatka (mniejszy plik, brak przeładowania palety podczas
    odtwarzania = płynniejsza animacja)."""
    thumb_size = (150, 150)
    strip = Image.new("RGB", (thumb_size[0] * len(images), thumb_size[1]))
    for i, im in enumerate(images):
        thumb = im.resize(thumb_size, RESAMPLE_LANCZOS)
        strip.paste(thumb, (i * thumb_size[0], 0))
    return strip.quantize(colors=colors, method=quantize_method)


def fit_to_canvas(img: Image.Image, canvas_size: tuple[int, int]) -> Image.Image:
    """Dopasowuje obraz do wspólnego płótna bez przycinania (letterbox), z zachowaniem
    proporcji, używając LANCZOS - najwyższej jakości metody resamplingu w Pillow."""
    if img.size == canvas_size:
        return img

    canvas_w, canvas_h = canvas_size
    img_ratio = img.width / img.height
    canvas_ratio = canvas_w / canvas_h

    if img_ratio > canvas_ratio:
        new_w, new_h = canvas_w, round(canvas_w / img_ratio)
    else:
        new_h, new_w = canvas_h, round(canvas_h * img_ratio)

    resized = img.resize((new_w, new_h), RESAMPLE_LANCZOS)
    canvas = Image.new("RGB", canvas_size, (0, 0, 0))
    canvas.paste(resized, ((canvas_w - new_w) // 2, (canvas_h - new_h) // 2))
    return canvas


def main():
    args = parse_args()

    if not (2 <= args.colors <= 256):
        print(f"--colors musi być w zakresie 2-256 (podano {args.colors}). Przerywam.")
        sys.exit(1)
    if args.scale <= 0:
        print(f"--scale musi być większe od 0 (podano {args.scale}). Przerywam.")
        sys.exit(1)

    print("Otwieram okno wyboru zdjęć...")
    paths = select_photos()
    paths = sort_paths(paths, args.sort)
    if args.reverse:
        paths = list(reversed(paths))

    print(f"Wybrano {len(paths)} zdjęć. Wczytywanie...")
    images = []
    fallback_files = []
    for p in paths:
        print(f"  -> {p.name}")
        try:
            img, used_fallback = load_image(p)
        except Exception as e:
            print(f"Błąd podczas wczytywania {p.name}: {e}")
            sys.exit(1)
        images.append(img)
        if used_fallback:
            fallback_files.append(p.name)

    if args.scale < 100:
        print(f"Skalowanie zdjęć do {args.scale}% oryginalnego rozmiaru...")
        images = [scale_image(im, args.scale) for im in images]

    sizes = {im.size for im in images}
    if args.require_same_size and len(sizes) > 1:
        print(f"Zdjęcia mają różne wymiary ({sizes}), a podano --require-same-size. Przerywam.")
        sys.exit(1)

    canvas_size = images[0].size if args.canvas == "first" else (
        max(im.width for im in images), max(im.height for im in images)
    )
    print(f"Rozmiar płótna GIF-a: {canvas_size[0]}x{canvas_size[1]}")

    fitted = [fit_to_canvas(im, canvas_size) for im in images]

    quantize_method = {
        "median-cut": QUANTIZE_MEDIANCUT,
        "fast-octree": QUANTIZE_FASTOCTREE,
        "libimagequant": QUANTIZE_LIBIMAGEQUANT,
    }[args.quantize]
    if quantize_method is None:
        print("libimagequant niedostępne w tej instalacji Pillow, używam median-cut.")
        quantize_method = QUANTIZE_MEDIANCUT

    dither = DITHER_FS if args.dither == "floyd-steinberg" else DITHER_NONE

    if args.palette_mode == "shared":
        print(f"Budowanie wspólnej palety ({args.colors} kolorów) dla wszystkich klatek...")
        shared_palette = build_shared_palette(fitted, args.colors, quantize_method)
        palette_frames = [
            im.quantize(colors=args.colors, palette=shared_palette, dither=dither) for im in fitted
        ]
    else:
        try:
            palette_frames = [
                im.quantize(colors=args.colors, method=quantize_method, dither=dither) for im in fitted
            ]
        except Exception as e:
            print(f"Kwantyzacja '{args.quantize}' nieudana ({e}), używam median-cut.")
            palette_frames = [
                im.quantize(colors=args.colors, method=QUANTIZE_MEDIANCUT, dither=dither) for im in fitted
            ]

    frames = []
    for f in palette_frames:
        frames.extend([f] * max(1, args.frames_per_photo))

    duration_ms = round(1000 / args.fps)
    # Przygotuj listę duration (jeden dla każdej klatki, zawsze taki sam)
    # To gwarantuje równomierne czasy wyświetlania w każdym GIF viewerze
    durations = [duration_ms] * len(frames)
    
    output_path = Path(args.output) if args.output else select_output_path()

    print(f"Zapisywanie GIF-a: {output_path} ({len(frames)} klatek, {duration_ms} ms/klatka)...")
    frames[0].save(
        output_path,
        save_all=True,
        append_images=frames[1:],
        duration=durations,
        loop=args.loop,
        optimize=True,   # bezstratne - tylko usuwa nieużywane kolory z palety, bez zmiany pikseli
        disposal=2,
    )

    if args.lossy > 0:
        size_before = output_path.stat().st_size
        print(f"Kompresja gifsicle --lossy={args.lossy}...")
        try:
            apply_gifsicle_lossy(output_path, args.lossy)
            size_after = output_path.stat().st_size
            reduction = 100 * (1 - size_after / size_before) if size_before else 0
            print(f"  {size_before / 1024:.0f} KB -> {size_after / 1024:.0f} KB ({reduction:.0f}% mniej)")
        except RuntimeError as e:
            print(f"  [!] Kompresja gifsicle nieudana: {e}")
            print(f"      GIF został zapisany bez dodatkowej kompresji (nadal poprawny plik).")

    print(f"Gotowe! Zapisano: {output_path.resolve()}")

    if fallback_files:
        print(
            f"\nUWAGA: {len(fallback_files)} plik(ów) wczytano przez fallback JPEG "
            f"(rawpy nie obsługiwał danych RAW), więc te klatki mają kompresję stratną:"
        )
        for name in fallback_files:
            print(f"  - {name}")


if __name__ == "__main__":
    main()