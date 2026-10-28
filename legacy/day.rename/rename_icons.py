"""Small code-drawn line icons, rendered at 3x for crisp Windows DPI scaling."""
from PIL import Image, ImageDraw
import customtkinter as ctk


def icon(name, color="#838794", size=18):
    scale = 3
    canvas = Image.new("RGBA", (24 * scale, 24 * scale))
    draw = ImageDraw.Draw(canvas)
    def line(points, width=1.7):
        draw.line([(int(x * scale), int(y * scale)) for x, y in points], fill=color, width=max(1, int(width * scale)), joint="curve")
    def box(bounds, radius=1.2):
        draw.rounded_rectangle(tuple(int(v * scale) for v in bounds), radius=int(radius * scale), outline=color, width=scale * 2)
    def plus(x, y):
        line([(x - 3, y), (x + 3, y)])
        line([(x, y - 3), (x, y + 3)])
    if name == "replace":
        line([(4, 9), (7, 5), (15, 5), (19, 9)])
        line([(19, 4), (19, 9), (14, 9)])
        line([(20, 15), (17, 19), (9, 19), (5, 15)])
        line([(5, 20), (5, 15), (10, 15)])
    elif name == "smart":
        line([(5, 20), (17, 8)], 3)
        line([(13, 8), (17, 12)], 2)
        plus(6, 6)
        plus(19, 18)
        plus(18, 3)
    elif name in ("insert", "file"):
        box((5, 3, 18, 21))
        plus(12, 12)
    elif name == "number":
        for y in (6, 12, 18):
            line([(9, y), (21, y)])
        line([(3, 5), (4, 4), (4, 8)])
        line([(3, 11), (5, 11), (3, 14), (5, 14)], 1)
        line([(3, 17), (5, 17), (4, 19), (5, 20), (3, 20)], 1)
    elif name == "manual":
        line([(5, 16), (16, 5), (20, 9), (9, 20), (4, 21), (5, 16), (9, 20)])
        line([(14, 7), (18, 11)])
    elif name == "folder":
        line([(3, 7), (3, 20), (21, 20), (21, 6), (12, 6), (10, 3), (3, 3), (3, 7), (21, 7)])
    elif name == "remove":
        line([(5, 7), (19, 7)])
        line([(8, 7), (8, 20), (16, 20), (16, 7)])
        line([(9, 4), (15, 4)])
    elif name == "undo":
        line([(8, 5), (3, 10), (8, 15)])
        line([(3, 10), (15, 10), (19, 14), (19, 18), (15, 21)])
    elif name == "play":
        draw.polygon([(8 * scale, 5 * scale), (20 * scale, 12 * scale), (8 * scale, 19 * scale)], fill=color)
    else:
        line([(6, 6), (18, 18)])
        line([(18, 6), (6, 18)])
    return ctk.CTkImage(light_image=canvas, dark_image=canvas, size=(size, size))
