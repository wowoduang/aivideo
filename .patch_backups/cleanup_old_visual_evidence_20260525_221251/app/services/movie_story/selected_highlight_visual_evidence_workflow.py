# -*- coding: utf-8 -*-
from __future__ import annotations

"""
selected_highlight_visual_evidence_workflow.py

What this module is:
- Production workflow for selected-highlight factual visual evidence.

Why it exists:
- movie_story keeps the "highlight" product concept, but backend should not
  overfit to proving that automatic highlights are always correct.
- Candidate/highlight selection happens elsewhere. This module only enriches
  already selected highlights with factual frame evidence for review, VLM, and
  the two-round narration chain.
- Frontend/manual review can later remove automatic highlights or add unselected
  candidates; once the final selected_highlights list exists, this workflow can
  run again on that selected list.

Input:
- video_path
- output_script_path pointing to movie_story_script.json
- sibling files:
  - movie_story_script_highlights.json
  - movie_story_script_highlight_narration_segments.json

Output:
- movie_story_script_selected_highlight_keyframes.json
- movie_story_script_selected_highlight_visual_evidence.json
- movie_story_script_two_round_input_packages.json
- optional movie_story_script_selected_highlight_contact_sheet.jpg
- optional movie_story_script_selected_highlight_contact_sheet_index.json

Producer:
- local movie_story_script job after native/legacy script generation.

Consumer:
- frontend highight review UI
- optional VLM relation checker
- two_round_narration_chain

Formality:
- FORMAL FACT-EVIDENCE BUILDER FOR SELECTED HIGHLIGHTS.

NOT FOR:
- selecting highlights
- ranking highlights
- changing highlight boundaries
- generating narration
- binding character names
- inferring character psychology
- replacing VLM interpretation

Failure policy:
- Missing files, misaligned highlight_id, unreadable video, failed frame
  extraction, or missing contact-sheet dependency raises. Do not silently skip.
"""

import json
from pathlib import Path
from typing import Any, Mapping, Sequence


__all__ = [
    "build_selected_highlight_visual_evidence_package",
    "derive_selected_highlight_visual_evidence_paths",
]


def build_selected_highlight_visual_evidence_package(
    *,
    video_path: str | Path,
    output_script_path: str | Path,
    max_frames_per_highlight: int = 6,
    write_contact_sheet: bool = True,
) -> dict[str, Any]:
    """Build selected-highlight visual evidence outputs next to script JSON.

    Input:
    - video_path: source video used by movie_story_script.
    - output_script_path: movie_story_script.json path.
    - max_frames_per_highlight: selected-highlight detail frame cap.
    - write_contact_sheet: whether to generate the review image.

    Output:
    - Result dict with generated file paths and counts.

    NOT FOR:
    - candidate-stage cheap fact frames.
    - automatic/manual highlight selection.
    - VLM calls.
    """
    source_video = Path(video_path)
    script_path = Path(output_script_path)

    if not source_video.exists():
        raise FileNotFoundError(f"video_path does not exist: {source_video}")
    if not script_path.exists():
        raise FileNotFoundError(f"output_script_path does not exist: {script_path}")
    if max_frames_per_highlight <= 0:
        raise ValueError("max_frames_per_highlight must be positive")

    paths = derive_selected_highlight_visual_evidence_paths(script_path)

    highlights = _load_json_list(paths["highlights"], "selected highlights")
    narration_segments = _load_json_list(paths["narration_segments"], "highlight narration segments")
    _assert_highlight_alignment(highlights, narration_segments)

    from app.services.movie_story.visual_frame_sampler import sample_keyframes_for_selected_highlights
    from app.services.movie_story.visual_highlight_evidence import build_visual_evidence_by_highlight
    from app.services.movie_story.two_round_input_packager import build_two_round_input_packages

    keyframes = sample_keyframes_for_selected_highlights(
        video_path=source_video,
        selected_highlights=highlights,
        output_dir=paths["frame_dir"],
        max_frames_per_highlight=max_frames_per_highlight,
    )
    visual_evidence = build_visual_evidence_by_highlight(
        highlights,
        keyframes,
        highlight_narration_segments=narration_segments,
    )
    two_round_packages = build_two_round_input_packages(
        selected_highlights=highlights,
        highlight_narration_segments=narration_segments,
        visual_evidence_by_highlight=visual_evidence,
    )

    _write_json(paths["keyframes"], keyframes)
    _write_json(paths["visual_evidence"], visual_evidence)
    _write_json(paths["two_round_packages"], two_round_packages)

    contact_sheet_path = ""
    contact_sheet_index_path = ""
    if write_contact_sheet:
        contact = write_selected_highlight_contact_sheet(
            keyframes=keyframes,
            contact_sheet_path=paths["contact_sheet"],
            index_path=paths["contact_sheet_index"],
        )
        contact_sheet_path = contact["contact_sheet_path"]
        contact_sheet_index_path = contact["contact_sheet_index_path"]

    return {
        "selected_highlight_keyframes_path": str(paths["keyframes"]),
        "selected_highlight_visual_evidence_path": str(paths["visual_evidence"]),
        "two_round_input_packages_path": str(paths["two_round_packages"]),
        "selected_highlight_contact_sheet_path": contact_sheet_path,
        "selected_highlight_contact_sheet_index_path": contact_sheet_index_path,
        "selected_highlight_keyframes_count": len(keyframes),
        "selected_highlight_visual_evidence_count": len(visual_evidence),
        "two_round_input_package_count": len(two_round_packages),
    }


