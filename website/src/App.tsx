import { useRef, useState } from 'react'
import NeuralCanvas, { Quality } from './NeuralCanvas'
import { useScrollProgress } from './useScrollProgress'

const repo = 'https://github.com/EONASH2722/MORICE'
const androidRelease = `${repo}/releases/tag/v0.8.0-android`
const portableRelease = `${repo}/releases/tag/v0.8.0-portable`
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
  ['07', 'Live Action', 'Talk naturally with interruptible speech, camera context, and the full workspace.'],
  ['08', 'Automatic web context', 'Reach online only when a request needs current information, then fall back locally offline.'],
  ['09', 'Model selection', 'Choose the local model and runtime that fit your machine.'],
  ['10', 'Prompt steering', 'Queue, redirect, cancel, and resume work while MORICE is active.'],
  ['11', 'Desktop native', 'A focused Windows workspace with tools, files, and diagnostics.'],
  ['12', 'Background wake', 'Wake locally by name, a configured magic word, or double-clap without taking focus.'],
  ['13', 'Adaptive execution', 'Match goals to verified tools, device context, and review boundaries before acting.'],
  ['14', 'MORICE Android', 'Carry chat, voice, Live Vision, and approved device controls in a lightweight companion.'],
  ['15', 'Verified Project Mode', 'Detect Unity, Unreal, Roblox, Visual Studio, web, and other toolchains—and report real files, builds, and tests.'],
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
      <a href="#features">Features</a><a href="#visualizations">Visualizations</a><a href="#live-action">Live Action</a><a href="#devices">Devices</a><a href="#privacy">Privacy</a>
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

const contextRoute = [
  ['Local first', 'Checks local knowledge and available tools.'],
  ['Notes when relevant', 'Brings in useful local notes automatically.'],
  ['Web when current', 'Uses source-linked web context when freshness matters.'],
  ['Local fallback offline', 'Keeps working without an internet connection.'],
]

function LiveAction() {
  return <section className="live-action" id="live-action">
    <div className="live-action-inner">
      <div className="live-action-copy">
        <h2>Present when <em>called.</em><br />Quiet when <em>not.</em></h2>
        <p>Say MORICE, use a magic word, or double-clap. Live Action opens without stealing focus.</p>
        <div className="local-listening"><i aria-hidden="true" /><span>Listening locally…</span></div>
        <div className="live-wave" aria-hidden="true">{Array.from({ length: 34 }, (_, i) => <i key={i} style={{ '--i': i, '--h': `${6 + Math.abs(Math.sin(i * .73)) * 29}px` } as React.CSSProperties} />)}</div>
        <div className="camera-privacy"><span aria-hidden="true">▣</span> Camera stays off until you enter Live Action.</div>
      </div>
      <div className="live-stage" aria-label="Live Action camera and voice workspace preview">
        <div className="live-stage-head"><span><i /> Live Action</span><b>—　⌗</b></div>
        <div className="focus-corners" aria-hidden="true"><i/><i/><i/><i/></div>
        <div className="stage-pulse" aria-hidden="true" />
        <div className="voice-dock"><b aria-hidden="true">●</b><span><i /> Listening locally</span><small>Wake word: MORICE</small></div>
      </div>
    </div>
    <div className="context-route" aria-label="Automatic context routing">
      {contextRoute.map(([title, copy], index) => <article key={title} className={index === 0 ? 'active' : ''}>
        <span>{String(index + 1).padStart(2, '0')}</span><div><h3>{title}</h3><p>{copy}</p></div>
      </article>)}
    </div>
  </section>
}

const deviceCapabilities = [
  ['Conversation', 'Continue chat and routed tasks through an enrolled desktop.'],
  ['Voice', 'Opt-in STT with barge-in, ElevenLabs streaming, and Android TTS fallback.'],
  ['Live Vision', 'Front or rear camera, explicit capture, real desktop vision results, and a visible camera indicator.'],
  ['PC control', 'Query system state, open approved apps, and control media through structured encrypted tasks.'],
]

