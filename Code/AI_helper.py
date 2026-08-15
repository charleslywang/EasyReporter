import streamlit as st
import openai
from openai import OpenAI
import os
import pandas as pd
import time
import random
import re
import numpy as np
import base64

# 导入密钥管理器
try:
    from key_manager import get_default_api_key
    KEY_MANAGER_AVAILABLE = True
except ImportError:
    KEY_MANAGER_AVAILABLE = False
    # 后备方案：如果密钥管理器不可用，使用空字符串
    def get_default_api_key():
        return ""


def _t(lang, zh_text, en_text):
    """根据语言返回对应文案"""
    return zh_text if (lang or 'zh') == 'zh' else en_text


def get_openai_key():
    """
    获取OpenAI API Key。
    优先从session_state获取，其次使用加密存储的默认密钥。
    """
    # 如果session_state中有密钥，优先使用（用户自定义）
    session_key = st.session_state.get("openai_api_key", "")
    if session_key:
        return session_key
    
    # 使用加密存储的默认DeepSeek API密钥
    if KEY_MANAGER_AVAILABLE:
        return get_default_api_key()
    else:
        return ""


def format_target_for_display(text):
    """
    将文本中的 sg1, sg2, ... sg12 替换为 site1, site2, ... site12
    用于 AI 报告中的显示格式化
    
    Args:
        text: 原始文本，可能包含 sg1-sg12 等标识符
    
    Returns:
        str: 格式化后的文本，sg 替换为 site
    """
    if not text:
        return text
    
    import re
    
    # 替换 sg数字 为 site数字（支持 sg1-sg12）
    # 使用单词边界确保只替换完整的 sg\d+ 模式
    formatted_text = re.sub(r'\bsg(\d+)\b', r'site\1', text, flags=re.IGNORECASE)
    
    return formatted_text


def group_charts_by_data(all_charts, main_category="Cell_Distribution_Scatter_Plot"):
    """
    按 Cell Distribution Scatter 图为主选，自动联动展示同一数据的其它类型图。
    返回：
      {
        main_chart_id: {
            "main": main_chart_info,
            "others": {cat: [chart_info, ...], ...}
        }, ...
      }
    """
    import re
    data_groups = {}
    # 文件名示例: 0606_293T_cas9-sg10_1-1_analysis.png
    # 提取格式: cas9-sg10_1-1 (蛋白-靶点_重复-视野)
    # 两种模式：
    # 1. 图表文件: cas9-sg10_1-1_analysis.png
    # 2. 原始图片: cas12-sg1_1_EGFP-1.tif
    pattern1 = re.compile(r"(cas\d+-sg\d+)_(\d+)-(\d+)_", re.IGNORECASE)  # 图表格式
    pattern2 = re.compile(r"(cas\d+-sg\d+)[._](\d+)[._][^-]+-(\d+)", re.IGNORECASE)  # 原始图片格式
    
    # 调试：打印输入
    print(f"[DEBUG] group_charts_by_data called")
    print(f"[DEBUG] main_category: {main_category}")
    print(f"[DEBUG] all_charts keys: {list(all_charts.keys()) if all_charts else 'None'}")
    
    # 先收集主图
    main_charts = all_charts.get(main_category, [])
    print(f"[DEBUG] Found {len(main_charts)} main charts in category '{main_category}'")
    
    for chart in main_charts:
        fname = chart["filename"]
        # 尝试两种模式
        m = pattern1.search(fname) or pattern2.search(fname)
        print(f"[DEBUG] Checking file: {fname}, Match: {m.groups() if m else 'No match'}")
        if m:
            # 生成格式: cas9-sg10_1-1
            data_id = f"{m.group(1)}_{m.group(2)}-{m.group(3)}"
            print(f"[DEBUG] Created data_id: {data_id}")
            data_groups[data_id] = {"main": chart, "others": {}}
    
    print(f"[DEBUG] Total data_groups created: {len(data_groups)}")
    
    # 再收集其它类型
    for cat, charts in all_charts.items():
        if cat == main_category:
            continue
        for chart in charts:
            fname = chart["filename"]
            m = pattern1.search(fname) or pattern2.search(fname)
            if m:
                data_id = f"{m.group(1)}_{m.group(2)}-{m.group(3)}"
                if data_id in data_groups:
                    if cat not in data_groups[data_id]["others"]:
                        data_groups[data_id]["others"][cat] = []
                    data_groups[data_id]["others"][cat].append(chart)
    return data_groups


def group_charts_by_protein(all_charts, main_category="Cell_Distribution_Scatter_Plot"):
    """
    按蛋白类型分组数据，每个蛋白下包含其所有数据ID。
    返回：
      {
        "cas9": {
            "cas9-sg1-01": {"main": ..., "others": {...}},
            "cas9-sg1-02": {"main": ..., "others": {...}},
            ...
        },
        "cas12": {
            "cas12-sg1-01": {"main": ..., "others": {...}},
            ...
        }
      }
    """
    import re
    protein_groups = {}
    # 文件名示例: 0606_293T_cas9-sg1_1-16_analysis.png
    pattern = re.compile(r"(cas\d+)-sg\d+[._-]\d+-\d+")
    
    # 先按数据ID分组所有图表
    data_groups = group_charts_by_data(all_charts, main_category)
    
    # 再按蛋白类型组织
    for data_id, charts in data_groups.items():
        # 从data_id中提取蛋白类型（如 "cas9-sg1-01" → "cas9"）
        m = re.match(r"(cas\d+)", data_id, re.IGNORECASE)
        if m:
            protein = m.group(1).lower()
            if protein not in protein_groups:
                protein_groups[protein] = {}
            protein_groups[protein][data_id] = charts
    
    return protein_groups


def group_charts_by_protein_and_target(all_charts, main_category="Cell_Distribution_Scatter_Plot"):
    """
    按蛋白→靶点→数据ID三层结构分组图表。
    返回：
      {
        "cas9": {
            "sg1": {
                "cas9-sg1_1-1": {"main": ..., "others": {...}},
                "cas9-sg1_2-3": {"main": ..., "others": {...}},
                ...
            },
            "sg2": {
                "cas9-sg2_1-1": {"main": ..., "others": {...}},
                ...
            }
        },
        "cas12": {
            "sg1": {...},
            ...
        }
      }
    """
    import re
    result = {}
    
    # 先按数据ID分组所有图表
    data_groups = group_charts_by_data(all_charts, main_category)
    
    # 按蛋白→靶点→数据ID三层组织
    for data_id, charts in data_groups.items():
        # 提取蛋白类型和靶点编号
        # data_id格式: cas9-sg1_1-1, cas12-sg2_3-4 等
        m = re.match(r"(cas\d+)[-_]sg(\d+)", data_id, re.IGNORECASE)
        if m:
            protein = m.group(1).lower()  # cas9, cas12
            target = f"sg{m.group(2)}"     # sg1, sg2, sg3
            
            if protein not in result:
                result[protein] = {}
            if target not in result[protein]:
                result[protein][target] = {}
            
            result[protein][target][data_id] = charts
    
    return result
    
    
def another_function():  # Example of existing function for context
    pass  # Placeholder for existing code
import streamlit as st
import openai
from openai import OpenAI
import os
import pandas as pd
import time
import random
import re
import numpy as np
import base64


def collect_chart_previews(work_dir: str, max_per_type: int = 1):
    """
    收集每种图表类型的代表图片（用于可视化模型或在提示词中列出）。
    返回列表：[ {"category": str, "path": str, "ext": str}, ... ]
    仅包含常见位图格式(.png/.jpg/.jpeg)，PDF等将被忽略（可在文本中列出）。
    """
    previews = []
    # 优先使用easyreporter_charts目录，如果不存在则使用Chart
    chart_dir = os.path.join(work_dir, "easyreporter_charts")
    if not os.path.exists(chart_dir):
        chart_dir = os.path.join(work_dir, "Chart")
        if not os.path.exists(chart_dir):
            return previews
    preferred_exts = (".png", ".jpg", ".jpeg")
    category_dirs = [d for d in sorted(os.listdir(chart_dir)) if os.path.isdir(os.path.join(chart_dir, d))]
    for cat in category_dirs:
        cat_dir = os.path.join(chart_dir, cat)
        chosen = []
        # 先在当前目录挑选
        try:
            files = [f for f in os.listdir(cat_dir) if os.path.isfile(os.path.join(cat_dir, f))]
            files_sorted = sorted(files)
            for ext in preferred_exts:
                for f in files_sorted:
                    if f.lower().endswith(ext):
                        chosen.append(os.path.join(cat_dir, f))
                        if len(chosen) >= max_per_type:
                            break
                if len(chosen) >= max_per_type:
                    break
        except Exception:
            pass
        # 若未找到，则在子目录递归搜索
        if len(chosen) < max_per_type:
            for root2, _, files2 in os.walk(cat_dir):
                files_sorted2 = sorted(files2)
                for ext in preferred_exts:
                    for f in files_sorted2:
                        if f.lower().endswith(ext):
                            chosen.append(os.path.join(root2, f))
                            if len(chosen) >= max_per_type:
                                break
                    if len(chosen) >= max_per_type:
                        break
                if len(chosen) >= max_per_type:
                    break
        # 记录
        for p in chosen:
            ext = os.path.splitext(p)[1].lower()
            previews.append({"category": cat, "path": p, "ext": ext})
    return previews


def collect_all_charts_info(work_dir: str):
    """
    收集所有图表的完整信息，包括每种类型的所有图表文件。
    返回字典：{"category": [{"path": str, "filename": str}, ...], ...}
    """
    all_charts = {}
    # 优先使用easyreporter_charts目录，如果不存在则使用Chart
    chart_dir = os.path.join(work_dir, "easyreporter_charts")
    if not os.path.exists(chart_dir):
        chart_dir = os.path.join(work_dir, "Chart")
        if not os.path.exists(chart_dir):
            return all_charts
    
    preferred_exts = (".png", ".jpg", ".jpeg")
    category_dirs = [d for d in sorted(os.listdir(chart_dir)) if os.path.isdir(os.path.join(chart_dir, d))]
    
    for cat in category_dirs:
        cat_dir = os.path.join(chart_dir, cat)
        chart_files = []
        
        # 递归搜索所有图表文件
        for root, _, files in os.walk(cat_dir):
            for f in sorted(files):
                if any(f.lower().endswith(ext) for ext in preferred_exts):
                    full_path = os.path.join(root, f)
                    chart_files.append({
                        "path": full_path,
                        "filename": f
                    })
        
        if chart_files:
            all_charts[cat] = chart_files
    
    return all_charts


def collect_chart_previews_original(work_dir: str, max_per_type: int = 1):
    previews = []
    chart_dir = os.path.join(work_dir, "Chart")
    if not os.path.exists(chart_dir):
        return previews
    preferred_exts = (".png", ".jpg", ".jpeg")
    category_dirs = [d for d in sorted(os.listdir(chart_dir)) if os.path.isdir(os.path.join(chart_dir, d))]
    for cat in category_dirs:
        cat_dir = os.path.join(chart_dir, cat)
        chosen = []
        # 先在当前目录挑选
        try:
            files = [f for f in os.listdir(cat_dir) if os.path.isfile(os.path.join(cat_dir, f))]
            files_sorted = sorted(files)
            for ext in preferred_exts:
                for f in files_sorted:
                    if f.lower().endswith(ext):
                        chosen.append(os.path.join(cat_dir, f))
                        if len(chosen) >= max_per_type:
                            break
                if len(chosen) >= max_per_type:
                    break
        except Exception:
            pass
        # 若未找到，则在子目录递归搜索
        if len(chosen) < max_per_type:
            for root2, _, files2 in os.walk(cat_dir):
                files_sorted2 = sorted(files2)
                for ext in preferred_exts:
                    for f in files_sorted2:
                        if f.lower().endswith(ext):
                            chosen.append(os.path.join(root2, f))
                            if len(chosen) >= max_per_type:
                                break
                    if len(chosen) >= max_per_type:
                        break
                if len(chosen) >= max_per_type:
                    break
        # 记录
        for p in chosen:
            ext = os.path.splitext(p)[1].lower()
            previews.append({"category": cat, "path": p, "ext": ext})
    return previews


