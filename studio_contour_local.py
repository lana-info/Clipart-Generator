"""Small, deterministic contour edits confined to selected node runs.

Coordinates are image pixels. Simplify removes a small batch of straight
anchors from each run; Smooth damps alternating boundary noise by at most 0.35px.
Coherent curvature is left alone, so repeated smoothing cannot shrink a flower
into a circle. No hidden history or strength setting is required.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from math import atan2, degrees, hypot
from collections.abc import Iterable, Sequence

from studio_contour import BezierNode, BezierPath, MAX_NODES_PER_PATH, MAX_PATHS, _auto_handles

Point = tuple[float, float]
Selection = frozenset[tuple[int, int]]
_MAX_SAMPLES = 32_768
_MAX_COMPARISONS = 200_000
_EPS = 1e-8
_CLEARANCE = .06  # exceeds the combined 0.025px cubic flattening error
_SIMPLIFY_ERROR = 1.25  # measured useful step beyond normal 1px extraction


@dataclass(frozen=True)
class LocalContourResult:
    paths: tuple[BezierPath, ...]
    selection: Selection
    changed: bool


def _inputs(paths: Sequence[BezierPath], selection: Iterable[tuple[int, int]]):
    if not isinstance(paths, Sequence) or isinstance(paths, (str, bytes)):
        raise ValueError("paths must be a bounded sequence")
    if len(paths) > MAX_PATHS or any(not isinstance(p, BezierPath) for p in paths):
        raise ValueError("paths contain unsupported values")
    original = tuple(paths)
    selected = set()
    try:
        for count, pair in enumerate(selection):
            if count >= MAX_PATHS * MAX_NODES_PER_PATH:
                raise ValueError("selection exceeds the node limit")
            if not isinstance(pair, tuple) or len(pair) != 2:
                raise ValueError("selection entries must be (path, node) pairs")
            pi, ni = pair
            if any(isinstance(v, bool) or not isinstance(v, int) for v in pair):
                raise ValueError("selection indices must be integers")
            if not 0 <= pi < len(original) or not 0 <= ni < len(original[pi].nodes):
                raise ValueError("selection index is outside the document")
            selected.add(pair)
    except TypeError as exc:
        raise ValueError("selection must contain index pairs") from exc
    return original, frozenset(selected)


def _runs(count: int, selected: set[int]) -> list[tuple[int, ...]]:
    if not selected:
        return []
    if len(selected) == count:
        return [tuple(range(count))]
    runs = []
    for start in sorted(i for i in selected if (i - 1) % count not in selected):
        run = [start]
        while (run[-1] + 1) % count in selected:
            run.append((run[-1] + 1) % count)
        runs.append(tuple(run))
    return runs


def _sub(a: Point, b: Point) -> Point:
    return a[0] - b[0], a[1] - b[1]


def _cross(a: Point, b: Point) -> float:
    return a[0] * b[1] - a[1] * b[0]


def _length(a: Point) -> float:
    return hypot(*a)


def _turn(points: Sequence[Point], i: int, stride: int = 1) -> float:
    p = points[i]
    a, b = _sub(p, points[(i - stride) % len(points)]), _sub(points[(i + stride) % len(points)], p)
    return degrees(atan2(_cross(a, b), a[0] * b[0] + a[1] * b[1]))


def _distance(p: Point, a: Point, b: Point) -> float:
    ab = _sub(b, a)
    length = _length(ab)
    return abs(_cross(ab, _sub(p, a))) / length if length > _EPS else _length(_sub(p, a))


def _sharp(points: Sequence[Point], i: int) -> bool:
    turn = _turn(points, i)
    support = _turn(points, i, 2) if len(points) >= 5 else turn
    depth = _distance(points[i], points[i - 1], points[(i + 1) % len(points)])
    # A one-pixel zigzag may have a large angle, but not a supported tip.
    return abs(turn) >= 55 and (depth >= .75 or (abs(support) >= 40 and turn * support > 0))


def _implicit(node: BezierNode) -> bool:
    return node.kind == "smooth" and (node.in_handle is None or node.out_handle is None)


def _segment_distance(point: Point, a: Point, b: Point) -> float:
    ab = _sub(b, a)
    squared = ab[0] ** 2 + ab[1] ** 2
    if squared <= _EPS:
        return hypot(point[0] - a[0], point[1] - a[1])
    ap = _sub(point, a)
    fraction = max(0., min(1., (ap[0] * ab[0] + ap[1] * ab[1]) / squared))
    return hypot(point[0] - a[0] - fraction * ab[0],
                 point[1] - a[1] - fraction * ab[1])


def _straight(a: Point, c1: Point, c2: Point, b: Point) -> bool:
    ab = _sub(b, a)
    squared = ab[0] ** 2 + ab[1] ** 2
    if squared <= _EPS:
        return False
    return all(_distance(c, a, b) <= .025 and
               -_EPS <= _sub(c, a)[0] * ab[0] + _sub(c, a)[1] * ab[1] <= squared + _EPS
               for c in (c1, c2))


def _mid(a: Point, b: Point) -> Point:
    return (a[0] + b[0]) / 2, (a[1] + b[1]) / 2


def _polyline(path: BezierPath) -> tuple[Point, ...] | None:
    points: list[Point] = []
    for i, node in enumerate(path.nodes):
        following = path.nodes[(i + 1) % len(path.nodes)]
        controls = (node.point, _auto_handles(path.nodes, i)[1],
                    _auto_handles(path.nodes, (i + 1) % len(path.nodes))[0], following.point)
        stack = [(controls, 0)]
        while stack:
            (a, b, c, d), depth = stack.pop()
            if _straight(a, b, c, d):
                points.append(a)
            elif depth >= 12:
                return None
            else:
                ab, bc, cd = _mid(a, b), _mid(b, c), _mid(c, d)
                abc, bcd = _mid(ab, bc), _mid(bc, cd)
                middle = _mid(abc, bcd)
                stack.extend([((middle, bcd, cd, d), depth + 1), ((a, ab, abc, middle), depth + 1)])
            if len(points) + len(stack) > _MAX_SAMPLES:
                return None
    return tuple(points)


def _intersects(a: Point, b: Point, c: Point, d: Point) -> bool:
    if max(a[0], b[0]) < min(c[0], d[0]) - _CLEARANCE or max(c[0], d[0]) < min(a[0], b[0]) - _CLEARANCE:
        return False
    if max(a[1], b[1]) < min(c[1], d[1]) - _CLEARANCE or max(c[1], d[1]) < min(a[1], b[1]) - _CLEARANCE:
        return False
    ab, cd = _sub(b, a), _sub(d, c)
    u, v = _cross(ab, _sub(c, a)), _cross(ab, _sub(d, a))
    w, z = _cross(cd, _sub(a, c)), _cross(cd, _sub(b, c))
    if u * v <= _EPS and w * z <= _EPS:
        return True

    def distance_to_segment(p, start, end):
        direction = _sub(end, start)
        square = direction[0] ** 2 + direction[1] ** 2
        if square <= _EPS:
            return _length(_sub(p, start))
        offset = _sub(p, start)
        t = max(0., min(1., (offset[0] * direction[0] + offset[1] * direction[1]) / square))
        return _length(_sub(p, (start[0] + t * direction[0], start[1] + t * direction[1])))

    return min(distance_to_segment(a, c, d), distance_to_segment(b, c, d),
               distance_to_segment(c, a, b), distance_to_segment(d, a, b)) <= _CLEARANCE


def _segments(points: Sequence[Point]):
    return [(min(a[0], b[0]), max(a[0], b[0]), i, a, b)
            for i, a in enumerate(points) for b in (points[(i + 1) % len(points)],)]


def _geometry_contacts(points: tuple[Point, ...]):
    """Bounded profile of forbidden geometry, keyed by exact segment coordinates.

    Extracted raster fur may already contain one-pixel backtracking contacts.
    Such contacts cannot be changed or removed, but do not veto unrelated edits.
    """
    from collections import Counter
    if len(points) < 3 or abs(_area(points)) < .01:
        return None
    if any(_length(_sub(a, points[(i + 1) % len(points)])) <= _EPS for i, a in enumerate(points)):
        return None
    contacts = Counter()
    for i, p in enumerate(points):
        incoming = _sub(p, points[i - 1])
        outgoing = _sub(points[(i + 1) % len(points)], p)
        if abs(_cross(incoming, outgoing)) <= _EPS and incoming[0] * outgoing[0] + incoming[1] * outgoing[1] < 0:
            contacts[("backtrack", points[i - 1], p, points[(i + 1) % len(points)])] += 1
    active = []
    comparisons = 0
    for segment in sorted(_segments(points)):
        left, _, i, a, b = segment
        active = [s for s in active if s[1] >= left - _CLEARANCE]
        for _, _, j, c, d in active:
            comparisons += 1
            if comparisons > _MAX_COMPARISONS:
                return None
            if (i - j) % len(points) in (1, len(points) - 1):
                continue
            if _intersects(a, b, c, d):
                contacts[("contact", tuple(sorted(((a, b), (c, d)))))] += 1
        active.append(segment)
    return contacts


def _simple(points: tuple[Point, ...]) -> bool:
    contacts = _geometry_contacts(points)
    return contacts is not None and not contacts


def _area(points: Sequence[Point]) -> float:
    return sum(_cross(p, points[(i + 1) % len(points)]) for i, p in enumerate(points)) / 2


def _cross_contacts(first: tuple[Point, ...], second: tuple[Point, ...]):
    from collections import Counter
    contacts = Counter()
    combined = [(s, group) for group, points in enumerate((first, second)) for s in _segments(points)]
    active = []
    comparisons = 0
    for segment, group in sorted(combined):
        left, _, _, a, b = segment
        active = [(s, g) for s, g in active if s[1] >= left - _CLEARANCE]
        for (_, _, _, c, d), other in active:
            if other != group:
                comparisons += 1
                if comparisons > _MAX_COMPARISONS:
                    return None
                if _intersects(a, b, c, d):
                    contacts[tuple(sorted(((a, b), (c, d))))] += 1
        active.append((segment, group))
    return contacts


def _separate(first: tuple[Point, ...], second: tuple[Point, ...]) -> bool:
    contacts = _cross_contacts(first, second)
    return contacts is not None and not contacts


def _contains(points: Sequence[Point], point: Point) -> bool:
    inside = False
    x, y = point
    for i, a in enumerate(points):
        b = points[(i + 1) % len(points)]
        if (a[1] > y) != (b[1] > y):
            if x < a[0] + (y - a[1]) * (b[0] - a[0]) / (b[1] - a[1]):
                inside = not inside
    return inside


def _safe(original: BezierPath, candidate: BezierPath, others: Sequence[BezierPath]) -> bool:
    before, after = _polyline(original), _polyline(candidate)
    if before is None or after is None:
        return False
    old_contacts, new_contacts = _geometry_contacts(before), _geometry_contacts(after)
    if old_contacts is None or new_contacts is None or old_contacts != new_contacts:
        return False
    if _area(before) * _area(after) <= 0:
        return False
    for path in others:
        points = _polyline(path)
        if points is None:
            return False
        old_crossings, new_crossings = _cross_contacts(before, points), _cross_contacts(after, points)
        if old_crossings is None or new_crossings is None or old_crossings != new_crossings:
            return False
        if (_contains(before, points[0]) != _contains(after, points[0])
                or _contains(points, before[0]) != _contains(points, after[0])):
            return False
    return True


def simplify_selected(paths: Sequence[BezierPath], selection: Iterable[tuple[int, int]]) -> LocalContourResult:
    """Remove a small batch of expendable straight anchors, remapping indices.

    Curved incident segments and implicit neighbor tangents are retained. Runs
    need three selected nodes; their two endpoint anchors never move or vanish.
    Each independent replacement chord deviates by at most 1.25 image pixels,
    allowing a small useful step after normal 1px auto-contour extraction.
    """
    original, selected = _inputs(paths, selection)
    result = list(original)
    remapped = set(selected)
    for pi, path in enumerate(original):
        selected_nodes = {ni for p, ni in selected if p == pi}
        runs = _runs(len(path.nodes), selected_nodes)
        points = tuple(node.point for node in path.nodes)
        remove = set()
        for run in runs:
            if len(run) < 3:
                continue
            candidates = run if len(run) == len(path.nodes) else run[1:-1]
            eligible = []
            for i in candidates:
                previous, node, following = path.nodes[i - 1], path.nodes[i], path.nodes[(i + 1) % len(path.nodes)]
                if _sharp(points, i) or _implicit(previous) or _implicit(following):
                    continue
                prev_out = _auto_handles(path.nodes, (i - 1) % len(path.nodes))[1]
                node_in, node_out = _auto_handles(path.nodes, i)
                next_in = _auto_handles(path.nodes, (i + 1) % len(path.nodes))[0]
                # Nonzero surviving handles change their parametrization when
                # an anchor vanishes; only zero handles are safe to retain.
                if prev_out != previous.point or next_in != following.point:
                    continue
                if not (_straight(previous.point, prev_out, node_in, node.point)
                        and _straight(node.point, node_out, next_in, following.point)):
                    continue
                # A cubic stays inside its control hull. Bound every control
                # against the replacement segment, not just its anchor: even
                # near-straight explicit handles can exceed the step limit.
                error = max(_segment_distance(control, previous.point, following.point)
                            for control in (prev_out, node_in, node.point, node_out, next_in))
                if error <= _SIMPLIFY_ERROR:
                    eligible.append((error, i))
            budget = min(8, max(1, len(run) // 4))
            taken = 0
            for _, i in sorted(eligible):
                if taken >= budget or len(path.nodes) - len(remove) <= 3:
                    break
                # Independent original chords bound this batch's deviation.
                if any(j in remove for j in ((i - 1) % len(path.nodes), (i + 1) % len(path.nodes))):
                    continue
                remove.add(i)
                taken += 1
        if not remove:
            continue
        candidate = replace(path, nodes=tuple(node for i, node in enumerate(path.nodes) if i not in remove))
        if not _safe(path, candidate, [p for j, p in enumerate(result) if j != pi]):
            continue
        result[pi] = candidate
        remapped.difference_update((pi, i) for i in selected_nodes)
        remapped.update((pi, i - sum(r < i for r in remove)) for i in selected_nodes if i not in remove)
    return LocalContourResult(tuple(result), frozenset(remapped), tuple(result) != original)


def smooth_selected(paths: Sequence[BezierPath], selection: Iterable[tuple[int, int]]) -> LocalContourResult:
    """Damp local alternating noise without flattening coherent curves or tips.

    Each click moves eligible anchors by one quarter of their normal residual,
    capped at 0.35px; residuals below 0.12px are stable and return unchanged.
    Existing explicit handles translate with their anchor. Automatic handles on
    unselected nodes and fixed run endpoints must not change indirectly.
    """
    original, selected = _inputs(paths, selection)
    result = list(original)
    for pi, path in enumerate(original):
        selected_nodes = {ni for p, ni in selected if p == pi}
        runs = _runs(len(path.nodes), selected_nodes)
        movable = {i for run in runs if len(run) >= 3 for i in
                   (run if len(run) == len(path.nodes) else run[1:-1])}
        points = tuple(node.point for node in path.nodes)
        nodes = list(path.nodes)
        for i in sorted(movable):
            if _sharp(points, i):
                continue
            # A neighbor's implicit tangent depends on this anchor, even when
            # that neighbor itself stays byte-for-byte unchanged.
            if any(_implicit(path.nodes[j]) and j not in movable
                   for j in ((i - 1) % len(nodes), (i + 1) % len(nodes))):
                continue
            turn = _turn(points, i)
            if not any(turn * _turn(points, j) < -1e-6 for j in ((i - 1) % len(nodes), (i + 1) % len(nodes))):
                continue
            a, p, b = points[i - 1], points[i], points[(i + 1) % len(nodes)]
            ab = _sub(b, a)
            squared = ab[0] ** 2 + ab[1] ** 2
            if squared <= _EPS:
                continue
            t = (_sub(p, a)[0] * ab[0] + _sub(p, a)[1] * ab[1]) / squared
            if not .05 <= t <= .95:
                continue
            target = (a[0] + t * ab[0], a[1] + t * ab[1])
            delta = _sub(target, p)
            residual = _length(delta)
            if residual < .12:
                continue
            factor = min(.25, .35 / residual)
            shift = (delta[0] * factor, delta[1] * factor)
            node = nodes[i]
            translate = lambda value: None if value is None else (value[0] + shift[0], value[1] + shift[1])
            nodes[i] = replace(node, point=translate(node.point), in_handle=translate(node.in_handle), out_handle=translate(node.out_handle))
        # Sharp tips and noise already below the limit are fixed too. An
        # automatic tangent at any fixed node must retain its original inputs.
        changed_nodes = {i for i, node in enumerate(nodes) if node != path.nodes[i]}
        while True:
            blocked = {i for i in changed_nodes
                       if any(_implicit(path.nodes[j]) and j not in changed_nodes
                              for j in ((i - 1) % len(nodes), (i + 1) % len(nodes)))}
            if not blocked:
                break
            for i in blocked:
                nodes[i] = path.nodes[i]
            changed_nodes.difference_update(blocked)
        if tuple(nodes) == path.nodes:
            continue
        try:
            candidate = replace(path, nodes=tuple(nodes))
        except ValueError:
            continue
        if _safe(path, candidate, [p for j, p in enumerate(result) if j != pi]):
            result[pi] = candidate
    return LocalContourResult(tuple(result), selected, tuple(result) != original)


def local_changed_path_rois(previous: BezierPath, replacement: BezierPath) -> tuple[tuple[int, int, int, int], ...]:
    """Separate padded supports for changed cubic runs, including node deletion.

    Exact unchanged segments cancel independent of their new node indices.
    Rectangles merge only when they overlap, retaining untouched gaps between
    disconnected edits. The caller composes each support against original alpha.
    """
    from collections import Counter
    from math import ceil, floor

    if previous.source_shape != replacement.source_shape:
        raise ValueError("replacement must retain the original source shape")

    def segments(path):
        return [(node.point, _auto_handles(path.nodes, i)[1],
                 _auto_handles(path.nodes, (i + 1) % len(path.nodes))[0],
                 path.nodes[(i + 1) % len(path.nodes)].point)
                for i, node in enumerate(path.nodes)]

    old, new = segments(previous), segments(replacement)
    old_counts, new_counts = Counter(old), Counter(new)
    height, width = previous.source_shape
    rois = []
    for ordered, unmatched in ((old, old_counts - new_counts), (new, new_counts - old_counts)):
        changed = set()
        for i, segment in enumerate(ordered):
            if unmatched[segment]:
                changed.add(i)
                unmatched[segment] -= 1
        for run in _runs(len(ordered), changed):
            points = [p for i in run for p in ordered[i]]
            rois.append((max(0, floor(min(p[0] for p in points)) - 13),
                         max(0, floor(min(p[1] for p in points)) - 13),
                         min(width, ceil(max(p[0] for p in points)) + 14),
                         min(height, ceil(max(p[1] for p in points)) + 14)))
    merged = []
    while rois:
        a = rois.pop(0)
        for pool in (rois, merged):
            match = next((i for i, b in enumerate(pool)
                          if a[0] < b[2] and b[0] < a[2] and a[1] < b[3] and b[1] < a[3]), None)
            if match is not None:
                b = pool.pop(match)
                rois.insert(0, (min(a[0], b[0]), min(a[1], b[1]), max(a[2], b[2]), max(a[3], b[3])))
                break
        else:
            merged.append(a)
    return tuple(sorted(merged))


def local_changed_path_roi(previous: BezierPath, replacement: BezierPath) -> tuple[int, int, int, int]:
    """Compatibility union; local alpha edits should use separate supports."""
    rois = local_changed_path_rois(previous, replacement)
    if not rois:
        return (0, 0, 1, 1)
    return (min(r[0] for r in rois), min(r[1] for r in rois),
            max(r[2] for r in rois), max(r[3] for r in rois))
