# EasyReporter

> EasyReporter is a portable fluorescence cell-analysis app for Windows. It lets you load TIFF images, ZIP archives, or folders, runs Cellpose to segment cells and measure fluorescence, offers interactive charts (box, bar, scatter, heatmap), and generates AI summaries—all without extra Python setup.

---

## 1. Overview

EasyReporter is a portable fluorescence-cell analysis suite that provides:

- Image upload/import (TIFF files, ZIP archives, local folders)
- Cellpose-based segmentation and fluorescence intensity quantification
- Multiple visualization types (box plots, bar charts, scatter plots, heatmaps, etc.)
- AI-powered experiment summaries, trend analysis, and recommendations
- A fully bundled Python runtime—no additional installation required

---

## 2. System Requirements

- Operating System: Windows 10 or later
- Memory: ≥ 8 GB recommended (4 GB minimum)
- Disk Space: ≥ 5 GB available
- GPU (optional): For Cellpose GPU acceleration, ensure a compatible CUDA driver is installed

---

## 3. Package Contents

After extracting the archive, the `EasyReporter` root folder contains:

| Item | Description |
| --- | --- |
| `start.bat` | Launch script (double-click to start the app) |
| `streamlit_app.py` | Main Streamlit application |
| `02.Code/` | Core logic modules (AI helper, plotting utilities, Cellpose wrapper) |
| `05.models/` | Bundled Cellpose pretrained models |
| `python_runtime/` | Portable Python 3.10 runtime with all dependencies |
| `assets/` | Icon and static resources |
| `.streamlit/` | Streamlit configuration (theme, etc.) |
| `README.txt` | Quick-start instructions (English) |
| `USER_MANUAL_CN.md` | Chinese user manual |
| `USER_MANUAL_EN.md` | This English manual |

> During runtime, the application stores project data inside `EasyReporter_Projects/`.

> Download package: [https://pan.baidu.com/s/1gopCC2PPV_ng2SiY7pshdQ?pwd=3g4x](https://pan.baidu.com/s/1gopCC2PPV_ng2SiY7pshdQ?pwd=3g4x)

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
- The files are copied into the current project’s `01.Data/`, then Cellpose performs segmentation and fluorescence quantification.

### Step 2: Chart Generation
- Choose from multiple visualization types, configure grouping/metrics/colors, and preview the charts in real time.

### Step 3: Download Outputs
- Download the generated charts, raw tables, and export artifacts in a single click for reporting and archiving.

### Step 4: AI Insights
- Enter an API key (or rely on the bundled encrypted default) to request AI-generated summaries, trend analysis, and recommendations.

---

## 6. Language Toggle

- Use the language switcher in the top-right corner of the interface to toggle between English and Chinese.

---

## 7. Directory & Data Layout

During operation, per-project data resides under `EasyReporter_Projects/<project_name>/`:

| Subfolder | Description |
| --- | --- |
| `01.Data/` | Uploaded/imported raw images (isolated per project) |
| `03.Cellpose_output/` | Cellpose results (`Cell_Counts/` and `Fluorescence_Intensity/`) |
| `04.Chart/` | Generated charts and exported files |
| Misc | Additional artifacts such as AI reports or temp files, depending on features used |

Delete individual project folders to remove historical runs without affecting other data or models.

---

## 8. Backup Recommendations

- Regularly back up the entire `EasyReporter_Projects/` directory, or archive specific project folders as needed.
- For shared or critical environments, place the folder under version control or a scheduled backup solution.

---

## 9. Troubleshooting

1. **Application won’t start**: Ensure `python_runtime\python.exe` exists and that `start.bat` sits next to `streamlit_app.py`.
2. **Port already in use**: The app defaults to port 8501; close other instances or edit the port arguments in `start.bat`.
3. **Cellpose errors**: Verify that `05.models/` is intact; switch to CPU mode or rerun if necessary.
4. **AI features unavailable**: Check network access and API key validity. Configure proxies at the OS level if required.
5. **UI not responding**: Refresh the browser or stop (`Ctrl + C`) and relaunch the application.

---

## 10. Customization & Extensions

- All business logic resides in `02.Code/`. Extend chart types, processing steps, or AI prompts there.
- Restart via `start.bat` after making changes for them to take effect.

---

## 11. Support

- Contact the project maintainer or review inline code comments for additional help.
- Feedback and feature requests are welcome via issues or email.

---

**Happy analyzing!**
