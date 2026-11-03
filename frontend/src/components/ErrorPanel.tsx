import Alert from "./Alert";
import Button from "./Button";
import type { AnalyzeError } from "../lib/api";

interface ErrorPanelProps {
  error: AnalyzeError;
  onRetry: () => void;
}

function titleFor(code: string): string {
  switch (code) {
    case "FETCH_BLOCKED":
      return "This site blocked the analysis.";
    case "UNSUPPORTED_SITE":
      return "This site is not supported.";
    case "TIMEOUT":
    case "FETCH_TIMEOUT":
      return "The analysis timed out.";
    case "INVALID_URL":
    case "URL_BLOCKED":
      return "That URL cannot be analyzed.";
    case "RATE_LIMITED":
      return "Too many requests.";
    case "CANCELLED":
      return "Analysis cancelled.";
    case "NETWORK_ERROR":
      return "Could not reach the analysis server.";
    default:
      return "Analysis failed.";
  }
}

function adviceFor(error: AnalyzeError): string {
  switch (error.code) {
    case "FETCH_BLOCKED":
      return "Some sites block automated readers. Try the homepage instead of a deep page, or confirm the site loads in your browser.";
    case "UNSUPPORTED_SITE":
      return "Social media and ad platform pages are out of scope. Use a public website or landing page instead.";
    case "TIMEOUT":
    case "FETCH_TIMEOUT":
      return "The page took too long to fetch or check. A second attempt often succeeds.";
    case "INVALID_URL":
    case "URL_BLOCKED":
      return "Use a full public address starting with http:// or https://.";
    case "RATE_LIMITED":
      return error.retryAfter === undefined
        ? "Wait a little while, then try again."
        : `Try again in about ${error.retryAfter} seconds.`;
    case "CANCELLED":
      return "Nothing was analyzed. Retry whenever you are ready.";
    case "NETWORK_ERROR":
      return "Check your connection and make sure the analysis server is running.";
    default:
      return "Check the URL and try again.";
  }
}

export default function ErrorPanel({ error, onRetry }: ErrorPanelProps) {
  return (
    <Alert tone="error" title={titleFor(error.code)}>
      <p>{error.message}</p>
      <p className="mt-1">{adviceFor(error)}</p>
      {error.retryable && (
        <div className="mt-3">
          <Button variant="secondary" onClick={onRetry}>
            Retry analysis
          </Button>
        </div>
      )}
    </Alert>
  );
}