def summarize_data_for_ai(work_dir, lang='zh'):
    """
    汇总分析结果，为AI生成prompt准备数据（自动压缩以降低Token）。
    - lang: 摘要语言标签（'zh' 或 'en'），必须与报告语言保持一致，避免英文报告混入中文标签
    - 仅选取每类最多3个CSV文件
    - 每个CSV仅保留前5行与关键统计（数值列的均值/标准差）
    - 重点加入编辑效率(all_summary.csv)的统计摘要，增加稳健统计(IQR)、异常值与组间差异
    - 附加：列出将要用于AI解读的代表图（类别与文件名），便于在无图像模型下也有上下文
    """
    summary = []
    use_en = (lang == 'en')

    def safe_stat(series, func):
        filtered = pd.Series(series).replace([np.inf, -np.inf], np.nan).dropna()
        if filtered.empty:
            return np.nan
        return float(func(filtered))

    def fmt_int(value):
        if value is None or (isinstance(value, float) and (np.isnan(value) or np.isinf(value))):
            return "NA"
        return f"{int(round(value))}"

    def fmt_float(value, digits=1):
        if value is None or (isinstance(value, float) and (np.isnan(value) or np.isinf(value))):
            return "NA"
        return f"{value:.{digits}f}"

    def fmt_percent(value, digits=1):
        if value is None or (isinstance(value, float) and (np.isnan(value) or np.isinf(value))):
            return "NA"
        return f"{value * 100:.{digits}f}%"

    def summarize_csv_dir(dir_path: str, title: str):
        if not os.path.exists(dir_path):
            return
        files = [f for f in os.listdir(dir_path) if f.endswith(".csv")]
        files.sort()
        # 限制处理的文件数量，减少提示词体积
        for file in files[:3]:
            fp = os.path.join(dir_path, file)
            try:
                df = pd.read_csv(fp)
                # 仅保留前5行
                head_text = df.head(5).to_string(index=False)
                # 数值列统计
                numeric_cols = df.select_dtypes(include=["number"]).columns
                stats_text = ""
                if len(numeric_cols) > 0:
                    desc = df[numeric_cols].describe().loc[["mean", "std", "min", "max"]]
                    stats_text = desc.to_string()
                summary.append(f"[{title}] file {file}\nTop 5 rows:\n{head_text}\nNumeric columns stats (mean/std/min/max):\n{stats_text}")
            except Exception as e:
                # 单个文件失败不影响整体
                summary.append(f"[{title}] file {file} read failed: {e}")

    # 1. 原始通道计数不再提供给AI（避免与图表匹配计数混淆）。
    #    统一使用 all_summary.csv（Cell Distribution Scatter 图表数据）作为唯一权威计数来源。

    # 2. 汇总荧光强度结果
    fluorescence_dir = os.path.join(work_dir, "Cellpose_output", "Fluorescence_Intensity")
    summarize_csv_dir(fluorescence_dir, "Fluorescent intensity results")

    # 预计算的全局总数（来自 all_summary.csv），供后文与AI解读引用
    all_summary_totals = None

    # 3. 汇总编辑效率（核心：Cell_Distribution_Scatter输出的 all_summary.csv ）
    try:
        eff_path = os.path.join(work_dir, "Chart", "Cell_Distribution_Scatter_Plot", "all_summary.csv")
        if os.path.exists(eff_path):
            df = pd.read_csv(eff_path)
            # 权威每样本匹配计数（即图表图例中的数值）——AI解读唯一应引用的细胞数来源
            count_cols = [c for c in ["EGFP_only", "mcherry_only", "overlap", "total"] if c in df.columns]
            if count_cols:
                summary.append(
                    "[AUTHORITATIVE per-sample cell counts (chart legend values)]\n"
                    "These matched counts come from the Cell Distribution Scatter distance matching and are the ONLY cell-count values to cite in the report.\n"
                    "NEVER cite raw per-channel segmentation counts from Cell_Counts/combined_results.csv (e.g., GreenCellCount/RedCellCount) - they are NOT the chart values.\n"
                    + df[["sample"] + count_cols].to_string(index=False)
                )
                # 预计算全局总数（由 all_summary.csv 汇总，AI报告中所有聚合总数必须引用这些值）
                num_df = df[count_cols].apply(pd.to_numeric, errors="coerce")
                all_summary_totals = {
                    "samples": int(len(df)),
                    "total_cells": int(num_df["total"].sum()) if "total" in num_df.columns else None,
                    "median_cells": float(num_df["total"].median()) if "total" in num_df.columns else None,
                    "egfp_only_total": int(num_df["EGFP_only"].sum()) if "EGFP_only" in num_df.columns else None,
                    "mcherry_only_total": int(num_df["mcherry_only"].sum()) if "mcherry_only" in num_df.columns else None,
                    "overlap_total": int(num_df["overlap"].sum()) if "overlap" in num_df.columns else None,
                }
                if use_en:
                    totals_lines = [
                        "[AUTHORITATIVE overall totals (precomputed from all_summary.csv)]",
                        f"Total samples: {all_summary_totals['samples']}",
                        f"Total cells across all samples (sum of 'total' column): {all_summary_totals['total_cells']}",
                        f"Median cells per sample: {fmt_int(all_summary_totals['median_cells'])}",
                        f"Total GFP-only: {all_summary_totals['egfp_only_total']} | Total mCherry-only: {all_summary_totals['mcherry_only_total']} | Total overlap: {all_summary_totals['overlap_total']}",
                        "When reporting aggregate cell counts (e.g., 'total cells across all samples'), ALWAYS use these precomputed values. Do NOT re-sum per-sample rows yourself.",
                    ]
                else:
                    totals_lines = [
                        "[权威全局总数（由 all_summary.csv 预计算）]",
                        f"总样本数: {all_summary_totals['samples']}",
                        f"全部样本总细胞数（total 列求和）: {all_summary_totals['total_cells']}",
                        f"单样本细胞中位数: {fmt_int(all_summary_totals['median_cells'])}",
                        f"GFP单阳性总数: {all_summary_totals['egfp_only_total']} | mCherry单阳性总数: {all_summary_totals['mcherry_only_total']} | 重叠(Overlap)总数: {all_summary_totals['overlap_total']}",
                        "报告任何聚合细胞总数时（如「所有样本的细胞总数」），必须使用这些预计算值，禁止自行对每样本数值再次求和。",
                    ]
                summary.append("\n".join(totals_lines))
            if "Target_Efficiency (%)" in df.columns:
                df["TargetEfficiency"] = pd.to_numeric(df["Target_Efficiency (%)"], errors="coerce")
                df_eff = df.dropna(subset=["TargetEfficiency"]).copy()
                n = len(df_eff)
                if n > 0:
                    desc = df_eff["TargetEfficiency"].describe()
                    # 稳健统计与异常值
                    q1 = df_eff["TargetEfficiency"].quantile(0.25)
                    q3 = df_eff["TargetEfficiency"].quantile(0.75)
                    iqr = q3 - q1
                    low_thr = q1 - 1.5 * iqr
                    high_thr = q3 + 1.5 * iqr
                    outliers = df_eff[(df_eff["TargetEfficiency"] < low_thr) | (df_eff["TargetEfficiency"] > high_thr)]
                    outlier_text = f"Outliers by IQR: {len(outliers)} (low<{low_thr:.2f}% | high>{high_thr:.2f}%)"

                    overall_text = (
                        f"Samples: {n}\n"
                        f"Mean: {desc.get('mean', np.nan):.2f}% | Median: {desc.get('50%', np.nan):.2f}%\n"
                        f"Min: {desc.get('min', np.nan):.2f}% | Max: {desc.get('max', np.nan):.2f}% | Std: {desc.get('std', np.nan):.2f}%\n"
                        f"Robust (IQR): Q1={q1:.2f}% | Q3={q3:.2f}% | IQR={iqr:.2f}%\n"
                        f"{outlier_text}"
                    )
                    # Top/Bottom 3
                    top3 = df_eff.nlargest(3, "TargetEfficiency")[ ["sample", "TargetEfficiency"] ]
                    bottom3 = df_eff.nsmallest(3, "TargetEfficiency")[ ["sample", "TargetEfficiency"] ]
                    top_text = "\n".join([f"Top{i+1}: {r['sample']} -> {r['TargetEfficiency']:.2f}%" for i, r in top3.iterrows()])
                    bot_text = "\n".join([f"Bottom{i+1}: {r['sample']} -> {r['TargetEfficiency']:.2f}%" for i, r in bottom3.iterrows()])

                    # 按 Main_Target 聚合（若能解析）
                    group_text = ""
                    effect_text = ""
                    try:
                        extract_pattern = r".*?((?:[Cc]as\d+-sg\d+))[._-](\d+)-\d+$"
                        extracted = df_eff["sample"].str.extract(extract_pattern, expand=True)
                        if not extracted.isnull().any().any():
                            df_eff["Main_Target"] = extracted[0].str.lower()
                            df_eff["Replicate"] = pd.to_numeric(extracted[1], errors="coerce")
                            means = df_eff.groupby("Main_Target")["TargetEfficiency"].mean().sort_values(ascending=False)
                            
                            # 转换为友好名称显示（cas9-sg1 -> SpCas9-sg1, cas12-sg2 -> hfCas12Max-sg2）
                            def convert_target_name(target_name):
                                """将内部目标名称转换为显示名称"""
                                match = re.match(r'(cas\d+)[-_]?sg(\d+)', str(target_name), re.IGNORECASE)
                                if match:
                                    cas_type = match.group(1).lower()
                                    sg_num = match.group(2)
                                    if cas_type == "cas9":
                                        return f"SpCas9-sg{sg_num}"
                                    elif cas_type == "cas12":
                                        return f"hfCas12Max-sg{sg_num}"
                                    else:
                                        return f"{match.group(1).capitalize()}-sg{sg_num}"
                                return str(target_name)
                            
                            group_text = "; ".join([f"{convert_target_name(k)}: {v:.2f}%" for k, v in means.head(10).items()])
                            # 复制一致性（CV）
                            cv_df = df_eff.groupby("Main_Target")["TargetEfficiency"].agg(['mean','std','count'])
                            cv_df["cv"] = cv_df["std"] / cv_df["mean"]
                            worst_cv = cv_df.sort_values("cv", ascending=False).head(5)
                            cv_text = "; ".join([f"{convert_target_name(idx)}: CV={row['cv']:.2f} (n={int(row['count'])})" for idx, row in worst_cv.iterrows() if np.isfinite(row['cv'])])
                            # 组间差异（简单效应大小：最佳-最差）
                            if len(means) >= 2:
                                effect_size = float(means.iloc[0] - means.iloc[-1])
                                effect_text = f"Effect size (best-worst): {effect_size:.2f}%"
                        else:
                            cv_text = "Unable to parse Main_Target/Replicate from sample"
                    except Exception:
                        group_text = ""
                        cv_text = "Failed to parse grouping"

                    summary.append(
                        "[Editing efficiency summary (from Cell Distribution Scatter)]\n"
                        "This analysis is based on cell spatial positions and counts, NOT fluorescence intensity.\n"
                        "Definition: Target_Efficiency(%) = GFP_only / (GFP_only + overlap) × 100.\n"
                        "Interpretation: GFP_only cells are considered successfully edited, while 'overlap' (GFP and mCherry double-positive) cells are considered unedited.\n"
                        f"Overall: \n{overall_text}\n"
                        f"Top 3 samples:\n{top_text}\n"
                        f"Bottom 3 samples:\n{bot_text}\n"
                        + (f"Mean by Main_Target (Top 10): {group_text}\n" if group_text else "")
                        + (f"Worst replicate consistency (highest CV): {cv_text}\n" if 'cv_text' in locals() else "")
                        + (f"{effect_text}" if effect_text else "")
                    )
    except Exception as e:
        summary.append(f"[Editing efficiency summary] failed to load: {e}")

    # 4. 增强：荧光强度全局统计与排名
    try:
        fluorescence_root = os.path.join(work_dir, "Cellpose_output", "Fluorescence_Intensity")
        sample_metrics = []
        read_warnings = []

        def classify_celltype(value: str) -> str:
            if not isinstance(value, str):
                return "other"
            lowered = value.lower()
            has_green = "egfp" in lowered
            has_red = "mcherry" in lowered
            if has_green and has_red:
                return "double_positive"
            if has_green:
                return "green_only"
            if has_red:
                return "red_only"
            return "other"

        if os.path.exists(fluorescence_root):
            # 递归查找所有直接包含 combined CSV 的目录（兼容任意目录层级）
            sample_dirs = []
            for walk_root, walk_dirs, walk_files in os.walk(fluorescence_root):
                if any(f.endswith("_combined.csv") for f in walk_files):
                    sample_dirs.append(walk_root)
            sample_dirs = sorted(set(sample_dirs))
            for sample_dir in sample_dirs:
                dir_path = sample_dir  # os.walk 返回的已是完整路径
                csv_paths = [os.path.join(dir_path, f) for f in os.listdir(dir_path) if f.endswith("_combined.csv")]
                csv_paths.sort()
                frames = []
                for csv_path in csv_paths:
                    try:
                        df = pd.read_csv(
                            csv_path,
                            usecols=[
                                "CellType",
                                "EGFP_TotalIntensity",
                                "EGFP_MeanIntensity",
                                "mcherry_TotalIntensity",
                                "mcherry_MeanIntensity",
                            ],
                        )
                        frames.append(df)
                    except Exception as err:
                        read_warnings.append(f"{os.path.basename(csv_path)}: {err}")
                if not frames:
                    continue

                sample_df = pd.concat(frames, ignore_index=True)
                sample_df["CellType"] = sample_df["CellType"].fillna("")
                sample_df["CellClass"] = sample_df["CellType"].apply(classify_celltype)

                total_cells = len(sample_df)
                green_only = int((sample_df["CellClass"] == "green_only").sum())
                double_positive = int((sample_df["CellClass"] == "double_positive").sum())
                red_only = int((sample_df["CellClass"] == "red_only").sum())
                informative = green_only + double_positive
                edited_ratio = (green_only / informative) if informative else np.nan
                double_positive_ratio = (double_positive / informative) if informative else np.nan

                egfp_means = sample_df["EGFP_MeanIntensity"].replace([np.inf, -np.inf], np.nan).dropna()
                mcherry_means = sample_df["mcherry_MeanIntensity"].replace([np.inf, -np.inf], np.nan).dropna()

                egfp_mean_val = float(egfp_means.mean()) if not egfp_means.empty else np.nan
                egfp_median_val = float(egfp_means.median()) if not egfp_means.empty else np.nan
                mcherry_mean_val = float(mcherry_means.mean()) if not mcherry_means.empty else np.nan
                mcherry_median_val = float(mcherry_means.median()) if not mcherry_means.empty else np.nan

                if not np.isnan(mcherry_mean_val) and mcherry_mean_val != 0:
                    mean_intensity_ratio = egfp_mean_val / mcherry_mean_val if not np.isnan(egfp_mean_val) else np.nan
                else:
                    mean_intensity_ratio = np.nan

                target_match = re.search(r"(cas\d+-sg\d+)", sample_dir, re.IGNORECASE)
                main_target = target_match.group(1).lower() if target_match else os.path.basename(sample_dir).lower()

                sample_metrics.append(
                    {
                        "sample": os.path.basename(sample_dir),
                        "main_target": main_target,
                        "total_cells": total_cells,
                        "green_only": green_only,
                        "double_positive": double_positive,
                        "red_only": red_only,
                        "edited_ratio": edited_ratio,
                        "double_positive_ratio": double_positive_ratio,
                        "egfp_mean_intensity": egfp_mean_val,
                        "egfp_median_intensity": egfp_median_val,
                        "mcherry_mean_intensity": mcherry_mean_val,
                        "mcherry_median_intensity": mcherry_median_val,
                        "mean_intensity_ratio": mean_intensity_ratio,
                    }
                )

        if sample_metrics:
            metrics_df = pd.DataFrame(sample_metrics)

            # 总数优先使用 all_summary.csv 的权威预计算值，保证与图表数据一致
            if all_summary_totals:
                overall_cells = all_summary_totals.get("total_cells")
                n_samples_total = all_summary_totals.get("samples")
                median_cells = all_summary_totals.get("median_cells")
                if median_cells is None:
                    median_cells = safe_stat(metrics_df["total_cells"], np.median)
            else:
                overall_cells = metrics_df["total_cells"].sum()
                n_samples_total = len(metrics_df)
                median_cells = safe_stat(metrics_df["total_cells"], np.median)
            median_edit_ratio = safe_stat(metrics_df["edited_ratio"], np.nanmedian)
            median_double_ratio = safe_stat(metrics_df["double_positive_ratio"], np.nanmedian)
            mean_egfp_intensity = safe_stat(metrics_df["egfp_mean_intensity"], np.nanmean)
            mean_mcherry_intensity = safe_stat(metrics_df["mcherry_mean_intensity"], np.nanmean)

            if use_en:
                overview_lines = [
                    f"Samples: {n_samples_total} | Total cells: {fmt_int(overall_cells)} | Median cells per sample: {fmt_int(median_cells)}",
                    f"Median GFP-only ratio: {fmt_percent(median_edit_ratio)} | Median double-positive ratio: {fmt_percent(median_double_ratio)}",
                    f"GFP mean intensity (sample mean): {fmt_float(mean_egfp_intensity, 2)} | mCherry mean intensity (sample mean): {fmt_float(mean_mcherry_intensity, 2)}",
                ]
            else:
                overview_lines = [
                    f"样本数: {n_samples_total} | 总细胞数: {fmt_int(overall_cells)} | 单样本细胞中位数: {fmt_int(median_cells)}",
                    f"绿色单阳性占比中位数: {fmt_percent(median_edit_ratio)} | 双阳性占比中位数: {fmt_percent(median_double_ratio)}",
                    f"GFP 平均强度(样本均值): {fmt_float(mean_egfp_intensity, 2)} | mCherry 平均强度(样本均值): {fmt_float(mean_mcherry_intensity, 2)}",
                ]
            summary.append("[Fluorescence intensity overview]\n" + "\n".join(overview_lines))

            ranked_edit = metrics_df.dropna(subset=["edited_ratio"]).sort_values("edited_ratio", ascending=False)
            if not ranked_edit.empty:
                top_lines = []
                for _, row in ranked_edit.head(5).iterrows():
                    if use_en:
                        top_lines.append(
                            f"{row['sample']} -> edit ratio {fmt_percent(row['edited_ratio'], 1)} (total cells {fmt_int(row['total_cells'])}, double-positive {fmt_percent(row['double_positive_ratio'], 1)})"
                        )
                    else:
                        top_lines.append(
                            f"{row['sample']} → 编辑占比 {fmt_percent(row['edited_ratio'], 1)} (总细胞 {fmt_int(row['total_cells'])}, 双阳性 {fmt_percent(row['double_positive_ratio'], 1)})"
                        )
                summary.append("[Top editing candidates]\n" + "\n".join(top_lines))

                bottom_candidates = ranked_edit.tail(5)
                bottom_lines = []
                for _, row in bottom_candidates.iterrows():
                    if use_en:
                        bottom_lines.append(
                            f"{row['sample']} -> edit ratio {fmt_percent(row['edited_ratio'], 1)} (GFP-only {fmt_int(row['green_only'])}, double-positive {fmt_int(row['double_positive'])})"
                        )
                    else:
                        bottom_lines.append(
                            f"{row['sample']} → 编辑占比 {fmt_percent(row['edited_ratio'], 1)} (绿单阳 {fmt_int(row['green_only'])}, 双阳 {fmt_int(row['double_positive'])})"
                        )
                summary.append("[Low editing candidates]\n" + "\n".join(bottom_lines))

            intensity_rank = metrics_df.dropna(subset=["mean_intensity_ratio"]).sort_values("mean_intensity_ratio", ascending=False)
            if not intensity_rank.empty:
                intensity_lines = []
                for _, row in intensity_rank.head(5).iterrows():
                    if use_en:
                        intensity_lines.append(
                            f"{row['sample']} -> GFP:mCherry mean intensity ratio {fmt_float(row['mean_intensity_ratio'], 2)} (GFP mean {fmt_float(row['egfp_mean_intensity'], 1)}, mCherry mean {fmt_float(row['mcherry_mean_intensity'], 1)})"
                        )
                    else:
                        intensity_lines.append(
                            f"{row['sample']} → GFP:mCherry 平均强度比 {fmt_float(row['mean_intensity_ratio'], 2)} (GFP 平均 {fmt_float(row['egfp_mean_intensity'], 1)}, mCherry 平均 {fmt_float(row['mcherry_mean_intensity'], 1)})"
                        )
                summary.append("[Top intensity contrast]\n" + "\n".join(intensity_lines))

            # 异常值检测
            try:
                from scipy.stats import zscore
                metrics_df['edited_ratio_zscore'] = metrics_df['edited_ratio'].transform(lambda x: zscore(x, nan_policy='omit'))
                outliers = metrics_df[abs(metrics_df['edited_ratio_zscore']) > 2]
                if not outliers.empty:
                    outlier_lines = []
                    for _, row in outliers.iterrows():
                        outlier_lines.append(f"{row['sample']} (z-score: {row['edited_ratio_zscore']:.2f})")
                    summary.append(f"[Outlier Detection - Edit Ratio]\n{', '.join(outlier_lines)}")
            except Exception as e:
                summary.append(f"[Outlier Detection] failed: {e}")

            # 相关性分析
            try:
                correlation_matrix = metrics_df[['edited_ratio', 'double_positive_ratio', 'mean_intensity_ratio']].corr()
                summary.append(f"[Correlation Analysis]\n{correlation_matrix.to_string()}")
            except Exception as e:
                summary.append(f"[Correlation Analysis] failed: {e}")

            # 组间差异的统计检验
            try:
                from scipy.stats import ttest_ind
                control_groups = metrics_df[metrics_df['main_target'].str.contains('control', case=False, na=False)]
                treatment_groups = metrics_df[~metrics_df['main_target'].str.contains('control', case=False, na=False)]

                if not control_groups.empty and not treatment_groups.empty:
                    # 比较编辑效率
                    control_edit_ratios = control_groups['edited_ratio'].dropna()
                    treatment_edit_ratios = treatment_groups['edited_ratio'].dropna()

                    if len(control_edit_ratios) > 1 and len(treatment_edit_ratios) > 1:
                        ttest_stat, p_value = ttest_ind(control_edit_ratios, treatment_edit_ratios, equal_var=False) # Welch's t-test
                        summary.append(f"[Group Difference - Edit Ratio]\nControl vs. Treatment: p-value = {p_value:.4f}")
            except Exception as e:
                summary.append(f"[Group Difference Analysis] failed: {e}")

            target_group = metrics_df.groupby("main_target").agg(
                edited_ratio_mean=("edited_ratio", "mean"),
                edited_ratio_std=("edited_ratio", "std"),
                cells_total=("total_cells", "sum"),
                intensity_ratio_mean=("mean_intensity_ratio", "mean"),
                samples_count=("sample", "count"),
            ).reset_index()

            if not target_group.empty:
                target_group = target_group.replace([np.inf, -np.inf], np.nan)
                high_targets = target_group.dropna(subset=["edited_ratio_mean"]).sort_values("edited_ratio_mean", ascending=False).head(5)
                if not high_targets.empty:
                    lines = []
                    for _, row in high_targets.iterrows():
                        if use_en:
                            lines.append(
                                f"{row['main_target']} -> mean edit ratio {fmt_percent(row['edited_ratio_mean'], 1)} (samples {int(row['samples_count'])}, cumulative cells {fmt_int(row['cells_total'])})"
                            )
                        else:
                            lines.append(
                                f"{row['main_target']} → 平均编辑占比 {fmt_percent(row['edited_ratio_mean'], 1)} (样本 {int(row['samples_count'])}, 累计细胞 {fmt_int(row['cells_total'])})"
                            )
                    summary.append("[Target ranking - Edit Ratio Top]" if use_en else "[Target ranking - 编辑占比 前列]")
                    summary[-1] += "\n" + "\n".join(lines)

                variable_targets = target_group.dropna(subset=["edited_ratio_std"]).sort_values("edited_ratio_std", ascending=False).head(5)
                if not variable_targets.empty:
                    lines = []
                    for _, row in variable_targets.iterrows():
                        if use_en:
                            lines.append(
                                f"{row['main_target']} -> edit ratio std {fmt_percent(row['edited_ratio_std'], 1)} (samples {int(row['samples_count'])})"
                            )
                        else:
                            lines.append(
                                f"{row['main_target']} → 编辑占比标准差 {fmt_percent(row['edited_ratio_std'], 1)} (样本 {int(row['samples_count'])})"
                            )
                    summary.append("[Target variability - watch list]" if use_en else "[Target variability - 需关注]")
                    summary[-1] += "\n" + "\n".join(lines)

        if read_warnings:
            warn_preview = "; ".join(read_warnings[:5])
            if len(read_warnings) > 5:
                if use_en:
                    warn_preview += f" and {len(read_warnings) - 5} more files"
                else:
                    warn_preview += f" 等 {len(read_warnings) - 5} 个文件"
            summary.append(f"[Fluorescent intensity read warnings]\n{warn_preview}")
    except Exception as e:
        summary.append(f"[Fluorescent intensity overview] failed: {e}")

    # 5. 为特定图表类型添加专门的AI分析提示
    chart_previews = collect_chart_previews(work_dir, max_per_type=1)
    chart_types_present = {p['category'] for p in chart_previews}

    if "Cell_Clustering_Scatter_Plot" in chart_types_present:
        summary.append(
            "[AI prompt for Cell Clustering Scatter Plot]\n"
            "This chart visualizes the spatial clustering of different cell types and does NOT use fluorescence intensity data. It transforms cell coordinates to group 'GFP' (edited), 'mcherry', and 'Overlap' (unedited) cells into different quadrants.\n"
            "CRITICAL: The visual quadrant area/span does NOT represent cell count — each cell type is forcibly placed in its designated quadrant regardless of population size. A larger visual spread within a quadrant does NOT mean more cells.\n"
            "CRITICAL - Efficiency vs. Cluster Size Relationship:\n"
            "  Editing Efficiency = GFP-only / (GFP-only + Overlap) x 100%\n"
            "  LOW efficiency (e.g., <10%) means: Overlap count FAR EXCEEDS GFP-only count → Overlap is the LARGEST population, NOT the smallest.\n"
            "  HIGH efficiency (e.g., >50%) means: GFP-only count exceeds Overlap count → GFP-only is the largest population.\n"
            "  DO NOT conflate 'low efficiency' with 'low Overlap proportion' — the relationship is INVERSE.\n"
            "Always check the cell count legend at the bottom of each chart to determine actual population sizes before making claims about cluster sizes."
        )
    
    if "Simulated_Flow_Cytometry_Plot" in chart_types_present:
        summary.append(
            "[AI prompt for Simulated Flow Cytometry Plot]\n"
            "This chart is a scatter plot of log10-transformed mean fluorescence intensity (MFI) for GFP and mCherry, mimicking a flow cytometry analysis. It does NOT use spatial coordinate data. Each dot is a single cell.\n"
            "- The X-axis is Log10(GFP-MFI), and the Y-axis is Log10(mcherry-MFI).\n"
            "- 'GFP' cells (edited) should have high GFP intensity and low mCherry intensity.\n"
            "- 'Overlap' cells (unedited) should have both high GFP and high mCherry intensity.\n"
            "Analyze the separation and distribution of these populations. The distance between the GFP and Overlap clusters on the Y-axis can indicate how effectively the mCherry marker is lost after editing."
        )
    
    # 相关性分析图表提示
    if "correlation_scatter" in chart_types_present or "correlation_scatter" in str(chart_types_present).lower():
        summary.append(
            "[AI prompt for Correlation Scatter Plot]\n"
            "These scatter plots compare three different methods for measuring gene editing efficiency:\n"
            "1. **FACS**: Flow cytometry-based measurement (traditional gold standard)\n"
            "2. **AI**: AI-based image analysis method (this project's automated approach using computer vision and deep learning)\n"
            "3. **Amplicon**: PCR amplicon sequencing method (molecular validation)\n\n"
            "Each scatter plot shows linear regression analysis with Spearman ρ² correlation coefficient:\n"
            "- **Plot 1 (FACS vs AI)**: Validates AI method against traditional flow cytometry\n"
            "- **Plot 2 (FACS vs Amplicon)**: Compares flow cytometry with molecular method\n"
            "- **Plot 3 (AI vs Amplicon)**: Validates AI method against molecular ground truth\n\n"
            "Analysis focus:\n"
            "1. **Correlation strength**: ρ² > 0.7 indicates strong agreement between methods\n"
            "2. **Systematic bias**: Points consistently above/below regression line suggest one method overestimates/underestimates\n"
            "3. **AI method validation**: Strong correlation between AI and both FACS/Amplicon validates the automated approach\n"
            "4. **Outliers**: Samples with large deviations may indicate method-specific limitations or biological complexity\n\n"
            "Interpret the results in terms of method reliability, consistency, and the validity of using AI-based automated analysis as a replacement for manual methods."
        )
    
    if "correlation" in chart_types_present or "correlation_heatmap" in chart_types_present or "correlation_heatmap" in str(chart_types_present).lower():
        summary.append(
            "[AI prompt for Correlation Heatmap]\n"
            "This correlation matrix heatmap shows pairwise correlation coefficients between multiple measurement variables across the three analytical methods:\n"
            "- **FACS**: Flow cytometry measurements\n"
            "- **AI**: AI-based image analysis (this project's automated method)\n"
            "- **Amplicon**: PCR amplicon sequencing\n\n"
            "The heatmap may include metrics such as:\n"
            "- Editing efficiency percentages from each method\n"
            "- Cell count or fluorescence intensity measurements\n"
            "- Other quantitative parameters\n\n"
            "Analysis focus:\n"
            "1. **Method concordance**: High correlation (close to +1) between FACS/AI/Amplicon measurements indicates consistent method performance\n"
            "2. **AI validation**: Strong correlation between AI-derived metrics and traditional methods validates the automated approach\n"
            "3. **Cross-metric relationships**: Identify which parameters are interdependent vs independent\n"
            "4. **Method independence**: If certain metrics show low correlation across methods, discuss potential reasons (technical differences, measurement principles)\n\n"
            "Interpret results focusing on the reliability and accuracy of the AI-based automated analysis system compared to established methods."
        )

    # 最终组合
    return "\n\n".join(summary)


