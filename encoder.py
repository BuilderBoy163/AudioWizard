import numpy as np
import soundfile as sf
import os

FREQ0 = 18500  # Hz representing bit "0"
FREQ1 = 19500  # Hz representing bit "1"
AMPLITUDE = 0.01  # Watermark amplitude relative to audio

SUPPORTED_FORMATS = {".wav", ".flac", ".ogg", ".aiff", ".aif"}


def text_to_bits(text: str) -> str:
    """Convert a UTF-8 string to a binary bit string."""
    encoded = text.encode("utf-8")
    return "".join(format(byte, "08b") for byte in encoded)


def encode_audio(
    input_file: str,
    output_file: str,
    message: str,
    chunk_ms: int = 50,
) -> None:
    """
    Embed a hidden text message into an audio file using ultrasonic FSK modulation.

    Args:
        input_file:  Path to the source audio file.
        output_file: Path where the watermarked audio will be saved.
        message:     The text message to embed.
        chunk_ms:    Duration of each bit tone in milliseconds (default 50 ms).

    Raises:
        ValueError: If the message is empty or the audio file is too short.
        FileNotFoundError: If the input file does not exist.
        RuntimeError: On any encoding failure.
    """
    if not os.path.isfile(input_file):
        raise FileNotFoundError(f"Input file not found: {input_file}")

    if not message:
        raise ValueError("Message cannot be empty.")

    try:
        audio, sr = sf.read(input_file, always_2d=False)
    except Exception as exc:
        raise RuntimeError(f"Failed to read audio file: {exc}") from exc

    # Normalise to float32
    if audio.dtype != np.float32:
        audio = audio.astype(np.float32)

    stereo = audio.ndim == 2

    # Build bit stream: 32-bit length header + message payload
    message_bits = text_to_bits(message)
    length_bits = format(len(message_bits), "032b")
    all_bits = length_bits + message_bits

    chunk = int(sr * chunk_ms / 1000)
    required_samples = len(all_bits) * chunk

    if required_samples > len(audio):
        max_chars = (len(audio) // chunk - 32) // 8
        raise ValueError(
            f"Audio file is too short to embed this message. "
            f"Maximum ~{max_chars} characters for this file."
        )

    # Build the ultrasonic watermark signal
    watermark = np.zeros(len(audio), dtype=np.float32)
    for i, bit in enumerate(all_bits):
        freq = FREQ1 if bit == "1" else FREQ0
        start = i * chunk
        t = np.arange(chunk, dtype=np.float32) / sr
        # Apply a Hann window to reduce spectral leakage
        tone = np.sin(2 * np.pi * freq * t) * np.hanning(chunk).astype(np.float32)
        watermark[start : start + chunk] += tone

    # Mix watermark into audio
    if stereo:
        watermark_2ch = np.column_stack([watermark, watermark])
        watermarked = audio + watermark_2ch * AMPLITUDE
    else:
        watermarked = audio + watermark * AMPLITUDE

    # Clip to valid range to prevent distortion
    watermarked = np.clip(watermarked, -1.0, 1.0)

    # Ensure output file has a supported extension
    _, ext = os.path.splitext(output_file)
    if ext.lower() not in SUPPORTED_FORMATS:
        output_file += ".wav"

    try:
        sf.write(output_file, watermarked, sr)
    except Exception as exc:
        raise RuntimeError(f"Failed to write output file: {exc}") from exc