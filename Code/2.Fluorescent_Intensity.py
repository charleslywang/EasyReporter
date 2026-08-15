# -*- coding: utf-8 -*-
import os
import sys
import io
import numpy as np

# 确保在Windows环境下正确处理Unicode字符
if sys.platform.startswith('win'):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')
import tifffile as tiff
import pandas as pd
import re
import argparse
from scipy.spatial import KDTree

def extract_cell_centers(outline_file):
    cell_centers = {}
    with open(outline_file, "r") as f:
        for i, line in enumerate(f):
            cell_id = i + 1
            line = line.strip()
            if not line:
                continue
            try:
                coords = list(map(int, line.split(',')))
            except ValueError:
                continue
            if len(coords) % 2 != 0:
                continue
            x_coords = coords[::2]
            y_coords = coords[1::2]
            center_x = int(np.mean(x_coords))
            center_y = int(np.mean(y_coords))
            cell_centers[cell_id] = (center_x, center_y)
    return cell_centers

def extract_fluorescence(image_path, mask_path, outline_path):
    img = tiff.imread(image_path) if image_path else None
    mask_data = np.load(mask_path, allow_pickle=True).item()
    masks = mask_data['masks']
    cell_centers = extract_cell_centers(outline_path)

    results = []
    unique_cells = np.unique(masks)[1:]  # exclude background

    for cell_id in unique_cells:
        cell_mask = (masks == cell_id)
        if img is not None:
            cell_pixels = img[cell_mask]
            total_intensity = np.sum(cell_pixels)
            mean_intensity = np.mean(cell_pixels)
            max_intensity = np.max(cell_pixels)
            min_intensity = np.min(cell_pixels)
        else:
            total_intensity = mean_intensity = max_intensity = min_intensity = np.nan

        center_x, center_y = cell_centers.get(cell_id, (None, None))

        results.append([
            cell_id, total_intensity, mean_intensity,
            max_intensity, min_intensity, center_x, center_y
        ])

    return pd.DataFrame(results, columns=[
        "CellID", "TotalIntensity", "MeanIntensity",
        "MaxIntensity", "MinIntensity", "CenterX", "CenterY"
    ])

def find_files(npy_dir, txt_dir):
    npy_files, tif_files, txt_files = {}, {}, {}

    for root, _, files in os.walk(npy_dir):
        for file in files:
            match_npy = re.match(r"(.+?)_(EGFP|mcherry)-(\d+)_seg\.npy$", file)
            match_tif = re.match(r"(.+?)_(EGFP|mcherry)-(\d+)\.tif$", file, re.IGNORECASE)

            if match_npy:
                base, channel, fid = match_npy.groups()
                key = f"{base}_{fid}"
                npy_files.setdefault(key, {})[f"{channel}_mask"] = os.path.join(root, file)

            if match_tif:
                base, channel, fid = match_tif.groups()
                key = f"{base}_{fid}"
                tif_files.setdefault(key, {})[f"{channel}_img"] = os.path.join(root, file)

    for root, _, files in os.walk(txt_dir):
        for file in files:
            match_txt = re.match(r"(.+?)_(EGFP|mcherry)-(\d+)_cp_outlines\.txt$", file)
            if match_txt:
                base, channel, fid = match_txt.groups()
                key = f"{base}_{fid}"
                txt_files.setdefault(key, {})[f"{channel}_outline"] = os.path.join(root, file)

    return npy_files, tif_files, txt_files

