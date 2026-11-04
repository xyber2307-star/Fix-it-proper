import { useEffect, useRef, useState } from "react";
import type { FormEvent } from "react";
import { Link, Navigate } from "react-router-dom";
import { LoaderCircle } from "lucide-react";
import { useAuth } from "../auth/AuthContext";
import Alert from "../components/Alert";
import Badge from "../components/Badge";
import Breadcrumbs from "../components/Breadcrumbs";
import Button from "../components/Button";
import Card from "../components/Card";
import Container from "../components/Container";
import Input from "../components/Input";
import { AnalyzeError, analyzeCreative, improveCreative } from "../lib/api";
import { useDocumentHead } from "../lib/head";
import { metaForPath } from "../lib/pages";
import type { CreativePlatform, CreativeResponse, Issue } from "../types/api";

const REQUEST_TIMEOUT_MS = 90000;

const PLATFORMS: { value: CreativePlatform; label: string }[] = [
  { value: "instagram_post", label: "Instagram post (1:1)" },
  { value: "instagram_story", label: "Instagram story (9:16)" },
  { value: "facebook_post", label: "Facebook post (1200:630)" },
  { value: "x_post", label: "X post (16:9)" },
  { value: "youtube_thumbnail", label: "YouTube thumbnail (16:9)" },
];

function platformLabel(value: string): string {
  return PLATFORMS.find((entry) => entry.value === value)?.label ?? value;
}

function CreativeIssueCard({ issue }: { issue: Issue }) {
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
              Measurement
            </p>
            <code className="mt-1 block break-words rounded-sm bg-paper px-2 py-1 font-mono text-sm">
              {issue.evidence.value}
            </code>
          </div>
          <details className="mt-2">
            <summary className="inline-block min-h-[44px] cursor-pointer py-3 font-semibold text-accent">
              Explain this
            </summary>
            <dl className="grid gap-3 text-sm sm:grid-cols-2">
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
          </details>
        </div>
      </div>
    </Card>
  );
}

