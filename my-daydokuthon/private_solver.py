"""Private-judge entry point: solve_challenge(payload) -> trace dict.

Backtracking exact cover that always fills the lowest-ordered empty cell.
Piece shapes are normalised so their minimum cell is (0, 0), so the origin of
a piece covering that cell is the cell itself.
"""

import re

from daydokuthon import Challenge, Simulation
from daydokuthon.core import iso_date

_DATE = re.compile(r"\d{4}-\d{2}-\d{2}")


def _search(simulation: Simulation) -> list | None:
    free = set(simulation.board.coordinates - simulation.exposed)
    shapes = {
        piece.id: [
            (o.rotation, o.flipped, tuple(sorted(o.cells)))
            for o in simulation.orientations(piece.id)
        ]
        for piece in simulation.pieces
    }
    sizes = {piece.id: len(piece.cells) for piece in simulation.pieces}
    remaining = list(sizes)
    chosen = []
    sums_cache = {}

    def sums() -> frozenset:
        key = frozenset(remaining)
        if key not in sums_cache:
            reach = {0}
            for piece_id in key:
                reach |= {r + sizes[piece_id] for r in reach}
            sums_cache[key] = frozenset(reach)
        return sums_cache[key]

    def regions_ok() -> bool:
        """Every enclosed empty region must be exactly fillable by remaining pieces."""
        reach = sums()
        seen = set()
        for start in free:
            if start in seen:
                continue
            seen.add(start)
            stack = [start]
            size = 0
            while stack:
                cell = stack.pop()
                size += 1
                for n in cell.neighbors():
                    if n in free and n not in seen:
                        seen.add(n)
                        stack.append(n)
            if size not in reach:
                return False
        return True

    def search() -> bool:
        if not free:
            return not remaining
        target = min(free)
        for piece_id in list(remaining):
            for rotation, flipped, cells in shapes[piece_id]:
                placed = [target + c for c in cells]
                if not all(c in free for c in placed):
                    continue
                free.difference_update(placed)
                remaining.remove(piece_id)
                chosen.append((piece_id, target, rotation, flipped))
                if regions_ok() and search():
                    return True
                chosen.pop()
                remaining.append(piece_id)
                free.update(placed)
        return False

    return chosen if search() else None


def solve_challenge(payload):
    try:
        raw_date = payload["date"]
        if not isinstance(raw_date, str) or not _DATE.fullmatch(raw_date):
            raise ValueError("Date must be YYYY-MM-DD")
        challenge = Challenge(
            str(payload.get("id", "challenge")) or "challenge",
            iso_date(raw_date),
            payload.get("title", "Honeycomb challenge"),
            payload.get("puzzle_version", "honeycomb-1"),
        )
    except Exception:
        return {"error": "invalid_date"}

    simulation = Simulation(challenge)
    solution = _search(simulation)
    if solution is not None:
        for piece_id, origin, rotation, flipped in solution:
            simulation.place(piece_id, origin, rotation, flipped)
    return simulation.to_trace()


if __name__ == "__main__":
    import json
    import sys

    print(json.dumps(solve_challenge(json.load(open(sys.argv[1], encoding="utf-8"))), indent=2))
