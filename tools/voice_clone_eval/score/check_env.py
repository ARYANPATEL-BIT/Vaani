"""Step 2 environment check: does torch see the GPU, and does ECAPA run?

Usage (from tools/voice_clone_eval/score):  uv run python check_env.py
Prints ASCII only. Exits non-zero if CUDA is not usable.
"""

import sys
import time

import speaker
import torch


def main() -> int:
    print("torch", torch.__version__, "| built for CUDA", torch.version.cuda)
    ok = torch.cuda.is_available()
    print("cuda.is_available():", ok)
    if not ok:
        return 1
    print(
        "GPU:",
        torch.cuda.get_device_name(0),
        "| compute capability",
        torch.cuda.get_device_capability(0),
    )
    # A tiny matmul proves kernels for this GPU actually exist in the wheel;
    # is_available() alone can be True on a build that lacks sm_120 kernels.
    x = torch.randn(1024, 1024, device="cuda")
    torch.cuda.synchronize()
    print("GPU matmul ok, checksum", round(float((x @ x).abs().mean()), 2))

    t0 = time.perf_counter()
    encoder = speaker.load_encoder("cpu")
    print(f"ECAPA loaded on CPU in {time.perf_counter() - t0:.1f} s")
    # Two seconds of noise: proves the forward pass runs; the score is meaningless.
    noise = torch.randn(2 * speaker.ECAPA_RATE) * 0.1
    t0 = time.perf_counter()
    emb = speaker.embed_wave(encoder, noise, speaker.ECAPA_RATE)
    print(
        f"ECAPA embedding: {tuple(emb.shape)} in {(time.perf_counter() - t0) * 1000:.0f} ms"
    )
    print("self-cosine (must be 1.0):", round(speaker.cosine(emb, emb), 4))
    return 0


if __name__ == "__main__":
    sys.exit(main())
