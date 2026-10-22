from daydokuthon import HexCoordinate, PuzzleAlgorithm, Simulation


class MyAlgorithm(PuzzleAlgorithm):
    """Backtracking with dead-region pruning.

    Backtracking: always fill the lowest-ordered empty cell. Piece shapes are
    normalised so their minimum cell is (0, 0), so a piece covering that cell is
    anchored exactly there; try each unplaced piece in each orientation, recurse,
    and undo the piece when the branch fails.

    Pruning: after every placement, flood-fill the empty cells. If any enclosed
    region has a size that no combination of the remaining pieces can fill
    exactly, abandon the branch immediately.

    The search runs on plain sets; only the final solution is replayed into the
    simulation, so the trace is exactly 12 place actions.
    """

    def solve(self, simulation: Simulation) -> None:
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
        chosen: list[tuple[str, HexCoordinate, int, bool]] = []
        sums_cache: dict[frozenset, frozenset] = {}

        def fillable_sizes() -> frozenset:
            key = frozenset(remaining)
            if key not in sums_cache:
                reach = {0}
                for piece_id in key:
                    reach |= {r + sizes[piece_id] for r in reach}
                sums_cache[key] = frozenset(reach)
            return sums_cache[key]

        def regions_ok() -> bool:
            reach = fillable_sizes()
            seen: set[HexCoordinate] = set()
            for start in free:
                if start in seen:
                    continue
                seen.add(start)
                stack, size = [start], 0
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

        if not search():
            raise RuntimeError("No solution found for this date")
        for piece_id, origin, rotation, flipped in chosen:
            simulation.place(piece_id, origin, rotation, flipped)
