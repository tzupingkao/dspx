from __future__ import annotations
from typing import List, Dict, Any, Tuple
from blessed import Terminal
from wcwidth import wcswidth
import time


# 欄位定義：name=欄位鍵, title=表頭, minw=最小寬度, maxw=偏好寬度, prio=優先度（數字越小越重要）
COLUMNS = [
    {"name": "name",    "title": "NAME",    "minw": 12, "maxw": 28, "prio": 0},
    {"name": "image",   "title": "IMAGE",   "minw": 14, "maxw": 32, "prio": 1},
    {"name": "status",  "title": "STATUS",  "minw": 10, "maxw": 14, "prio": 0},
    {"name": "health",  "title": "HEALTH",  "minw": 8,  "maxw": 10, "prio": 2},
    {"name": "created", "title": "CREATED", "minw": 8,  "maxw": 12, "prio": 1},
    {"name": "ports",   "title": "PORTS",   "minw": 12, "maxw": 30, "prio": 3},
    {"name": "networks","title": "NETWORKS","minw": 8,  "maxw": 16, "prio": 3},
    {"name": "mounts",  "title": "MOUNTS",  "minw": 12, "maxw": 30, "prio": 4},
    {"name": "command", "title": "COMMAND", "minw": 12, "maxw": 40, "prio": 4},
]

DENSITY = {
    1: 0.8,  # 精簡：欄位偏向使用 minw
    2: 1.0,  # 一般：介於 minw 與 maxw
    3: 1.2,  # 寬鬆：偏向 maxw（仍受總寬度限制）
}


def display_width(s: str) -> int:
    return max(0, wcswidth(s))


def ellipsize_middle(s: str, width: int) -> str:
    if width <= 0:
        return ""
    if display_width(s) <= width:
        return s
    if width <= 1:
        return s[:width]
    # 中間省略：保留頭尾
    head = max(1, width // 2 - 1)
    tail = max(1, width - head - 1)
    return s[:head] + "…" + s[-tail:]


def fit_columns(term_width: int, density: int) -> List[Dict[str, Any]]:
    """根據終端寬度與密度，計算要顯示哪些欄位與寬度。若不夠寬，依 prio 隱藏。"""
    cols = sorted(COLUMNS, key=lambda c: c["prio"])  # 先排重要度
    factor = DENSITY.get(density, 1.0)

    # 先給每欄一個想要的寬度
    planned = []
    for c in cols:
        w = int(c["minw"] + (c["maxw"] - c["minw"]) * (factor - 0.8) / (1.2 - 0.8))
        w = max(c["minw"], min(c["maxw"], w))
        planned.append({**c, "width": w})

    # 計算總寬（加上欄間空白 1）
    def total_w(lst: List[Dict[str, Any]]) -> int:
        if not lst:
            return 0
        return sum(x["width"] for x in lst) + (len(lst) - 1)

    visible = planned[:]
    while total_w(visible) > term_width and len(visible) > 1:
        # 由最低優先度（數字大）開始移除
        worst_prio = max(v["prio"] for v in visible)
        # 同 prio 中優先移除最寬那個
        worst_idx = None
        worst_w = -1
        for i, v in enumerate(visible):
            if v["prio"] == worst_prio and v["width"] >= v["minw"] and v["width"] > worst_w:
                worst_idx = i
                worst_w = v["width"]
        if worst_idx is not None:
            visible.pop(worst_idx)
        else:
            break

    # 若還是太寬，對剩餘欄位縮到 minw
    while total_w(visible) > term_width:
        changed = False
        for v in reversed(visible):  # 從低優先度開始縮
            if v["width"] > v["minw"]:
                v["width"] -= 1
                changed = True
                if total_w(visible) <= term_width:
                    break
        if not changed:
            break

    return visible


def format_row(row: Dict[str, Any], visible_cols: List[Dict[str, Any]]) -> str:
    parts: List[str] = []
    for c in visible_cols:
        key = c["name"]
        w = c["width"]
        val = str(row.get(key, ""))
        parts.append(ellipsize_middle(val, w).ljust(w))
    return " ".join(parts)


def draw_table(term: Terminal, rows: List[Dict[str, Any]], selected: int, expanded: set[int],
               visible_cols: List[Dict[str, Any]], filter_text: str, density: int) -> None:
    print(term.home + term.clear)

    # 標頭
    title = f"dpsx — Docker TUI  |  n={len(rows)}  |  filter=/{filter_text or '-'}  |  density={density}  |  q=quit"
    print(term.bold(title[:term.width]))

    # 欄位列
    header = " ".join(ellipsize_middle(c["title"], c["width"]).ljust(c["width"]) for c in visible_cols)
    print(term.reverse(header))

    # 可顯示高度（扣掉標頭 2 行 + footer 1 行）
    max_lines = max(0, term.height - 3)

    # 捲動視窗起點
    start = 0
    # 讓選取列盡量可見
    if selected >= max_lines:
        start = selected - max_lines + 1

    y = 0
    idx = 0
    for i, row in enumerate(rows):
        if i < start:
            continue
        if y >= max_lines:
            break

        line = format_row(row, visible_cols)
        if i == selected:
            print(term.on_darkolivegreen3(term.black(line)))
        else:
            print(line)
        y += 1

        if i in expanded and y < max_lines:
            # 詳細列（多行），以 ↳ 開頭
            detail_lines = build_detail_lines(row, term.width)
            for dl in detail_lines:
                if y >= max_lines:
                    break
                print(term.dim("↳ " + dl[: max(0, term.width - 2)]))
                y += 1
        idx += 1

    # footer
    help_bar = "↑/↓/j/k 移動  Enter/Space 展開  / 篩選  c 清除  r 重新整理  1/2/3 密度  q 離開"
    print(term.move(term.height - 1, 0) + term.reverse(help_bar[:term.width]))


def build_detail_lines(row: Dict[str, Any], maxw: int) -> List[str]:
    kv = []
    def add(label: str, value: str):
        if not value:
            return
        kv.append(f"{label}: {value}")

    add("ID", row.get("id", ""))
    add("Command", row.get("command", ""))
    add("Labels", ", ".join(f"{k}={v}" for k, v in (row.get("labels") or {}).items()))
    add("Ports", row.get("ports", ""))
    add("Networks", row.get("networks", ""))
    add("Mounts", row.get("mounts", ""))

    # 依寬度斷行
    lines: List[str] = []
    for s in kv:
        while s:
            if display_width(s) <= maxw - 2:
                lines.append(s)
                break
            # 簡單斷行：找最近空白
            cut = maxw - 2
            pos = s.rfind(" ", 0, cut)
            if pos <= 0:
                pos = cut
            lines.append(s[:pos])
            s = s[pos:].lstrip()
    return lines
