#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
EasyReporter Streamlit Web应用
生物信息学荧光细胞分析工具的图形界面
"""
import base64
import hashlib
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import zipfile
from datetime import datetime
from pathlib import Path

import streamlit as st

# --- AI/OpenAI 可选化处理开始 ---
AI_AVAILABLE = True
OPENAI_AVAILABLE = True
try:
    import openai  # noqa: F401
except Exception:
    OPENAI_AVAILABLE = False

sys.path.append('Code')
try:
    from AI_helper import (
        get_openai_key,
        summarize_data_for_ai,
        generate_ai_report,
        generate_local_report,
        collect_chart_previews,
        collect_chart_previews_by_group,
        generate_ai_report_by_group,
        generate_chart_insight,
        collect_chart_previews_original,
    )
    AI_AVAILABLE = True
except Exception as e:  # AI_helper 不存在或导入失败
    AI_AVAILABLE = False
    print(f"AI_helper导入失败: {e}")

    def get_openai_key(*_, **__):
        return None

    def summarize_data_for_ai(*_, **__):
        return ""

    def generate_ai_report(*_, **__):
        return None

    def generate_local_report(*_, **__):
        return "(AI 模块缺失，无法生成本地报告)"

    def collect_chart_previews(work_dir=None, max_per_type=1):
        return []

    def collect_chart_previews_by_group(work_dir=None, max_per_type=1):
        return {}

    def generate_ai_report_by_group(*_, **__):
        return None

    def generate_chart_insight(*_, **__):
        return None

    def collect_chart_previews_original(work_dir=None, max_per_type=1):
        return []
# --- AI/OpenAI 可选化处理结束 ---
# --- AI 输出净化：移除模板化免责声明 ---
if 'st' not in globals():  # 防止某些环境未正确导入 streamlit
    import streamlit as st
def sanitize_ai_output(text: str) -> str:
    """
    移除常见模板化免责声明或空泛提示，保留具体信息。
    - 过滤以“注：”“注意：”“免责声明：”“Note:” "Disclaimer:” 等开头的整行
    - 过滤包含“作为AI模型”“仅供参考”“可能不准确”等通用句式的整行
    - 合并多余空行
    """
    try:
        if not isinstance(text, str):
            return text
        import re
        patterns = [
            r'^\s*(注|注意|免责声明)[:：].*$',
            r'^\s*仅供参考[。\.]?.*$',
            r'^\s*不构成(建议|结论)[。\.]?.*$',
            r'^\s*作为(一个)?AI(模型)?[，,].*$',
            r'^\s*请注意[：:].*$',
            r'^\s*Note[:：].*$',
            r'^\s*Disclaimer[:：].*$',
            r'.*本内容(仅供|只供)学习(与交流)?(使用)?(，|,).*$',
            r'.*may be inaccurate.*',
            r'.*for reference only.*',
            # 新增：过滤特定的数据推断免责声明
            r'.*注[:：]?基于数据摘要推断图表特征[，,]?实际图像细节可能存在差异.*',
            r'.*注[:：]?分析基于数据摘要推断[，,]?未直接观察图表分布形态.*',
            r'.*基于数据摘要推断.*实际图像细节可能存在差异.*',
            r'.*分析基于数据摘要推断.*未直接观察图表分布形态.*',
            r'.*若无法看到图片.*请基于图表类型.*进行推断.*',
            r'.*标注不确定性.*',
            r'.*\(注[:：]?.*推断.*\).*',
            r'.*（注[:：]?.*推断.*）.*',
        ]
        compiled = [re.compile(p, re.IGNORECASE) for p in patterns]
        lines = text.splitlines()
        cleaned = []
        for line in lines:
            if any(c.match(line) for c in compiled):
                continue
            cleaned.append(line)
        out = '\n'.join(cleaned)
        out = re.sub(r'\n{3,}', '\n\n', out)
        return out.strip()
    except Exception:
        return text

# === i18n: 语言配置与翻译字典 ===
TRANSLATIONS = {
    "zh": {
        "app_title": "🔬 EasyReporter - 荧光细胞分析工具",
        "step1_title": "📤 步骤 1: 数据处理",
        "step2_title": "📊 步骤 2: 生成图表",
        "step3_title": "📥 步骤 3: 下载结果",
        "step4_title": "🤖 步骤 4: AI 解读",
        "step1_desc": "上传图像 → Cellpose分割 → 荧光强度分析",
        "step2_desc": "选择图表类型 → 配置参数 → 生成可视化图表",
        "step3_desc": "下载图表和数据文件",
        "step4_desc": "输入API密钥 → 生成报告",
        "upload_images": "1.1 上传荧光图像",
        "input_mode": "选择输入方式",
        "upload_tiff": "上传TIFF文件",
        "upload_zip": "上传ZIP压缩包",
        "select_folder": "选择本地目录",
        "step1_config_params_title": "1.2 配置处理参数",
        "cellpose_execution_mode_title": "Cellpose 运行方式",
        "select_cellpose_execution_mode": "选择 Cellpose 运行方式",
        "python_mode_label": "🐍 Python（推荐）",
        "apptainer_mode_label": "📦 Apptainer 容器",
        "select_cellpose_run_help": "选择 Cellpose 的运行方式",
        "cellpose_params_title": "Cellpose 参数",
        "apptainer_image_path_label": "Apptainer 镜像路径",
        "apptainer_image_path_help": "Cellpose 容器镜像文件路径",
        "python_mode_info": "Python 模式将直接使用本地安装的 Cellpose",
        "use_gpu_label": "使用GPU加速",
        "use_gpu_help": "如果 GPU 可用，启用以加快处理速度",
        "pretrained_model_label": "预训练模型",
        "pretrained_model_help": "请选择最适合您数据的 Cellpose 预训练模型",
        "fluorescence_params_title": "荧光分析参数",
        "matching_distance_threshold_label": "细胞匹配距离阈值（像素）",
        "matching_distance_threshold_help": "用于匹配 GFP 与 mCherry 细胞的距离阈值",
        "step1_start_processing_title": "1.3 开始处理",
        "start_data_processing_button": "🚀 开始数据处理",
        "please_upload_images_error": "请先上传图像文件或从文件夹导入",
        "zip_info": "上传一个包含 TIFF/TIF 图像的ZIP压缩包（最大支持5GB）；系统会将其中的图像解压到工作目录 Data 中进行处理",
        "select_tiff_label": "选择 TIFF 图像文件（支持 GFP 与 mCherry 通道）",
        "uploader_help": "请上传成对的 GFP 与 mCherry 图像，示例：sample_EGFP-1.tif, sample_mcherry-1.tif",
        "upload_zip_label": "上传包含 TIFF/TIF 图像的 ZIP 压缩包",
        "folder_info": "选择一个包含 TIFF/TIF 图像的本地文件夹；系统会将其复制到工作目录 Data 中进行处理",
        "local_dir_path": "本地目录路径",
        "include_subdirs": "包含子目录",
        "clear_target": "导入前清空目标目录(Data)",
        "clear_target_zip": "解压前清空目标目录(Data)",
        "save_files": "💾 保存上传的文件",
        "extract_zip": "📦 解压ZIP到输入目录",
        "import_from_dir": "📥 从该目录导入图像",
        "processing_log": "📋 处理日志",
        "uploaded_successfully": "成功上传了 {} 个文件",
        "view_files": "查看上传的文件",
        "select_zip_first": "请先选择一个ZIP文件",
            "imported_files": "已从ZIP导入 {} 个图像文件",
            "view_imported": "查看已导入文件",
            "no_tiff_found": "ZIP中未找到任何 TIFF/TIF 文件",
            "local_dir_placeholder": "例如：D:\\data\\experiment_01",
            "enter_dir_path": "请输入本地目录路径",
            "not_valid_dir": "该路径不是有效的本地目录",
            "copy_failed": "复制失败：{} -> {} ({})",
            "imported_from_dir": "已从目录导入 {} 个图像文件",
            "no_tiff_found_dir": "未在该目录中找到任何 TIFF/TIF 文件",
            "skipped_unsafe_path": "已跳过潜在不安全路径：{}",
            "extract_failed_entry": "解压失败：{} -> {} ({})",
            "zip_extract_error": "解压ZIP时出错：{}",
            "input_data_dir": "输入数据目录：{}",
            "switch_language_help": "切换语言",
        "switch_to_en": "切换为英文",
        "switch_to_zh": "切换为中文",
        "project_management": "📁 项目管理",
        "current_project": "📌 当前项目",
        "no_project_selected": "未选择",
        "project_action": "选择操作",
        "continue_current": "继续当前项目",
        "open_existing": "打开已有项目",
        "create_new": "创建新项目",
        "select_project": "选择项目",
        "open_project_btn": "📂 打开项目",
        "new_project_name": "新项目名称",
        "project_name_placeholder": "例如: Experiment_2024",
        "create_project_btn": "✨ 创建项目",
        "project_switched": "已切换到项目: {}",
        "project_created": "已创建新项目: {}",
        "invalid_project_name": "项目名称只能包含字母、数字、下划线和连字符",
        "enter_valid_name": "请输入有效的项目名称",
        "step4_header": "🤖 步骤 4: AI 解读",
        "step4_info": "该功能将调用大语言模型(LLM)对实验结果进行自动化分析并生成报告。若模型支持多模态，将附带代表性图像进行逐图解读。",
        "config_provider_api": "4.1 配置服务与密钥",
        "select_provider": "选择服务提供商",
        "provider_help": "支持 OpenAI 或兼容 OpenAI 协议的服务（例如 Kimi/Moonshot、DeepSeek）。",
        "base_url_label": "基础地址",
        "base_url_help": "OpenAI: https://api.openai.com/v1；Kimi: https://api.moonshot.cn/v1；DeepSeek: https://api.deepseek.com/v1",
        "model_name_label": "模型名称",
        "model_name_help": "例如 OpenAI: gpt-4o 或 gpt-3.5-turbo；Kimi: moonshot-v1-8k；DeepSeek: deepseek-chat 或 deepseek-vl-7b-chat（支持视觉）",
        "enter_openai_key": "请输入 OpenAI API Key",
        "enter_kimi_key": "请输入 Kimi API Key",
        "enter_deepseek_key": "DeepSeek API Key（已固定配置）",
        "api_key_help_openai": "API Key 仅用于本次会话，不会被保存。",
        "api_key_help_kimi": "API Key 仅用于本次会话，不会被保存；请确保已在 Moonshot 控制台创建。",
        "api_key_help_deepseek": "API密钥已固定为DeepSeek，无需重复输入",
        "api_key_fixed_success": "✅ DeepSeek API密钥已固定配置，可直接使用AI功能",
        "generate_analysis_report": "4.2 生成分析报告",
        "btn_generate_ai_report": "✨ 生成AI报告",
        "btn_launch_ai_screening": "🚀 启动AI筛选助手",
        "retry_ai_analysis": "🔄 重试AI分析",
        "use_local_report": "📊 使用简化本地报告",
        "ai_analysis_report": "4.3 AI分析报告",
        "btn_download_report": "📋 下载报告",
        "generating_report": "正在生成报告，请稍候...",
        "no_data_for_ai": "未找到可用于AI解读的数据，请先完成数据处理与图表生成。",
        "no_valid_content_generated": "未生成有效内容，请重试或使用简化报告。",
        "screening_spinner": "AI筛选助手正在分析数据...",
        "screening_success": "AI筛选助手已成功生成报告！",
            "screening_failed": "AI筛选助手未能生成有效报告。",
            "screening_no_response": "未从AI模型获得有效响应。",
            "screening_error": "运行AI筛选助手时发生错误: {}",
            "download_html_report": "📄 下载HTML报告",
            "download_pdf_report": "📑 下载PDF报告",
            "pdf_generation_failed": "PDF生成失败，请使用HTML版本",
            "pdf_generation_error": "PDF生成失败: {}",
            "use_html_version": "请使用HTML版本下载报告",
            "step2_header": "📊 步骤 2: 图表生成",
            "step2_congratulations": "🎉 恭喜！您现在可以生成各种类型的图表。请选择您需要的图表类型：",
            "select_chart_type": "2.1 选择图表类型",
            "configure_chart_params": "2.2 配置图表参数",
            "color_config": "🎨 颜色配置",
            "general_color_settings": "通用颜色设置",
            "general_color_info": "以下颜色设置将应用于除柱状图和箱线图之外的所有图表类型",
            "color1_egfp": "颜色1 (GFP)",
            "color2_mcherry": "颜色2 (mCherry)",
            "color3_overlap": "颜色 3 (重叠区域)",
            "bar_box_color_settings": "柱状图和箱线图颜色设置",
            "bar_box_color_info": "以下颜色设置将应用于柱状图和箱线图",
            "data_groups_count": "数据组数（颜色数量）",
            "data_groups_help": "根据您的数据组数选择需要的颜色数量",
            "size_config": "📏 图片尺寸参数配置",
            "chart_size_settings": "各图表类型尺寸设置",
            "chart_width": "图表宽度",
            "chart_height": "图表高度",
            "other_params_config": "⚙️ 其他参数配置",
            "distance_threshold": "匹配距离阈值",
            "generate_charts_section": "2.3 生成图表",
            "generate_selected_charts": "🎨 生成选中的图表",
            "chart_cell_distribution": "细胞分布散点图",
            "chart_cell_distribution_desc": "显示GFP和mCherry细胞的空间分布",
            "chart_targeting_efficiency": "靶向效率柱状图",
            "chart_targeting_efficiency_desc": "显示不同组别的靶向效率统计",
            "chart_cell_box": "细胞箱线图",
            "chart_cell_box_desc": "显示细胞数据分布和统计特征",
            "chart_cell_clustering": "细胞聚类散点图",
            "chart_cell_clustering_desc": "按细胞类型显示聚类分布",
            "chart_flow_cytometry": "模拟流式细胞术图",
            "chart_flow_cytometry_desc": "模拟流式细胞术的散点图表示",
            
            "correlation_section_title": "2.4 相关性热图（皮尔逊r）",
            "correlation_section_desc": "自动扫描 correlation/data 下的表格文件（CSV/TSV/Excel），批量生成 皮尔逊相关系数(r) 热图到 correlation/output。",
            "correlation_data_dir": "数据目录：{}",
            "correlation_upload_files": "上传相关性数据表（CSV/TSV/XLSX/XLS）",
            "correlation_clear_before": "保存前清空数据目录(correlation/data)",
            "correlation_generate_btn": "✨ 生成相关性热图（皮尔逊r）",
            "correlation_running": "正在生成相关性热图，请稍候...",
            "correlation_run_success": "✅ 相关性热图生成完成！",
            "correlation_run_failed": "❌ 相关性热图生成失败：{}",
            "correlation_no_files": "未在数据目录中找到可用的表格文件。",
            "correlation_generated_files_count": "本次生成了 {} 个输出文件",
            "correlation_preview_title": "预览生成的文件（前10个）",
            
            # 相关性散点图
            "scatter_section_title": "2.5 相关性散点图（线性回归）",
            "scatter_section_desc": "上传CSV数据，生成两两变量间的线性回归散点图（带R²值）。",
            "scatter_data_dir": "数据目录：{}",
            "scatter_upload_files": "上传散点图数据（CSV）",
            "scatter_clear_before": "保存前清空数据目录",
            "scatter_generate_btn": "✨ 生成散点图",
            "scatter_running": "正在生成散点图，请稍候...",
            "scatter_run_success": "✅ 散点图生成完成！",
            "scatter_run_failed": "❌ 散点图生成失败：{}",
            "scatter_no_files": "未在数据目录中找到可用的CSV文件。",
            "scatter_generated_files_count": "本次生成了 {} 个输出文件",
            "scatter_preview_title": "预览生成的文件（前10个）",
            "scatter_column_settings": "列名设置（可选，留空使用默认值）",
            "scatter_green_x": "绿色细胞X轴列名",
            "scatter_green_y": "绿色细胞Y轴列名",
            "scatter_red_x": "红色细胞X轴列名",
            "scatter_red_y": "红色细胞Y轴列名",
            "scatter_te_x": "编辑效率X轴列名",
            "scatter_te_y": "编辑效率Y轴列名",
            
            # HTML报告相关
            "html_report_title": "AI分析报告",
            "html_report_subtitle": "荧光细胞分析 - 现代化样式",
            "html_report_system_name": "EasyReporter AI 分析系统",
            "contains_all_targets": "(包含所有靶点数据)",
            "group_analysis_section_title": "按组别分析",
            "group_analysis_heading_template": "{}组分析",
            "chart_analysis_heading_template": "{}分析",
            "analysis_result_title": "📊 分析结果",
            "ai_insight_title": "🤖 AI解读",
            "comparative_analysis_section_title": "综合对比分析",
            "comparative_chart_heading_template": "{}综合对比",
            "comparative_analysis_title": "📊 综合分析",
            "key_findings_section_title": "🔍 关键发现与结论",
            "main_findings_title": "主要发现",
            "main_findings_content": "编辑效率差异显著: Cas9-site1(26.80%)明显优于Cas12-site1(10.50%)<br>细胞计数一致性: 两组红色细胞数量相近(380 vs 376)，绿色细胞Cas9组略多<br>荧光表达特征: GFP表达水平相近，但mCherry表达Cas12组更高<br>技术重复稳定性: 当前数据基于单次实验，需要更多重复验证",
            "conclusion_title": "结论",
            "conclusion_content": "在当前实验条件下，Cas9-site1系统显示出比Cas12-site1系统更高的基因编辑效率，差异具有生物学意义。两种系统均能实现目标基因编辑，但效率相差超过2.5倍。",
            "limitations_recommendations_title": "局限性与建议",
            "limitations_title": "📋 局限性说明",
            "limitations_content": "样本量限制: 每组仅1个技术重复，统计效力有限<br>时间点单一: 仅606单一时间点数据，无法评估时间动态<br>变异度未知: 缺乏生物学重复，无法评估组内变异<br>机制解释有限: 仅基于表型数据，缺乏分子水平验证",
            "recommendations_title": "💡 改进建议",
            "recommendations_content": "增加重复: 建议至少3个生物学重复以提高统计可靠性<br>时间序列: 增加多个时间点监测编辑动态过程<br>机制验证: 结合测序验证实际编辑位点和效率<br>浓度优化: 探索不同sgRNA浓度对编辑效率的影响<br>阴性对照: 加入无sgRNA对照组确认背景编辑水平",
            "uncertainty_title": "⚠️ 不确定性说明",
            "uncertainty_content": "当前结论基于有限样本量，需要更多重复实验确认结果的稳定性和可重复性。",
            "chart_fluorescence_intensity_label": "荧光强度统计",
            "chart_analysis_alt_template": "{} - {}",
            "comparative_alt_template": "综合对比 - {}",
            
            # Step 3 相关
            "step3_header": "📥 步骤3: 下载结果",
            "no_charts_generated": "尚未生成任何图表。请前往步骤2生成图表。",
            "preview_charts_title": "3.1 预览生成的图表",
            "no_previewable_files": "未找到可预览的图像文件。您仍可以在下方下载结果。",
            "download_results_title": "3.2 下载结果文件",
            "download_all_charts": "📊 下载所有图表",
            "download_charts_zip": "💾 下载图表压缩包",
            "download_processed_data": "📋 下载处理数据",
            "download_data_zip": "💾 下载数据压缩包",
            "individual_download_title": "3.3 单独文件下载",
            "select_file_download": "选择要下载的文件",
            "download_file": "💾 下载 {}",
            "failed_read_file": "读取文件失败: {}",
            "no_charts_complete_step2": "尚未生成任何图表。请先完成步骤2。",
            "could_not_display": "无法显示 {}\n错误: {}",
            # Cellpose progress messages
            "cellpose_init_complete": "初始化完成，找到 {} 个图像对",
            "cellpose_processing": "正在处理 ({}/{}) - {}%: {}",
            "cellpose_complete_file": "✅ 完成: {} (绿色细胞: {}, 红色细胞: {})",
            "cellpose_error": "❌ 错误: {}",
            "cellpose_finished": "🎉 Cellpose处理完成 - 100%！",
            # Fluorescence analysis messages
            "fluor_starting": "🔬 正在启动荧光强度分析...",
            "fluor_processing": "📊 正在处理分析结果...",
            "fluor_complete": "✅ 荧光强度分析完成！",
            "fluor_failed": "❌ 荧光强度分析失败",
            "fluor_error": "❌ 荧光强度分析出错",
            # Chart generation messages
            "chart_prepare_generate": "📊 准备生成 {} 个图表...",
            "chart_generating": "🔄 生成中",
            "chart_generating_progress": "正在生成 ({}/{}) : {}",
            "chart_complete": "✅ 完成",
            "chart_completed_progress": "已完成 {}/{} 个图表，预计剩余时间: {}",
            "chart_all_complete": "🎉 图表生成完成！成功生成 {}/{} 个图表，总用时: {}",
            "chart_partial_success": "⚠️ 部分图表生成成功 ({}/{})，请检查日志了解失败原因。",
            "chart_all_failed": "❌ 所有图表生成都失败了，请检查日志了解原因。",
            # AI analysis messages
            "ai_data_summary_complete": "📊 数据汇总完成，正在收集图表...",
            "ai_generating_insight": "🤖 正在生成 {} 的AI解读...",
            "ai_insight_complete": "✅ {} 解读完成",
            "ai_prepare_report": "📝 准备生成整体AI报告...",
            "ai_generating_report": "🤖 正在生成整体AI报告...",
            "ai_all_complete": "✅ AI解读全部完成！",
            # Additional AI messages
            "ai_no_valid_insight": "该图未生成有效解读",
            "ai_insight_failed": "❌ {} 解读失败",
            "ai_insight_error": "❌ {} 解读出错",
            "ai_chart_display_failed": "❌ 图表显示或解读失败",
            "ai_overall_report_failed": "❌ 整体报告生成失败",
            "ai_overall_report_error": "❌ 整体报告生成出错",
            "ai_wait_rate_limit": "⏳ 等待 {}s 以避免API速率限制...",
            "ai_wait_rate_limit_info": "为避免触发速率限制，等待 {}s 再开始该图解读...",
            "ai_wait_overall_report_info": "为避免触发速率限制，等待 {}s 再开始生成总体报告...",
            "ai_preparing": "🤖 正在准备AI解读...",
            "interpreting_chart_spinner": "正在解读该图...",
            "html_title": "AI分析报告 - 包含图片",
            "report_title": "🤖 AI智能分析报告",
            "overall_report": "📊 整体分析报告",
            "chart_details": "📈 图表详细解读",
            "ai_insight_label": "🤖 AI解读:",
            "file_name_label": "文件名:",
            "html_generation_failed": "报告生成失败",
            "pdf_caption_prefix": "图",
            "pdf_generated_by": "由 EasyReporter AI 智能分析系统生成",
            "pdf_missing_deps": "缺少PDF生成依赖库。请运行: pip install reportlab Pillow",
            "pdf_generation_failed_generic": "PDF生成失败: {}",
            "chart_status_waiting": "⏳ 等待中",
            "chart_status_failed": "❌ 失败",
            "chart_generation_failed": "图表生成失败: {}",
            "step1_completed_msg": "✅ 步骤 1 完成！数据处理成功。",
            "back_to_step1_button": "🔄 返回步骤 1（重新处理数据）",
            "app_info_header": "📋 应用信息",
            "working_dir_label": "工作目录：{}",
            "uploaded_files_label": "已上传文件：{}",
            "current_status_header": "📊 当前状态",
            "step1_status_label": "步骤 1（数据处理）：{}",
            "step_status_completed": "✅ 已完成",
            "step_status_not_completed": "⏳ 未完成",
            "no_overall_report": "暂无整体分析报告内容。",
            "could_not_load_image": "无法加载图片: {}",
            "per_chart_ai_insights_title": "### 每图AI解读",
            "ai_not_available_warning": "AI 功能未启用，缺少: {}。如需启用，请安装相应依赖并放回 AI_helper。",
            "files_saved_success": "文件保存成功!",
            "files_save_failed": "保存文件失败: {}",
            "delete_file_failed": "无法删除 {}: {}",
            "step1_starting_process": "开始数据处理(模式: {})...",
            "cellpose_segmenting": "正在运行 Cellpose 分割...",
            "cellpose_failed_error": "Cellpose 处理失败",
            "fluor_analyzing": "正在分析荧光强度...",
            "fluor_failed_error": "荧光强度分析失败",
            "processing_completed_status": "数据处理完成!",
            "processing_completed_success": "🎉 数据处理完成!现在可以生成图表。",
            "page_refresh_info": "📋 页面即将刷新以显示步骤 2 和 3...",
            "data_processing_failed": "数据处理失败: {}",
            "existing_charts_detected": "✅ 检测到已有图表数据!",
            "skip_step2_btn": "⏭️ 跳过步骤2(使用现有图表)",
            "redo_step2_btn": "🔄 重新生成图表",
            "cleared_old_charts": "已清理旧的图表数据",
            "clear_charts_failed": "清理图表数据失败: {}",
            "step2_skipped_info": "📊 步骤2已跳过，使用现有图表数据进行AI报告生成",
            "corr_scatter_size_color_title": "⚙️ 图片大小与散点颜色设置",
            "image_size_inches": "**图片尺寸 (英寸)**",
            "width_label": "宽度",
            "height_label": "高度",
            "scatter_colors_hex": "**散点颜色 (HEX格式)**",
            "group1_color": "第一组 (FACS vs AI)",
            "group2_color": "第二组 (FACS vs Amplicon)",
            "group3_color": "第三组 (AI vs Amplicon)",
            "scatter_module_error": "散点图模块错误: {}",
            "correlation_preview_error": "相关性预览错误: {}",
            "charts_detected": "✅ 检测到图表数据!",
            "skip_step3_btn": "⏭️ 跳过步骤3(直接进行AI解读)",
            "step3_skipped_preview": "已跳过步骤3预览，可直接进行步骤4 AI解读",
            "view_chart_preview_btn": "👁️ 查看图表预览",
            "step3_skipped_info": "📊 步骤3已跳过，可直接进行步骤4的AI报告生成",
            "ai_summary_complete_layered": "数据汇总完成，开始分层AI解读...",
            "ai_generating_layered_report": "正在生成分层AI解读报告...",
            "ai_rate_limit_info": "为避免 OpenAI 429 速率限制，我们将在每次AI调用之间自动等待约 {} 秒。",
            "ai_reused_report_status": "已复用同一批数据的报告。",
            "ai_reused_report_info": "数据和分析设置未变，已复用上次报告，内容保持一致。",
            "ai_layered_complete": "分层AI解读完成!",
            "ai_no_valid_content": "未生成有效的AI解读内容",
            "ai_interpretation_failed": "AI解读失败",
            "ai_layered_error": "分层AI解读生成错误: {}",
            "ai_generation_error_status": "AI解读生成错误",
            "ai_process_error": "AI解读过程错误: {}",
            "ai_interpretation_success_log": "分层AI解读成功完成",
            "charts_collected_info": "收集到 {} 个图表类别，共 {} 张图片",
            "no_charts_warning": "未收集到任何图表，请先生成图表",
            "proteins_targets_found": "找到 {} 个蛋白，共 {} 个靶点",
            "protein_targets_detail": "  • {}: {} 个靶点 ({})",
            "no_protein_groups_warning": "未找到蛋白和靶点分组数据",
            "select_data_per_target_title": "#### 为每个靶点选择展示的数据",
            "select_data_hint": "💡 提示：每个靶点选择一个数据ID，报告中将为每种图表类型展示所有靶点的图片（一行3张）",
            "protein_expander_title": "🧬 {} 蛋白 ({} 个靶点)",
            "select_data_for": "选择 {}-{} 的数据",
            "selected_caption": "已选择: {} (将在报告中展示)",
            "targets_selected_success": "✅ 已为 {} 个靶点选择数据",
            "current_selection_caption": "当前选择详情: ",
            "load_group_failed": "无法加载数据分组: {}",
            "pdf_timeout_warning": "PDF 转换超时，正在使用备用方案...",
            "browser_pdf_failed": "浏览器 PDF 转换失败: {}，正在使用备用方案...",
            "simple_pdf_fallback_info": "📄 正在使用简易 PDF 备用方案生成报告...",
            "pdf_missing_deps_error": "缺少PDF生成依赖: {}",
            "pdf_detailed_error": "详细错误信息: {}",
            "html_report_by_group_suffix": " - 按实验组别",
            "group_analysis_heading": "{} 组分析",
            "chart_analysis_heading": "{}分析",
            "statistical_charts_heading": "统计分析图表",
            "ai_comprehensive_analysis_heading": "🤖 AI 综合分析",
            "key_findings_recommendations_heading": "🔍 关键发现与建议",
            "quick_start_ai_info": "🎯 检测到项目中已有数据!您可以直接跳到AI解读步骤。",
            "quick_start_ai_btn": "⚡ 快速进入AI解读(跳过步骤1)",
            "quick_mode_enabled": "已启用快捷模式，您可以在步骤2选择是否重新生成图表!",
            "start_over_btn": "🔄 从头开始(重新运行所有步骤)",
            "start_from_step1": "将从步骤1开始",
            "current_project_label": "📌 当前项目: **{}**",
            "project_data_status": "**项目数据状态:**",
            "raw_images_label": "原始图片",
            "segmentation_results_label": "细胞分割结果",
            "fluorescence_data_label": "荧光强度数据",
            "statistical_charts_label": "统计图表",
            "cellpose_mode_label_status": "Cellpose 模式: {} {}",
            "debug_info_expander": "🔧 调试信息",
            "session_state_label": "会话状态:",
            "environment_check_header": "🔍 环境检测",
            "clear_work_dir_btn": "🗑️ 清空工作目录",
            "work_dir_cleared": "工作目录已清空",
            "cellpose_log_running": "正在运行命令: {}",
            "cellpose_log_working_dir": "工作目录: {}",
            "cellpose_log_starting": "开始 Cellpose 处理，以下是实时日志:",
            "color_number_label": "颜色 {}",
            "ready_to_use": "👆 准备就绪!",
            "cellpose_execution_error_log": "Cellpose 执行错误: {}",
            "cellpose_install_suggestion": "提示: 请安装 cellpose 或使用 Apptainer 模式",
            "cellpose_processing_failed_log": "Cellpose 处理失败: {}",
            "cellpose_processing_success_log": "Cellpose 处理成功 ({})",
            "correlation_section_error": "相关性分析出错: {}",
            "execution_error_log": "执行错误: {}",
            "fluor_analysis_error_log": "荧光分析出错: {}",
            "fluor_analysis_failed_log": "荧光分析失败: {}",
            "fluor_analysis_succeeded_log": "荧光分析成功",
            "no_ai_report_available": "暂无AI报告",
            "no_files_selected": "未选择文件",
            "realtime_log_label": "实时日志",
            "save_failed": "保存文件失败: {}",
            "time_min": "分",
            "time_sec": "秒"
    },
    "en": {
        "app_title": "🔬 EasyReporter - Fluorescent Cell Analysis Tool",
        "step1_title": "📤 Step 1: Data Processing",
        "step2_title": "📊 Step 2: Chart Generation",
        "step3_title": "📥 Step 3: Download Results",
        "step4_title": "🤖 Step 4: AI Interpretation",
        "step1_desc": "Upload images → Cellpose segmentation → Fluorescence intensity analysis",
        "step2_desc": "Select chart types → Configure parameters → Generate visuals",
        "step3_desc": "Download charts and data files",
        "step4_desc": "Enter API Key → Generate report",
        "ready_to_use": "👆 Ready to use!",
        "upload_images": "1.1 Upload Fluorescent Images",
        "input_mode": "Select input mode",
        "upload_tiff": "Upload TIFF files",
        "upload_zip": "Upload ZIP",
        "select_folder": "Select local folder",
        "step1_config_params_title": "1.2 Configure Processing Parameters",
        "cellpose_execution_mode_title": "Cellpose Execution Mode",
        "select_cellpose_execution_mode": "Select Cellpose Execution Mode",
        "python_mode_label": "🐍 Python (Recommended)",
        "apptainer_mode_label": "📦 Apptainer Container",
        "select_cellpose_run_help": "Select how to run Cellpose",
        "cellpose_params_title": "Cellpose Parameters",
        "apptainer_image_path_label": "Apptainer Image Path",
        "apptainer_image_path_help": "Path to the Cellpose container image file",
        "python_mode_info": "Python mode will directly use locally installed Cellpose",
        "use_gpu_label": "Use GPU Acceleration",
        "use_gpu_help": "If GPU is available, enable it to speed up processing",
        "pretrained_model_label": "Pretrained Model",
        "pretrained_model_help": "Select the Cellpose pretrained model that best fits your data",
        "fluorescence_params_title": "Fluorescence Analysis Parameters",
        "matching_distance_threshold_label": "Cell Matching Distance Threshold (pixels)",
        "matching_distance_threshold_help": "Distance threshold for matching GFP and mCherry cells",
        "step1_start_processing_title": "1.3 Start Processing",
        "start_data_processing_button": "🚀 Start Data Processing",
        "please_upload_images_error": "Please upload image files or import from a folder first",
        "upload_images": "1.1 Upload Fluorescent Images",
        "input_mode": "Select Input Mode",
        "upload_tiff": "Upload TIFF Files",
        "upload_zip": "Upload ZIP Archive",
        "select_folder": "Select Local Directory",
        "zip_info": "Upload a ZIP archive containing TIFF/TIF images (max 5GB supported); the system will extract them to the working directory Data for processing",
        "select_tiff_label": "Select TIFF Image Files (GFP and mCherry channels supported)",
        "uploader_help": "Please upload paired GFP and mCherry image files, filename format example: sample_EGFP-1.tif, sample_mcherry-1.tif",
        "upload_zip_label": "Upload ZIP containing TIFF/TIF images",
        "folder_info": "Select a local folder containing TIFF/TIF images; the system will copy them to the working directory Data for processing",
        "local_dir_path": "Local Directory Path",
        "include_subdirs": "Include Subdirectories",
        "clear_target": "Clear target directory before import (Data)",
        "clear_target_zip": "Clear target directory before extraction (Data)",
        "save_files": "💾 Save Uploaded Files",
        "extract_zip": "📦 Extract ZIP to Input Directory",
        "import_from_dir": "📥 Import Images from Directory",
        "processing_log": "📋 Processing Log",
        "uploaded_successfully": "Successfully uploaded {} files",
        "view_files": "View Uploaded Files",
        "select_zip_first": "Please select a ZIP file first",
        "imported_files": "Imported {} image files from ZIP",
        "view_imported": "View Imported Files",
        "no_tiff_found": "No TIFF/TIF files found in ZIP",
            "local_dir_placeholder": "e.g., D:\\data\\experiment_01",
            "enter_dir_path": "Please enter a local directory path",
            "not_valid_dir": "The path is not a valid local directory",
            "copy_failed": "Copy failed: {} -> {} ({})",
            "imported_from_dir": "Imported {} image files from directory",
            "no_tiff_found_dir": "No TIFF/TIF files found in the directory",
            "skipped_unsafe_path": "Skipped potentially unsafe path: {}",
            "extract_failed_entry": "Extract failed: {} -> {} ({})",
            "zip_extract_error": "Error occurred while extracting ZIP: {}",
            "input_data_dir": "Input data directory: {}",
            "switch_language_help": "Switch language",
            "switch_to_en": "Switch to English",
            "switch_to_zh": "Switch to Chinese",
        "project_management": "📁 Project Management",
        "current_project": "📌 Current Project",
        "no_project_selected": "None",
        "project_action": "Select Action",
        "continue_current": "Continue Current Project",
        "open_existing": "Open Existing Project",
        "create_new": "Create New Project",
        "select_project": "Select Project",
        "open_project_btn": "📂 Open Project",
        "new_project_name": "New Project Name",
        "project_name_placeholder": "e.g., Experiment_2024",
        "create_project_btn": "✨ Create Project",
        "project_switched": "Switched to project: {}",
        "project_created": "Created new project: {}",
        "invalid_project_name": "Project name can only contain letters, numbers, underscores, and hyphens",
        "enter_valid_name": "Please enter a valid project name",
            "step4_header": "🤖 Step 4: AI Interpretation",
            "step4_info": "This feature uses a Large Language Model (LLM) to analyze your experimental data and automatically generate a report. If the model supports multimodality, representative images will be attached for per-chart interpretation.",
            "config_provider_api": "4.1 Configure Provider and API Key",
            "select_provider": "Select Provider",
            "provider_help": "Supports OpenAI or OpenAI-compatible services (e.g., Kimi/Moonshot, DeepSeek).",
            "base_url_label": "Base URL",
            "base_url_help": "OpenAI: https://api.openai.com/v1; Kimi: https://api.moonshot.cn/v1; DeepSeek: https://api.deepseek.com/v1",
            "model_name_label": "Model Name",
            "model_name_help": "e.g., OpenAI: gpt-4o or gpt-3.5-turbo; Kimi: moonshot-v1-8k; DeepSeek: deepseek-chat or deepseek-vl-7b-chat (vision support)",
            "enter_openai_key": "Enter your OpenAI API Key",
            "enter_kimi_key": "Enter your Kimi API Key",
            "enter_deepseek_key": "DeepSeek API Key (Fixed Configuration)",
            "api_key_help_openai": "Your API Key is used only for this session and will not be stored.",
            "api_key_help_kimi": "Your API Key is used only for this session and will not be stored; please ensure you have created one in the Moonshot console.",
            "api_key_help_deepseek": "API key is fixed to DeepSeek, no need to enter repeatedly",
            "api_key_fixed_success": "✅ DeepSeek API key is fixed and configured, ready to use AI features",
            "generate_analysis_report": "4.2 Generate Analysis Report",
            "btn_generate_ai_report": "✨ Generate AI Report",
            "btn_launch_ai_screening": "🚀 Launch AI Screening Assistant",
            "retry_ai_analysis": "🔄 Retry AI Analysis",
            "use_local_report": "📊 Use Simplified Local Report",
            "ai_analysis_report": "4.3 AI Analysis Report",
            "btn_download_report": "📋 Download Report",
            "generating_report": "Generating report, please wait...",
            "no_data_for_ai": "No data found for AI interpretation. Please complete data processing and chart generation first.",
            "no_valid_content_generated": "No valid content generated. Please retry or use the simplified report.",
            "screening_spinner": "AI Screening Assistant is analyzing your data...",
            "screening_success": "AI Screening Assistant report generated successfully!",
            "screening_failed": "AI Screening Assistant failed to generate a valid report.",
            "screening_no_response": "Failed to get a response from the AI model.",
            "screening_error": "An error occurred while running the AI Screening Assistant: {}",
            "download_html_report": "📄 Download HTML Report",
            "download_pdf_report": "📑 Download PDF Report",
            "pdf_generation_failed": "PDF generation failed, please use HTML version",
            "pdf_generation_error": "PDF generation failed: {}",
            "use_html_version": "Please use HTML version to download report",
            "step2_header": "📊 Step 2: Chart Generation",
            "step2_congratulations": "🎉 Congratulations! You can now generate various types of charts. Please select the chart types you need:",
            "select_chart_type": "2.1 Select Chart Type",
            "configure_chart_params": "2.2 Configure Chart Parameters",
            "color_config": "🎨 Color Configuration",
            "general_color_settings": "General Color Settings",
            "general_color_info": "The following color settings will be applied to all chart types except bar charts and box plots",
            "color1_egfp": "Color 1 (GFP)",
            "color2_mcherry": "Color 2 (mCherry)",
            "color3_overlap": "Color 3 (Overlap)",
            "bar_box_color_settings": "Bar Chart and Box Plot Color Settings",
            "bar_box_color_info": "The following color settings will be applied to bar charts and box plots",
            "data_groups_count": "Number of Data Groups (Color Count)",
            "data_groups_help": "Select the number of colors needed based on your data groups",
            "size_config": "📏 Chart Size Configuration",
            "chart_size_settings": "Chart Size Settings for Each Type",
            "chart_width": "Chart Width",
            "chart_height": "Chart Height",
            "other_params_config": "⚙️ Other Parameter Configuration",
            "distance_threshold": "Matching Distance Threshold",
            "generate_charts_section": "2.3 Generate Charts",
            "generate_selected_charts": "🎨 Generate Selected Charts",
            "chart_cell_distribution": "Cell Distribution Scatter Plot",
            "chart_cell_distribution_desc": "Display spatial distribution of GFP and mCherry cells",
            "chart_targeting_efficiency": "Targeting Efficiency Bar Chart",
            "chart_targeting_efficiency_desc": "Show targeting efficiency statistics for different groups",
            "chart_cell_box": "Cell Box Plot",
            "chart_cell_box_desc": "Show cell data distribution and statistical features",
            "chart_cell_clustering": "Cell Clustering Scatter Plot",
            "chart_cell_clustering_desc": "Display clustering distribution by cell type",
            "chart_flow_cytometry": "Simulated Flow Cytometry Plot",
            "chart_flow_cytometry_desc": "Scatter plot representation of simulated flow cytrometry",
            
            "correlation_section_title": "2.4 Correlation Heatmap (Pearson r)",
            "correlation_section_desc": "Auto-scan tables under correlation/data (CSV/TSV/Excel) and batch generate Pearson (r) correlation heatmaps into correlation/output.",
            "correlation_data_dir": "Data directory: {}",
            "correlation_upload_files": "Upload correlation tables (CSV/TSV/XLSX/XLS)",
            "correlation_clear_before": "Clear data directory before saving (correlation/data)",
            "correlation_generate_btn": "✨ Generate Correlation Heatmap (Pearson r)",
            "correlation_running": "Generating correlation heatmaps, please wait...",
            "correlation_run_success": "✅ Correlation heatmap generation completed!",
            "correlation_run_failed": "❌ Correlation heatmap generation failed: {}",
            "correlation_no_files": "No valid table files found in the data directory.",
            "correlation_generated_files_count": "{} output files were generated",
            "correlation_preview_title": "Preview generated files (first 10)",
            
            # Correlation Scatter Plot
            "scatter_section_title": "2.5 Correlation Scatter Plot (Linear Regression)",
            "scatter_section_desc": "Upload CSV data to generate pairwise linear regression scatter plots (with R² values).",
            "scatter_data_dir": "Data directory: {}",
            "scatter_upload_files": "Upload scatter plot data (CSV)",
            "scatter_clear_before": "Clear data directory before saving",
            "scatter_generate_btn": "✨ Generate Scatter Plots",
            "scatter_running": "Generating scatter plots, please wait...",
            "scatter_run_success": "✅ Scatter plot generation completed!",
            "scatter_run_failed": "❌ Scatter plot generation failed: {}",
            "scatter_no_files": "No valid CSV files found in the data directory.",
            "scatter_generated_files_count": "{} output files were generated",
            "scatter_preview_title": "Preview generated files (first 10)",
            "scatter_column_settings": "Column Settings (optional, leave blank to use defaults)",
            "scatter_green_x": "Green Cell X-axis Column",
            "scatter_green_y": "Green Cell Y-axis Column",
            "scatter_red_x": "Red Cell X-axis Column",
            "scatter_red_y": "Red Cell Y-axis Column",
            "scatter_te_x": "Target Efficiency X-axis Column",
            "scatter_te_y": "Target Efficiency Y-axis Column",
            
            # HTML report related
            "html_report_title": "Comprehensive Gene Editing Efficiency Analysis Report",
            "html_report_subtitle": "AI Analysis Report",
            "html_report_system_name": "EasyReporter AI Analysis System",
            "contains_all_targets": "(Contains all target data)",
            "group_analysis_section_title": "Group-wise Analysis",
            "group_analysis_heading_template": "{} Group Analysis",
            "chart_analysis_heading_template": "{} Analysis",
            "analysis_result_title": "📊 Analysis Findings",
            "ai_insight_title": "🤖 AI Insight",
            "comparative_analysis_section_title": "Comparative Analysis",
            "comparative_chart_heading_template": "{} Comparative Overview",
            "comparative_analysis_title": "📊 Comparative Insight",
            "key_findings_section_title": "🔍 Key Findings & Conclusions",
            "main_findings_title": "Key Findings",
            "main_findings_content": "Editing efficiency differs markedly: Cas9-site1 (26.80%) clearly outperforms Cas12-site1 (10.50%)<br>Cell counts remain consistent: red-cell totals are comparable (380 vs 376) while Cas9 has slightly more green cells<br>Fluorescence expression: GFP levels are similar, but mCherry intensity is higher in the Cas12 group<br>Technical repeatability: current results rely on a single run and require additional replicates for confirmation",
            "conclusion_title": "Conclusion",
            "conclusion_content": "Under the current assay conditions, the Cas9-site1 system achieves substantially higher editing efficiency than Cas12-site1. Both systems edit the target, yet Cas9 delivers more than 2.5× the efficiency.",
            "limitations_recommendations_title": "Limitations & Recommendations",
            "limitations_title": "📋 Limitations",
            "limitations_content": "Sample size: only one technical replicate per group limits statistical power<br>Single time point: measurements at 606 only prevent temporal trend assessment<br>Unknown variability: absence of biological replicates leaves within-group variance uncharacterized<br>Mechanistic insight: conclusions rely on phenotypic readouts without molecular validation",
            "recommendations_title": "💡 Recommendations",
            "recommendations_content": "Increase replicates: collect ≥3 biological repeats to improve statistical reliability<br>Time-course profiling: capture additional time points to track editing dynamics<br>Mechanistic validation: pair the assay with sequencing to confirm on-target edits and efficiency<br>Concentration optimization: test different sgRNA doses to probe efficiency gains<br>Negative control: include sgRNA-free controls to benchmark background editing",
            "uncertainty_title": "⚠️ Uncertainties",
            "uncertainty_content": "These conclusions derive from limited data; further replicates are required to verify robustness and reproducibility.",
            "chart_fluorescence_intensity_label": "Fluorescence Intensity Summary",
            "chart_analysis_alt_template": "{} - {}",
            "comparative_alt_template": "Comparative Overview - {}",
            
            # Step 3 related
            "step3_header": "📥 Step 3: Download Results",
            "no_charts_generated": "No charts have been generated yet. Please go to Step 2 to generate charts.",
            "preview_charts_title": "3.1 Preview Generated Charts",
            "no_previewable_files": "No previewable image files found. You can still download the results below.",
            "download_results_title": "3.2 Download Result Files",
            "download_all_charts": "📊 Download All Charts",
            "download_charts_zip": "💾 Download Charts ZIP",
            "download_processed_data": "📋 Download Processed Data",
            "download_data_zip": "💾 Download Data ZIP",
            "individual_download_title": "3.3 Individual File Download",
            "select_file_download": "Select File to Download",
            "download_file": "💾 Download {}",
            "failed_read_file": "Failed to read file: {}",
            "no_charts_complete_step2": "No charts have been generated yet. Please complete Step 2 first.",
            "could_not_display": "Could not display {}\nError: {}",
            # Cellpose progress messages
            "cellpose_init_complete": "Initialization complete, found {} image pairs",
            "cellpose_processing": "Processing ({}/{}) - {}%: {}",
            "cellpose_complete_file": "✅ Complete: {} (Green cells: {}, Red cells: {})",
            "cellpose_error": "❌ Error: {}",
            "cellpose_finished": "🎉 Cellpose processing complete - 100%!",
            # Fluorescence analysis messages
            "fluor_starting": "🔬 Starting fluorescence intensity analysis...",
            "fluor_processing": "📊 Processing analysis results...",
            "fluor_complete": "✅ Fluorescence intensity analysis complete!",
            "fluor_failed": "❌ Fluorescence intensity analysis failed",
            "fluor_error": "❌ Fluorescence intensity analysis error",
            # Chart generation messages
            "chart_prepare_generate": "📊 Preparing to generate {} charts...",
            "chart_generating": "🔄 Generating",
            "chart_generating_progress": "Generating ({}/{}) : {}",
            "chart_complete": "✅ Complete",
            "chart_completed_progress": "Completed {}/{} charts, estimated remaining time: {}",
            "chart_all_complete": "🎉 Chart generation complete! Successfully generated {}/{} charts, total time: {}",
            "chart_partial_success": "⚠️ Some charts generated successfully ({}/{}), please check logs for failure reasons.",
            "chart_all_failed": "❌ All chart generation failed, please check logs for reasons.",
            # AI analysis messages
            "ai_data_summary_complete": "📊 Data summary complete, collecting charts...",
            "ai_generating_insight": "🤖 Generating AI insight for {}...",
            "ai_insight_complete": "✅ {} insight complete",
            "ai_prepare_report": "📝 Preparing to generate overall AI report...",
            "ai_generating_report": "🤖 Generating overall AI report...",
            "ai_all_complete": "✅ All AI analysis complete!",
            # Additional AI messages
            "ai_no_valid_insight": "No valid insight generated for this chart.",
            "ai_insight_failed": "❌ {} insight failed",
            "ai_insight_error": "❌ {} insight error",
            "ai_chart_display_failed": "❌ Chart display or insight failed",
            "ai_overall_report_failed": "❌ Overall report generation failed",
            "ai_overall_report_error": "❌ Overall report generation error",
            "ai_wait_rate_limit": "⏳ Waiting {}s to avoid API rate limit...",
            "ai_wait_rate_limit_info": "Waiting {}s to avoid rate limit before starting chart insight...",
            "ai_wait_overall_report_info": "Waiting {}s to avoid rate limit before generating overall report...",
            "ai_preparing": "🤖 Preparing AI interpretation...",
            "interpreting_chart_spinner": "Interpreting this chart...",
            "html_title": "AI Analysis Report - With Images",
            "report_title": "🤖 AI Analysis Report",
            "overall_report": "📊 Overall Analysis Report",
            "chart_details": "📈 Detailed Chart Interpretation",
            "ai_insight_label": "🤖 AI Insight:",
            "file_name_label": "File name:",
            "html_generation_failed": "Report generation failed",
            "pdf_caption_prefix": "Fig",
            "pdf_generated_by": "Generated by EasyReporter AI Analysis System",
            "pdf_missing_deps": "Missing PDF dependencies. Please run: pip install reportlab Pillow",
            "pdf_generation_failed_generic": "PDF generation failed: {}",
            "chart_status_waiting": "⏳ Waiting",
            "chart_status_failed": "❌ Failed",
            "chart_generation_failed": "Chart generation failed: {}",
            "step1_completed_msg": "✅ Step 1 completed! Data processing succeeded.",
            "back_to_step1_button": "🔄 Back to Step 1 (re-process data)",
            "app_info_header": "📋 Application Info",
            "working_dir_label": "Working directory: {}",
            "uploaded_files_label": "Uploaded files: {}",
            "current_status_header": "📊 Current Status",
            "step1_status_label": "Step 1 (Data Processing): {}",
            "step_status_completed": "✅ Completed",
            "step_status_not_completed": "⏳ Not Completed",
            "no_overall_report": "No overall analysis report content.",
            "could_not_load_image": "Could not load image: {}",
            "per_chart_ai_insights_title": "### Per-chart AI insights",
            "ai_not_available_warning": "AI features are not enabled, missing: {}. To enable them, install the required dependencies and restore AI_helper.",
            "files_saved_success": "Files saved successfully!",
            "files_save_failed": "Failed to save files: {}",
            "delete_file_failed": "Failed to delete {}: {}",
            "step1_starting_process": "Starting data processing (mode: {})...",
            "cellpose_segmenting": "Running Cellpose segmentation...",
            "cellpose_failed_error": "Cellpose processing failed",
            "fluor_analyzing": "Analyzing fluorescence intensity...",
            "fluor_failed_error": "Fluorescence intensity analysis failed",
            "processing_completed_status": "Data processing completed!",
            "processing_completed_success": "🎉 Data processing completed! You can now generate charts.",
            "page_refresh_info": "📋 The page will refresh to show Steps 2 and 3...",
            "data_processing_failed": "Data processing failed: {}",
            "existing_charts_detected": "✅ Existing chart data detected!",
            "skip_step2_btn": "⏭️ Skip Step 2 (use existing charts)",
            "redo_step2_btn": "🔄 Regenerate Charts",
            "cleared_old_charts": "Old chart data cleared",
            "clear_charts_failed": "Failed to clear chart data: {}",
            "step2_skipped_info": "📊 Step 2 skipped; using existing charts for AI report generation",
            "corr_scatter_size_color_title": "⚙️ Image Size & Scatter Color Settings",
            "image_size_inches": "**Image Size (inches)**",
            "width_label": "Width",
            "height_label": "Height",
            "scatter_colors_hex": "**Scatter Colors (HEX format)**",
            "group1_color": "Group 1 (FACS vs AI)",
            "group2_color": "Group 2 (FACS vs Amplicon)",
            "group3_color": "Group 3 (AI vs Amplicon)",
            "scatter_module_error": "Scatter plot module error: {}",
            "correlation_preview_error": "Correlation preview error: {}",
            "charts_detected": "✅ Chart data detected!",
            "skip_step3_btn": "⏭️ Skip Step 3 (go straight to AI interpretation)",
            "step3_skipped_preview": "Step 3 preview skipped; you can go straight to Step 4 AI interpretation",
            "view_chart_preview_btn": "👁️ View Chart Preview",
            "step3_skipped_info": "📊 Step 3 skipped; you can proceed to Step 4 AI report generation",
            "ai_summary_complete_layered": "Data summary complete, starting layered AI interpretation...",
            "ai_generating_layered_report": "Generating layered AI interpretation report...",
            "ai_rate_limit_info": "To avoid OpenAI 429 rate limits, we will automatically wait about {} seconds between AI calls.",
            "ai_reused_report_status": "Reused the report for the same input data.",
            "ai_reused_report_info": "The data and analysis settings are unchanged, so the previous report was reused.",
            "ai_layered_complete": "Layered AI interpretation complete!",
            "ai_no_valid_content": "No valid AI interpretation content was generated.",
            "ai_interpretation_failed": "AI interpretation failed",
            "ai_layered_error": "Layered AI interpretation error: {}",
            "ai_generation_error_status": "AI interpretation generation error",
            "ai_process_error": "AI interpretation process error: {}",
            "ai_interpretation_success_log": "Structured AI interpretation completed successfully",
            "charts_collected_info": "Collected {} chart categories with {} images in total",
            "no_charts_warning": "No charts collected. Please generate charts first.",
            "proteins_targets_found": "Found {} proteins with {} targets in total",
            "protein_targets_detail": "  • {}: {} targets ({})",
            "no_protein_groups_warning": "No protein-target grouping data found.",
            "select_data_per_target_title": "#### Select Data to Display for Each Target",
            "select_data_hint": "💡 Tip: select one data ID per target; the report will show images of all targets for each chart type (3 per row)",
            "protein_expander_title": "🧬 {} protein ({} targets)",
            "select_data_for": "Select data for {}-{}",
            "selected_caption": "Selected: {} (will be shown in the report)",
            "targets_selected_success": "✅ Data selected for {} targets",
            "current_selection_caption": "Current selection: ",
            "load_group_failed": "Failed to load data grouping: {}",
            "pdf_timeout_warning": "PDF conversion timed out; using the backup plan...",
            "browser_pdf_failed": "Browser PDF conversion failed: {}; using the backup plan...",
            "simple_pdf_fallback_info": "📄 Generating report using the simplified PDF fallback...",
            "pdf_missing_deps_error": "Missing PDF generation dependency: {}",
            "pdf_detailed_error": "Detailed error: {}",
            "html_report_by_group_suffix": " - By Experimental Group",
            "group_analysis_heading": "{} Group Analysis",
            "chart_analysis_heading": "{} Analysis",
            "statistical_charts_heading": "Statistical Charts",
            "ai_comprehensive_analysis_heading": "🤖 AI Comprehensive Analysis",
            "key_findings_recommendations_heading": "🔍 Key Findings & Recommendations",
            "quick_start_ai_info": "🎯 Existing data detected in the project! You can jump straight to the AI interpretation step.",
            "quick_start_ai_btn": "⚡ Quick Access to AI Interpretation (skip Step 1)",
            "quick_mode_enabled": "Quick mode enabled. In Step 2 you can choose whether to regenerate charts.",
            "start_over_btn": "🔄 Start Over (rerun all steps)",
            "start_from_step1": "Will start from Step 1",
            "current_project_label": "📌 Current Project: **{}**",
            "project_data_status": "**Project Data Status:**",
            "raw_images_label": "Raw Images",
            "segmentation_results_label": "Segmentation Results",
            "fluorescence_data_label": "Fluorescence Intensity Data",
            "statistical_charts_label": "Statistical Charts",
            "cellpose_mode_label_status": "Cellpose Mode: {} {}",
            "debug_info_expander": "🔧 Debug Info",
            "session_state_label": "Session State:",
            "environment_check_header": "🔍 Environment Check",
            "clear_work_dir_btn": "🗑️ Clear Working Directory",
            "work_dir_cleared": "Working directory cleared",
            "cellpose_log_running": "Running command: {}",
            "cellpose_log_working_dir": "Working directory: {}",
            "cellpose_log_starting": "Starting Cellpose processing, live logs below:",
            "color_number_label": "Color {}",
            "cellpose_execution_error_log": "Cellpose execution error: {}",
            "cellpose_install_suggestion": "Tip: install cellpose or use Apptainer mode",
            "cellpose_processing_failed_log": "Cellpose processing failed: {}",
            "cellpose_processing_success_log": "Cellpose processing succeeded ({})",
            "correlation_section_error": "Correlation analysis error: {}",
            "execution_error_log": "Execution error: {}",
            "fluor_analysis_error_log": "Fluorescence analysis error: {}",
            "fluor_analysis_failed_log": "Fluorescence analysis failed: {}",
            "fluor_analysis_succeeded_log": "Fluorescence analysis succeeded",
            "no_ai_report_available": "No AI report available",
            "no_files_selected": "No files selected",
            "realtime_log_label": "Real-time log",
            "save_failed": "Failed to save file: {}",
            "time_min": "min",
            "time_sec": "sec"
        }
    }

def get_text(key, lang=None):
    if lang is None:
        lang = st.session_state.get('language', 'zh')
    return TRANSLATIONS.get(lang, TRANSLATIONS['zh']).get(key, key)


def render_language_selector():
    col_main, col_btn = st.columns([8, 2])
    with col_btn:
        current_lang = st.session_state.get('language', 'zh')
        label = get_text("switch_to_en") if current_lang == 'zh' else get_text("switch_to_zh")
        if st.button(label, key="lang_toggle", help=get_text("switch_language_help")):
            st.session_state.language = 'en' if current_lang == 'zh' else 'zh'
            st.rerun()

# 初始化语言设置
if 'language' not in st.session_state:
    st.session_state.language = 'zh'

# 设置页面配置
st.set_page_config(
    page_title=get_text("app_title"),
    page_icon="🔬",
    layout="wide",
    initial_sidebar_state="expanded"
)

# 若 AI 功能不可用，在侧边栏给出提示
if (not OPENAI_AVAILABLE or not AI_AVAILABLE) and 'ai_notice' not in st.session_state:
    st.session_state['ai_notice'] = True
    with st.sidebar:
        missing_parts = []
        if not OPENAI_AVAILABLE:
            missing_parts.append('openai')
        if not AI_AVAILABLE:
            missing_parts.append('AI_helper')
        st.warning(get_text("ai_not_available_warning").format(", ".join(missing_parts)))

# 添加CSS样式
st.markdown("""
<style>
    .main-header {
        font-size: 2.5rem;
        color: #1f77b4;
        text-align: center;
        margin-bottom: 2rem;
    }
    .step-header {
        font-size: 1.5rem;
        color: #ff7f0e;
        margin-top: 2rem;
        margin-bottom: 1rem;
    }
    .success-box {
        padding: 1rem;
        border-radius: 0.5rem;
        background-color: #d4edda;
        border: 1px solid #c3e6cb;
        color: #155724;
        margin: 1rem 0;
    }
    .error-box {
        padding: 1rem;
        border-radius: 0.5rem;
        background-color: #f8d7da;
        border: 1px solid #f5c6cb;
        color: #721c24;
        margin: 1rem 0;
    }
    .info-box {
        padding: 1rem;
        border-radius: 0.5rem;
        background-color: #d1ecf1;
        border: 1px solid #bee5eb;
        color: #0c5460;
        margin: 1rem 0;
    }
    /* 进度条美化样式 */
    .progress-container {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        padding: 20px;
        border-radius: 15px;
        box-shadow: 0 8px 32px rgba(0,0,0,0.1);
        margin: 20px 0;
        border: 1px solid rgba(255,255,255,0.2);
        backdrop-filter: blur(10px);
    }
    .progress-status {
        font-size: 16px;
        font-weight: 600;
        color: #ffffff;
        margin-bottom: 15px;
        display: flex;
        align-items: center;
        text-shadow: 0 2px 4px rgba(0,0,0,0.3);
    }
    .progress-emoji {
        font-size: 24px;
        margin-right: 12px;
        filter: drop-shadow(0 2px 4px rgba(0,0,0,0.3));
    }
    .chart-status-item {
        background: rgba(255,255,255,0.9);
        padding: 12px 16px;
        margin: 8px 0;
        border-radius: 10px;
        border-left: 4px solid #28a745;
        font-size: 14px;
        font-weight: 500;
        box-shadow: 0 2px 8px rgba(0,0,0,0.1);
        transition: all 0.3s ease;
    }
    .chart-status-waiting {
        border-left-color: #ffc107;
        background: rgba(255,243,205,0.9);
    }
    .chart-status-generating {
        border-left-color: #007bff;
        background: rgba(230,243,255,0.9);
        animation: pulse 2s infinite;
    }
    .chart-status-completed {
        border-left-color: #28a745;
        background: rgba(230,247,230,0.9);
    }
    .chart-status-failed {
        border-left-color: #dc3545;
        background: rgba(255,230,230,0.9);
    }
    @keyframes pulse {
        0% { transform: scale(1); }
        50% { transform: scale(1.02); }
        100% { transform: scale(1); }
    }
    /* Streamlit进度条美化 */
    .stProgress > div > div > div > div {
        background: linear-gradient(90deg, #4CAF50, #45a049);
        border-radius: 10px;
    }
    .stProgress > div > div > div {
        background-color: rgba(255,255,255,0.3);
        border-radius: 10px;
    }
</style>
""", unsafe_allow_html=True)

class EasyReporterApp:
    def __init__(self):
        self.setup_session_state()
        self.setup_directories()
        
    def setup_session_state(self):
        """初始化session state"""
        if 'step1_completed' not in st.session_state:
            st.session_state.step1_completed = False
        if 'processing_log' not in st.session_state:
            st.session_state.processing_log = []
        if 'uploaded_files' not in st.session_state:
            st.session_state.uploaded_files = []
        if 'work_dir' not in st.session_state:
            st.session_state.work_dir = None
        if 'cellpose_mode' not in st.session_state:
            st.session_state.cellpose_mode = 'python'
        if 'openai_api_key' not in st.session_state:
            # 使用加密存储的默认密钥（从AI_helper获取）
            try:
                sys.path.insert(0, 'Code')
                from AI_helper import get_openai_key
                st.session_state.openai_api_key = get_openai_key()
            except:
                st.session_state.openai_api_key = ""
        if 'ai_report' not in st.session_state:
            st.session_state.ai_report = ""
        if 'project_name' not in st.session_state:
            st.session_state.project_name = None
        if 'skip_step2' not in st.session_state:
            st.session_state.skip_step2 = False
        if 'skip_step3' not in st.session_state:
            st.session_state.skip_step3 = False

    def initialize_session_state(self):
        """向后兼容：旧代码仍可能调用此方法"""
        self.setup_session_state()
    
    def check_existing_data(self):
        """检查项目中已有的数据，返回各步骤的完成状态"""
        if not st.session_state.work_dir or not os.path.exists(st.session_state.work_dir):
            return {
                "has_images": False,
                "has_cellpose_output": False,
                "has_intensity_data": False,
                "has_charts": False
            }
        
        work_dir = st.session_state.work_dir
        
        # 检查是否有上传的图片
        data_dir = os.path.join(work_dir, "Data")
        has_images = False
        if os.path.exists(data_dir):
            for root, dirs, files in os.walk(data_dir):
                if any(f.lower().endswith(('.tif', '.tiff', '.png', '.jpg')) for f in files):
                    has_images = True
                    break
        
        # 检查Cellpose输出
        cellpose_dir = os.path.join(work_dir, "Cellpose_output")
        cell_counts_dir = os.path.join(cellpose_dir, "Cell_Counts")
        has_cellpose_output = os.path.exists(cell_counts_dir) and len(os.listdir(cell_counts_dir)) > 0
        
        # 检查荧光强度数据
        intensity_dir = os.path.join(cellpose_dir, "Fluorescence_Intensity")
        has_intensity_data = os.path.exists(intensity_dir) and len(os.listdir(intensity_dir)) > 0
        
        # 检查图表 - 更严格的判断：至少要有一个图表子目录且包含图片文件
        chart_dir = os.path.join(work_dir, "Chart")
        has_charts = False
        if os.path.exists(chart_dir):
            # 检查是否有常见的图表子目录
            expected_chart_dirs = [
                "1.bar_graph",
                "2.box_graph", 
                "3.Cell_Distribution_Scatter_Plot",
                "4.Cell_Clustering_Scatter_Plot",
                "5.Simulated_Flow_Cytometry_Plot"
            ]
            chart_file_count = 0
            for chart_subdir in expected_chart_dirs:
                subdir_path = os.path.join(chart_dir, chart_subdir)
                if os.path.exists(subdir_path):
                    # 检查该子目录及其子目录中是否有图片文件
                    for root, dirs, files in os.walk(subdir_path):
                        chart_files = [f for f in files if f.lower().endswith(('.png', '.jpg', '.pdf'))]
                        chart_file_count += len(chart_files)
                        if chart_file_count > 0:
                            break
                    if chart_file_count > 0:
                        break
            # 只有在找到至少一个有效的图表文件时才认为有图表
            has_charts = chart_file_count > 0
        
        return {
            "has_images": has_images,
            "has_cellpose_output": has_cellpose_output,
            "has_intensity_data": has_intensity_data,
            "has_charts": has_charts
        }
            
    def setup_directories(self):
        """设置工作目录"""
        if st.session_state.work_dir is None:
            # 使用项目目录下的带时间戳的工作目录，避免覆盖之前的数据
            # 如果用户已选择项目名称，则使用该名称；否则使用时间戳
            script_dir = os.path.dirname(os.path.abspath(__file__))
            
            if st.session_state.project_name:
                work_dir = os.path.join(script_dir, "EasyReporter_Projects", st.session_state.project_name)
            else:
                # 默认使用时间戳创建新项目
                timestamp = time.strftime("%Y%m%d_%H%M%S")
                work_dir = os.path.join(script_dir, "EasyReporter_Projects", f"Project_{timestamp}")
                st.session_state.project_name = f"Project_{timestamp}"
            
            st.session_state.work_dir = work_dir
            
            # 创建必要的子目录
            os.makedirs(os.path.join(work_dir, "Data"), exist_ok=True)
            os.makedirs(os.path.join(work_dir, "Cellpose_output", "Cell_Counts"), exist_ok=True)
            os.makedirs(os.path.join(work_dir, "Cellpose_output", "Fluorescence_Intensity"), exist_ok=True)
            os.makedirs(os.path.join(work_dir, "Chart"), exist_ok=True)
            
    def log_message(self, message, level="info"):
        """添加日志消息"""
        timestamp = time.strftime("%H:%M:%S")
        st.session_state.processing_log.append({
            "time": timestamp,
            "level": level,
            "message": message
        })
    
    @staticmethod
    def extract_friendly_chart_name(filename):
        """
        从文件名提取友好的图表名称，格式为 Cas9-site1
        
        Args:
            filename: 原始文件名，如 "0606_293T_cas9-sg1_1-16_analysis.png"
        
        Returns:
            str: 友好名称，如 "Cas9-site1"，若无法提取则返回原文件名
        """
        import re
        
        # 尝试匹配 cas数字-sg数字 模式
        match = re.search(r'(cas\d+)-sg(\d+)', filename, re.IGNORECASE)
        if match:
            cas_part = match.group(1).capitalize()  # cas9 -> Cas9
            site_num = match.group(2)
            return f"{cas_part}-site{site_num}"
        
        # 如果无法匹配，返回不带扩展名的原文件名
        return os.path.splitext(filename)[0]
    
    @staticmethod
    def convert_protein_name_to_friendly(protein_name):
        """
        将蛋白名称转换为友好格式
        
        Args:
            protein_name: 原始名称，如 "cas9-sg1" 或 "CAS9" 或 "cas9"
        
        Returns:
            str: 友好名称，如 "Cas9-site1" 或 "Cas9"
        """
        import re
        
        # 尝试匹配 cas数字-sg数字 模式
        match = re.search(r'(cas\d+)-sg(\d+)', str(protein_name), re.IGNORECASE)
        if match:
            cas_part = match.group(1).capitalize()  # cas9 -> Cas9
            site_num = match.group(2)
            return f"{cas_part}-site{site_num}"
        
        # 如果只是cas数字，格式化为Cas9
        match = re.match(r'(cas\d+)', str(protein_name), re.IGNORECASE)
        if match:
            return match.group(1).capitalize()
        
        # 其他情况返回首字母大写
        return str(protein_name).capitalize() if protein_name else protein_name
        
    def display_log(self):
        """显示处理日志"""
        if st.session_state.processing_log:
            st.subheader(get_text("processing_log"))
            log_container = st.container()
            with log_container:
                for log_entry in st.session_state.processing_log[-10:]:  # 显示最近10条
                    level_emoji = {"info": "ℹ️", "success": "✅", "error": "❌", "warning": "⚠️"}
                    emoji = level_emoji.get(log_entry["level"], "ℹ️")
                    st.text(f"{log_entry['time']} {emoji} {log_entry['message']}")
                    
    def render_header(self):
        """渲染页面头部"""
        # 语言切换按钮 + 动态标题
        render_language_selector()
        st.markdown(f'<h1 class="main-header">{get_text("app_title")}</h1>', unsafe_allow_html=True)
        st.markdown("---")
        
        # 显示工作流程
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            status1 = "✅" if st.session_state.step1_completed else "⏳"
            st.markdown(f"**{get_text('step1_title')}** {status1}")
            st.caption(get_text('step1_desc'))

        with col2:
            status2 = "✅" if st.session_state.step1_completed else "⏸️"
            st.markdown(f"**{get_text('step2_title')}** {status2}")
            st.caption(get_text('step2_desc'))
            if st.session_state.step1_completed:
                st.success(get_text('ready_to_use'))

        with col3:
            status3 = "📥" if st.session_state.step1_completed else "⏸️"
            st.markdown(f"**{get_text('step3_title')}** {status3}")
            st.caption(get_text('step3_desc'))
            if st.session_state.step1_completed:
                st.success(get_text('ready_to_use'))
        
        with col4:
            status4 = "🤖" if st.session_state.step1_completed else "⏸️"
            st.markdown(f"**{get_text('step4_title')}** {status4}")
            st.caption(get_text('step4_desc'))
            if st.session_state.step1_completed:
                st.success(get_text('ready_to_use'))
            
        st.markdown("---")

    def render_step1(self):
        """渲染步骤1: 数据处理"""
        st.markdown(f'<h2 class="step-header">{get_text("step1_title")}</h2>', unsafe_allow_html=True)
        
        # 文件上传区域
        st.subheader(get_text("upload_images"))
        
        # 新增：输入方式选择（上传文件 或 选择本地目录）
        lang = st.session_state.get("language", "zh")
        input_mode = st.radio(
            get_text("input_mode"),
            options=["upload_tiff", "upload_zip", "select_folder"],
            format_func=lambda x: { 
                "upload_tiff": get_text("upload_tiff"),
                "upload_zip": get_text("upload_zip"),
                "select_folder": get_text("select_folder")
            }[x],
            horizontal=True,
            key="input_mode_select"
        )
        
        if input_mode == "upload_tiff":
            uploaded_files = st.file_uploader(
                get_text("select_tiff_label"),
                type=['tif', 'tiff'],
                accept_multiple_files=True,
                help=get_text("uploader_help")
            )
            
            if uploaded_files:
                st.success(get_text("uploaded_successfully").format(len(uploaded_files)))
                
                # 显示文件列表
                with st.expander(get_text("view_files")):
                    for file in uploaded_files:
                        st.text(f"📁 {file.name} ({file.size / 1024:.1f} KB)")
                        
                # 保存上传的文件
                if st.button(get_text("save_files")):
                    self.save_uploaded_files(uploaded_files)
        elif input_mode == "upload_zip":
            st.info(get_text("zip_info"))
            zip_uploaded = st.file_uploader(get_text("upload_zip_label"), type=['zip'], accept_multiple_files=False, key="zip_uploader")
            clear_target_zip = st.checkbox(get_text("clear_target_zip"), value=False, key="clear_target_zip")
            if st.button(get_text("extract_zip")):
                if not zip_uploaded:
                    st.error(get_text("select_zip_first"))
                else:
                    data_dir = os.path.join(st.session_state.work_dir, "Data")
                    os.makedirs(data_dir, exist_ok=True)
                    # 可选：清空目标目录
                    if clear_target_zip:
                        for root, dirs, files in os.walk(data_dir):
                            for f in files:
                                try:
                                    os.remove(os.path.join(root, f))
                                except Exception:
                                    pass
                            for d in dirs:
                                try:
                                    shutil.rmtree(os.path.join(root, d))
                                except Exception:
                                    pass
                    # 将上传的ZIP先写入临时文件再解压，避免文件指针问题
                    copied = []
                    tmp_path = None
                    try:
                        with tempfile.NamedTemporaryFile(delete=False, suffix=".zip") as tmp:
                            tmp.write(zip_uploaded.getbuffer())
                            tmp_path = tmp.name
                        with zipfile.ZipFile(tmp_path, 'r') as zf:
                            data_dir_norm = os.path.abspath(data_dir)
                            for info in zf.infolist():
                                if info.is_dir():
                                    continue
                                name_lower = info.filename.lower()
                                if not (name_lower.endswith('.tif') or name_lower.endswith('.tiff')):
                                    continue
                                # 规范化相对路径，防止路径穿越
                                rel_path = os.path.normpath(info.filename).lstrip("\\/")
                                dest_path = os.path.abspath(os.path.join(data_dir, rel_path))
                                if not (dest_path == data_dir_norm or dest_path.startswith(data_dir_norm + os.sep)):
                                    st.warning(get_text("skipped_unsafe_path").format(info.filename))
                                    continue
                                os.makedirs(os.path.dirname(dest_path), exist_ok=True)
                                try:
                                    with zf.open(info, 'r') as src, open(dest_path, 'wb') as dst:
                                        shutil.copyfileobj(src, dst)
                                    copied.append(os.path.relpath(dest_path, data_dir))
                                except Exception as e:
                                    st.warning(get_text("extract_failed_entry").format(info.filename, dest_path, e))
                    except Exception as e:
                        st.error(get_text("zip_extract_error").format(e))
                    finally:
                        if tmp_path and os.path.exists(tmp_path):
                            try:
                                os.remove(tmp_path)
                            except Exception:
                                pass
                    if copied:
                        st.session_state.uploaded_files = copied
                        st.success(get_text("imported_files").format(len(copied)))
                        with st.expander(get_text("view_imported")):
                            for name in copied[:200]:
                                st.text(f"📁 {name}")
                    else:
                        st.warning(get_text("no_tiff_found"))
        elif input_mode == "select_folder":
            st.info(get_text("folder_info"))
            default_dir = st.session_state.get("last_input_dir", "")
            dir_path = st.text_input(get_text("local_dir_path"), value=default_dir, placeholder=get_text("local_dir_placeholder"))
            include_subdirs = st.checkbox(get_text("include_subdirs"), value=True)
            clear_target = st.checkbox(get_text("clear_target"), value=False)
            
            if st.button(get_text("import_from_dir")):
                if not dir_path:
                    st.error(get_text("enter_dir_path"))
                elif not os.path.isdir(dir_path):
                    st.error(get_text("not_valid_dir"))
                else:
                    st.session_state.last_input_dir = dir_path
                    data_dir = os.path.join(st.session_state.work_dir, "Data")
                    os.makedirs(data_dir, exist_ok=True)
                    
                    # 可选：清空目标目录
                    if clear_target:
                        if os.path.isdir(data_dir):
                            for item in os.listdir(data_dir):
                                item_path = os.path.join(data_dir, item)
                                try:
                                    if os.path.isfile(item_path) or os.path.islink(item_path):
                                        os.unlink(item_path)
                                    elif os.path.isdir(item_path):
                                        shutil.rmtree(item_path)
                                except Exception as e:
                                    st.warning(get_text("delete_file_failed").format(item_path, e))
                    
                    # 遍历并拷贝图像
                    copied = []
                    if include_subdirs:
                        walker = os.walk(dir_path)
                    else:
                        try:
                            files = [f for f in os.listdir(dir_path)]
                        except Exception:
                            files = []
                        walker = [(dir_path, [], files)]
                    
                    for root, _, files in walker:
                        for f in files:
                            if f.lower().endswith((".tif", ".tiff")):
                                src = os.path.join(root, f)
                                rel = os.path.relpath(root, dir_path) if include_subdirs else ""
                                dest_dir = os.path.join(data_dir, rel)
                                os.makedirs(dest_dir, exist_ok=True)
                                dest = os.path.join(dest_dir, f)
                                try:
                                    shutil.copy2(src, dest)
                                    copied.append(os.path.relpath(dest, data_dir))
                                except Exception as e:
                                    st.warning(get_text("copy_failed").format(src, dest, e))
                    
                    if copied:
                        st.session_state.uploaded_files = copied
                        st.success(get_text("imported_from_dir").format(len(copied)))
                        with st.expander(get_text("view_imported")):
                            # 为避免界面过长，最多展示前200条
                            for name in copied[:200]:
                                st.text(f"📁 {name}")
                    else:
                        st.warning(get_text("no_tiff_found_dir"))
        
        # 判断输入目录是否已有可用的图像文件
        data_dir = os.path.join(st.session_state.work_dir, "Data")
        has_input_files = False
        if os.path.isdir(data_dir):
            for _r, _d, _f in os.walk(data_dir):
                if any(fn.lower().endswith((".tif", ".tiff")) for fn in _f):
                    has_input_files = True
                    break
        if has_input_files:
            st.caption(get_text("input_data_dir").format(data_dir))
                
        # 参数配置区域
        st.subheader(get_text("step1_config_params_title"))

        # Cellpose运行方式选择
        st.markdown(f"**{get_text('cellpose_execution_mode_title')}**")
        cellpose_mode = st.selectbox(
            get_text("select_cellpose_execution_mode"),
            options=["python", "apptainer"],
            format_func=lambda x: {
                "python": get_text("python_mode_label"),
                "apptainer": get_text("apptainer_mode_label")
            }[x],
            index=0,
            help=get_text("select_cellpose_run_help"),
            key="cellpose_mode_select"
        )

        st.session_state.cellpose_mode = cellpose_mode

        col1, col2 = st.columns(2)

        with col1:
            st.markdown(f"**{get_text('cellpose_params_title')}**")

            # 根据运行方式显示不同的配置选项
            if cellpose_mode == "apptainer":
                apptainer_path = st.text_input(
                    get_text("apptainer_image_path_label"),
                    value="../06.Cellpose/cellpose_2.2.2.sif",
                    help=get_text("apptainer_image_path_help")
                )
            else:  # python模式
                st.info(get_text("python_mode_info"))
                apptainer_path = None

            use_gpu = st.checkbox(
                get_text("use_gpu_label"),
                value=False,  # 默认关闭，避免环境问题
                help=get_text("use_gpu_help")
            )

            # 根据模式调整模型选项
            # 动态扫描项目 models 目录中实际存在的模型（目录内需含同名文件），
            # 避免选到不存在的模型名导致 Cellpose 回退到官方 cyto 并触发联网下载。
            models_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "models")
            model_options = []
            if os.path.isdir(models_dir):
                for _name in sorted(os.listdir(models_dir)):
                    _p = os.path.join(models_dir, _name)
                    if os.path.isdir(_p):
                        try:
                            if any(_f == _name for _f in os.listdir(_p)):
                                model_options.append(_name)
                        except Exception:
                            continue
            if not model_options:
                model_options = ["cyto3"]
            default_model = "cyto3" if "cyto3" in model_options else model_options[0]

            pretrained_model = st.selectbox(
                get_text("pretrained_model_label"),
                options=model_options,
                index=model_options.index(default_model),
                help=get_text("pretrained_model_help")
            )
            
        with col2:
            st.markdown(f"**{get_text('fluorescence_params_title')}**")
            distance_threshold = st.number_input(
                get_text("matching_distance_threshold_label"),
                min_value=1,
                max_value=100,
                value=15,
                help=get_text("matching_distance_threshold_help")
            )
            
        # 执行按钮
        st.subheader(get_text("step1_start_processing_title"))
        
        # 使用检测到的输入文件情况决定是否可点击
        if st.button(get_text("start_data_processing_button"), type="primary", disabled=not has_input_files):
            if has_input_files:
                # 准备参数
                processor_params = {
                    "mode": cellpose_mode,
                    "use_gpu": use_gpu,
                    "pretrained_model": pretrained_model,
                    "distance_threshold": distance_threshold
                }

                if cellpose_mode == "apptainer":
                    processor_params["apptainer_path"] = apptainer_path

                self.run_step1_processing(**processor_params)
            else:
                st.error(get_text("please_upload_images_error"))
                
    def save_uploaded_files(self, uploaded_files):
        """保存上传的文件到工作目录"""
        try:
            data_dir = os.path.join(st.session_state.work_dir, "Data")
            
            for uploaded_file in uploaded_files:
                file_path = os.path.join(data_dir, uploaded_file.name)
                with open(file_path, "wb") as f:
                    f.write(uploaded_file.getbuffer())
                    
            st.session_state.uploaded_files = [f.name for f in uploaded_files]
            self.log_message(get_text("uploaded_successfully").format(len(uploaded_files)), "success")
            st.success(get_text("files_saved_success"))
            
        except Exception as e:
            self.log_message(get_text("files_save_failed").format(str(e)), "error")
            st.error(get_text("files_save_failed").format(str(e)))
            
    def run_step1_processing(self, mode, use_gpu, pretrained_model, distance_threshold, **kwargs):
        """执行步骤1的数据处理"""
        try:
            self.log_message(get_text("step1_starting_process").format(mode), "info")

            # 创建进度条
            progress_bar = st.progress(0)
            status_text = st.empty()

            # 步骤1: 运行Cellpose
            status_text.text(get_text("cellpose_segmenting"))
            progress_bar.progress(25)

            success1 = self.run_cellpose(mode, use_gpu, pretrained_model, **kwargs)

            if not success1:
                st.error(get_text("cellpose_failed_error"))
                return

            progress_bar.progress(50)

            # 步骤2: 运行荧光强度分析
            status_text.text(get_text("fluor_analyzing"))
            progress_bar.progress(75)

            success2 = self.run_fluorescence_analysis(distance_threshold)

            if not success2:
                st.error(get_text("fluor_failed_error"))
                return

            progress_bar.progress(100)
            status_text.text(get_text("processing_completed_status"))

            # 标记步骤1完成
            st.session_state.step1_completed = True
            self.log_message(get_text("processing_completed_status"), "success")

            st.success(get_text("processing_completed_success"))
            st.info(get_text("page_refresh_info"))

            # 强制刷新页面以显示步骤2和步骤3
            time.sleep(1)  # 给用户时间看到成功消息
            st.rerun()

        except Exception as e:
            self.log_message(get_text("data_processing_failed").format(str(e)), "error")
            st.error(get_text("data_processing_failed").format(str(e)))
            
    def run_cellpose(self, mode, use_gpu, pretrained_model, **kwargs):
        """运行Cellpose处理"""
        try:
            # 构建命令:直接调用 1.cellpose.py,且仅支持 python/apptainer 两种模式
            cmd = [
                sys.executable, "Code/1.cellpose.py",
                "--parent-folder", os.path.join(st.session_state.work_dir, "Data"),
                "--output-folder", os.path.join(st.session_state.work_dir, "Cellpose_output", "Cell_Counts"),
                "--mode", mode,
                "--pretrained-model", pretrained_model
            ]

            if use_gpu:
                cmd.append("--use-gpu")

            # 根据模式添加特定参数
            if mode == "apptainer":
                apptainer_path = kwargs.get("apptainer_path")
                if apptainer_path:
                    cmd.extend(["--apptainer-path", apptainer_path])
                else:
                    self.log_message("Apptainer mode requires specifying the image path", "error")
                    return False


            # 执行命令：实时显示进度和日志
            self.log_message(get_text("cellpose_log_running").format(' '.join(cmd)), "info")
            self.log_message(get_text("cellpose_log_working_dir").format(os.getcwd()), "info")
            self.log_message(get_text("cellpose_log_starting"), "info")

            # 创建可跟随长度的自定义进度条和日志容器
            progress_placeholder = st.empty()
            
            def render_cellpose_progress(pct: int):
                progress_placeholder.markdown(
                    f"<div style='position:relative;width:100%;height:14px;background:rgba(0,0,0,0.08);border-radius:7px;overflow:hidden;'>"
                    f"<div style='position:relative;height:100%;width:{pct}%;background:linear-gradient(90deg,#4CAF50,#45a049);transition:width .3s ease;'>"
                    f"<span style='position:absolute;right:6px;top:50%;transform:translateY(-50%);font-size:12px;color:#fff;font-weight:600'>{pct}%</span>"
                    f"</div></div>",
                    unsafe_allow_html=True
                )
            
            render_cellpose_progress(0)
            cellpose_status = st.empty()
            log_container = st.empty()

            try:
                # 启动子进程，实时捕获输出
                process = subprocess.Popen(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    bufsize=1,
                    universal_newlines=True,
                    # encoding='utf-8',  # 删除这行。解决windows中文乱码
                    errors='ignore',
                    cwd=os.getcwd()
                )

                # 实时读取并显示输出
                output_lines = []
                total_pairs = 0
                current_pair = 0
                
                while True:
                    output = process.stdout.readline()
                    if output == '' and process.poll() is not None:
                        break
                    if output:
                        line = output.strip()
                        output_lines.append(line)
                        self.log_message(f"[Cellpose] {line}", "info")

                        # 解析进度信息
                        if line.startswith("PROGRESS_INIT:"):
                            # 提取总数
                            import re
                            match = re.search(r'Found (\d+) image pairs', line)
                            if match:
                                total_pairs = int(match.group(1))
                                cellpose_status.text(get_text("cellpose_init_complete").format(total_pairs))
                                render_cellpose_progress(0)
                        elif line.startswith("PROGRESS_UPDATE:"):
                            # 提取当前处理的文件
                            match = re.search(r'Processing pair (\d+)/(\d+): (.+)', line)
                            if match:
                                current_pair = int(match.group(1))
                                total = int(match.group(2))
                                filename = match.group(3)
                                # 计算百分比 (1-100)
                                progress_percent = int((current_pair / total) * 100) if total > 0 else 0
                                cellpose_status.text(get_text("cellpose_processing").format(current_pair, total, progress_percent, filename))
                                if total > 0:
                                    render_cellpose_progress(progress_percent)
                        elif line.startswith("PROGRESS_COMPLETE:"):
                            # 提取完成信息
                            match = re.search(r'(.+?) - Green cells: (\d+), Red cells: (\d+)', line.replace("PROGRESS_COMPLETE: ", ""))
                            if match:
                                filename = match.group(1)
                                green = match.group(2)
                                red = match.group(3)
                                cellpose_status.text(get_text("cellpose_complete_file").format(filename, green, red))
                        elif line.startswith("PROGRESS_ERROR:"):
                            error_msg = line.replace("PROGRESS_ERROR: ", "")
                            cellpose_status.text(get_text("cellpose_error").format(error_msg))
                        elif line.startswith("PROGRESS_FINISHED:"):
                            cellpose_status.text(get_text("cellpose_finished"))
                            render_cellpose_progress(100)

                        # 更新页面显示（最近10行）
                        recent_lines = output_lines[-10:]
                        log_container.text_area(
                            get_text("realtime_log_label"),
                            "\n".join(recent_lines),
                            height=200,
                            key=f"cellpose_log_{len(output_lines)}"
                        )

                return_code = process.poll()
                result = type('Result', (), {
                    'returncode': return_code,
                    'stdout': '\n'.join(output_lines),
                    'stderr': ''
                })()

            except Exception as e:
                self.log_message(get_text("execution_error_log").format(e), "error")
                return False

            if result.returncode == 0:
                self.log_message(get_text("cellpose_processing_success_log").format(mode), "success")
                return True
            else:
                self.log_message(get_text("cellpose_processing_failed_log").format(result.stderr), "error")
                # 如果是Python模式失败，提供安装建议
                if mode == "python" and "import cellpose" in result.stderr:
                    self.log_message(get_text("cellpose_install_suggestion"), "warning")
                return False

        except Exception as e:
            self.log_message(get_text("cellpose_execution_error_log").format(str(e)), "error")
            return False
            
    def run_fluorescence_analysis(self, distance_threshold):
        """运行荧光强度分析"""
        try:
            # 构建命令
            cmd = [
                sys.executable, "Code/2.Fluorescent_Intensity.py",
                "--npy_input", os.path.join(st.session_state.work_dir, "Data"),
                "--txt_input", os.path.join(st.session_state.work_dir, "Cellpose_output"),
                "--output", os.path.join(st.session_state.work_dir, "Cellpose_output", "Fluorescence_Intensity"),
                "--distance_threshold", str(distance_threshold)
            ]
            
            # 创建进度条和状态显示
            fluor_progress = st.progress(0)
            fluor_status = st.empty()
            
            fluor_status.text(get_text("fluor_starting"))
            fluor_progress.progress(0.1)
            
            # 执行命令，指定编码避免Windows下的编码问题
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                # encoding='utf-8',  # 删除这行。解决windows中文乱码
                errors='ignore',  # 忽略编码错误
                cwd=os.getcwd()
            )
            
            fluor_progress.progress(0.8)
            fluor_status.text(get_text("fluor_processing"))
            
            if result.returncode == 0:
                fluor_progress.progress(1.0)
                fluor_status.text(get_text("fluor_complete"))
                self.log_message(get_text("fluor_analysis_succeeded_log"), "success")
                return True
            else:
                fluor_status.text(get_text("fluor_failed"))
                self.log_message(get_text("fluor_analysis_failed_log").format(result.stderr), "error")
                return False
                
        except Exception as e:
            fluor_status.text(get_text("fluor_error"))
            self.log_message(get_text("fluor_analysis_error_log").format(str(e)), "error")
            return False

    def render_step2(self):
        """渲染步骤2: 图表生成"""
        st.markdown(f'<h2 class="step-header">{get_text("step2_header")}</h2>', unsafe_allow_html=True)

        # 检查是否有现有的图表数据
        existing_data = self.check_existing_data()
        
        # 添加跳过选项
        if existing_data["has_charts"]:
            st.success(get_text("existing_charts_detected"))
            col1, col2 = st.columns([1, 1])
            with col1:
                if st.button(get_text("skip_step2_btn"), key="skip_step2_btn"):
                    st.session_state.skip_step2 = True
                    st.rerun()
            with col2:
                if st.button(get_text("redo_step2_btn"), key="redo_step2_btn"):
                    # 清理旧的图表数据
                    import shutil
                    chart_dir = os.path.join(st.session_state.work_dir, "Chart")
                    if os.path.exists(chart_dir):
                        try:
                            shutil.rmtree(chart_dir)
                            self.log_message(get_text("cleared_old_charts"), "info")
                        except Exception as e:
                            self.log_message(get_text("clear_charts_failed").format(str(e)), "warning")
                    st.session_state.skip_step2 = False
                    st.rerun()
        
        # 如果选择跳过，则不显示图表生成界面
        if st.session_state.get('skip_step2', False):
            st.info(get_text("step2_skipped_info"))
            return

        # 添加明显的提示
        st.info(get_text("step2_congratulations"))

        # 图表类型选择
        st.subheader(get_text("select_chart_type"))

        chart_options = {
            "Cell_Distribution_Scatter": {
                "name": get_text("chart_cell_distribution"),
                "description": get_text("chart_cell_distribution_desc"),
                "script": "Cell_Distribution_Scatter.py"
            },
            "Grouped_Bar": {
                "name": get_text("chart_targeting_efficiency"),
                "description": get_text("chart_targeting_efficiency_desc"),
                "script": "Grouped_Bar.py"
            },
            "Grouped_Box": {
                "name": get_text("chart_cell_box"),
                "description": get_text("chart_cell_box_desc"),
                "script": "Grouped_box.py"
            },
            "Cell_Clustering_Scatter": {
                "name": get_text("chart_cell_clustering"),
                "description": get_text("chart_cell_clustering_desc"),
                "script": "Cell_Clustering_Scatter.py"
            },
            "Simulated_Flow_Cytometry": {
                "name": get_text("chart_flow_cytometry"),
                "description": get_text("chart_flow_cytometry_desc"),
                "script": "Simulated_Flow_Cytometry.py"
            }
        }

        selected_charts = []

        # 使用复选框让用户选择多个图表
        col1, col2 = st.columns(2)

        chart_keys = list(chart_options.keys())
        for i, chart_key in enumerate(chart_keys):
            chart_info = chart_options[chart_key]
            col = col1 if i % 2 == 0 else col2

            with col:
                if st.checkbox(
                    f"📈 {chart_info['name']}",
                    key=f"chart_{chart_key}",
                    help=chart_info['description']
                ):
                    selected_charts.append(chart_key)

        if selected_charts:
            st.subheader(get_text("configure_chart_params"))

            # 颜色参数配置区域
            with st.expander(get_text("color_config"), expanded=True):
                # 通用颜色设置
                st.markdown(f"**{get_text('general_color_settings')}**")
                st.info(get_text("general_color_info"))
                col1, col2, col3 = st.columns(3)
                with col1:
                    color1 = st.color_picker(
                        get_text("color1_egfp"),
                        value="#238C2A",
                        key="general_color1"
                    )
                with col2:
                    color2 = st.color_picker(
                        get_text("color2_mcherry"), 
                        value="#BF0B3B",
                        key="general_color2"
                    )
                with col3:
                    color3 = st.color_picker(
                        get_text("color3_overlap"),
                        value="#F2B90C",
                        key="general_color3"
                    )
                colors = [color1, color2, color3]
                
                # 柱状图和箱线图的特殊颜色配置
                if any(chart_key in ["Grouped_Bar", "Grouped_Box"] for chart_key in selected_charts):
                    st.markdown(f"**{get_text('bar_box_color_settings')}**")
                    st.info(get_text("bar_box_color_info"))
                    
                    # 让用户选择需要多少个颜色
                    num_colors = st.number_input(
                        get_text("data_groups_count"),
                        min_value=1, max_value=12, value=3,
                        help=get_text("data_groups_help"),
                        key="bar_box_num_colors"
                    )
                    
                    # 预定义的颜色列表
                    default_colors = [
                        "#3498db", "#e74c3c", "#f39c12", "#2ecc71", "#9b59b6", "#1abc9c",
                        "#34495e", "#f1c40f", "#e67e22", "#95a5a6", "#d35400", "#8e44ad"
                    ]
                    
                    # 动态创建颜色选择器
                    bar_box_colors = []
                    cols_per_row = 4
                    for i in range(0, num_colors, cols_per_row):
                        cols = st.columns(min(cols_per_row, num_colors - i))
                        for j, col in enumerate(cols):
                            color_index = i + j
                            if color_index < num_colors:
                                with col:
                                    color = st.color_picker(
                                        get_text("color_number_label").format(color_index + 1),
                                        value=default_colors[color_index % len(default_colors)],
                                        key=f"bar_box_color_{color_index + 1}"
                                    )
                                    bar_box_colors.append(color)
                else:
                    bar_box_colors = None

            # 图片尺寸参数配置区域
            with st.expander(get_text("size_config"), expanded=True):
                st.markdown(f"**{get_text('chart_size_settings')}**")
                chart_sizes = {}
                
                for chart_key in selected_charts:
                    chart_name = chart_options[chart_key]['name']
                    st.markdown(f"**{chart_name}**")
                    col1, col2 = st.columns(2)
                    with col1:
                        width = st.number_input(
                            get_text("chart_width"),
                            min_value=6, max_value=20, value=12,
                            key=f"width_{chart_key}"
                        )
                    with col2:
                        height = st.number_input(
                            get_text("chart_height"),
                            min_value=6, max_value=20, value=12,
                            key=f"height_{chart_key}"
                        )
                    chart_sizes[chart_key] = {"figsize_width": width, "figsize_height": height}

            # 其他特定参数配置
            with st.expander(get_text("other_params_config"), expanded=True):
                chart_params = {}
                
                for chart_key in selected_charts:
                    chart_name = chart_options[chart_key]['name']
                    chart_params[chart_key] = chart_sizes[chart_key].copy()  # 包含尺寸参数
                    
                    if chart_key in ["Grouped_Bar", "Grouped_Box"]:
                        if bar_box_colors:
                            chart_params[chart_key]["custom_colors"] = bar_box_colors
                        
                        # 移除调色板选择，使用默认配置
                        
                    elif chart_key == "Cell_Distribution_Scatter":
                        distance = st.number_input(
                            get_text("distance_threshold"),
                            min_value=1, max_value=100, value=15,
                            key=f"distance_{chart_key}"
                        )
                        chart_params[chart_key]["distance"] = distance
                        
                    elif chart_key == "Simulated_Flow_Cytometry":
                        # 移除流式图调色板选择，使用默认配置
                        pass
                        
                    elif chart_key == "Cell_Clustering_Scatter":
                        pass

            # 生成图表按钮
            st.subheader(get_text("generate_charts_section"))

            if st.button(get_text("generate_selected_charts"), type="primary"):
                self.generate_charts(selected_charts, chart_options, colors, chart_params)

            st.markdown("---")
            self.render_correlation_section()
            
            # 添加相关性散点图部分
            st.markdown("---")
            self.render_correlation_scatter_section()

    def render_correlation_section(self):
        """相关性热图（Pearson r）专区：上传、保存与批量生成"""
        try:
            st.subheader(get_text("correlation_section_title"))
            st.caption(get_text("correlation_section_desc"))

            data_dir = os.path.join(st.session_state.work_dir, "correlation", "data")
            out_dir = os.path.join(st.session_state.work_dir, "correlation", "output")
            os.makedirs(data_dir, exist_ok=True)
            os.makedirs(out_dir, exist_ok=True)

            st.caption(get_text("correlation_data_dir").format(data_dir))

            uploaded = st.file_uploader(
                get_text("correlation_upload_files"),
                type=["csv", "tsv", "txt", "xlsx", "xls"],
                accept_multiple_files=True,
                key="corr_uploader"
            )
            clear_before = st.checkbox(get_text("correlation_clear_before"), value=False, key="corr_clear_before")

            col1, col2 = st.columns(2)
            with col1:
                if st.button(get_text("save_files"), key="btn_save_corr_files"):
                    # 可选：清空原目录
                    if clear_before:
                        try:
                            for f in os.listdir(data_dir):
                                fp = os.path.join(data_dir, f)
                                if os.path.isfile(fp):
                                    os.remove(fp)
                        except Exception:
                            pass
                    saved = 0
                    if uploaded:
                        for uf in uploaded:
                            try:
                                dest = os.path.join(data_dir, uf.name)
                                with open(dest, "wb") as w:
                                    w.write(uf.getbuffer())
                                saved += 1
                            except Exception as e:
                                st.warning(get_text("save_failed").format(uf.name, e))
                    if saved:
                        st.success(get_text("uploaded_successfully").format(saved))
                    else:
                        st.info(get_text("no_files_selected"))
            with col2:
                if st.button(get_text("correlation_generate_btn"), type="primary", key="btn_run_corr"):
                    with st.spinner(get_text("correlation_running")):
                        result = self.run_correlation_generation(data_dir, out_dir)
                    if result.get("success", 0) > 0:
                        st.success(get_text("correlation_run_success"))
                        st.info(get_text("correlation_generated_files_count").format(result.get("success", 0)))
                    else:
                        err = "; ".join(result.get("errors", [])) if result.get("errors") else ""
                        st.error(get_text("correlation_run_failed").format(err))

            # 预览生成文件（前10个）
            try:
                gen_files = []
                if os.path.isdir(out_dir):
                    for f in sorted(os.listdir(out_dir)):
                        if f.lower().endswith((".pdf", ".png", ".jpg", ".jpeg")):
                            gen_files.append(os.path.join(out_dir, f))
                if gen_files:
                    st.markdown("---")
                    st.markdown(f"**{get_text('correlation_preview_title')}**")
                    for p in gen_files[:10]:
                        st.text(f"📄 {os.path.basename(p)}")
                else:
                    st.info(get_text("correlation_no_files"))
            except Exception:
                pass
        except Exception as e:
            st.warning(get_text("correlation_section_error").format(e))
    
    def render_correlation_scatter_section(self):
        """相关性散点图（线性回归）专区：上传、保存与批量生成"""
        try:
            st.subheader(get_text("scatter_section_title"))
            st.caption(get_text("scatter_section_desc"))

            data_dir = os.path.join(st.session_state.work_dir, "correlation_scatter", "data")
            out_dir = os.path.join(st.session_state.work_dir, "correlation_scatter", "output")
            os.makedirs(data_dir, exist_ok=True)
            os.makedirs(out_dir, exist_ok=True)

            st.caption(get_text("scatter_data_dir").format(data_dir))

            uploaded = st.file_uploader(
                get_text("scatter_upload_files"),
                type=["csv"],
                accept_multiple_files=True,
                key="scatter_uploader"
            )
            
            # 参数设置
            with st.expander(get_text("scatter_column_settings"), expanded=True):
                st.caption(get_text("corr_scatter_size_color_title"))
                
                col1, col2 = st.columns(2)
                with col1:
                    st.markdown(get_text("image_size_inches"))
                    fig_width = st.number_input(get_text("width_label"), min_value=6.0, max_value=24.0, value=12.0, step=0.5, key="scatter_fig_width")
                    fig_height = st.number_input(get_text("height_label"), min_value=6.0, max_value=24.0, value=12.0, step=0.5, key="scatter_fig_height")
                
                with col2:
                    st.markdown(get_text("scatter_colors_hex"))
                    color1 = st.color_picker(get_text("group1_color"), value="#37AB7B", key="scatter_color1")
                    color2 = st.color_picker(get_text("group2_color"), value="#F94141", key="scatter_color2")
                    color3 = st.color_picker(get_text("group3_color"), value="#589FF3", key="scatter_color3")
                
                # 隐藏的列名参数(使用默认值)
                green_x = "FACS(%)"
                green_y = "AI(%)"
                red_x = "FACS(%)"
                red_y = "Amplicon(%)"
                te_x = "AI(%)"
                te_y = "Amplicon(%)"
            
            clear_before = st.checkbox(get_text("scatter_clear_before"), value=False, key="scatter_clear_before")

            col1, col2 = st.columns(2)
            with col1:
                if st.button(get_text("save_files"), type="secondary", key="btn_save_scatter"):
                    if clear_before:
                        try:
                            for f in os.listdir(data_dir):
                                fp = os.path.join(data_dir, f)
                                if os.path.isfile(fp):
                                    os.remove(fp)
                        except Exception:
                            pass
                    saved = 0
                    if uploaded:
                        for uf in uploaded:
                            try:
                                dest = os.path.join(data_dir, uf.name)
                                with open(dest, "wb") as w:
                                    w.write(uf.getbuffer())
                                saved += 1
                            except Exception as e:
                                st.warning(get_text("save_failed").format(uf.name, e))
                    if saved:
                        st.success(get_text("uploaded_successfully").format(saved))
                    else:
                        st.info(get_text("no_files_selected"))
            with col2:
                if st.button(get_text("scatter_generate_btn"), type="primary", key="btn_run_scatter"):
                    with st.spinner(get_text("scatter_running")):
                        result = self.run_scatter_generation(
                            data_dir, out_dir,
                            green_x, green_y, red_x, red_y, te_x, te_y,
                            fig_width, fig_height, color1, color2, color3
                        )
                    if result.get("success", 0) > 0:
                        st.success(get_text("scatter_run_success"))
                        st.info(get_text("scatter_generated_files_count").format(result.get("success", 0)))
                        # 显示警告信息（如果有）
                        if result.get("errors"):
                            for err_msg in result.get("errors", []):
                                st.warning(err_msg)
                    else:
                        err = "; ".join(result.get("errors", [])) if result.get("errors") else ""
                        st.error(get_text("scatter_run_failed").format(err))

            # 预览生成文件（前10个）
            try:
                gen_files = []
                if os.path.isdir(out_dir):
                    for f in sorted(os.listdir(out_dir)):
                        if f.lower().endswith((".pdf", ".png")):
                            gen_files.append(os.path.join(out_dir, f))
                if gen_files:
                    st.markdown("---")
                    st.markdown(f"**{get_text('scatter_preview_title')}**")
                    for p in gen_files[:10]:
                        st.text(f"📄 {os.path.basename(p)}")
                else:
                    st.info(get_text("scatter_no_files"))
            except Exception:
                pass
        except Exception as e:
            st.warning(get_text("scatter_module_error").format(e))
    
    def run_scatter_generation(self, data_dir, out_dir, green_x, green_y, red_x, red_y, te_x, te_y, 
                               fig_width=12.0, fig_height=12.0, color1="#37AB7B", color2="#F94141", color3="#589FF3"):
        """批量读取CSV并生成线性回归散点图"""
        summary = {"success": 0, "failed": 0, "errors": []}
        try:
            if not os.path.isdir(data_dir):
                summary["errors"].append("data dir not found")
                return summary
            
            files = [f for f in os.listdir(data_dir)
                     if os.path.isfile(os.path.join(data_dir, f))
                     and f.lower().endswith(".csv")
                     and not f.startswith("~$")]
            
            if not files:
                return summary

            os.makedirs(out_dir, exist_ok=True)

            for fname in files:
                in_path = os.path.join(data_dir, fname)
                base = os.path.splitext(fname)[0]
                
                # 调用Correlation_scatter.py(使用绝对路径)
                try:
                    script_path = os.path.join(
                        os.path.dirname(os.path.abspath(__file__)),
                        "Code",
                        "Correlation_scatter.py"
                    )
                    cmd = [
                        sys.executable,
                        script_path,
                        os.path.abspath(in_path),
                        "--green-x", green_x,
                        "--green-y", green_y,
                        "--red-x", red_x,
                        "--red-y", red_y,
                        "--te-x", te_x,
                        "--te-y", te_y,
                        "--figsize-width", str(fig_width),
                        "--figsize-height", str(fig_height),
                        "--color1", color1,
                        "--color2", color2,
                        "--color3", color3,
                        "--output-dir", os.path.abspath(out_dir)
                    ]
                    
                    result = subprocess.run(
                        cmd,
                        capture_output=True,
                        text=True
                    )
                    
                    if result.returncode == 0:
                        summary["success"] += 1
                    else:
                        summary["failed"] += 1
                        summary["errors"].append(f"{fname}: {result.stderr[:200]}")
                except Exception as e:
                    summary["failed"] += 1
                    summary["errors"].append(f"{fname}: {str(e)}")
            
            return summary
        except Exception as e:
            summary["errors"].append(str(e))
            return summary

    def run_correlation_generation(self, data_dir, out_dir):
        """批量读取数据表并输出皮尔逊相关系数(r)热图到PDF"""
        summary = {"success": 0, "failed": 0, "errors": []}
        try:
            allowed = {".csv", ".tsv", ".txt", ".xls", ".xlsx"}
            if not os.path.isdir(data_dir):
                summary["errors"].append("data dir not found")
                return summary
            files = [f for f in os.listdir(data_dir)
                     if os.path.isfile(os.path.join(data_dir, f))
                     and os.path.splitext(f)[1].lower() in allowed
                     and not f.startswith("~$")]
            if not files:
                return summary

            os.makedirs(out_dir, exist_ok=True)

            for fname in files:
                in_path = os.path.join(data_dir, fname)
                base, _ = os.path.splitext(fname)
                
                # 调用Correlation_heatmap.py脚本(使用绝对路径)
                try:
                    script_path = os.path.join(
                        os.path.dirname(os.path.abspath(__file__)),
                        "Code",
                        "Correlation_heatmap.py"
                    )
                    cmd = [
                        sys.executable,
                        script_path,
                        os.path.abspath(in_path),
                        "--output-prefix", base,
                        "--output-dir", os.path.abspath(out_dir)
                    ]
                    
                    result = subprocess.run(
                        cmd,
                        capture_output=True,
                        text=True
                    )
                    
                    if result.returncode == 0:
                        summary["success"] += 1
                    else:
                        summary["failed"] += 1
                        summary["errors"].append(f"{fname}: {result.stderr[:200]}")
                except Exception as e:
                    summary["failed"] += 1
                    summary["errors"].append(f"{fname}: {str(e)}")
            return summary
        except Exception as e:
            summary["errors"].append(str(e))
            return summary

    def generate_charts(self, selected_charts, chart_options, colors, chart_params):
        """生成选中的图表"""
        try:
            lang = st.session_state.get('language', 'zh') # 获取当前语言
            total_charts = len(selected_charts)
            self.log_message(f"Starting to generate {total_charts} charts", "info")

            # 使用新的美化进度条容器
            st.markdown('<div class="progress-container">', unsafe_allow_html=True)
            status_text = st.empty()
            progress_bar = st.progress(0)
            chart_status_container = st.empty()
            
            # 创建图表状态显示
            chart_statuses = {chart_key: get_text("chart_status_waiting", lang) for chart_key in selected_charts}
            failed_charts_errors = [] # 新增：存储失败图表的错误信息
            
            def update_chart_status_display():
                status_lines = []
                for chart_key in selected_charts:
                    chart_name = chart_options[chart_key]['name']
                    status = chart_statuses[chart_key]
                    status_class = "chart-status-item "
                    if get_text("chart_generating", lang) in status:
                        status_class += "chart-status-generating"
                    elif get_text("chart_complete", lang) in status:
                        status_class += "chart-status-completed"
                    elif get_text("chart_status_failed", lang) in status:
                        status_class += "chart-status-failed"
                    else:
                        status_class += "chart-status-waiting"
                    status_lines.append(f"<div class='{status_class}'>{chart_name}: {status}</div>")
                chart_status_container.markdown("\n".join(status_lines), unsafe_allow_html=True)
            
            # 初始显示
            status_text.markdown(f'<div class="progress-status"><span class="progress-emoji">📊</span> {get_text("chart_prepare_generate").format(total_charts)}</div>', unsafe_allow_html=True)
            update_chart_status_display()
            
            import time
            start_time = time.time()

            for i, chart_key in enumerate(selected_charts):
                chart_info = chart_options[chart_key]
                
                # 更新当前图表状态
                chart_statuses[chart_key] = get_text("chart_generating", lang)
                status_text.markdown(f'<div class="progress-status"><span class="progress-emoji">⚙️</span> {get_text("chart_generating_progress").format(i+1, total_charts, chart_info["name"])}</div>', unsafe_allow_html=True)
                update_chart_status_display()
                
                # 更新进度条（开始生成时）
                progress_bar.progress((i + 0.5) / total_charts)

                success, error_msg = self.run_chart_script(chart_key, chart_info, colors, chart_params.get(chart_key, {}), lang)

                # 更新图表完成状态
                if success:
                    chart_statuses[chart_key] = get_text("chart_complete", lang)
                    self.log_message(f"Successfully generated: {chart_info['name']}", "success")
                else:
                    chart_statuses[chart_key] = get_text("chart_status_failed", lang)
                    self.log_message(f"Failed to generate: {chart_info['name']}", "error")
                    if error_msg:
                        failed_charts_errors.append(error_msg)

                # 更新进度条（完成时）
                progress_bar.progress((i + 1) / total_charts)
                update_chart_status_display()
                
                # 显示预计剩余时间
                if i < total_charts - 1:
                    elapsed_time = time.time() - start_time
                    avg_time_per_chart = elapsed_time / (i + 1)
                    remaining_charts = total_charts - (i + 1)
                    estimated_remaining = avg_time_per_chart * remaining_charts
                    
                    if estimated_remaining > 60:
                        time_str = f"{int(estimated_remaining // 60)} {get_text('time_min', lang)} {int(estimated_remaining % 60)} {get_text('time_sec', lang)}"
                    else:
                        time_str = f"{int(estimated_remaining)} {get_text('time_sec', lang)}"
                    
                    status_text.markdown(f'<div class="progress-status"><span class="progress-emoji">⏳</span> {get_text("chart_completed_progress").format(i+1, total_charts, time_str)}</div>', unsafe_allow_html=True)
            
            # 最终状态
            total_time = time.time() - start_time
            successful_charts = sum(1 for status in chart_statuses.values() if status == get_text("chart_complete", lang))
            
            if total_time > 60:
                time_str = f"{int(total_time // 60)} {get_text('time_min', lang)} {int(total_time % 60)} {get_text('time_sec', lang)}"
            else:
                time_str = f"{int(total_time)} {get_text('time_sec', lang)}"
            
            status_text.markdown(f'<div class="progress-status"><span class="progress-emoji">🎉</span> {get_text("chart_all_complete").format(successful_charts, total_charts, time_str)}</div>', unsafe_allow_html=True)
            st.markdown('</div>', unsafe_allow_html=True) # 关闭美化容器

            # 如果有失败的图表，显示所有错误信息
            if failed_charts_errors:
                st.markdown("### ⚠️ Chart Generation Failures")
                for error in failed_charts_errors:
                    st.error(error)

        except Exception as e:
            self.log_message(f"Chart generation failed: {str(e)}", "error")
            st.error(get_text("chart_generation_failed", lang).format(e))

    def run_chart_script(self, chart_key, chart_info, colors, specific_params, lang='zh'):
        """运行单个图表脚本"""
        try:
            # 获取图表的图大小参数
            figsize_width = specific_params.get('figsize_width', 10)
            figsize_height = specific_params.get('figsize_height', 6)
            
            # 确定输入和输出目录
            if chart_key == "Cell_Distribution_Scatter":
                # 细胞分布散点图使用Cellpose输出的CSV文件
                input_dir = os.path.join(st.session_state.work_dir, "Cellpose_output", "Cell_Counts")
            elif chart_key in ["Grouped_Bar", "Grouped_Box"]:
                # 柱状图和箱线图使用细胞分布散点图的输出
                input_dir = os.path.join(st.session_state.work_dir, "Chart", "Cell_Distribution_Scatter_Plot")
            else:  # Cell_Clustering_Scatter, Simulated_Flow_Cytometry
                # 聚类图和流式图使用荧光强度分析的输出
                input_dir = os.path.join(st.session_state.work_dir, "Cellpose_output", "Fluorescence_Intensity")

            # 新增：必要输入检查（Grouped_Bar/Grouped_Box 依赖 all_summary.csv）
            if chart_key in ["Grouped_Bar", "Grouped_Box"]:
                summary_csv = os.path.join(input_dir, "all_summary.csv")
                if not os.path.exists(summary_csv):
                    self.log_message(
                        f"Prerequisite missing for {chart_info['name']}: {summary_csv} not found. Please generate 'Cell Distribution Scatter Plot' first.",
                        "error"
                    )
                    return False

            output_dir = os.path.join(st.session_state.work_dir, "Chart", f"{chart_key}_Plot")

            # 确保输出目录存在
            os.makedirs(output_dir, exist_ok=True)

            # 构建命令
            cmd = [
                sys.executable, f"Code/{chart_info['script']}",
                "--input", input_dir,
                "--output", output_dir,
                "--figsize", str(figsize_width), str(figsize_height),
                "--colors"
            ]

            # 添加颜色参数
            if chart_key in ["Grouped_Bar", "Grouped_Box"]:
                # 柱状图和箱线图使用自定义颜色（如果有的话）
                if "custom_colors" in specific_params:
                    cmd.extend(specific_params["custom_colors"])
                else:
                    cmd.extend(colors[:3])  # 回退到通用颜色
            else:
                # 其他图表使用通用颜色
                cmd.extend(colors[:3])

            # 添加特定参数
            if "distance" in specific_params:
                cmd.extend(["--distance", str(specific_params["distance"])])
            
            # 添加语言参数
            cmd.extend(["--lang", lang])
            
            # Simulated_Flow_Cytometry 特定参数
            if chart_key == "Simulated_Flow_Cytometry":
                pass

            # 执行命令，指定编码避免Windows下的编码问题
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                encoding='utf-8',
                errors='ignore',  # 忽略编码错误
                cwd=os.getcwd()
            )

            # 新增：失败时输出详细日志
            if result.returncode != 0:
                error_message = f"Error running script **{chart_info['script']}**."
                self.log_message(
                    f"Chart script failed ({chart_info['script']}), return code {result.returncode}",
                    "error"
                )
                stderr_log = result.stderr.strip()
                if stderr_log:
                    self.log_message(f"stderr: {stderr_log}", "error")
                    error_message += f"\n\n**Error Details:**\n```\n{stderr_log}\n```"
                stdout_log = result.stdout.strip()
                if stdout_log:
                    self.log_message(f"stdout: {stdout_log}", "info")
                
                return False, error_message
            return True, None

        except Exception as e:
            error_message = f"An unexpected error occurred while trying to run {chart_info['script']}: {str(e)}"
            self.log_message(f"Chart script execution error: {str(e)}", "error")
            return False, error_message

    def render_step3(self):
        """渲染步骤3: 结果下载"""
        st.markdown(f'<h2 class="step-header">{get_text("step3_header")}</h2>', unsafe_allow_html=True)

        chart_dir = os.path.join(st.session_state.work_dir, "Chart")

        if not os.path.exists(chart_dir) or not os.listdir(chart_dir):
            st.warning(get_text("no_charts_generated"))
            return
        
        # 添加跳过选项
        st.success(get_text("charts_detected"))
        col1, col2 = st.columns([1, 1])
        with col1:
            if st.button(get_text("skip_step3_btn"), key="skip_step3_btn"):
                st.session_state.skip_step3 = True
                st.info(get_text("step3_skipped_preview"))
        with col2:
            if st.button(get_text("view_chart_preview_btn"), key="show_step3_btn"):
                st.session_state.skip_step3 = False
        
        # 如果选择跳过，则不显示预览
        if st.session_state.get('skip_step3', False):
            st.info(get_text("step3_skipped_info"))
            return

        st.subheader(get_text("preview_charts_title"))

        # 使用与AI报告相同的图表收集逻辑，确保预览和报告一致
        if AI_AVAILABLE:
            chart_previews_by_group = collect_chart_previews_by_group(st.session_state.work_dir, max_per_type=1)
        else:
            chart_previews_by_group = {}
        
        # 提取所有图表进行展示（按图表类型分组）
        previews = []  # [(category, image_path, target_info)]
        
        # 首先显示汇总图表（Grouped_Bar, Grouped_Box）
        if 'summary_charts' in chart_previews_by_group:
            summary = chart_previews_by_group['summary_charts']
            for chart_type, charts in summary.items():
                if charts:
                    chart = charts[0]  # 取第一个
                    display_cat = chart_type.replace('_', ' ')
                    previews.append((display_cat, chart['path'], "Summary"))
        
        # 然后显示按靶点的图表（选择一个代表性靶点）
        # 为每种图表类型选择一个靶点的图片作为代表
        chart_types_shown = set()
        for group_name, group_charts in chart_previews_by_group.items():
            if group_name == 'summary_charts':
                continue
            
            for chart_type, charts in group_charts.items():
                # 每种图表类型只显示一次（来自第一个遇到的靶点）
                if chart_type not in chart_types_shown and charts:
                    chart = charts[0]
                    display_cat = chart_type.replace('_', ' ')
                    target_info = chart.get('target', group_name)
                    previews.append((display_cat, chart['path'], f"Target: {target_info}"))
                    chart_types_shown.add(chart_type)

        if not previews:
            st.info(get_text("no_previewable_files"))
        else:
            # 美化预览布局：栅格卡片样式 + 统一标题与文件名展示
            st.markdown(
                """
                <style>
                .preview-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 16px; }
                @media (max-width: 1200px) { .preview-grid { grid-template-columns: repeat(2, 1fr); } }
                @media (max-width: 800px) { .preview-grid { grid-template-columns: 1fr; } }
                .preview-card { background: #fff; border: 1px solid #e6ebf2; border-radius: 10px; padding: 12px; box-shadow: 0 4px 12px rgba(0,0,0,0.06); }
                .preview-title { font-size: 18px; color: #2c3e50; margin: 4px 0 10px 0; font-weight: 600; }
                .preview-img { width: 100%; height: auto; border-radius: 8px; border: 1px solid #d8dee9; box-shadow: 0 2px 8px rgba(0,0,0,0.05); }
                .preview-meta { font-size: 14px; color: #6b7280; margin-top: 8px; }
                .file-pill { display: inline-block; padding: 6px 10px; border-radius: 6px; background: #f3f4f6; color: #374151; border: 1px solid #e5e7eb; }
                </style>
                """,
                unsafe_allow_html=True,
            )

            import base64
            cards_html = ["<div class='preview-grid'>"]
            for (cat, img_path, target_info) in previews:
                try:
                    if img_path.lower().endswith((".png", ".jpg", ".jpeg")) and os.path.exists(img_path):
                        with open(img_path, "rb") as f:
                            b64 = base64.b64encode(f.read()).decode("utf-8")
                        mime = "image/png" if img_path.lower().endswith(".png") else "image/jpeg"
                        cards_html.append(
                            f"<div class='preview-card'>"
                            f"<div class='preview-title'>{cat}</div>"
                            f"<img class='preview-img' src='data:{mime};base64,{b64}' alt='{cat}'>"
                            f"<div class='preview-meta'>{target_info} • {os.path.basename(img_path)}</div>"
                            f"</div>"
                        )
                    else:
                        # 非图片文件（如 PDF）统一卡片展示
                        cards_html.append(
                            f"<div class='preview-card'>"
                            f"<div class='preview-title'>{cat}</div>"
                            f"<div class='file-pill'>📄 {os.path.basename(img_path)}</div>"
                            f"<div class='preview-meta'>{target_info}</div>"
                            f"</div>"
                        )
                except Exception as e:
                    cards_html.append(
                        f"<div class='preview-card'>"
                        f"<div class='preview-title'>{cat}</div>"
                        f"<div class='file-pill'>⚠️ {get_text('could_not_display').format(os.path.basename(img_path), e)}</div>"
                        f"</div>"
                    )
            cards_html.append("</div>")
            st.markdown("\n".join(cards_html), unsafe_allow_html=True)

        # 新增：相关性热图输出预览
        corr_out_dir = os.path.join(st.session_state.work_dir, "correlation", "output")
        try:
            corr_files = []
            if os.path.isdir(corr_out_dir):
                for f in sorted(os.listdir(corr_out_dir)):
                    if f.lower().endswith(('.pdf', '.png', '.jpg', '.jpeg')):
                        corr_files.append(os.path.join(corr_out_dir, f))
            st.subheader(get_text("correlation_preview_title"))
            if corr_files:
                # 统一使用同样的卡片栅格样式
                import base64
                corr_html = ["<div class='preview-grid'>"]
                for p in corr_files[:12]:
                    try:
                        if p.lower().endswith((".png", ".jpg", ".jpeg")) and os.path.exists(p):
                            with open(p, "rb") as f:
                                b64 = base64.b64encode(f.read()).decode("utf-8")
                            mime = "image/png" if p.lower().endswith(".png") else "image/jpeg"
                            corr_html.append(
                                f"<div class='preview-card'>"
                                f"<div class='preview-title'>{os.path.basename(p)}</div>"
                                f"<img class='preview-img' src='data:{mime};base64,{b64}' alt='{os.path.basename(p)}'>"
                                f"</div>"
                            )
                        else:
                            corr_html.append(
                                f"<div class='preview-card'>"
                                f"<div class='file-pill'>📄 {os.path.basename(p)}</div>"
                                f"</div>"
                            )
                    except Exception as e:
                        corr_html.append(
                            f"<div class='preview-card'>"
                            f"<div class='file-pill'>⚠️ {get_text('could_not_display').format(os.path.basename(p), e)}</div>"
                            f"</div>"
                        )
                corr_html.append("</div>")
                st.markdown("\n".join(corr_html), unsafe_allow_html=True)
            else:
                st.info(get_text("correlation_no_files"))
        except Exception as e:
            st.warning(get_text("correlation_preview_error").format(e))

        st.subheader(get_text("download_results_title"))

        col1, col2 = st.columns(2)

        with col1:
            # 下载所有图表
            if st.button(get_text("download_all_charts")):
                zip_data = self.create_charts_zip()
                if zip_data:
                    st.download_button(
                        label=get_text("download_charts_zip"),
                        data=zip_data,
                        file_name="easyreporter_charts.zip",
                        mime="application/zip"
                    )

        with col2:
            # 下载处理数据
            if st.button(get_text("download_processed_data")):
                zip_data = self.create_data_zip()
                if zip_data:
                    st.download_button(
                        label=get_text("download_data_zip"),
                        data=zip_data,
                        file_name="easyreporter_data.zip",
                        mime="application/zip"
                    )

        # 单独文件下载
        st.subheader(get_text("individual_download_title"))

        # 列出所有可下载的文件
        all_files = []

        # 添加图表文件
        for root, dirs, files in os.walk(chart_dir):
            for file in files:
                file_path = os.path.join(root, file)
                rel_path = os.path.relpath(file_path, st.session_state.work_dir)
                all_files.append((rel_path, file_path))

        # 新增：添加相关性热图输出文件
        corr_out_dir = os.path.join(st.session_state.work_dir, "correlation", "output")
        if os.path.exists(corr_out_dir):
            for root, dirs, files in os.walk(corr_out_dir):
                for file in files:
                    file_path = os.path.join(root, file)
                    rel_path = os.path.relpath(file_path, st.session_state.work_dir)
                    all_files.append((rel_path, file_path))

        # 添加数据文件
        data_dirs = [
            "Cellpose_output",
        ]

        for data_dir in data_dirs:
            full_data_dir = os.path.join(st.session_state.work_dir, data_dir)
            if os.path.exists(full_data_dir):
                for root, dirs, files in os.walk(full_data_dir):
                    for file in files:
                        if file.endswith(('.csv', '.txt')):
                            file_path = os.path.join(root, file)
                            rel_path = os.path.relpath(file_path, st.session_state.work_dir)
                            all_files.append((rel_path, file_path))

        if all_files:
            selected_file = st.selectbox(
                get_text("select_file_download"),
                options=[f[0] for f in all_files],
                format_func=lambda x: x
            )

            if selected_file:
                file_path = next(f[1] for f in all_files if f[0] == selected_file)

                try:
                    with open(file_path, 'rb') as f:
                        file_data = f.read()

                    st.download_button(
                        label=get_text("download_file").format(os.path.basename(selected_file)),
                        data=file_data,
                        file_name=os.path.basename(selected_file),
                        mime="application/octet-stream"
                    )
                except Exception as e:
                    st.error(get_text("failed_read_file").format(str(e)))

        else:
            st.info(get_text("no_charts_complete_step2"))


    def run_ai_interpretation(self):
        """执行AI智能解读：分层结构 - 单蛋白分析 + 综合分析"""
        try:
            self.log_message("Starting structured AI interpretation...", "info")
            
            # 创建AI解读进度条
            ai_progress = st.progress(0)
            ai_status = st.empty()
            
            ai_status.text(get_text("ai_preparing"))
            ai_progress.progress(0.1)

            # 1) 汇总数据
            data_summary = summarize_data_for_ai(st.session_state.work_dir, lang=st.session_state.get('language', 'zh'))
            if not data_summary:
                ai_status.text(get_text("no_data_for_ai"))
                st.warning(get_text("no_data_for_ai"))
                return
            
            ai_status.text(get_text("ai_summary_complete_layered"))
            ai_progress.progress(0.2)

            # 2) 使用新的分层AI解读逻辑
            ai_status.text(get_text("ai_generating_layered_report"))
            
            # 设置速率限制
            base_url_val = st.session_state.get("ai_base_url", "")
            is_openai = (not base_url_val) or ("openai.com" in base_url_val.lower())
            min_interval_sec = st.session_state.get("ai_rate_limit_sec", 21 if is_openai else 0)
            
            if is_openai and min_interval_sec >= 10:
                st.info(get_text("ai_rate_limit_info").format(min_interval_sec))

            with st.spinner(get_text("ai_generating_layered_report")):
                try:
                    # 调用按组别分析的AI解读函数
                    chart_previews_by_group = collect_chart_previews_by_group(st.session_state.work_dir, max_per_type=2)
                    
                    # 如果用户为每个蛋白选择了特定数据，则只传递这些数据给报告生成函数
                    selected_per_protein = st.session_state.get('selected_data_per_protein', {})
                    if selected_per_protein:
                        import re
                        # 构建只包含选中数据的chart_previews
                        filtered_previews = {}
                        
                        print(f"\n[DEBUG] ========== 开始过滤图表 ==========")
                        print(f"[DEBUG] selected_per_protein: {selected_per_protein}")
                        print(f"[DEBUG] chart_previews_by_group keys: {list(chart_previews_by_group.keys())}")
                        
                        for protein, selected_data_id in selected_per_protein.items():
                            print(f"\n[DEBUG] 处理蛋白: {protein}, 选择的data_id: {selected_data_id}")
                            # selected_data_id格式如 "cas9-sg10_1-4" (蛋白-靶点_重复-视野)
                            # chart_previews_by_group的key格式如 "cas9-sg10"
                            # 图表文件名格式：cas9-sg10_1-4_analysis.png
                            match = re.match(r'(cas\d+-sg\d+|wt)[_-](\d+)[_-](\d+)', selected_data_id, re.IGNORECASE)
                            if match:
                                group_key = match.group(1).lower()
                                replicate_number = match.group(2)  # 重复次数：如 "1", "2", "3"
                                field_number = match.group(3)  # 视野编号：如 "1", "4"
                                
                                print(f"[DEBUG] 提取: group_key={group_key}, replicate={replicate_number}, field={field_number}")
                                
                                # 在chart_previews_by_group中查找匹配的key
                                for key in chart_previews_by_group.keys():
                                    if key != 'summary_charts' and key.lower() == group_key:
                                        print(f"[DEBUG] 找到匹配的组: {key}")
                                        # 找到组后，过滤该组内的图表，只保留该重复和视野的文件
                                        group_data = chart_previews_by_group[key]
                                        print(f"[DEBUG]   group_data的keys: {list(group_data.keys())}")
                                        filtered_group_data = {}
                                        
                                        # group_data结构：{chart_type: [{path, ext, filename}, ...]}
                                        for chart_type, chart_list in group_data.items():
                                            filtered_charts = []
                                            print(f"[DEBUG]   检查图表类型: {chart_type}, 共{len(chart_list)}张")
                                            for chart_info in chart_list:
                                                filename = chart_info.get('filename', '')
                                                # 匹配多种文件名格式:
                                                # 1. cas9-sg10_1-1_analysis.png (重复-视野用连字符)
                                                # 2. cas9-sg10_1_1_combined_plot.png (重复_视野用下划线)
                                                # 3. cas9-sg10_1_1_combined.png (重复_视野用下划线)
                                                # 4. cas12-sg1_1_EGFP-1.tif (原始图片格式)
                                                
                                                # Pattern1: 连字符格式 cas9-sg10_1-1_
                                                pattern1 = rf'{group_key}_{replicate_number}-{field_number}[._]'
                                                # Pattern2: 下划线格式 cas9-sg10_1_1_
                                                pattern2 = rf'{group_key}_{replicate_number}_{field_number}[._]'
                                                # Pattern3: 原始图片格式 cas12-sg1_1_xxx-1
                                                pattern3 = rf'{group_key}_{replicate_number}_.*?-{field_number}[._]'
                                                
                                                match1 = re.search(pattern1, filename, re.IGNORECASE)
                                                match2 = re.search(pattern2, filename, re.IGNORECASE)
                                                match3 = re.search(pattern3, filename, re.IGNORECASE)
                                                
                                                print(f"[DEBUG]     文件: {filename}")
                                                print(f"[DEBUG]       pattern1({pattern1})匹配: {bool(match1)}")
                                                print(f"[DEBUG]       pattern2({pattern2})匹配: {bool(match2)}")
                                                print(f"[DEBUG]       pattern3匹配: {bool(match3)}")
                                                
                                                if match1 or match2 or match3:
                                                    filtered_charts.append(chart_info)
                                                    print(f"[DEBUG]       ✓ 保留此文件")
                                            
                                            if filtered_charts:
                                                filtered_group_data[chart_type] = filtered_charts
                                                print(f"[DEBUG]   保留了{len(filtered_charts)}张{chart_type}图表")
                                        
                                        if filtered_group_data:
                                            filtered_previews[key] = filtered_group_data
                                            print(f"[DEBUG] ✓ 添加到filtered_previews: {key}, 包含{len(filtered_group_data)}种图表类型")
                                        break
                        
                        # 保留summary_charts（柱状图/箱线图）
                        if 'summary_charts' in chart_previews_by_group:
                            filtered_previews['summary_charts'] = chart_previews_by_group['summary_charts']
                            print(f"[DEBUG] 保留summary_charts")
                        
                        print(f"\n[DEBUG] 过滤后的keys: {list(filtered_previews.keys())}")
                        print(f"[DEBUG] ========== 过滤完成 ==========\n")
                        
                        chart_previews_for_report = filtered_previews
                    else:
                        chart_previews_for_report = chart_previews_by_group

                    # 相同数据、图表选择、语言和模型直接复用首次生成结果，
                    # 保证重复生成时报告逐字一致。
                    report_cache_key = self._build_ai_report_cache_key(
                        data_summary,
                        chart_previews_for_report,
                    )
                    cached_report = self._load_cached_ai_report(report_cache_key)
                    if cached_report:
                        lang = st.session_state.get('language', 'zh')
                        cached_report = self._normalize_ai_report_title(cached_report, lang)
                        st.session_state.ai_report = cached_report
                        st.session_state.ai_report_failed = False
                        st.session_state.show_local_option = False
                        ai_progress.progress(1.0)
                        ai_status.text(get_text("ai_reused_report_status", lang))
                        self.log_message(get_text("ai_reused_report_status", lang), "success")
                        st.info(get_text("ai_reused_report_info", lang))
                        return

                    response_stream = generate_ai_report_by_group(
                        st.session_state.openai_api_key,
                        data_summary,
                        base_url=st.session_state.get("ai_base_url"),
                        model=st.session_state.get("ai_model"),
                        chart_previews_by_group=chart_previews_for_report,
                        lang=st.session_state.get('language', 'zh')
                    )

                    if response_stream:
                        from AI_helper import format_target_for_display
                        report_container = st.empty()
                        full_report = ""
                        for chunk in response_stream:
                            try:
                                delta = chunk.choices[0].delta
                                content = getattr(delta, "content", None)
                                if content:
                                    full_report += content
                                    # 实时格式化显示（sg → site）
                                    formatted_display = format_target_for_display(full_report)
                                    report_container.markdown(formatted_display)
                            except Exception:
                                continue
                        
                        if full_report.strip():
                            lang = st.session_state.get('language', 'zh')
                            full_report = self._normalize_ai_report_title(full_report, lang)
                            # 存储统一标题后的内容，并将其缓存供同一输入复用。
                            st.session_state.ai_report = full_report
                            self._save_cached_ai_report(report_cache_key, full_report)
                            report_container.markdown(format_target_for_display(full_report))
                            st.session_state.ai_report_failed = False
                            st.session_state.show_local_option = False
                            ai_status.text(get_text("ai_layered_complete"))
                            ai_progress.progress(1.0)
                            self.log_message(get_text("ai_interpretation_success_log"), "success")
                        else:
                            st.session_state.ai_report_failed = True
                            st.session_state.show_local_option = True
                            st.error(get_text("ai_no_valid_content"))
                            ai_status.text(get_text("ai_interpretation_failed"))
                    else:
                        st.session_state.ai_report_failed = True
                        st.session_state.show_local_option = True
                        ai_status.text(get_text("ai_interpretation_failed"))
                        
                except Exception as e:
                    self.log_message(get_text("ai_layered_error").format(str(e)), "error")
                    st.session_state.ai_report_failed = True
                    st.session_state.show_local_option = True
                    st.error(get_text("ai_layered_error").format(e))
                    ai_status.text(get_text("ai_generation_error_status"))
                    
        except Exception as e:
            self.log_message(get_text("ai_process_error").format(str(e)), "error")
            st.error(get_text("ai_process_error").format(str(e)))





    def render_step4(self):
        """渲染步骤4: AI解读"""
        st.markdown(f'<h2 class="step-header">{get_text("step4_header")}</h2>', unsafe_allow_html=True)

        st.info(get_text("step4_info"))

        # 提供方与模型设置
        if 'ai_provider' not in st.session_state:
            st.session_state.ai_provider = 'DeepSeek'
        if 'ai_base_url' not in st.session_state:
            st.session_state.ai_base_url = 'https://api.deepseek.com/v1'
        if 'ai_model' not in st.session_state:
            st.session_state.ai_model = 'deepseek-chat'

        st.subheader(get_text("config_provider_api"))
        colp1, colp2, colp3 = st.columns([1.2, 1.8, 1.2])
        with colp1:
            provider = st.selectbox(
                get_text("select_provider"),
                options=["OpenAI", "Kimi (Moonshot)", "DeepSeek"],
                index=0 if st.session_state.ai_provider == 'OpenAI' else (1 if st.session_state.ai_provider == 'Kimi (Moonshot)' else 2),
                help=get_text("provider_help"),
                key="ai_provider_select"
            )
            if provider != st.session_state.ai_provider:
                st.session_state.ai_provider = provider
                # 切换默认 base_url & model（仅在切换时覆盖，用户手动调整后不再覆盖）
                if provider.startswith("OpenAI"):
                    st.session_state.ai_base_url = 'https://api.openai.com/v1'
                    st.session_state.ai_model = 'gpt-3.5-turbo'
                elif provider.startswith("Kimi"):
                    st.session_state.ai_base_url = 'https://api.moonshot.cn/v1'
                    st.session_state.ai_model = 'moonshot-v1-8k'
                else:  # DeepSeek
                    st.session_state.ai_base_url = 'https://api.deepseek.com/v1'
                    st.session_state.ai_model = 'deepseek-chat'
        with colp2:
            st.session_state.ai_base_url = st.text_input(
                get_text("base_url_label"),
                value=st.session_state.ai_base_url,
                help=get_text("base_url_help")
            )
        with colp3:
            st.session_state.ai_model = st.text_input(
                get_text("model_name_label"),
                value=st.session_state.ai_model,
                help=get_text("model_name_help")
            )

        # API Key显示（已固定）
        if st.session_state.ai_provider == 'OpenAI':
            api_label = get_text("enter_openai_key")
            api_help = get_text("api_key_help_openai")
        elif st.session_state.ai_provider == 'Kimi (Moonshot)':
            api_label = get_text("enter_kimi_key")
            api_help = get_text("api_key_help_kimi")
        else:  # DeepSeek
            api_label = get_text("enter_deepseek_key")
            api_help = get_text("api_key_help_deepseek")
        
        # 显示固定的API密钥（部分隐藏）
        masked_key = st.session_state.openai_api_key[:8] + "*" * 20 + st.session_state.openai_api_key[-8:] if st.session_state.openai_api_key else ""
        st.text_input(
            api_label,
            value=masked_key,
            disabled=True,
            help=api_help
        )
        
        # 显示固定密钥的提示信息
        if st.session_state.ai_provider == 'DeepSeek':
            st.success(get_text("api_key_fixed_success"))



        # 报告生成
        st.subheader(get_text("generate_analysis_report"))
        # 让用户为每个蛋白的每个靶点选择用于报告的数据组
        try:
            from AI_helper import collect_all_charts_info, group_charts_by_protein_and_target
            all_charts = collect_all_charts_info(st.session_state.work_dir)
            
            # 调试：显示收集到的图表信息
            if all_charts:
                st.info(get_text("charts_collected_info").format(len(all_charts), sum(len(v) for v in all_charts.values())))
            else:
                st.warning(get_text("no_charts_warning"))
            
            protein_target_groups = group_charts_by_protein_and_target(all_charts)
            
            # 调试：显示蛋白→靶点分组信息
            if protein_target_groups:
                total_proteins = len(protein_target_groups)
                total_targets = sum(len(targets) for targets in protein_target_groups.values())
                st.success(get_text("proteins_targets_found").format(total_proteins, total_targets))
                for prot, targets in protein_target_groups.items():
                    st.write(get_text("protein_targets_detail").format(prot.upper(), len(targets), ', '.join(targets.keys())))
            else:
                st.warning(get_text("no_protein_groups_warning"))
            
            # 为每个蛋白的每个靶点创建独立的选择器
            if protein_target_groups:
                st.markdown(get_text("select_data_per_target_title"))
                st.caption(get_text("select_data_hint"))
                
                # 初始化选择状态：{protein: {target: data_id}}
                # 清理旧的数据结构（如果存在的话）
                if 'selected_data_per_target' not in st.session_state:
                    st.session_state.selected_data_per_target = {}
                else:
                    # 验证数据结构是否正确，如果不正确则重置
                    if not isinstance(st.session_state.selected_data_per_target, dict):
                        st.session_state.selected_data_per_target = {}
                    else:
                        # 检查每个值是否都是字典
                        for key, value in list(st.session_state.selected_data_per_target.items()):
                            if not isinstance(value, dict):
                                # 如果发现旧的数据结构，清空重新开始
                                st.session_state.selected_data_per_target = {}
                                break
                
                for protein in sorted(protein_target_groups.keys()):
                    targets_dict = protein_target_groups[protein]
                    protein_display = protein.capitalize()  # Cas9, Cas12
                    
                    # 为每个蛋白创建一个expander
                    with st.expander(get_text("protein_expander_title").format(protein_display, len(targets_dict)), expanded=True):
                        if protein not in st.session_state.selected_data_per_target:
                            st.session_state.selected_data_per_target[protein] = {}
                        
                        # 为每个靶点创建选择器
                        for target in sorted(targets_dict.keys(), key=lambda x: int(x[2:])):  # 按sg1, sg2, sg3排序
                            data_ids_dict = targets_dict[target]
                            data_ids = list(data_ids_dict.keys())
                            
                            if data_ids:
                                col1, col2 = st.columns([1, 4])
                                with col1:
                                    st.markdown(f"**{target.upper()}:**")
                                with col2:
                                    default_idx = 0
                                    if target in st.session_state.selected_data_per_target.get(protein, {}):
                                        try:
                                            default_idx = data_ids.index(st.session_state.selected_data_per_target[protein][target])
                                        except (ValueError, KeyError):
                                            default_idx = 0
                                    
                                    selected = st.selectbox(
                                        get_text("select_data_for").format(protein_display, target.upper()),
                                        options=data_ids,
                                        index=default_idx,
                                        key=f'select_{protein}_{target}',
                                        label_visibility="collapsed"
                                    )
                                    st.session_state.selected_data_per_target[protein][target] = selected
                                    st.caption(get_text("selected_caption").format(selected))
                
                # 显示当前选择摘要
                if st.session_state.selected_data_per_target:
                    total_selected = sum(len(targets) if isinstance(targets, dict) else 0 
                                       for targets in st.session_state.selected_data_per_target.values())
                    st.success(get_text("targets_selected_success").format(total_selected))
                    
                    # 显示详细选择信息
                    summary_lines = []
                    for prot, targets in sorted(st.session_state.selected_data_per_target.items()):
                        if isinstance(targets, dict):
                            target_info = [f"{t.upper()}={d}" for t, d in sorted(targets.items())]
                            summary_lines.append(f"{prot.capitalize()}: {', '.join(target_info)}")
                    if summary_lines:
                        st.caption(get_text("current_selection_caption") + " | ".join(summary_lines))
            else:
                # 没有找到分组数据
                if 'selected_data_per_target' in st.session_state:
                    del st.session_state['selected_data_per_target']
        except Exception as e:
            st.warning(get_text("load_group_failed").format(e))
            import traceback
            st.code(traceback.format_exc())
            protein_target_groups = {}
            if 'selected_data_per_target' in st.session_state:
                del st.session_state['selected_data_per_target']

        generate_button = st.button(get_text("btn_generate_ai_report"), disabled=not st.session_state.openai_api_key)


        # 重试按钮（在失败后显示）
        if st.session_state.get("ai_report_failed", False):
            col1, col2, col3 = st.columns([1, 2, 1])
            with col2:
                if st.button(get_text("retry_ai_analysis"), key="retry_ai"):
                    st.session_state.ai_report_failed = False
                    self.run_ai_interpretation()

        # 使用简化报告按钮
        if st.session_state.get("show_local_option", False):
            col1, col2, col3 = st.columns([1, 2, 1])
            with col2:
                if st.button(get_text("use_local_report"), key="use_local"):
                    from AI_helper import generate_local_report
                    # 生成本地文本型报告
                    local_report = generate_local_report(st.session_state.work_dir, lang=st.session_state.get('language', 'zh'))
                    # 生成包含图片的HTML报告（保持原有样式）
                    try:
                        html_report = self.create_html_report_with_images(
                            st.session_state.get('language', 'zh'),
                            html_paged=True,
                        )
                    except Exception:
                        html_report = None

                    if local_report:
                        # 优先保存可显示的HTML报告到 session（若可用），否则保存文本报告
                        if html_report:
                            st.session_state.ai_report_html = html_report
                            st.session_state.ai_report = local_report  # 保留文本备份
                        else:
                            st.session_state.ai_report = local_report
                            if 'ai_report_html' in st.session_state:
                                del st.session_state['ai_report_html']

                        st.session_state.ai_report_failed = False
                        st.session_state.show_local_option = False
                        st.rerun()

        if generate_button:
            self.run_ai_interpretation()

        # 显示报告
        if st.session_state.ai_report:
            from AI_helper import format_target_for_display
            st.subheader(get_text("ai_analysis_report"))
            # 如果有HTML版本的报告（包含图片），优先显示并允许HTML渲染
            if st.session_state.get('ai_report_html'):
                # 完整HTML报告在隔离iframe中运行，确保分页脚本和报告CSS生效。
                import streamlit.components.v1 as components
                components.html(
                    st.session_state.get('ai_report_html'),
                    height=1100,
                    scrolling=True,
                )
            else:
                # 格式化显示（sg → site）
                formatted_report = format_target_for_display(st.session_state.ai_report)
                st.markdown(formatted_report)
            
            # 下载选项
            col1, col2, col3 = st.columns([1, 1, 1])
            with col1:
                # 生成包含图片的HTML报告（保持原有样式）
                html_report = self.create_html_report_with_images(
                    st.session_state.get('language', 'zh'),
                    html_paged=True,
                )
                st.download_button(
                    label=get_text("download_html_report"),
                    data=html_report,
                    file_name="ai_analysis_report_with_images.html",
                    mime="text/html"
                )
            
            with col3:
                # 生成PDF报告
                try:
                    pdf_path = self.create_pdf_report_with_images()
                    if pdf_path and os.path.exists(pdf_path):
                        # 读取PDF文件数据
                        with open(pdf_path, 'rb') as f:
                            pdf_data = f.read()
                        st.download_button(
                            label=get_text("download_pdf_report"),
                            data=pdf_data,
                            file_name="ai_analysis_report_with_images.pdf",
                            mime="application/pdf"
                        )
                    else:
                        st.error(get_text("pdf_generation_failed"))
                except Exception as e:
                    st.error(get_text("pdf_generation_error").format(str(e)))
                    st.info(get_text("use_html_version"))
            

            



    def create_charts_zip(self):
        """创建图表文件的ZIP压缩包"""
        try:
            chart_dir = os.path.join(st.session_state.work_dir, "Chart")

            if not os.path.exists(chart_dir):
                return None

            # 创建内存中的ZIP文件
            from io import BytesIO
            zip_buffer = BytesIO()

            with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
                for root, dirs, files in os.walk(chart_dir):
                    for file in files:
                        file_path = os.path.join(root, file)
                        arc_name = os.path.relpath(file_path, chart_dir)
                        zip_file.write(file_path, arc_name)

            zip_buffer.seek(0)
            return zip_buffer.getvalue()

        except Exception as e:
            self.log_message(f"Failed to create charts ZIP: {str(e)}", "error")
            return None

    def create_data_zip(self):
        """创建数据文件的ZIP压缩包"""
        try:
            # 创建内存中的ZIP文件
            from io import BytesIO
            zip_buffer = BytesIO()

            with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
                # 添加Cellpose输出
                cellpose_dir = os.path.join(st.session_state.work_dir, "Cellpose_output")
                if os.path.exists(cellpose_dir):
                    for root, dirs, files in os.walk(cellpose_dir):
                        for file in files:
                            if file.endswith(('.csv', '.txt', '.npy')):
                                file_path = os.path.join(root, file)
                                arc_name = os.path.relpath(file_path, st.session_state.work_dir)
                                zip_file.write(file_path, arc_name)

            zip_buffer.seek(0)
            return zip_buffer.getvalue()

        except Exception as e:
            self.log_message(f"Failed to create data ZIP: {str(e)}", "error")
            return None

    @staticmethod
    def _normalize_ai_report_title(report_text, lang='zh'):
        """确保每份 AI 报告只有一个固定的一级标题。"""
        if not report_text or not report_text.strip():
            return ""

        import re

        title = (
            "# Comprehensive Analysis Report: Dual-Fluorescence Reporter Gene Editing Efficiency Evaluation"
            if lang == 'en'
            else "# 综合分析报告：双荧光报告基因编辑效率评估"
        )
        lines = report_text.replace('\r\n', '\n').replace('\r', '\n').split('\n')

        # 清除模型偶尔在报告首尾输出的 Markdown 分隔线。
        while lines and (not lines[0].strip() or re.fullmatch(r'(?:-{3,}|\*{3,}|_{3,})', lines[0].strip())):
            lines.pop(0)
        while lines and (not lines[-1].strip() or re.fullmatch(r'(?:-{3,}|\*{3,}|_{3,})', lines[-1].strip())):
            lines.pop()

        normalized = []
        found_h1 = False
        for line in lines:
            if re.match(r'^#(?!#)\s+', line.strip()):
                if not found_h1:
                    normalized.append(title)
                    found_h1 = True
                else:
                    # 额外一级标题降为二级，避免报告出现多个主标题。
                    normalized.append('#' + line)
            else:
                normalized.append(line)

        if not found_h1:
            normalized = [title, ""] + normalized

        return '\n'.join(normalized).strip()

    @staticmethod
    def _report_chart_manifest(chart_previews_by_group, work_dir):
        """提取实际传给 AI 的图表清单，用于生成稳定缓存指纹。"""
        manifest = []
        for group_name in sorted((chart_previews_by_group or {}).keys()):
            group_data = chart_previews_by_group.get(group_name) or {}
            if not isinstance(group_data, dict):
                continue
            for chart_type in sorted(group_data.keys()):
                charts = group_data.get(chart_type) or []
                if isinstance(charts, dict):
                    charts = [charts]
                for chart in charts:
                    if not isinstance(chart, dict):
                        continue
                    chart_path = chart.get('path', '')
                    try:
                        display_path = os.path.relpath(chart_path, work_dir) if chart_path else ''
                    except Exception:
                        display_path = chart_path
                    manifest.append({
                        "group": group_name,
                        "chart_type": chart_type,
                        "path": display_path.replace('\\', '/'),
                        "filename": chart.get('filename') or os.path.basename(chart_path),
                    })
        manifest.sort(key=lambda item: (
            item["group"], item["chart_type"], item["path"], item["filename"]
        ))
        return manifest

    def _build_ai_report_cache_key(self, data_summary, chart_previews_by_group):
        """根据 AI 的全部有效输入生成报告缓存键。"""
        payload = {
            # 提示词或规范化逻辑变更时递增，避免误用旧报告。
            "cache_version": "report-v4-20260815",
            "data_summary": data_summary,
            "charts": self._report_chart_manifest(chart_previews_by_group, st.session_state.work_dir),
            "language": st.session_state.get('language', 'zh'),
            "provider": st.session_state.get('ai_provider', ''),
            "base_url": st.session_state.get('ai_base_url', ''),
            "model": st.session_state.get('ai_model', ''),
            "selected_data_per_target": st.session_state.get('selected_data_per_target', {}),
            "selected_data_per_protein": st.session_state.get('selected_data_per_protein', {}),
        }
        canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(',', ':'), default=str)
        return hashlib.sha256(canonical.encode('utf-8')).hexdigest()

    def _ai_report_cache_path(self, cache_key):
        cache_dir = os.path.join(st.session_state.work_dir, "report_cache")
        return os.path.join(cache_dir, f"{cache_key}.json")

    def _load_cached_ai_report(self, cache_key):
        cache_path = self._ai_report_cache_path(cache_key)
        if not os.path.isfile(cache_path):
            return None
        try:
            with open(cache_path, 'r', encoding='utf-8') as cache_file:
                cached = json.load(cache_file)
            if cached.get('cache_key') != cache_key:
                return None
            report = cached.get('report', '')
            return report if isinstance(report, str) and report.strip() else None
        except Exception as e:
            self.log_message(f"Failed to read AI report cache: {str(e)}", "warning")
            return None

    def _save_cached_ai_report(self, cache_key, report_text):
        cache_path = self._ai_report_cache_path(cache_key)
        cache_dir = os.path.dirname(cache_path)
        os.makedirs(cache_dir, exist_ok=True)
        temp_path = cache_path + ".tmp"
        payload = {
            "cache_key": cache_key,
            "report": report_text,
            "language": st.session_state.get('language', 'zh'),
            "provider": st.session_state.get('ai_provider', ''),
            "model": st.session_state.get('ai_model', ''),
        }
        try:
            with open(temp_path, 'w', encoding='utf-8') as cache_file:
                json.dump(payload, cache_file, ensure_ascii=False, indent=2)
            os.replace(temp_path, cache_path)
        except Exception as e:
            self.log_message(f"Failed to save AI report cache: {str(e)}", "warning")
            try:
                if os.path.exists(temp_path):
                    os.remove(temp_path)
            except Exception:
                pass

    @staticmethod
    def _normalize_report_math(text):
        """将报告中的 LaTeX 公式降级为可直接打印的纯文本。"""
        if not text:
            return ""

        import re

        def replace_formula(match):
            formula = match.group(1).strip()
            formula_lower = formula.lower()

            # 报告中最常见的编辑效率公式，使用固定文本保证稳定显示。
            if "efficiency" in formula_lower and "gfp-only" in formula_lower and "overlap" in formula_lower:
                return "Target Efficiency = GFP-only / (GFP-only + Overlap) × 100%"

            # 对其他简单 LaTeX 做通用降级，避免将反斜杠命令原样打印。
            plain = re.sub(r'\\(?:text|mathrm)\{([^{}]*)\}', r'\1', formula)
            previous = None
            while previous != plain:
                previous = plain
                plain = re.sub(r'\\frac\{([^{}]+)\}\{([^{}]+)\}', r'(\1) / (\2)', plain)
            replacements = {
                r'\times': '×',
                r'\cdot': '·',
                r'\%': '%',
                r'\pm': '±',
                r'\le': '≤',
                r'\ge': '≥',
            }
            for source, target in replacements.items():
                plain = plain.replace(source, target)
            plain = plain.replace('{', '').replace('}', '')
            plain = re.sub(r'\\([A-Za-z]+)', r'\1', plain)
            return plain.strip()

        # 先处理块级公式，再处理行内公式。
        text = re.sub(r'\$\$(.*?)\$\$', replace_formula, text, flags=re.DOTALL)
        text = re.sub(r'(?<!\$)\$([^\n$]+)\$(?!\$)', replace_formula, text)
        return text

    @staticmethod
    def _format_markdown_inline(text):
        """转换报告中的常用行内 Markdown。"""
        import re

        formatted = text.strip()
        formatted = re.sub(r'`([^`]+)`', r'<code>\1</code>', formatted)
        formatted = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', formatted)
        formatted = re.sub(r'(?<!\*)\*([^*]+?)\*(?!\*)', r'<em>\1</em>', formatted)
        # 即使模型把多个“加粗标签：内容”写在同一行，也强制换行。
        formatted = re.sub(
            r'\s+(?=<strong>[^<]{1,120}(?::|：)</strong>)',
            '<br>',
            formatted,
        )
        return formatted

    def clean_text_for_html(self, text):
        """将 AI 输出的 Markdown 转换为结构稳定的 HTML 块。"""
        if not text:
            return ""

        import re

        text = self._normalize_report_math(text)
        lines = text.replace('\r\n', '\n').replace('\r', '\n').split('\n')
        html_blocks = []
        i = 0

        while i < len(lines):
            stripped = lines[i].strip()

            if not stripped:
                i += 1
                continue

            # AI 偶尔用 --- 包裹整份报告；报告自身已有分隔样式，不再显示该标记。
            if re.fullmatch(r'(?:-{3,}|\*{3,}|_{3,})', stripped):
                i += 1
                continue

            # Markdown 表格必须整体处理，否则单行会被误判为无效表格。
            if stripped.startswith('|') and stripped.endswith('|'):
                table_lines = []
                while i < len(lines):
                    table_line = lines[i].strip()
                    if not (table_line.startswith('|') and table_line.endswith('|')):
                        break
                    table_lines.append(table_line)
                    i += 1
                table_html = self._convert_markdown_table_to_html(table_lines)
                if table_html:
                    html_blocks.append(table_html)
                continue

            heading_match = re.match(r'^(#{1,6})\s+(.+)$', stripped)
            if heading_match:
                level = len(heading_match.group(1))
                heading = self._format_markdown_inline(heading_match.group(2))
                html_blocks.append(f'<h{level}>{heading}</h{level}>')
                i += 1
                continue

            bullet_match = re.match(r'^[-+*]\s+(.+)$', stripped)
            if bullet_match:
                items = []
                while i < len(lines):
                    item_match = re.match(r'^\s*[-+*]\s+(.+)$', lines[i])
                    if not item_match:
                        break
                    items.append(f'<li>{self._format_markdown_inline(item_match.group(1))}</li>')
                    i += 1
                html_blocks.append('<ul>' + ''.join(items) + '</ul>')
                continue

            numbered_match = re.match(r'^\d+[.)]\s+(.+)$', stripped)
            if numbered_match:
                items = []
                while i < len(lines):
                    item_match = re.match(r'^\s*\d+[.)]\s+(.+)$', lines[i])
                    if not item_match:
                        break
                    items.append(f'<li>{self._format_markdown_inline(item_match.group(1))}</li>')
                    i += 1
                html_blocks.append('<ol>' + ''.join(items) + '</ol>')
                continue

            if stripped.startswith('>'):
                quote = self._format_markdown_inline(stripped.lstrip('>').strip())
                html_blocks.append(f'<blockquote>{quote}</blockquote>')
            else:
                # 每个非空源行都是独立段落，避免 HTML 将换行折叠为空格。
                html_blocks.append(f'<p>{self._format_markdown_inline(stripped)}</p>')
            i += 1

        return '\n'.join(html_blocks)
    
    def _convert_markdown_table_to_html(self, table_lines):
        """将Markdown表格转换为HTML表格"""
        if len(table_lines) < 2:
            return f'<p>{self._format_markdown_inline(table_lines[0])}</p>' if table_lines else ""
        
        html_parts = ['<table style="border-collapse: collapse; width: 100%; margin: 10px 0;">']
        
        # 处理表头
        header_line = table_lines[0]
        header_cells = [cell.strip() for cell in header_line.split('|')[1:-1]]  # 去掉首尾空元素
        html_parts.append('<thead>')
        html_parts.append('<tr>')
        for cell in header_cells:
            cell_html = self._format_markdown_inline(cell)
            html_parts.append(f'<th style="border: 1px solid #ddd; padding: 8px; background-color: #f2f2f2; text-align: left;">{cell_html}</th>')
        html_parts.append('</tr>')
        html_parts.append('</thead>')
        
        # 跳过分隔行（第二行）
        if len(table_lines) > 2:
            html_parts.append('<tbody>')
            for line in table_lines[2:]:
                if '|' in line:
                    cells = [cell.strip() for cell in line.split('|')[1:-1]]  # 去掉首尾空元素
                    html_parts.append('<tr>')
                    for cell in cells:
                        cell_html = self._format_markdown_inline(cell)
                        html_parts.append(f'<td style="border: 1px solid #ddd; padding: 8px;">{cell_html}</td>')
                    html_parts.append('</tr>')
            html_parts.append('</tbody>')
        
        html_parts.append('</table>')
        return '\n'.join(html_parts)

    def analyze_target_protein_counts(self, data_dir):
        """分析数据目录中的靶点和蛋白数量"""
        import re
        import os
        
        targets = set()
        proteins = set()
        
        try:
            if os.path.exists(data_dir):
                for item in os.listdir(data_dir):
                    item_path = os.path.join(data_dir, item)
                    if os.path.isdir(item_path):
                        # 从目录名解析靶点和蛋白信息
                        # 格式示例：0606_293T_cas9-sg1_1
                        match = re.search(r"(cas\d+)-sg(\d+)", item, re.IGNORECASE)
                        if match:
                            protein = match.group(1).lower()  # cas9, cas12等
                            target = f"{protein}-sg{match.group(2)}"  # cas9-sg1等
                            proteins.add(protein)
                            targets.add(target)
        except Exception as e:
            print(f"分析靶点和蛋白数量时出错: {e}")
        
        # 调试信息：打印识别到的靶点
        print(f"识别到的靶点: {sorted(targets)}")
        print(f"识别到的蛋白: {sorted(proteins)}")
        print(f"靶点数量: {len(targets)}, 蛋白数量: {len(proteins)}")
        
        return len(targets), len(proteins), targets, proteins

    def create_html_report_with_images(self, language=None, html_paged=False):
        """创建包含图片的HTML格式AI报告"""
        if language is None:
            language = st.session_state.get('language', 'zh')
        try:
            import base64
            import os
            from datetime import datetime
            from AI_helper import collect_chart_previews, format_target_for_display
            
            # 获取AI报告文本并格式化（sg → site）
            ai_report_raw = st.session_state.get('ai_report', '')
            ai_report = format_target_for_display(ai_report_raw) if ai_report_raw else ''
            
            # 解析AI报告，提取每个蛋白、每种图表类型的文字解读
            import re
            protein_sections = {}  # {protein_type: {chart_type: text}}
            
            if ai_report:
                report_text = ai_report.replace('\r\n', '\n')
                lines = report_text.split('\n')

                current_protein = None
                current_chart = None

                def extract_protein(name: str):
                    match = re.search(r'(cas\d+)', name, re.IGNORECASE)
                    return match.group(1).upper() if match else None

                chart_keywords = [
                    ('细胞分布散点图', 'Cell_Distribution_Scatter'),
                    ('细胞分布特征', 'Cell_Distribution_Scatter'),
                    ('Cell Distribution Scatter', 'Cell_Distribution_Scatter'),
                    ('Cell Distribution Features', 'Cell_Distribution_Scatter'),
                    ('细胞聚类散点图', 'Cell_Clustering_Scatter'),
                    ('细胞集群散点图', 'Cell_Clustering_Scatter'),
                    ('聚类特征', 'Cell_Clustering_Scatter'),
                    ('聚类模式', 'Cell_Clustering_Scatter'),
                    ('Cell Clustering Scatter', 'Cell_Clustering_Scatter'),
                    ('Clustering Features', 'Cell_Clustering_Scatter'),
                    ('模拟流式细胞术图', 'Simulated_Flow_Cytometry'),
                    ('模拟流式细胞术', 'Simulated_Flow_Cytometry'),
                    ('模拟流式', 'Simulated_Flow_Cytometry'),
                    ('流式细胞术', 'Simulated_Flow_Cytometry'),
                    ('流式细胞', 'Simulated_Flow_Cytometry'),
                    ('荧光表型', 'Simulated_Flow_Cytometry'),
                    ('对数强度', 'Simulated_Flow_Cytometry'),
                    ('Simulated Flow Cytometry', 'Simulated_Flow_Cytometry'),
                    ('Fluorescence Phenotype', 'Simulated_Flow_Cytometry'),
                ]

                for raw_line in lines:
                    line = raw_line.strip()
                    if not line:
                        continue
                    lower_line = line.lower()

                    # 检测蛋白标题
                    if line.startswith('●') or line.startswith('###'):
                        extracted = extract_protein(line)
                        if extracted:
                            current_protein = extracted
                            protein_sections.setdefault(current_protein, {})
                            current_chart = None
                        continue

                    # 检测是否进入综合分析或结论部分（停止提取单个蛋白内容）
                    if ('综合对比' in line or '关键发现' in line or '结论' in line or 
                        'comparative analysis' in lower_line or 'key findings' in lower_line or 
                        'conclusion' in lower_line):
                        current_protein = None
                        current_chart = None
                        continue

                    # 检测图表类型关键词
                    chart_detected = False
                    for keyword, chart_label in chart_keywords:
                        if keyword.lower() in lower_line:
                            current_chart = chart_label
                            chart_detected = True
                            if current_protein:
                                protein_sections[current_protein].setdefault(current_chart, [])
                            break
                    
                    if chart_detected:
                        continue

                    # 普通文本内容，追加到当前图表类型
                    if current_protein and current_chart:
                        # 跳过空行和标题行
                        if line and not line.startswith('#') and not line.startswith('**小结'):
                            protein_sections[current_protein][current_chart].append(line)

                # 将每个列表拼接为字符串
                for prot, charts in protein_sections.items():
                    for chart_type, texts in charts.items():
                        protein_sections[prot][chart_type] = '\n'.join(texts).strip()
            
            # 收集按组别组织的图表
            chart_previews_by_group = collect_chart_previews_by_group(st.session_state.work_dir, max_per_type=1)
            
            # 直接使用收集到的所有图表(collect函数已经做了靶点级别的筛选)
            print(f"[DEBUG] Using all collected charts: {len(chart_previews_by_group)} groups")
            
            # 获取AI报告按组别的内容
            from AI_helper import generate_ai_report_by_group
            group_reports = st.session_state.get('group_reports', {})
            
            # 读取SVG图标
            def load_svg_icon(icon_name):
                # 安全的图标fallback映射 - 使用Unicode符号避免编码问题
                icon_fallbacks = {
                    'microscope': '<span style="font-size: 24px; color: #4CAF50;">◉</span>',
                    'dna': '<span style="font-size: 24px; color: #2196F3;">◈</span>',
                    'chart': '<span style="font-size: 24px; color: #FF9800;">■</span>',
                    'ai-robot': '<span style="font-size: 24px; color: #9C27B0;">◆</span>',
                    'report': '<span style="font-size: 24px; color: #607D8B;">▣</span>',
                    'cell': '<span style="font-size: 24px; color: #E91E63;">●</span>',
                    'analysis': '<span style="font-size: 24px; color: #3F51B5;">▲</span>'
                }
                
                icon_path = os.path.join(st.session_state.work_dir, 'assets', 'icons', f'{icon_name}.svg')
                if os.path.exists(icon_path):
                    try:
                        with open(icon_path, 'r', encoding='utf-8') as f:
                            svg_content = f.read()
                            # 确保SVG内容安全且有效
                            if svg_content.strip() and '<svg' in svg_content:
                                return svg_content
                    except Exception as e:
                        print(f"Error loading SVG icon {icon_name}: {e}")
                
                # 如果SVG加载失败，使用安全的fallback
                return icon_fallbacks.get(icon_name, '<span style="font-size: 24px; color: #666;">●</span>')
            
            # 加载所有图标
            microscope_icon = load_svg_icon('microscope')
            dna_icon = load_svg_icon('dna')
            chart_icon = load_svg_icon('chart')
            ai_robot_icon = load_svg_icon('ai-robot')
            report_icon = load_svg_icon('report')
            cell_icon = load_svg_icon('cell')
            analysis_icon = load_svg_icon('analysis')
            
            # 构建HTML内容
            lang_attr = "en" if language == "en" else "zh-CN"
            body_class = "html-paged" if html_paged else ""
            pagination_target = "window" if html_paged else "document"
            pagination_event = "load" if html_paged else "DOMContentLoaded"
            pagination_threshold = "0.96" if html_paged else "1.15"
            html_content = f"""
<!DOCTYPE html>
<html lang="{lang_attr}">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{get_text("html_title")}</title>
    <style>
        /* === A4页面专业报告样式 === */
        
        /* 页面容器 - A4尺寸 */
        @page {{
            size: A4;
            margin: 25mm 20mm;
        }}
        
        /* 全局样式 - 专业报告格式 */
        * {{
            box-sizing: border-box;
        }}
        
        body {{
            font-family: 'Times New Roman', 'Songti SC', 'SimSun', serif;
            font-size: 14pt;
            line-height: 1.6;
            color: #000000;
            background: #e8e8e8;
            margin: 0;
            padding: 20px 0;
            -webkit-print-color-adjust: exact;
            print-color-adjust: exact;
        }}
        
        /* A4页面容器 */
        .a4-page {{
            width: 210mm;
            min-height: 297mm;
            background: #ffffff;
            margin: 0 auto 20px;
            padding: 0;
            box-shadow: 0 2px 10px rgba(0,0,0,0.1);
            position: relative;
            page-break-after: always;
        }}
        
        .a4-page:last-child {{
            margin-bottom: 0;
        }}
        
        /* Page Header */
        .page-header {{
            position: absolute;
            top: 10mm;
            left: 20mm;
            right: 20mm;
            height: 8mm;
            border-bottom: 0.5pt solid #cccccc;
            font-size: 12pt;
            color: #666666;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }}
        
        /* 封面页样式 */
        .cover-page {{
            width: 210mm;
            height: 297mm;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            margin: 0 auto 20mm;
            display: flex;
            flex-direction: column;
            justify-content: center;
            align-items: center;
            color: #ffffff;
            text-align: center;
            padding: 40mm 30mm;
            box-shadow: 0 2px 10px rgba(0,0,0,0.1);
            page-break-after: always;
        }}
        
        .cover-content {{
            max-width: 150mm;
        }}
        
        .cover-title {{
            font-size: 28pt;
            font-weight: 700;
            margin-bottom: 15mm;
            letter-spacing: 2pt;
            line-height: 1.3;
            text-shadow: 2px 2px 4px rgba(0,0,0,0.3);
        }}
        
        .cover-subtitle {{
            font-size: 20pt;
            margin-bottom: 20mm;
            opacity: 0.95;
            font-weight: 500;
            text-align: center;
        }}
        
        .cover-icons {{
            display: flex;
            justify-content: center;
            gap: 8mm;
            margin: 15mm 0;
            flex-wrap: nowrap;
        }}
        
        .cover-icon {{
            width: 15mm;
            height: 15mm;
            background: rgba(255,255,255,0.2);
            border-radius: 3mm;
            display: flex;
            align-items: center;
            justify-content: center;
            backdrop-filter: blur(10px);
        }}
        
        .cover-icon svg {{
            width: 8mm;
            height: 8mm;
            fill: #ffffff;
        }}
        
        .cover-info {{
            margin-top: 20mm;
            font-size: 16pt;
            line-height: 1.8;
            text-align: center;
        }}
        
        .cover-info p {{
            margin: 2mm 0;
            text-align: center;
            width: 100%;
        }}
        
        /* 内容页样式 */
        .content-page {{
            position: absolute;
            top: 20mm;
            bottom: 20mm;
            left: 20mm;
            right: 20mm;
            overflow: visible;
        }}
        
        /* 标题样式 - 专业报告格式 */
        h1 {{
            font-size: 21pt;
            font-weight: 700;
            color: #1a1a1a;
            text-align: center;
            margin: 0 0 8mm 0;
            padding-bottom: 4mm;
            border-bottom: 2pt solid #667eea;
            page-break-after: avoid;
        }}
        
        h2 {{
            font-size: 17pt;
            font-weight: 700;
            color: #2d3748;
            margin: 8mm 0 4mm 0;
            padding-left: 4mm;
            border-left: 4pt solid #667eea;
            page-break-after: avoid;
        }}
        
        h3 {{
            font-size: 15pt;
            font-weight: 600;
            color: #374151;
            margin: 6mm 0 3mm 0;
            page-break-after: avoid;
        }}
        
        h4 {{
            font-size: 14pt;
            font-weight: 600;
            color: #4b5563;
            margin: 5mm 0 2mm 0;
            page-break-after: avoid;
        }}
        
        h5 {{
            font-size: 14pt;
            font-weight: 500;
            color: #6b7280;
            margin: 4mm 0 2mm 0;
            text-align: center;
        }}
        
        /* 段落样式 */
        p {{
            margin: 0 0 3mm 0;
            text-align: justify;
            text-indent: 2em;
            line-height: 1.8;
            orphans: 3;
            widows: 3;
        }}
        
        p:first-of-type, 
        h1 + p, h2 + p, h3 + p, h4 + p {{
            text-indent: 0;
        }}
        
        /* 列表样式 */
        ul, ol {{
            margin: 3mm 0;
            padding-left: 8mm;
            line-height: 1.8;
        }}
        
        ul li {{
            margin-bottom: 2mm;
            list-style-type: none;
            position: relative;
            padding-left: 5mm;
        }}
        
        ul li::before {{
            content: "•";
            position: absolute;
            left: 0;
            color: #667eea;
            font-weight: 700;
        }}
        
        ol li {{
            margin-bottom: 2mm;
        }}
        
        /* 强调文本 */
        strong, b {{
            font-weight: 700;
            color: #1a1a1a;
        }}
        
        em, i {{
            font-style: italic;
        }}
        
        /* 图片网格 - 3列布局 */
        .image-grid-row {{
            display: flex;
            justify-content: space-between;
            gap: 3mm;
            margin: 5mm 0;
            page-break-inside: avoid;
        }}
        
        .image-col {{
            flex: 0 0 calc(33.333% - 2mm);
            text-align: center;
        }}
        
        .image-col img {{
            width: 100%;
            height: auto;
            border: 0.5pt solid #e5e7eb;
            border-radius: 1mm;
        }}
        
        .image-col h5 {{
            margin: 2mm 0 0 0;
            font-size: 14pt;
            color: #4b5563;
        }}
        
        /* 图表容器 */
        .chart-container {{
            margin: 5mm 0;
            text-align: center;
            page-break-inside: avoid;
        }}
        
        .chart-container img {{
            max-width: 100%;
            height: auto;
            border: 0.5pt solid #e5e7eb;
            border-radius: 1mm;
        }}
        
        /* 表格样式 */
        table {{
            width: 100%;
            border-collapse: collapse;
            margin: 5mm 0;
            font-size: 10pt;
            page-break-inside: avoid;
        }}
        
        th {{
            background: #f3f4f6;
            padding: 2mm 3mm;
            text-align: left;
            font-weight: 600;
            border: 0.5pt solid #d1d5db;
        }}
        
        td {{
            padding: 2mm 3mm;
            border: 0.5pt solid #e5e7eb;
        }}
        
        tr:nth-child(even) {{
            background: #f9fafb;
        }}
        
        /* 引用框 */
        blockquote {{
            margin: 4mm 0;
            padding: 3mm 4mm;
            background: #f7f9fc;
            border-left: 3pt solid #667eea;
            font-style: italic;
            page-break-inside: avoid;
        }}
        
        /* 代码块 */
        code {{
            background: #f3f4f6;
            padding: 1mm 2mm;
            border-radius: 1mm;
            font-family: 'Courier New', monospace;
            font-size: 9pt;
        }}
        
        pre {{
            background: #f8f9fa;
            padding: 4mm;
            border-radius: 2mm;
            overflow-x: auto;
            margin: 4mm 0;
            border: 0.5pt solid #e5e7eb;
        }}
        
        pre code {{
            background: none;
            padding: 0;
        }}
        
        /* 打印优化 */
        @media print {{
            body {{
                background: #ffffff;
                padding: 0;
            }}
            
            .a4-page {{
                width: 100%;
                margin: 0;
                box-shadow: none;
                page-break-after: always;
            }}
            
            .page-header {{
                display: flex;
            }}
            
            .cover-page {{
                margin: 0;
                box-shadow: none;
            }}
        }}
        
        /* 屏幕显示优化 */
        @media screen {{
            body {{
                padding: 10mm 0;
            }}

            /* 仅HTML分页模式固定每张白纸为A4；PDF路径不使用此类。 */
            body.html-paged .a4-page {{
                height: 297mm;
                min-height: 297mm;
                max-height: 297mm;
                overflow: hidden;
            }}

            body.html-paged .content-page {{
                overflow: hidden;
            }}

            /*
             * HTML安全降级：分页完成前由白色页面承载全部正文。
             * 分页成功并写入data-pagination-complete后才锁定为独立A4页面。
             */
            body.html-paged:not([data-pagination-started="true"]) .a4-page {{
                height: auto;
                min-height: 297mm;
                max-height: none;
                overflow: visible;
            }}

            body.html-paged:not([data-pagination-started="true"]) .content-page {{
                position: static;
                margin: 0;
                padding: 20mm;
                min-height: 257mm;
                overflow: visible;
            }}
        }}
    </style>
</head>
<body class="{body_class}">
    <!-- 封面页 -->
    <div class="cover-page">
        <div class="cover-content">
            <h1 class="cover-title">{get_text("html_report_title")}</h1>
            <p class="cover-subtitle">{get_text("html_report_subtitle")}</p>
            
            <div class="cover-icons">
                <div class="cover-icon">
                    {microscope_icon}
                </div>
                <div class="cover-icon">
                    {dna_icon}
                </div>
                <div class="cover-icon">
                    {chart_icon}
                </div>
                <div class="cover-icon">
                    {ai_robot_icon}
                </div>
                <div class="cover-icon">
                    {report_icon}
                </div>
            </div>
            
            <div class="cover-info">
            </div>
        </div>
    </div>

    <!-- A4 Page Container - Page 1 -->
    <div class="a4-page">
        <!-- Page Header -->
        <div class="page-header">
            <span>EasyReporter - Gene Editing Efficiency Analysis Report</span>
        </div>
        
        <!-- Content Area -->
        <div class="content-page">
            <!-- Complete AI Analysis Report -->
            <div class="text-content">
"""
            
            # 将图表嵌入到AI报告中的对应位置
            if ai_report and chart_previews_by_group:
                # 构建图表类型到实际图表路径的映射
                chart_map = {}  # {protein_type: {chart_type: [chart_info1, chart_info2, ...]}}
                summary_chart_map = {}  # 存储汇总图表
                
                print(f"[DEBUG] chart_previews_by_group has {len(chart_previews_by_group)} groups")
                
                for group_name, group_data in chart_previews_by_group.items():
                    print(f"[DEBUG] Processing group: {group_name}, chart types: {list(group_data.keys()) if isinstance(group_data, dict) else 'N/A'}")
                    
                    if group_name == 'summary_charts':
                        # 处理汇总图表
                        for chart_type_value, charts in group_data.items():
                            if charts and len(charts) > 0:
                                summary_chart_map[chart_type_value] = charts[0]
                                print(f"[DEBUG] Added summary chart: {chart_type_value}")
                        continue
                    
                    # 提取蛋白类型
                    protein_type = ''
                    if str(group_name).lower() == 'wt':
                        protein_type = 'WT'
                    else:
                        protein_match = re.match(r'(cas\d+)', str(group_name), re.IGNORECASE)
                        if protein_match:
                            protein_type = protein_match.group(1).upper()
                            print(f"[DEBUG] Extracted protein_type '{protein_type}' from group_name '{group_name}'")

                    if protein_type:
                        if protein_type not in chart_map:
                            chart_map[protein_type] = {}
                        
                        # 映射所有图表类型 - 改为收集所有组的图表而不是覆盖
                        for chart_type_value, charts in group_data.items():
                            if charts and len(charts) > 0:
                                if chart_type_value not in chart_map[protein_type]:
                                    chart_map[protein_type][chart_type_value] = []
                                # 将当前组的所有图表添加到列表中
                                chart_map[protein_type][chart_type_value].extend(charts)
                                print(f"[DEBUG] Added {len(charts)} charts of type '{chart_type_value}' to protein '{protein_type}'")
                
                # 打印最终的chart_map结构
                print("\n[DEBUG] === Final chart_map Structure ===")
                for protein_type, charts_dict in chart_map.items():
                    print(f"[DEBUG] [{protein_type}]")
                    for chart_type, chart_list in charts_dict.items():
                        print(f"[DEBUG]   {chart_type}: {len(chart_list)} charts")
                print(f"[DEBUG] === End chart_map ===\n")
                
                # 按段落分割AI报告（以空行或标题行分隔）
                lines = ai_report.split('\n')
                current_protein = None
                in_comparison_section = False
                processed_html = []
                inserted_charts = set()  # 记录已插入的图表，避免重复
                
                # 定义图表关键词和类型的映射 - 使用更精确的匹配
                chart_keywords = {
                    'Cell_Distribution_Scatter': [
                        '细胞分布散点图', 'Cell Distribution Scatter',
                        '细胞分布特征', 'Cell Distribution Features',
                        # 四级标题特有关键词
                        '#### 细胞分布特征', '#### Cell Distribution Features'
                    ],
                    'Cell_Clustering_Scatter': [
                        '细胞聚类散点图', 'Cell Clustering Scatter',
                        '聚类特征', 'Clustering Features',
                        # 四级标题特有关键词
                        '#### 聚类特征', '#### Clustering Features'
                    ],
                    'Simulated_Flow_Cytometry': [
                        '模拟流式细胞术图', '模拟流式细胞术', '模拟流式细胞图', '模拟流式',
                        'Simulated Flow Cytometry', 'simulated flow cytometry', 'simulated flow',
                        '流式细胞术', '流式细胞', '荧光表型与编辑效率',
                        'Fluorescence Phenotype & Editing Efficiency',
                        'fluorescence phenotype & editing efficiency', 'fluorescence phenotype',
                        '对数强度', 'Log Intensity', 'log intensity',
                        # 四级标题特有关键词（更精确）
                        '#### 荧光表型与编辑效率', '#### Fluorescence Phenotype & Editing Efficiency',
                        '#### 荧光表型', '#### Fluorescence Phenotype'
                    ]
                }
                
                summary_keywords = {
                    'Grouped_Bar': [
                        '编辑效率对比', '柱状图', '效率对比',
                        'efficiency comparison', 'bar chart', 'grouped bar',
                        '### 3.1', '### 3.1 编辑效率对比', '### 3.1 Editing Efficiency Comparison'
                    ],
                    'Grouped_Box': [
                        '箱线图', '分布箱线', '箱型图',
                        'box plot', 'boxplot', 'grouped box',
                        '### 3.2', '### 3.2 分布特征对比', '### 3.2 Distribution Comparison'
                    ],
                    'Correlation_Scatter': [
                        '相关性散点图', '方法学验证', '检测方法对比', '线性回归',
                        'correlation scatter', 'method validation', 'linear regression',
                        '### 3.3', '### 3.3 方法学验证', '### 3.3 Method Validation',
                        'spearman', 'pearson'
                    ],
                    'Correlation_Heatmap': [
                        '相关性热图', '相关性矩阵', '热图分析',
                        'correlation heatmap', 'correlation matrix', 'heatmap analysis',
                        '### 3.4', '### 3.4 相关性分析', '### 3.4 Correlation Analysis'
                    ]
                }
                
                def should_insert_chart(line_content, keywords):
                    """检查是否应该在此处插入图表 - 改进版，优先匹配标题"""
                    line_lower = line_content.lower()
                    line_stripped = line_content.strip()
                    
                    # 优先级1：四级标题（####）精确匹配
                    if line_stripped.startswith('####') or '<h4>' in line_content.lower():
                        for kw in keywords:
                            kw_lower = kw.lower()
                            # 移除标记符号后比较
                            clean_line = line_stripped.replace('####', '').replace('<h4>', '').replace('</h4>', '').strip()
                            clean_kw = kw_lower.replace('####', '').strip()
                            if clean_kw in clean_line.lower():
                                return True
                    
                    # 优先级2：三级标题（###）精确匹配（用于汇总图表）
                    if line_stripped.startswith('###') or '<h3>' in line_content.lower():
                        for kw in keywords:
                            kw_lower = kw.lower()
                            clean_line = line_stripped.replace('###', '').replace('<h3>', '').replace('</h3>', '').strip()
                            clean_kw = kw_lower.replace('###', '').strip()
                            if clean_kw in clean_line.lower():
                                return True
                    
                    # 优先级3：常规关键词匹配（非标题行）
                    if not line_stripped.startswith('#') and '<h' not in line_content.lower():
                        for kw in keywords:
                            if not kw.startswith('#') and kw.lower() in line_lower:
                                return True
                    
                    return False
                
                def extract_data_title(chart_path):
                    """从图表路径中提取数据标题，格式为 SpCas9-site1 或 hfCas12Max-site1"""
                    filename = os.path.basename(chart_path)
                    # 匹配 cas9-sg1, cas12-sg2 等格式（支持下划线和连字符）
                    match = re.search(r'(cas\d+)[-_]?sg(\d+)', filename, re.IGNORECASE)
                    if match:
                        cas_type = match.group(1).lower()  # cas9, cas12
                        site_num = match.group(2)  # 1, 2, 3
                        # 使用自定义蛋白名称
                        if cas_type == "cas9":
                            protein = "SpCas9"
                        elif cas_type == "cas12":
                            protein = "hfCas12Max"
                        else:
                            protein = match.group(1).capitalize()  # 其他情况保持首字母大写
                        return f"{protein}-site{site_num}"  # SpCas9-site1, hfCas12Max-site2
                    return None
                
                i = 0
                last_protein = None
                print(f"[DEBUG] Starting line-by-line processing, total lines: {len(lines)}")
                while i < len(lines):
                    line = lines[i]
                    
                    # 检测蛋白章节标题 - 支持 SpCas9, hfCas12Max 等自定义蛋白名称
                    protein_match = re.search(r'###\s*\d+\.\d+\s*(SpCas9|hfCas12Max|cas\d+)', line, re.IGNORECASE)
                    if protein_match:
                        # 将自定义蛋白名称映射回原始类型（用于查找图表）
                        matched_name = protein_match.group(1)
                        if matched_name.lower() == 'spcas9':
                            new_protein = 'CAS9'
                        elif matched_name.lower() == 'hfcas12max':
                            new_protein = 'CAS12'
                        else:
                            new_protein = matched_name.upper()
                        print(f"[DEBUG] Detected protein section: {matched_name} -> {new_protein} at line {i}: '{line[:60]}...'")
                        
                        # 如果之前有蛋白分析，检查是否有未插入的图表
                        if last_protein and last_protein in chart_map:
                            print(f"[DEBUG] Checking未插入的图表 for last_protein: {last_protein}")
                            for chart_type in ['Cell_Distribution_Scatter', 'Cell_Clustering_Scatter', 'Simulated_Flow_Cytometry']:
                                chart_key = f"{last_protein}_{chart_type}"
                                if chart_key not in inserted_charts and chart_type in chart_map[last_protein]:
                                    # 插入该类型的所有图表（多个 sg 组），使用3列网格布局
                                    chart_list = chart_map[last_protein][chart_type]
                                    # 开始3列网格行
                                    processed_html.append("<br><div class='image-grid-row'>")
                                    
                                    for idx, chart_info in enumerate(chart_list):
                                        chart_path = chart_info.get('path', '')
                                        if chart_path and os.path.exists(chart_path):
                                            try:
                                                from PIL import Image as PILImage
                                                img = PILImage.open(chart_path)
                                                buffered = io.BytesIO()
                                                img.save(buffered, format="PNG")
                                                img_base64 = base64.b64encode(buffered.getvalue()).decode()
                                                
                                                data_title = extract_data_title(chart_path)
                                                title_html = f"<h5>{data_title}</h5>" if data_title else ""
                                                
                                                # 添加图片列
                                                processed_html.append(
                                                    f"<div class='image-col'>"
                                                    f"{title_html}"
                                                    f"<img src='data:image/png;base64,{img_base64}' "
                                                    f"alt='{last_protein} {chart_type}'>"
                                                    f"</div>"
                                                )
                                            except Exception as e:
                                                pass
                                    
                                    # 结束3列网格行
                                    processed_html.append("</div>")
                                    inserted_charts.add(chart_key)
                        
                        current_protein = new_protein
                        last_protein = new_protein
                        in_comparison_section = False
                    
                    # 检测综合对比章节
                    elif re.search(r'###\s*3[\.\s]|综合对比|综合分析', line, re.IGNORECASE):
                        # 在进入综合对比前，检查最后一个蛋白是否有未插入的图表
                        if last_protein and last_protein in chart_map:
                            for chart_type in ['Cell_Distribution_Scatter', 'Cell_Clustering_Scatter', 'Simulated_Flow_Cytometry']:
                                chart_key = f"{last_protein}_{chart_type}"
                                if chart_key not in inserted_charts and chart_type in chart_map[last_protein]:
                                    # 插入该类型的所有图表（多个 sg 组），使用3列网格布局
                                    chart_list = chart_map[last_protein][chart_type]
                                    # 开始3列网格行
                                    processed_html.append("<br><div class='image-grid-row'>")
                                    
                                    for idx, chart_info in enumerate(chart_list):
                                        chart_path = chart_info.get('path', '')
                                        if chart_path and os.path.exists(chart_path):
                                            try:
                                                from PIL import Image as PILImage
                                                img = PILImage.open(chart_path)
                                                buffered = io.BytesIO()
                                                img.save(buffered, format="PNG")
                                                img_base64 = base64.b64encode(buffered.getvalue()).decode()
                                                
                                                data_title = extract_data_title(chart_path)
                                                title_html = f"<h5>{data_title}</h5>" if data_title else ""
                                                
                                                # 添加图片列
                                                processed_html.append(
                                                    f"<div class='image-col'>"
                                                    f"{title_html}"
                                                    f"<img src='data:image/png;base64,{img_base64}' "
                                                    f"alt='{last_protein} {chart_type}'>"
                                                    f"</div>"
                                                )
                                            except Exception as e:
                                                pass
                                    
                                    # 结束3列网格行
                                    processed_html.append("</div>")
                                    inserted_charts.add(chart_key)
                        
                        in_comparison_section = True
                        current_protein = None
                    
                    # 检测关键发现章节：先做全局兜底，确保所有未插入的组别图都不缺失
                    elif re.search(r'##\s*4[.\s]|关键发现|key findings', line, re.IGNORECASE):
                        for prot, types_map in chart_map.items():
                            for chart_type in ['Cell_Distribution_Scatter', 'Cell_Clustering_Scatter', 'Simulated_Flow_Cytometry']:
                                chart_key = f"{prot}_{chart_type}"
                                if chart_key not in inserted_charts and chart_type in types_map:
                                    # 插入该类型的所有图表（多个 sg 组），使用3列网格布局
                                    chart_list = types_map[chart_type]
                                    processed_html.append("<br><div class='image-grid-row'>")
                                    
                                    for chart_info in chart_list:
                                        chart_path = chart_info.get('path', '')
                                        if chart_path and os.path.exists(chart_path):
                                            try:
                                                from PIL import Image as PILImage
                                                img = PILImage.open(chart_path)
                                                buffered = io.BytesIO()
                                                img.save(buffered, format="PNG")
                                                img_base64 = base64.b64encode(buffered.getvalue()).decode()
                                                
                                                data_title = extract_data_title(chart_path)
                                                title_html = f"<h5>{data_title}</h5>" if data_title else ""
                                                
                                                processed_html.append(
                                                    f"<div class='image-col'>"
                                                    f"{title_html}"
                                                    f"<img src='data:image/png;base64,{img_base64}' "
                                                    f"alt='{prot} {chart_type}'>"
                                                    f"</div>"
                                                )
                                            except Exception as e:
                                                pass
                                    
                                    processed_html.append("</div>")
                                    inserted_charts.add(chart_key)
                                    print(f"[DEBUG] Fallback inserted {chart_type} for {prot} (global fallback)")
                        
                        in_comparison_section = False
                        current_protein = None
                    
                    # 添加当前 Markdown 块。表格需要一次传入全部行，
                    # 否则单行表格会被判定为无效并丢失内容。
                    is_table_line = line.strip().startswith('|') and line.strip().endswith('|')
                    is_multiline_math = line.strip().startswith('$$') and line.count('$$') < 2
                    if is_multiline_math:
                        formula_lines = [line]
                        formula_end = i + 1
                        while formula_end < len(lines):
                            formula_lines.append(lines[formula_end])
                            if '$$' in lines[formula_end]:
                                formula_end += 1
                                break
                            formula_end += 1
                        processed_html.append(self.clean_text_for_html('\n'.join(formula_lines)))
                        i = formula_end
                        continue
                    elif is_table_line:
                        table_lines = []
                        table_end = i
                        while table_end < len(lines):
                            candidate = lines[table_end].strip()
                            if not (candidate.startswith('|') and candidate.endswith('|')):
                                break
                            table_lines.append(candidate)
                            table_end += 1
                        processed_html.append(self.clean_text_for_html('\n'.join(table_lines)))
                        i = table_end
                        continue
                    else:
                        rendered_line = self.clean_text_for_html(line)
                        if rendered_line:
                            processed_html.append(rendered_line)
                    
                    # 在综合对比部分插入汇总图表
                    if in_comparison_section and summary_chart_map:
                        for chart_type, keywords in summary_keywords.items():
                            chart_key = f"summary_{chart_type}"
                            if chart_key not in inserted_charts and should_insert_chart(line, keywords):
                                if chart_type in summary_chart_map:
                                    # 相关性散点图 - 3图一行布局
                                    if chart_type == 'Correlation_Scatter':
                                        chart_list = summary_chart_map[chart_type]
                                        if chart_list:
                                            try:
                                                # 开始3列网格行
                                                processed_html.append("<br><div class='image-grid-row'>")
                                                
                                                for chart_info in chart_list[:3]:  # 最多3张图
                                                    chart_path = chart_info.get('path', '')
                                                    if chart_path and os.path.exists(chart_path):
                                                        from PIL import Image as PILImage
                                                        img = PILImage.open(chart_path)
                                                        buffered = io.BytesIO()
                                                        img.save(buffered, format="PNG")
                                                        img_base64 = base64.b64encode(buffered.getvalue()).decode()
                                                        
                                                        # 从文件名提取标题 (如: cas12i_cas9_01.pdf -> FACS vs AI)
                                                        filename = os.path.basename(chart_path)
                                                        if '_01' in filename:
                                                            title = "FACS vs AI"
                                                        elif '_02' in filename:
                                                            title = "FACS vs Amplicon"
                                                        elif '_03' in filename:
                                                            title = "AI vs Amplicon"
                                                        else:
                                                            title = ""
                                                        
                                                        title_html = f"<h5>{title}</h5>" if title else ""
                                                        
                                                        # 添加图片列
                                                        processed_html.append(
                                                            f"<div class='image-col'>"
                                                            f"{title_html}"
                                                            f"<img src='data:image/png;base64,{img_base64}' "
                                                            f"alt='Correlation Scatter {title}'>"
                                                            f"</div>"
                                                        )
                                                
                                                # 结束3列网格行
                                                processed_html.append("</div>")
                                                inserted_charts.add(chart_key)
                                            except Exception as e:
                                                processed_html.append(f"<p style='color: #ef4444;'>❌ 无法加载相关性散点图: {str(e)}</p>")
                                    else:
                                        # 其他汇总图表 - 单图居中布局 (Grouped_Bar, Grouped_Box, Correlation_Heatmap)
                                        chart_info = summary_chart_map[chart_type]
                                        chart_path = chart_info.get('path', '') if isinstance(chart_info, dict) else chart_info[0].get('path', '')
                                        if chart_path and os.path.exists(chart_path):
                                            try:
                                                from PIL import Image as PILImage
                                                img = PILImage.open(chart_path)
                                                buffered = io.BytesIO()
                                                img.save(buffered, format="PNG")
                                                img_base64 = base64.b64encode(buffered.getvalue()).decode()
                                                
                                                # 提取数据标题
                                                data_title = extract_data_title(chart_path)
                                                title_html = f"<h4 style='color: #1f2937; font-size: 22px; margin-bottom: 10px; font-weight: 600;'>{data_title}</h4>" if data_title else ""
                                                
                                                processed_html.append(
                                                    f"<br><div class='chart-container' style='margin: 20px 0; text-align: center;'>"
                                                    f"{title_html}"
                                                    f"<img src='data:image/png;base64,{img_base64}' "
                                                    f"style='max-width: 72%; height: auto; border-radius: 8px; box-shadow: 0 2px 8px rgba(0,0,0,0.1);' "
                                                    f"alt='Summary {chart_type}'>"
                                                    f"</div>"
                                                )
                                                inserted_charts.add(chart_key)
                                            except Exception as e:
                                                processed_html.append(f"<p style='color: #ef4444;'>❌ 无法加载图表: {str(e)}</p>")
                    
                    # 在蛋白分析部分插入对应图表
                    elif current_protein and current_protein in chart_map:
                        for chart_type, keywords in chart_keywords.items():
                            chart_key = f"{current_protein}_{chart_type}"
                            if chart_key not in inserted_charts:
                                should_insert = should_insert_chart(line, keywords)
                                if should_insert:
                                    print(f"[DEBUG] ✅ Inserting {chart_type} for {current_protein} at line {i}")
                                    if chart_type in chart_map[current_protein]:
                                        # 插入该类型的所有图表（多个 sg 组），使用3列网格布局
                                        chart_list = chart_map[current_protein][chart_type]
                                        # 开始3列网格行
                                        processed_html.append("<br><div class='image-grid-row'>")
                                        
                                        for idx, chart_info in enumerate(chart_list):
                                            chart_path = chart_info.get('path', '')
                                            if chart_path and os.path.exists(chart_path):
                                                try:
                                                    from PIL import Image as PILImage
                                                    img = PILImage.open(chart_path)
                                                    buffered = io.BytesIO()
                                                    img.save(buffered, format="PNG")
                                                    img_base64 = base64.b64encode(buffered.getvalue()).decode()
                                                    
                                                    # 提取数据标题
                                                    data_title = extract_data_title(chart_path)
                                                    title_html = f"<h5>{data_title}</h5>" if data_title else ""
                                                    
                                                    # 添加图片列
                                                    processed_html.append(
                                                        f"<div class='image-col'>"
                                                        f"{title_html}"
                                                        f"<img src='data:image/png;base64,{img_base64}' "
                                                        f"alt='{current_protein} {chart_type}'>"
                                                        f"</div>"
                                                    )
                                                except Exception as e:
                                                    processed_html.append(f"<p style='color: #ef4444;'>❌ 无法加载图表: {str(e)}</p>")
                                        
                                        # 结束3列网格行
                                        processed_html.append("</div>")
                                        inserted_charts.add(chart_key)
                    
                    i += 1
                
                # 最终全局兜底：报告解析完后，把所有蛋白所有未插入的组别图补到正文末尾
                for prot, types_map in chart_map.items():
                    for chart_type in ['Cell_Distribution_Scatter', 'Cell_Clustering_Scatter', 'Simulated_Flow_Cytometry']:
                        chart_key = f"{prot}_{chart_type}"
                        if chart_key not in inserted_charts and chart_type in types_map:
                            chart_list = types_map[chart_type]
                            processed_html.append("<br><div class='image-grid-row'>")
                            
                            for chart_info in chart_list:
                                chart_path = chart_info.get('path', '')
                                if chart_path and os.path.exists(chart_path):
                                    try:
                                        from PIL import Image as PILImage
                                        img = PILImage.open(chart_path)
                                        buffered = io.BytesIO()
                                        img.save(buffered, format="PNG")
                                        img_base64 = base64.b64encode(buffered.getvalue()).decode()
                                        
                                        data_title = extract_data_title(chart_path)
                                        title_html = f"<h5>{data_title}</h5>" if data_title else ""
                                        
                                        processed_html.append(
                                            f"<div class='image-col'>"
                                            f"{title_html}"
                                            f"<img src='data:image/png;base64,{img_base64}' "
                                            f"alt='{prot} {chart_type}'>"
                                            f"</div>"
                                        )
                                    except Exception as e:
                                        pass
                            
                            processed_html.append("</div>")
                            inserted_charts.add(chart_key)
                            print(f"[DEBUG] End-of-report fallback inserted {chart_type} for {prot}")
                
                html_content += '\n'.join(processed_html) + '\n'
            elif ai_report:
                html_content += f"                {self.clean_text_for_html(ai_report)}\n"
            else:
                html_content += f"                <p>{get_text('no_ai_report_available')}</p>\n"
            
            html_content += """            </div>
        </div>
        
    </div>
    
    <!-- JavaScript for A4 pagination -->
    <script>
        {pagination_target}.addEventListener('{pagination_event}', async function() {{
            console.log('开始A4智能分页...');

            const htmlPagedMode = document.body.classList.contains('html-paged');
            if (htmlPagedMode) {{
                if (document.fonts && document.fonts.ready) {{
                    try {{ await document.fonts.ready; }} catch (fontError) {{
                        console.warn('字体加载等待失败，使用当前字体继续分页', fontError);
                    }}
                }}
                await Promise.all(Array.from(document.images).map((img) => {{
                    if (img.complete) return Promise.resolve();
                    return new Promise((resolve) => {{
                        img.addEventListener('load', resolve, {{ once: true }});
                        img.addEventListener('error', resolve, {{ once: true }});
                    }});
                }}));
                await new Promise((resolve) => requestAnimationFrame(() => requestAnimationFrame(resolve)));
                document.body.dataset.paginationStarted = 'true';
            }}
            
            // A4页面配置 (单位: px, 按96 DPI计算)
            const A4_HEIGHT_MM = 297;
            const A4_WIDTH_MM = 210;
            const DPI = 96;
            const MM_TO_PX = DPI / 25.4;
            
            // Page size (px)
            const PAGE_HEIGHT = A4_HEIGHT_MM * MM_TO_PX; // ~1122px
            const PAGE_WIDTH = A4_WIDTH_MM * MM_TO_PX;   // ~793px
            
            // Header and content margins (px)
            const TOP_MARGIN = 10 * MM_TO_PX;      // Header from top: 10mm
            const HEADER_HEIGHT = 8 * MM_TO_PX;     // Header height: 8mm
            const CONTENT_TOP = 20 * MM_TO_PX;      // Content from top: 20mm
            const CONTENT_BOTTOM = 20 * MM_TO_PX;   // Content from bottom: 20mm
            
            // Available content height = page height - content top - content bottom
            const CONTENT_HEIGHT = PAGE_HEIGHT - CONTENT_TOP - CONTENT_BOTTOM; // ~257mm = 972px
            
            // Use looser threshold, allow some overflow (images may be smaller after loading)
            const CONTENT_HEIGHT_THRESHOLD = CONTENT_HEIGHT * {pagination_threshold};
            
            console.log(`A4配置: 页面高度=${{PAGE_HEIGHT}}px, 内容高度=${{CONTENT_HEIGHT}}px, 阈值=${{CONTENT_HEIGHT_THRESHOLD}}px`);
            
            // 获取初始内容
            const firstPage = document.querySelector('.a4-page');
            const firstContentPage = firstPage.querySelector('.content-page');
            const textContent = firstContentPage.querySelector('.text-content');
            
            if (!textContent) {{
                console.log('未找到.text-content');
                return;
            }}
            
            // 将所有内容元素移到临时容器
            const allElements = Array.from(textContent.children);
            console.log(`总共有 ${{allElements.length}} 个顶级元素待分页`);
            
            // 清空原始容器
            textContent.innerHTML = '';
            
            let pageNumber = 1;
            let currentPage = firstPage;
            let currentContentDiv = firstContentPage;
            let currentHeight = 0;
            
            // 创建新页面的函数
            function createNewPage() {{
                pageNumber++;
                console.log(`创建新页面: 第${{pageNumber}}页`);
                
                const newPage = document.createElement('div');
                newPage.className = 'a4-page';
                
                // Page Header
                const header = document.createElement('div');
                header.className = 'page-header';
                header.innerHTML = `
                    <span>EasyReporter - Gene Editing Efficiency Analysis Report</span>
                `;
                
                // Content Container
                const contentDiv = document.createElement('div');
                contentDiv.className = 'content-page';
                
                newPage.appendChild(header);
                newPage.appendChild(contentDiv);
                
                // 插入到当前页之后
                currentPage.parentNode.insertBefore(newPage, currentPage.nextSibling);
                
                currentPage = newPage;
                currentContentDiv = contentDiv;
                currentHeight = 0;
            }}
            
            // 获取元素高度的函数
            function getElementHeight(element) {{
                // 临时添加到DOM以测量高度
                const originalStyle = element.getAttribute('style');
                element.style.visibility = 'hidden';
                element.style.position = htmlPagedMode ? 'static' : 'absolute';
                if (htmlPagedMode) element.style.width = '100%';
                currentContentDiv.appendChild(element);
                
                const rect = element.getBoundingClientRect();
                const height = rect.height;
                const marginTop = parseFloat(getComputedStyle(element).marginTop) || 0;
                const marginBottom = parseFloat(getComputedStyle(element).marginBottom) || 0;
                const totalHeight = height + marginTop + marginBottom;
                
                // 移除临时添加
                currentContentDiv.removeChild(element);
                if (htmlPagedMode) {{
                    if (originalStyle === null) {{
                        element.removeAttribute('style');
                    }} else {{
                        element.setAttribute('style', originalStyle);
                    }}
                }} else {{
                    element.style.visibility = '';
                    element.style.position = '';
                }}
                
                return totalHeight;
            }}
            
            // 检查元素是否应该避免分页
            function shouldAvoidBreak(element) {{
                const tag = element.tagName;
                // H4标题允许跨页,但图表组必须完整
                return tag === 'H1' || tag === 'H2' || tag === 'H3' || 
                       element.classList.contains('image-grid-row') ||
                       element.classList.contains('chart-container') ||
                       element.classList.contains('no-break');
            }}
            
            // 检查是否为标题+内容组合(需要一起处理)
            function isTitleWithContent(element, nextElement) {{
                if (!nextElement) return false;
                
                // 检查当前元素是否为标题
                const isTitle = element.tagName === 'H1' || element.tagName === 'H2' || 
                               element.tagName === 'H3' || element.tagName === 'H4' || 
                               element.tagName === 'H5' || element.tagName === 'H6';
                
                if (!isTitle) return false;
                
                // 检查下一个元素是否为内容(图表、段落、列表等)
                const nextIsContent = nextElement.classList.contains('image-grid-row') ||
                                     nextElement.classList.contains('chart-container') ||
                                     nextElement.tagName === 'P' ||
                                     nextElement.tagName === 'UL' ||
                                     nextElement.tagName === 'OL' ||
                                     nextElement.tagName === 'BLOCKQUOTE' ||
                                     nextElement.tagName === 'PRE';
                
                return nextIsContent;
            }}

            function appendSplitHtmlList(listElement) {{
                const listTag = listElement.tagName.toLowerCase();
                let activeList = document.createElement(listTag);
                activeList.className = listElement.className;
                const sourceStyle = listElement.getAttribute('style');
                if (sourceStyle) activeList.setAttribute('style', sourceStyle);

                Array.from(listElement.children).forEach((item) => {{
                    const itemHeight = getElementHeight(item);
                    if (currentHeight + itemHeight > CONTENT_HEIGHT_THRESHOLD && currentHeight > 0) {{
                        if (activeList.children.length > 0) currentContentDiv.appendChild(activeList);
                        createNewPage();
                        activeList = document.createElement(listTag);
                        activeList.className = listElement.className;
                        if (sourceStyle) activeList.setAttribute('style', sourceStyle);
                    }}
                    activeList.appendChild(item);
                    currentHeight += itemHeight;
                }});

                if (activeList.children.length > 0) currentContentDiv.appendChild(activeList);
            }}
            
            // 遍历所有元素进行智能分页
            allElements.forEach((element, index) => {{
                const elementHeight = getElementHeight(element);
                const isAvoidBreak = shouldAvoidBreak(element);
                const nextElement = allElements[index + 1];
                const isTitleContent = isTitleWithContent(element, nextElement);
                
                console.log(`元素[${{index}}] ${{element.tagName}} 高度=${{elementHeight.toFixed(1)}}px, 当前页高=${{currentHeight.toFixed(1)}}px, 避免分页=${{isAvoidBreak}}, 标题+内容=${{isTitleContent}}`);

                if (htmlPagedMode &&
                    (element.tagName === 'UL' || element.tagName === 'OL') &&
                    elementHeight > CONTENT_HEIGHT_THRESHOLD) {{
                    appendSplitHtmlList(element);
                    return;
                }}
                
                // 特殊处理: 任何标题后紧跟内容
                if (isTitleContent) {{
                    const nextHeight = getElementHeight(nextElement);
                    const totalHeight = elementHeight + nextHeight;
                    
                    // 使用宽松阈值判断,如果标题+内容放不下,且当前页有较多内容,整体移到下一页
                    if (currentHeight + totalHeight > CONTENT_HEIGHT_THRESHOLD && currentHeight > CONTENT_HEIGHT * 0.3) {{
                        console.log(`  → 标题+内容组合(${{totalHeight.toFixed(1)}}px)超过阈值(${{CONTENT_HEIGHT_THRESHOLD.toFixed(1)}}px),整体移到下一页`);
                        createNewPage();
                    }}
                }}
                
                // 判断是否需要分页
                else if (currentHeight + elementHeight > CONTENT_HEIGHT_THRESHOLD) {{
                    // 如果是标题或图表组,且当前页不是空的,则创建新页
                    if (isAvoidBreak && currentHeight > 100) {{
                        console.log(`  → 元素过高,创建新页`);
                        createNewPage();
                    }}
                    // 如果元素本身就超过页面高度,强制添加(允许溢出)
                    else if (elementHeight > CONTENT_HEIGHT_THRESHOLD) {{
                        console.log(`  → 元素超高(${{elementHeight.toFixed(1)}}px > ${{CONTENT_HEIGHT_THRESHOLD.toFixed(1)}}px),强制添加`);
                        // 如果当前页已有较多内容(超过30%),先创建新页
                        if (currentHeight > CONTENT_HEIGHT * 0.3) {{
                            createNewPage();
                        }}
                    }}
                    // 普通元素,如果加上会溢出,先创建新页
                    else {{
                        console.log(`  → 内容即将溢出,创建新页`);
                        createNewPage();
                    }}
                }}
                
                // 添加元素到当前页
                currentContentDiv.appendChild(element);
                currentHeight += elementHeight;
                
                console.log(`  ✓ 已添加,当前页高=${{currentHeight.toFixed(1)}}px`);
            }});
            
            document.body.dataset.paginationComplete = 'true';
            document.body.dataset.paginationPages = String(pageNumber);
            console.log(`A4智能分页完成! 总页数: ${{pageNumber}}`);
        }});
    </script>
</body>
</html>
"""
            
            return html_content
            
        except Exception as e:
            self.log_message(f"Failed to create HTML report: {str(e)}", "error")
            # 如果生成HTML失败，返回纯文本报告
            return st.session_state.get('ai_report', get_text('html_generation_failed'))
    
    def create_pdf_cover_page(self, story, styles, chinese_font, strip_emoji_func):
        """创建PDF封面页"""
        from reportlab.lib.units import inch
        from reportlab.lib import colors
        from reportlab.platypus import (
            Paragraph,
            Spacer,
            Table,
            TableStyle,
            PageBreak,
        )
        from reportlab.lib.styles import ParagraphStyle
        language = st.session_state.get('language', 'zh')
        if language == 'en':
            main_title = "AI Analysis Report"
            sub_title = "EasyReporter Fluorescence Analytics"
            icon_labels = ["Microscopy", "Data Visualization", "Bioinformatics"]
        else:
            main_title = "AI 分析报告"
            sub_title = "EasyReporter 荧光细胞分析系统"
            icon_labels = ["显微镜分析", "数据可视化", "生物信息学"]

        cover_title_style = ParagraphStyle(
            'CoverTitle',
            parent=styles['Normal'],
            fontName=chinese_font,
            fontSize=34,
            textColor=colors.HexColor('#1f2937'),
            alignment=1,
            spaceAfter=18,
            leading=40
        )

        cover_subtitle_style = ParagraphStyle(
            'CoverSubtitle',
            parent=styles['Normal'],
            fontName=chinese_font,
            fontSize=18,
            textColor=colors.HexColor('#4b5563'),
            alignment=1,
            spaceAfter=26,
            leading=26
        )

        cover_info_style = ParagraphStyle(
            'CoverInfo',
            parent=styles['Normal'],
            fontName=chinese_font,
            fontSize=12,
            textColor=colors.HexColor('#6b7280'),
            alignment=1,
            spaceAfter=8
        )

        story.append(Spacer(1, 1.6*inch))
        story.append(Paragraph(strip_emoji_func(main_title), cover_title_style))
        story.append(Paragraph(strip_emoji_func(sub_title), cover_subtitle_style))

        icon_data = [
            ["◆", "■", "●"],
            icon_labels
        ]
        icon_table = Table(icon_data, colWidths=[1.9*inch] * 3)
        icon_table.setStyle(TableStyle([
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('FONTSIZE', (0, 0), (-1, 0), 28),
            ('FONTSIZE', (0, 1), (-1, 1), 12),
            ('TEXTCOLOR', (0, 1), (-1, 1), colors.HexColor('#4b5563')),
            ('TOPPADDING', (0, 0), (-1, -1), 6),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ]))
        story.append(icon_table)
        story.append(Spacer(1, 0.6*inch))

        footer_label = "Generated by EasyReporter AI" if language == 'en' else "由 EasyReporter AI 分析系统生成"
        story.append(Paragraph(footer_label, cover_info_style))

        story.append(PageBreak())

    def log_pdf_creation(self, message, level='info'):
        """记录PDF创建过程中的日志信息"""
        if not hasattr(st.session_state, 'work_dir'):
            # 如果work_dir不存在，则无法记录日志
            return
        log_dir = os.path.join(st.session_state.work_dir, "logs")
        os.makedirs(log_dir, exist_ok=True)
        log_file = os.path.join(log_dir, "pdf_creation.log")
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with open(log_file, "a", encoding='utf-8') as f:
            f.write(f"[{timestamp}] [{level.upper()}] {message}\n")

    def create_pdf_report_with_images(self):
        """创建包含图片的PDF格式AI报告 - 使用浏览器无头打印，与HTML报告完全一致"""
        self.log_pdf_creation("--- 开始创建PDF报告（Edge 无头打印模式） ---")
        try:
            import tempfile
            import os
            import subprocess
            import sys
            
            # 定义PDF文件保存路径
            pdf_path = os.path.join(st.session_state.work_dir, "AI_Analysis_Report.pdf")
            self.log_pdf_creation(f"PDF将保存到: {pdf_path}")
            
            # ===== 方案1: 使用 Microsoft Edge 无头打印（推荐，与HTML完全一致） =====
            try:
                # 1. 生成 HTML 报告
                self.log_pdf_creation("正在生成 HTML 报告...")
                html_content = self.create_html_report_with_images(
                    st.session_state.get('language', 'zh')
                )
                
                if not html_content or len(html_content) < 500:
                    raise ValueError("HTML 报告内容为空或过短")
                
                self.log_pdf_creation(f"HTML 报告生成成功，长度: {len(html_content)} 字符")
                
                # 2. 写入临时 HTML 文件
                import tempfile
                html_path = os.path.join(tempfile.gettempdir(), 'easyreporter_report.html')
                with open(html_path, 'w', encoding='utf-8') as f:
                    f.write(html_content)
                self.log_pdf_creation(f"HTML 临时文件: {html_path}")
                
                # 3. 查找 Edge 浏览器
                edge_paths = [
                    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
                    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
                ]
                edge_exe = None
                for p in edge_paths:
                    if os.path.exists(p):
                        edge_exe = p
                        break
                if not edge_exe:
                    edge_exe = shutil.which("msedge") or shutil.which("microsoft-edge")
                
                if edge_exe:
                    self.log_pdf_creation(f"使用 Edge: {edge_exe}")
                    
                    # 4. 调用 Edge 无头打印
                    html_url = f"file:///{html_path.replace(os.sep, '/')}"
                    cmd = [
                        edge_exe,
                        '--headless',
                        '--disable-gpu',
                        f'--print-to-pdf={pdf_path}',
                        '--no-pdf-header-footer',
                        '--print-to-pdf-no-header',
                        '--virtual-time-budget=20000',
                        html_url,
                    ]
                    
                    result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
                    
                    # 5. 验证结果
                    if result.returncode == 0 and os.path.exists(pdf_path) and os.path.getsize(pdf_path) > 0:
                        self.log_pdf_creation(f"✅ PDF 生成成功 (Edge): {pdf_path} ({os.path.getsize(pdf_path)} bytes)")
                        # 清理临时文件
                        try:
                            os.unlink(html_path)
                        except Exception:
                            pass
                        return pdf_path
                    else:
                        stderr_info = result.stderr[:300] if result.stderr else "(无)"
                        self.log_pdf_creation(f"Edge 返回错误码 {result.returncode}: {stderr_info}")
                else:
                    self.log_pdf_creation("未找到 Microsoft Edge，尝试其他浏览器...")
                    
                    # 尝试 Chrome
                    chrome_paths = [
                        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
                        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
                    ]
                    chrome_exe = None
                    for p in chrome_paths:
                        if os.path.exists(p):
                            chrome_exe = p
                            break
                    if not chrome_exe:
                        chrome_exe = shutil.which("chrome") or shutil.which("google-chrome")
                    
                    if chrome_exe:
                        self.log_pdf_creation(f"使用 Chrome: {chrome_exe}")
                        html_url = f"file:///{html_path.replace(os.sep, '/')}"
                        cmd = [
                            chrome_exe,
                            '--headless',
                            '--disable-gpu',
                            f'--print-to-pdf={pdf_path}',
                            '--no-pdf-header-footer',
                            '--print-to-pdf-no-header',
                            '--virtual-time-budget=20000',
                            html_url,
                        ]
                        result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
                        
                        if result.returncode == 0 and os.path.exists(pdf_path) and os.path.getsize(pdf_path) > 0:
                            self.log_pdf_creation(f"✅ PDF 生成成功 (Chrome): {pdf_path}")
                            try:
                                os.unlink(html_path)
                            except Exception:
                                pass
                            return pdf_path
                        else:
                            stderr_info = result.stderr[:300] if result.stderr else "(无)"
                            self.log_pdf_creation(f"Chrome 返回错误码 {result.returncode}: {stderr_info}")
                
                # 清理临时 HTML
                try:
                    os.unlink(html_path)
                except Exception:
                    pass
                    
            except FileNotFoundError:
                self.log_pdf_creation("浏览器可执行文件未找到")
            except subprocess.TimeoutExpired:
                self.log_pdf_creation("HTML→PDF 转换超时 (120秒)")
                st.warning(get_text("pdf_timeout_warning"))
            except Exception as e:
                self.log_pdf_creation(f"浏览器 PDF 转换失败: {str(e)}")
                st.warning(get_text("browser_pdf_failed").format(str(e)))
            
            # ===== 方案2: 使用 pdf_renderer.py 独立脚本（备用） =====
            try:
                self.log_pdf_creation("尝试使用 pdf_renderer.py 独立脚本...")
                
                # 重新生成 HTML（如果之前没有）
                html_content = self.create_html_report_with_images(
                    st.session_state.get('language', 'zh')
                )
                
                html_path = os.path.join(tempfile.gettempdir(), 'easyreporter_report.html')
                with open(html_path, 'w', encoding='utf-8') as f:
                    f.write(html_content)
                
                # 调用独立脚本
                script_dir = os.path.dirname(os.path.abspath(__file__))
                renderer_script = os.path.join(script_dir, 'Code', 'pdf_renderer.py')
                
                if os.path.exists(renderer_script):
                    result = subprocess.run(
                        [sys.executable, renderer_script, html_path, pdf_path],
                        capture_output=True, text=True, timeout=120
                    )
                    
                    if result.returncode == 0 and os.path.exists(pdf_path) and os.path.getsize(pdf_path) > 0:
                        self.log_pdf_creation(f"✅ PDF 生成成功 (pdf_renderer): {pdf_path}")
                        try:
                            os.unlink(html_path)
                        except Exception:
                            pass
                        return pdf_path
                    else:
                        self.log_pdf_creation(f"pdf_renderer 失败: {result.stderr[:300]}")
                
                try:
                    os.unlink(html_path)
                except Exception:
                    pass
                    
            except Exception as e:
                self.log_pdf_creation(f"pdf_renderer 脚本失败: {str(e)}")
            
            # ===== 方案3: 简易 ReportLab PDF（最终备用） =====
            self.log_pdf_creation("所有浏览器方案失败，使用简易 ReportLab PDF 备用方案...")
            st.info(get_text("simple_pdf_fallback_info"))
            return self._create_simple_pdf_fallback(pdf_path)
            
        except ImportError as import_error:
            missing_module = str(import_error).split("'")[1] if "'" in str(import_error) else "unknown"
            st.error(get_text("pdf_missing_deps_error").format(missing_module))
            st.error(get_text("pdf_missing_deps"))
            return None
        except Exception as e:
            st.error(get_text("pdf_generation_failed_generic").format(str(e)))
            import traceback
            st.error(get_text("pdf_detailed_error").format(traceback.format_exc()))
            return None

    def _create_simple_pdf_fallback(self, pdf_path):
        """简易 ReportLab PDF 备用方案 - 当浏览器不可用时使用"""
        try:
            from reportlab.lib.pagesizes import A4
            from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
            from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
            from reportlab.lib.units import inch
            from reportlab.pdfbase import pdfmetrics
            from reportlab.pdfbase.ttfonts import TTFont
            import platform
            
            # 注册中文字体
            font_name = 'Helvetica'
            if platform.system() == "Windows":
                font_paths = [
                    "C:/Windows/Fonts/msyh.ttc",
                    "C:/Windows/Fonts/simhei.ttf",
                ]
                for fp in font_paths:
                    if os.path.exists(fp):
                        try:
                            pdfmetrics.registerFont(TTFont('ChineseFont', fp))
                            font_name = 'ChineseFont'
                            break
                        except Exception:
                            pass
            
            doc = SimpleDocTemplate(pdf_path, pagesize=A4,
                                    topMargin=0.6*inch, bottomMargin=0.6*inch,
                                    leftMargin=0.7*inch, rightMargin=0.7*inch)
            
            styles = getSampleStyleSheet()
            title_style = ParagraphStyle('Title', parent=styles['Heading1'],
                                         fontSize=24, fontName=font_name,
                                         alignment=1, spaceAfter=20)
            normal_style = ParagraphStyle('Normal', parent=styles['Normal'],
                                          fontSize=12, fontName=font_name,
                                          leading=18, spaceAfter=8)
            
            story = []
            story.append(Paragraph("AI Analysis Report", title_style))
            story.append(Spacer(1, 20))
            
            # 添加 AI 报告内容
            ai_report = st.session_state.get('ai_report', '')
            if ai_report:
                import re
                # 简化 Markdown → 纯文本
                clean = re.sub(r'[#*`\[\]\(\)]', '', ai_report)
                for line in clean.split('\n'):
                    line = line.strip()
                    if line:
                        story.append(Paragraph(line, normal_style))
            else:
                story.append(Paragraph("(No report content available)", normal_style))
            
            doc.build(story)
            
            if os.path.exists(pdf_path) and os.path.getsize(pdf_path) > 0:
                return pdf_path
            return None
            
        except Exception as e:
            self.log_pdf_creation(f"简易 PDF 备用方案也失败: {str(e)}")
            return None

    def _embed_charts_in_ai_report(self, ai_report, chart_previews_by_group):
        """将图表嵌入到AI报告的相应位置"""
        try:
            import base64
            import os
            import re
            
            if not ai_report or not chart_previews_by_group:
                return self.clean_text_for_html(ai_report) if ai_report else ""
            
            # 创建图表映射 - 根据图表类型和文件名建立映射
            chart_mapping = {}
            insight_dict = st.session_state.get('chart_insights', {})
            
            for group_name, group_data in chart_previews_by_group.items():
                charts = group_data.get('charts', {})
                for chart_type, chart_list in charts.items():
                    for chart_info in chart_list:
                        chart_path = chart_info.get('path', '')
                        if os.path.exists(chart_path):
                            # 从文件名提取图表类型关键词
                            filename = os.path.basename(chart_path).lower()
                            
                            # 定义图表类型关键词映射
                            chart_keywords = {
                                'scatter': ['scatter', 'distribution', '分布', '散点'],
                                'violin': ['violin', 'density', '小提琴', '密度'],
                                'box': ['box', 'boxplot', '箱线', '箱图'],
                                'bar': ['bar', 'count', '柱状', '计数'],
                                'heatmap': ['heatmap', 'correlation', '热图', '相关'],
                                'histogram': ['histogram', 'hist', '直方图', '分布图'],
                                'line': ['line', 'trend', '折线', '趋势'],
                                'pie': ['pie', 'proportion', '饼图', '比例']
                            }
                            
                            # 根据文件名匹配图表类型
                            matched_type = None
                            for chart_type_key, keywords in chart_keywords.items():
                                if any(keyword in filename for keyword in keywords):
                                    matched_type = chart_type_key
                                    break
                            
                            if matched_type:
                                if matched_type not in chart_mapping:
                                    chart_mapping[matched_type] = []
                                chart_mapping[matched_type].append({
                                    'path': chart_path,
                                    'group': group_name,
                                    'insight': insight_dict.get(chart_path, '')
                                })
            
            # 处理AI报告内容，查找图表相关的段落并插入图表
            processed_content = ai_report
            
            # 定义图表类型的中英文标题模式
            chart_patterns = {
                'scatter': [
                    r'(细胞分布.*?散点.*?分析|Cell.*?Distribution.*?Scatter.*?Analysis|散点图.*?分析|Scatter.*?Plot.*?Analysis)',
                    r'(分布.*?散点|Distribution.*?Scatter|细胞.*?分布|Cell.*?Distribution)'
                ],
                'violin': [
                    r'(小提琴图.*?分析|Violin.*?Plot.*?Analysis|密度.*?分布|Density.*?Distribution)',
                    r'(小提琴.*?图|Violin.*?Plot|密度.*?图|Density.*?Plot)'
                ],
                'box': [
                    r'(箱线图.*?分析|Box.*?Plot.*?Analysis|箱图.*?分析|Boxplot.*?Analysis)',
                    r'(箱线.*?图|Box.*?Plot|箱.*?图|Boxplot)'
                ],
                'bar': [
                    r'(柱状图.*?分析|Bar.*?Chart.*?Analysis|计数.*?分析|Count.*?Analysis)',
                    r'(柱状.*?图|Bar.*?Chart|计数.*?图|Count.*?Plot)'
                ],
                'heatmap': [
                    r'(热图.*?分析|Heatmap.*?Analysis|相关性.*?分析|Correlation.*?Analysis)',
                    r'(热.*?图|Heatmap|相关.*?图|Correlation.*?Plot)'
                ]
            }
            
            # 为每种图表类型查找匹配的段落并插入图表
            for chart_type, patterns in chart_patterns.items():
                if chart_type in chart_mapping:
                    charts = chart_mapping[chart_type]
                    
                    for pattern in patterns:
                        # 查找匹配的段落
                        matches = list(re.finditer(pattern, processed_content, re.IGNORECASE))
                        
                        if matches:
                            # 从后往前替换，避免位置偏移
                            for match in reversed(matches):
                                match_text = match.group(0)
                                match_start = match.start()
                                match_end = match.end()
                                
                                # 找到段落的结束位置（下一个换行符或文档结束）
                                paragraph_end = processed_content.find('\n\n', match_end)
                                if paragraph_end == -1:
                                    paragraph_end = len(processed_content)
                                
                                # 构建图表HTML
                                chart_html = self._create_chart_html_for_embedding(charts, chart_type)
                                
                                # 在段落后插入图表
                                processed_content = (
                                    processed_content[:paragraph_end] + 
                                    '\n\n' + chart_html + '\n\n' + 
                                    processed_content[paragraph_end:]
                                )
                                
                                # 移除已使用的图表，避免重复插入
                                if chart_type in chart_mapping:
                                    del chart_mapping[chart_type]
                                break
                            break
            
            # 清理HTML并返回
            return self.clean_text_for_html(processed_content)
            
        except Exception as e:
            self.log_message(f"Error embedding charts in AI report: {str(e)}", "error")
            return self.clean_text_for_html(ai_report) if ai_report else ""
    
    def _create_chart_html_for_embedding(self, charts, chart_type):
        """为嵌入创建图表HTML代码"""
        try:
            import base64
            
            html_parts = []
            
            for chart_info in charts[:2]:  # 最多显示2个图表
                chart_path = chart_info['path']
                group_name = chart_info['group']
                insight = chart_info['insight']
                
                if os.path.exists(chart_path):
                    # 编码图片为Base64
                    with open(chart_path, 'rb') as img_file:
                        img_data = img_file.read()
                        img_base64 = base64.b64encode(img_data).decode('utf-8')
                        img_ext = os.path.splitext(chart_path)[1].lower()
                        mime_type = 'image/png' if img_ext == '.png' else 'image/jpeg'
                    
                    # 创建图表HTML
                    chart_html = f"""
<div class='chart-container' style='margin: 18px 0; padding: 18px 20px; background: #f7f9fc; border-radius: 12px; border: none;'>
    <img src='data:{mime_type};base64,{img_base64}' class='chart-image' style='max-width: 72%; height: auto; display: block; margin: 16px auto; border-radius: 10px;' alt='{chart_type} chart for {group_name}'>
    <p class='chart-caption' style='text-align: center; font-style: italic; color: #4b5563; margin-top: 10px; font-size: 14px;'><strong>{get_text('file_name_label')}:</strong> {os.path.basename(chart_path)} ({group_name})</p>
"""
                    
                    # 添加AI解读
                    if insight and insight.strip():
                        chart_html += f"""
    <div class='ai-insight' style='background: #eef4ff; border-radius: 10px; padding: 16px 18px; margin-top: 12px;'>
        <h4 style='color: #1f2933; margin-bottom: 8px; font-size: 15px; font-weight: 600;'>{get_text('ai_insight_label')}</h4>
        <div style='line-height: 1.6; color: #1f2933;'>{self.clean_text_for_html(insight)}</div>
    </div>
"""
                    
                    chart_html += "</div>"
                    html_parts.append(chart_html)
            
            return '\n'.join(html_parts)
            
        except Exception as e:
            self.log_message(f"Error creating chart HTML for embedding: {str(e)}", "error")
            return ""

    def create_html_report_with_images_by_group(self, language=None):
        """创建按实验组别组织的HTML格式AI报告"""
        if language is None:
            language = st.session_state.get('language', 'zh')
        try:
            import base64
            import os
            from datetime import datetime
            from AI_helper import collect_chart_previews_by_group, format_target_for_display
            
            # 获取AI报告文本并格式化（sg → site）
            ai_report_raw = st.session_state.get('ai_report', '')
            ai_report = format_target_for_display(ai_report_raw) if ai_report_raw else ''
            
            # 调试：检查AI报告是否存在
            print(f"\n[DEBUG] ========== 开始生成HTML报告 ==========")
            print(f"[DEBUG] ai_report 长度: {len(ai_report) if ai_report else 0} 字符")
            if ai_report:
                print(f"[DEBUG] ai_report 前500字符:\n{ai_report[:500]}")
            else:
                print(f"[DEBUG] ⚠️ ai_report 为空！")
            print(f"[DEBUG] ==========================================\n")
            
            # 收集按实验组别组织的图表
            chart_previews_by_group = collect_chart_previews_by_group(st.session_state.work_dir, max_per_type=2)
            
            # 若用户为每个靶点选择了特定数据，则只保留这些数据用于报告
            selected_per_target = st.session_state.get('selected_data_per_target', {})
            if selected_per_target:
                import re
                filtered_previews = {}
                # selected_per_target结构：{protein: {target: data_id}}
                # 例如：{'CAS9': {'sg1': 'cas9-sg1_1-4', 'sg10': 'cas9-sg10_2-3'}}
                for protein, targets_dict in selected_per_target.items():
                    for target, selected_data_id in targets_dict.items():
                        # selected_data_id格式如 "cas9-sg10_1-4" (蛋白-靶点_重复-视野)
                        # chart_previews_by_group的key格式如 "cas9-sg10"
                        # 图表文件名格式：cas9-sg10_1-4_analysis.png
                        match = re.match(r'(cas\d+-sg\d+)[_-](\d+)[_-](\d+)', selected_data_id, re.IGNORECASE)
                        if match:
                            group_key = match.group(1).lower()
                            replicate_number = match.group(2)  # 重复次数：如 "1", "2", "3"
                            field_number = match.group(3)  # 视野编号：如 "1", "4"
                            
                            # 在chart_previews_by_group中查找匹配的key
                            for key in chart_previews_by_group.keys():
                                if key != 'summary_charts' and key.lower() == group_key:
                                    # 找到组后，过滤该组内的图表，只保留该重复和视野的文件
                                    group_data = chart_previews_by_group[key]
                                    filtered_group_data = {}
                                    
                                    # group_data结构：{chart_type: [{path, ext, filename}, ...]}
                                    for chart_type, chart_list in group_data.items():
                                        filtered_charts = []
                                        for chart_info in chart_list:
                                            filename = chart_info.get('filename', '')
                                            # 匹配多种文件名格式
                                            pattern1 = rf'{group_key}_{replicate_number}-{field_number}[._]'  # 连字符格式
                                            pattern2 = rf'{group_key}_{replicate_number}_{field_number}[._]'  # 下划线格式
                                            pattern3 = rf'{group_key}_{replicate_number}_.*?-{field_number}[._]'  # 原始图片格式
                                            if re.search(pattern1, filename, re.IGNORECASE) or re.search(pattern2, filename, re.IGNORECASE) or re.search(pattern3, filename, re.IGNORECASE):
                                                filtered_charts.append(chart_info)
                                        
                                        if filtered_charts:
                                            filtered_group_data[chart_type] = filtered_charts
                                    
                                    if filtered_group_data:
                                        filtered_previews[key] = filtered_group_data
                                    break
                
                # 保留summary_charts（柱状图/箱线图）
                summary = chart_previews_by_group.get('summary_charts')
                if summary:
                    filtered_previews['summary_charts'] = summary
                
                chart_previews_by_group = filtered_previews
            
            # 获取图表洞察字典
            insight_dict = st.session_state.get('chart_insights', {})
            
            # 读取SVG图标
            def load_svg_icon(icon_name):
                # 安全的图标fallback映射 - 使用Unicode符号避免编码问题
                icon_fallbacks = {
                    'microscope': '<span style="font-size: 24px; color: #4CAF50;">◉</span>',
                    'dna': '<span style="font-size: 24px; color: #2196F3;">◈</span>',
                    'chart': '<span style="font-size: 24px; color: #FF9800;">■</span>',
                    'ai-robot': '<span style="font-size: 24px; color: #9C27B0;">◆</span>',
                    'report': '<span style="font-size: 24px; color: #607D8B;">▣</span>',
                    'cell': '<span style="font-size: 24px; color: #E91E63;">●</span>',
                    'analysis': '<span style="font-size: 24px; color: #3F51B5;">▲</span>',
                    'group': '<span style="font-size: 24px; color: #FF5722;">◇</span>'
                }
                
                icon_path = os.path.join(st.session_state.work_dir, 'assets', 'icons', f'{icon_name}.svg')
                if os.path.exists(icon_path):
                    try:
                        with open(icon_path, 'r', encoding='utf-8') as f:
                            svg_content = f.read()
                            # 确保SVG内容安全且有效
                            if svg_content.strip() and '<svg' in svg_content:
                                return svg_content
                    except Exception as e:
                        print(f"Error loading SVG icon {icon_name}: {e}")
                
                # 如果SVG加载失败，使用安全的fallback
                return icon_fallbacks.get(icon_name, '<span style="font-size: 24px; color: #666;">●</span>')
            
            # 加载所有图标
            microscope_icon = load_svg_icon('microscope')
            dna_icon = load_svg_icon('dna')
            chart_icon = load_svg_icon('chart')
            ai_robot_icon = load_svg_icon('ai-robot')
            report_icon = load_svg_icon('report')
            cell_icon = load_svg_icon('cell')
            analysis_icon = load_svg_icon('analysis')
            group_icon = load_svg_icon('group')
            
            # 构建HTML内容
            lang_attr = "en" if language == "en" else "zh-CN"
            html_content = f"""
<!DOCTYPE html>
<html lang="{lang_attr}">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{get_text('html_report_title')}{get_text('html_report_by_group_suffix')}</title>
    <style>
        /* 全局排版优化 - 现代化设计 */
        body {{
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            font-size: 23px;
            line-height: 1.6;
            letter-spacing: 0.3px;
            margin: 0;
            padding: 0;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: #2c3e50;
            word-wrap: break-word;
            overflow-wrap: break-word;
            hyphens: auto;
            min-height: 100vh;
        }}
        
        /* 封面样式 - 专业学术风格 */
        .cover-page {{
            min-height: 100vh;
            display: flex;
            flex-direction: column;
            justify-content: center;
            align-items: center;
            background: linear-gradient(135deg, #2c3e50 0%, #34495e 50%, #3498db 100%);
            color: white;
            text-align: center;
            padding: 80px 60px;
            page-break-after: always;
            position: relative;
            overflow: hidden;
            box-shadow: inset 0 0 100px rgba(0,0,0,0.1);
        }}
        
        .cover-page::before {{
            content: '';
            position: absolute;
            top: 0;
            left: 0;
            right: 0;
            bottom: 0;
            background: url('data:image/svg+xml,<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100"><defs><pattern id="grid" width="15" height="15" patternUnits="userSpaceOnUse"><path d="M 15 0 L 0 0 0 15" fill="none" stroke="rgba(255,255,255,0.08)" stroke-width="0.5"/></pattern></defs><rect width="100" height="100" fill="url(%23grid)"/></svg>');
            opacity: 0.4;
        }}
        
        .cover-content {{
            position: relative;
            z-index: 1;
            max-width: 800px;
        }}
        
        .cover-title {{
            font-size: 57px;
            font-weight: 700;
            margin-bottom: 35px;
            text-shadow: 2px 2px 8px rgba(0,0,0,0.4);
            letter-spacing: 3px;
            line-height: 1.2;
            font-family: 'Times New Roman', serif;
        }}
        
        .cover-subtitle {{
            font-size: 42px;
            margin-bottom: 50px;
            opacity: 0.95;
            font-weight: 500;
            line-height: 1.4;
            text-align: center;
        }}
        
        .cover-icons {{
            display: flex;
            justify-content: center;
            gap: 30px;
            margin: 50px 0;
            flex-wrap: nowrap;
        }}
        
        .cover-icon {{
            width: 70px;
            height: 70px;
            background: rgba(255,255,255,0.15);
            border-radius: 15px;
            display: flex;
            align-items: center;
            justify-content: center;
            backdrop-filter: blur(15px);
            border: 2px solid rgba(255,255,255,0.25);
            transition: all 0.4s cubic-bezier(0.4, 0, 0.2, 1);
            box-shadow: 0 8px 32px rgba(0,0,0,0.1);
            filter: drop-shadow(0 4px 8px rgba(0,0,0,0.2));
        }}
        
        .cover-icon:hover {{
            transform: translateY(-8px) scale(1.05);
            background: rgba(255,255,255,0.25);
            box-shadow: 0 12px 40px rgba(0,0,0,0.15);
        }}
        
        .cover-icon svg {{
            width: 35px;
            height: 35px;
            fill: white;
            filter: drop-shadow(0 2px 4px rgba(0,0,0,0.2));
        }}
        
        .cover-info {{
            margin-top: 60px;
            font-size: 28px;
            opacity: 0.9;
            line-height: 1.6;
            text-align: center;
        }}
        
        .cover-info p {{
            margin: 10px 0;
            font-weight: 300;
            text-align: center;
            width: 100%;
        }}
        
        /* 主要内容样式 */
        .main-content {{
            max-width: 1200px;
            margin: 0 auto;
            padding: 60px 40px;
            background: rgba(255, 255, 255, 0.95);
            backdrop-filter: blur(20px);
            border-radius: 20px;
            box-shadow: 0 20px 40px rgba(0, 0, 0, 0.1);
            border: 1px solid rgba(255, 255, 255, 0.2);
            margin-top: 40px;
            margin-bottom: 40px;
        }}
        
        /* 学术论文格式标题层次 */
        h1 {{
            color: #000000;
            font-size: 41px;
            font-weight: 700;
            line-height: 1.2;
            margin-top: 45px;
            margin-bottom: 28px;
            border-bottom: 4px solid #000000;
            padding-bottom: 18px;
            text-align: center;
            letter-spacing: 1.5px;
            font-family: 'Times New Roman', serif;
        }}
        
        .title-icon {{
            display: inline-block;
            width: 32px;
            height: 32px;
            margin-right: 12px;
            vertical-align: middle;
            fill: #000000;
        }}
        
        .title-icon svg {{
            width: 100%;
            height: 100%;
        }}
        
        h2 {{
            color: #000000;
            font-size: 35px;
            font-weight: 600;
            line-height: 1.3;
            margin-top: 38px;
            margin-bottom: 22px;
            padding-left: 25px;
            border-left: 5px solid #000000;
            background-color: #f8f9fa;
            padding: 14px 25px;
            border-radius: 5px;
            font-family: 'Times New Roman', serif;
            letter-spacing: 1px;
        }}
        
        h3 {{
            color: #000000;
            font-size: 31px;
            font-weight: 600;
            line-height: 1.35;
            margin-top: 32px;
            margin-bottom: 18px;
            padding-left: 15px;
            border-bottom: 2px solid #000000;
            padding-bottom: 10px;
            font-family: 'Times New Roman', serif;
            letter-spacing: 0.5px;
        }}
        
        h4 {{
            color: #000000;
            font-size: 27px;
            font-weight: 500;
            line-height: 1.4;
            margin-top: 26px;
            margin-bottom: 15px;
            font-family: 'Times New Roman', serif;
            border-left: 3px solid #000000;
            padding-left: 12px;
            letter-spacing: 0.3px;
        }}
        
        /* 正文段落样式 */
        p {{
            margin: 0 0 20px 0;
            line-height: 1.85;
            text-align: justify;
            text-indent: 2em;
            font-size: 23px;
            font-family: 'Times New Roman', 'SimSun', serif;
            color: #000000;
            word-wrap: break-word;
            overflow-wrap: break-word;
            hyphens: auto;
            white-space: normal;
            letter-spacing: 0.3px;
            text-rendering: optimizeLegibility;
            -webkit-font-smoothing: antialiased;
            -moz-osx-font-smoothing: grayscale;
        }}
        
        /* 首段不缩进 */
        p:first-of-type {{
            text-indent: 0;
            margin-top: 0;
        }}
        
        /* 标题后的首段不缩进 */
        h1 + p, h2 + p, h3 + p, h4 + p, h5 + p, h6 + p {{
            text-indent: 0;
        }}
        
        /* 修复英文版换行空白问题 */
        .text-content {{
            white-space: normal;
            word-wrap: break-word;
            overflow-wrap: break-word;
            hyphens: auto;
            line-height: 1.85;
            font-family: 'Times New Roman', 'SimSun', serif;
        }}
        
        .text-content p {{
            white-space: normal;
            word-wrap: break-word;
            overflow-wrap: break-word;
            margin-bottom: 20px;
            font-family: 'Times New Roman', 'SimSun', serif;
            letter-spacing: 0.3px;
        }}
        
        /* 实验组别容器样式 */
        .group-container {{
            margin: 32px 0;
            padding: 26px 28px;
            background: #f8fafc;
            border-radius: 16px;
            border: none;
        }}

        /* 图表容器样式 */
        .chart-container {{
            margin: 24px 0;
            padding: 20px 22px;
            background: #ffffff;
            border-radius: 12px;
            border: 1px solid #e5e7eb;
            box-shadow: none;
        }}

        .chart-image {{
            width: 74%;
            max-width: 740px;
            height: auto;
            display: block;
            margin: 18px auto;
            border-radius: 10px;
            box-shadow: none;
            border: none;
        }}

        .chart-caption {{
            text-align: center;
            font-style: italic;
            color: #4b5563;
            margin-top: 12px;
            font-size: 20px;
            line-height: 1.6;
        }}

        /* 三列图片网格布局 */
        .image-grid-row {{
            display: flex;
            justify-content: space-between;
            margin: 20px 0;
            gap: 16px;
            flex-wrap: wrap;
        }}

        .image-col {{
            flex: 0 0 calc(33.333% - 11px);
            max-width: calc(33.333% - 11px);
            text-align: center;
        }}

        .image-col img {{
            width: 100%;
            height: auto;
            border-radius: 8px;
            box-shadow: 0 2px 8px rgba(0,0,0,0.1);
        }}

        .image-col h5 {{
            margin: 10px 0 8px 0;
            font-size: 23px;
            font-weight: 600;
            color: #1f2937;
        }}

        /* AI洞察样式 */
        .ai-insight {{
            background: #eef4ff;
            border-radius: 12px;
            padding: 20px 22px;
            margin: 18px 0;
            font-size: 21px;
            line-height: 1.7;
            border: none;
        }}

        .ai-insight-title {{
            color: #1f2933;
            font-weight: 600;
            margin-bottom: 12px;
            font-size: 22px;
            letter-spacing: 0.3px;
        }}

        /* 响应式设计 */
        @media (max-width: 768px) {{
            .cover-title {{
                font-size: 34px;
                letter-spacing: 0.8px;
            }}
            
            .cover-subtitle {{
                font-size: 28px;
            }}
            
            .cover-icons {{
                gap: 20px;
                flex-wrap: wrap;
            }}
            
            .cover-icon {{
                width: 64px;
                height: 64px;
            }}
            
            .cover-icon svg {{
                width: 30px;
                height: 30px;
            }}
            
            h1 {{
                font-size: 26px;
                margin-top: 30px;
                margin-bottom: 18px;
            }}
            
            h2 {{
                font-size: 22px;
                margin-top: 26px;
                margin-bottom: 16px;
            }}
            
            h3 {{
                font-size: 20px;
                margin-top: 22px;
                margin-bottom: 14px;
            }}
            
            .main-content {{
                padding: 32px 24px;
            }}
            
            .group-container {{
                margin: 24px 0;
                padding: 20px;
            }}
        }}

        /* 打印样式 */
        @media print {{
            body {{
                font-size: 12pt;
                line-height: 1.6;
            }}
            .cover-page {{
                page-break-after: always;
                background: #ffffff !important;
                color: #1f2933 !important;
            }}
            .group-container {{
                page-break-inside: avoid;
            }}
            h1, h2, h3 {{
                page-break-after: avoid;
            }}
        }}
    </style>
</head>
<body>
    <!-- 封面页 -->
    <div class="cover-page">
        <div class="cover-content">
            <h1 class="cover-title">{get_text('html_report_title')}{get_text('html_report_by_group_suffix')}</h1>
            <p class="cover-subtitle">{get_text("html_report_subtitle")}</p>
            
            <div class="cover-icons">
                <div class="cover-icon">
                    {microscope_icon}
                </div>
                <div class="cover-icon">
                    {dna_icon}
                </div>
                <div class="cover-icon">
                    {chart_icon}
                </div>
                <div class="cover-icon">
                    {group_icon}
                </div>
                <div class="cover-icon">
                    {ai_robot_icon}
                </div>
                <div class="cover-icon">
                    {report_icon}
                </div>
            </div>
            
            <div class="cover-info">
            </div>
        </div>
    </div>

    <!-- 主要内容 -->
    <div class="main-content">
        <h1><span class="title-icon">{ai_robot_icon}</span> {get_text('html_report_title')}{get_text('html_report_by_group_suffix')}</h1>
"""
            
            # 解析AI报告，提取每个蛋白、每种图表类型的文字解读
            import re
            protein_sections = {}  # {protein_type: {chart_type: text}}
            summary_lines = []
            insight_lines = []

            if ai_report:
                report_text = ai_report.replace('\r\n', '\n')
                lines = report_text.split('\n')

                current_protein = None
                current_chart = None
                in_summary = False
                in_insight = False

                def extract_protein(name: str):
                    match = re.search(r'(cas\d+)', name, re.IGNORECASE)
                    return match.group(1).upper() if match else None

                chart_keywords = [
                    ('细胞分布散点图', 'Cell_Distribution_Scatter'),
                    ('细胞分布特征', 'Cell_Distribution_Scatter'),
                    ('Cell Distribution Scatter', 'Cell_Distribution_Scatter'),
                    ('Cell Distribution Features', 'Cell_Distribution_Scatter'),
                    ('Cell Distribution', 'Cell_Distribution_Scatter'),
                    ('细胞聚类散点图', 'Cell_Clustering_Scatter'),
                    ('细胞集群散点图', 'Cell_Clustering_Scatter'),
                    ('聚类特征', 'Cell_Clustering_Scatter'),
                    ('聚类模式', 'Cell_Clustering_Scatter'),
                    ('Cell Clustering Scatter', 'Cell_Clustering_Scatter'),
                    ('Clustering Features', 'Cell_Clustering_Scatter'),
                    ('Clustering Patterns', 'Cell_Clustering_Scatter'),
                    ('Cell Clustering', 'Cell_Clustering_Scatter'),
                    ('模拟流式细胞术', 'Simulated_Flow_Cytometry'),
                    ('流式细胞术', 'Simulated_Flow_Cytometry'),
                    ('流式细胞', 'Simulated_Flow_Cytometry'),
                    ('荧光表型', 'Simulated_Flow_Cytometry'),
                    ('荧光强度', 'Simulated_Flow_Cytometry'),
                    ('流式特征', 'Simulated_Flow_Cytometry'),
                    ('Simulated Flow Cytometry', 'Simulated_Flow_Cytometry'),
                    ('Flow Cytometry Features', 'Simulated_Flow_Cytometry'),
                    ('Flow Cytometry Analysis', 'Simulated_Flow_Cytometry'),
                    ('Fluorescence Phenotype', 'Simulated_Flow_Cytometry'),
                    ('Flow Cytometry', 'Simulated_Flow_Cytometry'),
                ]

                def extract_after_keyword(full_line: str, keyword: str) -> str:
                    """Return the descriptive text that follows the chart keyword, with better cleaning."""
                    # 先去除Markdown格式符号
                    clean_line = full_line.replace('**', '').replace('__', '').replace('*', '')
                    clean_line = re.sub(r'^\s*[-•]\s*', '', clean_line)
                    
                    # 尝试匹配关键词后的内容（支持冒号、逗号等分隔符）
                    pattern = rf"{re.escape(keyword)}[：:、，,\-\s]*[:：]?\s*(.*)"
                    match = re.search(pattern, clean_line, re.IGNORECASE)
                    if match and match.group(1).strip():
                        result = match.group(1).strip()
                        # 去除开头的"基于...图分析"等冗余文字
                        result = re.sub(r'^基于\s*\w+\s*图分析[，,、]?\s*', '', result)
                        return result
                    
                    # fallback: 直接移除关键词
                    if keyword.lower() in clean_line.lower():
                        idx = clean_line.lower().index(keyword.lower())
                        remainder = clean_line[idx + len(keyword):]
                        remainder = re.sub(r'^[：:、，,\-\s\*]+', '', remainder)
                        remainder = re.sub(r'^基于\s*\w+\s*图分析[，,、]?\s*', '', remainder)
                        return remainder.strip()
                    
                    return ""

                for raw_line in lines:
                    line = raw_line.strip()
                    if not line:
                        continue

                    lower_line = line.lower()

                    if line.startswith('●'):
                        # 进入某个蛋白组别，例如“●CAS9-SG10组分析”
                        current_protein = extract_protein(line.lstrip('●').strip())
                        if current_protein:
                            protein_sections.setdefault(current_protein, {})
                        current_chart = None
                        in_summary = False
                        in_insight = False
                        continue

                    heading_match = re.search(r'(cas\d+)', line, re.IGNORECASE)
                    if heading_match and (
                        line.startswith('#')
                        or line.startswith('-')
                        or '蛋白' in line
                        or 'protein' in lower_line
                        or '组分析' in line
                        or 'analysis' in lower_line
                    ):
                        current_protein = heading_match.group(1).upper()
                        protein_sections.setdefault(current_protein, {})
                        current_chart = None
                        in_summary = False
                        in_insight = False
                        continue

                    if line.startswith('▲') or '综合对比分析' in line or line.startswith('📊') or 'comprehensive comparison' in lower_line or 'overall comparative analysis' in lower_line or 'inter-protein comparative analysis' in lower_line or 'comparative analysis' in lower_line:
                        # 综合分析相关内容
                        current_protein = None
                        current_chart = None
                        in_summary = True
                        in_insight = False
                        summary_lines.append(line)
                        continue

                    if line.startswith('🔍') or '关键发现' in line or '结论' in line or '建议' in line or '局限' in line or 'key findings' in lower_line or 'conclusion' in lower_line or 'conclusions' in lower_line or 'recommendation' in lower_line or 'recommendations' in lower_line or 'limitation' in lower_line or 'limitations' in lower_line:
                        # 关键发现/结论/建议部分
                        current_protein = None
                        current_chart = None
                        in_summary = False
                        in_insight = True
                        insight_lines.append(line)
                        continue

                    chart_line_handled = False
                    for keyword, chart_label in chart_keywords:
                        if keyword in line:
                            current_chart = chart_label
                            chart_line_handled = True

                            if current_protein:
                                protein_sections[current_protein].setdefault(current_chart, [])
                                extra_text = extract_after_keyword(line, keyword)
                                if extra_text:
                                    protein_sections[current_protein][current_chart].append(extra_text)
                            else:
                                captured_text = extract_after_keyword(line, keyword)
                                if captured_text:
                                    summary_lines.append(captured_text)
                                else:
                                    summary_lines.append(line)

                            break

                    if chart_line_handled:
                        continue

                    # 普通文本内容，追加到当前上下文
                    if current_protein and current_chart:
                        protein_sections[current_protein][current_chart].append(line)
                    elif in_summary:
                        summary_lines.append(line)
                    elif in_insight:
                        insight_lines.append(line)

                # 将每个列表拼接为字符串
                for prot, charts in protein_sections.items():
                    for chart_type, texts in charts.items():
                        protein_sections[prot][chart_type] = '\n'.join(texts).strip()

            comprehensive_analysis_text = '\n'.join(summary_lines).strip()
            key_findings_text = '\n'.join(insight_lines).strip()

            # 调试输出
            print(f"\n[DEBUG] ========== AI报告解析结果 ==========")
            print(f"[DEBUG] protein_sections keys: {list(protein_sections.keys())}")
            for prot, charts in protein_sections.items():
                print(f"[DEBUG] 蛋白 {prot}:")
                for chart_type, text in charts.items():
                    print(f"[DEBUG]   - {chart_type}: {len(text)} 字符")
                    if text:
                        print(f"[DEBUG]     前100字符: {text[:100]}...")
            print(f"[DEBUG] comprehensive_analysis_text: {len(comprehensive_analysis_text)} 字符")
            print(f"[DEBUG] key_findings_text: {len(key_findings_text)} 字符")
            print(f"[DEBUG] ========================================\n")

            # 按组别展示分析结果（key 与 collect_chart_previews_by_group 返回的下划线格式保持一致）
            chart_type_order = ['Cell_Distribution_Scatter', 'Cell_Clustering_Scatter', 'Simulated_Flow_Cytometry']
            if language == 'en':
                chart_type_names = {
                    'Cell_Distribution_Scatter': 'Cell Distribution Scatter',
                    'Cell_Clustering_Scatter': 'Cell Clustering Scatter',
                    'Simulated_Flow_Cytometry': 'Simulated Flow Cytometry'
                }
            else:
                chart_type_names = {
                    'Cell_Distribution_Scatter': '细胞分布散点图',
                    'Cell_Clustering_Scatter': '细胞聚类散点图',
                    'Simulated_Flow_Cytometry': '模拟流式细胞术'
                }
            
            for group_name, group_data in chart_previews_by_group.items():
                # 跳过summary_charts,稍后单独处理
                if group_name == 'summary_charts':
                    continue
                    
                html_content += f"        <div class='group-container'>\n"
                html_content += f"            <h2><span class='title-icon'>{group_icon}</span>{get_text('group_analysis_heading').format(group_name.upper())}</h2>\n"
                
                # group_data结构是 {chart_type: [{path, ext, filename}, ...]}
                # 不再有'charts'这一层
                charts = group_data
                
                # 提取该组对应的蛋白类型 (如: cas9-sg10 -> CAS9)
                protein_type = None
                if group_name.lower() == 'wt':
                    protein_type = 'WT'
                else:
                    protein_match = re.match(r'(cas\d+)', group_name, re.IGNORECASE)
                    if protein_match:
                        protein_type = protein_match.group(1).upper()
                
                # 按指定顺序展示每种图表类型
                for chart_type in chart_type_order:
                    if chart_type in charts and charts[chart_type]:
                        html_content += f"            <h3><span class='title-icon'>{chart_icon}</span>{get_text('chart_analysis_heading').format(chart_type_names.get(chart_type, chart_type))}</h3>\n"
                        
                        # 展示该类型的所有图表
                        for chart_info in charts[chart_type]:
                            chart_path = chart_info.get('path', '')
                            if os.path.exists(chart_path):
                                html_content += "            <div class='chart-container'>\n"
                                
                                try:
                                    with open(chart_path, 'rb') as img_file:
                                        img_data = img_file.read()
                                        img_base64 = base64.b64encode(img_data).decode('utf-8')
                                        img_ext = os.path.splitext(chart_path)[1].lower()
                                        mime_type = 'image/png' if img_ext == '.png' else 'image/jpeg'
                                        
                                        # 提取友好的图片名称（Cas9-site1格式）
                                        friendly_name = self.extract_friendly_chart_name(os.path.basename(chart_path))
                                        
                                        html_content += f"                <img src='data:{mime_type};base64,{img_base64}' class='chart-image' alt='{chart_type} - {group_name}'>\n"
                                        html_content += f"                <p class='chart-caption'><strong>{get_text('file_name_label')}</strong> {friendly_name}</p>\n"
                                        
                                except Exception as e:
                                    html_content += f"                <p>❌ {get_text('could_not_load_image').format(str(e))}</p>\n"
                                
                                html_content += "            </div>\n"
                        
                        # 在所有该类型图表展示后，添加该类型的AI分析
                        if protein_type and protein_type in protein_sections:
                            ai_text = protein_sections[protein_type].get(chart_type, '')
                            if ai_text:
                                html_content += f"            <div class='ai-insight'>\n"
                                html_content += f"                <h4 class='ai-insight-title'>{get_text('ai_insight_title')}</h4>\n"
                                html_content += f"                <div class='text-content'>{self.clean_text_for_html(ai_text)}</div>\n"
                                html_content += f"            </div>\n"
                
                html_content += f"        </div>\n"
            
            # 添加综合对比分析部分
            html_content += f"        <div class='group-container'>\n"
            html_content += f"            <h2><span class='title-icon'>{analysis_icon}</span>{get_text('comparative_analysis_section_title')}</h2>\n"
            
            # 收集所有综合分析图表（柱状图、箱线图、相关性图等）
            comprehensive_charts = []
            
            # 从summary_charts中收集柱状图、箱线图与相关性图
            if 'summary_charts' in chart_previews_by_group:
                summary_charts = chart_previews_by_group['summary_charts']
                for chart_type, chart_list in summary_charts.items():
                    if chart_type in ['Grouped_Bar', 'Grouped_Box', 'Correlation_Scatter', 'Correlation_Heatmap']:
                        for chart_info in chart_list:
                            comprehensive_charts.append(chart_info)
            
            # 从其他组别中收集相关性图等其他综合分析图表
            for group_name, group_data in chart_previews_by_group.items():
                if group_name == 'summary_charts':
                    continue  # 已经处理过了
                    
                # 如果group_data是字典且包含charts键
                if isinstance(group_data, dict):
                    charts = group_data.get('charts', group_data)  # 兼容不同的数据结构
                    for chart_type, chart_list in charts.items():
                        if chart_type in ['Correlation', 'Correlation_Scatter', 'Correlation_Heatmap', '综合分析']:
                            for chart_info in chart_list:
                                if chart_info not in comprehensive_charts:
                                    comprehensive_charts.append(chart_info)
            
            if comprehensive_charts:
                html_content += f"            <h3><span class='title-icon'>{chart_icon}</span>{get_text('statistical_charts_heading')}</h3>\n"
                for chart_info in comprehensive_charts:
                    chart_path = chart_info.get('path', '')
                    if os.path.exists(chart_path):
                        html_content += "            <div class='chart-container'>\n"
                        
                        try:
                            with open(chart_path, 'rb') as img_file:
                                img_data = img_file.read()
                                img_base64 = base64.b64encode(img_data).decode('utf-8')
                                img_ext = os.path.splitext(chart_path)[1].lower()
                                mime_type = 'image/png' if img_ext == '.png' else 'image/jpeg'
                                
                                # 提取友好的图片名称（Cas9-site1格式）
                                friendly_name = self.extract_friendly_chart_name(os.path.basename(chart_path))
                                
                                html_content += f"                <img src='data:{mime_type};base64,{img_base64}' class='chart-image' alt='{get_text('statistical_charts_heading')}'>\n"
                                html_content += f"                <p class='chart-caption'><strong>{get_text('file_name_label')}</strong> {friendly_name}</p>\n"
                                
                                # 添加AI解读
                                if chart_path in insight_dict and insight_dict[chart_path]:
                                    html_content += f"                <div class='ai-insight'>\n"
                                    html_content += f"                    <h4 class='ai-insight-title'>{get_text('ai_insight_label')}</h4>\n"
                                    html_content += f"                    <div class='text-content'>{self.clean_text_for_html(insight_dict[chart_path])}</div>\n"
                                    html_content += f"                </div>\n"
                                
                        except Exception as e:
                            html_content += f"                <p>❌ {get_text('could_not_load_image').format(str(e))}</p>\n"
                        
                        html_content += "            </div>\n"
            
            # 添加综合分析与关键发现的AI文字
            if comprehensive_analysis_text:
                html_content += f"            <div class='ai-insight'>\n"
                html_content += f"                <h4 class='ai-insight-title'>{get_text('ai_comprehensive_analysis_heading')}</h4>\n"
                html_content += f"                <div class='text-content'>{self.clean_text_for_html(comprehensive_analysis_text)}</div>\n"
                html_content += f"            </div>\n"

            if key_findings_text:
                html_content += f"            <div class='ai-insight'>\n"
                html_content += f"                <h4 class='ai-insight-title'>{get_text('key_findings_recommendations_heading')}</h4>\n"
                html_content += f"                <div class='text-content'>{self.clean_text_for_html(key_findings_text)}</div>\n"
                html_content += f"            </div>\n"
            
            html_content += f"        </div>\n"
            
            html_content += """
    </div>
</body>
</html>
"""
            
            return html_content
            
        except Exception as e:
            self.log_message(f"Failed to create HTML report by group: {str(e)}", "error")
            # 如果生成HTML失败，返回纯文本报告
            return st.session_state.get('ai_report', get_text('html_generation_failed'))

def main():
    """主函数"""
    app = EasyReporterApp()
    
    # 渲染页面
    app.render_header()
    
    # 检查项目数据状态
    existing_data = app.check_existing_data()
    
    # 如果打开的项目有完整的数据，提供快捷通道
    if not st.session_state.step1_completed and (existing_data["has_cellpose_output"] or existing_data["has_charts"]):
        st.info(get_text("quick_start_ai_info"))
        col1, col2 = st.columns([1, 1])
        with col1:
            if st.button(get_text("quick_start_ai_btn"), key="quick_start_ai"):
                st.session_state.step1_completed = True
                # 注意：不再自动设置 skip_step2 和 skip_step3，让用户在步骤2/3中自行选择
                st.success(get_text("quick_mode_enabled"))
                st.rerun()
        with col2:
            if st.button(get_text("start_over_btn"), key="start_from_beginning"):
                st.session_state.skip_step2 = False
                st.session_state.skip_step3 = False
                st.info(get_text("start_from_step1"))
    
    # 根据步骤显示不同内容
    if not st.session_state.step1_completed:
        app.render_step1()
    else:
        # 显示步骤1完成的状态
        st.success(get_text("step1_completed_msg"))

        # 添加一个返回步骤1的选项
        if st.button(get_text("back_to_step1_button")):
            st.session_state.step1_completed = False
            st.rerun()

        st.markdown("---")

        # 渲染步骤2、3和4
        app.render_step2()
        app.render_step3()
        app.render_step4()

    # 显示日志（只在页面底部显示一次）
    st.markdown("---")
    app.display_log()
    
    # 侧边栏信息
    with st.sidebar:
        st.header(get_text("app_info_header"))
        
        # 项目管理部分
        st.subheader(get_text("project_management"))
        
        # 获取所有已存在的项目
        script_dir = os.path.dirname(os.path.abspath(__file__))
        projects_dir = os.path.join(script_dir, "EasyReporter_Projects")
        existing_projects = []
        if os.path.exists(projects_dir):
            existing_projects = [d for d in os.listdir(projects_dir) if os.path.isdir(os.path.join(projects_dir, d))]
        
        # 显示当前项目
        current_project = st.session_state.project_name if st.session_state.project_name else get_text("no_project_selected")
        st.info(get_text("current_project_label").format(current_project))
        
        # 项目选择器
        action_labels = [get_text("continue_current"), get_text("open_existing"), get_text("create_new")]
        if st.session_state.get("project_action") not in action_labels:
            st.session_state.pop("project_action", None)
        project_action = st.radio(
            get_text("project_action"),
            action_labels,
            key="project_action"
        )
        
        if project_action == get_text("open_existing") and existing_projects:
            selected_project = st.selectbox(
                get_text("select_project"),
                existing_projects,
                key="selected_existing_project"
            )
            if st.button(get_text("open_project_btn")):
                st.session_state.work_dir = None
                st.session_state.project_name = selected_project
                st.session_state.step1_completed = False
                st.session_state.uploaded_files = []
                st.session_state.processing_log = []
                st.session_state.skip_step2 = False
                st.session_state.skip_step3 = False
                st.success(get_text("project_switched").format(selected_project))
                st.rerun()
            
            # 显示项目数据状态
            if selected_project:
                temp_work_dir = os.path.join(projects_dir, selected_project)
                if os.path.exists(temp_work_dir):
                    st.markdown(get_text("project_data_status"))
                    
                    # 检查图片
                    data_dir = os.path.join(temp_work_dir, "Data")
                    has_images = os.path.exists(data_dir) and any(
                        f.lower().endswith(('.tif', '.tiff', '.png', '.jpg')) 
                        for root, _, files in os.walk(data_dir) for f in files
                    )
                    st.write(f"{'✅' if has_images else '❌'} {get_text('raw_images_label')}")
                    
                    # 检查Cellpose输出
                    cellpose_dir = os.path.join(temp_work_dir, "Cellpose_output", "Cell_Counts")
                    has_cellpose = os.path.exists(cellpose_dir) and len(os.listdir(cellpose_dir)) > 0
                    st.write(f"{'✅' if has_cellpose else '❌'} {get_text('segmentation_results_label')}")
                    
                    # 检查荧光强度
                    intensity_dir = os.path.join(temp_work_dir, "Cellpose_output", "Fluorescence_Intensity")
                    has_intensity = os.path.exists(intensity_dir) and len(os.listdir(intensity_dir)) > 0
                    st.write(f"{'✅' if has_intensity else '❌'} {get_text('fluorescence_data_label')}")
                    
                    # 检查图表
                    chart_dir = os.path.join(temp_work_dir, "Chart")
                    has_charts = os.path.exists(chart_dir) and any(
                        f.lower().endswith(('.png', '.jpg', '.pdf'))
                        for root, _, files in os.walk(chart_dir) for f in files
                    )
                    st.write(f"{'✅' if has_charts else '❌'} {get_text('statistical_charts_label')}")
        
        elif project_action == get_text("create_new"):
            new_project_name = st.text_input(
                get_text("new_project_name"),
                placeholder=get_text("project_name_placeholder"),
                key="new_project_name_input"
            )
            if st.button(get_text("create_project_btn")):
                if new_project_name and new_project_name.strip():
                    # 验证项目名称（不允许特殊字符）
                    import re
                    if re.match(r'^[\w\-]+$', new_project_name):
                        st.session_state.work_dir = None
                        st.session_state.project_name = new_project_name.strip()
                        st.session_state.step1_completed = False
                        st.session_state.uploaded_files = []
                        st.session_state.processing_log = []
                        st.success(get_text("project_created").format(new_project_name))
                        st.rerun()
                    else:
                        st.error(get_text("invalid_project_name"))
                else:
                    st.error(get_text("enter_valid_name"))
        
        st.markdown("---")
        
        st.info(get_text("working_dir_label").format(st.session_state.work_dir))
        st.info(get_text("uploaded_files_label").format(len(st.session_state.uploaded_files)))

        # 显示当前状态
        st.subheader(get_text("current_status_header"))

        # 步骤完成状态
        step1_status = get_text("step_status_completed") if st.session_state.step1_completed else get_text("step_status_not_completed")
        st.info(get_text("step1_status_label").format(step1_status))

        # 显示当前Cellpose模式
        mode_emoji = {
            "python": "🐍",
            "apptainer": "📦"
        }
        if st.session_state.get('language', 'zh') == 'en':
            mode_name = {
                "python": "Direct Python",
                "apptainer": "Apptainer Container"
            }
        else:
            mode_name = {
                "python": "Python 模式",
                "apptainer": "Apptainer 容器"
            }
        current_mode = st.session_state.get('cellpose_mode', 'python')
        st.info(get_text("cellpose_mode_label_status").format(mode_emoji.get(current_mode, '🔧'), mode_name.get(current_mode, current_mode)))

        # 调试信息
        with st.expander(get_text("debug_info_expander")):
            st.write(get_text("session_state_label"))
            st.json({
                "step1_completed": st.session_state.step1_completed,
                "uploaded_files_count": len(st.session_state.uploaded_files),
                "cellpose_mode": st.session_state.get('cellpose_mode', 'python'),
                "work_dir_exists": os.path.exists(st.session_state.work_dir) if st.session_state.work_dir else False,
                "openai_api_key_set": bool(st.session_state.openai_api_key)
            })

        # 环境检测
        st.subheader(get_text("environment_check_header"))

        # 检测Python环境
        try:
            import cellpose
            st.success("✅ Cellpose (Python)")
        except ImportError:
            st.error("❌ Cellpose (Python)")



        # 检测WSL/Apptainer (简化检测)
        try:
            result = subprocess.run(
                ["wsl", "--list"],
                capture_output=True,
                text=True,
                encoding='utf-8',
                errors='ignore'
            )
            if result.returncode == 0:
                st.success("✅ WSL")
            else:
                st.error("❌ WSL")
        except:
            st.error("❌ WSL")

        if st.button(get_text("clear_work_dir_btn")):
            if st.session_state.work_dir and os.path.exists(st.session_state.work_dir):
                shutil.rmtree(st.session_state.work_dir)
                st.session_state.work_dir = None
                st.session_state.step1_completed = False
                st.session_state.processing_log = []
                st.session_state.uploaded_files = []
                st.success(get_text("work_dir_cleared"))
                st.rerun()

if __name__ == "__main__":
    main()
