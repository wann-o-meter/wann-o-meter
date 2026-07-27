// WCAG contrast of every calendar day cell, light and dark, accounting for
// element opacity and for backgrounds that come from color-mix(). Same
// throwaway-diagnostic status as scripts/cls.mjs - puppeteer is not a project
// dependency:
//
//   bun add -d puppeteer && bun run build && bun run preview &
//   node scripts/contrast.mjs [url]      # default http://localhost:4321/
import puppeteer from "puppeteer";

const url = process.argv[2] ?? "http://localhost:4321/";
const browser = await puppeteer.launch({ headless: true, args: ["--no-sandbox"] });

for (const scheme of ["light", "dark"]) {
  const page = await browser.newPage();
  await page.setViewport({ width: 412, height: 823, isMobile: true });
  await page.emulateMediaFeatures([{ name: "prefers-color-scheme", value: scheme }]);
  await page.goto(url, { waitUntil: "networkidle0" });
  await new Promise((r) => setTimeout(r, 1500));

  const rows = await page.evaluate(() => {
    const parse = (c) => (c.match(/[\d.]+/g) ?? []).map(Number);
    const over = (fg, bg, a) => fg.map((v, i) => v * a + bg[i] * (1 - a));
    const lum = ([r, g, b]) =>
      [r, g, b]
        .map((v) => v / 255)
        .map((v) => (v <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4))
        .reduce((a, v, i) => a + v * [0.2126, 0.7152, 0.0722][i], 0);
    const ratio = (a, b) => {
      const [x, y] = [lum(a), lum(b)].sort((m, n) => n - m);
      return (x + 0.05) / (y + 0.05);
    };
    const pageBg = parse(getComputedStyle(document.body).backgroundColor).slice(0, 3);

    return [...document.querySelectorAll(".day-cell, .day")].map((el) => {
      const cs = getComputedStyle(el);
      const alpha = Number(cs.opacity);
      const own = parse(cs.backgroundColor);
      // element background over the page, then the element's own opacity
      const bgOpaque = own.length === 4 ? over(own.slice(0, 3), pageBg, own[3]) : own.slice(0, 3);
      const bg = over(bgOpaque, pageBg, alpha);
      const fgRaw = parse(cs.color);
      const fg = over(over(fgRaw.slice(0, 3), bg, fgRaw[3] ?? 1), bg, alpha);
      return {
        text: el.textContent.trim(),
        cls: el.className.replace(/\bday-cell\b|\bday\b/, "").trim() || "(current month)",
        shaded: cs.backgroundColor !== getComputedStyle(document.body).backgroundColor,
        ratio: +ratio(fg, bg).toFixed(2),
      };
    });
  });
  await page.close();

  const worst = rows.sort((a, b) => a.ratio - b.ratio);
  const failing = worst.filter((r) => r.ratio < 4.5);
  console.log(`\n== ${scheme}: ${failing.length}/${rows.length} cells below 4.5:1`);
  for (const r of worst.slice(0, 6)) {
    console.log(`  ${r.ratio.toFixed(2).padStart(5)}:1  "${r.text}"  ${r.cls}${r.shaded ? " [shaded]" : ""}`);
  }
}

await browser.close();