function Devices() {
  return <section className="section devices" id="devices">
    <div className="device-heading"><div><p>MORICE network</p><h2>One intelligence.<br /><em>More than one device.</em></h2></div><p className="device-lede">MORICE Android is a lightweight companion—not a desktop clone. Pair it locally with MORICE Desktop, compare the six-digit code, and grant capabilities per device.</p></div>
    <div className="device-grid">
      <article className="phone-card" aria-label="MORICE Android companion preview">
        <div className="phone-shell"><div className="phone-sensor" /><header><b>M</b><span>MORICE</span><i>Encrypted</i></header><div className="phone-chat"><p><small>YOU</small>How much battery does my PC have?</p><p><small>MORICE</small>Your desktop reports 74%.</p></div><div className="phone-actions"><span>Devices</span><span className="active">Voice</span><span>Vision</span></div><div className="phone-input">Message MORICE… <b>↑</b></div></div>
      </article>
      <div className="device-details">
        {deviceCapabilities.map(([title, copy], index) => <article key={title}><span>{String(index + 1).padStart(2, '0')}</span><div><h3>{title}</h3><p>{copy}</p></div></article>)}
        <div className="security-note"><b>Authenticated by design</b><p>P-256 key agreement, AES-GCM task envelopes, replay protection, time-limited pairing, Android Keystore, Windows DPAPI, and device-scoped grants. A shared Wi-Fi network alone never creates trust.</p></div>
      </div>
    </div>
  </section>
}

function Privacy() {
  return <section className="section privacy" id="privacy">
    <div className="privacy-title"><p>Private by design</p><h2>Your conversations belong<br />on your machine.</h2></div>
    <div className="privacy-split">
      <article><span className="mode-number">01</span><h3>Local processing</h3><strong>Private by default.</strong><p>Your prompts, files, and local model inference stay on the computer you control.</p><ul><li>Works offline</li><li>Local conversation context</li><li>Your model, your hardware</li></ul></article>
      <article><span className="mode-number">02</span><h3>Automatic online context</h3><strong>Only when the answer needs it.</strong><p>MORICE recognizes freshness-sensitive questions, uses source-linked web context when online, and stays local when offline.</p><ul><li>No special command</li><li>Local fallback</li><li>Visible sources</li></ul></article>
    </div>
  </section>
}

function Download() {
  return <section className="download" id="download">
    <div className="download-inner"><div><p>Open source. Local first.</p><h2>Run MORICE<br />your way.</h2><span>Windows 10/11 · Android 9+ · Local GGUF or Ollama</span></div><div className="download-actions"><a className="button primary" href={portableRelease}>Portable plug-and-play <b>↓</b></a><a className="button" href={androidRelease}>Android companion <b>↓</b></a><a className="button" href={repo}>View on GitHub ↗</a><a className="text-link" href={`${repo}/tree/main/docs`}>Read documentation →</a></div></div>
    <div className="finale"><div className="core" aria-hidden="true"><i/><i/><i/><i/><span/></div><h2>Intelligence should<br />feel personal.</h2><a className="button primary" href={`${repo}/releases/latest`}>Download MORICE</a></div>
  </section>
}

export default function App() {
  const [quality, setQuality] = useState<Quality>('auto')
  return <><a className="skip-link" href="#features">Skip cinematic introduction</a><Header quality={quality} setQuality={setQuality} /><main><Hero quality={quality} /><Intro /><Visualizations /><LiveAction /><Devices /><Privacy /><Download /></main><footer><a className="brand" href="#top"><span className="brand-logo-frame" aria-hidden="true"><img className="brand-logo" src="./morice-logo.png" alt="" /></span>MORICE</a><span>Local intelligence, under your control.</span><a href={repo}>GitHub ↗</a></footer></>
}
