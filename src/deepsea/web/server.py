"""FastAPI app: room REST endpoints + realtime WebSocket gameplay.

Run with:
    python -m deepsea.web.server
or:
    uvicorn deepsea.web.server:app --reload
"""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from .rooms import registry

app = FastAPI(title="Deep Sea Crew Online")

STATIC_DIR = Path(__file__).resolve().parent / "static"


class CreateRoomRequest(BaseModel):
    num_players: int = 3
    difficulty: int = 8


@app.post("/api/rooms")
def create_room(req: CreateRoomRequest) -> dict:
    if not (2 <= req.num_players <= 5):
        return {"error": "num_players must be between 2 and 5"}
    room = registry.create(req.num_players, req.difficulty)
    return {"code": room.code}


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
        from .serialize import serialize_state

        await ws.send_json(serialize_state(room.state, seat, room.players_meta()))
    else:
        await ws.send_json({"type": "joined", "seat": seat})
        await room.broadcast_lobby()

    try:
        while True:
            msg = await ws.receive_json()
            mtype = msg.get("type")

            if mtype == "add_ai" and not room.started:
                room.add_ai()
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
                await room.play_human_card(seat, msg.get("card", ""))
            elif mtype == "communicate" and room.started:
                await room.communicate(seat, msg.get("card", ""))
    except WebSocketDisconnect:
        room.remove_seat(seat)
        if not room.started:
            await room.broadcast_lobby()


if STATIC_DIR.exists():
    app.mount("/", StaticFiles(directory=str(STATIC_DIR), html=True), name="static")


def run() -> None:
    import uvicorn

    uvicorn.run("deepsea.web.server:app", host="127.0.0.1", port=8000, reload=False)


if __name__ == "__main__":
    run()
