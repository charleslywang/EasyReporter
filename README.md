# EasyReporter


> EasyReporter is a portable Windows application for quantifying gene-editing efficiency from fluorescence images. It integrates Cellpose-based segmentation with fluorescence intensity profiling, delivers interactive multi-plot visualization (box/bar/scatter/heatmap), and outputs AI-generated analysis reports — all with zero external Python configuration. The UI and reports are available in both English and Chinese.

---

## 1. Overview

EasyReporter is a portable fluorescence-cell analysis suite that provides:

- Image upload/import (TIFF files, ZIP archives, local folders)
- Cellpose-based segmentation and fluorescence intensity quantification
- Multiple visualization types: cell distribution scatter, clustering scatter, simulated flow cytometry, grouped bar, grouped box, correlation heatmap and correlation scatter
- AI-powered experiment summaries, trend analysis, and recommendations (OpenAI-compatible services, with optional vision-model per-chart interpretation)
- HTML and A4 PDF report export
- A fully bundled Python 3.10 runtime — no additional installation required

---

## 2. System Requirements

- Operating System: Windows 10 or later
- Memory: ≥ 8 GB recommended (4 GB minimum)
- Disk Space: ≥ 5 GB available
- GPU (optional): For Cellpose GPU acceleration, ensure a compatible CUDA driver is installed

---

## 3. Package Contents

The `EasyReporter` root folder contains:

| Item | Description |
| --- | --- |
| `start.bat` | Launch script (double-click to start the app) |
| `streamlit_app.py` | Main Streamlit application |
| `Code/` | Core logic modules: Cellpose wrapper (`1.cellpose.py`), fluorescence analysis (`2.Fluorescent_Intensity.py`), chart scripts, AI helper, key manager, PDF renderer |
| `models/` | Bundled Cellpose pretrained models (`cyto_0` ~ `cyto_3`, `cyto3`) |
| `python_runtime/` | Portable Python 3.10 runtime with all dependencies |
| `assets/` | Icon and static resources |
| `.streamlit/` | Streamlit configuration (theme, upload size limit, etc.) |
| `requirements.txt` | Python dependency manifest |
| `config.ini` | Reserved configuration placeholder (currently unused) |
| `README.md` | This document |

> During runtime, the application stores project data inside `EasyReporter_Projects/`.

---

## 4. Quick Start

1. Copy the entire `EasyReporter` folder to the target machine.
2. Double-click `start.bat` and wait until the console shows `URL: http://localhost:8501`.
3. Open your browser and navigate to `http://localhost:8501`.
4. When finished, press `Ctrl + C` in the console to stop the service.

> The first launch may take 1–3 minutes while models and dependencies load.

---

## 5. Workflow Overview

### Step 1: Data Processing
- Upload TIFF files, a ZIP archive, or import from a local folder.
- Files are copied into the current project's `Data/`, then Cellpose performs segmentation (output to `Cellpose_output/Cell_Counts/`) and fluorescence quantification (output to `Cellpose_output/Fluorescence_Intensity/`).
- Input images should come in matched pairs, e.g. `sample_EGFP-1.tif` + `sample_mcherry-1.tif`. The default matching distance threshold is 15 pixels.

### Step 2: Chart Generation
- Choose from multiple visualization types, configure colors/sizes/metrics, and generate charts in real time.
- Charts are written under `Chart/`; correlation heatmaps and scatter plots go to `correlation/` and `correlation_scatter/` respectively.

### Step 3: Download Outputs
- Preview the generated charts and download them as ZIP archives, along with raw tables and export artifacts.

### Step 4: AI Insights
- Select an OpenAI-compatible provider (OpenAI / Kimi / DeepSeek) and a model, then generate a structured AI report.
- DeepSeek is pre-configured with a bundled encrypted key by default; you can switch providers and enter your own API key.
- Vision-capable models (e.g. `gpt-4o`, `deepseek-vl-7b-chat`) attach chart images for multimodal per-chart interpretation.
- Reports can be downloaded as HTML or A4 PDF.

---

## 6. Language Toggle

- Use the language switcher in the top-right corner of the interface to toggle between English and Chinese.
- All UI text, including the sidebar and status messages, switches accordingly. Text inside generated charts always stays in English to avoid font issues.

---

## 7. Directory & Data Layout

During operation, per-project data resides under `EasyReporter_Projects/<project_name>/`:

| Subfolder | Description |
| --- | --- |
| `Data/` | Uploaded/imported raw images (isolated per project) |
| `Cellpose_output/` | Cellpose results (`Cell_Counts/` and `Fluorescence_Intensity/`) |
| `Chart/` | Generated charts (`Cell_Distribution_Scatter_Plot`, `Cell_Clustering_Scatter_Plot`, `Simulated_Flow_Cytometry_Plot`, `Grouped_Bar_Plot`, `Grouped_Box_Plot`, ...) |
| `correlation/` | Correlation heatmap workspace (`data/` and `output/`) |
| `correlation_scatter/` | Correlation scatter workspace (`data/` and `output/`) |
| `logs/` | Processing logs |
| `report_cache/` | AI report cache |

Delete individual project folders to remove historical runs without affecting other data or models.

---

## 8. Repository vs. Portable Package

This repository contains the source code and configuration only. The following large or user-specific assets are listed in `.gitignore` and are **not** committed to Git:

- `python_runtime/` — bundled Python runtime (hundreds of MB)
- `models/` — Cellpose model files (~126 MB); prepare them locally after cloning
- `EasyReporter_Projects/` — user experiment data
- `__pycache__/`, `*.pyc` — Python caches

To run from source:

```bash
pip install -r requirements.txt
streamlit run streamlit_app.py
```

The portable release package ships with all of these assets pre-bundled.

---

## 9. Troubleshooting

1. **Application won't start**: Ensure `python_runtime\python.exe` exists and that `start.bat` sits next to `streamlit_app.py`.
2. **Port already in use**: The app defaults to port 8501; close other instances or edit the port arguments in `start.bat`.
3. **Cellpose errors**: Verify that `models/` is intact; switch to CPU mode or rerun if necessary.
4. **AI features unavailable**: Check network access and API key validity. Configure proxies at the OS level if required.
5. **PDF download fails**: The HTML report always works; PDF rendering needs system Edge/Chrome, with a ReportLab fallback.
6. **UI not responding**: Refresh the browser or stop (`Ctrl + C`) and relaunch the application.

---

## 10. Customization & Extensions

- All business logic resides in `Code/`. Extend chart types, processing steps, or AI prompts there.
- Restart via `start.bat` after making changes for them to take effect.

---

## 11. Support

- Contact the project maintainer or review inline code comments for additional help.
- Feedback and feature requests are welcome via issues or email.

---
