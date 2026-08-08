"""FastAPI app: room REST endpoints + realtime WebSocket gameplay.

Game-agnostic: every room is bound to a game slug looked up in
boardy.core.registry (populated by importing boardy.games). This module
has no knowledge of any specific game's rules.

Run with:
    python -m boardy.web.server
or:
    uvicorn boardy.web.server:app --reload
"""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from .. import games  # noqa: F401  (import side effect: registers built-in games)
from ..core import registry as game_registry
from .rooms import registry

app = FastAPI(title="Boardy Online")

STATIC_DIR = Path(__file__).resolve().parent / "static"


class CreateRoomRequest(BaseModel):
    game: str = "deep_sea_crew"
    num_players: int = 3
    difficulty: int = 8


@app.get("/api/games")
def list_games() -> dict:
    return {
        "games": [
            {
                "slug": spec.slug,
                "name": spec.name,
                "description": spec.description,
                "min_players": spec.min_players,
                "max_players": spec.max_players,
            }
            for spec in game_registry.all_specs()
        ]
    }


@app.post("/api/rooms")
def create_room(req: CreateRoomRequest) -> dict:
    spec = game_registry.get(req.game)
    if spec is None:
        return {"error": f"Unknown game: {req.game}"}
    if not (spec.min_players <= req.num_players <= spec.max_players):
        return {
            "error": f"{spec.name} supports {spec.min_players}-{spec.max_players} players"
        }
    room = registry.create(spec, req.num_players, req.difficulty)
    return {"code": room.code, "game": spec.slug}


@app.websocket("/ws/{code}")
async def ws_room(ws: WebSocket, code: str, name: str = "player") -> None:
    room = registry.get(code)
    if room is None:
        await ws.close(code=4404)
        return

    await ws.accept()
    seat = room.add_human(name, ws)
    if seat is None:
        await ws.send_json({"type": "error", "message": "Room is full"})
        await ws.close(code=4403)
        return

    if room.started:
        assert room.state is not None
        view = room.spec.serialize_seat(room.state, seat, room.players_meta())
        await ws.send_json({"type": "state", "seat": seat, "game": room.spec.slug, **view})
    else:
        await ws.send_json({"type": "joined", "seat": seat})
        await room.broadcast_lobby()

    try:
        while True:
            msg = await ws.receive_json()
            mtype = msg.get("type")

            if mtype == "add_ai" and not room.started:
                room.add_ai(mode=msg.get("mode", "random"))
                await room.broadcast_lobby()
            elif mtype == "start" and not room.started:
                try:
                    room.start()
                except ValueError as e:
                    await ws.send_json({"type": "error", "message": str(e)})
                    continue
                await room.broadcast()
                await room.run_ai_turns()
            elif mtype == "play" and room.started:
                await room.play_human_card(seat, msg.get("action", ""))
            elif mtype == "communicate" and room.started:
                await room.communicate(seat, msg.get("action", ""))
    except WebSocketDisconnect:
        room.remove_seat(seat)
        if not room.started:
            await room.broadcast_lobby()


if STATIC_DIR.exists():
    app.mount("/", StaticFiles(directory=str(STATIC_DIR), html=True), name="static")


def run() -> None:
    import uvicorn

    uvicorn.run("boardy.web.server:app", host="127.0.0.1", port=8000, reload=False)


if __name__ == "__main__":
    run()
