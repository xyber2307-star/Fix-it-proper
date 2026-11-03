import { useEffect, useRef, useState } from "react";
import type { FormEvent } from "react";
import { Link } from "react-router-dom";
import { ArrowRight, LoaderCircle } from "lucide-react";
import exampleFixture from "../../../backend/tests/fixtures/full_success.json";
import { useAuth } from "../auth/AuthContext";
import { BRAND } from "../config/brand";
import Breadcrumbs from "../components/Breadcrumbs";
import Button from "../components/Button";
import Card from "../components/Card";
import Container from "../components/Container";
import ErrorPanel from "../components/ErrorPanel";
import Input from "../components/Input";
import Report, { hostOf } from "../components/Report";
import { AnalyzeError, analyzeUrl } from "../lib/api";
import { useDocumentHead } from "../lib/head";
import { metaForPath } from "../lib/pages";
import type { AnalyzeResponse } from "../types/api";

const REQUEST_TIMEOUT_MS = 45000;

// Rendered verbatim. Backend tests validate this file against the API schema.
const exampleReport = exampleFixture as AnalyzeResponse;

const CHECK_GROUPS: { title: string; items: string[] }[] = [
  {
    title: "Titles and descriptions",
    items: [
      "Page title missing, empty, or outside 30 to 60 characters",
      "Title identical to the main heading",
      "Meta description missing or outside 70 to 160 characters",
    ],
  },
  {
    title: "Headings",
    items: [
      "Missing main heading, more than one, or skipped heading levels",
    ],
  },
  {
    title: "Links and images",
    items: [
      "Links with empty text and malformed anchor addresses",
      "Images missing alt text, with the first 5 reported",
      "Images missing width and height",
    ],
  },
  {
    title: "Social and document tags",
    items: [
      "Open Graph title, description, and image",
      "Twitter card, viewport tag, and page language",
    ],
  },
  {
    title: "Technical",
    items: [
      "Canonical address missing or pointing off host",
      "Accidental noindex flag, HTTPS, and mixed content",
      "robots.txt and sitemap.xml presence",
      "Structured data missing or unparseable",
    ],
  },
  {
    title: "Performance, from Google PageSpeed",
    items: [
      "Largest Contentful Paint, layout shift, and responsiveness",
      "Total page weight and the worst failing audits",
    ],
  },
  {
    title: "YouTube video pages",
    items: [
      "Title length, description hook, call to action and links",
      "Chapters on videos of 3 minutes or more, caption tracks",
    ],
  },
];

const LIMITS: string[] = [
  "Public pages only. Anything behind a login is out of reach, and we analyze one page per report, not whole sites.",
  "No social or ad analysis. Instagram, Facebook, TikTok, X, LinkedIn, and ad platforms are refused with a clear error.",
  "No traffic predictions. Results are a checklist of problems found, not a forecast of rankings, traffic, or virality.",
  "Performance data needs a PageSpeed API key. Without one, that section is listed as unavailable instead of guessed.",
  "Some checks assume English copy, including the call to action word lists.",
];

