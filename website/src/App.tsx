import { useEffect, useRef, useState } from "react";
import type { CSSProperties } from "react";
import { ArrowDown } from "@phosphor-icons/react/dist/csr/ArrowDown";
import { ArrowRight } from "@phosphor-icons/react/dist/csr/ArrowRight";
import { ArrowUpRight } from "@phosphor-icons/react/dist/csr/ArrowUpRight";
import { Code } from "@phosphor-icons/react/dist/csr/Code";
import { Desktop } from "@phosphor-icons/react/dist/csr/Desktop";
import { DownloadSimple } from "@phosphor-icons/react/dist/csr/DownloadSimple";
import { GithubLogo } from "@phosphor-icons/react/dist/csr/GithubLogo";
import { List } from "@phosphor-icons/react/dist/csr/List";
import { Pause } from "@phosphor-icons/react/dist/csr/Pause";
import { Play } from "@phosphor-icons/react/dist/csr/Play";
import { ShieldCheck } from "@phosphor-icons/react/dist/csr/ShieldCheck";
import { Sparkle } from "@phosphor-icons/react/dist/csr/Sparkle";
import { X } from "@phosphor-icons/react/dist/csr/X";
import HeroScene from "./HeroScene";
import CustomCursor from "./CustomCursor";

const repo = "https://github.com/EONASH2722/MORICE";
const version = "0.12.0";
const release = `${repo}/releases/tag/v${version}`;
const workspaces = [
  {
    name: "Core",
    label: "A space to think.",
    image: "morice-home.png",
    copy: "Conversation, local intelligence, and a living globe. Your starting point for whatever comes next.",
    tag: "YOUR PERSONAL WORKSPACE",
  },
  {
    name: "Projects",
    label: "An idea. Then a reality.",
    image: "morice-projects.png",
    copy: "Go from a request to real files. Plan a change, review the proposal, and keep your code and checks in one place.",
    tag: "BUILD SOMETHING THAT MATTERS",
  },
  {
    name: "Research",
    label: "Follow your curiosity.",
    image: "morice-research.png",
    copy: "Explore questions, run supported computations, and inspect the evidence behind your results.",
    tag: "THINK A LITTLE DEEPER",
  },
  {
    name: "Spatial",
    label: "A world to explore.",
    image: "morice-spatial.png",
    copy: "Find real places, resolve ambiguous locations, and compare distances between verified coordinates.",
    tag: "SEE THE BIGGER PICTURE",
  },
  {
    name: "Media",
    label: "Make the imagined real.",
    image: "morice-media.png",
    copy: "Generate and edit images with compatible installed providers. Keep the idea, the process, and the output together.",
    tag: "GIVE YOUR IDEAS A FORM",
  },
  {
    name: "Security Lab",
    label: "Trust the evidence.",
    image: "morice-security-lab.png",
    copy: "Inspect local files, review source, and verify supported recovery with supplied passwords or keys. Every result comes with evidence.",
    tag: "INSPECT. UNDERSTAND. VERIFY.",
  },
] as const;

function Brand() {
  return (
    <a href="#top" className="brand" aria-label="MORICE home">
      <img src="./morice-logo.png" width="42" height="42" alt="" />
      <span>
        MORICE<span className="brand-period">.</span>
      </span>
    </a>
  );
}