def generate_chart_insight(api_key, data_summary, base_url=None, model=None, chart_item=None, lang='zh'):
    """
    针对单一图表类型生成简明的AI解读（要点+风险+建议），支持多模态模型附图。
    返回：流式响应对象（成功）或 None（失败）
    """
    if not api_key:
        st.error(_t(lang, "未配置有效的 OpenAI API Key。", "No valid OpenAI API Key configured."))
        return None
    if not chart_item or not isinstance(chart_item, dict):
        st.error(_t(lang, "未提供用于逐图解读的图表条目。", "No chart item provided for per-chart interpretation."))
        return None

    # 初始化客户端
    try:
        if base_url:
            client = OpenAI(api_key=api_key, base_url=base_url)
        else:
            client = OpenAI(api_key=api_key)
    except Exception as e:
        st.error(_t(lang, f"初始化 OpenAI 客户端失败: {e}", f"Failed to initialize OpenAI client: {e}"))
        return None

    model_name = model or "gpt-3.5-turbo"

    def model_supports_vision(name: str) -> bool:
        n = (name or "").lower()
        return ("gpt-4o" in n) or ("vision" in n) or ("omni" in n) or ("deepseek-vl" in n)

    def to_data_uri(path: str, ext: str) -> str:
        mime = "image/png" if ext == ".png" else "image/jpeg"
        with open(path, "rb") as f:
            b64 = base64.b64encode(f.read()).decode("utf-8")
        return f"data:{mime};base64,{b64}"

    # 清洗类别名
    category = chart_item.get("category", "Chart").replace('_Plot', '').replace('_', ' ')
    image_path = chart_item.get("path")
    ext = (chart_item.get("ext") or "").lower()

    # 根据语言设置生成system prompt
    if lang == 'en':
        system_prompt = (
            "You are a senior expert in biological imaging and gene editing evaluation. Please output in English, keeping it concise and point-based."
        )
    else:
        system_prompt = (
            "你是一名资深生物影像与基因编辑评估专家。请以中文输出，保持简洁、要点化。"
        )

    # 根据语言设置生成user prompt
    if lang == 'en':
        user_prompt = f"""
    Please interpret only the following chart type, do not output an overall report:
    - Chart Type: {category}

    Background (for reference):
    {data_summary}

    IMPORTANT: The data summary above includes information about ALL charts generated in this category, not just the single preview image shown. Your analysis should consider the comprehensive data from all samples/conditions represented across all charts in this category.

    Output requirements (approximately 180-260 words):
    1) Key observation points (3-5 items) — each must cite at least one numeric metric (percentages, counts, intensity values) pulled from the summary;
    2) Potential biases/limitations (2 items) — quantify their magnitude whenever possible and reference specific subgroups affected;
    3) Recommendations/next steps (2-3 items) — align suggested actions with the quantified findings (e.g., focus on high double-positive cohorts, replicate low performers).
    Mention concrete contrasts between high and low performers whenever rankings or extremes are available. If you cannot see the image, make inferences based on the chart type and comprehensive data summary, and note uncertainties explicitly.
    """
    else:
        user_prompt = f"""
    现在请仅针对下列图表类型进行解读，不要输出整体报告：
    - 图表类型：{category}

    背景（供参考）：
    {data_summary}

    重要提示：上述数据摘要包含了该类别中生成的所有图表的信息，而不仅仅是界面显示的单张预览图。您的分析应该考虑该类别中所有样本/条件的综合数据。

    输出要求（约180-260字）：
    1) 核心观察要点（3-5条）——每条必须引用至少1个具体数值（如比例、细胞数、强度等），并比较表现最好/最差的样本或组；
    2) 潜在偏差/局限（2条）——尽量量化影响范围，指出受影响的具体组别；
    3) 建议/下一步（2-3条）——结合量化结果提出针对性行动（如放大样本、重复某组、关注高双阳性群体）。
    若无法看到图片，请基于图表类型与数据摘要进行推断，并明确说明不确定性。
    """

    # 构建消息
    attach_images = model_supports_vision(model_name) and image_path
    if attach_images:
        try:
            data_uri = to_data_uri(image_path, ext)
            user_content = [
                {"type": "text", "text": user_prompt},
                {"type": "text", "text": f"Chart Type: {category} | File: {os.path.basename(image_path)}"},
                {"type": "image_url", "image_url": {"url": data_uri}},
            ]
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content},
            ]
        except Exception:
            fallback_note = "(Image failed to load; interpreting in text mode)" if lang == 'en' else "(注：图像加载失败，将按文本模式解读)"
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"{user_prompt}\n{fallback_note}"},
            ]
    else:
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]

    # 调用API（带智能重试）
    max_retries = 3
    for attempt in range(max_retries):
        try:
            return client.chat.completions.create(
                model=model_name,
                messages=messages,
                temperature=0.0,
                max_tokens=400,
                stream=True,
                timeout=30,
            )
        except Exception as e:
            error_str = str(e)
            is_rate = ("429" in error_str) or ("rate_limit" in error_str.lower()) or ("rate limit" in error_str.lower())
            
            if attempt < max_retries - 1:
                if is_rate:
                    # 尝试从错误信息中解析等待时间
                    import re
                    wait_match = re.search(r'try again after (\d+) seconds?', error_str)
                    if wait_match:
                        wait = int(wait_match.group(1)) + random.uniform(1, 3)
                    else:
                        # 根据RPM限制计算等待时间
                        rpm_match = re.search(r'max RPM: (\d+)', error_str)
                        if rpm_match:
                            rpm = int(rpm_match.group(1))
                            wait = max(60 / rpm, 2) + random.uniform(1, 3)
                        else:
                            wait = 21 + random.uniform(0, 1.0)
                else:
                    wait = min(8, (2 ** attempt)) + random.uniform(0, 0.5)
                st.warning(f"生成逐图解读失败，{wait:.1f}s 后重试...")
                time.sleep(wait)
                continue
            else:
                st.error(f"生成逐图解读失败: {str(e)}")
                return None


