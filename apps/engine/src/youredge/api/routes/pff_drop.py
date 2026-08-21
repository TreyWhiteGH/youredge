"""Receiver for the PFF harvest: the browser page POSTs each facet's JSON here.

Dev-only surface: CORS-opened to premium.pff.com so in-page fetch loops can
deliver rows; writes land in data/pff/ for the pff ingest. Names are strictly
validated — this endpoint writes files, so nothing but the expected pattern
is accepted.
"""

import json
import re
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter(tags=["pff-drop"])

PFF_DIR = Path("/app/data/pff")
NAME = re.compile(r"^[a-z_]+_\d{4}(_wk\d+)?\.json$")


class Drop(BaseModel):
    name: str
    rows: list[dict]


@router.post("/pff-drop")
async def pff_drop(drop: Drop):
    if not NAME.match(drop.name):
        raise HTTPException(status_code=400, detail="bad name")
    PFF_DIR.mkdir(parents=True, exist_ok=True)
    (PFF_DIR / drop.name).write_text(json.dumps(drop.rows))
    return {"saved": drop.name, "rows": len(drop.rows)}


@router.get("/pff-drop/list")
async def pff_list():
    if not PFF_DIR.exists():
        return {"files": []}
    return {"files": sorted(p.name for p in PFF_DIR.glob("*.json"))}
