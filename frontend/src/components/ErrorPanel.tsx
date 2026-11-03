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
    case "FETCH_FAILED":
      return "That page could not be fetched.";
    case "NOT_HTML":
      return "That address is not a web page.";
    case "TOO_MANY_REDIRECTS":
      return "That address redirects too much.";
    case "RESPONSE_TOO_LARGE":
      return "That page is too large.";
    case "NOT_FOUND":
      return "The analysis server did not answer.";
    case "INTERNAL_ERROR":
      return "Something went wrong on our side.";
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
    case "FETCH_FAILED":
      return "The site may be down, the page may be gone, or the address may be wrong. Check that it loads in your browser, or try the site homepage.";
    case "NOT_HTML":
      return "Use an address that returns a web page, not a file download.";
    case "TOO_MANY_REDIRECTS":
      return "The address bounces between pages without settling. Try the final address or the site homepage.";
    case "RESPONSE_TOO_LARGE":
      return "The page is larger than 3 MB. Try a lighter page on the same site.";
    case "NOT_FOUND":
      return "The app sent its request to an address the server does not recognize. The site owner should check the configured server address.";
    case "INTERNAL_ERROR":
      return "This is our fault, not yours. Try again in a minute.";
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
