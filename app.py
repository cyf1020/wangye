from __future__ import annotations

import html
import io
import os
import re
import uuid
from pathlib import Path
from typing import Any

import requests
from flask import Flask, Response, jsonify, request, send_from_directory
from PIL import Image

try:
    import cairosvg  # type: ignore
except Exception:  # pragma: no cover - optional dependency
    cairosvg = None


BASE_DIR = Path(__file__).resolve().parent
app = Flask(__name__, static_folder=str(BASE_DIR), static_url_path="")


def extract_svg_from_unknown_payload(payload: Any) -> str | None:
    """Try to extract SVG markup from various API response shapes."""
    if isinstance(payload, str):
        match = re.search(r"(<svg[\s\S]*?</svg>)", payload, flags=re.IGNORECASE)
        return match.group(1) if match else None

    if isinstance(payload, dict):
        common_keys = [
            "svg",
            "svg_code",
            "result",
            "data",
            "content",
            "output",
            "vector",
        ]
        for key in common_keys:
            if key in payload:
                value = extract_svg_from_unknown_payload(payload[key])
                if value:
                    return value

    if isinstance(payload, list):
        for item in payload:
            value = extract_svg_from_unknown_payload(item)
            if value:
                return value

    return None


def call_external_text_api(
    endpoint: str,
    api_key: str | None,
    text: str,
    options: dict[str, Any],
) -> str | None:
    headers: dict[str, str] = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
        headers["x-api-key"] = api_key

    payload = {"text": text, "options": options}
    response = requests.post(endpoint, json=payload, headers=headers, timeout=45)
    response.raise_for_status()

    maybe_json = None
    try:
        maybe_json = response.json()
    except Exception:
        maybe_json = response.text

    return extract_svg_from_unknown_payload(maybe_json)


def call_external_image_api(
    endpoint: str,
    api_key: str | None,
    image_bytes: bytes,
    filename: str,
    options: dict[str, Any],
) -> str | None:
    headers: dict[str, str] = {}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
        headers["x-api-key"] = api_key

    files = {"file": (filename, image_bytes)}
    data = {"options": str(options)}
    response = requests.post(
        endpoint, headers=headers, files=files, data=data, timeout=90
    )
    response.raise_for_status()

    maybe_json = None
    try:
        maybe_json = response.json()
    except Exception:
        maybe_json = response.text

    return extract_svg_from_unknown_payload(maybe_json)


def local_text_to_svg(
    text: str,
    font_family: str,
    font_size: int,
    fill: str,
    stroke: str,
    stroke_width: float,
    preset: str,
) -> str:
    lines = [line for line in text.splitlines() if line.strip()] or [text]
    line_height = max(int(font_size * 1.35), 20)
    padding = max(int(font_size * 0.9), 16)
    width = int(max(len(line) for line in lines) * font_size * 0.65 + padding * 2)
    height = int(line_height * len(lines) + padding * 2)
    width = max(width, 240)
    height = max(height, 120)

    defs = ""
    fill_expr = fill
    extra_text_style = ""
    if preset == "outline":
        fill_expr = "none"
        stroke = fill
        stroke_width = max(stroke_width, 1.8)
    elif preset == "gradient":
        gradient_id = f"grad-{uuid.uuid4().hex[:8]}"
        defs = (
            "<defs>"
            f'<linearGradient id="{gradient_id}" x1="0%" y1="0%" x2="100%" y2="100%">'
            '<stop offset="0%" stop-color="#60a5fa"/>'
            '<stop offset="55%" stop-color="#8b5cf6"/>'
            '<stop offset="100%" stop-color="#ec4899"/>'
            "</linearGradient>"
            "</defs>"
        )
        fill_expr = f"url(#{gradient_id})"
        extra_text_style = ' style="filter: drop-shadow(0 2px 1px rgba(0,0,0,0.25));"'

    text_nodes = []
    for idx, line in enumerate(lines):
        y = padding + line_height * (idx + 0.85)
        safe_line = html.escape(line)
        text_nodes.append(
            (
                f'<text id="text-line-{idx}" x="{padding}" y="{y}" '
                f'font-family="{html.escape(font_family)}" font-size="{font_size}" '
                f'fill="{fill_expr}" stroke="{stroke}" stroke-width="{stroke_width}"'
                f'{extra_text_style}>{safe_line}</text>'
            )
        )

    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}">{defs}{"".join(text_nodes)}</svg>'
    )