def generate_ai_report(api_key, data_summary, base_url=None, model=None, chart_previews=None, lang='zh'):
    """
    生成整体AI分析报告（流式）。
    入参：
      - api_key: OpenAI或兼容服务的API Key
      - data_summary: 文本型数据摘要（summarize_data_for_ai 的返回值）
      - base_url: 可选，OpenAI兼容服务Base URL
      - model: 可选，模型名称（如 gpt-4o / gpt-3.5-turbo / moonshot-v1-8k 等）
      - chart_previews: 可选，代表性图表列表 [{'category': str, 'path': str, 'ext': str}, ...]
      - lang: 可选，输出语言（'zh' 或 'en'）
    返回：
      - 成功：可迭代的 stream 对象
      - 失败：None
    """
    if not api_key:
        st.error(_t(lang, "未配置有效的 OpenAI API Key。", "No valid OpenAI API Key configured."))
        return None
    if not data_summary:
        st.error(_t(lang, "未提供AI报告所需的数据摘要。", "No data summary provided for AI report."))
        return None

    # 初始化OpenAI客户端
    try:
        if base_url:
            client = OpenAI(api_key=api_key, base_url=base_url)
        else:
            client = OpenAI(api_key=api_key)
    except Exception as e:
        st.error(_t(lang, f"初始化 OpenAI 客户端失败: {e}", f"Failed to initialize OpenAI client: {e}"))
        return None

    model_name = model or "gpt-3.5-turbo"

    # 组织图表预览文案（不传图片，仅提供文件名与类型）
    preview_text = ""
    try:
        if chart_previews:
            lines = []
            for p in chart_previews:
                try:
                    cat_clean = (p.get("category", "Chart").replace('_Plot', '').replace('_', ' '))
                    fname = os.path.basename(p.get("path", ""))
                    lines.append(f"- {cat_clean}: {fname}")
                except Exception:
                    continue
            if lines:
                preview_text = "\n".join(lines)
    except Exception:
        preview_text = ""

    # 根据语言设置生成system prompt
    if lang == 'en':
        system_prompt = (
            "You are a senior expert in biostatistics and gene editing experimental analysis. Please output in English, using Markdown structured presentation, "
            "with concise, actionable, and reproducible language. Explicitly cite numeric evidence (percentages, counts, intensity values) to support every key conclusion."
        )
    else:
        system_prompt = (
            "你是一名资深生物统计与基因编辑实验分析专家。请以中文输出，使用Markdown结构化呈现,"
            "语言简洁、可操作、可复现，并为每条核心结论引用具体数值（比例、细胞数、强度等）作为证据。"
        )

    # 根据语言设置生成user prompt
    if lang == 'en':
        user_prompt = (
            "Please generate a comprehensive analysis report based on the following data summary and chart information:\n\n"
            "[Data Summary]\n"
            f"{data_summary}\n\n"
            + ("[Representative Charts]\n" + preview_text + "\n\n" if preview_text else "") +
            "IMPORTANT: The data summary above includes comprehensive information from ALL generated charts and data files across all samples and conditions, not just the representative charts listed. Your analysis should reflect patterns and insights from the complete dataset.\n\n"
            "Suggested Report Structure:\n"
            "1) Experimental Purpose & Data Overview (one sentence describing data source and key points);\n"
            "2) Key Findings (3-6 items, conclusion first then evidence) - consider patterns across all samples;\n"
            "3) Chart Highlights & Corresponding Explanations (if charts are available, name the corresponding files);\n"
            "4) Potential Biases & Limitations (2-4 items) - including sample coverage and representation;\n"
            "5) Recommendations & Next Steps (divided into short-term/medium-term, list actionable items) - based on comprehensive analysis;\n"
            "6) Appendix: Necessary notes or data gaps.\n\n"
            "Writing Requirements:\n"
            "- Reference at least three concrete numeric metrics (e.g., editing efficiency %, cell counts, intensity ratios) inside every major section;\n"
            "- Contrast top vs. low-performing samples or targets using the provided ranking blocks;\n"
            "- Interpret any variability, warnings, or anomalies surfaced in the summary, explaining likely experimental causes;\n"
            "- If certain datasets are missing, explicitly note the gap rather than offering generic statements;\n"
            "- Avoid canned disclaimers and ensure each insight ties back to the given data snapshot.\n\n"
            "Please use clear Markdown subheadings and bullet points for output."
        )
    else:
        user_prompt = (
            "请基于以下数据摘要与图表信息，生成一份完整的分析报告：\n\n"
            "[数据摘要]\n"
            f"{data_summary}\n\n"
            + ("[代表性图表]\n" + preview_text + "\n\n" if preview_text else "") +
            "重要提示：上述数据摘要包含了所有样本和条件下生成的全部图表和数据文件的综合信息，而不仅仅是列出的代表性图表。您的分析应该反映完整数据集的模式和洞察。\n\n"
            "报告结构建议：\n"
            "1) 实验目的与数据概览（一句话描述数据来源与要点）；\n"
            "2) 关键发现（3-6条，先结论后证据）- 考虑所有样本的模式；\n"
            "3) 图表亮点与对应解释（如有图表则点名对应文件）；\n"
            "4) 潜在偏差与局限（2-4条）- 包括样本覆盖范围和代表性；\n"
            "5) 建议与下一步（分短期/中期，列出可执行操作）- 基于综合分析；\n"
            "6) 附：必要的注意事项或数据缺口。\n\n"
            "写作要求：\n"
            "- 各主要小节至少引用3个以上具体数值（如编辑效率%、细胞数、强度比等）支撑结论；\n"
            "- 分析关键指标之间的相关性，并提出可能的解释；\n"
            "- 解读任何统计检验结果（如p值），并讨论其生物学意义；\n"
            "- 利用摘要中的排名或概览，比较表现最好与最弱的样本/靶点，并解释差异原因；\n"
            "- 若摘要给出波动/告警信息，请分析可能的实验因素并提出缓解思路；\n"
            "- 如果发现数据缺失或样本不足，请明确指出而非给出套话；\n"
            "- 禁止模板式免责声明，所有解读需紧扣提供的数据。\n\n"
            "输出请使用清晰的Markdown小标题与条目。"
        )

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]

    # 带智能重试的流式调用
    max_retries = 3
    for attempt in range(max_retries):
        try:
            return client.chat.completions.create(
                model=model_name,
                messages=messages,
                temperature=0.0,
                max_tokens=1800,
                stream=True,
                timeout=60,
            )
        except Exception as e:
            error_str = str(e)
            is_rate = ("429" in error_str) or ("rate_limit" in error_str.lower()) or ("rate limit" in error_str.lower())
            
            if attempt < max_retries - 1:
                if is_rate:
                    # 尝试从错误信息中解析等待时间
                    import re
                    wait_match = re.search(r'try again after (\d+) seconds?', error_str)
                    if wait_match:
                        wait = int(wait_match.group(1)) + random.uniform(1, 3)
                    else:
                        # 根据RPM限制计算等待时间
                        rpm_match = re.search(r'max RPM: (\d+)', error_str)
                        if rpm_match:
                            rpm = int(rpm_match.group(1))
                            wait = max(60 / rpm, 2) + random.uniform(1, 3)
                        else:
                            wait = 21 + random.uniform(0, 1.0)
                else:
                    wait = min(8, (2 ** attempt)) + random.uniform(0, 0.5)
                st.warning(f"生成整体报告失败，{wait:.1f}s 后重试...")
                time.sleep(wait)
                continue
            else:
                st.error(f"生成整体报告失败: {str(e)}")
                return None


