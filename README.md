# SVG Studio Pro

基于 **Python + HTML/CSS/JavaScript** 的 SVG 生成与编辑网站，支持：

- 文字转 SVG（字体、字号、填充、描边、样式预设）
- 图片转 SVG（PNG/JPG/WebP，拖拽上传）
- SVG 代码实时编辑（Monaco Editor）
- 画布实时预览（缩放 / 平移 / 背景切换）
- 双向同步（代码改动 -> 预览更新；点击元素 -> 定位代码）
- 图层管理、填充描边编辑、优化代码
- 导入 SVG / 保存 SVG / 复制代码 / 导出 PNG/PDF/EPS
- API 配置（自定义 Endpoint + API Key，失败自动回退本地引擎）
- 自动保存、历史记录、分享链接、暗黑模式、响应式布局

---

## 运行方式

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python app.py
```

默认地址：`http://127.0.0.1:8000`

---

## API 概览

- `POST /api/text-to-svg`
- `POST /api/image-to-svg`
- `POST /api/optimize-svg`
- `POST /api/export`
- `GET /api/health`

---

## 技术栈

- 后端：Flask（Python）
- 前端：HTML + TailwindCSS + JavaScript（React UMD）
- 编辑器：Monaco Editor
- SVG 导出：CairoSVG
