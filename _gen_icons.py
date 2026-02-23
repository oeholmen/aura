#!/usr/bin/env python3
"""Generate PNG icons from SVG for Android PWA launcher."""
import subprocess, os, sys

os.chdir(os.path.join(os.path.dirname(__file__), 'interface', 'static'))

svg_data = open('icon.svg', 'rb').read()

generated = False

# Try cairosvg
try:
    import cairosvg
    cairosvg.svg2png(bytestring=svg_data, write_to='icon-192.png', output_width=192, output_height=192)
    cairosvg.svg2png(bytestring=svg_data, write_to='icon-512.png', output_width=512, output_height=512)
    print('Generated via cairosvg')
    generated = True
except ImportError:
    pass

# Try rsvg-convert
if not generated:
    try:
        for size, name in [(192, 'icon-192.png'), (512, 'icon-512.png')]:
            subprocess.run(['rsvg-convert', '-w', str(size), '-h', str(size), 'icon.svg', '-o', name], check=True)
        print('Generated via rsvg-convert')
        generated = True
    except (FileNotFoundError, subprocess.CalledProcessError):
        pass

# Pillow fallback
if not generated:
    try:
        from PIL import Image, ImageDraw
        for size, name in [(192, 'icon-192.png'), (512, 'icon-512.png')]:
            img = Image.new('RGBA', (size, size), (3, 0, 5, 255))
            draw = ImageDraw.Draw(img)
            cx, cy = size // 2, size // 2
            for r in range(size // 2, 0, -1):
                frac = r / (size // 2)
                c = (int(217 * frac + 6 * (1 - frac)),
                     int(70 * frac + 182 * (1 - frac)),
                     int(239 * frac + 212 * (1 - frac)))
                draw.ellipse([cx - r, cy - r, cx + r, cy + r], outline=(*c, max(50, int(255 * (1 - frac)))))
            d = size // 4
            draw.polygon([(cx, cy - d), (cx - d, cy), (cx, cy + d), (cx + d, cy)],
                         fill=(217, 70, 239, 200))
            img.save(name)
        print('Generated via Pillow')
        generated = True
    except ImportError:
        pass

# Last resort: use sips (macOS built-in)
if not generated:
    # Create a simple HTML canvas render approach won't work, so just use sips with a temp PDF
    # Actually let's use Python's built-in to create a minimal PNG
    import struct, zlib

    def make_png(width, height, r, g, b):
        """Create a solid-color PNG with a centered diamond shape."""
        rows = []
        cx, cy = width // 2, height // 2
        d = width // 4
        for y in range(height):
            row = b'\x00'  # filter byte
            for x in range(width):
                # Diamond check
                if abs(x - cx) + abs(y - cy) <= d:
                    row += bytes([217, 70, 239, 230])  # Magenta diamond
                elif abs(x - cx) + abs(y - cy) <= d + 4:
                    row += bytes([6, 182, 212, 180])  # Cyan border
                else:
                    # Radial gradient
                    dist = ((x - cx) ** 2 + (y - cy) ** 2) ** 0.5
                    max_dist = (cx ** 2 + cy ** 2) ** 0.5
                    frac = min(1.0, dist / max_dist)
                    pr = int(20 * (1 - frac))
                    pg = int(5 * (1 - frac))
                    pb = int(30 * (1 - frac))
                    row += bytes([pr, pg, pb, 255])
            rows.append(row)
        raw = b''.join(rows)

        def chunk(ctype, data):
            c = ctype + data
            crc = struct.pack('>I', zlib.crc32(c) & 0xffffffff)
            return struct.pack('>I', len(data)) + c + crc

        sig = b'\x89PNG\r\n\x1a\n'
        ihdr = struct.pack('>IIBBBBB', width, height, 8, 6, 0, 0, 0)
        compressed = zlib.compress(raw)
        return sig + chunk(b'IHDR', ihdr) + chunk(b'IDAT', compressed) + chunk(b'IEND', b'')

    for size, name in [(192, 'icon-192.png'), (512, 'icon-512.png')]:
        png_data = make_png(size, size, 217, 70, 239)
        with open(name, 'wb') as f:
            f.write(png_data)
    print('Generated via pure Python PNG')
    generated = True

for f in ['icon-192.png', 'icon-512.png']:
    if os.path.exists(f):
        print(f'{f}: {os.path.getsize(f)} bytes')
    else:
        print(f'{f}: MISSING')

if generated:
    print('DONE_OK')
