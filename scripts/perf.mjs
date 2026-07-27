// FCP / LCP / font-request timings under Lighthouse-ish mobile throttling,
// median of N runs (single runs swing far too much to compare against).
// Same throwaway-diagnostic status as scripts/cls.mjs:
//
//   bun add -d puppeteer && bun run build && bun run preview &
//   node scripts/perf.mjs [path] [runs]
import puppeteer from "puppeteer";

const path = process.argv[2] ?? "/";
const runs = Number(process.argv[3] ?? 5);
const median = (xs) => xs.slice().sort((a, b) => a - b)[Math.floor(xs.length / 2)];

const browser = await puppeteer.launch({ headless: true, args: ["--no-sandbox"] });
const out = { fcp: [], lcp: [], fontDone: [], fontBytes: [] };

for (let i = 0; i < runs; i++) {
  const page = await browser.newPage();
  await page.setViewport({ width: 412, height: 823, deviceScaleFactor: 1.75, isMobile: true });
  await page.setCacheEnabled(false);
  const cdp = await page.createCDPSession();
  await cdp.send("Emulation.setCPUThrottlingRate", { rate: 4 });
  await cdp.send("Network.enable");
  await cdp.send("Network.emulateNetworkConditions", {
    offline: false,
    latency: 150,
    downloadThroughput: (1.6 * 1024 * 1024) / 8,
    uploadThroughput: (750 * 1024) / 8,
  });

  // LCP entries are only delivered through a buffered observer - they are not
  // in performance.getEntriesByType() by the time we ask.
  await page.evaluateOnNewDocument(() => {
    window.__lcp = 0;
    window.__tbt = 0;
    new PerformanceObserver((l) => {
      for (const e of l.getEntries()) if (e.duration > 50) window.__tbt += e.duration - 50;
    }).observe({ type: "longtask", buffered: true });
    new PerformanceObserver((l) => {
      for (const e of l.getEntries()) window.__lcp = e.startTime;
    }).observe({ type: "largest-contentful-paint", buffered: true });
  });

  const fonts = [];
  page.on("response", async (r) => {
    if (r.url().endsWith(".woff2")) fonts.push({ url: r.url(), t: Date.now() });
  });

  const t0 = Date.now();
  await page.goto("http://localhost:4321" + path, { waitUntil: "load", timeout: 60000 });
  await new Promise((r) => setTimeout(r, 4000));

  const paints = await page.evaluate(() => ({
    fcp: performance.getEntriesByName("first-contentful-paint")[0]?.startTime ?? null,
    lcp: window.__lcp ?? null,
    tbt: window.__tbt ?? 0,
  }));
  out.fcp.push(paints.fcp);
  out.lcp.push(paints.lcp);
  (out.tbt ??= []).push(paints.tbt);
  out.fontDone.push(fonts.length ? Math.max(...fonts.map((f) => f.t)) - t0 : 0);
  out.fontBytes.push(fonts.length);
  await page.close();
}

console.log(`${path}  (median of ${runs})`);
console.log(`  FCP            ${Math.round(median(out.fcp))} ms`);
console.log(`  LCP            ${Math.round(median(out.lcp))} ms`);
console.log(`  TBT            ${Math.round(median(out.tbt))} ms`);
console.log(`  last woff2 in  ${Math.round(median(out.fontDone))} ms  (${median(out.fontBytes)} files)`);

await browser.close();