def generate_screening_report(api_key, work_dir, base_url=None, model=None, custom_criteria=None):
    """
    生成筛选策略报告，专注于帮助用户快速识别高效率的编辑组。
    增强版：包含多维度分析、异常值检测、稳定性评估等。
    返回值：
      - 成功：返回一个可迭代的stream对象（供前端逐块渲染）
      - 失败：返回None
    """
    if not api_key:
        st.error(_t(st.session_state.get('language', 'zh'), "未配置有效的 OpenAI API Key。", "No valid OpenAI API Key configured."))
        return None

    # 初始化OpenAI客户端
    try:
        if base_url:
            client = OpenAI(api_key=api_key, base_url=base_url)
        else:
            client = OpenAI(api_key=api_key)
    except Exception as e:
        st.error(_t(st.session_state.get('language', 'zh'), f"初始化 OpenAI 客户端失败: {e}", f"Failed to initialize OpenAI client: {e}"))
        return None

    # 读取并分析数据
    try:
        eff_path = os.path.join(work_dir, "Chart", "Cell_Distribution_Scatter_Plot", "all_summary.csv")
        if not os.path.exists(eff_path):
            st.error("编辑效率数据文件(all_summary.csv)不存在")
            return None

        df = pd.read_csv(eff_path)
        if "Target_Efficiency (%)" not in df.columns:
            st.error("数据文件缺少编辑效率列(Target_Efficiency (%))")
            return None

        # 数据预处理
        df["TargetEfficiency"] = pd.to_numeric(df["Target_Efficiency (%)"], errors="coerce")
        df_eff = df.dropna(subset=["TargetEfficiency"]).copy()
        
        # 提取组信息
        extract_pattern = r".*?((?:[Cc]as\d+-sg\d+))[._-](\d+)-\d+$"
        extracted = df_eff["sample"].str.extract(extract_pattern, expand=True)
        if not extracted.isnull().any().any():
            df_eff["Main_Target"] = extracted[0].str.lower()
            df_eff["Replicate"] = pd.to_numeric(extracted[1], errors="coerce")
        else:
            st.warning("无法从样本名解析出组信息，将使用单样本分析模式")
            df_eff["Main_Target"] = df_eff["sample"]
            df_eff["Replicate"] = 1

        # 按组计算关键指标
        group_stats = df_eff.groupby("Main_Target").agg({
            "TargetEfficiency": ["mean", "std", "count", "min", "max", "median"]
        }).round(2)
        group_stats.columns = ["mean", "std", "count", "min", "max", "median"]
        group_stats["cv"] = (group_stats["std"] / group_stats["mean"]).round(3)
        
        # 增强分析：计算更多指标
        # 1. 稳定性评分 (基于CV和范围)
        group_stats["range_pct"] = ((group_stats["max"] - group_stats["min"]) / group_stats["mean"] * 100).round(2)
        group_stats["stability_score"] = (100 - group_stats["cv"] * 100 - group_stats["range_pct"] * 0.5).clip(0, 100).round(1)
        
        # 2. 异常值检测 (使用IQR方法)
        def detect_outliers_in_group(group_name):
            group_data = df_eff[df_eff["Main_Target"] == group_name]["TargetEfficiency"]
            if len(group_data) < 3:
                return 0
            q1, q3 = group_data.quantile([0.25, 0.75])
            iqr = q3 - q1
            lower_bound = q1 - 1.5 * iqr
            upper_bound = q3 + 1.5 * iqr
            outliers = group_data[(group_data < lower_bound) | (group_data > upper_bound)]
            return len(outliers)
        
        group_stats["outlier_count"] = [detect_outliers_in_group(idx) for idx in group_stats.index]
        
        # 3. 综合评分 (效率 + 稳定性 - 异常值惩罚)
        max_eff = group_stats["mean"].max()
        group_stats["efficiency_score"] = (group_stats["mean"] / max_eff * 100).round(1)
        group_stats["outlier_penalty"] = (group_stats["outlier_count"] * 10).clip(0, 30)
        group_stats["composite_score"] = (group_stats["efficiency_score"] * 0.6 + 
                                         group_stats["stability_score"] * 0.3 - 
                                         group_stats["outlier_penalty"] * 0.1).clip(0, 100).round(1)
        
        # 计算组级别的统计阈值
        q1 = group_stats["composite_score"].quantile(0.25)
        q3 = group_stats["composite_score"].quantile(0.75)
        iqr = q3 - q1
        
        # 获取筛选标准（支持自定义）
        if custom_criteria is None:
            custom_criteria = {}
        
        # 默认筛选标准
        criteria = {
            'high_efficiency_threshold': custom_criteria.get('high_efficiency_threshold', 70),
            'low_efficiency_threshold': custom_criteria.get('low_efficiency_threshold', 50),
            'high_cv_threshold': custom_criteria.get('high_cv_threshold', 0.20),
            'medium_cv_threshold': custom_criteria.get('medium_cv_threshold', 0.40),
            'min_replicates': custom_criteria.get('min_replicates', 3),
            'high_composite_threshold': custom_criteria.get('high_composite_threshold', q3 + 0.2 * iqr),
            'low_composite_threshold': custom_criteria.get('low_composite_threshold', q1 - 0.2 * iqr),
            'min_efficiency_baseline': custom_criteria.get('min_efficiency_baseline', group_stats["mean"].median())
        }
        
        # 增强的T1/T2/T3分级算法
        def assign_tier_enhanced(row):
            # T1: 高综合评分 + 足够重复 + 低CV + 高效率
            if (row["composite_score"] >= criteria['high_composite_threshold'] and 
                row["count"] >= criteria['min_replicates'] and 
                row["cv"] <= criteria['high_cv_threshold'] and 
                row["mean"] >= criteria['min_efficiency_baseline'] and
                row["outlier_count"] <= 1):
                return "T1"
            
            # T3: 低综合评分 或 高CV 或 多异常值
            if (row["composite_score"] <= criteria['low_composite_threshold'] or 
                row["cv"] > criteria['medium_cv_threshold'] or 
                row["outlier_count"] >= 2 or
                row["mean"] < criteria['min_efficiency_baseline'] * 0.7):
                return "T3"
            
            # T2: 其他情况
            return "T2"
            
        group_stats["tier"] = group_stats.apply(assign_tier_enhanced, axis=1)
        
        # 为每个梯队内部排序
        group_stats = group_stats.sort_values(["tier", "composite_score"], ascending=[True, False])
        
        # 生成增强的数据摘要
        t1_groups = group_stats[group_stats["tier"] == "T1"]
        t2_groups = group_stats[group_stats["tier"] == "T2"]
        t3_groups = group_stats[group_stats["tier"] == "T3"]
        
        # 识别最佳候选
        top_candidates = group_stats.nlargest(3, "composite_score")
        
        # 识别需要关注的问题组
        high_cv_groups = group_stats[group_stats["cv"] > criteria['high_cv_threshold']]
        low_replicate_groups = group_stats[group_stats["count"] < criteria['min_replicates']]
        outlier_groups = group_stats[group_stats["outlier_count"] >= 2]
        
        # 生成推荐候选列表和实验设计建议
        recommendations = {
            'priority_candidates': [],
            'backup_candidates': [],
            'experimental_design': [],
            'quality_control': []
        }
        
        # T1级推荐候选
        if len(t1_groups) > 0:
            for idx, row in t1_groups.head(5).iterrows():
                recommendations['priority_candidates'].append({
                    'group': idx,
                    'efficiency': row['mean'],
                    'stability': row['stability_score'],
                    'composite_score': row['composite_score'],
                    'reason': f"高效率({row['mean']:.1f}%) + 高稳定性(CV={row['cv']:.1f}%)"
                })
        
        # T2级备选候选
        if len(t2_groups) > 0:
            for idx, row in t2_groups.head(3).iterrows():
                recommendations['backup_candidates'].append({
                    'group': idx,
                    'efficiency': row['mean'],
                    'stability': row['stability_score'],
                    'composite_score': row['composite_score'],
                    'reason': f"中等效率({row['mean']:.1f}%) + 可接受稳定性(CV={row['cv']:.1f}%)"
                })
        
        # 实验设计建议
        recommendations['experimental_design'] = [
            f"建议验证批次大小: {min(len(recommendations['priority_candidates']) + 2, 8)}个候选",
            f"推荐重复实验数: {max(4, criteria['min_replicates'] + 1)}次",
            f"质控标准: 效率>{criteria['high_efficiency_threshold']:.0f}%, CV<{criteria['high_cv_threshold']*100:.0f}%",
            "建议同时设置阳性和阴性对照",
            "建议增加独立重复实验以评估重现性"
        ]
        
        # 质量控制建议
        if len(high_cv_groups) > 0:
            recommendations['quality_control'].append(f"注意高变异组: {', '.join(high_cv_groups.index.tolist()[:3])}")
        if len(low_replicate_groups) > 0:
            recommendations['quality_control'].append(f"增加重复数: {', '.join(low_replicate_groups.index.tolist()[:3])}")
        if len(outlier_groups) > 0:
            recommendations['quality_control'].append(f"检查异常值: {', '.join(outlier_groups.index.tolist()[:3])}")
        
        data_summary = {
            "总样本数": len(df_eff),
            "总组数": len(group_stats),
            "分级统计": {
                "T1组数": len(t1_groups),
                "T2组数": len(t2_groups), 
                "T3组数": len(t3_groups)
            },
            "效率统计": {
                "整体中位效率": f"{group_stats['mean'].median():.1f}%",
                "整体效率范围": f"{group_stats['mean'].min():.1f}%-{group_stats['mean'].max():.1f}%",
                "最高效率组": group_stats.loc[group_stats["mean"].idxmax()].to_dict(),
                "最稳定组": group_stats.loc[group_stats["stability_score"].idxmax()].to_dict()
            },
            "Top3候选": top_candidates.to_dict("index"),
            "T1组详情": t1_groups.to_dict("index"),
            "T2组详情": t2_groups.to_dict("index"),
            "T3组详情": t3_groups.to_dict("index"),
            "质量问题": {
                "高变异组": high_cv_groups.index.tolist(),
                "重复数不足组": low_replicate_groups.index.tolist(),
                "异常值较多组": outlier_groups.index.tolist()
            },
            "筛选建议": {
                "立即验证": t1_groups.index.tolist()[:3],
                "补充实验": low_replicate_groups.index.tolist(),
                "重新设计": t3_groups.index.tolist()[-3:] if len(t3_groups) >= 3 else t3_groups.index.tolist()
            },
            "推荐候选": recommendations
        }

    except Exception as e:
        st.error(f"数据分析失败: {str(e)}")
        return None

    # 系统提示词（专注于筛选决策）
    system_prompt = """你是一位经验丰富的基因编辑筛选专家，擅长从大量实验数据中快速识别最有潜力的sgRNA和编辑工具。
    你的核心任务是帮助研究人员做出关键决策："哪些编辑组合值得优先投入资源进行下游验证和优化？"
    
    你拥有以下专业能力：
    1. 多维度评估：综合考虑编辑效率、稳定性、重复性和异常值
    2. 风险评估：识别可能影响实验结果可靠性的因素
    3. 资源优化：基于数据质量和潜力给出资源分配建议
    4. 实验设计：针对数据缺陷提出改进建议
    
    分析原则：
    - 优先推荐高综合评分且数据可靠的组合
    - 明确指出需要补充实验的组合及原因
    - 识别并标记可能存在系统性问题的组合
    - 提供具体的、可执行的下一步行动建议
    - 使用清晰的优先级排序和风险分级
    """

    # 用户提示词
    user_prompt = f"""
    我刚完成了一批sgRNA/基因编辑工具的筛选实验，需要你作为专家帮我制定下一步的验证策略。
    我的目标是从这些候选中筛选出编辑效率高、稳定性好的工具进行深入研究。

    以下是增强分析的结果数据：
    ```json
    {data_summary}
    ```

    请基于多维度分析结果，输出一份专业的中文筛选策略报告：

    ## 1. 🎯 执行摘要
    - **核心发现**：用2-3句话总结最重要的筛选结果
    - **推荐候选**：直接列出Top 3最值得验证的编辑组合（基于综合评分）
    - **资源分配建议**：说明应该如何分配验证资源
    
    ## 6. 📋 可操作建议清单
    ### 优先验证候选
    - 基于推荐候选数据，列出具体的验证计划
    - 包含每个候选的关键指标和选择理由
    
    ### 实验设计要点
    - 具体的批次大小、重复数建议
    - 质控标准和对照设置
    - 时间安排和资源需求
    
    ### 质量控制检查点
    - 需要特别关注的问题组合
    - 数据质量改进措施
    - 风险缓解策略

    ## 2. 📊 分级筛选结果
    ### T1梯队 - 立即验证 ⭐⭐⭐
    - 列出所有T1组合及其关键指标（效率、稳定性评分、综合评分）
    - 说明为什么这些是最优选择
    
    ### T2梯队 - 条件验证 ⭐⭐
    - 列出T2组合及需要关注的问题
    - 说明在什么条件下可以考虑验证
    
    ### T3梯队 - 暂缓或重新设计 ⭐
    - 简要说明T3组合的主要问题
    - 是否值得重新设计或放弃

    ## 3. ⚠️ 数据质量评估
    - **异常值警告**：标注存在异常值的组合及可能原因
    - **重复性问题**：指出重复数不足的组合
    - **稳定性风险**：标注变异系数过高的组合
    - **建议补充实验**：明确哪些组合需要增加重复

    ## 4. 🚀 行动计划
    ### 短期行动（1-2周）
    - 具体列出应该立即验证的组合
    - 建议的验证实验设计要点
    
    ### 中期规划（1个月）
    - 需要补充数据的组合及实验计划
    - 可能的优化方向
    
    ### 风险缓解
    - 针对发现的问题提出具体解决方案
    - 如何提高后续实验的数据质量

    ## 5. 💡 专家建议
    - 基于当前数据给出的方法学建议
    - 如何优化sgRNA设计或实验条件
    - 预期的成功率和时间投入
    
    ## 7. 📊 导出数据摘要
    - 将推荐候选列表以表格形式呈现
    - 提供可复制的实验设计参数
    - 总结关键决策点和判断标准

    **要求**：
    - 使用专业术语但保持易懂
    - 每个建议都要有数据支撑
    - 突出重点信息（使用**粗体**）
    - 提供具体的数值和排名
    - 语言简洁、决策导向
    - 在报告末尾提供可操作的候选清单和实验参数
    """

    # 允许自定义模型
    model_name = model or "gpt-3.5-turbo"

    # 生成报告（带智能重试机制）
    max_retries = 3
    for attempt in range(max_retries):
        try:
            return client.chat.completions.create(
                model=model_name,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0.0,  # 使相同输入尽可能保持一致
                max_tokens=1500,  # 增加token限制以支持更详细的分析
                stream=True,
                timeout=45,  # 增加超时时间
            )
        except Exception as e:
            error_str = str(e)
            is_rate = ("429" in error_str) or ("rate_limit" in error_str.lower()) or ("rate limit" in error_str.lower())
            
            if attempt < max_retries - 1:
                if is_rate:
                    # 尝试从错误信息中解析等待时间
                    import re
                    wait_match = re.search(r'try again after (\d+) seconds?', error_str)
                    if wait_match:
                        wait = int(wait_match.group(1)) + random.uniform(1, 3)
                    else:
                        # 根据RPM限制计算等待时间
                        rpm_match = re.search(r'max RPM: (\d+)', error_str)
                        if rpm_match:
                            rpm = int(rpm_match.group(1))
                            wait = max(60 / rpm, 2) + random.uniform(1, 3)
                        else:
                            wait = 21 + random.uniform(0, 1.0)
                else:
                    wait = min(8, (2 ** attempt)) + random.uniform(0, 0.5)
                st.warning(f"生成整体报告失败，{wait:.1f}s 后重试...")
                time.sleep(wait)
                continue
            else:
                st.error(f"生成筛选报告失败: {str(e)}")
                return None


def generate_local_report(work_dir, lang='zh'):
    """生成本地增强版报告（以编辑效率为核心，结构化输出）"""
    try:
        # 优先使用 all_summary.csv（编辑效率）进行本地报告
        eff_path = os.path.join(work_dir, "Chart", "Cell_Distribution_Scatter_Plot", "all_summary.csv")
        if os.path.exists(eff_path):
            df = pd.read_csv(eff_path)
            if "Target_Efficiency (%)" in df.columns:
                df["TargetEfficiency"] = pd.to_numeric(df["Target_Efficiency (%)"], errors="coerce")
                df_eff = df.dropna(subset=["TargetEfficiency"]).copy()
                if len(df_eff) > 0:
                    desc = df_eff["TargetEfficiency"].describe()
                    # 稳健统计与异常值
                    q1 = df_eff["TargetEfficiency"].quantile(0.25)
                    q3 = df_eff["TargetEfficiency"].quantile(0.75)
                    iqr = q3 - q1
                    low_thr = q1 - 1.5 * iqr
                    high_thr = q3 + 1.5 * iqr
                    outliers = df_eff[(df_eff["TargetEfficiency"] < low_thr) | (df_eff["TargetEfficiency"] > high_thr)]

                    if lang == 'en':
                        report = "📊 Editing Efficiency Report (Enhanced Offline Version)\n\n"
                        report += "## 1) Summary\n"
                        report += f"- Overall Efficiency: Mean {desc.get('mean', np.nan):.2f}%; Median {desc.get('50%', np.nan):.2f}%; Range {desc.get('min', np.nan):.2f}% - {desc.get('max', np.nan):.2f}%; Std {desc.get('std', np.nan):.2f}%\n"
                        report += f"- Robust Statistics: Q1={q1:.2f}% / Q3={q3:.2f}% / IQR={iqr:.2f}%; Suspected outliers: {len(outliers)}\n\n"
                    else:
                        report = "📊 编辑效率报告（离线增强版）\n\n"
                        report += "## 1) 结论摘要\n"
                        report += f"- 总体效率：均值 {desc.get('mean', np.nan):.2f}%；中位数 {desc.get('50%', np.nan):.2f}%；范围 {desc.get('min', np.nan):.2f}% - {desc.get('max', np.nan):.2f}%；Std {desc.get('std', np.nan):.2f}%\n"
                        report += f"- 稳健统计：Q1={q1:.2f}% / Q3={q3:.2f}% / IQR={iqr:.2f}%；疑似异常值 {len(outliers)} 个\n\n"

                    # Top/Bottom 样本
                    top3 = df_eff.nlargest(3, "TargetEfficiency")[ ["sample", "TargetEfficiency"] ]
                    bottom3 = df_eff.nsmallest(3, "TargetEfficiency")[ ["sample", "TargetEfficiency"] ]
                    if len(top3) > 0:
                        if lang == 'en':
                            report += "## 2) Top Samples\n" + "\n".join([f"- {r['sample']}: {r['TargetEfficiency']:.2f}%" for _, r in top3.iterrows()]) + "\n\n"
                        else:
                            report += "## 2) Top 样本\n" + "\n".join([f"- {r['sample']}: {r['TargetEfficiency']:.2f}%" for _, r in top3.iterrows()]) + "\n\n"
                    if len(bottom3) > 0:
                        if lang == 'en':
                            report += "## 3) Bottom Samples\n" + "\n".join([f"- {r['sample']}: {r['TargetEfficiency']:.2f}%" for _, r in bottom3.iterrows()]) + "\n\n"
                        else:
                            report += "## 3) Bottom 样本\n" + "\n".join([f"- {r['sample']}: {r['TargetEfficiency']:.2f}%" for _, r in bottom3.iterrows()]) + "\n\n"

                    # 分组与一致性
                    try:
                        extract_pattern = r".*?((?:[Cc]as\d+-sg\d+))[._-](\d+)-\d+$"
                        extracted = df_eff["sample"].str.extract(extract_pattern, expand=True)
                        if not extracted.isnull().any().any():
                            df_eff["Main_Target"] = extracted[0].str.lower()
                            df_eff["Replicate"] = pd.to_numeric(extracted[1], errors="coerce")
                            means = df_eff.groupby("Main_Target")["TargetEfficiency"].mean().sort_values(ascending=False)
                            if lang == 'en':
                                report += "## 4) Group Comparison (Main_Target)\n"
                                report += "- Average Efficiency (Top 10):\n" + "\n".join([f"  - {k}: {v:.2f}%" for k, v in means.head(10).items()]) + "\n"
                                if len(means) >= 2:
                                    effect_size = float(means.iloc[0] - means.iloc[-1])
                                    report += f"- Group Difference (Best-Worst): ≈ {effect_size:.2f}%\n\n"
                            else:
                                report += "## 4) 分组比较 (Main_Target)\n"
                                report += "- 平均效率(Top  10)：\n" + "\n".join([f"  - {k}: {v:.2f}%" for k, v in means.head(10).items()]) + "\n"
                                if len(means) >= 2:
                                    effect_size = float(means.iloc[0] - means.iloc[-1])
                                    report += f"- 组间差异(最佳-最差)：≈ {effect_size:.2f}%\n\n"

                            cv_df = df_eff.groupby("Main_Target")["TargetEfficiency"].agg(['mean','std','count'])
                            cv_df["cv"] = cv_df["std"] / cv_df["mean"]
                            worst_cv = cv_df.sort_values("cv", ascending=False).head(5)
                            if len(worst_cv) > 0:
                                if lang == 'en':
                                    report += "## 5) Replicate Consistency (CV)\n" + "\n".join([f"- {idx}: CV={row['cv']:.2f} (n={int(row['count'])})" for idx, row in worst_cv.iterrows() if np.isfinite(row['cv'])]) + "\n\n"
                                else:
                                    report += "## 5) 重复一致性 (CV)\n" + "\n".join([f"- {idx}: CV={row['cv']:.2f} (n={int(row['count'])})" for idx, row in worst_cv.iterrows() if np.isfinite(row['cv'])]) + "\n\n"
                    except Exception:
                        pass

                    # 方法学与建议
                    if lang == 'en':
                        report += "## 6) Quality Control & Methodology\n"
                        report += "- Check segmentation quality, distance threshold for double-positive determination, fluorescence threshold and saturation;\n"
                        report += "- Pay attention to sample size and replicate adequacy, supplement if necessary;\n\n"

                        report += "## 7) Recommendations & Next Steps\n"
                        report += "- Improve efficiency: optimize sgRNA design, improve SNR (exposure/gain/denoising), standardize imaging parameters;\n"
                        report += "- Statistical validation: supplement significance testing/effect size assessment, increase replicates to stabilize conclusions;\n"
                        report += "- Re-examine or re-test abnormal samples;\n"
                    else:
                        report += "## 6) 质量控制与方法学\n"
                        report += "- 检查分割质量、双阳判定的距离阈值、荧光阈值与饱和；\n"
                        report += "- 关注样本量与重复数的充分性，必要时补充；\n\n"

                        report += "## 7) 建议与下一步\n"
                        report += "- 提升效率：优化sgRNA设计、提高SNR(曝光/增益/去噪)、统一成像参数；\n"
                        report += "- 统计验证：补充显著性检验/效应量评估，提升重复数以稳定结论；\n"
                        report += "- 对异常样本进行复查或复测；\n"
                    return report

        # 若没有效率文件，则退回到通用摘要
        data_summary = summarize_data_for_ai(work_dir, lang=lang)
        if not data_summary or data_summary.strip() == "":
            if lang == 'en':
                return "Please complete the preliminary analysis steps to generate data."
            else:
                return "请先完成前序分析步骤以生成数据。"

        # 通用摘要（中文化+效率导向）
        lines = data_summary.split('\n')
        if lang == 'en':
            report = "📊 Fluorescent Cell Analysis Summary\n\n"
            report += "## Data Overview\n"
        else:
            report = "📊 荧光细胞分析摘要\n\n"
            report += "## 数据概览\n"

        # 提取关键信息
        key_info = []
        keywords = ['cell', 'fluorescence', 'count', 'intensity', 'mean', 'std', 'efficiency', 'total']
        for line in lines:
            line = line.strip()
            if line and any(keyword in line.lower() for keyword in keywords):
                key_info.append(line)

        for info in key_info[:6]:
            report += f"- {info}\n"

        if lang == 'en':
            report += "\n## Key Conclusions (Focus on Editing Efficiency)\n"
            report += "- Summarize and compare Target_Efficiency(%) group differences and replicate consistency in all_summary.csv;\n"
            report += "- Annotate Top/Bottom samples and potential technical/biological causes;\n"
            report += "- Check CV between different Main_Target and replicates;\n\n"

            report += "## Next Step Recommendations\n"
            report += "- Increase replicates, optimize sgRNA design, improve SNR;\n"
            report += "- Evaluate the impact of distance threshold on overlap counting;\n"
            report += "- Re-examine or re-test abnormal samples.\n"
        else:
            report += "\n## 关键结论（聚焦编辑效率）\n"
            report += "- 汇总与比较 all_summary.csv 中 Target_Efficiency(%) 的组间差异与重复一致性；\n"
            report += "- 标注Top/Bottom样本与潜在技术/生物学原因；\n"
            report += "- 检查不同Main_Target与重复之间的CV；\n\n"

            report += "## 下一步建议\n"
            report += "- 增加重复、优化sg设计、提升SNR；\n"
            report += "- 评估距离阈值对overlap计数的影响；\n"
            report += "- 对异常样本进行复核或复测。\n"

        return report

    except Exception as e:
        return f"Error generating local report: {str(e)}"