def match_cells(egfp_df, mcherry_df, distance_threshold):
    egfp_cells, mcherry_cells, overlap_cells = [], [], []

    if not egfp_df.empty and not mcherry_df.empty:
        # 使用有效坐标的红色细胞表（reset_index 保证行列一一对应）
        mcherry_valid = mcherry_df.dropna(subset=["CenterX", "CenterY"]).reset_index(drop=True)
        mcherry_coords = mcherry_valid[["CenterX", "CenterY"]].values
        mcherry_tree = KDTree(mcherry_coords)

        matched_mcherry_ids = set()
        used_mcherry_pos = set()  # 已被占用的红色细胞位置：保证一对一匹配，避免重复使用同一个红色细胞
        k = min(len(mcherry_valid), 10)

        for _, egfp_row in egfp_df.iterrows():
            if pd.isna(egfp_row["CenterX"]) or pd.isna(egfp_row["CenterY"]):
                continue
            matched = False
            if len(mcherry_valid) > 0:
                dists, idxs = mcherry_tree.query([egfp_row["CenterX"], egfp_row["CenterY"]], k=k)
                dists = np.atleast_1d(dists)
                idxs = np.atleast_1d(idxs)
                for dist, j in zip(dists, idxs):
                    if dist > distance_threshold:
                        break
                    j = int(j)
                    if j in used_mcherry_pos:
                        continue  # 该红色细胞已被其他绿色细胞匹配，尝试下一个最近红色细胞
                    mcherry_row = mcherry_valid.iloc[j]
                    overlap_cells.append({
                        "CellType": "EGFP+mcherry",
                        "CenterX": egfp_row["CenterX"],
                        "CenterY": egfp_row["CenterY"],
                        "EGFP_CellID": egfp_row["CellID"],
                        "EGFP_TotalIntensity": egfp_row["TotalIntensity"],
                        "EGFP_MeanIntensity": egfp_row["MeanIntensity"],
                        "mcherry_CellID": mcherry_row["CellID"],
                        "mcherry_TotalIntensity": mcherry_row["TotalIntensity"],
                        "mcherry_MeanIntensity": mcherry_row["MeanIntensity"],
                    })
                    matched_mcherry_ids.add(mcherry_row["CellID"])
                    used_mcherry_pos.add(j)
                    matched = True
                    break
            if not matched:
                egfp_cells.append({
                    "CellType": "EGFP",
                    "CenterX": egfp_row["CenterX"],
                    "CenterY": egfp_row["CenterY"],
                    "EGFP_CellID": egfp_row["CellID"],
                    "EGFP_TotalIntensity": egfp_row["TotalIntensity"],
                    "EGFP_MeanIntensity": egfp_row["MeanIntensity"],
                    "mcherry_CellID": np.nan,
                    "mcherry_TotalIntensity": np.nan,
                    "mcherry_MeanIntensity": np.nan,
                })

        for _, mcherry_row in mcherry_df.iterrows():
            if mcherry_row["CellID"] in matched_mcherry_ids:
                continue
            if pd.isna(mcherry_row["CenterX"]) or pd.isna(mcherry_row["CenterY"]):
                continue
            mcherry_cells.append({
                "CellType": "mcherry",
                "CenterX": mcherry_row["CenterX"],
                "CenterY": mcherry_row["CenterY"],
                "EGFP_CellID": np.nan,
                "EGFP_TotalIntensity": np.nan,
                "EGFP_MeanIntensity": np.nan,
                "mcherry_CellID": mcherry_row["CellID"],
                "mcherry_TotalIntensity": mcherry_row["TotalIntensity"],
                "mcherry_MeanIntensity": mcherry_row["MeanIntensity"],
            })

    all_cells = egfp_cells + mcherry_cells + overlap_cells
    return pd.DataFrame(all_cells)

def process_all(npy_dir, txt_dir, output_dir, distance_threshold=15):
    npy_files, tif_files, txt_files = find_files(npy_dir, txt_dir)
    os.makedirs(output_dir, exist_ok=True)

    for base_name in npy_files:
        required_keys = ["EGFP_mask", "mcherry_mask"]
        has_npy = all(k in npy_files[base_name] for k in required_keys)
        has_tif = base_name in tif_files and all(k in tif_files[base_name] for k in ["EGFP_img", "mcherry_img"])
        has_txt = base_name in txt_files and all(k in txt_files[base_name] for k in ["EGFP_outline", "mcherry_outline"])

        if not (has_npy and has_tif and has_txt):
            print(f"WARNING: Missing files: {base_name}")
            continue

        egfp_df = extract_fluorescence(
            tif_files[base_name]["EGFP_img"],
            npy_files[base_name]["EGFP_mask"],
            txt_files[base_name]["EGFP_outline"]
        )
        mcherry_df = extract_fluorescence(
            tif_files[base_name]["mcherry_img"],
            npy_files[base_name]["mcherry_mask"],
            txt_files[base_name]["mcherry_outline"]
        )

        result_df = match_cells(egfp_df, mcherry_df, distance_threshold)

        relative_path = os.path.relpath(npy_files[base_name]["EGFP_mask"], npy_dir)
        sub_dir = os.path.dirname(relative_path)
        output_sub_dir = os.path.join(output_dir, sub_dir)
        os.makedirs(output_sub_dir, exist_ok=True)

        output_file = os.path.join(output_sub_dir, f"{base_name}_combined.csv")
        result_df.to_csv(output_file, index=False)
        print(f"[SUCCESS] Saved: {output_file}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Cell fluorescence intensity analysis and pairing')
    parser.add_argument('--npy_input', required=True, help='Root directory containing .npy and .tif files')
    parser.add_argument('--txt_input', required=True, help='Root directory containing .txt files')
    parser.add_argument('--output', required=True, help='Output directory')
    parser.add_argument('--distance_threshold', type=int, default=15, help='Cell matching distance threshold (default: 15 pixels)')
    args = parser.parse_args()

    process_all(
        npy_dir=args.npy_input,
        txt_dir=args.txt_input,
        output_dir=args.output,
        distance_threshold=args.distance_threshold
    )


