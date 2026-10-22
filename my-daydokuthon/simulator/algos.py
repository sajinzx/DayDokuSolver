"""Solvers used by the simulator, all on one bitmask engine so timings are comparable.

Bit i of every mask is board cell i in (q, r) order, so the lowest set bit of the
free mask is the lowest empty cell. Piece shapes are normalised with their minimum
cell at (0, 0), so a piece covering the lowest empty cell is anchored exactly there.
"""

import math
import random
import time

from daydokuthon.core import BOARD, PIECES

CELLS = sorted(BOARD.coordinates)
IDX = {c: i for i, c in enumerate(CELLS)}
NB = [sum(1 << IDX[n] for n in c.neighbors() if n in IDX) for c in CELLS]
PIDS = [p.id for p in PIECES]
SIZES = [len(p.cells) for p in PIECES]
ALL_PIECES = (1 << len(PIECES)) - 1
STEP_CAP = 20000

# BY_ANCHOR[a] = candidates (piece_index, rotation, flipped, mask, open_neighbours_mask)
BY_ANCHOR = [[] for _ in CELLS]
for _pi, _p in enumerate(PIECES):
    for _o in _p.orientations():
        _offsets = sorted(_o.cells)
        for _a, _c in enumerate(CELLS):
            _idx = [IDX.get(_c + d) for d in _offsets]
            if None in _idx:
                continue
            _mask = sum(1 << i for i in _idx)
            _nb = 0
            for i in _idx:
                _nb |= NB[i]
            BY_ANCHOR[_a].append((_pi, _o.rotation, _o.flipped, _mask, _nb & ~_mask))
BY_ANCHOR_BIG = [sorted(c, key=lambda t: -SIZES[t[0]]) for c in BY_ANCHOR]

_REACH = {}


class _Timeout(Exception):
    pass


class _Cutoff(Exception):
    pass


def _cells_of(mask):
    out = []
    while mask:
        b = mask & -mask
        c = CELLS[b.bit_length() - 1]
        out.append((c.q, c.r))
        mask ^= b
    return out


def _reach(rem):
    if rem not in _REACH:
        reach = {0}
        for i, s in enumerate(SIZES):
            if rem >> i & 1:
                reach |= {r + s for r in reach}
        _REACH[rem] = frozenset(reach)
    return _REACH[rem]


def _regions_ok(free, rem):
    """Every enclosed empty region must be exactly fillable by some remaining pieces."""
    reach = _reach(rem)
    rest = free
    while rest:
        low = rest & -rest
        comp, frontier = low, low
        while frontier:
            b = frontier & -frontier
            frontier ^= b
            n = NB[b.bit_length() - 1] & rest & ~comp
            comp |= n
            frontier |= n
        if comp.bit_count() not in reach:
            return False
        rest &= ~comp
    return True


def _free0(exposed):
    return ((1 << len(CELLS)) - 1) & ~sum(1 << IDX[c] for c in exposed)


def _result(algo, status, elapsed_ms, chosen, stats):
    placements = []
    for pi, rot, flip, mask, *_ in chosen:
        cells = _cells_of(mask)
        placements.append({
            "piece": PIDS[pi], "origin": {"q": cells[0][0], "r": cells[0][1]},
            "rotation": rot, "flipped": flip, "cells": cells,
        })
    return {
        "algo": algo, "status": status, "time_ms": round(elapsed_ms, 3),
        "pieces_placed": len(chosen),
        "covered": sum(SIZES[c[0]] for c in chosen),
        "placements": placements, **stats,
    }


