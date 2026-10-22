# DayDokuSolver

A solver and visual simulator for the **Daydokuthon** honeycomb calendar puzzle.

The board is a hexagonal calendar with 50 cells: 12 months, 31 day numbers and 7 weekdays. For a given date, the cells for that month, day and weekday stay exposed. Twelve pieces (47 cells in total) must cover every other cell, and pieces may be rotated and reflected. Any complete legal arrangement is a valid answer.

Puzzle docs: <https://prem-dharshan.github.io/daydokuthon-docs/>

## Contents

All code lives in [`my-daydokuthon/`](my-daydokuthon).

| File | Purpose |
|---|---|
| `solution.py` | The main solver, `MyAlgorithm`, run by the `daydokuthon` CLI to produce `submission.json`. |
| `private_solver.py` | Standalone `solve_challenge(payload)` for the optional private judging. |
| `challenge.json` | The challenge being solved (ID, date, puzzle version). Replace it with your assigned one. |
| `submission.json` | The generated trace of 12 `place` actions. |
| `simulator/` | Localhost web dashboard that compares seven algorithms. |

## The algorithm: backtracking with pruning

**Backtracking.** The search always fills the lowest-ordered empty cell. Piece shapes are normalised so their minimum cell is `(0, 0)`, which means any piece covering that cell must be anchored exactly on it. The origin is therefore forced, and only the (piece, orientation) pair is searched. If a branch gets stuck, the last piece is removed and the next option is tried.

**Pruning.** After each placement, the empty cells are flood-filled into connected regions. If any region has a size that no combination of the remaining pieces can fill exactly, the branch is abandoned immediately, long before it would fail on its own.

The search runs on plain sets, and only the final solution is replayed into the SDK's `Simulation`. The trace is therefore exactly 12 `place` actions with no removals.

Greedy alone does not work here. It places the first piece that fits and never undoes it, and in testing it solved only 2 of 61 dates.

## Setup

Requires Python 3.12+.

```
cd my-daydokuthon
python -m venv .venv
.venv\Scripts\activate
python -m pip install "daydokuthon[visualizer]>=0.1.1"
```

## Solve a challenge

1. Download your assigned `challenge.json` from the event submission page and place it in `my-daydokuthon/`. Its ID, date and puzzle version must match the event.
2. Generate and check the trace:

```
python -m daydokuthon run --algorithm solution:MyAlgorithm --challenge challenge.json --output submission.json
python -m daydokuthon validate submission.json --challenge challenge.json
python -m daydokuthon replay submission.json --challenge challenge.json
```

`validate` should report `legal: true`, `solved: true`, 12 actions and 47 covered cells. Then upload `submission.json` to the event URL with your roll number.

If `daydokuthon` is not on your PATH, use `python -m daydokuthon` as above.

## Private solver judging (optional)

`private_solver.py` is a single self-contained file exporting `solve_challenge(payload)`. It takes a challenge dictionary and returns a trace dictionary that keeps the challenge ID, date and puzzle version. For an impossible or malformed date it returns exactly `{"error": "invalid_date"}` instead of raising. It uses only the standard library and the SDK.

Attach it on the receipt page with **Submit solver for private tests**, then **Freeze Python submission**, before the challenge closes. A receipt accepts one source version only.

It was tested on all 366 dates of a leap year. Every date solved and replayed as valid, with a worst case of about 2.3 s against the judge's 10 s limit.

## Simulator dashboard

A localhost app that runs each algorithm on a chosen date, shows how long it took, and animates the search on the board.

```
cd my-daydokuthon
.venv\Scripts\python.exe simulator\server.py
```

Then open <http://localhost:8000>, pick a date and press **Solve & compare**. The server listens on `127.0.0.1` only and uses just the standard library.

Algorithms compared:

- **Greedy:** first piece that fits, never undone.
- **Backtracking:** removes the last piece when stuck.
- **Backtracking + pruning:** the main solver.
- **Pruning + greedy order & cutoff:** tries the greedy-preferred placement first (fewest open neighbouring cells). If an attempt exceeds its node budget, it restarts with a larger budget and a reshuffled order.
- **Genetic algorithm:** evolves 12-gene choice sequences decoded into boards, with fitness equal to cells covered.
- **Firefly algorithm:** the same encoding, with each firefly moving toward brighter ones.
- **GA + Firefly hybrid:** a genetic algorithm whose mutation step is a firefly move.

All algorithms share one bitmask engine so their timings are comparable. The randomised ones use a fixed seed (42).

### Benchmark

Median time and worst case over 61 dates (one every 6 days through 2024), with a 10 s limit:

| Algorithm | Solved | Median (worst) |
|---|---|---|
| Greedy | 2 / 61 | 0.1 ms |
| Backtracking | 61 / 61 | 3.6 ms (98.7 ms) |
| Backtracking + pruning | 61 / 61 | 3.1 ms (43.5 ms) |
| Pruning + greedy order & cutoff | 61 / 61 | 1.8 ms (27.5 ms) |
| Genetic algorithm | 61 / 61 | 35.6 ms (181 ms) |
| Firefly algorithm | 61 / 61 | 79.4 ms (648 ms) |
| GA + Firefly hybrid | 61 / 61 | 57.1 ms (3.9 s) |

Guided exact search suits this puzzle best, because it has many valid solutions and a strong structural prune. The metaheuristics solve every date but are 10 to 40 times slower, and the hybrid did not beat the plain genetic algorithm. Greedy's tiny time reflects that it quits early, not that it solves the puzzle.

The simulator's extra algorithms live only in `simulator/algos.py`. The submission files use backtracking with pruning.