def derive_selected_highlight_visual_evidence_paths(output_script_path: str | Path) -> dict[str, Path]:
    """Derive all selected-highlight evidence paths from movie_story_script.json.

    This function centralizes naming so local job, tests, and future frontend
    consumers do not invent parallel path conventions.
    """
    script_path = Path(output_script_path)
    return {
        "highlights": Path(str(script_path).replace(".json", "_highlights.json")),
        "narration_segments": Path(str(script_path).replace(".json", "_highlight_narration_segments.json")),
        "keyframes": Path(str(script_path).replace(".json", "_selected_highlight_keyframes.json")),
        "visual_evidence": Path(str(script_path).replace(".json", "_selected_highlight_visual_evidence.json")),
        "two_round_packages": Path(str(script_path).replace(".json", "_two_round_input_packages.json")),
        "frame_dir": script_path.with_name(f"{script_path.stem}_visual_frames") / "selected_highlight_detail",
        "contact_sheet": Path(str(script_path).replace(".json", "_selected_highlight_contact_sheet.jpg")),
        "contact_sheet_index": Path(str(script_path).replace(".json", "_selected_highlight_contact_sheet_index.json")),
    }


def write_selected_highlight_contact_sheet(
    *,
    keyframes: Sequence[Mapping[str, Any]],
    contact_sheet_path: str | Path,
    index_path: str | Path,
    thumb_width: int = 320,
    thumb_height: int = 180,
) -> dict[str, Any]:
    """Write a review contact sheet for sampled selected-highlight frames.

    What this function does:
    - Creates a human-review artifact from already sampled frames.
    - It does not create new evidence and does not call any model.

    NOT FOR:
    - production visual interpretation.
    - scoring highlights.
    - modifying frame records.
    """
    try:
        from PIL import Image, ImageDraw, ImageFont
    except Exception as exc:
        raise RuntimeError("Pillow is required for selected-highlight contact sheet generation") from exc

    if not keyframes:
        raise ValueError("keyframes must not be empty")
    if thumb_width <= 0 or thumb_height <= 0:
        raise ValueError("thumb dimensions must be positive")

    grouped: dict[str, list[Mapping[str, Any]]] = {}
    for frame in keyframes:
        highlight_id = _required_str(frame, "highlight_id", "keyframe")
        grouped.setdefault(highlight_id, []).append(frame)
    for frames in grouped.values():
        frames.sort(key=lambda item: float(item.get("timestamp") or 0.0))

    label_h = 44
    row_gap = 16
    col_gap = 12
    margin = 16
    max_cols = max(len(items) for items in grouped.values())
    row_w = margin * 2 + max_cols * thumb_width + (max_cols - 1) * col_gap
    row_h = label_h + thumb_height
    sheet_h = margin * 2 + len(grouped) * row_h + (len(grouped) - 1) * row_gap

    sheet = Image.new("RGB", (row_w, sheet_h), "white")
    draw = ImageDraw.Draw(sheet)
    font = ImageFont.load_default()

    index_records: list[dict[str, Any]] = []
    y = margin
    for highlight_id, frames in sorted(grouped.items()):
        start_y = y
        draw.text((margin, y), f"{highlight_id} | frames={len(frames)}", fill="black", font=font)
        y += label_h

        x = margin
        for order, frame in enumerate(frames, start=1):
            frame_path = Path(_required_str(frame, "frame_path", f"{highlight_id} frame"))
            if not frame_path.exists():
                raise FileNotFoundError(frame_path)
            timestamp = float(frame.get("timestamp") or 0.0)

            with Image.open(frame_path) as img:
                img = img.convert("RGB")
                img.thumbnail((thumb_width, thumb_height))
                tile = Image.new("RGB", (thumb_width, thumb_height), "white")
                paste_x = (thumb_width - img.width) // 2
                paste_y = (thumb_height - img.height) // 2
                tile.paste(img, (paste_x, paste_y))
                sheet.paste(tile, (x, y))

            draw.text((x + 4, y + 4), f"{order} | {timestamp:.3f}s", fill="black", font=font)
            index_records.append(
                {
                    "highlight_id": highlight_id,
                    "order": order,
                    "timestamp": timestamp,
                    "frame_path": str(frame_path),
                    "sheet_box": [x, y, x + thumb_width, y + thumb_height],
                }
            )
            x += thumb_width + col_gap

        y = start_y + row_h + row_gap

    contact_path = Path(contact_sheet_path)
    index_output_path = Path(index_path)
    contact_path.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(contact_path, quality=92)
    _write_json(index_output_path, index_records)

    return {
        "contact_sheet_path": str(contact_path),
        "contact_sheet_index_path": str(index_output_path),
        "contact_sheet_highlight_count": len(grouped),
        "contact_sheet_frame_count": len(keyframes),
    }


