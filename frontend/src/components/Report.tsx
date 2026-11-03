import { useEffect, useRef, useState } from "react";
import type { Ref } from "react";
import Alert from "./Alert";
import Badge from "./Badge";
import Button from "./Button";
import Card from "./Card";
import type {
  AnalyzeResponse,
  DataQuality,
  EvidenceType,
  Issue,
  IssueCategory,
  Rewrite,
  RewriteTarget,
  Score,
  Severity,
} from "../types/api";

const EVIDENCE_LABELS: Record<EvidenceType, string> = {
  text: "Exact text",
  selector: "Selector",
  metric: "Measurement",
};

const TARGET_LABELS: Record<RewriteTarget, string> = {
  title: "Page title",
  meta_description: "Meta description",
  h1: "Main heading",
  cta: "Call to action",
};

const CATEGORY_LABELS: Record<IssueCategory, string> = {
  seo: "SEO",
  content: "Content",
  technical: "Technical",
  performance: "Performance",
  accessibility: "Accessibility",
};

const SEVERITY_ORDER: Record<Severity, number> = { high: 0, medium: 1, low: 2 };

type SortKey = "recommended" | "severity" | "confidence";

export function hostOf(raw: string): string {
  try {
    return new URL(raw).hostname;
  } catch {
    return raw;
  }
}

function IssueCard({ issue }: { issue: Issue }) {
  return (
    <Card>
      <div className="flex items-start gap-3">
        <span className="tnum font-serif text-xl font-semibold text-muted">
          {issue.impact_rank}
        </span>
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <Badge severity={issue.severity} />
            <h4 className="font-serif text-lg font-semibold leading-snug">{issue.title}</h4>
          </div>
          <div className="mt-3">
            <p className="text-xs font-semibold uppercase tracking-wide text-muted">
              {EVIDENCE_LABELS[issue.evidence.type]}
            </p>
            <code className="mt-1 block break-words rounded-sm bg-paper px-2 py-1 font-mono text-sm">
              {issue.evidence.value}
            </code>
          </div>
          <dl className="mt-3 grid gap-3 text-sm sm:grid-cols-2">
            <div>
              <dt className="font-semibold">Why it matters</dt>
              <dd className="mt-0.5">{issue.why_it_matters}</dd>
            </div>
            <div>
              <dt className="font-semibold">Suggested fix</dt>
              <dd className="mt-0.5">{issue.suggested_fix}</dd>
            </div>
          </dl>
          <p className="mt-2 text-sm text-muted">
            Source: {issue.source} · {Math.round(issue.confidence * 100)}% confidence
          </p>
        </div>
      </div>
    </Card>
  );
}

function FixesSection({ issues, idPrefix }: { issues: Issue[]; idPrefix: string }) {
  const [category, setCategory] = useState("all");
  const [severity, setSeverity] = useState("all");
  const [sort, setSort] = useState<SortKey>("recommended");
  const filtered = issues
    .filter((issue) => category === "all" || issue.category === category)
    .filter((issue) => severity === "all" || issue.severity === severity)
    .slice()
    .sort((left, right) => {
      if (sort === "severity") {
        return (
          SEVERITY_ORDER[left.severity] - SEVERITY_ORDER[right.severity] ||
          left.impact_rank - right.impact_rank
        );
      }
      if (sort === "confidence") {
        return right.confidence - left.confidence || left.impact_rank - right.impact_rank;
      }
      return left.impact_rank - right.impact_rank;
    });
  const selectClass =
    "min-h-[44px] rounded-md border border-line bg-surface px-3 text-ink transition-colors duration-150 hover:border-muted";
  return (
    <section aria-labelledby={`${idPrefix}-fixes-heading`}>
      <h3 id={`${idPrefix}-fixes-heading`} className="font-serif text-xl font-semibold">
        Ranked fixes
      </h3>
      <div className="mt-4 grid gap-3 sm:grid-cols-3">
        <div>
          <label htmlFor={`${idPrefix}-filter-category`} className="mb-1 block text-sm font-semibold">
            Category
          </label>
          <select
            id={`${idPrefix}-filter-category`}
            value={category}
            onChange={(event) => setCategory(event.target.value)}
            className={`w-full ${selectClass}`}
          >
            <option value="all">All categories</option>
            {(Object.keys(CATEGORY_LABELS) as IssueCategory[]).map((value) => (
              <option key={value} value={value}>
                {CATEGORY_LABELS[value]}
              </option>
            ))}
          </select>
        </div>
        <div>
          <label htmlFor={`${idPrefix}-filter-severity`} className="mb-1 block text-sm font-semibold">
            Severity
          </label>
          <select
            id={`${idPrefix}-filter-severity`}
            value={severity}
            onChange={(event) => setSeverity(event.target.value)}
            className={`w-full ${selectClass}`}
          >
            <option value="all">All severities</option>
            <option value="high">High</option>
            <option value="medium">Medium</option>
            <option value="low">Low</option>
          </select>
        </div>
        <div>
          <label htmlFor={`${idPrefix}-sort-order`} className="mb-1 block text-sm font-semibold">
            Sort by
          </label>
          <select
            id={`${idPrefix}-sort-order`}
            value={sort}
            onChange={(event) => setSort(event.target.value as SortKey)}
            className={`w-full ${selectClass}`}
          >
            <option value="recommended">Recommended order</option>
            <option value="severity">Severity</option>
            <option value="confidence">Confidence</option>
          </select>
        </div>
      </div>
      <p role="status" className="mt-3 text-sm text-muted">
        Showing {filtered.length} of {issues.length} fixes.
      </p>
      {filtered.length === 0 ? (
        <div className="mt-4">
          <Alert tone="info" title="No fixes match these filters.">
            <div className="mt-3">
              <Button
                variant="secondary"
                onClick={() => {
                  setCategory("all");
                  setSeverity("all");
                }}
              >
                Clear filters
              </Button>
            </div>
          </Alert>
        </div>
      ) : (
        <ol className="mt-4 space-y-4">
          {filtered.map((issue) => (
            <li key={issue.id}>
              <IssueCard issue={issue} />
            </li>
          ))}
        </ol>
      )}
    </section>
  );
}

