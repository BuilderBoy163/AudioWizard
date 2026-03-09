import numpy as np
import soundfile as sf
from scipy.fft import rfft, rfftfreq
import os

FREQ0 = 18500  # Hz representing bit "0"
FREQ1 = 19500  # Hz representing bit "1"
MAX_MESSAGE_BITS = 1_000_000  # Safety cap: ~125 KB of text


def decode_audio(input_file: str, chunk_ms: int = 50) -> str:
    """
    Extract a hidden text message from a watermarked audio file.

    Args:
        input_file: Path to the watermarked audio file.
        chunk_ms:   Bit-chunk duration in milliseconds — must match the value
                    used during encoding (default 50 ms).

    Returns:
        The decoded message string.

    Raises:
        FileNotFoundError: If the input file does not exist.
        ValueError: If no valid watermark is detected or the data is corrupt.
        RuntimeError: On any decoding failure.
    """
    if not os.path.isfile(input_file):
        raise FileNotFoundError(f"File not found: {input_file}")

    try:
        audio, sr = sf.read(input_file, always_2d=False)
    except Exception as exc:
        raise RuntimeError(f"Failed to read audio file: {exc}") from exc

    chunk = int(sr * chunk_ms / 1000)
    if chunk == 0:
        raise ValueError("chunk_ms is too small for the audio sample rate.")

    # Convert to mono float32 for analysis
    if audio.ndim == 2:
        audio = audio.mean(axis=1)
    audio = audio.astype(np.float32)

    # Pre-compute FFT frequency bins for our two target frequencies
    freqs = rfftfreq(chunk, d=1.0 / sr)
    idx0 = int(np.argmin(np.abs(freqs - FREQ0)))
    idx1 = int(np.argmin(np.abs(freqs - FREQ1)))

    num_chunks = len(audio) // chunk

    if num_chunks < 32:
        raise ValueError(
            "Audio file is too short to contain a valid watermark header."
        )

    # --- Decode the 32-bit length header ---
    header_bits = []
    for i in range(32):
        segment = audio[i * chunk : (i + 1) * chunk]
        spectrum = np.abs(rfft(segment * np.hanning(chunk).astype(np.float32)))
        header_bits.append("1" if spectrum[idx1] > spectrum[idx0] else "0")

    try:
        message_length = int("".join(header_bits), 2)
    except ValueError:
        raise ValueError("Failed to decode watermark header — file may not be watermarked.")

    if message_length <= 0 or message_length > MAX_MESSAGE_BITS:
        raise ValueError(
            f"Invalid message length ({message_length} bits) — "
            "file may not be watermarked or the chunk size is wrong."
        )

    required_chunks = 32 + message_length
    if required_chunks > num_chunks:
        raise ValueError(
            "Audio file is too short to contain the full watermarked message."
        )

    # --- Decode message bits ---
    message_bits = []
    for i in range(32, 32 + message_length):
        segment = audio[i * chunk : (i + 1) * chunk]
        spectrum = np.abs(rfft(segment * np.hanning(chunk).astype(np.float32)))
        message_bits.append("1" if spectrum[idx1] > spectrum[idx0] else "0")

    # --- Convert bit groups back to UTF-8 bytes ---
    if len(message_bits) % 8 != 0:
        raise ValueError("Decoded bit count is not a multiple of 8 — data may be corrupt.")

    byte_values = []
    for i in range(0, len(message_bits), 8):
        byte_group = "".join(message_bits[i : i + 8])
        byte_values.append(int(byte_group, 2))

    try:
        message = bytes(byte_values).decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError(
            f"Decoded bytes are not valid UTF-8 text — "
            f"file may not be watermarked or chunk_ms mismatch. ({exc})"
        ) from exc

    return message