// Erzeugt alle App-Icons als PNG aus einer eigenen SVG-Zeichnung (Hantel).
// Keine externen Assets, keine fremden Grafiken. Ausführen: node scripts/make-icons.mjs
import { mkdirSync, writeFileSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { deflateSync } from 'node:zlib'

const outDir = resolve(dirname(fileURLToPath(import.meta.url)), '..', 'public', 'icons')
mkdirSync(outDir, { recursive: true })

/** Minimaler PNG-Encoder (RGBA, 8 bit). */
function encodePng(width, height, rgba) {
  const raw = Buffer.alloc((width * 4 + 1) * height)
  for (let y = 0; y < height; y++) {
    raw[y * (width * 4 + 1)] = 0 // filter: none
    rgba.copy(raw, y * (width * 4 + 1) + 1, y * width * 4, (y + 1) * width * 4)
  }
  const chunks = []
  const chunk = (type, data) => {
    const len = Buffer.alloc(4)
    len.writeUInt32BE(data.length)
    const body = Buffer.concat([Buffer.from(type, 'ascii'), data])
    const crc = Buffer.alloc(4)
    crc.writeUInt32BE(crc32(body) >>> 0)
    chunks.push(len, body, crc)
  }
  const ihdr = Buffer.alloc(13)
  ihdr.writeUInt32BE(width, 0)
  ihdr.writeUInt32BE(height, 4)
  ihdr[8] = 8 // bit depth
  ihdr[9] = 6 // color type RGBA
  chunk('IHDR', ihdr)
  chunk('IDAT', deflateSync(raw, { level: 9 }))
  chunk('IEND', Buffer.alloc(0))
  return Buffer.concat([Buffer.from([137, 80, 78, 71, 13, 10, 26, 10]), ...chunks])
}

const CRC_TABLE = (() => {
  const t = new Int32Array(256)
  for (let n = 0; n < 256; n++) {
    let c = n
    for (let k = 0; k < 8; k++) c = c & 1 ? 0xedb88320 ^ (c >>> 1) : c >>> 1
    t[n] = c
  }
  return t
})()
function crc32(buf) {
  let c = -1
  for (let i = 0; i < buf.length; i++) c = CRC_TABLE[(c ^ buf[i]) & 0xff] ^ (c >>> 8)
  return c ^ -1
}

/** Zeichnet das Hantel-Symbol als Pixelraster (Vektor-Rechtecke, 4x supersampled). */
function drawIcon(size, { maskable }) {
  const ss = 4
  const S = size * ss
  const px = Buffer.alloc(size * size * 4)
  const acc = new Float64Array(size * size * 4)

  // Logische Zeichenfläche: 100x100. Bei maskable etwas kleiner (Safe Zone).
  const inset = maskable ? 0.72 : 0.86
  const toS = (v) => (v / 100 - 0.5) * inset * S + S / 2

  // Bar (Stange) + 4 Scheiben — eigene, simple Geometrie.
  const rects = [
    // Stange
    { x0: 14, y0: 46, x1: 86, y1: 54, r: 4, c: [255, 255, 255] },
    // innere Scheiben
    { x0: 26, y0: 30, x1: 38, y1: 70, r: 5, c: [255, 255, 255] },
    { x0: 62, y0: 30, x1: 74, y1: 70, r: 5, c: [255, 255, 255] },
    // äußere Scheiben
    { x0: 12, y0: 38, x1: 22, y1: 62, r: 4, c: [120, 122, 128] },
    { x0: 78, y0: 38, x1: 88, y1: 62, r: 4, c: [120, 122, 128] },
  ]

  const bg = maskable ? [0, 0, 0] : [10, 10, 12]
  for (let y = 0; y < S; y++) {
    for (let x = 0; x < S; x++) {
      let col = bg
      // Abgerundeter dunkler Hintergrund für nicht-maskable Icons
      if (!maskable) {
        const r = S * 0.22
        const inCorner =
          (x < r && y < r && (x - r) ** 2 + (y - r) ** 2 > r * r) ||
          (x > S - r && y < r && (x - (S - r)) ** 2 + (y - r) ** 2 > r * r) ||
          (x < r && y > S - r && (x - r) ** 2 + (y - (S - r)) ** 2 > r * r) ||
          (x > S - r && y > S - r && (x - (S - r)) ** 2 + (y - (S - r)) ** 2 > r * r)
        if (inCorner) {
          const i = ((y / ss) | 0) * size * 4 + (((x / ss) | 0) * 4)
          acc[i + 3] += 0 // transparent
          continue
        }
      }
      for (const rc of rects) {
        const x0 = toS(rc.x0)
        const y0 = toS(rc.y0)
        const x1 = toS(rc.x1)
        const y1 = toS(rc.y1)
        const rr = (rc.r / 100) * inset * S
        const cx = Math.min(Math.max(x, x0 + rr), x1 - rr)
        const cy = Math.min(Math.max(y, y0 + rr), y1 - rr)
        if ((x - cx) ** 2 + (y - cy) ** 2 <= rr * rr) col = rc.c
      }
      const i = ((y / ss) | 0) * size * 4 + ((x / ss) | 0) * 4
      acc[i] += col[0]
      acc[i + 1] += col[1]
      acc[i + 2] += col[2]
      acc[i + 3] += 255
    }
  }
  const n = ss * ss
  for (let i = 0; i < size * size; i++) {
    const a = acc[i * 4 + 3] / n
    // Farben sind bereits über die abgedeckten Subpixel gemittelt
    const cover = a / 255 || 1
    px[i * 4] = Math.round(acc[i * 4] / n / cover)
    px[i * 4 + 1] = Math.round(acc[i * 4 + 1] / n / cover)
    px[i * 4 + 2] = Math.round(acc[i * 4 + 2] / n / cover)
    px[i * 4 + 3] = Math.round(a)
  }
  return encodePng(size, size, px)
}

const targets = [
  ['icon-192.png', 192, { maskable: false }],
  ['icon-512.png', 512, { maskable: false }],
  ['icon-maskable-512.png', 512, { maskable: true }],
  ['apple-touch-icon.png', 180, { maskable: true }], // iOS maskiert selbst -> voller Hintergrund
]
for (const [name, size, opts] of targets) {
  writeFileSync(resolve(outDir, name), drawIcon(size, opts))
  console.log('icon:', name, size)
}

writeFileSync(
  resolve(outDir, 'favicon.svg'),
  `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100">
  <rect width="100" height="100" rx="22" fill="#0a0a0c"/>
  <g fill="#fff">
    <rect x="14" y="46" width="72" height="8" rx="4"/>
    <rect x="26" y="30" width="12" height="40" rx="5"/>
    <rect x="62" y="30" width="12" height="40" rx="5"/>
  </g>
  <g fill="#7a7c80">
    <rect x="12" y="38" width="10" height="24" rx="4"/>
    <rect x="78" y="38" width="10" height="24" rx="4"/>
  </g>
</svg>
`,
)
console.log('icon: favicon.svg')