def collect_chart_previews_by_group(work_dir: str, max_per_type: int = 1):
    """
    按实验组别收集图表，而非按图表类型分组。
    从文件名中提取实验组别信息（如cas9-sg1, cas12-sg1等）。
    返回格式：{
        "group_name": {
            "Cell_Distribution_Scatter": [{"path": str, "ext": str, "filename": str}],
            "Cell_Clustering_Scatter": [{"path": str, "ext": str, "filename": str}],
            "Simulated_Flow_Cytometry": [{"path": str, "ext": str, "filename": str}]
        },
        "summary_charts": {
            "Grouped_Bar": [{"path": str, "ext": str, "filename": str}],
            "Grouped_Box": [{"path": str, "ext": str, "filename": str}]
        }
    }
    """
    import re
    
    # 优先使用easyreporter_charts目录，如果不存在则使用Chart
    chart_dir = os.path.join(work_dir, "easyreporter_charts")
    if not os.path.exists(chart_dir):
        chart_dir = os.path.join(work_dir, "Chart")
        if not os.path.exists(chart_dir):
            return {}
    
    preferred_exts = (".png", ".jpg", ".jpeg")
    grouped_charts = {}
    summary_charts = {}
    
    # 定义图表类型映射
    chart_type_mapping = {
        "Cell_Distribution_Scatter_Plot": "Cell_Distribution_Scatter",
        "Cell_Clustering_Scatter_Plot": "Cell_Clustering_Scatter", 
        "Simulated_Flow_Cytometry_Plot": "Simulated_Flow_Cytometry",
        "Grouped_Bar_Plot": "Grouped_Bar",
        "Grouped_Box_Plot": "Grouped_Box",
        "correlation_scatter": "Correlation_Scatter",
        "correlation": "Correlation_Heatmap",
        "correlation_heatmap": "Correlation_Heatmap"
    }
    
    category_dirs = [d for d in sorted(os.listdir(chart_dir)) if os.path.isdir(os.path.join(chart_dir, d))]
    
    for cat in category_dirs:
        cat_dir = os.path.join(chart_dir, cat)
        chart_type = chart_type_mapping.get(cat, cat)
        
        # 检查是否为汇总图表（柱状图、箱线图、相关性图）
        if chart_type in ["Grouped_Bar", "Grouped_Box", "Correlation_Heatmap"]:
            if chart_type not in summary_charts:
                summary_charts[chart_type] = []
            
            # 收集汇总图表
            try:
                files = [f for f in os.listdir(cat_dir) if os.path.isfile(os.path.join(cat_dir, f))]
                files_sorted = sorted(files)
                for ext in preferred_exts:
                    for f in files_sorted:
                        if f.lower().endswith(ext):
                            file_path = os.path.join(cat_dir, f)
                            summary_charts[chart_type].append({
                                "path": file_path,
                                "ext": ext,
                                "filename": f
                            })
                            break  # 每种汇总图表只取一个
                    if summary_charts[chart_type]:
                        break
            except Exception as e:
                print(f"[DEBUG] Error scanning summary charts in {cat}: {e}")
        elif chart_type == "Correlation_Scatter":
            # 相关性散点图 - 收集所有3张图
            if chart_type not in summary_charts:
                summary_charts[chart_type] = []
            
            try:
                files = [f for f in os.listdir(cat_dir) if os.path.isfile(os.path.join(cat_dir, f))]
                files_sorted = sorted(files)
                # 收集所有PNG文件(最多3个: _01, _02, _03)
                for f in files_sorted:
                    if f.lower().endswith('.png') and len(summary_charts[chart_type]) < 3:
                        file_path = os.path.join(cat_dir, f)
                        summary_charts[chart_type].append({
                            "path": file_path,
                            "ext": ".png",
                            "filename": f
                        })
            except Exception as e:
                print(f"[DEBUG] Error scanning correlation scatter charts in {cat}: {e}")
        else:
            # 处理按组别的图表（Cell_Distribution_Scatter, Cell_Clustering_Scatter, Simulated_Flow_Cytometry）
            try:
                # 用于跟踪每个靶点已选择的图片,避免重复
                target_selected = {}  # {group_name: bool}
                
                # ★ 使用 os.walk 递归扫描所有深度的子目录（修复三层嵌套目录问题） ★
                # 目录结构示例：
                #   Cell_Distribution_Scatter_Plot/
                #     293T_Cas9_v2/                          ← 中间层（不含 -sg 标识）
                #       0606_293T_cas9-sg1_1/                ← 目标层（匹配正则）
                #         0606_293T_cas9-sg1_1-1_analysis.png
                all_subdirs = []  # [(relative_depth, dirpath, dirname)]
                for dirpath, dirnames, filenames in os.walk(cat_dir):
                    # 计算相对深度
                    rel_path = os.path.relpath(dirpath, cat_dir)
                    depth = 0 if rel_path == '.' else rel_path.count(os.sep) + 1
                    for dirname in dirnames:
                        all_subdirs.append((depth, dirpath, dirname))
                
                # 按深度排序：先处理浅层目录，再处理深层
                all_subdirs.sort(key=lambda x: x[0])
                print(f"[DEBUG] Found {len(all_subdirs)} subdirectories (recursive) in {cat}")
                
                for depth, dirpath, dirname in all_subdirs:
                    # 从目录名提取靶点信息（如 0606_293T_cas9-sg1_1 → cas9-sg1）
                    subdir_match = re.search(r'(cas\d+-sg\d+)(?:[_-]|$)', dirname.lower())
                    if not subdir_match:
                        continue  # 跳过不匹配的中间层目录（如 293T_Cas9_v2）
                    
                    group_name = subdir_match.group(1)
                    
                    # 如果这个靶点已经选过图片了,跳过
                    if group_name in target_selected:
                        continue
                    
                    if group_name not in grouped_charts:
                        grouped_charts[group_name] = {}
                    
                    if chart_type not in grouped_charts[group_name]:
                        grouped_charts[group_name][chart_type] = []
                    
                    # 扫描该子目录中的图片,只选第一个
                    subdir_path = os.path.join(dirpath, dirname)
                    try:
                        subdir_files = [f for f in os.listdir(subdir_path) if os.path.isfile(os.path.join(subdir_path, f))]
                        image_files = sorted([f for f in subdir_files if any(f.lower().endswith(ext) for ext in preferred_exts)])
                        
                        if image_files:
                            # 只选第一个图片作为代表
                            selected_file = image_files[0]
                            file_path = os.path.join(subdir_path, selected_file)
                            ext = os.path.splitext(selected_file)[1].lower()
                            
                            grouped_charts[group_name][chart_type].append({
                                "path": file_path,
                                "ext": ext,
                                "filename": selected_file,
                                "target": group_name
                            })
                            
                            target_selected[group_name] = True
                            print(f"[DEBUG] Selected {selected_file} for target '{group_name}' (depth={depth}, from {len(image_files)} images in {dirname})")
                    except Exception as e:
                        print(f"[DEBUG] Error processing subdir {dirname}: {e}")
                
                # 同时扫描顶层目录中的文件（兼容直接放在分类目录下的图片）
                files = [f for f in os.listdir(cat_dir) if os.path.isfile(os.path.join(cat_dir, f))]
                files_sorted = sorted(files)
                
                for f in files_sorted:
                    if any(f.lower().endswith(ext) for ext in preferred_exts):
                        match = re.search(r'(cas\d+-sg\d+)(?:[_-]|$)', f.lower())
                        if match:
                            group_name = match.group(1)
                            if group_name in target_selected:
                                continue
                            
                            if group_name not in grouped_charts:
                                grouped_charts[group_name] = {}
                            if chart_type not in grouped_charts[group_name]:
                                grouped_charts[group_name][chart_type] = []
                            
                            file_path = os.path.join(cat_dir, f)
                            ext = os.path.splitext(f)[1].lower()
                            
                            grouped_charts[group_name][chart_type].append({
                                "path": file_path,
                                "ext": ext,
                                "filename": f
                            })
                            target_selected[group_name] = True
                            print(f"[DEBUG] Selected {f} for target '{group_name}' from top-level directory")
                            
            except Exception as e:
                print(f"[DEBUG] Error scanning {cat} directory: {e}")
                import traceback
                traceback.print_exc()
    
    # 合并结果
    result = {}
    result.update(grouped_charts)
    if summary_charts:
        result["summary_charts"] = summary_charts
    
    # 打印收集结果统计
    print("\n[DEBUG] === Chart Collection Summary ===")
    for group_name, group_data in result.items():
        if group_name == 'summary_charts':
            print(f"[summary_charts]")
            for chart_type, charts in group_data.items():
                print(f"  {chart_type}: {len(charts)} files")
        else:
            print(f"[{group_name}]")
            for chart_type, charts in group_data.items():
                print(f"  {chart_type}: {len(charts)} files")
    print("[DEBUG] === End Summary ===\n")
    
    return result


