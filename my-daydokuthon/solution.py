from daydokuthon import HexCoordinate, PuzzleAlgorithm, Simulation


class MyAlgorithm(PuzzleAlgorithm):
    def solve(self, simulation: Simulation) -> None:
        # Implement your search/greedy/backtracking strategy here.
        # A failed can_place check has no effect and is not recorded.
        # Place a whole piece, remove it to backtrack, and leave a solved board.
        # See examples/first_piece.py for a deliberately incomplete demonstration.
        for piece in simulation.pieces:
            for orientation in simulation.orientations(piece.id):
                for origin in sorted(simulation.board.coordinates):
                    if simulation.can_place(piece.id, origin,
                                            orientation.rotation, orientation.flipped):
                        simulation.place(piece.id, origin,
                                         orientation.rotation, orientation.flipped)
                        return  # Demonstration only: one piece is NOT a full solution.
