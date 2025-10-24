from __future__ import annotations
from typing import List, Dict, Any, Set
from blessed import Terminal
import time
from .docker_client import list_containers
from .ui import draw_table, fit_columns


def _apply_filter(rows: List[Dict[str, Any]], q: str) -> List[Dict[str, Any]]:
    if not q:
        return rows
    q = q.lower()
    keys = ["name", "image", "status", "health", "ports", "networks", "mounts", "command"]
    out = []
    for r in rows:
        hay = "\n".join(str(r.get(k, "")) for k in keys).lower()
        if q in hay:
            out.append(r)
    return out


def main() -> None:
    term = Terminal()
    with term.fullscreen(), term.cbreak(), term.hidden_cursor():
        density = 2
        selected = 0
        expanded: Set[int] = set()
        query = ""

        rows = list_containers(all_containers=True)
        filtered = _apply_filter(rows, query)
        visible_cols = fit_columns(term.width, density)
        draw_table(term, filtered, selected, expanded, visible_cols, query, density)

        while True:
            k = term.inkey(timeout=1)
            resized = False
            if k.name == "KEY_RESIZE":
                resized = True

            if k:
                if k.lower() == "q":
                    break
                elif k.name in ("KEY_DOWN",) or k == "j":
                    if filtered:
                        selected = min(len(filtered) - 1, selected + 1)
                elif k.name in ("KEY_UP",) or k == "k":
                    if filtered:
                        selected = max(0, selected - 1)
                elif k.name in ("KEY_ENTER",) or k == "\n" or k == " ":
                    if filtered:
                        if selected in expanded:
                            expanded.remove(selected)
                        else:
                            expanded.add(selected)
                elif k == "/":
                    # 進入簡易輸入模式
                    query = _prompt(term, prefix="/")
                    selected = 0
                    expanded.clear()
                elif k.lower() == "c":
                    query = ""
                    selected = 0
                    expanded.clear()
                elif k.lower() == "r":
                    rows = list_containers(all_containers=True)
                elif k == "1":
                    density = 1
                elif k == "2":
                    density = 2
                elif k == "3":
                    density = 3

            filtered = _apply_filter(rows, query)
            if selected >= len(filtered):
                selected = max(0, len(filtered) - 1)

            if resized:
                pass
            visible_cols = fit_columns(term.width, density)
            draw_table(term, filtered, selected, expanded, visible_cols, query, density)


def _prompt(term: Terminal, prefix: str = "") -> str:
    buf = ""
    print(term.move(term.height - 1, 0) + term.clear_eol + term.reverse(prefix), end="", flush=True)
    while True:
        k = term.inkey()
        if not k:
            continue
        if k.name in ("KEY_ENTER",) or k == "\n":
            return buf
        elif k.name in ("KEY_BACKSPACE", "KEY_DELETE") or k == "\x7f":
            buf = buf[:-1]
        elif k.is_sequence and k.name.startswith("KEY_"):
            continue
        else:
            buf += str(k)
        # 更新顯示
        print(term.move(term.height - 1, 0) + term.clear_eol + term.reverse(prefix + buf), end="", flush=True)
