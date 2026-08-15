#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Cellpose batch processing script, keeping output structure aligned with the input
Functionally equivalent to the original 1.cellpose.sh script
"""

import os
import sys
import argparse
import subprocess
import glob
import csv
from pathlib import Path
import re
import io

# 确保在Windows环境下正确处理Unicode字符
if sys.platform.startswith('win'):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')
import shutil


class CellposeProcessor:
    def __init__(self):
        self.input_folder = ""
        self.output_folder = ""
        self.apptainer_path = ""
        self.use_gpu = False
        self.pretrained_model = "cyto3"
        self.mode = "apptainer"  # default aligns with the shell script
        
    def parse_arguments(self):
        """Parse command-line arguments"""
        parser = argparse.ArgumentParser(description='Cellpose batch processing script')
        parser.add_argument('--parent-folder', required=True, 
                          help='Input parent folder path')
        parser.add_argument('--output-folder', required=True,
                          help='Output folder path')
        # mode: apptainer or python
        parser.add_argument('--mode', choices=['apptainer', 'python'], default='apptainer',
                          help='Run mode: apptainer or python (default: apptainer)')

        parser.add_argument('--apptainer-path', required=False,
                          help='Path to Apptainer image file (only required in apptainer mode)')
        parser.add_argument('--use-gpu', action='store_true',
                          help='Use GPU acceleration')
        parser.add_argument('--pretrained-model', default='cyto3',
                          help='Pretrained model name (default: cyto3)')
        
        args = parser.parse_args()

        self.input_folder = args.parent_folder
        self.output_folder = args.output_folder
        self.mode = args.mode
        self.apptainer_path = args.apptainer_path
        self.use_gpu = args.use_gpu
        self.pretrained_model = args.pretrained_model
        
    def validate_arguments(self):
        """Validate arguments"""
        if not self.input_folder or not self.output_folder:
            print("Error: Missing required arguments")
            print("Usage:")
            print("  python 1.cellpose.py --parent-folder ./data --output-folder ./output [--mode apptainer|python] [--apptainer-path cellpose.sif] [--use-gpu] [--pretrained-model cyto3]")
            sys.exit(1)

        if self.mode == 'apptainer':
            # Check apptainer availability
            if shutil.which('apptainer') is None:
                print("ERROR: Apptainer CLI not found on PATH. Please run inside WSL with Apptainer installed or use python mode.")
                sys.exit(1)
            if not self.apptainer_path:
                print("Error: --apptainer-path is required in apptainer mode")
                sys.exit(1)
            # Resolve apptainer image path: try CWD relative, script-relative, then absolute
            candidates = []
            if not os.path.isabs(self.apptainer_path):
                cwd_path = os.path.realpath(os.path.join(os.getcwd(), self.apptainer_path))
                script_dir = os.path.dirname(os.path.abspath(__file__))
                script_rel = os.path.realpath(os.path.join(script_dir, self.apptainer_path))
                candidates.extend([cwd_path, script_rel])
            else:
                candidates.append(self.apptainer_path)
            resolved = None
            for p in candidates:
                if os.path.isfile(p):
                    resolved = p
                    break
            if resolved is None:
                print("Error: Apptainer image not found. Tried paths:")
                for p in candidates:
                    print(f"  - {p}")
                sys.exit(1)
            self.apptainer_path = resolved
            print(f"Using Apptainer image: {self.apptainer_path}")
            
    def setup_model_path(self):
        """Construct model path and mounts (based on script directory to avoid CWD differences)"""
        script_dir = os.path.dirname(os.path.abspath(__file__))
        self.model_dir = os.path.realpath(os.path.join(script_dir, "../models"))
        # Host model path
        self.pretrained_model_path_host = os.path.join(self.model_dir, self.pretrained_model)
        # Container model path (via --bind mapped to /models)
        self.pretrained_model_path_container = f"/models/{self.pretrained_model}"

        # cellpose 2.x 要求 pretrained_model 指向模型“文件”；而 models 目录内的
        # 模型采用“目录内同名文件”的布局（如 models/cyto3/cyto3）。
        # 若模型是目录，则自动指向目录内的同名文件，避免 torch.load(目录) 报 PermissionError。
        if os.path.isdir(self.pretrained_model_path_host):
            inner_file = os.path.join(self.pretrained_model_path_host, self.pretrained_model)
            if os.path.isfile(inner_file):
                self.pretrained_model_path_host = inner_file
                self.pretrained_model_path_container = f"/models/{self.pretrained_model}/{self.pretrained_model}"

        if not os.path.isdir(self.model_dir):
            print(f"Error: Model directory does not exist: {self.model_dir}")
            sys.exit(1)
            
    def initialize_output(self):
        """Initialize output directory and CSV file"""
        os.makedirs(self.output_folder, exist_ok=True)
        self.csv_file = os.path.join(self.output_folder, "combined_results.csv")
        
        with open(self.csv_file, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(["Filename", "Time", "Gene", "GreenCellCount", "RedCellCount"])
            
    def find_image_pairs(self):
        """Find image pairs"""
        # recursively find EGFP images
        pattern = os.path.join(self.input_folder, "**", "*EGFP-*.tif")
        green_paths = glob.glob(pattern, recursive=True)
        
        image_pairs = []
        
        for green_path in green_paths:
            if not os.path.isfile(green_path):
                continue
                
            green_file = os.path.basename(green_path)
            
            # extract base_prefix and suffix_num from xxx_EGFP-123.tif
            match = re.match(r'(.+?)_EGFP-(\d+)\.tif$', green_file)
            if not match:
                continue
                
            base_prefix = match.group(1)
            suffix_num = match.group(2)
            filename_id = f"{base_prefix}-{suffix_num}"
            
            # find matching red channel image
            red_pattern = f"{base_prefix}_mcherry-{suffix_num}.tif"
            red_paths = glob.glob(os.path.join(self.input_folder, "**", red_pattern), recursive=True)
            
            if not red_paths:
                print(f"Warning: Red channel image not found for {green_file}")
                continue
                
            red_path = red_paths[0]  # take the first match
            
            image_pairs.append({
                'green_path': green_path,
                'red_path': red_path,
                'green_file': green_file,
                'red_file': os.path.basename(red_path),
                'base_prefix': base_prefix,
                'suffix_num': suffix_num,
                'filename_id': filename_id
            })
            
        return image_pairs
    
    def build_cellpose_command(self, output_subdir):
        """Build Cellpose command (aligned with 1.cellpose.sh; provide visible paths for container on Windows)"""
        if self.mode == 'apptainer':
            # 绑定模型目录到 /models，输入到 /input，当前输出子目录到 /output
            cmd = [
                "apptainer", "exec",
                "--bind", f"{self.model_dir}:/models",
                "--bind", f"{self.input_folder}:/input",
                "--bind", f"{output_subdir}:/output",
            ]
            if self.use_gpu:
                cmd.append("--nv")
            cmd.extend([
                self.apptainer_path,
                "python", "-m", "cellpose",
                "--pretrained_model", self.pretrained_model_path_container
            ])
            if self.use_gpu:
                cmd.append("--use_gpu")
            # 保存到容器内 /output
            cmd.extend(["--savedir", "/output"])
        else:  # python 直接模式
            cmd = [
                sys.executable, "-m", "cellpose",
                "--pretrained_model", self.pretrained_model_path_host
            ]
            if self.use_gpu:
                cmd.append("--use_gpu")
            # 直接保存到宿主输出目录
            cmd.extend(["--savedir", output_subdir])

        cmd.extend([
            "--save_outlines",
            "--save_txt",
            "--verbose"
        ])

        return cmd
    
    def process_channel(self, image_path, channel, cmd_base, output_subdir):
        """Process a single channel"""
        cmd = cmd_base.copy()
        # 在 apptainer 模式下，使用容器内的输入路径 /input/...
        if self.mode == 'apptainer':
            rel = os.path.relpath(image_path, self.input_folder)
            rel_posix = rel.replace('\\', '/')
            image_path_arg = f"/input/{rel_posix}"
        else:
            image_path_arg = image_path
        cmd.extend([
            "--image_path", image_path_arg,
            "--chan", str(channel),
            "--chan2", str(channel)
        ])
        
        if self.use_gpu:
            channel_name = "Green" if channel == 2 else "Red"
            print(f"  Using GPU to process {channel_name} channel: {os.path.basename(image_path)}")
        
        try:
            print(f"Executing command: {' '.join(cmd)}")
            print("Starting cellpose processing, please wait...")

            # 实时输出进度
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                universal_newlines=True,
                encoding='utf-8',
                errors='ignore'
            )

            # 实时读取输出
            while True:
                output = process.stdout.readline()
                if output == '' and process.poll() is not None:
                    break
                if output:
                    print(f"[Cellpose] {output.strip()}")

            return_code = process.poll()
            if return_code == 0:
                print(f"[SUCCESS] Completed: {os.path.basename(image_path)}")
            else:
                print(f"[ERROR] Failed: {os.path.basename(image_path)}")
                return 0

        except Exception as e:
            print(f"[ERROR] Exception: {os.path.basename(image_path)} - {e}")
            return 0
            
        # 计算细胞数量
        base_name = os.path.splitext(os.path.basename(image_path))[0]
        txt_file = os.path.join(output_subdir, f"{base_name}_cp_outlines.txt")
        
        if os.path.isfile(txt_file):
            try:
                with open(txt_file, 'r') as f:
                    count = sum(1 for line in f)
                return count
            except Exception as e:
                print(f"Warning: failed to read file {txt_file}: {e}")
                return 0
        else:
            return 0
    
    def process_image_pair(self, pair):
        """Process an image pair"""
        print(f"Processing image pair: {pair['green_file']} and {pair['red_file']}")

        # 计算输出子目录
        relative_path = os.path.relpath(pair['green_path'], self.input_folder)
        output_subdir = os.path.join(self.output_folder, os.path.dirname(relative_path))
        os.makedirs(output_subdir, exist_ok=True)

        # 构造基础命令（在 apptainer 模式下绑定输入输出目录，避免容器内路径不可见）
        cmd_base = self.build_cellpose_command(output_subdir)
        if self.mode == 'apptainer':
            # 追加挂载输入与输出目录，方便容器内直接访问
            # 注：此处通过 --bind 已绑定模型目录，输入输出路径在命令里用宿主绝对路径
            pass
        
        # 处理红色通道 (chan 1)
        red_count = self.process_channel(pair['red_path'], 1, cmd_base, output_subdir)
        
        # 处理绿色通道 (chan 2)  
        green_count = self.process_channel(pair['green_path'], 2, cmd_base, output_subdir)
        
        # 写入CSV
        time_field = pair['base_prefix'].split('_')[0]
        gene_field = '_'.join(pair['base_prefix'].split('_')[1:])
        
        with open(self.csv_file, 'a', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow([pair['filename_id'], time_field, gene_field, green_count, red_count])
            
        return green_count, red_count
    
    def run(self):
        """Main run function"""
        self.parse_arguments()
        self.validate_arguments()
        self.setup_model_path()
        self.initialize_output()
        
        image_pairs = self.find_image_pairs()
        
        if not image_pairs:
            print("No image pairs found to process")
            return
            
        total_pairs = len(image_pairs)
        print(f"PROGRESS_INIT: Found {total_pairs} image pairs to process")
        
        for i, pair in enumerate(image_pairs, 1):
            try:
                print(f"PROGRESS_UPDATE: Processing pair {i}/{total_pairs}: {pair['filename_id']}")
                green_count, red_count = self.process_image_pair(pair)
                print(f"PROGRESS_COMPLETE: {pair['filename_id']} - Green cells: {green_count}, Red cells: {red_count}")
                print(f"PROGRESS_PERCENT: {int((i / total_pairs) * 100)}")
            except Exception as e:
                print(f"PROGRESS_ERROR: Failed to process {pair['filename_id']}: {e}")
                continue
                
        print(f"PROGRESS_FINISHED: All images processed. Results saved to {self.csv_file}")


def main():
    processor = CellposeProcessor()
    processor.run()


if __name__ == "__main__":
    main()
