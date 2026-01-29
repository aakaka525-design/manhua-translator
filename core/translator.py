"""
Region Merging Utilities - Preprocessing for translation.

Provides functions to merge adjacent OCR regions for better translation context.
"""

from typing import List
from uuid import uuid4

from .models import RegionData, Box2D


def merge_adjacent_regions(
    regions: List[RegionData],
    y_gap_ratio: float = 1.5,
    x_overlap_ratio: float = 0.3,
) -> List[RegionData]:
    """
    合并垂直相邻的区域为段落（属于同一对话气泡）。
    
    用于翻译前预处理，将 OCR 的碎片化结果合并为完整段落，
    以便翻译器获得更好的上下文理解。
    
    Args:
        regions: OCR 输出的区域列表
        y_gap_ratio: 垂直间距阈值（相对于平均高度）
        x_overlap_ratio: 水平重叠阈值
        
    Returns:
        合并后的区域列表
    """
    if len(regions) <= 1:
        return regions
    
    # 按 Y 坐标排序
    valid_regions = [r for r in regions if r.box_2d and r.source_text]
    if not valid_regions:
        return regions
    
    sorted_regions = sorted(valid_regions, key=lambda r: (r.box_2d.y1, r.box_2d.x1))
    
    # 聚类：相邻区域合并
    clusters = []
    current_cluster = [sorted_regions[0]]
    
    for region in sorted_regions[1:]:
        # 检查是否应该与当前 cluster 合并
        should_merge = False
        
        for member in current_cluster:
            if _should_merge_vertical(member, region, y_gap_ratio, x_overlap_ratio):
                should_merge = True
                break
        
        if should_merge:
            current_cluster.append(region)
        else:
            clusters.append(current_cluster)
            current_cluster = [region]
    
    if current_cluster:
        clusters.append(current_cluster)
    
    # 合并每个 cluster
    merged = []
    for cluster in clusters:
        if len(cluster) == 1:
            merged.append(cluster[0])
        else:
            # 先按行分组（center_y 接近的为同一行）
            lines = []
            for region in cluster:
                center_y = (region.box_2d.y1 + region.box_2d.y2) / 2
                matched_line = None
                for line in lines:
                    line_center_y = sum((r.box_2d.y1 + r.box_2d.y2) / 2 for r in line) / len(line)
                    avg_height = sum(r.box_2d.height for r in line) / len(line)
                    if abs(center_y - line_center_y) < avg_height * 0.7:
                        matched_line = line
                        break
                if matched_line:
                    matched_line.append(region)
                else:
                    lines.append([region])
            
            # 按行的平均 Y 排序
            lines.sort(key=lambda line: sum((r.box_2d.y1 + r.box_2d.y2) / 2 for r in line) / len(line))
            
            # 每行内按 X 排序，然后拼接
            all_texts = []
            for line in lines:
                sorted_line = sorted(line, key=lambda r: r.box_2d.x1)
                line_text = " ".join(r.source_text for r in sorted_line if r.source_text)
                all_texts.append(line_text)
            
            combined_text = " ".join(all_texts)
            
            # 合并 box
            x1 = min(r.box_2d.x1 for r in cluster)
            y1 = min(r.box_2d.y1 for r in cluster)
            x2 = max(r.box_2d.x2 for r in cluster)
            y2 = max(r.box_2d.y2 for r in cluster)
            
            # 平均置信度
            avg_conf = sum(r.confidence for r in cluster) / len(cluster)
            
            merged_region = RegionData(
                region_id=uuid4(),
                box_2d=Box2D(x1=x1, y1=y1, x2=x2, y2=y2),
                source_text=combined_text,
                confidence=avg_conf
            )
            merged.append(merged_region)
    
    return merged


def _should_merge_vertical(
    r1: RegionData, 
    r2: RegionData, 
    y_gap_ratio: float,
    x_overlap_ratio: float,
) -> bool:
    """判断两个区域是否垂直相邻（应合并为段落）。"""
    b1, b2 = r1.box_2d, r2.box_2d
    
    # 计算垂直间距
    y_gap = b2.y1 - b1.y2
    avg_height = (b1.height + b2.height) / 2
    
    # 垂直间距太大，不合并
    if y_gap > avg_height * y_gap_ratio:
        return False
    
    # 计算水平重叠
    x_left = max(b1.x1, b2.x1)
    x_right = min(b1.x2, b2.x2)
    overlap = max(0, x_right - x_left)
    
    min_width = min(b1.width, b2.width)
    if min_width > 0 and overlap / min_width >= x_overlap_ratio:
        return True
    
    # 中心点 X 接近也可以合并
    center_x1 = (b1.x1 + b1.x2) / 2
    center_x2 = (b2.x1 + b2.x2) / 2
    if abs(center_x1 - center_x2) <= avg_height * 2:
        return True
    
    return False


def group_adjacent_regions(
    regions: List[RegionData],
    y_gap_ratio: float = 0.8,   # 收紧：垂直间距阈值（更严格）
    x_overlap_ratio: float = 0.5,  # 收紧：水平重叠阈值（更严格）
) -> List[List[RegionData]]:
    """
    将相邻区域分组（不合并 box），返回分组列表。
    
    每个分组是一个原始区域列表，属于同一对话气泡。
    """
    if len(regions) <= 1:
        return [[r] for r in regions]
    
    valid_regions = [r for r in regions if r.box_2d and r.source_text]
    if not valid_regions:
        return [[r] for r in regions]
    
    sorted_regions = sorted(valid_regions, key=lambda r: (r.box_2d.y1, r.box_2d.x1))
    
    groups = []
    current_group = [sorted_regions[0]]
    
    for region in sorted_regions[1:]:
        should_merge = False
        for member in current_group:
            if _should_merge_vertical(member, region, y_gap_ratio, x_overlap_ratio):
                should_merge = True
                break
        
        if should_merge:
            current_group.append(region)
        else:
            groups.append(current_group)
            current_group = [region]
    
    if current_group:
        groups.append(current_group)
    
    return groups


def split_translation_by_ratio(
    group: List[RegionData],
    translation: str,
) -> List[str]:
    """
    按原始文本字符比例分割翻译结果到各个区域。
    
    Args:
        group: 属于同一对话的原始区域列表
        translation: 整体翻译结果
        
    Returns:
        分割后的翻译列表，与 group 一一对应
    """
    if len(group) == 1:
        return [translation]
    
    if not translation:
        return [""] * len(group)
    
    # 计算每个区域原文的字符比例
    char_counts = [len(r.source_text.strip()) if r.source_text else 0 for r in group]
    total_chars = sum(char_counts)
    
    if total_chars == 0:
        # 平均分配
        avg_len = len(translation) // len(group)
        return [translation[i*avg_len:(i+1)*avg_len] for i in range(len(group))]
    
    # 按比例分割翻译
    trans_len = len(translation)
    splits = []
    start = 0
    
    for i, char_count in enumerate(char_counts):
        if i == len(char_counts) - 1:
            # 最后一个区域取剩余全部
            splits.append(translation[start:])
        else:
            ratio = char_count / total_chars
            end = start + int(trans_len * ratio)
            
            # 尝试在标点或空格处分割，避免截断词语
            best_end = end
            for offset in range(min(10, end - start)):
                check_pos = end - offset
                if check_pos > start and check_pos < trans_len:
                    if translation[check_pos] in '，。！？、；：,.:;!? ':
                        best_end = check_pos + 1
                        break
            
            splits.append(translation[start:best_end])
            start = best_end
    
    return splits
