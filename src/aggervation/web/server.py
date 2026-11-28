"""The Aggravation website: create/join games by code and play live over WebSockets.

Run locally:
    uv run aggervation-web            (then open http://localhost:8000)
"""

from __future__ import annotations

import asyncio
import contextlib
import hashlib
import os
from pathlib import Path

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from ..layout_data import PLAYERS, TRACK, VIEWBOX
from .rooms import RoomError, RoomManager, clean_name

STATIC = Path(__file__).parent / "static"
TICK = 0.25  # how often to check for computer turns


class Connections:
    """Open sockets per room, keyed by player token (one per player; a newer tab replaces an older one)."""

    def __init__(self):
        self.by_room: dict[str, dict[str, WebSocket]] = {}

    def add(self, code: str, token: str, ws: WebSocket) -> WebSocket | None:
        room = self.by_room.setdefault(code, {})
        old = room.get(token)
        room[token] = ws
        return old

    def remove(self, code: str, token: str, ws: WebSocket) -> bool:
        """Forget ``ws``. False if a newer socket for the same player has replaced it."""
        room = self.by_room.get(code, {})
        if room.get(token) is not ws:
            return False
        del room[token]
        return True

    def sockets(self, code: str) -> dict[str, WebSocket]:
        return dict(self.by_room.get(code, {}))


manager = RoomManager()
connections = Connections()


async def broadcast(code: str) -> None:
    room = manager.rooms.get(code)
    if not room:
        return
    for token, ws in connections.sockets(code).items():
        with contextlib.suppress(Exception):
            await ws.send_json(room.view(token))


async def computer_turns() -> None:
    """Background loop: let computers (and stand-ins for disconnected players) take their turns."""
    while True:
        await asyncio.sleep(TICK)
        for code, room in list(manager.rooms.items()):
            if room.computer_should_play():
                room.play_computer_turn()
                await broadcast(code)
        manager.cleanup()


@contextlib.asynccontextmanager
async def lifespan(app: FastAPI):
    task = asyncio.create_task(computer_turns())
    yield
    task.cancel()


class Static(StaticFiles):
    """Static files that browsers must re-check each time (cheap: unchanged files get a 304),
    so a new version of the site is picked up straight after it's deployed."""

    def file_response(self, *args, **kwargs):
        response = super().file_response(*args, **kwargs)
        response.headers["Cache-Control"] = "no-cache"
        return response


def _index_html() -> str:
    """index.html with the script and styles tagged by content, so an update can't use stale copies."""
    html = (STATIC / "index.html").read_text(encoding="utf-8")
    for name in ("app.js", "style.css"):
        version = hashlib.sha256((STATIC / name).read_bytes()).hexdigest()[:12]
        html = html.replace(f"/static/{name}", f"/static/{name}?v={version}")
    return html


INDEX_HTML = _index_html()

app = FastAPI(title="Aggravation", lifespan=lifespan)
app.mount("/static", Static(directory=STATIC), name="static")


class CreateRequest(BaseModel):
    token: str
    name: str


@app.get("/")
@app.get("/g/{code}")
async def index(code: str | None = None):
    return HTMLResponse(INDEX_HTML, headers={"Cache-Control": "no-cache"})


@app.get("/api/layout")
async def layout():
    return {"viewbox": VIEWBOX, "track": TRACK, "players": PLAYERS}


@app.post("/api/rooms")
async def create_room(req: CreateRequest):
    if not req.token:
        raise HTTPException(400, "Missing player id")
    room = manager.create(req.token, clean_name(req.name))
    return {"code": room.code}


@app.get("/api/rooms/{code}")
async def room_info(code: str):
    room = manager.get(code)
    if not room:
        raise HTTPException(404, "No game with that code")
    return {"code": room.code, "phase": room.phase}


@app.websocket("/ws/{code}")
async def play(ws: WebSocket, code: str, token: str, name: str = ""):
    await ws.accept()
    room = manager.get(code)
    if not room or not token:
        await ws.send_json({"type": "error", "fatal": True, "message": "No game with that code"})
        await ws.close()
        return
    code = room.code
    old = connections.add(code, token, ws)
    if old:
        with contextlib.suppress(Exception):
            await old.close()
    room.join(token, name)
    await broadcast(code)
    try:
        while True:
            msg = await ws.receive_json()
            try:
                if msg.get("type") == "seven":  # a private answer; nothing changes for anyone else
                    await ws.send_json(
                        room.seven(token, int(msg["card"]), msg["segments"], int(msg["turn_seq"]))
                    )
                    continue
                handle(room, token, msg)
            except RoomError as e:
                await ws.send_json({"type": "error", "message": str(e)})
                continue
            except (KeyError, TypeError, ValueError):
                await ws.send_json({"type": "error", "message": "Bad request"})
                continue
            await broadcast(code)
    except WebSocketDisconnect:
        pass
    finally:
        if connections.remove(code, token, ws):
            room.leave(token)
            await broadcast(code)


def handle(room, token: str, msg: dict) -> None:
    kind = msg.get("type")
    if kind == "sit":
        room.sit(token, msg["seat"])
    elif kind == "stand":
        room.stand(token)
    elif kind == "computer":
        room.set_computer(token, msg["seat"], bool(msg["on"]))
    elif kind == "partners":
        room.set_partners(token, bool(msg["on"]))
    elif kind == "start":
        room.start(token)
    elif kind == "play":
        move = msg.get("move")
        room.play(token, int(msg["card"]), None if move is None else int(move), int(msg["turn_seq"]),
                  seven=msg.get("seven"))
    elif kind == "lobby":
        room.back_to_lobby(token)
    elif kind == "rename":
        room.join(token, msg["name"])
    else:
        raise RoomError("Unknown request")


def main() -> None:
    import uvicorn

    uvicorn.run(
        "aggervation.web.server:app",
        host=os.environ.get("HOST", "0.0.0.0"),
        port=int(os.environ.get("PORT", "8000")),
    )
