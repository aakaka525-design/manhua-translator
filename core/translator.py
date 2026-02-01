"""
Region Merging Utilities - Preprocessing for translation.

Provides functions to merge adjacent OCR regions for better translation context.
"""

import logging
import os
from typing import List
from uuid import UUID, uuid4

from .models import RegionData, Box2D

logger = logging.getLogger(__name__)


def _snippet(text: str, max_len: int = 80) -> str:
    if not text:
        return ""
    text = text.strip()
    return text if len(text) <= max_len else f"{text[: max_len - 3]}..."


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
    height_ratio: float | None = None,
) -> bool:
    """判断两个区域是否垂直相邻（应合并为段落）。"""
    b1, b2 = r1.box_2d, r2.box_2d

    # 避免将拟声词与对白合并
    if r1.is_sfx != r2.is_sfx:
        return False

    bucket1 = _script_bucket(r1.source_text or "")
    bucket2 = _script_bucket(r2.source_text or "")
    if (
        bucket1
        and bucket2
        and bucket1 != bucket2
        and "mixed" not in (bucket1, bucket2)
    ):
        return False

    height_failed = False
    height_ratio_value = 1.0
    if height_ratio is not None:
        max_h = max(b1.height, b2.height, 1)
        min_h = min(b1.height, b2.height)
        height_ratio_value = min_h / max_h
        if height_ratio_value < height_ratio:
            height_failed = True
    
    # 计算垂直间距
    y_gap = b2.y1 - b1.y2
    avg_height = (b1.height + b2.height) / 2
    
    # 计算水平重叠
    x_left = max(b1.x1, b2.x1)
    x_right = min(b1.x2, b2.x2)
    overlap = max(0, x_right - x_left)
    
    min_width = min(b1.width, b2.width)
    overlap_ratio = overlap / max(min_width, 1)
    allow_height_mismatch = (
        height_failed
        and height_ratio_value >= max(0.45, (height_ratio or 0) * 0.75)
        and overlap_ratio >= max(0.85, x_overlap_ratio)
        and y_gap <= avg_height * max(0.85, y_gap_ratio)
    )

    # 垂直间距太大，不合并
    if y_gap > avg_height * y_gap_ratio and not allow_height_mismatch:
        return False

    if height_failed and not allow_height_mismatch:
        return False
    
    if min_width > 0 and overlap_ratio >= x_overlap_ratio:
        return True

    # 同行相邻：Y 重叠高且水平间距小
    y_overlap = min(b1.y2, b2.y2) - max(b1.y1, b2.y1)
    if y_overlap > 0:
        y_overlap_ratio = y_overlap / max(min(b1.height, b2.height), 1)
        gap = max(b2.x1 - b1.x2, b1.x1 - b2.x2, 0)
        min_overlap_required = min(0.6, x_overlap_ratio)
        if y_overlap_ratio >= 0.7 and gap <= avg_height * 0.8 and overlap / max(min_width, 1) >= min_overlap_required:
            return True
        # 同行紧贴：允许小间隙的同一行文本合并（更严格的间隙阈值）
        if y_overlap_ratio >= 0.75 and gap <= avg_height * 0.3:
            return True
    
    # 中心点 X 接近也可以合并
    center_x1 = (b1.x1 + b1.x2) / 2
    center_x2 = (b2.x1 + b2.x2) / 2
    if x_overlap_ratio <= 0.7 and abs(center_x1 - center_x2) <= avg_height * 2:
        return True
    
    return False


def _script_bucket(text: str) -> str | None:
    """粗略判断文本脚本类型，用于避免跨语言泡泡合并。"""
    if not text:
        return None
    counts = {"hangul": 0, "latin": 0, "cjk": 0}
    for ch in text:
        code = ord(ch)
        if 0xAC00 <= code <= 0xD7A3:
            counts["hangul"] += 1
        elif 0x0041 <= code <= 0x005A or 0x0061 <= code <= 0x007A:
            counts["latin"] += 1
        elif 0x4E00 <= code <= 0x9FFF:
            counts["cjk"] += 1
    nonzero = [k for k, v in counts.items() if v > 0]
    if not nonzero:
        return None
    if len(nonzero) > 1:
        return "mixed"
    return nonzero[0]


def group_adjacent_regions(
    regions: List[RegionData],
    y_gap_ratio: float = 0.55,   # 适度放宽：垂直间距阈值
    x_overlap_ratio: float = 0.9,  # 收紧：水平重叠阈值（更严格）
    height_ratio: float = 0.6,  # 收紧：高度相似度（避免大小字合并）
    max_group_size: int | None = 4,  # 限制单组大小，避免过度合并
    bubble_map: dict[UUID, int] | None = None,  # 只合并同气泡的文本
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

    groups: list[list[RegionData]] = []

    for region in sorted_regions:
        merged = False
        # 尝试合并到已有分组（允许跳过中间区域）
        for group in groups:
            if max_group_size is not None and len(group) >= max_group_size:
                continue
            for member in group:
                # SFX 与对话文本不合并，避免跨语义污染
                is_sfx_left = bool(getattr(member, "is_sfx", False))
                is_sfx_right = bool(getattr(region, "is_sfx", False))
                if is_sfx_left != is_sfx_right:
                    continue
                if bubble_map is not None:
                    bubble_id_left = bubble_map.get(member.region_id)
                    bubble_id_right = bubble_map.get(region.region_id)
                    # 两侧都有 bubble_id 时才强制同气泡；缺失 bubble_id 则回退空间规则
                    if bubble_id_left is not None and bubble_id_right is not None:
                        if bubble_id_left != bubble_id_right:
                            continue
                if _should_merge_vertical(member, region, y_gap_ratio, x_overlap_ratio, height_ratio):
                    group.append(region)
                    merged = True
                    break
            if merged:
                break
        if not merged:
            groups.append([region])

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
    
    if os.getenv("DEBUG_TRANSLATOR") == "1":
        logger.info(
            "[split_by_ratio] srcs=%s trans=%s counts=%s splits=%s",
            [_snippet(r.source_text or "") for r in group],
            _snippet(translation),
            char_counts,
            [_snippet(s) for s in splits],
        )
    return splits
