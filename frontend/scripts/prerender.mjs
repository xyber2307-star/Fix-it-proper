// Build time prerender: renders each route to static HTML with full head tags,
// plus sitemap.xml, robots.txt, and a static 404 page.
//
// Usage: npm run build (runs this automatically), optionally with
// SITE_URL=https://example.com for absolute canonical, OG, and sitemap URLs.
// Without SITE_URL those URLs fall back to site-relative paths.
import { readdirSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { pathToFileURL } from "node:url";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const dist = join(here, "..", "dist");
const SITE_URL = (process.env.SITE_URL || "").replace(/\/$/, "");
const LASTMOD = "2026-11-02";
const EMAIL = "xyber2307@gmail.com";

const abs = (path) => (SITE_URL === "" ? path : `${SITE_URL}${path}`);

const serverDir = join(dist, "server");
const entryName = readdirSync(serverDir).find(
  (name) => name.startsWith("entry-server") && name.endsWith(".js"),
);
if (!entryName) {
  throw new Error("SSR bundle not found. Run vite build --ssr first.");
}
const server = await import(pathToFileURL(join(serverDir, entryName)).href);
const { render, PAGE_META, NOT_FOUND_META } = server;

const template = readFileSync(join(dist, "index.html"), "utf-8");

function escapeAttr(value) {
  return value.replace(/&/g, "&amp;").replace(/"/g, "&quot;");
}

function orgGraph() {
  const graph = {
    "@context": "https://schema.org",
    "@graph": [
      {
        "@type": "Organization",
        name: "Fix It Proper",
        url: abs("/"),
        contactPoint: {
          "@type": "ContactPoint",
          email: EMAIL,
          contactType: "customer service",
        },
      },
      {
        "@type": "WebApplication",
        name: "Fix It Proper",
        url: abs("/"),
        applicationCategory: "BusinessApplication",
        operatingSystem: "Web",
        description: PAGE_META[0].description,
      },
    ],
  };
  return `<script type="application/ld+json">${JSON.stringify(graph)}</script>`;
}

function breadcrumbJsonLd(trail) {
  const data = {
    "@context": "https://schema.org",
    "@type": "BreadcrumbList",
    itemListElement: trail.map((crumb, index) => ({
      "@type": "ListItem",
      position: index + 1,
      name: crumb.name,
      item: abs(crumb.path),
    })),
  };
  return `<script type="application/ld+json">${JSON.stringify(data)}</script>`;
}

function headTags(meta, jsonLd) {
  const tags = [
    `<link rel="canonical" href="${escapeAttr(abs(meta.path))}" />`,
    `<meta property="og:title" content="${escapeAttr(meta.fullTitle)}" />`,
    `<meta property="og:description" content="${escapeAttr(meta.description)}" />`,
    '<meta property="og:type" content="website" />',
    `<meta property="og:url" content="${escapeAttr(abs(meta.path))}" />`,
    `<meta property="og:image" content="${escapeAttr(abs("/og-image.png"))}" />`,
    `<meta property="og:image:width" content="1200" />`,
    `<meta property="og:image:height" content="630" />`,
    '<meta name="twitter:card" content="summary_large_image" />',
    `<meta name="twitter:title" content="${escapeAttr(meta.fullTitle)}" />`,
    `<meta name="twitter:description" content="${escapeAttr(meta.description)}" />`,
    `<meta name="twitter:image" content="${escapeAttr(abs("/og-image.png"))}" />`,
  ];
  if (jsonLd) tags.push(jsonLd);
  return tags.join("\n    ");
}

async function renderPage(meta, url, jsonLd) {
  const body = await render(url);
  let html = template.replace(/<title>.*?<\/title>/, `<title>${escapeAttr(meta.fullTitle)}</title>`);
  html = html.replace(
    /<meta name="description" content=".*?" \/>/,
    `<meta name="description" content="${escapeAttr(meta.description)}" />`,
  );
  html = html.replace("</head>", `    ${headTags(meta, jsonLd)}\n  </head>`);
  html = html.replace('<div id="root"></div>', `<div id="root">${body}</div>`);
  return html;
}

const outputs = [
  { file: "index.html", meta: PAGE_META[0], url: "/", jsonLd: orgGraph() },
  ...PAGE_META.slice(1).map((meta) => ({
    file: `${meta.path.slice(1)}.html`,
    meta,
    url: meta.path,
    jsonLd: breadcrumbJsonLd([
      { name: "Home", path: "/" },
      { name: meta.shortTitle, path: meta.path },
    ]),
  })),
  { file: "404.html", meta: NOT_FOUND_META, url: "/404-not-found", jsonLd: null },
];

for (const output of outputs) {
  writeFileSync(join(dist, output.file), await renderPage(output.meta, output.url, output.jsonLd));
  console.log(`prerendered ${output.file}`);
}

const sitemap = [
  '<?xml version="1.0" encoding="UTF-8"?>',
  '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">',
  ...PAGE_META.map(
    (meta) => `  <url><loc>${escapeAttr(abs(meta.path))}</loc><lastmod>${LASTMOD}</lastmod></url>`,
  ),
  "</urlset>",
  "",
].join("\n");
writeFileSync(join(dist, "sitemap.xml"), sitemap);

// Sitemap entries must be absolute URLs, so the line is only emitted when
// SITE_URL is set. Without it the file stays valid with just Allow.
const robotsLines = ["User-agent: *", "Allow: /"];
if (SITE_URL !== "") {
  robotsLines.push(`Sitemap: ${abs("/sitemap.xml")}`);
}
writeFileSync(join(dist, "robots.txt"), robotsLines.join("\n") + "\n");

rmSync(serverDir, { recursive: true, force: true });
console.log("prerender done");