# ---------------------------------------------------------------- exact family
def _exact(algo, free0, record, deadline):
    table = BY_ANCHOR_BIG if algo == "greedy" else BY_ANCHOR
    prune = algo in ("pruned", "pruned_greedy")
    ordered = algo == "pruned_greedy"
    commit = algo == "greedy"
    stats = {"nodes": 0, "backtracks": 0, "restarts": 0}
    chosen, steps = [], []
    rng = random.Random(7)
    state = {"budget": None, "attempt_nodes": 0, "noise": 0.0}

    def note(*event):
        if record and len(steps) < STEP_CAP:
            steps.append(event)

    def dfs(free, rem):
        if not free:
            return rem == 0
        stats["nodes"] += 1
        state["attempt_nodes"] += 1
        if stats["nodes"] & 1023 == 0 and time.perf_counter() > deadline:
            raise _Timeout
        if state["budget"] is not None and state["attempt_nodes"] > state["budget"]:
            raise _Cutoff
        a = (free & -free).bit_length() - 1
        cs = [c for c in table[a] if rem >> c[0] & 1 and c[3] & free == c[3]]
        if ordered:
            # greedy value ordering: placements that hug walls/pieces (fewest open
            # neighbours) first, bigger pieces first on ties; restarts add noise
            noise = state["noise"]
            cs.sort(key=lambda c: ((c[4] & free).bit_count()
                                   + (rng.random() * noise if noise else 0.0), -SIZES[c[0]]))
        for c in cs:
            nf, nr = free & ~c[3], rem & ~(1 << c[0])
            chosen.append(c)
            if record:
                note("p", PIDS[c[0]], _cells_of(c[3]))
            if commit:
                return dfs(nf, nr)  # greedy: first fit is final, never undone
            if (not prune or _regions_ok(nf, nr)) and dfs(nf, nr):
                return True
            chosen.pop()
            stats["backtracks"] += 1
            note("r", PIDS[c[0]])
        return False

    status = "failed"
    start = time.perf_counter()
    try:
        if ordered:
            # greedy-guided search with a node cutoff: when an attempt blows its
            # budget, restart with a bigger budget and a re-shuffled greedy order
            budget = 300
            while True:
                chosen.clear()
                state.update(budget=budget, attempt_nodes=0,
                             noise=0.0 if stats["restarts"] == 0 else 3.0)
                try:
                    status = "solved" if dfs(free0, ALL_PIECES) else "failed"
                    break
                except _Cutoff:
                    stats["restarts"] += 1
                    budget = int(budget * 1.6)
                    note("x")
        else:
            status = "solved" if dfs(free0, ALL_PIECES) else "failed"
    except _Timeout:
        status = "timeout"
    elapsed = (time.perf_counter() - start) * 1000
    out = _result(algo, status, elapsed, chosen, stats)
    if record:
        out["steps"], out["steps_truncated"] = steps, len(steps) >= STEP_CAP
    return out


# ------------------------------------------------------------ metaheuristics
GENES = len(PIECES)


def _decode(genes, free0):
    """Genes in [0,1): gene k picks which legal (piece, orientation) goes at the lowest
    empty cell on step k. A cell nothing fits in is left as a hole."""
    free, rem, chosen = free0, ALL_PIECES, []
    while free and rem:
        a = (free & -free).bit_length() - 1
        cs = [c for c in BY_ANCHOR[a] if rem >> c[0] & 1 and c[3] & free == c[3]]
        if not cs:
            free &= free - 1
            continue
        c = cs[min(int(genes[len(chosen)] * len(cs)), len(cs) - 1)]
        chosen.append(c)
        free &= ~c[3]
        rem &= ~(1 << c[0])
    return chosen