export default function App() {
  const [motion, setMotion] = useState(
    () => !matchMedia("(prefers-reduced-motion: reduce)").matches,
  );
  const [menuOpen, setMenuOpen] = useState(false);
  const [selected, setSelected] = useState(0);
  const menuButton = useRef<HTMLButtonElement>(null);
  const workspace = workspaces[selected];

  useEffect(() => {
    const media = matchMedia("(prefers-reduced-motion: reduce)");
    const change = () => setMotion(!media.matches);
    media.addEventListener("change", change);
    const observer = new IntersectionObserver(
      (entries) =>
        entries.forEach((entry) => {
          if (entry.isIntersecting) {
            entry.target.classList.add("is-visible");
            observer.unobserve(entry.target);
          }
        }),
      { threshold: 0.12 },
    );
    document
      .querySelectorAll("[data-reveal]")
      .forEach((el) => observer.observe(el));
    return () => {
      media.removeEventListener("change", change);
      observer.disconnect();
    };
  }, []);

  useEffect(() => {
    const close = (event: KeyboardEvent) => {
      if (event.key === "Escape" && menuOpen) {
        setMenuOpen(false);
        menuButton.current?.focus();
      }
    };
    const desktop = matchMedia("(min-width: 901px)");
    const resize = () => {
      if (desktop.matches) setMenuOpen(false);
    };
    document.addEventListener("keydown", close);
    desktop.addEventListener("change", resize);
    return () => {
      document.removeEventListener("keydown", close);
      desktop.removeEventListener("change", resize);
    };
  }, [menuOpen]);

  const switchWorkspace = (index: number, focus = false) => {
    setSelected(index);
    if (focus) document.getElementById(`workspace-tab-${index}`)?.focus();
  };

  return (
    <div className={`site-shell ${motion ? "" : "motion-paused"}`}>
      <CustomCursor motion={motion} />
      <a className="skip-link" href="#workspace">
        Skip to content
      </a>
      <header className="site-header">
        <div className="header-inner">
          <Brand />
          <nav
            id="main-nav"
            className={menuOpen ? "nav-open" : ""}
            aria-label="Main navigation"
          >
            <a href="#workspace" onClick={() => setMenuOpen(false)}>
              Workspace
            </a>
            <a href="#explore" onClick={() => setMenuOpen(false)}>
              Explore
            </a>
            <a href="#principles" onClick={() => setMenuOpen(false)}>
              Our approach
            </a>
            <a href={`${repo}/tree/main/docs`}>
              Documentation
              <ArrowUpRight size={12} />
            </a>
            <a href="#download" onClick={() => setMenuOpen(false)}>
              Download
            </a>
            <a href={repo} className="nav-github">
              <GithubLogo size={18} />
              GitHub
            </a>
          </nav>
          <button
            ref={menuButton}
            className="menu-toggle"
            aria-expanded={menuOpen}
            aria-controls="main-nav"
            aria-label={menuOpen ? "Close navigation" : "Open navigation"}
            onClick={() => setMenuOpen(!menuOpen)}
          >
            {menuOpen ? <X size={24} /> : <List size={24} />}
          </button>
        </div>
      </header>
      <main>
        <section className="hero" id="top" aria-labelledby="hero-title">
          <a className="release-badge" href={release}>
            <span />
            MORICE {version}
            <span className="badge-divider" />
            UNLEASHED
            <ArrowUpRight size={12} />
          </a>
          <div className="hero-scene">
            <HeroScene motion={motion} />
            <h1 id="hero-title">MORICE</h1>
          </div>
          <div className="hero-content">
            <p className="hero-tagline">
              A little curiosity.
              <br className="mobile-break" /> Limitless possibility.
            </p>
            <p className="hero-description">
              Your ideas. Your intelligence. Your machine.
            </p>
            <div className="hero-actions">
              <a className="pill pill-primary" href="#download">
                Meet MORICE
                <ArrowRight size={18} />
              </a>
              <a className="pill" href={repo}>
                Explore the source
                <ArrowUpRight size={17} />
              </a>
            </div>
          </div>
          <div className="hero-bottom">
            <a className="scroll-cue" href="#explore">
              <span>SCROLL TO EXPLORE</span>
              <ArrowDown size={15} />
            </a>
            <button
              className="motion-toggle"
              aria-pressed={!motion}
              aria-label={motion ? "Pause animations" : "Resume animations"}
              onClick={() => setMotion(!motion)}
            >
              {motion ? (
                <Pause size={14} weight="fill" />
              ) : (
                <Play size={14} weight="fill" />
              )}
              <span>{motion ? "Pause motion" : "Resume motion"}</span>
            </button>
          </div>
        </section>
        <section className="section explore-section" id="explore">
          <div className="section-heading" data-reveal>
            <div>
              <p className="eyebrow">THE NEXT CHAPTER</p>
              <h2>More room for possibility.</h2>
              <p className="section-description">
                Meet the tools that turn a spark of curiosity into something
                real.
              </p>
            </div>
            <a className="pill" href={`${repo}/blob/main/CHANGELOG.md`}>
              What’s new
              <ArrowUpRight size={16} />
            </a>
          </div>
          <div className="feature-grid">
            {[
              {
                image: "morice-home.png",
                category: "MEET MORICE",
                title: "Intelligence, on your terms.",
                copy: "Local models. A living interface. A workspace that feels like yours.",
                target: 0,
              },
              {
                image: "morice-security-lab.png",
                category: "INTRODUCING SECURITY LAB",
                title: "Look closer. Know more.",
                copy: "Real file analysis and verifiable results, right on your machine.",
                target: 5,
              },
              {
                image: "morice-projects.png",
                category: "BUILT FOR BUILDERS",
                title: "Less friction. More creating.",
                copy: "Bring your next project to life, from first thought to real files.",
                target: 1,
              },
            ].map((item, index) => (
              <a
                className="feature-card"
                href="#workspace"
                key={item.title}
                data-reveal
                style={
                  { "--reveal-delay": `${index * 100}ms` } as CSSProperties
                }
                onClick={() => switchWorkspace(item.target)}
              >
                <div className="feature-image">
                  <img
                    src={`./${item.image}?v=${version}`}
                    alt={`Actual MORICE ${workspaces[item.target].name} desktop app`}
                    width="1708"
                    height="1050"
                    loading="lazy"
                  />
                  <span className="card-arrow">
                    <ArrowUpRight size={20} />
                  </span>
                </div>
                <div className="feature-copy">
                  <p className="eyebrow">{item.category}</p>
                  <h3>{item.title}</h3>
                  <p>{item.copy}</p>
                </div>
              </a>
            ))}
          </div>
        </section>
        <section
          className="section workspace-section"
          id="workspace"
          aria-labelledby="workspace-title"
        >
          <div className="center-heading" data-reveal>
            <p className="eyebrow">ONE WORKSPACE. YOUR WHOLE WORLD.</p>
            <h2 id="workspace-title">
              Great ideas deserve
              <br />a space to grow.
            </h2>
            <p className="section-description">
              Think, build, research, create. Follow the idea wherever it takes
              you.
            </p>
          </div>
          <div className="workspace-showcase" data-reveal>
            <div
              className="workspace-tabs"
              role="tablist"
              aria-label="Explore MORICE workspaces"
            >
              {workspaces.map((item, index) => (
                <button
                  id={`workspace-tab-${index}`}
                  key={item.name}
                  role="tab"
                  aria-selected={selected === index}
                  aria-controls="workspace-panel"
                  tabIndex={selected === index ? 0 : -1}
                  onClick={() => switchWorkspace(index)}
                  onKeyDown={(event) => {
                    let next = selected;
                    if (event.key === "ArrowRight")
                      next = (selected + 1) % workspaces.length;
                    else if (event.key === "ArrowLeft")
                      next =
                        (selected + workspaces.length - 1) % workspaces.length;
                    else if (event.key === "Home") next = 0;
                    else if (event.key === "End") next = workspaces.length - 1;
                    else return;
                    event.preventDefault();
                    switchWorkspace(next, true);
                  }}
                >
                  <span className="tab-number">0{index + 1}</span>
                  {item.name}
                  <ArrowUpRight size={14} />
                </button>
              ))}
            </div>
            <div
              id="workspace-panel"
              className="workspace-panel"
              role="tabpanel"
              aria-labelledby={`workspace-tab-${selected}`}
              tabIndex={0}
            >
              <div className="workspace-copy" key={`${workspace.name}-copy`}>
                <p className="eyebrow">{workspace.tag}</p>
                <h3>{workspace.label}</h3>
                <p>{workspace.copy}</p>
                <a className="text-link" href={`${repo}/tree/main/docs`}>
                  Discover the workspace
                  <ArrowRight size={18} />
                </a>
                <span className="capture-note">
                  Actual MORICE desktop capture
                </span>
              </div>
              <div className="workspace-capture" key={workspace.name}>
                <div className="window-bar">
                  <span className="window-dots">
                    <i />
                    <i />
                    <i />
                  </span>
                  <span>MORICE / {workspace.name}</span>
                  <span>v{version}</span>
                </div>
                <img
                  src={`./${workspace.image}?v=${version}`}
                  alt={`Actual MORICE ${workspace.name} desktop workspace`}
                  width="1708"
                  height="1050"
                  loading="lazy"
                />
              </div>
            </div>
          </div>
        </section>
        <section className="section principles-section" id="principles">
          <div className="principles-intro" data-reveal>
            <p className="eyebrow">POWERFUL BY NATURE. PERSONAL BY DESIGN.</p>
            <h2>
              A world of intelligence.
              <br />
              <span>Still entirely yours.</span>
            </h2>
            <p className="section-description">
              We believe the best tools give you more freedom.
              <br />
              To think independently. To create openly. To stay in control.
            </p>
          </div>
          <div className="principles-grid">
            {[
              {
                Icon: Desktop,
                index: "01",
                title: "At home on your machine.",
                copy: "Run compatible local models on your own hardware. Your workspace and your files stay close to you.",
              },
              {
                Icon: ShieldCheck,
                index: "02",
                title: "You set the boundaries.",
                copy: "Microphone, camera, devices, and desktop control are yours to enable. Optional online providers remain your choice.",
              },
              {
                Icon: Code,
                index: "03",
                title: "Open from the beginning.",
                copy: "Explore the code. Understand how it works. Make it your own. MORICE is open source, under the MIT license.",
              },
            ].map(({ Icon, index, title, copy }) => (
              <article className="principle" data-reveal key={index}>
                <div className="principle-top">
                  <Icon size={28} weight="light" />
                  <span>{index}</span>
                </div>
                <h3>{title}</h3>
                <p>{copy}</p>
              </article>
            ))}
          </div>
        </section>
        <section className="download-section" id="download">
          <div className="download-content" data-reveal>
            <img
              className="download-logo"
              src="./morice-logo.png"
              alt="MORICE"
              width="88"
              height="88"
              loading="lazy"
            />
            <p className="eyebrow">YOUR NEXT IDEA STARTS HERE</p>
            <h2>
              Made for possibility.
              <br />
              Ready when you are.
            </h2>
            <p className="section-description">
              Bring MORICE to your desktop. See where curiosity takes you.
            </p>
            <div className="download-actions">
              <a className="pill pill-primary" href={release}>
                <DownloadSimple size={19} />
                Download for Windows
                <ArrowUpRight size={16} />
              </a>
              <a className="pill" href={`${repo}#run-from-source`}>
                <GithubLogo size={19} />
                Build from source
                <ArrowUpRight size={16} />
              </a>
            </div>
            <p className="download-meta">
              Windows 10 / 11<span>·</span>v{version} preview<span>·</span>Free
              & open source
            </p>
            <a
              className="android-link"
              href={`${repo}/releases/tag/v0.8.0-android`}
            >
              Looking for the Android companion?
              <ArrowUpRight size={13} />
            </a>
            <p className="requirements">
              Local inference requires compatible runtimes, model weights, and
              sufficient memory.
              <br />
              Media and voice features depend on your installed providers.
            </p>
          </div>
          <a className="closing-link" href={release}>
            <span>Let’s make something.</span>
            <ArrowUpRight weight="light" />
          </a>
        </section>
      </main>
      <footer className="site-footer">
        <div className="footer-main">
          <div className="footer-identity">
            <Brand />
            <p>Intelligence, under your control.</p>
            <a href={repo} aria-label="MORICE on GitHub">
              <GithubLogo size={22} />
            </a>
          </div>
          <div className="footer-column">
            <h3>Discover</h3>
            <a href="#workspace">Workspace</a>
            <a href="#explore">What’s new</a>
            <a href="#principles">Our approach</a>
          </div>
          <div className="footer-column">
            <h3>Get MORICE</h3>
            <a href={release}>Windows desktop</a>
            <a href={`${repo}/releases/tag/v0.8.0-android`}>
              Android companion
            </a>
            <a href={`${repo}#run-from-source`}>Build from source</a>
          </div>
          <div className="footer-column">
            <h3>Resources</h3>
            <a href={`${repo}/tree/main/docs`}>Documentation</a>
            <a href={`${repo}/issues`}>Feedback & issues</a>
            <a href={`${repo}/blob/main/LICENSE`}>MIT license</a>
          </div>
        </div>
        <div className="footer-bottom">
          <p>© {new Date().getFullYear()} MORICE. Built with curiosity.</p>
          <span>
            <Sparkle size={13} />
            LOCAL FIRST. OPEN ALWAYS.
          </span>
          <a href="#top">
            Back to top
            <ArrowUpRight size={14} />
          </a>
        </div>
      </footer>
    </div>
  );
}