def color_to_hex(color: tuple[int, int, int, int]) -> tuple[str, float]:
    r, g, b, a = color
    return f"#{r:02x}{g:02x}{b:02x}", round(a / 255, 4)


def local_image_to_svg(
    image_bytes: bytes,
    max_edge: int = 220,
    max_colors: int = 12,
) -> str:
    image = Image.open(io.BytesIO(image_bytes)).convert("RGBA")
    orig_w, orig_h = image.size
    if orig_w == 0 or orig_h == 0:
        raise ValueError("无效图片尺寸。")

    scale = max(orig_w, orig_h) / float(max_edge)
    if scale < 1:
        scale = 1
    down_w = max(1, int(orig_w / scale))
    down_h = max(1, int(orig_h / scale))

    resized = image.resize((down_w, down_h), Image.Resampling.LANCZOS)
    quantized = resized.convert("P", palette=Image.Palette.ADAPTIVE, colors=max_colors)
    rgba_img = quantized.convert("RGBA")
    pixels = rgba_img.load()

    x_step = orig_w / down_w
    y_step = orig_h / down_h
    rects: list[str] = []
    node_idx = 0

    for y in range(down_h):
        x = 0
        while x < down_w:
            color = pixels[x, y]
            if color[3] < 18:
                x += 1
                continue

            run_x = x + 1
            while run_x < down_w and pixels[run_x, y] == color:
                run_x += 1

            hex_color, opacity = color_to_hex(color)
            svg_x = round(x * x_step, 3)
            svg_y = round(y * y_step, 3)
            svg_w = round((run_x - x) * x_step, 3)
            svg_h = round(y_step, 3)

            opacity_attr = f' fill-opacity="{opacity}"' if opacity < 1 else ""
            rects.append(
                (
                    f'<rect id="layer-{node_idx}" x="{svg_x}" y="{svg_y}" '
                    f'width="{svg_w}" height="{svg_h}" fill="{hex_color}"{opacity_attr}/>'
                )
            )
            node_idx += 1
            x = run_x

    if not rects:
        rects = ['<rect id="layer-empty" x="0" y="0" width="1" height="1" fill="#000"/>']

    return (
        '<svg xmlns="http://www.w3.org/2000/svg" '
        f'width="{orig_w}" height="{orig_h}" viewBox="0 0 {orig_w} {orig_h}" '
        'shape-rendering="crispEdges">'
        + "".join(rects)
        + "</svg>"
    )


def optimize_svg(svg: str) -> str:
    # Light-weight optimization without changing semantics.
    optimized = svg.strip()
    optimized = re.sub(r"<!--[\s\S]*?-->", "", optimized)
    optimized = re.sub(r">\s+<", "><", optimized)
    optimized = re.sub(r"\s{2,}", " ", optimized)
    optimized = re.sub(r"\s+/>", "/>", optimized)
    return optimized.strip()


@app.get("/api/health")
def health() -> Response:
    return jsonify({"status": "ok"})