def generate_ai_report_by_group(api_key, data_summary, base_url=None, model=None, chart_previews_by_group=None, lang='zh'):
    """
    按实验组别生成AI分析报告（流式输出）
    参数：
      - api_key: OpenAI API密钥
      - data_summary: 数据摘要文本
      - base_url: 可选，API基础地址
      - model: 可选，模型名称（如 gpt-4o / gpt-3.5-turbo / moonshot-v1-8k 等）
      - chart_previews_by_group: 可选，按组别组织的图表数据
      - lang: 可选，输出语言（'zh' 或 'en'）
    返回：
      - 成功：可迭代的 stream 对象
      - 失败：None
    """
    if not api_key:
        st.error(_t(lang, "未配置有效的 OpenAI API Key。", "No valid OpenAI API Key configured."))
        return None
    if not data_summary:
        st.error(_t(lang, "未提供AI报告所需的数据摘要。", "No data summary provided for AI report."))
        return None

    # 初始化OpenAI客户端
    try:
        if base_url:
            client = OpenAI(api_key=api_key, base_url=base_url)
        else:
            client = OpenAI(api_key=api_key)
    except Exception as e:
        st.error(_t(lang, f"初始化 OpenAI 客户端失败: {e}", f"Failed to initialize OpenAI client: {e}"))
        return None

    model_name = model or "gpt-3.5-turbo"

    # 组织按组别的图表预览文案
    preview_text = ""
    protein_groups = {}  # 按蛋白类型分组 {protein_type: [group_names]}
    
    try:
        if chart_previews_by_group:
            lines = []
            
            # 首先按蛋白类型分组（从靶点名称中提取）
            import re
            for group_name in chart_previews_by_group.keys():
                if group_name != "summary_charts":
                    # 提取蛋白类型（如 cas9, cas12）
                    match = re.search(r'(cas\d+)', group_name.lower())
                    if match:
                        cas_type = match.group(1).lower()
                        # 转换为显示名称
                        if cas_type == "cas9":
                            protein_type = "SpCas9"
                        elif cas_type == "cas12":
                            protein_type = "hfCas12Max"
                        else:
                            protein_type = match.group(1).upper()
                        
                        if protein_type not in protein_groups:
                            protein_groups[protein_type] = []
                        protein_groups[protein_type].append(group_name)
            
            # 按蛋白类型组织图表预览
            for protein_type, group_names in sorted(protein_groups.items()):
                if lang == 'en':
                    lines.append(f"\n**{protein_type} protein group:**")
                else:
                    lines.append(f"\n**{protein_type} 蛋白组:**")
                # 列出该蛋白的所有靶点及其图表
                for group_name in sorted(group_names):
                    group_charts = chart_previews_by_group.get(group_name, {})
                    for chart_type, charts in group_charts.items():
                        if charts:
                            chart_type_display = chart_type.replace('_', ' ')
                            for chart in charts:
                                fname = chart.get("filename", "")
                                lines.append(f"  - {chart_type_display}: {fname}")
            
            # 处理汇总图表
            if "summary_charts" in chart_previews_by_group:
                if lang == 'en':
                    lines.append(f"\n**Summary charts:**")
                else:
                    lines.append(f"\n**综合分析图表:**")
                for chart_type, charts in chart_previews_by_group["summary_charts"].items():
                    if charts:
                        chart_type_display = chart_type.replace('_', ' ')
                        for chart in charts:
                            fname = chart.get("filename", "")
                            lines.append(f"  - {chart_type_display}: {fname}")
            
            if lines:
                preview_text = "\n".join(lines)
    except Exception:
        preview_text = ""

    # 根据语言设置生成system prompt
    if lang == 'en':
        system_prompt = (
            "You are a senior expert in biostatistics and gene editing experimental analysis, and fluorescence microscopy imaging. "
            "You have deep expertise in:\n"
            "- Dual-fluorescence reporter systems (GFP/mCherry)\n"
            "- Cell matching algorithms based on Euclidean distance thresholds\n"
            "- Gene editing efficiency calculation and interpretation\n"
            "- Flow cytometry data analysis and quadrant gating strategies\n"
            "- Spatial cell distribution pattern recognition\n\n"
            "Please output in English using structured Markdown format. Your analysis should be:\n"
            "- **Data-driven**: Always cite specific numerical values (percentages, counts, intensities)\n"
            "- **Mechanistically informed**: Explain phenomena with biological/technical reasoning\n"
            "- **Critical**: Point out data quality issues, anomalies, or limitations\n"
            "- **Comparative**: Cross-reference information from different charts\n"
            "- **Actionable**: Provide concrete suggestions based on findings\n"
            "- **Precise**: Use accurate scientific terminology while maintaining readability\n\n"
            "Avoid vague statements like 'relatively high' - always specify exact numbers. "
            "When uncertainty exists, state it clearly with supporting evidence."
        )
    else:
        system_prompt = (
            "你是一名资深生物统计与基因编辑实验分析专家，精通荧光显微成像技术。你在以下领域具有深厚造诣：\n"
            "- 双荧光报告系统（GFP/mCherry）的原理与应用\n"
            "- 基于欧氏距离阈值的细胞匹配算法\n"
            "- 基因编辑效率的计算方法与生物学意义解读\n"
            "- 流式细胞术数据分析与象限门控策略\n"
            "- 细胞空间分布模式识别与统计分析\n\n"
            "请以中文输出，使用Markdown结构化呈现。你的分析应当：\n"
            "- **数据驱动**：必须引用具体数值（百分比、细胞数、荧光强度）\n"
            "- **机制解读**：用生物学/技术原理解释现象\n"
            "- **批判性思维**：指出数据质量问题、异常值或实验局限性\n"
            "- **关联分析**：交叉引用不同图表的信息相互印证\n"
            "- **可操作性**：基于发现提供具体的优化建议\n"
            "- **精准表达**：使用准确的科学术语，同时保持可读性\n"
            "- **命名规范**：引用蛋白和靶点时，必须使用标准格式：SpCas9（对应cas9）、hfCas12Max（对应cas12），例如'SpCas9-sg1'、'hfCas12Max-sg2'，严禁使用'cas9-sg1'、'Cas9-sg1'等其他格式\n"
            "- **荧光蛋白命名规范**：引用绿色荧光蛋白时，必须使用'GFP'（严禁使用'EGFP'），例如'GFP⁺'、'GFP⁻'、'GFP单阳性'等\n\n"
            "避免模糊表述如'较高'、'较低'——始终给出具体数字。"
            "存在不确定性时，明确说明并给出证据支持。"
        )
    
    # 根据语言设置生成user prompt
    if lang == 'en':
        # 获取蛋白类型列表（用于生成动态提示）
        # 统一格式化为 SpCas9-site1, hfCas12Max-site2 等友好名称
        def convert_to_friendly_name(name):
            """将蛋白名称转换为友好格式（cas9 -> SpCas9, cas12 -> hfCas12Max）"""
            import re
            # 尝试匹配 cas数字-sg数字 模式
            match = re.search(r'(cas\d+)[-_]?sg(\d+)', str(name), re.IGNORECASE)
            if match:
                cas_type = match.group(1).lower()  # cas9, cas12
                site_num = match.group(2)
                
                # 将内部名称转换为显示名称
                if cas_type == "cas9":
                    display_cas = "SpCas9"
                elif cas_type == "cas12":
                    display_cas = "hfCas12Max"
                else:
                    display_cas = cas_type.capitalize()
                
                return f"{display_cas}-site{site_num}"
            # 如果只是cas数字，格式化为对应的显示名称
            match = re.match(r'(cas\d+)', str(name), re.IGNORECASE)
            if match:
                cas_type = match.group(1).lower()
                if cas_type == "cas9":
                    return "SpCas9"
                elif cas_type == "cas12":
                    return "hfCas12Max"
                else:
                    return cas_type.capitalize()
            # 其他情况返回首字母大写
            return str(name).capitalize() if name else name
        
        protein_list = [convert_to_friendly_name(p) 
                       for p in (protein_groups.keys() if protein_groups else ["cas9", "cas12"])]
        protein_examples = ", ".join(protein_list) if protein_list else "SpCas9, hfCas12Max"
        
        user_prompt = (
            "Please generate a comprehensive analysis report based on the following data summary and chart information organized by protein types:\n\n"
            "[Data Summary]\n"
            f"{data_summary}\n\n"
            + ("[Charts by Protein Types]\n" + preview_text + "\n\n" if preview_text else "") +
            "【Experimental Methodology Background】\n"
            "This experiment uses a dual-fluorescence reporter system to evaluate gene editing efficiency:\n"
            "- GFP (green fluorescence): Reporter gene indicating editing events\n"
            "- mCherry (red fluorescence): Control marker\n"
            "- Cell classification criteria: Based on cell center Euclidean distance matching (15-pixel threshold)\n"
            "  * GFP: GFP-only positive cells (GFP⁺/mCherry⁻)\n"
            "  * Overlap: Double-positive cells (GFP⁺/mCherry⁺)\n"
            "  * mCherry: mCherry-only positive cells (GFP⁻/mCherry⁺)\n"
            "- Editing efficiency formula:\n"
            "  Editing Efficiency = N(GFP) / [N(GFP) + N(Overlap)] × 100%\n\n"
            "【CRITICAL - Plotting Methodology】\n"
            "**IMPORTANT: Different plots use different coordinate systems:**\n\n"
            "**1. Cell Clustering Scatter Plot:**\n"
            "- Uses TRANSFORMED spatial coordinates (CenterX, CenterY)\n"
            "- Cells are repositioned to quadrants based on their cell type:\n"
            "  * GFP cells → Upper-left quadrant (negative X, positive Y)\n"
            "  * Overlap cells → Upper-right quadrant (positive X, positive Y)\n"
            "  * mCherry cells → Lower-right quadrant (negative X, negative Y)\n"
            "- NO log transformation applied\n"
            "- This shows spatial clustering patterns, NOT fluorescence intensity relationships\n\n"
            "**2. Simulated Flow Cytometry Plot:**\n"
            "- Uses LOG10-TRANSFORMED fluorescence intensities\n"
            "- X-axis: log10(GFP average intensity), Y-axis: log10(mCherry average intensity)\n"
            "- **Missing value handling**: For single-fluorescence cells, the missing channel is filled with 1/10 of the minimum non-zero value\n"
            "- **Reference lines (dashed)**: Visual guides only, NOT classification boundaries:\n"
            "  * Vertical line: 90% of minimum GFP value in GFP⁺ category (log10-transformed)\n"
            "  * Horizontal line: 90% of minimum mCherry value in mCherry⁺ category (log10-transformed)\n"
            "  * These lines do NOT define quadrants - they are visual references for intensity thresholds\n\n"
            "【IMPORTANT ANALYSIS WARNINGS】\n"
            "❌ **DO NOT** assume Q3 (GFP⁻/mCherry⁻ quadrant) represents dead cells or background - it is typically EMPTY due to the missing value filling strategy\n"
            "❌ **DO NOT** analyze or discuss transfection efficiency - GFP⁻/mCherry⁺ cell count does NOT represent transfection efficiency\n"
            "❌ **DO NOT** over-interpret the reference dashed lines as strict classification boundaries\n"
            "❌ **DO NOT** infer or mention experimental time points, incubation times, or temporal parameters from filenames or data\n"
            "✅ **DO** focus on the actual data distribution patterns visible in the plots\n"
            "✅ **DO** cite specific cell counts and percentages from the data summary\n"
            "✅ **DO** recognize that log transformation compresses high-intensity values and expands low-intensity ranges\n"
            "✅ **DO** use standardized protein names: SpCas9, hfCas12Max (for cas9 and cas12 respectively) - NOT Cas9, cas9, Cas12, cas12, CAS9, or other variations\n"
            "✅ **CRITICAL NAMING CONVENTION**: When citing target names from data, always use the format 'SpCas9-sg1', 'hfCas12Max-sg2', etc. Never use lowercase formats like 'cas9-sg1' or 'cas12-sg2'\n"
            "✅ **CRITICAL FLUOROPHORE NAMING**: Always use 'GFP' (NOT 'EGFP') when referring to the green fluorescence reporter. Use 'GFP⁺', 'GFP⁻', 'GFP-only', etc.\n\n"
            "【STRICT REQUIREMENTS】You MUST follow this structure with detailed analysis, supporting every section with data:\n\n"
            "# Comprehensive Analysis Report: Dual-Fluorescence Reporter Gene Editing Efficiency Evaluation\n\n"
            "The first line above and every numbered heading below must be reproduced exactly. Do not rename, omit, reorder, or add top-level sections.\n\n"
            "## 1. Experimental Purpose & Data Overview\n"
            "- Experimental objectives: Compare gene editing efficiency of different Cas proteins\n"
            "- Dataset summary: Sample count, total cell count, fluorescence signal quality assessment\n"
            "- Data reliability: Cell counting accuracy, fluorescence signal intensity, background noise level\n\n"
            "## 2. Detailed Analysis by Protein Type\n"
            f"【CRITICAL】You MUST generate comprehensive and independent analysis for EACH protein type ({protein_examples}).\n"
            "Each protein's analysis MUST include the following (with specific numerical values):\n\n"
            f"### 2.1 {protein_list[0] if protein_list else 'SpCas9'} Protein Analysis\n\n"
            "#### Cell Distribution Features (Cell Distribution Scatter)\n"
            "- **Spatial distribution pattern**: Is cell distribution uniform across the field? Any edge effects or clustering zones?\n"
            "- **Cell density**: Spatial density comparison between GFP⁺ and mCherry⁺ cells\n"
            "- **Co-localization analysis**: Degree of spatial overlap between green and red fluorescent cells\n"
            "- **Data support**: Cite the matched counts from the AUTHORITATIVE per-sample summary (EGFP_only, mcherry_only, overlap, total). NEVER cite raw channel totals (e.g., '258 GFP cells / 303 mCherry cells' from segmentation) - always use the chart legend values.\n\n"
            "#### Clustering Features (Cell Clustering Scatter)\n"
            "**NOTE: This plot uses TRANSFORMED spatial coordinates (NOT log-transformed intensities). Cells are repositioned to quadrants based on their cell type.**\n"
            "**CRITICAL — Visual Area ≠ Cell Count**: Each cell type is forcibly placed in its designated quadrant (GFP→upper-left, Overlap→upper-right, mCherry→lower-right). The visual spread/area of a quadrant does NOT indicate cell count. A widely dispersed cluster may have very few cells; a compact cluster may be the most populous. ALWAYS refer to the cell count legend at the bottom of the chart for actual numbers.\n"
            "**CRITICAL — Efficiency vs. Overlap Size**: Editing Efficiency = GFP-only / (GFP-only + Overlap) x 100%. LOW efficiency (<10%) means Overlap >> GFP-only, so Overlap is the LARGEST population. HIGH efficiency (>50%) means GFP-only > Overlap. DO NOT say 'low efficiency therefore low Overlap' — the relationship is the OPPOSITE.\n"
            "- **Spatial distribution pattern**: How are the three cell types distributed in the transformed coordinate space?\n"
            "- **Cluster separation**: Degree of separation between GFP cells (upper-left quadrant), Overlap cells (upper-right quadrant), and mCherry cells (lower-right quadrant)\n"
            "- **Cell type distribution**:\n"
            "  * GFP cells: Positioned in upper-left quadrant\n"
            "  * Overlap cells: Positioned in upper-right quadrant\n"
            "  * mCherry cells: Positioned in lower-right quadrant\n"
            "- **Actual population sizes**: Read the cell count legend at the bottom. Which cell type is numerically dominant? Is this consistent with the editing efficiency?\n"
            "- **Data density**: Are cells concentrated or dispersed within each quadrant?\n"
            "- **Cluster compactness**: How tightly are cells of the same type clustered together?\n\n"
            "#### Fluorescence Phenotype & Editing Efficiency (Simulated Flow Cytometry)\n"
            "**NOTE: This is a log-transformed scatter plot, NOT true flow cytometry. Lower-left region is typically empty.**\n"
            "- **Cell population distribution** (use actual labels from the plot, base analysis on ACTUAL visible data points):\n"
            "  * GFP cells (upper-left region): GFP-only positive (GFP⁺/mCherry⁻) - CITE SPECIFIC COUNT/PERCENTAGE\n"
            "  * Overlap cells (upper-right region): Double-positive (GFP⁺/mCherry⁺) - CITE SPECIFIC COUNT/PERCENTAGE\n"
            "  * mCherry cells (lower-right region): mCherry-only positive (GFP⁻/mCherry⁺) - CITE SPECIFIC COUNT/PERCENTAGE\n"
            "  * Lower-left region: Typically EMPTY (due to missing value filling) - do not analyze\n"
            "- **Editing efficiency**: Precise value from data summary (NOT estimated from plot)\n"
            "  Editing Efficiency = N(GFP) / [N(GFP) + N(Overlap)] × 100%\n"
            "- **Editing specificity**: Ratio of GFP cells to all GFP-positive cells\n"
            "- **Intensity correlation**: Analyze fluorescence intensity characteristics and distribution patterns of the three cell types\n"
            "- **IMPORTANT**: Reference dashed lines are for visual guidance only, NOT classification boundaries\n\n"
            "#### Data Quality Assessment\n"
            "- Is cell count sufficient? (Recommend >500 cells)\n"
            "- Is fluorescence signal intensity adequate? Signal-to-noise ratio?\n"
            "- Any technical issues (e.g., cell overlap, fluorescence quenching)?\n\n"
            "#### Summary\n"
            "- Overall performance: Editing efficiency, specificity, stability\n"
            "- Comparison with expected results\n"
            "- Strengths and weaknesses\n\n"
            + (f"### 2.2 {protein_list[1]} Protein Analysis\n"
               "[Apply the same detailed analysis framework, following the structure of 2.1]\n\n"
               "[If more protein types are present, continue adding the corresponding subsections]\n\n"
               if len(protein_list) > 1 else "")
            + ("## 3. Cross-Protein Comparative Analysis\n\n"
               if len(protein_list) > 1
               else "## 3. Comparative Analysis Across Targets\n\n")
            + "### 3.1 Editing Efficiency Comparison (based on bar chart)\n"
            "- **Efficiency ranking**: List each protein's editing efficiency from high to low\n"
            "- **Significance of differences**: Are the efficiency differences statistically significant? (based on error bars or data dispersion)\n"
            "- **Efficiency fold-change**: How many times higher is the best-performing protein than the runner-up?\n"
            "- **Biological interpretation**: Why is one protein more efficient? Possible mechanisms (PAM recognition, cleavage efficiency, repair pathways, etc.)\n"
            "- **Practical recommendations**: Based on efficiency data, recommend the protein for practical applications\n\n"
            "### 3.2 Distribution Feature Comparison (based on box plot)\n"
            "- **Median comparison**: Compare median editing efficiency across proteins\n"
            "- **Dispersion analysis**:\n"
            "  * Interquartile range (IQR): Reflects data stability\n"
            "  * Outliers: Identify and explain outlying data points\n"
            "- **Replicability assessment**: Which protein's data is more stable and reproducible?\n"
            "- **Risk assessment**: Risks of proteins with high efficiency variability in practical applications\n\n"
            "### 3.3 Fluorescence Intensity Correlation (if data available)\n"
            "- Correlation between GFP and mCherry intensity (hinting at the relationship between transfection and editing)\n"
            "- Does higher fluorescence intensity correspond to higher editing efficiency?\n"
            "- Relationship between fluorescence intensity and cell state\n\n"
            "## 4. Key Findings & Conclusions\n\n"
            "### 4.1 Main Findings\n"
            "- The best-performing protein and its editing efficiency (exact values)\n"
            "- Relative strengths and weaknesses of each protein (data-driven)\n"
            "- Unexpected findings or anomalies\n\n"
            "### 4.2 Biological Significance\n"
            "- Implications of these results for gene editing research\n"
            "- Guidance for target design\n"
            "- Potential impact on clinical applications\n\n"
            "### 4.3 Methodological Validation\n"
            "- Soundness of the experimental design\n"
            "- Reliability of the data quality\n"
            "- Consistency with literature reports\n\n"
            "## 5. Limitations & Recommendations\n\n"
            "### 5.1 Limitations of the Current Study\n"
            "- Is the sample size sufficient?\n"
            "- Are the experimental conditions comprehensive (e.g., any missing controls)?\n"
            "- Technical limitations (e.g., fluorescence detection sensitivity, cell segmentation accuracy)\n\n"
            "### 5.2 Recommendations for Follow-up Experiments\n"
            "- Additional experiments needed (e.g., more replicates, testing more sgRNAs)\n"
            "- Optimizable steps (e.g., optimizing cell culture conditions, improving fluorescence signal strength, refining the workflow)\n"
            "- Future research directions (e.g., mechanistic exploration, off-target analysis)\n\n"
            "[Analysis Requirements]\n"
            "- **Must cite exact values**: Do not say only 'high' or 'low'; always give the specific number\n"
            "- **In-depth interpretation**: Not only describe phenomena, but also explain causes and significance\n"
            "- **Data linkage**: Cross-validate information from different charts\n"
            "- **Professional terminology**: Use accurate scientific terms while maintaining readability\n"
            "- **Critical thinking**: Point out deficiencies or contradictions in the data\n"
            "- **No file names**: Use chart type names, do not mention specific file names\n"
            "- **Avoid over-speculation**: Base conclusions on data, do not over-interpret\n"
            "- **Formatting stability**: Every heading must be followed by substantive content; never output an empty section.\n"
            "- **No LaTeX**: Do not use $, $$, \\frac, \\text, or other LaTeX syntax. Write formulas as plain text, for example: Target Efficiency = GFP-only / (GFP-only + Overlap) × 100%.\n"
            "- **Line separation**: Put each labeled observation on its own Markdown bullet or paragraph. Never concatenate multiple bold labels into one paragraph.\n"
            "- **No separators**: Do not output standalone Markdown separator lines such as ---.\n"
        )
    else:
        # 生成中文用户提示词（与英文分支结构保持一致）
        def convert_to_friendly_name(name):
            """将蛋白名称转换为友好格式"""
            import re
            # 尝试匹配 cas数字-sg数字 模式
            match = re.search(r'(cas\d+)[-_]?sg(\d+)', str(name), re.IGNORECASE)
            if match:
                cas_type = match.group(1).lower()
                site_num = match.group(2)
                # 使用自定义名称映射
                if cas_type == "cas9":
                    protein_name = "SpCas9"
                elif cas_type == "cas12":
                    protein_name = "hfCas12Max"
                else:
                    protein_name = match.group(1).capitalize()
                return f"{protein_name}-sg{site_num}"
            # 如果只是cas数字，格式化为自定义名称
            match = re.match(r'(cas\d+)', str(name), re.IGNORECASE)
            if match:
                cas_type = match.group(1).lower()
                if cas_type == "cas9":
                    return "SpCas9"
                elif cas_type == "cas12":
                    return "hfCas12Max"
                else:
                    return match.group(1).capitalize()
            # 其他情况返回首字母大写
            return str(name).capitalize() if name else name

        protein_list = [convert_to_friendly_name(p) for p in (protein_groups.keys() if protein_groups else ["cas9", "cas12"])]
        protein_examples = ", ".join(protein_list) if protein_list else "SpCas9, hfCas12Max"

        user_prompt = (
            "请基于下述数据摘要和按蛋白类型组织的图表信息，生成一份结构化的中文分析报告：\n\n"
            "[数据摘要]\n"
            f"{data_summary}\n\n"
            + ("[按蛋白分类的图表]\n" + preview_text + "\n\n" if preview_text else "")
            + "实验方法背景：\n"
            + "本实验采用双荧光报告系统评估基因编辑效率（GFP 绿色荧光为报告基因，mCherry 红色荧光为对照标记）：\n"
            + "- 细胞分类标准：基于细胞中心欧氏距离匹配（15 像素阈值）\n"
            + "  * GFP：仅 GFP 阳性细胞（GFP⁺/mCherry⁻）\n"
            + "  * Overlap：双阳性细胞（GFP⁺/mCherry⁺）\n"
            + "  * mCherry：仅 mCherry 阳性细胞（GFP⁻/mCherry⁺）\n"
            + "- 编辑效率公式：编辑效率 = N(GFP) / [N(GFP) + N(Overlap)] × 100%\n\n"
            + "【严格输出要求】必须严格按以下结构输出，每个标题必须原样复制，不得改名、删除、调换或新增章节，且每个标题下必须有实质内容（引用具体数值）：\n\n"
            + "# 综合分析报告：双荧光报告基因编辑效率评估\n\n"
            + "## 1. 实验目的与数据概览\n"
            + "- 实验目标：比较不同 Cas 蛋白的基因编辑效率\n"
            + "- 数据集摘要：样本数、总细胞数、荧光信号质量评估\n"
            + "- 数据可靠性：细胞计数准确性、荧光信号强度、背景噪声水平\n\n"
            + "## 2. 按蛋白类型的详细分析\n"
            + f"【关键】必须为每种蛋白（{protein_examples}）生成独立且全面的分析，引用具体数值：\n\n"
            + f"### 2.1 {protein_list[0] if protein_list else 'SpCas9'} 蛋白分析\n\n"
            + "#### 细胞分布特征（细胞分布散点图）\n"
            + "- **空间分布模式**：细胞在视野中分布是否均匀？有无边缘效应或聚集区域？\n"
            + "- **细胞密度**：GFP⁺ 与 mCherry⁺ 细胞的空间密度比较\n"
            + "- **共定位分析**：绿色与红色荧光细胞的空间重叠程度\n"
            + "- **数据支撑**：引用每个样本匹配后的权威计数（GFP-only、mCherry-only、Overlap、总数），严禁引用分割的原始通道计数。\n\n"
            + "#### 聚类特征（细胞聚类散点图）\n"
            + "**注意：该图使用变换后的空间坐标（非对数强度）。各细胞类型被强制置于指定象限（GFP→左上，Overlap→右上，mCherry→右下），象限面积不代表细胞数量，请以图例计数为准。**\n"
            + "- **空间分布模式**：三种细胞类型在变换坐标空间中的分布\n"
            + "- **簇分离度**：三类细胞象限间的分离程度\n"
            + "- **实际数量**：以图例计数为准，哪类细胞数量占优？是否与编辑效率一致？\n"
            + "- **簇紧密度**：同类细胞聚集的紧密程度\n\n"
            + "#### 荧光表型与编辑效率（模拟流式细胞术图）\n"
            + "**注意：这是对数变换散点图（X 轴 log10(GFP 平均强度)，Y 轴 log10(mCherry 平均强度)），左下区域通常为空。参考虚线仅为视觉指引，不是分类边界。**\n"
            + "- **细胞群分布**：GFP（左上）、Overlap（右上）、mCherry（右下）各自的数量与比例（引用具体数值）\n"
            + "- **编辑效率**：引用数据摘要中的精确值（编辑效率 = N(GFP) / [N(GFP) + N(Overlap)] × 100%）\n"
            + "- **强度相关性**：三类细胞的荧光强度特征与分布模式\n\n"
            + "#### 数据质量评估\n"
            + "- 细胞数是否充足（建议 >500 个）？荧光信号信噪比如何？有无技术问题（细胞重叠、荧光淬灭）？\n\n"
            + "#### 小结\n"
            + "- 总体表现：编辑效率、特异性、稳定性\n\n"
            + (f"### 2.2 {protein_list[1]} 蛋白分析\n"
               + "[按 2.1 的相同框架进行分析，必须原样包含相同的四个 #### 小节标题：细胞分布特征（细胞分布散点图）、聚类特征（细胞聚类散点图）、荧光表型与编辑效率（模拟流式细胞术图）、数据质量评估、小结]\n"
               + "[若有更多蛋白类型，继续添加相应小节]\n\n"
               if len(protein_list) > 1 else "")
            + ("## 3. 跨蛋白综合对比分析\n\n"
               if len(protein_list) > 1
               else "## 3. 靶点间综合对比分析\n\n")
            + "### 3.1 编辑效率对比（基于柱状图）\n"
            + "- **效率排序**：从高到低列出各蛋白的编辑效率\n"
            + "- **差异显著性**：结合误差棒或数据离散度判断差异是否显著\n"
            + "- **倍数关系**：最优蛋白比次优蛋白高多少倍\n"
            + "- **生物学解释**：可能的机制（PAM 识别、切割效率、修复通路等）\n"
            + "- **实用建议**：基于效率数据推荐实际应用方案\n\n"
            + "### 3.2 分布特征对比（基于箱线图）\n"
            + "- **中位数比较**：比较各蛋白编辑效率的中位数\n"
            + "- **离散度分析**：四分位距（IQR）与离群值\n"
            + "- **可重复性评估**：哪组数据更稳定\n"
            + "- **风险提示**：效率变异大的蛋白在实际应用中的风险\n\n"
            + "### 3.3 荧光强度相关性（方法学验证）\n"
            + "- GFP 与 mCherry 强度的相关性\n"
            + "- 荧光强度越高是否编辑效率越高？\n\n"
            + "### 3.4 相关性分析（相关性热图）\n"
            + "- 各指标间的相关性矩阵解读\n\n"
            + "## 4. 关键发现与结论\n\n"
            + "### 4.1 主要发现\n"
            + "- 表现最佳的蛋白及其精确编辑效率\n"
            + "- 各蛋白的相对优劣（数据驱动）\n"
            + "- 意外发现或异常\n\n"
            + "### 4.2 生物学意义\n"
            + "- 对基因编辑研究的启示、靶点设计指导、潜在应用影响\n\n"
            + "### 4.3 方法学验证\n"
            + "- 实验设计合理性、数据质量可靠性、与文献的一致性\n\n"
            + "## 5. 局限性与建议\n\n"
            + "### 5.1 当前研究的局限性\n"
            + "- 样本量是否足够？实验条件是否全面？技术局限（荧光检测灵敏度、分割精度等）\n\n"
            + "### 5.2 后续实验建议\n"
            + "- 需要补充的实验（更多重复、更多 sgRNA）\n"
            + "- 可优化的环节（培养条件、信号增强、流程改进）\n"
            + "- 未来研究方向（机制探索、脱靶分析）\n\n"
            + "[分析要求]\n"
            + "- **必须引用精确数值**：不得只说“较高”“较低”，始终给出具体数字\n"
            + "- **深入解读**：不仅描述现象，还要解释原因与意义\n"
            + "- **数据联动**：交叉印证不同图表的信息\n"
            + "- **专业术语**：使用准确科学术语，同时保持可读性\n"
            + "- **批判性思维**：指出数据不足或矛盾\n"
            + "- **不提文件名**：使用图表类型名称\n"
            + "- **避免过度推断**：结论以数据为依据\n"
            + "- **格式稳定**：每个标题下必须有实质内容，禁止输出空章节\n"
            + "- **禁止 LaTeX**：公式写成普通文本，例如：靶向效率 = GFP单阳性 / (GFP单阳性 + Overlap) × 100%\n"
            + "- **每个加粗要点单独一行**：不得把多个加粗标签连在同一段\n"
            + "- **禁止输出 --- 等独立 Markdown 分隔线**\n"
        )

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]

    # 带智能重试的流式调用
    max_retries = 3
    for attempt in range(max_retries):
        try:
            return client.chat.completions.create(
                model=model_name,
                messages=messages,
                temperature=0.0,
                max_tokens=6000,  # 增加token数量以支持更详细的分组分析（每组~1500 tokens + 综合分析~1500 tokens）
                stream=True,
                timeout=60,
            )
        except Exception as e:
            error_str = str(e)
            is_rate = ("429" in error_str) or ("rate_limit" in error_str.lower()) or ("rate limit" in error_str.lower())
            
            if attempt < max_retries - 1:
                if is_rate:
                    # 尝试从错误信息中解析等待时间
                    import re
                    wait_match = re.search(r'try again after (\d+) seconds?', error_str)
                    if wait_match:
                        wait = int(wait_match.group(1)) + random.uniform(1, 3)
                    else:
                        # 根据RPM限制计算等待时间
                        rpm_match = re.search(r'max RPM: (\d+)', error_str)
                        if rpm_match:
                            rpm = int(rpm_match.group(1))
                            wait = max(60 / rpm, 2) + random.uniform(1, 3)
                        else:
                            wait = 21 + random.uniform(0, 1.0)
                else:
                    wait = min(8, (2 ** attempt)) + random.uniform(0, 0.5)
                st.warning(f"生成分组报告失败，{wait:.1f}s 后重试...")
                time.sleep(wait)
                continue
            else:
                st.error(f"生成分组报告失败: {str(e)}")
                return None
