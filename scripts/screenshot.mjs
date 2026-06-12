// Drives the running Gradio app and captures README/Loom screenshots.
// Usage: npx playwright launch via `node scripts/screenshot.mjs` (chromium must be installed)
import { chromium } from "playwright";

const BASE = "http://127.0.0.1:7860";
const OUT = "docs";

const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } });
await page.goto(BASE, { waitUntil: "networkidle" });
await page.waitForTimeout(1500);

// 1. Fresh console
await page.screenshot({ path: `${OUT}/01-console.png`, fullPage: false });

// 2. Pick the first sample from gr.Examples (web-outage.log) and run
await page.locator(".gallery button, .gallery .example, table.gallery tr").first().click().catch(async () => {
  // fallback selector for newer Gradio examples markup
  await page.getByText("web-outage.log", { exact: false }).first().click();
});
await page.waitForTimeout(1000);
await page.getByRole("button", { name: "Analyze" }).click();

// 3. Wait for the run to finish (cookbook trace line appears), max 3 min
// NOTE: the page has multiple textareas (paste-log box + trace) — check them all.
await page.waitForFunction(
  () =>
    [...document.querySelectorAll("textarea")].some((t) =>
      t.value.includes("Cookbook: checklist synthesized")
    ),
  null,
  { timeout: 180000, polling: 2000 }
);
await page.waitForTimeout(2500);

// 4. Capture: full results view + trace close-up
await page.screenshot({ path: `${OUT}/02-analysis.png`, fullPage: false });
await page.screenshot({ path: `${OUT}/03-fullpage.png`, fullPage: true });

// 5. Open the LangGraph accordion and capture the compiled-graph diagram
//    (shows the verify_causes critic node + the dashed loop edge back to classify)
const graphAccordion = page.getByText("Orchestration graph", { exact: false }).first();
await graphAccordion.scrollIntoViewIfNeeded();
await graphAccordion.click();
await page.waitForTimeout(1200);
const graphImg = page.locator(".accordion img, .gradio-accordion img, img[src*='incident_suite_graph']").last();
await graphImg.scrollIntoViewIfNeeded();
await graphImg.screenshot({ path: `${OUT}/04-graph.png` });

const trace = await page.evaluate(() =>
  [...document.querySelectorAll("textarea")]
    .map((t) => t.value)
    .sort((a, b) => b.length - a.length)[0]
);
console.log("=== FINAL TRACE (tail) ===");
console.log(trace.split("\n").slice(-14).join("\n"));

await browser.close();
console.log("Screenshots written to docs/");