@app.post("/api/text-to-svg")
def text_to_svg_api() -> Response:
    data = request.get_json(silent=True) or {}
    text = str(data.get("text", "")).strip()
    if not text:
        return jsonify({"error": "请输入要转换的文本。"}), 400

    font_family = str(data.get("fontFamily", "Inter"))
    font_size = int(data.get("fontSize", 64))
    fill = str(data.get("fill", "#111827"))
    stroke = str(data.get("stroke", "none"))
    stroke_width = float(data.get("strokeWidth", 0))
    preset = str(data.get("preset", "flat"))

    endpoint = str(data.get("apiEndpoint", "")).strip()
    api_key = str(data.get("apiKey", "")).strip() or None

    try:
        if endpoint:
            external_svg = call_external_text_api(
                endpoint=endpoint,
                api_key=api_key,
                text=text,
                options=data,
            )
            if external_svg:
                return jsonify({"svg": external_svg, "source": "external"})

        local_svg = local_text_to_svg(
            text=text,
            font_family=font_family,
            font_size=font_size,
            fill=fill,
            stroke=stroke,
            stroke_width=stroke_width,
            preset=preset,
        )
        return jsonify({"svg": local_svg, "source": "local"})
    except Exception as exc:
        return jsonify({"error": f"文本转SVG失败: {exc}"}), 500


@app.post("/api/image-to-svg")
def image_to_svg_api() -> Response:
    uploaded = request.files.get("file")
    if not uploaded:
        return jsonify({"error": "请上传图片文件。"}), 400

    image_bytes = uploaded.read()
    endpoint = (request.form.get("apiEndpoint") or "").strip()
    api_key = (request.form.get("apiKey") or "").strip() or None
    max_edge = int(request.form.get("maxEdge", 220))
    max_colors = int(request.form.get("maxColors", 12))

    try:
        if endpoint:
            external_svg = call_external_image_api(
                endpoint=endpoint,
                api_key=api_key,
                image_bytes=image_bytes,
                filename=uploaded.filename or "image.png",
                options={
                    "maxEdge": max_edge,
                    "maxColors": max_colors,
                },
            )
            if external_svg:
                return jsonify({"svg": external_svg, "source": "external"})

        local_svg = local_image_to_svg(
            image_bytes=image_bytes, max_edge=max_edge, max_colors=max_colors
        )
        return jsonify({"svg": local_svg, "source": "local"})
    except Exception as exc:
        return jsonify({"error": f"图片转SVG失败: {exc}"}), 500


@app.post("/api/optimize-svg")
def optimize_svg_api() -> Response:
    data = request.get_json(silent=True) or {}
    svg = str(data.get("svg", "")).strip()
    if not svg:
        return jsonify({"error": "SVG 代码为空。"}), 400
    return jsonify({"svg": optimize_svg(svg)})


@app.post("/api/export")
def export_api() -> Response:
    data = request.get_json(silent=True) or {}
    svg = str(data.get("svg", "")).strip()
    fmt = str(data.get("format", "png")).lower().strip()
    if not svg:
        return jsonify({"error": "SVG 代码为空。"}), 400

    if cairosvg is None:
        return (
            jsonify(
                {
                    "error": "导出功能依赖 cairosvg，请先安装 requirements.txt 依赖。",
                    "format": fmt,
                }
            ),
            501,
        )

    try:
        output: bytes
        mimetype: str
        filename: str
        if fmt == "png":
            output = cairosvg.svg2png(bytestring=svg.encode("utf-8"))
            mimetype = "image/png"
            filename = "export.png"
        elif fmt == "pdf":
            output = cairosvg.svg2pdf(bytestring=svg.encode("utf-8"))
            mimetype = "application/pdf"
            filename = "export.pdf"
        elif fmt == "eps":
            output = cairosvg.svg2ps(bytestring=svg.encode("utf-8"))
            mimetype = "application/postscript"
            filename = "export.eps"
        else:
            return jsonify({"error": f"不支持的导出格式: {fmt}"}), 400

        return Response(
            output,
            mimetype=mimetype,
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )
    except Exception as exc:
        return jsonify({"error": f"导出失败: {exc}"}), 500


@app.get("/")
def root() -> Response:
    return send_from_directory(BASE_DIR, "index.html")


@app.get("/<path:path>")
def static_files(path: str) -> Response:
    full_path = BASE_DIR / path
    if full_path.exists() and full_path.is_file():
        return send_from_directory(BASE_DIR, path)
    return send_from_directory(BASE_DIR, "index.html")


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8000"))
    app.run(host="0.0.0.0", port=port, debug=True)
