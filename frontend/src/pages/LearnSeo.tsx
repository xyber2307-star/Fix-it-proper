import { Link } from "react-router-dom";
import Breadcrumbs from "../components/Breadcrumbs";
import Card from "../components/Card";
import Container from "../components/Container";
import { useDocumentHead } from "../lib/head";
import { metaForPath } from "../lib/pages";

const SECTIONS: { title: string; body: string[] }[] = [
  {
    title: "Page title",
    body: [
      "The title tag names the page in search results and browser tabs. It must exist, must not be empty, and reads best between 30 and 60 characters.",
      "Fix: write one title per page that names the page topic and, for local businesses, the city. Keep it under 60 characters so it is not cut off.",
    ],
  },
  {
    title: "Meta description",
    body: [
      "The meta description is the short summary under the title in search results. It must exist and reads best between 70 and 160 characters.",
      "Fix: summarize what the page offers and who it is for in one or two sentences. Every page needs its own description.",
    ],
  },
  {
    title: "Headings",
    body: [
      "The H1 is the main heading of the page. A page needs exactly one. Heading levels should not skip, so an H3 follows an H2, never an H1 directly.",
      "Fix: give the page one H1 that matches its topic, then nest H2 and H3 sections in order.",
    ],
  },
  {
    title: "Canonical address",
    body: [
      "The canonical tag tells search engines which address is the official copy of the page. It must exist and must point to the same host.",
      "Fix: add a canonical tag with the full page address on every page, including paginated and filtered variants.",
    ],
  },
  {
    title: "Indexing",
    body: [
      "A robots meta tag with noindex tells search engines to drop the page from results. That is correct for private pages and a disaster on pages you want found.",
      "Fix: remove noindex from public pages. Keep it only on pages that must stay out of search.",
    ],
  },
  {
    title: "Images",
    body: [
      "Alt text describes each image for screen readers and search engines. Width and height attributes reserve space so the page does not jump while images load.",
      "Fix: write short alt text for every meaningful image and set width and height on each img tag.",
    ],
  },
  {
    title: "Social preview tags",
    body: [
      "Open Graph tags (og:title, og:description, og:image) control the preview card when the page is shared. A missing tag means a broken or blank preview.",
      "Fix: set all three tags with the page title, a one line summary, and an image at least 1200 by 630 pixels.",
    ],
  },
  {
    title: "Mobile basics",
    body: [
      "The viewport tag tells phones how wide to render the page. Without it, mobile visitors get a shrunken desktop layout.",
      "Fix: add the standard viewport tag to every page and check the layout at 320 pixels wide.",
    ],
  },
  {
    title: "Page language",
    body: [
      "The lang attribute names the page language for screen readers, translation, and spell checking.",
      "Fix: set lang on the html tag, for example lang=\"en\" for English.",
    ],
  },
  {
    title: "Links",
    body: [
      "Links with empty text give screen reader users nothing to activate. Broken anchor addresses point at pages that do not exist.",
      "Fix: give every link descriptive text and check that each address resolves.",
    ],
  },
  {
    title: "Structured data",
    body: [
      "JSON-LD structured data describes the business, page, or product in a format search engines read directly. Pages without it miss rich results.",
      "Fix: add valid JSON-LD for the page type and test it in the Rich Results Test before publishing.",
    ],
  },
  {
    title: "Crawl files",
    body: [
      "robots.txt tells crawlers which paths they may fetch. sitemap.xml lists the pages worth indexing.",
      "Fix: serve both files at the site root and reference the sitemap from robots.txt.",
    ],
  },
  {
    title: "HTTPS and mixed content",
    body: [
      "Pages must load over HTTPS. Mixed content means a secure page loads images, scripts, or styles over plain HTTP, which browsers block or warn about.",
      "Fix: serve everything over HTTPS and rewrite any http:// asset address to https://.",
    ],
  },
  {
    title: "Performance",
    body: [
      "Largest Contentful Paint measures when the main content appears. Layout shift measures how much the page jumps. Responsiveness measures how fast it reacts to input. Page weight is the total download size.",
      "Fix: compress images, defer work the first screen does not need, reserve space for late loading content, and re-measure instead of guessing.",
    ],
  },
];

export default function LearnSeo() {
  const meta = metaForPath("/learn/seo");
  useDocumentHead(meta.fullTitle, meta.description, meta.path);
  return (
    <Container className="py-10">
      <Breadcrumbs
        items={[
          { label: "Home", href: "/" },
          { label: "Learn" },
          { label: meta.shortTitle },
        ]}
      />
      <h1 className="mt-2 font-serif text-3xl font-semibold">{meta.shortTitle}</h1>
      <p className="mt-2 max-w-2xl text-muted">
        Every check below maps to a rule the analyzer runs. Thresholds match the tool
        exactly, so a report and this guide always agree.
      </p>
      <div className="mt-8 max-w-3xl space-y-4">
        {SECTIONS.map((section) => (
          <Card key={section.title}>
            <h2 className="font-serif text-xl font-semibold">{section.title}</h2>
            {section.body.map((paragraph) => (
              <p key={paragraph.slice(0, 24)} className="mt-2 text-sm text-muted">
                {paragraph}
              </p>
            ))}
          </Card>
        ))}
        <Card>
          <h2 className="font-serif text-xl font-semibold">Run the checks on your page</h2>
          <p className="mt-2 text-sm text-muted">
            Sign in, complete your business profile, and paste a URL to see which of
            these your page passes.
          </p>
          <p className="mt-4 flex flex-wrap gap-2">
            <Link
              to="/login"
              className="inline-flex min-h-[44px] items-center justify-center gap-2 rounded-md bg-accent px-5 font-semibold text-white transition-colors duration-150 hover:bg-accent-strong"
            >
              Sign in
            </Link>
            <Link
              to="/signup"
              className="inline-flex min-h-[44px] items-center justify-center gap-2 rounded-md border border-line bg-surface px-5 font-semibold text-ink transition-colors duration-150 hover:border-muted"
            >
              Create account
            </Link>
          </p>
        </Card>
      </div>
    </Container>
  );
}