def _load_json_list(path: Path, label: str) -> list[dict[str, Any]]:
    if not path.exists():
        raise FileNotFoundError(f"missing {label}: {path}")
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise TypeError(f"{label} must be a JSON list: {path}")
    if not data:
        raise ValueError(f"{label} must not be empty: {path}")
    for index, item in enumerate(data):
        if not isinstance(item, dict):
            raise TypeError(f"{label}[{index}] must be a JSON object")
    return data


def _assert_highlight_alignment(
    highlights: Sequence[Mapping[str, Any]],
    narration_segments: Sequence[Mapping[str, Any]],
) -> None:
    highlight_ids = [_required_str(dict(item), "highlight_id", f"highlights[{idx}]") for idx, item in enumerate(highlights)]
    narration_ids = [
        _required_str(dict(item), "highlight_id", f"narration_segments[{idx}]")
        for idx, item in enumerate(narration_segments)
    ]

    duplicate_highlights = sorted({value for value in highlight_ids if highlight_ids.count(value) > 1})
    duplicate_narration = sorted({value for value in narration_ids if narration_ids.count(value) > 1})
    if duplicate_highlights:
        raise RuntimeError(f"duplicate highlight ids in highlights: {duplicate_highlights}")
    if duplicate_narration:
        raise RuntimeError(f"duplicate highlight ids in narration_segments: {duplicate_narration}")

    missing_narration = sorted(set(highlight_ids) - set(narration_ids))
    extra_narration = sorted(set(narration_ids) - set(highlight_ids))
    if missing_narration or extra_narration:
        raise RuntimeError(
            "highlight/narration alignment mismatch: "
            f"missing_narration={missing_narration}, extra_narration={extra_narration}"
        )

    for idx, item in enumerate(highlights):
        item_dict = dict(item)
        start = _required_float(item_dict, "start", f"highlights[{idx}]")
        end = _required_float(item_dict, "end", f"highlights[{idx}]")
        if end <= start:
            raise ValueError(f"invalid highlight time range at highlights[{idx}]")


def _required_str(item: Mapping[str, Any], key: str, label: str) -> str:
    value = str(item.get(key) or "").strip()
    if not value:
        raise KeyError(f"{label} missing required string key: {key}")
    return value


def _required_float(item: Mapping[str, Any], key: str, label: str) -> float:
    if key not in item:
        raise KeyError(f"{label} missing required numeric key: {key}")
    value = item[key]
    if value in (None, ""):
        raise ValueError(f"{label} empty numeric key: {key}")
    return float(value)


def _write_json(path: str | Path, data: Any) -> None:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
        newline="\n",
    )
