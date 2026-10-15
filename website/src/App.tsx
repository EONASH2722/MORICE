import { useEffect, useState } from 'react'

const repo = 'https://github.com/EONASH2722/MORICE'
const sourceVersion = '0.9.2'
const workspaces = [
  { name: 'Core', icon: 'core', image: `morice-home.png?v=${sourceVersion}`, title: 'A calmer place to begin.', copy: 'A luminous Core, a compact composer, and the tools you need within reach.' },
  { name: 'Spatial', icon: 'globe', image: `morice-spatial.png?v=${sourceVersion}`, title: 'Real places. Deterministic answers.', copy: 'Explore Earth, resolve locations offline, and compare WGS84 surface and through-Earth distances.' },
  { name: 'Research', icon: 'research', image: `morice-research.png?v=${sourceVersion}`, title: 'Keep evidence close to the question.', copy: 'Inspect provenance, run controlled computations, and pause or resume experiments without losing results.' },
  { name: 'Media', icon: 'image', image: `morice-media.png?v=${sourceVersion}`, title: 'A local studio, with clear limits.', copy: 'Choose compatible local models, review the queue, and inspect verified artifacts. Generation depends on installed models and available resources.' },
] as const

// Every pictogram is authored for this site; no icon pack or icon font.
const marks: Record<string, string> = {
  core: 'M12 8a4 4 0 1 0 0 8 4 4 0 0 0 0-8M3 12c0-4 18-4 18 0s-18 4-18 0M12 3c4 0 4 18 0 18s-4-18 0-18',
  globe: 'M12 3a9 9 0 1 0 0 18 9 9 0 0 0 0-18M3 12h18M12 3c5 5 5 13 0 18-5-5-5-13 0-18M5 7h14M5 17h14',
  research: 'M9 3h6M10 3v6l-5 9a2 2 0 0 0 2 3h10a2 2 0 0 0 2-3l-5-9V3M8 14h8M10 17h.1M14 18h.1',
  image: 'M5 4h14a1 1 0 0 1 1 1v14a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V5a1 1 0 0 1 1-1M4 16l5-5 4 4 3-3 4 5M15 7h.1',
  code: 'M8 6l-6 6 6 6M16 6l6 6-6 6M14 3l-4 18',
  shield: 'M12 2l8 4v6c0 5-5 8-8 10-3-2-8-5-8-10V6l8-4M8 12l3 3 5-6',
  voice: 'M9 4a3 3 0 0 1 6 0v8a3 3 0 0 1-6 0V4M5 10v2a7 7 0 0 0 14 0v-2M12 19v3M8 22h8',
  devices: 'M3 4h12v10H3V4M7 18h5M9 14v4M17 8h5v13h-5V8M19 18h1',
  arrow: 'M4 12h15M13 6l6 6-6 6',
  download: 'M12 3v12M7 10l5 5 5-5M4 16v5h16v-5',
  branch: 'M6 3v13a4 4 0 0 0 4 4h8M6 6h9a3 3 0 0 0 3-3M4 3h4M16 3h4M16 20h4',
  motion: 'M3 7h9M3 12h5M3 17h9M16 5l5 7-5 7V5',
  pause: 'M8 4v16M16 4v16',
  palette: 'M12 3a9 9 0 1 0 0 18h2a2 2 0 0 0 2-2c0-2-3-2-3-4s3-2 5-2c4 0 3-10-6-10M7 8h.1M12 6h.1M17 8h.1M6 13h.1',
}
function Mark({ name }: { name: string }) {
  return <svg className="mark" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.55" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d={marks[name] ?? marks.core} /></svg>
}
function Brand() {
  return <a className="brand" href="#top" aria-label="MORICE home"><img src="./morice-logo.png" alt="" width="34" height="34" /><span>MORICE</span></a>
}
function Core({ motion, theme }: { motion: boolean; theme: string }) {
  const petals = Array.from({ length: 12 }, (_, i) => i)
  return <div className={`core-preview ${motion ? '' : 'still'}`} aria-hidden="true"><div className="core-aura" />
    {theme === 'midnight' ? <>{[0, 1, 2].map(i => <div className={`orbit-plane plane-${i}`} key={i}><div className="orbit-float"><div className="orbit-ring"><i /></div></div></div>)}<svg className="scene-motif star-atlas" viewBox="0 0 400 400">{petals.map(i => <circle key={i} cx={200 + 164 * Math.cos(i * Math.PI / 6)} cy={200 + 130 * Math.sin(i * Math.PI / 6)} r={i % 3 === 0 ? 2.5 : 1.3} />)}</svg></> :
      <svg className={`scene-motif motif-${theme}`} viewBox="0 0 400 400" fill="none" stroke="currentColor" strokeWidth="1">
        {theme === 'glass' ? [0,1,2,3].map(i => <g className={`facet facet-${i}`} key={i}><polygon points="200,50 324,152 276,300 122,316 58,148" transform={`translate(200 200) rotate(${i*37}) scale(${.45+i*.15}) translate(-200 -200)`} /><path d="M90 130L270 96M132 260L296 188" /></g>) :
          theme === 'ice' ? petals.filter(i => i % 2 === 0).map(i => <g className="frost-arm" key={i} transform={`rotate(${i*30} 200 200)`}><path d="M200 200V42M200 78L172 101M200 78L228 101M200 116L158 151M200 116L242 151M200 158L172 180M200 158L228 180" /><path d="M200 44L214 68L200 92L186 68Z" /></g>) : petals.map(i => <path className="solar-filament" key={i} d="M200 84C142 126 156 176 200 200C244 176 258 126 200 84Z" transform={`rotate(${i*30} 200 200)`} />)}
      </svg>}
    <div className="core-light" /><div className="core-centre" /></div>
}