export default function Home() {
  const meta = metaForPath("/");
  useDocumentHead(meta.fullTitle, meta.description, meta.path);
  const [url, setUrl] = useState("");
  const [brandVoice, setBrandVoice] = useState("");
  const [inputError, setInputError] = useState("");
  const [loading, setLoading] = useState(false);
  const [report, setReport] = useState<AnalyzeResponse | null>(null);
  const [error, setError] = useState<AnalyzeError | null>(null);
  const [elapsed, setElapsed] = useState(0);
  const reportHeading = useRef<HTMLHeadingElement>(null);
  const { user, configured, getToken } = useAuth();
  const controllerRef = useRef<AbortController | null>(null);
  const abortReason = useRef<"user" | "timeout" | null>(null);

  useEffect(() => {
    if (!loading) return;
    setElapsed(0);
    const id = window.setInterval(() => setElapsed((seconds) => seconds + 1), 1000);
    return () => window.clearInterval(id);
  }, [loading]);

  async function runAnalysis(trimmed: string) {
    setInputError("");
    setLoading(true);
    setError(null);
    setReport(null);
    abortReason.current = null;
    const controller = new AbortController();
    controllerRef.current = controller;
    const timer = window.setTimeout(() => {
      abortReason.current = "timeout";
      controller.abort();
    }, REQUEST_TIMEOUT_MS);
    try {
      let idToken: string | undefined;
      if (user !== null) {
        try {
          idToken = (await getToken()) ?? undefined;
        } catch {
          idToken = undefined;
        }
      }
      const result = await analyzeUrl(trimmed, brandVoice, controller.signal, idToken);
      setReport(result);
      requestAnimationFrame(() => reportHeading.current?.focus());
    } catch (unknown) {
      if (unknown instanceof DOMException && unknown.name === "AbortError") {
        if (abortReason.current === "user") {
          setError(
            new AnalyzeError("Analysis cancelled before it finished.", "CANCELLED", true, 0),
          );
        } else {
          setError(
            new AnalyzeError(
              "The request timed out. Try again in a minute.",
              "TIMEOUT",
              true,
              0,
            ),
          );
        }
      } else if (unknown instanceof AnalyzeError) {
        setError(unknown);
      } else {
        setError(new AnalyzeError("Something went wrong. Try again.", "UNKNOWN", true, 0));
      }
    } finally {
      window.clearTimeout(timer);
      controllerRef.current = null;
      setLoading(false);
    }
  }

  function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const trimmed = url.trim();
    if (trimmed === "") {
      setInputError("Enter a website URL.");
      return;
    }
    if (!/^https?:\/\//i.test(trimmed)) {
      setInputError("URL must start with http:// or https://.");
      return;
    }
    void runAnalysis(trimmed);
  }

  function onCancel() {
    abortReason.current = "user";
    controllerRef.current?.abort();
  }

  function onRetry() {
    void runAnalysis(url.trim());
  }

  return (
    <Container className="py-10">
      <h1 className="font-serif text-3xl font-semibold leading-tight">
        Find the specific problems on your website, ranked by what to fix first.
      </h1>
      <p className="mt-2 max-w-2xl text-muted">
        Paste a public website URL. {BRAND.name} runs deterministic checks and returns a
        ranked fix list with evidence, plus rewrite suggestions to test.
      </p>

      <Card className="mt-6">
        <form onSubmit={onSubmit} noValidate>
          <Input
            id="website-url"
            label="Website URL"
            type="url"
            autoComplete="url"
            inputMode="url"
            placeholder="https://example.com/"
            value={url}
            onChange={(event) => setUrl(event.target.value)}
            error={inputError}
            hint="Public websites and landing pages only."
          />
          <details className="mt-4">
            <summary className="inline-block min-h-[44px] cursor-pointer py-3 font-semibold text-accent">
              Brand voice (optional)
            </summary>
            <Input
              id="brand-voice"
              label="How should suggestions sound?"
              placeholder="Friendly neighborhood plumber"
              value={brandVoice}
              onChange={(event) => setBrandVoice(event.target.value)}
              hint="Plain words the AI uses as context for rewrites."
            />
          </details>
          <div className="mt-4">
            <Button type="submit" loading={loading}>
              {loading ? "Analyzing…" : "Analyze website"}
              {!loading && <ArrowRight className="size-4" aria-hidden="true" />}
            </Button>
          </div>
          {user !== null && (
            <p className="mt-3 text-sm text-muted">
              Signed in as {user.email ?? "your account"}. This report will be saved
              to your history.
            </p>
          )}
          {user === null && configured && (
            <>
              <div className="mt-4 flex flex-wrap gap-2">
                <Link
                  to="/signin"
                  className="inline-flex min-h-[44px] items-center justify-center gap-2 rounded-md border border-line bg-surface px-5 font-semibold text-ink transition-colors duration-150 hover:border-muted"
                >
                  Sign in
                </Link>
                <Link
                  to="/signin?mode=signup"
                  className="inline-flex min-h-[44px] items-center justify-center gap-2 rounded-md border border-line bg-surface px-5 font-semibold text-ink transition-colors duration-150 hover:border-muted"
                >
                  Create account
                </Link>
              </div>
              <p className="mt-2 text-sm text-muted">
                Keep a history of your reports, saved for 30 days.
              </p>
            </>
          )}
        </form>
      </Card>

      {loading && (
        <Card className="mt-6">
          <div role="status" className="flex items-start gap-3">
            <LoaderCircle
              className="mt-1 size-5 shrink-0 motion-safe:animate-spin"
              aria-hidden="true"
            />
            <div className="flex-1">
              <p className="font-serif text-lg font-semibold">
                Analyzing {hostOf(url.trim())}
              </p>
              <p aria-hidden="true" className="tnum mt-0.5 text-sm text-muted">
                {elapsed}s elapsed
              </p>
              <p className="mt-2 text-sm text-muted">
                Fetching the page, running checks, measuring performance, and writing
                suggestions. Usually under 40 seconds.
              </p>
              <div className="mt-3">
                <Button variant="secondary" onClick={onCancel}>
                  Cancel
                </Button>
              </div>
            </div>
          </div>
        </Card>
      )}

      {!loading && error !== null && (
        <div className="mt-6">
          <ErrorPanel error={error} onRetry={onRetry} />
        </div>
      )}

      {report !== null && (
        <section aria-label="Analysis report" className="mt-10">
          <Breadcrumbs items={[{ label: "Analyze" }, { label: hostOf(report.url) }]} />
          <div className="mt-2">
            <Report
              key={report.request_id}
              report={report}
              heading={`Report for ${hostOf(report.url)}`}
              caption={`Fetched ${new Date(report.fetched_at).toLocaleString()} · Report ${report.request_id}`}
              headingRef={reportHeading}
            />
          </div>
        </section>
      )}

      <section aria-labelledby="how-it-works" className="mt-16">
        <h2 id="how-it-works" className="font-serif text-2xl font-semibold">
          How it works
        </h2>
        <ol className="mt-6 grid gap-8 sm:grid-cols-3">
          <li>
            <p className="tnum font-serif text-4xl font-semibold text-accent">01</p>
            <h3 className="mt-2 font-serif text-lg font-semibold">Paste a public URL</h3>
            <p className="mt-1 text-sm text-muted">
              Enter any public website or landing page address, plus optional brand voice
              for the rewrite suggestions.
            </p>
          </li>
          <li>
            <p className="tnum font-serif text-4xl font-semibold text-accent">02</p>
            <h3 className="mt-2 font-serif text-lg font-semibold">We run the checks</h3>
            <p className="mt-1 text-sm text-muted">
              The backend fetches the page, runs SEO, technical, and accessibility rules
              plus Google PageSpeed, and ranks every issue by severity and confidence.
            </p>
          </li>
          <li>
            <p className="tnum font-serif text-4xl font-semibold text-accent">03</p>
            <h3 className="mt-2 font-serif text-lg font-semibold">You get a ranked fix list</h3>
            <p className="mt-1 text-sm text-muted">
              Each fix shows the evidence, why it matters, and what to change, with
              copy ready AI rewrites labeled for testing.
            </p>
          </li>
        </ol>
      </section>

      <section aria-labelledby="what-we-check" className="mt-16">
        <h2 id="what-we-check" className="font-serif text-2xl font-semibold">
          What we check
        </h2>
        <div className="mt-6 grid gap-8 sm:grid-cols-2">
          {CHECK_GROUPS.map((group) => (
            <div key={group.title}>
              <h3 className="font-serif text-lg font-semibold">{group.title}</h3>
              <ul className="mt-2 list-disc space-y-1 pl-5 text-sm text-muted">
                {group.items.map((item) => (
                  <li key={item}>{item}</li>
                ))}
              </ul>
            </div>
          ))}
        </div>
      </section>

      <section aria-labelledby="what-we-cannot-do" className="mt-16">
        <h2 id="what-we-cannot-do" className="font-serif text-2xl font-semibold">
          What we cannot do yet
        </h2>
        <ul className="mt-6 list-disc space-y-2 pl-5 text-sm text-muted">
          {LIMITS.map((limit) => (
            <li key={limit}>{limit}</li>
          ))}
        </ul>
      </section>

      <section aria-label="Example report" className="mt-16">
        <Report
          report={exampleReport}
          heading="Example report"
          idPrefix="example"
          caption="A plumbing homepage built from the full_success.json contract fixture. Sample data, not a real customer."
        />
      </section>
    </Container>
  );
}
