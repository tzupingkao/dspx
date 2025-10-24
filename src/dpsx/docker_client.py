from __future__ import annotations
from datetime import datetime, timezone
from typing import Any, Dict, List
import docker
import humanize



def _safe_str(x: Any) -> str:
    if x is None:
        return ""
    return str(x)




def list_containers(all_containers: bool = True) -> List[Dict[str, Any]]:
    """以 Docker SDK 取得容器清單，並整理常用欄位與詳細資訊。"""
    client = docker.from_env()
    containers = client.containers.list(all=all_containers)


    result: List[Dict[str, Any]] = []
    now = datetime.now(timezone.utc)


    for c in containers:
        attrs = c.attrs # type: ignore[attr-defined]
        name = c.name or (attrs.get("Name", "").lstrip("/"))
        image = getattr(c.image, "tags", None) or []
        image_str = image[0] if image else attrs.get("Config", {}).get("Image", c.image.short_id)
        created = attrs.get("Created")
        created_dt: datetime | None = None
        if created:
            try:
                created_dt = datetime.fromisoformat(created.replace("Z", "+00:00"))
            except Exception:
                created_dt = None
        created_ago = humanize.naturaltime(now - created_dt) if created_dt else "?" # type: ignore[arg-type]


        state = attrs.get("State", {})
        status = state.get("Status", "unknown")
        running = state.get("Running", False)
        health = (state.get("Health", {}) or {}).get("Status")


        ports_map = attrs.get("NetworkSettings", {}).get("Ports", {}) or {}
        ports_list: List[str] = []
        for k, v in ports_map.items():
            if not v:
                continue
            for m in v:
                hp = f"{m.get('HostIp','')}:{m.get('HostPort','')}->{k}"
                ports_list.append(hp)
        ports_str = ", ".join(ports_list)


        cmd = " ".join(attrs.get("Config", {}).get("Cmd", []) or [])
        labels = attrs.get("Config", {}).get("Labels", {}) or {}


        networks_info = attrs.get("NetworkSettings", {}).get("Networks", {}) or {}
        networks = ", ".join(sorted(networks_info.keys()))


        mounts_info = attrs.get("Mounts", []) or []
        mounts = ", ".join(
            f"{m.get('Type')}:{m.get('Source','')}->{m.get('Destination','')}" for m in mounts_info
        )


        item = {
            "id": c.short_id,
            "name": name,
            "image": image_str,
            "status": status,
            "running": running,
            "health": health or "",
            "created": created_ago,
            "ports": ports_str,
            "command": cmd,
            "labels": labels,
            "networks": networks,
            "mounts": mounts,
        }
        result.append(item)
    return result