function CopyButton({ text }: { text: string }) {
  const [copied, setCopied] = useState(false);
  const [failed, setFailed] = useState(false);
  const timer = useRef<number | null>(null);
  useEffect(() => {
    return () => {
      if (timer.current !== null) window.clearTimeout(timer.current);
    };
  }, []);

  function showMessage(ok: boolean) {
    setCopied(ok);
    setFailed(!ok);
    if (timer.current !== null) window.clearTimeout(timer.current);
    timer.current = window.setTimeout(() => {
      setCopied(false);
      setFailed(false);
    }, 2000);
  }

  async function onCopy() {
    try {
      await navigator.clipboard.writeText(text);
      showMessage(true);
      return;
    } catch {
      // Clipboard API unavailable (permissions, old browser): fall through.
    }
    try {
      const area = document.createElement("textarea");
      area.value = text;
      document.body.appendChild(area);
      area.select();
      const ok = document.execCommand("copy");
      document.body.removeChild(area);
      showMessage(ok);
    } catch {
      showMessage(false);
    }
  }

  return (
    <span className="inline-flex min-h-[44px] items-center gap-2">
      <Button variant="secondary" onClick={onCopy}>
        Copy
      </Button>
      {copied && (
        <span role="status" className="text-sm font-semibold text-accent">
          Copied
        </span>
      )}
      {failed && (
        <span role="status" className="text-sm font-semibold text-sev-high">
          Copy failed, select the text manually.
        </span>
      )}
    </span>
  );
}

function RewriteBlock({ rewrite, first }: { rewrite: Rewrite; first: boolean }) {
  const cells = [{ label: "Original", text: rewrite.original }].concat(
    rewrite.variants.map((variant, index) => ({ label: `Variant ${index + 1}`, text: variant })),
  );
  return (
    <section
      aria-label={TARGET_LABELS[rewrite.target]}
      className={first ? "" : "border-t border-line pt-5"}
    >
      <h4 className="font-serif text-lg font-semibold">{TARGET_LABELS[rewrite.target]}</h4>
      <div className="mt-3 grid gap-3 sm:grid-cols-2">
        {cells.map((cell) => (
          <div key={cell.label} className="rounded-md border border-line bg-surface p-4">
            <p className="text-xs font-semibold uppercase tracking-wide text-muted">
              {cell.label}
            </p>
            <p className="mt-1 break-words text-sm">{cell.text}</p>
            <div className="mt-3">
              <CopyButton text={cell.text} />
            </div>
          </div>
        ))}
      </div>
      <p className="mt-2 text-sm font-semibold text-muted">{rewrite.label}</p>
    </section>
  );
}

