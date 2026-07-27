// Measures CLS + per-element shift attribution on a Lighthouse-mobile-ish
// emulation (Moto G Power viewport, 4x CPU throttle, slow 4G), and prints the
// before/after rect of every element that moved - which is what tells you
// *what* shifted, not just that something did.
//
// Puppeteer is deliberately NOT a dependency of this project - this is a
// one-off diagnostic, not part of the build:
//
//   bun add -d puppeteer && bun run build && bun run preview &
//   node scripts/cls.mjs [url]        # default http://localhost:4321/
import puppeteer from "puppeteer";

const url = process.argv[2] ?? "http://localhost:4321/";

const browser = await puppeteer.launch({ headless: true, args: ["--no-sandbox"] });
const page = await browser.newPage();
await page.setViewport({ width: 412, height: 823, deviceScaleFactor: 1.75, isMobile: true, hasTouch: true });
await page.setUserAgent(
  "Mozilla/5.0 (Linux; Android 11; moto g power) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Mobile Safari/537.36",
);
const cdp = await page.createCDPSession();
await cdp.send("Emulation.setCPUThrottlingRate", { rate: 4 });
await cdp.send("Network.enable");
await cdp.send("Network.emulateNetworkConditions", {
  offline: false,
  latency: 150,
  downloadThroughput: (1.6 * 1024 * 1024) / 8,
  uploadThroughput: (750 * 1024) / 8,
});

await page.evaluateOnNewDocument(() => {
  window.__shifts = [];
  new PerformanceObserver((list) => {
    for (const e of list.getEntries()) {
      if (e.hadRecentInput) continue;
      window.__shifts.push({
        value: e.value,
        time: e.startTime,
        nodes: e.sources.map((s) => s.node),
        rects: e.sources.map((s) => [s.previousRect, s.currentRect]),
      });
    }
  }).observe({ type: "layout-shift", buffered: true });
});

await page.goto(url, { waitUntil: "load", timeout: 60000 });
await new Promise((r) => setTimeout(r, 8000));

const result = await page.evaluate(() => {
  const describe = (n) => {
    if (!n) return "(detached)";
    const el = n.nodeType === 1 ? n : n.parentElement;
    if (!el) return "(text)";
    return (
      el.tagName.toLowerCase() +
      (el.id ? `#${el.id}` : "") +
      (el.className && typeof el.className === "string" ? `.${el.className.trim().split(/\s+/).join(".")}` : "")
    ).slice(0, 90);
  };
  const byNode = new Map();
  let total = 0;
  for (const s of window.__shifts) {
    total += s.value;
    for (const n of s.nodes) {
      const k = describe(n);
      byNode.set(k, (byNode.get(k) ?? 0) + s.value / s.nodes.length);
    }
  }
  return {
    cls: total,
    shifts: window.__shifts.map((s) => ({
      value: +s.value.toFixed(4),
      t: Math.round(s.time),
      nodes: s.nodes.map((n, i) => {
        const [p, c] = s.rects[i];
        const r = (x) => `${Math.round(x.x)},${Math.round(x.y)} ${Math.round(x.width)}x${Math.round(x.height)}`;
        return `${describe(n)}  [${r(p)} -> ${r(c)}]`;
      }),
    })),
    byNode: [...byNode].sort((a, b) => b[1] - a[1]).map(([k, v]) => [k, +v.toFixed(4)]),
  };
});

console.log(`CLS ${result.cls.toFixed(4)}  (${result.shifts.length} shifts)\n`);
console.log("Per element:");
for (const [node, value] of result.byNode) console.log(`  ${value.toFixed(4)}  ${node}`);
console.log("\nTimeline:");
for (const s of result.shifts) console.log(`  t=${s.t}ms  ${s.value}  ${s.nodes.join("\n           ")}`);

await browser.close();