export default function App() {
  const [selected, setSelected] = useState(0)
  const [theme, setTheme] = useState('midnight')
  const [motion, setMotion] = useState(() => !matchMedia('(prefers-reduced-motion: reduce)').matches)
  const [visible, setVisible] = useState(() => !document.hidden)
  const workspace = workspaces[selected]
  useEffect(() => {
    const changed = () => setVisible(!document.hidden)
    const media = matchMedia('(prefers-reduced-motion: reduce)')
    const reduced = () => { if (media.matches) setMotion(false) }
    document.addEventListener('visibilitychange', changed); media.addEventListener('change', reduced)
    return () => { document.removeEventListener('visibilitychange', changed); media.removeEventListener('change', reduced) }
  }, [])
  return <div className={`site-shell ${theme}`}>
    <a className="skip-link" href="#workspace">Skip to the workspace</a>
    <header className="site-header"><Brand /><nav aria-label="Main navigation"><a href="#workspace">Workspace</a><a href="#capabilities">Capabilities</a><a href="#privacy">Your control</a><a href={`${repo}/tree/main/docs`}>Docs</a></nav><a className="button compact" href={repo}><Mark name="branch" />Source</a></header>
    <main>
      <section className="hero" id="top">
        <div className="hero-copy"><p className="eyebrow">PRIVATE INTELLIGENCE · A NEW WORKSPACE</p><h1>Think clearly.<br />Build freely.<br /><em>Stay in control.</em></h1><p className="hero-description">Meet the renovated MORICE. A calmer home for local AI, meaningful tools, and work you can inspect.</p><div className="hero-actions"><a className="button primary" href="#workspace">Explore the workspace<Mark name="arrow" /></a><a className="text-link" href="#get">Run MORICE</a></div><p className="release-note">Current source {sourceVersion} · Windows desktop preview</p></div>
        <div className="hero-art"><div className="art-grid" /><Core motion={motion && visible} theme={theme} /><div className="core-caption"><span className="small-label">MORICE CORE</span><p>Room for your next idea.</p><span className="preview-label">{({midnight:'Star atlas',ice:'Crystal bloom',solar:'Solar corona',glass:'Prismatic glass'} as Record<string,string>)[theme]} · Visual preview</span></div><div className="appearance-controls"><div className="palette-controls" aria-label="Website theme and animation">{['midnight', 'ice', 'solar', 'glass'].map(name => <button key={name} className={`swatch swatch-${name}`} aria-label={`${name} theme`} aria-pressed={theme === name} onClick={() => setTheme(name)}><Mark name="palette" /></button>)}</div><button className="motion-control" aria-pressed={motion} onClick={() => setMotion(value => !value)}><Mark name={motion ? 'pause' : 'motion'} />{motion ? 'Pause motion' : 'Enable motion'}</button></div></div>
      </section>
      <section className="section workspace-section" id="workspace"><div className="section-head"><p className="eyebrow">ONE HOME. MANY WAYS TO WORK.</p><h2>A little less noise.<br /><em>A lot more possibility.</em></h2><p>Move between focused spaces while the same execution, permission, and verification systems keep your work grounded.</p></div><div className="workspace-tabs" role="tablist" aria-label="Desktop workspace captures">{workspaces.map((item, index) => <button key={item.name} id={`tab-${index}`} role="tab" aria-selected={selected === index} aria-controls="workspace-panel" tabIndex={selected === index ? 0 : -1} onClick={() => setSelected(index)} onKeyDown={event => { if (event.key === 'ArrowRight' || event.key === 'ArrowLeft') { event.preventDefault(); const next = (selected + (event.key === 'ArrowRight' ? 1 : -1) + workspaces.length) % workspaces.length; setSelected(next); document.getElementById(`tab-${next}`)?.focus() } }}><Mark name={item.icon} />{item.name}</button>)}</div><article className="workspace-panel" id="workspace-panel" role="tabpanel" aria-labelledby={`tab-${selected}`}><div className="capture-bar"><span><Mark name={workspace.icon} />{workspace.name}</span><span>Actual desktop capture</span></div><img key={workspace.image} src={`./${workspace.image}`} alt={`MORICE ${workspace.name} workspace captured from the native desktop app`} width="1708" height="1050" loading="lazy" /><div className="capture-copy"><h3>{workspace.title}</h3><p>{workspace.copy}</p></div></article></section>
      <section className="section" id="capabilities"><div className="section-head compact-head"><p className="eyebrow">TOOLS WITH A PURPOSE</p><h2>From a question<br />to something <em>you can use.</em></h2></div><div className="capability-grid">{[
        ['code', 'Build, test, review.', 'Projects keep plans, files, terminal output and verification together. Review proposed changes before applying them.'],
        ['research', 'Follow the evidence.', 'Research tracks provenance and distinguishes supplied data, computed results and unverified interpretations.'],
        ['globe', 'Explore your world.', 'Offline city search and deterministic geography support real locations, bearings, paths and distance comparisons.'],
        ['image', 'Make space for creativity.', 'Media Lab exposes installed model capabilities, actual queue states, resource limits and verified outputs.'],
        ['voice', 'Present when called.', 'Opt-in wake and voice use existing speech services. Camera capture stays explicit; model and device availability remain visible.'],
        ['devices', 'Connect with intent.', 'Pair explicitly, compare codes, scope trust and verify transfers. Shared Wi-Fi alone creates no trust.'],
      ].map(([icon, title, copy]) => <article className="capability-card" key={title}><Mark name={icon} /><h3>{title}</h3><p>{copy}</p></article>)}</div></section>
      <section className="section trust-section" id="privacy"><div className="trust-visual" aria-hidden="true"><Mark name="shield" /><span className="trust-orbit" /></div><div className="trust-copy"><p className="eyebrow">YOUR MACHINE. YOUR BOUNDARIES.</p><h2>Capability comes<br />with <em>accountability.</em></h2><p>Local models can keep inference on your device. Online search and optional providers have their own availability and permission boundaries. A requested action becomes success only when the relevant verification succeeds.</p><ul><li>One shared runtime, with bounded workers and resource leases.</li><li>Explicit camera, microphone, file, device and connector access.</li><li>Visible provenance, cancellation and recovery limits.</li><li>Reduced Motion, adaptive visual quality and authored interface icons.</li></ul><a className="text-link" href={`${repo}/tree/main/docs`}>Read the architecture and constraints<Mark name="arrow" /></a></div></section>
      <section className="section get-section" id="get"><div><p className="eyebrow">OPEN SOURCE. LOCAL FIRST.</p><h2>Make it<br /><em>your workspace.</em></h2><p>Download the renovated Windows desktop preview or build it from source. Model inference needs compatible local runtimes, installed weights and enough available RAM/VRAM. Physical-device and provider validation remains scoped in the audit reports.</p></div><div className="get-options"><a className="get-card featured" href={`${repo}/releases/tag/v${sourceVersion}`}><Mark name="download" /><span><strong>Windows preview · {sourceVersion}</strong><small>Updated app, documentation and verified checksums</small></span><Mark name="arrow" /></a><a className="get-card" href={`${repo}#installation`}><Mark name="code" /><span><strong>Build current source · {sourceVersion}</strong><small>Python packages or local development setup</small></span><Mark name="arrow" /></a><a className="get-card" href={`${repo}/releases/tag/v0.8.0-android`}><Mark name="devices" /><span><strong>Published Android · 0.8.0</strong><small>Earlier companion release; physical hardware checks are separate</small></span><Mark name="arrow" /></a><p className="availability-note">This website is a product overview. Its Core animation is decorative; it does not record audio, start a model, or represent a live task.</p></div></section>
    </main><footer><Brand /><p>Intelligence, under your control.</p><a className="text-link" href={repo}>View the repository<Mark name="arrow" /></a></footer>
  </div>
}
