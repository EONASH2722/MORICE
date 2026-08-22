import { useEffect, useRef } from 'react'

export type Quality = 'auto' | 'high' | 'medium' | 'low'

function resolvedQuality(value: Quality) {
  if (value !== 'auto') return value
  const memory = (navigator as Navigator & { deviceMemory?: number }).deviceMemory ?? 4
  if (matchMedia('(prefers-reduced-motion: reduce)').matches || innerWidth < 680 || memory <= 2) return 'low'
  if (innerWidth < 1100 || memory <= 4) return 'medium'
  return 'high'
}

export default function NeuralCanvas({ progress, quality }: { progress: number; quality: Quality }) {
  const canvasRef = useRef<HTMLCanvasElement>(null)

  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas) return
    const context = canvas.getContext('2d')
    if (!context) return
    const mode = resolvedQuality(quality)
    const count = mode === 'high' ? 180 : mode === 'medium' ? 110 : 56
    let width = 0
    let height = 0
    let raf = 0
    let active = true

    const resize = () => {
      const dpr = Math.min(devicePixelRatio, mode === 'high' ? 1.7 : 1.2)
      width = innerWidth
      height = innerHeight
      canvas.width = width * dpr
      canvas.height = height * dpr
      canvas.style.width = `${width}px`
      canvas.style.height = `${height}px`
      context.setTransform(dpr, 0, 0, dpr, 0, 0)
    }

    const draw = () => {
      if (!active) return
      context.clearRect(0, 0, width, height)
      const cx = width * (0.55 + progress * 0.03)
      const cy = height * 0.5
      const travel = progress * 920
      const core = Math.max(0, (progress - 0.72) / 0.28)

      const glow = context.createRadialGradient(cx, cy, 0, cx, cy, Math.max(width, height) * .68)
      glow.addColorStop(0, `rgba(64, 179, 255, ${0.04 + core * 0.18})`)
      glow.addColorStop(.28, `rgba(106, 72, 255, ${0.035 + core * 0.08})`)
      glow.addColorStop(1, 'rgba(2, 3, 7, 0)')
      context.fillStyle = glow
      context.fillRect(0, 0, width, height)

      const points: Array<[number, number, number]> = []
      for (let i = 0; i < count; i++) {
        const z = ((i * 89 + travel) % 1000) / 1000
        const angle = i * 2.399 + progress * 0.9
        const radius = (0.09 + ((i * 47) % 100) / 100) * Math.min(width, height) * (0.16 + z * .76)
        const x = cx + Math.cos(angle) * radius * (width / Math.max(height, 600))
        const y = cy + Math.sin(angle) * radius
        points.push([x, y, z])
      }
      for (let i = 0; i < points.length; i++) {
        const [x, y, z] = points[i]
        const next = points[(i + 13) % points.length]
        if (Math.hypot(x - next[0], y - next[1]) < Math.min(width, height) * .28) {
          context.beginPath()
          context.moveTo(x, y)
          context.lineTo(next[0], next[1])
          context.strokeStyle = `rgba(${i % 4 ? '111, 202, 255' : '162, 119, 255'}, ${.025 + z * .1})`
          context.lineWidth = .55
          context.stroke()
        }
        context.beginPath()
        context.arc(x, y, .45 + z * 1.55, 0, Math.PI * 2)
        context.fillStyle = `rgba(${i % 5 ? '157, 221, 255' : '181, 137, 255'}, ${.24 + z * .62})`
        context.fill()
      }

      if (core > 0) {
        const radius = 38 + core * Math.min(width, height) * .17
        context.save()
        context.translate(cx, cy)
        context.rotate(progress * .45)
        for (let ring = 0; ring < 7; ring++) {
          context.beginPath()
          context.ellipse(0, 0, radius, radius * (.3 + ring * .09), ring * .42, 0, Math.PI * 2)
          context.strokeStyle = `rgba(${ring % 2 ? '135, 107, 255' : '107, 211, 255'}, ${.16 + core * .34})`
          context.lineWidth = .7
          context.stroke()
        }
        context.restore()
      }
      raf = requestAnimationFrame(draw)
    }
    resize()
    draw()
    addEventListener('resize', resize)
    return () => {
      active = false
      cancelAnimationFrame(raf)
      removeEventListener('resize', resize)
    }
  }, [progress, quality])

  return <canvas ref={canvasRef} className="neural-canvas" aria-hidden="true" />
}