function RewritesSection({
  rewrites,
  idPrefix,
}: {
  rewrites: Rewrite[];
  idPrefix: string;
}) {
  return (
    <section aria-labelledby={`${idPrefix}-rewrites-heading`}>
      <h3 id={`${idPrefix}-rewrites-heading`} className="font-serif text-xl font-semibold">
        Rewrites
      </h3>
      <p className="mt-2 text-sm text-muted">
        Test one variant at a time against the original, keep everything else unchanged, and
        give it at least two weeks before deciding.
      </p>
      {rewrites.length === 0 ? (
        <div className="mt-4">
          <Alert tone="info" title="No rewrites in this report.">
            Rewrites need page content and a configured AI key.
          </Alert>
        </div>
      ) : (
        <div className="mt-4 space-y-5">
          {rewrites.map((rewrite, index) => (
            <RewriteBlock key={rewrite.target} rewrite={rewrite} first={index === 0} />
          ))}
        </div>
      )}
    </section>
  );
}

function ScoreSection({
  score,
  quality,
  idPrefix,
}: {
  score: Score | undefined | null;
  quality: DataQuality;
  idPrefix: string;
}) {
  if (score === undefined || score === null) {
    const reason =
      quality === "partial"
        ? "Some checks could not run, so no score was computed. The ranked fixes above are the report."
        : "Only page tags could be read, so no score was computed. The ranked fixes above are the report.";
    return (
      <section aria-labelledby={`${idPrefix}-score-heading`}>
        <h3 id={`${idPrefix}-score-heading`} className="font-serif text-xl font-semibold">
          Score
        </h3>
        <div className="mt-4">
          <Alert tone="info" title="Score omitted.">
            {reason}
          </Alert>
        </div>
      </section>
    );
  }
  return (
    <section aria-labelledby={`${idPrefix}-score-heading`}>
      <h3 id={`${idPrefix}-score-heading`} className="font-serif text-xl font-semibold">
        Score
      </h3>
      <Card className="mt-4">
        <p className="tnum font-serif text-5xl font-semibold">{score.value}</p>
        <p className="mt-1 text-sm text-muted">out of 100 · formula {score.formula_version}</p>
        <details className="mt-3">
          <summary className="inline-block min-h-[44px] cursor-pointer py-3 font-semibold text-accent">
            How this score is computed
          </summary>
          <p className="text-sm">
            100 minus 10 per high issue, 5 per medium, 2 per low, floored at 0. The ranked
            fixes matter more than this number.
          </p>
          <dl className="mt-3 grid gap-2 text-sm sm:grid-cols-3">
            {score.components.map((component) => (
              <div key={component.name} className="rounded-md border border-line px-3 py-2">
                <dt className="text-muted">{component.name.replace(/_/g, " ")}</dt>
                <dd className="tnum mt-0.5 font-semibold">−{component.value}</dd>
              </div>
            ))}
          </dl>
        </details>
      </Card>
    </section>
  );
}

interface ReportProps {
  report: AnalyzeResponse;
  heading: string;
  caption?: string;
  headingRef?: Ref<HTMLHeadingElement>;
  idPrefix?: string;
}

export default function Report({
  report,
  heading,
  caption,
  headingRef,
  idPrefix = "report",
}: ReportProps) {
  return (
    <div>
      <h2
        ref={headingRef}
        tabIndex={headingRef === undefined ? undefined : -1}
        className="font-serif text-2xl font-semibold"
      >
        {heading}
      </h2>
      {caption !== undefined && <p className="mt-1 text-sm text-muted">{caption}</p>}

      {report.data_quality !== "full" && (
        <div className="mt-4">
          <Alert
            tone="warning"
            title={
              report.data_quality === "partial"
                ? "Partial data: some checks could not run."
                : "We could only read Open Graph tags. This analysis is limited."
            }
          >
            Results below are limited. See what could not be checked in the limitations
            section.
          </Alert>
        </div>
      )}

      <p className="mt-4 text-lg">{report.summary}</p>

      {report.issues.length === 0 ? (
        <div className="mt-6">
          <Alert tone="success" title="No issues found.">
            The page passed every check that ran.
          </Alert>
        </div>
      ) : (
        <div className="mt-8">
          <FixesSection issues={report.issues} idPrefix={idPrefix} />
        </div>
      )}

      <div className="mt-10">
        <RewritesSection rewrites={report.rewrites} idPrefix={idPrefix} />
      </div>

      {report.limitations.length > 0 && (
        <div className="mt-10">
          <Alert tone="info" title="What could not be checked">
            <ul className="list-disc space-y-1 pl-5">
              {report.limitations.map((limitation) => (
                <li key={limitation}>{limitation}</li>
              ))}
            </ul>
          </Alert>
        </div>
      )}

      <div className="mt-10">
        <ScoreSection score={report.score} quality={report.data_quality} idPrefix={idPrefix} />
      </div>
    </div>
  );
}
