"""Line charts for the printed reports, as inline SVG: the PDF builder
draws SVG reliably, without scripts. The gradebook grid draws the same
chart in the browser (gradebook_chart.js)."""

import math

from markupsafe import Markup

STUDENT_COLOR = "#2a78d6"  # the selected student: the one accent
AVERAGE_COLOR = "#7a7974"  # the class average: recessive gray
AVERAGE_FILL = "#7a7974"
GRID_COLOR = "#e3e2de"
TEXT_COLOR = "#52514e"


def value_floor(values):
    """Bottom of the percent axis: 60, or lower in steps of 10 to fit the
    lowest value (Candle's charts start at 60 too)."""
    low = min((v for v in values if v is not None), default=100)
    return max(0, min(60, math.floor(low / 10) * 10))


def _segments(points):
    """Runs of consecutive points, split where a value is None."""
    runs, run = [], []
    for point in points:
        if point[1] is None:
            if run:
                runs.append(run)
            run = []
        else:
            run.append(point)
    if run:
        runs.append(run)
    return runs


def performance_svg(averages, student, width=420, height=130):
    """A student's scores beside the class average, one x step per
    assignment in order.

    :param averages: class average per assignment (None: no scores)
    :param student: the student's percent per assignment (None: no score)
    """
    count = len(averages)
    left, right, top, bottom = 26, 6, 6, 16
    plot_w, plot_h = width - left - right, height - top - bottom
    low = value_floor(list(averages) + list(student))
    step = plot_w / (count - 1) if count > 1 else 0

    def x(index):
        return left + (index * step if count > 1 else plot_w / 2)

    def y(value):
        value = max(low, min(100, value))
        return top + (100 - value) / (100 - low) * plot_h

    # A fixed size: the PDF builder can't size an SVG from its container.
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}" font-family="sans-serif" font-size="8">'
    ]
    # Hairline gridlines every 10, labelled on the left.
    for value in range(low, 101, 10 if 100 - low <= 50 else 20):
        gy = y(value)
        parts.append(
            f'<line x1="{left}" x2="{width - right}" y1="{gy:.1f}" y2="{gy:.1f}" '
            f'stroke="{GRID_COLOR}" stroke-width="1"/>'
            f'<text x="{left - 4}" y="{gy + 3:.1f}" text-anchor="end" fill="{TEXT_COLOR}">{value}</text>'
        )
    # Assignment numbers along the bottom, thinned out when crowded.
    every = max(1, math.ceil(count / 15))
    for index in range(count):
        # The last number too, unless it would touch the one before.
        last = index == count - 1 and (count - 1) % every > every // 2
        if index % every == 0 or last:
            parts.append(
                f'<text x="{x(index):.1f}" y="{height - 4}" text-anchor="middle" '
                f'fill="{TEXT_COLOR}">{index + 1}</text>'
            )
    # Class average: a light area under a gray line.
    for run in _segments(list(enumerate(averages))):
        line = " ".join(f"{x(i):.1f},{y(v):.1f}" for i, v in run)
        base = top + plot_h
        area = f"{x(run[0][0]):.1f},{base:.1f} {line} {x(run[-1][0]):.1f},{base:.1f}"
        parts.append(f'<polygon points="{area}" fill="{AVERAGE_FILL}" fill-opacity="0.12"/>')
        if len(run) > 1:
            parts.append(
                f'<polyline points="{line}" fill="none" stroke="{AVERAGE_COLOR}" stroke-width="2" '
                f'stroke-linejoin="round" stroke-linecap="round"/>'
            )
        else:  # a lone point has no line: a dot shows it
            parts.append(
                f'<circle cx="{x(run[0][0]):.1f}" cy="{y(run[0][1]):.1f}" r="2.5" fill="{AVERAGE_COLOR}"/>'
            )
    # The student: a blue line, with dots when there is room for them.
    dots = count <= 24
    for run in _segments(list(enumerate(student))):
        if len(run) > 1:
            line = " ".join(f"{x(i):.1f},{y(v):.1f}" for i, v in run)
            parts.append(
                f'<polyline points="{line}" fill="none" stroke="{STUDENT_COLOR}" stroke-width="2" '
                f'stroke-linejoin="round" stroke-linecap="round"/>'
            )
        for i, v in run:
            if dots or len(run) == 1:
                parts.append(
                    f'<circle cx="{x(i):.1f}" cy="{y(v):.1f}" r="3" fill="{STUDENT_COLOR}" '
                    f'stroke="#ffffff" stroke-width="1.5"/>'
                )
    parts.append("</svg>")
    return Markup("".join(parts))