def _meta(algo, free0, record, deadline):
    rng = random.Random(42)
    target = free0.bit_count()
    stats = {"nodes": 0, "generations": 0, "restarts": 0}
    steps = []
    best = {"cov": -1, "chosen": []}
    clamp = lambda g: 0.0 if g < 0 else (0.999999 if g >= 1 else g)

    def evaluate(genes):
        chosen = _decode(genes, free0)
        stats["nodes"] += 1
        cov = sum(SIZES[c[0]] for c in chosen)
        if cov > best["cov"]:
            best["cov"], best["chosen"] = cov, chosen
            if record and len(steps) < STEP_CAP:
                steps.append(("f", [[PIDS[c[0]], _cells_of(c[3])] for c in chosen]))
        return cov

    def rand_genes():
        return [rng.random() for _ in range(GENES)]

    def tournament(pop, fit, k=3):
        return max(rng.sample(range(len(pop)), k), key=lambda i: fit[i])

    def crossover(a, b):
        return [x if rng.random() < 0.5 else y for x, y in zip(a, b)]

    def mutate(g, rate=0.15, sigma=0.2):
        return [clamp(x + rng.gauss(0, sigma)) if rng.random() < rate
                else (rng.random() if rng.random() < 0.03 else x) for x in g]

    def dist2(a, b):
        return sum((x - y) ** 2 for x, y in zip(a, b))

    def firefly_move(x, xj, alpha, gamma=0.5, beta0=1.0):
        beta = beta0 * math.exp(-gamma * dist2(x, xj))
        return [clamp(a + beta * (b - a) + alpha * (rng.random() - 0.5)) for a, b in zip(x, xj)]

    def timed_out():
        return time.perf_counter() > deadline

    start = time.perf_counter()
    P = 60 if algo != "firefly" else 30
    pop = [rand_genes() for _ in range(P)]
    fit = [evaluate(g) for g in pop]
    last_improve, last_best = 0, max(fit)
    alpha = 0.5
    while best["cov"] < target and not timed_out():
        stats["generations"] += 1
        if algo == "firefly":
            # every firefly moves toward each brighter one; attraction fades with distance
            order = sorted(range(P), key=lambda i: fit[i])
            for i in range(P):
                x = pop[i]
                for j in range(P):
                    if fit[j] > fit[i]:
                        x = firefly_move(x, pop[j], alpha)
                if x is pop[i]:  # brightest firefly: random walk
                    x = [clamp(v + alpha * (rng.random() - 0.5)) for v in x]
                nf = evaluate(x)
                if nf >= fit[i]:
                    pop[i], fit[i] = x, nf
                if best["cov"] >= target or timed_out():
                    break
            alpha = max(0.02, alpha * 0.97)
        else:
            elite = sorted(range(P), key=lambda i: -fit[i])[:2]
            new, new_fit = [pop[i] for i in elite], [fit[i] for i in elite]
            while len(new) < P:
                i1, i2 = tournament(pop, fit), tournament(pop, fit)
                child = crossover(pop[i1], pop[i2])
                if algo == "hybrid":
                    # firefly attraction replaces plain mutation: drift toward a brighter
                    # individual, with a small random walk; fall back to mutation if none
                    j = tournament(pop, fit)
                    if fit[j] > (fit[i1] + fit[i2]) / 2:
                        child = firefly_move(child, pop[j], alpha)
                    else:
                        child = mutate(child)
                else:
                    child = mutate(child)
                new.append(child)
                new_fit.append(evaluate(child))
                if best["cov"] >= target or timed_out():
                    break
            while len(new) < P:  # keep population size if we broke out early
                new.append(pop[len(new)]); new_fit.append(fit[len(new_fit)])
            pop, fit = new, new_fit
            alpha = max(0.05, alpha * 0.98)
        if max(fit) > last_best:
            last_best, last_improve = max(fit), stats["generations"]
        elif stats["generations"] - last_improve > 60:
            # stagnation: keep the best quarter, re-seed the rest
            keep = sorted(range(P), key=lambda i: -fit[i])[: P // 4]
            pop = [pop[i] for i in keep] + [rand_genes() for _ in range(P - len(keep))]
            fit = [fit[i] for i in keep] + [evaluate(g) for g in pop[len(keep):]]
            last_improve = stats["generations"]
            alpha = 0.5
            stats["restarts"] += 1
    elapsed = (time.perf_counter() - start) * 1000
    status = "solved" if best["cov"] >= target else "failed"
    out = _result(algo, status, elapsed, best["chosen"], stats)
    if record:
        out["steps"], out["steps_truncated"] = steps, len(steps) >= STEP_CAP
    return out


ALGOS = ("greedy", "backtrack", "pruned", "pruned_greedy", "ga", "firefly", "hybrid")
RANDOMISED = ("ga", "firefly", "hybrid")


def run(algo, exposed, record=False, time_limit=30.0):
    free0 = _free0(exposed)
    deadline = time.perf_counter() + time_limit
    fn = _meta if algo in RANDOMISED else _exact
    return fn(algo, free0, record, deadline)


def board_json(day):
    exposed = BOARD.exposed(day)
    return {
        "cells": [
            {"q": c.coordinate.q, "r": c.coordinate.r, "value": c.value, "type": c.type,
             "exposed": c.coordinate in exposed}
            for c in BOARD.cells
        ],
        "algos": list(ALGOS),
    }


def exposed_for(day):
    return BOARD.exposed(day)
