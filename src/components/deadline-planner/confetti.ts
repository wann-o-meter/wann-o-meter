const COLORS = ["var(--accent)", "var(--overdue)", "var(--ink)"];
const PIECES = 12;

export function burst(el: Element | null | undefined) {
  if (!el || matchMedia("(prefers-reduced-motion: reduce)").matches) return;
  const box = el.getBoundingClientRect();
  const x = box.left + box.width / 2;
  const y = box.top + box.height / 2;

  for (let i = 0; i < PIECES; i++) {
    const piece = document.createElement("i");
    piece.className = "wom-confetti";
    piece.style.left = `${x}px`;
    piece.style.top = `${y}px`;
    piece.style.background = COLORS[i % COLORS.length];
    document.body.appendChild(piece);

    const angle = (Math.PI * 2 * i) / PIECES + Math.random() * 0.4;
    const dist = 40 + Math.random() * 40;
    const dx = Math.cos(angle) * dist;
    const dy = Math.sin(angle) * dist + 30;

    piece
      .animate(
        [
          { transform: "translate(0,0) scale(1)", opacity: 1 },
          {
            transform: `translate(${dx}px,${dy}px) scale(0.4) rotate(${Math.random() * 360}deg)`,
            opacity: 0,
          },
        ],
        {
          duration: 600 + Math.random() * 300,
          easing: "cubic-bezier(.2,.7,.4,1)",
        },
      )
      .addEventListener("finish", () => piece.remove());
  }
}
