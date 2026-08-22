import { useRef, useState } from 'react'
import NeuralCanvas, { Quality } from './NeuralCanvas'
import { useScrollProgress } from './useScrollProgress'

const repo = 'https://github.com/EONASH2722/MORICE'
const statements = [
  'MORICE does not simply answer.',
  'It thinks beside you.',
  'Private by design.',
  'Powerful without the cloud.',
  'Build. Visualize. Simulate.',
  'Your intelligence. Your machine.',
  'Meet MORICE.',
]

const features = [
  ['01', 'Offline local AI', 'Run GGUF or Ollama models without sending every thought away.'],
  ['02', 'Private conversations', 'Keep local conversations and context on your own machine.'],
  ['03', 'Project creation', 'Build files and projects through a reviewable, validated workflow.'],
  ['04', 'Interactive graphs', 'Pan, zoom, inspect, reset, and export real mathematical plots.'],
  ['05', 'Scientific visuals', 'Explore chemistry, biology, data structures, and diagrams.'],
  ['06', 'Physics simulations', 'Run particles, waves, pendulums, orbits, and dynamic systems.'],
  ['07', 'Voice activation', 'Move into a hands-free workspace with interruptible speech.'],
  ['08', 'Optional web lookup', 'Reach online only when the task needs current information.'],
  ['09', 'Model selection', 'Choose the local model and runtime that fit your machine.'],
  ['10', 'Prompt steering', 'Queue, redirect, cancel, and resume work while MORICE is active.'],
  ['11', 'Desktop native', 'A focused Windows workspace with tools, files, and diagnostics.'],
]

const showcase = {
  Graph: ['A mathematical graph takes shape.', 'graph'],
  Simulation: ['A particle system responds in real time.', 'simulation'],
  Code: ['A project grows from a reviewed plan.', 'code'],
  Voice: ['Your voice becomes a private local command.', 'voice'],
} as const

function Header({ quality, setQuality }: { quality: Quality; setQuality: (q: Quality) => void }) {
  return <header className="site-header">
    <a className="brand" href="#top" aria-label="MORICE home"><span className="brand-logo-frame" aria-hidden="true"><img className="brand-logo" src="./morice-logo.png" alt="" /></span><span>MORICE</span></a>
    <nav aria-label="Main navigation">
      <a href="#features">Features</a><a href="#visualizations">Visualizations</a><a href="#privacy">Privacy</a>
      <a href={`${repo}/tree/main/docs`}>Documentation</a><a href={repo}>GitHub</a>
    </nav>
    <div className="header-actions">
      <label className="quality"><span>Visuals</span><select value={quality} onChange={(e) => setQuality(e.target.value as Quality)} aria-label="Visual quality"><option value="auto">Auto</option><option value="high">High</option><option value="medium">Medium</option><option value="low">Low</option></select></label>
      <a className="button small" href={`${repo}/releases/latest`}>Download</a>
    </div>
  </header>
}

function Hero({ quality }: { quality: Quality }) {
  const ref = useRef<HTMLElement>(null)
  const progress = useScrollProgress(ref)
  return <section id="top" className="hero" ref={ref} aria-label="MORICE introduction">
    <div className="hero-sticky">
      <NeuralCanvas progress={progress} quality={quality} />
      <div className="vignette" />
      <div className="statements" aria-live="polite">
        {statements.map((text, index) => {
          const center = index / (statements.length - 1)
          const delta = (progress - center) * (statements.length - 1)
          const opacity = Math.max(0, 1 - Math.abs(delta) * 1.55)
          return <h1 key={text} style={{ opacity, transform: `translate3d(0, ${delta * -48}px, 0)`, filter: `blur(${Math.min(10, Math.abs(delta) * 6)}px)` }}>{text}</h1>
        })}
      </div>
      <div className="scroll-cue" style={{ opacity: Math.max(0, 1 - progress * 8) }}><span />Scroll to enter</div>
      <div className="chapter">{String(Math.min(7, Math.floor(progress * 7) + 1)).padStart(2, '0')} / 07</div>
    </div>
  </section>
}

function Intro() {
  return <section className="section intro" id="features">
    <div className="section-heading"><p>Built for your machine</p><h2>AI that stays close.</h2><span>MORICE is a private desktop AI workspace built to reason, create, and explore locally—while keeping you in control of when it reaches beyond your device.</span></div>
    <div className="feature-rail">
      {features.map(([number, title, copy]) => <article key={number}><b>{number}</b><h3>{title}</h3><p>{copy}</p></article>)}
    </div>
  </section>
}

