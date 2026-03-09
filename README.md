# AudioWizard — Copyright Encoder

**Invisibly embed and extract copyright notices in audio files.**

AudioWizard uses ultrasonic Frequency-Shift Keying (FSK) watermarking to hide text messages inside any audio file. The watermark is completely inaudible — sitting at 18,500–19,500 Hz, above the range of human hearing — and survives standard audio operations like trimming and volume adjustment.

---

## Download

Pre-built binaries are available for every platform. Download the latest version from the [Releases tab] on GitHub.

| Platform | File |
|---|---|
| macOS | `AudioWizard-macOS.zip` → extract and run `AudioWizard.app` |
| Windows | `AudioWizard-Windows.zip` → run `AudioWizard.exe` |
| Debian / Ubuntu | `AudioWizard-Linux-Debian-Ubuntu.tar.gz` |
| Arch Linux | `AudioWizard-Linux-Arch.tar.gz` |

> **macOS note:** If you see a warning that the app can't be checked for malware, right-click the app → **Open** → **Open** anyway. Or run in Terminal:
> ```bash
> xattr -dr com.apple.quarantine ~/path/to/AudioWizard.app
> ```

---

## Running from Source

**Requirements:** Python 3.10+

```bash
# Clone the repo
git clone https://github.com/YOUR_USERNAME/AudioWizard.git
cd AudioWizard

# Install dependencies
pip install -r requirements.txt
# If that fails, run the following:
pip install cffi numpy pycparser PySide6 PySide6_Addons PySide6_Essentials scipy shiboken6 soundfile

# Run
python main.py
```

---

## How to Use

### Encoding a Watermark
1. Open the **Encode** tab from the sidebar
2. Click **Browse** and select a source audio file (WAV, FLAC, OGG, or AIFF)
3. Type your copyright notice or hidden message in the text box
4. Click **Export Watermarked Audio** and choose where to save it

### Decoding a Watermark
1. Open the **Decode** tab from the sidebar
2. Click **Browse** and select a watermarked audio file
3. Click **Decode Watermark** — the hidden message will appear
4. Click **Copy to Clipboard** to copy the result

---

## Settings

Open settings with the gear icon in the top right.

| Setting | Description |
|---|---|
| **Theme** | Choose from Dark, Light, Midnight, Ocean, or Rose |
| **Bit Duration** | Duration of each encoded bit tone in ms. Must match on both encode and decode. Default: 50 ms |
| **Default Output Format** | Preferred format for exported audio. WAV is lossless and recommended |
| **Custom Placeholder Message** | Set a custom hint message shown in the encode text box |

---

## How It Works

AudioWizard encodes text as a binary bit stream and embeds it into the host audio file using two ultrasonic sine tones:

- **18,500 Hz** = bit `0`
- **19,500 Hz** = bit `1`

Each bit is encoded as a short tone chunk (default 50 ms), windowed with a Hann function to reduce spectral leakage. A 32-bit length header is prepended to the payload so the decoder knows exactly how many bits to read back.

The watermark is mixed into the audio at 1% amplitude — inaudible to humans but detectable by FFT analysis.

**Supported formats:** WAV, FLAC, OGG, AIFF  
**Encoding:** UTF-8 (supports all Unicode characters including emoji)  
**Lossy formats:** MP3 and low-bitrate OGG may degrade or destroy the watermark due to frequency compression above 16 kHz

---

## Building from Source

Builds for all platforms are handled automatically by GitHub Actions on every push. See `.github/workflows/build.yml` for the full pipeline.

To build manually:
```bash
pip install pyinstaller
pyinstaller --noconfirm --windowed --name "AudioWizard" --add-data "icons:icons" main.py
```

---

## License

All rights reserved. This software and its source code are the property of the author.
