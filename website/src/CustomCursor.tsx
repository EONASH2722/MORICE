import { useEffect, useRef } from "react";

export default function CustomCursor({ motion }: { motion: boolean }) {
  const ringRef = useRef<HTMLDivElement>(null);
  const dotRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const ring = ringRef.current,
      dot = dotRef.current;
    const pointer = matchMedia("(hover: hover) and (pointer: fine)");
    const reduced = matchMedia("(prefers-reduced-motion: reduce)");
    if (!ring || !dot) return;
    let frame = 0,
      x = 0,
      y = 0,
      ringX = 0,
      ringY = 0,
      shown = false;
    const hide = () => {
      shown = false;
      ring.classList.remove("is-visible", "is-hover", "is-down");
      dot.classList.remove("is-visible");
      document.documentElement.classList.remove("custom-cursor-active");
      cancelAnimationFrame(frame);
      frame = 0;
    };
    const draw = () => {
      const ease = motion ? 0.22 : 1;
      ringX += (x - ringX) * ease;
      ringY += (y - ringY) * ease;
      ring.style.transform = `translate3d(${ringX}px, ${ringY}px, 0)`;
      if (shown && (Math.abs(x - ringX) > 0.1 || Math.abs(y - ringY) > 0.1))
        frame = requestAnimationFrame(draw);
      else frame = 0;
    };
    const move = (event: PointerEvent) => {
      if (!pointer.matches || reduced.matches || event.pointerType !== "mouse")
        return hide();
      x = event.clientX;
      y = event.clientY;
      if (!shown) {
        shown = true;
        ringX = x;
        ringY = y;
        document.documentElement.classList.add("custom-cursor-active");
        ring.classList.add("is-visible");
        dot.classList.add("is-visible");
      }
      dot.style.transform = `translate3d(${x}px, ${y}px, 0)`;
      ring.classList.toggle(
        "is-hover",
        Boolean((event.target as Element)?.closest('a, button, [role="tab"]')),
      );
      if (!frame) draw();
    };
    const down = () => {
      if (shown) ring.classList.add("is-down");
    };
    const up = () => ring.classList.remove("is-down");
    const visibility = () => {
      if (document.hidden) hide();
    };
    document.addEventListener("pointermove", move, { passive: true });
    document.addEventListener("pointerdown", down);
    document.addEventListener("pointerup", up);
    document.documentElement.addEventListener("pointerleave", hide);
    document.addEventListener("visibilitychange", visibility);
    window.addEventListener("blur", hide);
    window.addEventListener("keydown", hide);
    pointer.addEventListener("change", hide);
    reduced.addEventListener("change", hide);
    return () => {
      hide();
      document.removeEventListener("pointermove", move);
      document.removeEventListener("pointerdown", down);
      document.removeEventListener("pointerup", up);
      document.documentElement.removeEventListener("pointerleave", hide);
      document.removeEventListener("visibilitychange", visibility);
      window.removeEventListener("blur", hide);
      window.removeEventListener("keydown", hide);
      pointer.removeEventListener("change", hide);
      reduced.removeEventListener("change", hide);
    };
  }, [motion]);
  return (
    <>
      <div className="cursor-ring" ref={ringRef} aria-hidden="true">
        <span />
      </div>
      <div className="cursor-dot" ref={dotRef} aria-hidden="true" />
    </>
  );
}