export default function Creative() {
  const meta = metaForPath("/creative");
  useDocumentHead(meta.fullTitle, meta.description, meta.path);
  const { user, ready, profileLoaded, profileComplete, getToken } = useAuth();
  const [platform, setPlatform] = useState<CreativePlatform>("instagram_post");
  const [goal, setGoal] = useState("");
  const [youtubeUrl, setYoutubeUrl] = useState("");
  const [image, setImage] = useState<File | null>(null);
  const [preview, setPreview] = useState("");
  const [inputError, setInputError] = useState("");
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<CreativeResponse | null>(null);
  const [error, setError] = useState<AnalyzeError | null>(null);
  const [headline, setHeadline] = useState("");
  const [subtext, setSubtext] = useState("");
  const [cta, setCta] = useState("");
  const [improving, setImproving] = useState(false);
  const [improvedUrl, setImprovedUrl] = useState("");
  const [improveError, setImproveError] = useState("");
  const controllerRef = useRef<AbortController | null>(null);

  useEffect(() => {
    return () => {
      if (preview !== "") URL.revokeObjectURL(preview);
      if (improvedUrl !== "") URL.revokeObjectURL(improvedUrl);
    };
  }, [preview, improvedUrl]);

  if (ready && user === null) return <Navigate to="/login" replace />;
  if (ready && profileLoaded && !profileComplete) {
    return <Navigate to="/onboarding" replace />;
  }

  function onFile(event: React.ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0] ?? null;
    setImage(file);
    setYoutubeUrl("");
    setInputError("");
    if (preview !== "") URL.revokeObjectURL(preview);
    setPreview(file === null ? "" : URL.createObjectURL(file));
  }

  function onYoutubeChange(value: string) {
    setYoutubeUrl(value);
    if (value.trim() !== "") {
      setImage(null);
      if (preview !== "") URL.revokeObjectURL(preview);
      setPreview("");
    }
  }

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (image === null && youtubeUrl.trim() === "") {
      setInputError("Upload an image or paste a YouTube link, not both and not neither.");
      return;
    }
    if (image !== null && image.size > 10 * 1024 * 1024) {
      setInputError("The image is larger than 10 MB.");
      return;
    }
    setInputError("");
    setLoading(true);
    setError(null);
    setResult(null);
    setImprovedUrl("");
    setImproveError("");
    const controller = new AbortController();
    controllerRef.current = controller;
    const timer = window.setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS);
    try {
      const token = await getToken();
      if (token === null) throw new Error("missing token");
      const response = await analyzeCreative(
        token,
        { platform, goal: goal.trim(), youtubeUrl: youtubeUrl.trim(), image },
        controller.signal,
      );
      setResult(response);
      if (response.review !== null) {
        setHeadline(response.review.suggested_headline);
        setSubtext(response.review.suggested_subtext);
        setCta(response.review.suggested_cta);
      }
    } catch (unknown) {
      if (unknown instanceof DOMException && unknown.name === "AbortError") {
        setError(
          new AnalyzeError("The request timed out. Try again in a minute.", "TIMEOUT", true, 0),
        );
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

  async function onImprove(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (image === null) return;
    if (headline.trim() === "") {
      setImproveError("A headline is required.");
      return;
    }
    setImproving(true);
    setImproveError("");
    const controller = new AbortController();
    const timer = window.setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS);
    try {
      const token = await getToken();
      if (token === null) throw new Error("missing token");
      const blob = await improveCreative(
        token,
        { image, headline: headline.trim(), subtext: subtext.trim(), cta: cta.trim() },
        controller.signal,
      );
      if (improvedUrl !== "") URL.revokeObjectURL(improvedUrl);
      setImprovedUrl(URL.createObjectURL(blob));
    } catch (unknown) {
      setImproveError(
        unknown instanceof AnalyzeError ? unknown.message : "Could not render the image. Try again.",
      );
    } finally {
      window.clearTimeout(timer);
      setImproving(false);
    }
  }

  const selectClass =
    "min-h-[44px] w-full rounded-md border border-line bg-surface px-3 text-ink transition-colors duration-150 hover:border-muted";

  return (
    <Container className="py-10">
      <Breadcrumbs items={[{ label: "Home", href: "/" }, { label: meta.shortTitle }]} />
      <h1 className="mt-2 font-serif text-3xl font-semibold">{meta.shortTitle}</h1>
      <p className="mt-2 max-w-2xl text-muted">
        Upload an ad image or paste a public YouTube link. Deterministic checks measure
        shape, size, brightness, and video page basics, then an AI review suggests ranked
        changes. Nothing is auto applied.
      </p>

      <Card className="mt-6">
        <form onSubmit={onSubmit} noValidate>
          <div className="space-y-4">
            <div>
              <label htmlFor="creative-platform" className="mb-1 block text-sm font-semibold">
                Platform
              </label>
              <select
                id="creative-platform"
                value={platform}
                onChange={(event) => setPlatform(event.target.value as CreativePlatform)}
                className={selectClass}
              >
                {PLATFORMS.map((entry) => (
                  <option key={entry.value} value={entry.value}>
                    {entry.label}
                  </option>
                ))}
              </select>
            </div>
            <Input
              id="creative-goal"
              label="Goal (optional)"
              placeholder="Get spring bookings, grow channel subscribers"
              value={goal}
              onChange={(event) => setGoal(event.target.value)}
            />
            <div>
              <label htmlFor="creative-image" className="mb-1 block text-sm font-semibold">
                Ad image (JPEG, PNG, or WebP, max 10 MB)
              </label>
              <input
                id="creative-image"
                type="file"
                accept="image/jpeg,image/png,image/webp"
                onChange={onFile}
                className="block min-h-[44px] w-full text-sm"
              />
              {preview !== "" && (
                <img
                  src={preview}
                  alt="Uploaded creative preview"
                  className="mt-3 max-h-64 rounded-md border border-line"
                />
              )}
            </div>
            <Input
              id="creative-youtube"
              label="Or a YouTube link"
              type="url"
              placeholder="https://www.youtube.com/watch?v=…"
              value={youtubeUrl}
              onChange={(event) => onYoutubeChange(event.target.value)}
              hint="Public video pages only. Checklist based, not a performance forecast."
            />
            {inputError !== "" && (
              <p role="alert" className="text-sm font-semibold text-sev-high">
                {inputError}
              </p>
            )}
            <div>
              <Button type="submit" loading={loading}>
                {loading ? "Reviewing…" : "Review creative"}
              </Button>
            </div>
          </div>
        </form>
      </Card>

      {loading && (
        <Card className="mt-6">
          <div role="status" className="flex items-start gap-3">
            <LoaderCircle
              className="mt-1 size-5 shrink-0 motion-safe:animate-spin"
              aria-hidden="true"
            />
            <p className="font-serif text-lg font-semibold">Reviewing your creative…</p>
          </div>
        </Card>
      )}

      {error !== null && (
        <div className="mt-6">
          <Alert tone="error" title="Review failed.">
            {error.message}{" "}
            {error.code === "UNAUTHORIZED" && (
              <Link to="/login" className="underline underline-offset-4">
                Sign in again.
              </Link>
            )}
          </Alert>
        </div>
      )}

      {result !== null && (
        <div className="mt-10 space-y-8">
          <div>
            <h2 className="font-serif text-2xl font-semibold">
              Results for {platformLabel(result.platform)}
            </h2>
            <p className="mt-1 text-sm text-muted">
              Source: {result.source === "image" ? "uploaded image" : "YouTube link"} · Data:{" "}
              {result.data_quality}
            </p>
            {result.data_quality !== "full" && (
              <div className="mt-4">
                <Alert tone="warning" title="Partial data: some checks could not run.">
                  Results below are limited.
                </Alert>
              </div>
            )}
            <p className="mt-4 text-lg">{result.summary}</p>
          </div>

          <section aria-label="Ranked changes">
            <h3 className="font-serif text-xl font-semibold">Ranked changes</h3>
            {result.issues.length === 0 ? (
              <div className="mt-4">
                <Alert tone="success" title="No issues found.">
                  The creative passed every check that ran.
                </Alert>
              </div>
            ) : (
              <ol className="mt-4 space-y-4">
                {result.issues.map((issue) => (
                  <li key={issue.id}>
                    <CreativeIssueCard issue={issue} />
                  </li>
                ))}
              </ol>
            )}
          </section>

          <section aria-label="AI review">
            <h3 className="font-serif text-xl font-semibold">AI review</h3>
            {result.review === null ? (
              <div className="mt-4">
                <Alert tone="info" title="No AI review in this result.">
                  The deterministic checks above still stand on their own.
                </Alert>
              </div>
            ) : (
              <Card className="mt-4">
                <p>{result.review.summary}</p>
                <ol className="mt-3 list-decimal space-y-1 pl-5 text-sm">
                  {result.review.changes.map((change) => (
                    <li key={change}>{change}</li>
                  ))}
                </ol>
                <p className="mt-3 text-sm font-semibold text-muted">{result.review.label}</p>
              </Card>
            )}
          </section>

          {result.limitations.length > 0 && (
            <Alert tone="info" title="What could not be checked">
              <ul className="list-disc space-y-1 pl-5">
                {result.limitations.map((limitation) => (
                  <li key={limitation}>{limitation}</li>
                ))}
              </ul>
            </Alert>
          )}

          {result.source === "image" && (
            <section aria-label="Improved version">
              <h3 className="font-serif text-xl font-semibold">Generate improved version</h3>
              <p className="mt-1 text-sm text-muted">
                The texts below are added as real overlays on your image. Edit them first if
                you like.
              </p>
              <Card className="mt-4">
                <form onSubmit={onImprove} noValidate>
                  <div className="space-y-4">
                    <Input
                      id="improve-headline"
                      label="Headline"
                      value={headline}
                      onChange={(event) => setHeadline(event.target.value)}
                    />
                    <Input
                      id="improve-subtext"
                      label="Subtext (optional)"
                      value={subtext}
                      onChange={(event) => setSubtext(event.target.value)}
                    />
                    <Input
                      id="improve-cta"
                      label="Call to action (optional)"
                      value={cta}
                      onChange={(event) => setCta(event.target.value)}
                    />
                    {improveError !== "" && (
                      <p role="alert" className="text-sm font-semibold text-sev-high">
                        {improveError}
                      </p>
                    )}
                    <div>
                      <Button type="submit" loading={improving}>
                        {improving ? "Rendering…" : "Generate improved version"}
                      </Button>
                    </div>
                  </div>
                </form>
              </Card>
              {improvedUrl !== "" && (
                <Card className="mt-4">
                  <img
                    src={improvedUrl}
                    alt="Improved creative with text overlays"
                    className="max-h-96 rounded-md border border-line"
                  />
                  <p className="mt-3">
                    <a
                      href={improvedUrl}
                      download="improved-creative.png"
                      className="inline-flex min-h-[44px] items-center justify-center gap-2 rounded-md border border-line bg-surface px-5 font-semibold text-ink transition-colors duration-150 hover:border-muted"
                    >
                      Download PNG
                    </a>
                  </p>
                </Card>
              )}
            </section>
          )}
        </div>
      )}
    </Container>
  );
}
