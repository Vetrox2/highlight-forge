# Photo to GIF Converter

A Python tool that converts a sequence of photos into animated GIF files with extensive customization options.

## Overview

**photo_to_gif.py** creates smooth, high-quality animated GIFs from your photo collection. It supports:
- Standard image formats: JPG, PNG, BMP, TIFF, WEBP
- Raw formats: DNG, CR2, CR3, NEF, ARW, RAF, ORF, RW2
- Flexible frame ordering (selection, alphabetical, by date)
- Advanced color quantization and dithering
- Lossless and lossy compression options
- EXIF orientation correction
- Automatic palette optimization

## Installation

```bash
# Install Python dependencies
pipenv install pillow numpy

# Optional: For RAW/DNG support
pipenv install rawpy

# Optional: For newest DNG files (phones)
winget install --id OliverBetz.ExifTool -e

# Optional: For lossy compression (--lossy flag)
# Download gifsicle.exe from https://eternallybored.org/misc/gifsicle/
# and place it in the same folder as photo_to_gif.py
```

## Quick Start

```bash
# Interactive mode (opens file picker)
pipenv run python photo_to_gif.py

# With specific parameters
pipenv run python photo_to_gif.py --fps 10 --frames-per-photo 2 --loop 0
```

## Usage Examples

**Slow, easy-to-follow animation:**
```bash
pipenv run python photo_to_gif.py --fps 5 --frames-per-photo 4
```

**Fast, energetic animation:**
```bash
pipenv run python photo_to_gif.py --fps 20 --frames-per-photo 1
```

**Single playback (no loop), high-quality dithering:**
```bash
pipenv run python photo_to_gif.py --loop 1 --dither floyd-steinberg
```

**Small file for Discord/WhatsApp (lossy compression):**
```bash
pipenv run python photo_to_gif.py --lossy 80
```

**Alphabetical order, custom output:**
```bash
pipenv run python photo_to_gif.py --sort name --output "C:\path\to\animation.gif"
```

## Parameters Reference

### Animation Timing
- `--fps <number>` (default: 10.0)
  - Animation speed in frames per second
  - Frame duration = 1000 / fps milliseconds
  
- `--frames-per-photo <number>` (default: 1)
  - How many times to repeat each photo
  - Higher values slow down the animation
  
- `--loop <number>` (default: 0)
  - Animation repetitions: 0 = infinite, 1 = play once, N = play N times

### File Selection & Ordering
- `--sort {selection|name|date}` (default: selection)
  - selection: order you selected files in dialog
  - name: alphabetically by filename
  - date: by file modification date
  
- `--reverse`
  - Reverse the frame order

### Canvas & Sizing
- `--canvas {first|max}` (default: max)
  - first: use first photo's dimensions (crops/shrinks larger photos)
  - max: use largest dimensions (smaller photos get letterbox with black background)
  
- `--require-same-size`
  - Abort if photos have different dimensions (useful for full control)
  
- `--scale <percent>` (default: 100.0)
  - Scale all photos by percentage (100 = no change)
  - Example: --scale 50 makes file ~4x smaller

### Color & Quality
- `--colors <2-256>` (default: 256)
  - Maximum colors in GIF palette
  - Lower values = smaller file, worse gradients
  
- `--dither {none|floyd-steinberg}` (default: floyd-steinberg)
  - none: faster, more visible color artifacts
  - floyd-steinberg: better visual quality
  
- `--quantize {median-cut|fast-octree|libimagequant}` (default: median-cut)
  - Color palette selection method
  - median-cut: fast, universal
  - fast-octree: good for synthetic images
  - libimagequant: best quality (requires system library)
  
- `--palette-mode {per-frame|shared}` (default: per-frame)
  - per-frame: optimal colors per frame (larger file)
  - shared: one palette for entire GIF (smaller, smoother playback)

### Compression
- `--lossy <0-200>` (default: 0)
  - Lossy LZW compression via gifsicle
  - 0: disabled (default)
  - 30: very light, imperceptible
  - 65-80: recommended balance
  - 150-200: strong compression, visible artifacts
  - **Does NOT change resolution or color count**

### I/O
- `--output <path>`
  - Save GIF to specific path
  - Default: interactive save dialog

## Technical Details

### Format Limitations
- **GIF hard limit: 256 colors** — this is a GIF format restriction, not additional compression
- Dithering algorithms approximate more colors within this palette
- All output is 8-bit RGB (per GIF spec)

### Image Processing Pipeline

1. **Loading**: RAW files decoded with rawpy (or JPEG fallback via ExifTool)
2. **EXIF Correction**: Orientation tags applied automatically
3. **Scaling**: LANCZOS resampling (highest quality in Pillow)
4. **Canvas Fitting**: Letterbox with black background if sizes differ
5. **Quantization**: Reduced to 256-color palette with selected method
6. **Dithering**: Floyd-Steinberg or none applied
7. **Encoding**: GIF with optimized palette
8. **Lossy Pass**: Optional gifsicle compression (LZW only)

### Performance Notes

- **Palette mode impact**: per-frame = larger file + potential playback stuttering on weak devices
- **Scale recommendation**: Use --scale 50 for ~4x file size reduction and smoother playback
- **Lossy sweet spot**: --lossy 65-80 typically reduces file by 30-50% without visible degradation
- **Processing time**: Dominated by RAW decoding and quantization (can take several seconds for many high-res photos)

### Fallback Behavior

- **RAW decode failure**: Automatically extracts embedded JPEG preview (requires ExifTool)
- **Missing gifsicle**: Skips lossy compression, saves normal GIF
- **Unavailable quantize method**: Falls back to median-cut

## Troubleshooting

**"rawpy cannot decode this file"**
- Install ExifTool; script will use JPEG preview fallback

**"ExifTool not found"**
- Run: `winget install --id OliverBetz.ExifTool -e`

**"gifsicle not found"**
- Download from https://eternallybored.org/misc/gifsicle/ and place .exe in script folder

**"Photos have different dimensions with --require-same-size"**
- Remove flag or ensure all photos are same resolution

**GIF stutters during playback despite correct duration**
- Try `--palette-mode shared` to reduce palette reloading
