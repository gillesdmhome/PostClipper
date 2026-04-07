from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PlatformPreset:
    platform: str
    target_min: float
    target_max: float
    hard_max: float
    max_candidates: int
    width: int = 1080
    height: int = 1920
    letterbox_bottom_px: int = 260


PRESETS: dict[str, PlatformPreset] = {
    # Defaults tuned for short-form; hard_max is the absolute cap we will not exceed.
    "tiktok": PlatformPreset("tiktok", target_min=18.0, target_max=55.0, hard_max=60.0, max_candidates=6),
    "youtube_shorts": PlatformPreset(
        "youtube_shorts", target_min=18.0, target_max=55.0, hard_max=60.0, max_candidates=6
    ),
    "instagram_reels": PlatformPreset(
        "instagram_reels", target_min=18.0, target_max=70.0, hard_max=90.0, max_candidates=6
    ),
    # X supports many shapes; we still generate a 9:16 short-form candidate set.
    "x": PlatformPreset("x", target_min=18.0, target_max=70.0, hard_max=140.0, max_candidates=4),
}


def default_platforms() -> list[str]:
    return ["tiktok", "youtube_shorts", "instagram_reels", "x"]