function Visualizations() {
  const [mode, setMode] = useState<keyof typeof showcase>('Graph')
  return <section className="section visualization" id="visualizations">
    <div className="stage-copy"><p>Inside the workspace</p><h2>Ideas become visible.</h2><span>{showcase[mode][0]}</span></div>
    <div className="stage">
      <div className="mode-tabs" role="tablist" aria-label="Visualization examples">
        {(Object.keys(showcase) as Array<keyof typeof showcase>).map((item) => <button role="tab" aria-selected={mode === item} onClick={() => setMode(item)} key={item}>{item}</button>)}
      </div>
      <div className={`demo demo-${showcase[mode][1]}`}>
        {mode === 'Graph' && <svg viewBox="0 0 900 330" role="img" aria-label="Animated wave graph"><path className="axis" d="M30 165H870M450 20V310"/><path className="wave one" d="M30 165 C110 10 150 320 230 165 S350 10 430 165 S550 320 630 165 S750 10 870 165"/><path className="wave two" d="M30 165 C90 80 130 250 190 165 S290 80 350 165 S450 250 510 165 S610 80 670 165 S770 250 870 165"/></svg>}
        {mode === 'Simulation' && <div className="orbits">{Array.from({ length: 18 }, (_, i) => <i key={i} style={{ '--i': i } as React.CSSProperties} />)}</div>}
        {mode === 'Code' && <pre><code><em>project</em> MORICE-Lab{`\n`}├── src/simulation.py{`\n`}├── src/renderer.ts{`\n`}├── tests/test_motion.py{`\n`}└── README.md{`\n\n`}<strong>✓</strong> 18 checks passed</code></pre>}
        {mode === 'Voice' && <div className="waveform">{Array.from({ length: 48 }, (_, i) => <i key={i} style={{ '--i': i, '--h': `${22 + Math.abs(Math.sin(i * .62)) * 118}px` } as React.CSSProperties} />)}</div>}
      </div>
      <img className="product-shot" src="./morice-home.png" alt="MORICE desktop workspace showing a local conversation" loading="lazy" />
    </div>
  </section>
}

function Privacy() {
  return <section className="section privacy" id="privacy">
    <div className="privacy-title"><p>Private by design</p><h2>Your conversations belong<br />on your machine.</h2></div>
    <div className="privacy-split">
      <article><span className="mode-number">01</span><h3>Local processing</h3><strong>Private by default.</strong><p>Your prompts, files, and local model inference stay on the computer you control.</p><ul><li>Works offline</li><li>Local conversation context</li><li>Your model, your hardware</li></ul></article>
      <article><span className="mode-number">02</span><h3>Optional online lookup</h3><strong>Only when you choose.</strong><p>Use online context for current information without making the cloud your default workspace.</p><ul><li>Explicit opt-in</li><li>Permission-aware tools</li><li>Visible activity</li></ul></article>
    </div>
  </section>
}

function Download() {
  return <section className="download" id="download">
    <div className="download-inner"><div><p>Open source. Local first.</p><h2>Run MORICE on<br />your machine.</h2><span>Windows 10/11 · Python 3.12+ · Local GGUF or Ollama</span></div><div className="download-actions"><a className="button primary" href={`${repo}/releases/latest`}>Download MORICE <b>↓</b></a><a className="button" href={repo}>View on GitHub ↗</a><a className="text-link" href={`${repo}/tree/main/docs`}>Read documentation →</a></div></div>
    <div className="finale"><div className="core" aria-hidden="true"><i/><i/><i/><i/><span/></div><h2>Intelligence should<br />feel personal.</h2><a className="button primary" href={`${repo}/releases/latest`}>Download MORICE</a></div>
  </section>
}

export default function App() {
  const [quality, setQuality] = useState<Quality>('auto')
  return <><a className="skip-link" href="#features">Skip cinematic introduction</a><Header quality={quality} setQuality={setQuality} /><main><Hero quality={quality} /><Intro /><Visualizations /><Privacy /><Download /></main><footer><a className="brand" href="#top"><span className="brand-logo-frame" aria-hidden="true"><img className="brand-logo" src="./morice-logo.png" alt="" /></span>MORICE</a><span>Local intelligence, under your control.</span><a href={repo}>GitHub ↗</a></footer></>
}
