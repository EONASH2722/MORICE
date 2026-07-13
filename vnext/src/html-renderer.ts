/**
 * HTML renderer for VNext visualizations
 * Creates responsive containers for graph and physics rendering
 */

export interface RendererConfig {
  containerId: string;
  darkMode?: boolean;
  width?: number;
  height?: number;
}

export function createGraphContainer(config: RendererConfig): HTMLElement {
  const container = document.getElementById(config.containerId);
  if (!container) {
    throw new Error(`Container ${config.containerId} not found`);
  }

  container.style.width = config.width ? `${config.width}px` : '100%';
  container.style.height = config.height ? `${config.height}px` : '400px';
  container.style.backgroundColor = config.darkMode ? '#050711' : '#ffffff';
  container.style.borderRadius = '12px';
  container.style.overflow = 'hidden';
  container.className = 'vnext-graph-container';

  return container;
}

export function createPhysicsContainer(config: RendererConfig): HTMLElement {
  const container = document.getElementById(config.containerId);
  if (!container) {
    throw new Error(`Container ${config.containerId} not found`);
  }

  container.style.width = config.width ? `${config.width}px` : '100%';
  container.style.height = config.height ? `${config.height}px` : '500px';
  container.style.backgroundColor = config.darkMode ? '#050711' : '#ffffff';
  container.style.borderRadius = '12px';
  container.style.overflow = 'hidden';
  container.className = 'vnext-physics-container';

  return container;
}

export function createControlPanel(): HTMLElement {
  const panel = document.createElement('div');
  panel.className = 'vnext-control-panel';
  panel.style.display = 'flex';
  panel.style.gap = '8px';
  panel.style.padding = '12px';
  panel.style.backgroundColor = 'rgba(0,0,0,0.2)';
  panel.style.borderRadius = '8px';

  return panel;
}

export function addControlButton(panel: HTMLElement, label: string, onClick: () => void): HTMLButtonElement {
  const button = document.createElement('button');
  button.textContent = label;
  button.style.padding = '8px 16px';
  button.style.borderRadius = '6px';
  button.style.border = '1px solid rgba(200,200,200,0.3)';
  button.style.backgroundColor = 'rgba(100,100,120,0.6)';
  button.style.color = '#ffffff';
  button.style.cursor = 'pointer';
  button.onclick = onClick;

  button.addEventListener('mouseenter', () => {
    button.style.backgroundColor = 'rgba(130,130,160,0.8)';
  });

  button.addEventListener('mouseleave', () => {
    button.style.backgroundColor = 'rgba(100,100,120,0.6)';
  });

  panel.appendChild(button);
  return button;
}
