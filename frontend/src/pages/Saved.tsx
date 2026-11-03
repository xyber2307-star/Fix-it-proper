import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useAuth } from "../auth/AuthContext";
import Alert from "../components/Alert";
import Breadcrumbs from "../components/Breadcrumbs";
import Button from "../components/Button";
import Card from "../components/Card";
import Container from "../components/Container";
import { AnalyzeError, deleteAccount, deleteReport, fetchReports } from "../lib/api";
import { useDocumentHead } from "../lib/head";
import { metaForPath } from "../lib/pages";
import type { ReportSummary } from "../types/api";

function formatDate(iso: string): string {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return iso;
  return date.toLocaleString(undefined, {
    dateStyle: "medium",
    timeStyle: "short",
  });
}

export default function Saved() {
  const meta = metaForPath("/saved");
  useDocumentHead(meta.fullTitle, meta.description, meta.path);
  const { user, ready, configured, getToken, signOut } = useAuth();
  const navigate = useNavigate();
  const [reports, setReports] = useState<ReportSummary[] | null>(null);
  const [loadError, setLoadError] = useState("");
  const [loadErrorCode, setLoadErrorCode] = useState("");

  function clearError() {
    setLoadError("");
    setLoadErrorCode("");
  }

  function failWith(unknown: unknown, fallback: string) {
    if (unknown instanceof AnalyzeError) {
      setLoadError(unknown.message);
      setLoadErrorCode(unknown.code);
    } else {
      setLoadError(fallback);
      setLoadErrorCode("");
    }
  }
  const [notice, setNotice] = useState("");
  const [confirming, setConfirming] = useState<string | null>(null);
  const [deleting, setDeleting] = useState(false);
  const [confirmingAccount, setConfirmingAccount] = useState(false);
  const [deletingAccount, setDeletingAccount] = useState(false);

  useEffect(() => {
    if (!ready || user === null) return;
    let cancelled = false;
    setReports(null);
    clearError();
    getToken()
      .then((token) => {
        if (token === null) throw new Error("missing token");
        return fetchReports(token);
      })
      .then((list) => {
        if (!cancelled) setReports(list.reports);
      })
      .catch((unknown: unknown) => {
        if (cancelled) return;
        failWith(unknown, "Could not load saved reports. Try again.");
      });
    return () => {
      cancelled = true;
    };
  }, [ready, user, getToken]);

  async function onDelete(id: string) {
    setDeleting(true);
    setNotice("");
    clearError();
    try {
      const token = await getToken();
      if (token === null) throw new Error("missing token");
      await deleteReport(token, id);
      setReports((current) => (current === null ? current : current.filter((entry) => entry.id !== id)));
      setConfirming(null);
      setNotice("Report deleted.");
    } catch (unknown) {
      failWith(unknown, "Could not delete the report. Try again.");
    } finally {
      setDeleting(false);
    }
  }

  async function onDeleteAccount() {
    setDeletingAccount(true);
    setNotice("");
    clearError();
    try {
      const token = await getToken();
      if (token === null) throw new Error("missing token");
      await deleteAccount(token);
      await signOut();
      navigate("/");
    } catch (unknown) {
      failWith(unknown, "Could not delete your account. Try again.");
    } finally {
      setDeletingAccount(false);
    }
  }

  return (
    <Container className="py-10">
      <Breadcrumbs items={[{ label: "Home", href: "/" }, { label: meta.shortTitle }]} />
      <h1 className="mt-2 font-serif text-3xl font-semibold">{meta.shortTitle}</h1>
      <p className="mt-2 max-w-2xl text-muted">
        Reports you run while signed in are saved here for 30 days, then removed
        automatically.
      </p>
      <div className="mt-8 max-w-3xl space-y-4">
        {!ready && <p className="text-muted">Loading saved reports...</p>}
        {ready && !configured && (
          <Alert tone="info" title="Sign in is not configured on this site.">
            The site owner has not added sign in keys yet.
          </Alert>
        )}
        {ready && configured && user === null && (
          <Card>
            <p className="font-semibold">Sign in required.</p>
            <p className="mt-1 text-muted">
              Sign in to see the reports saved to your account.
            </p>
            <p className="mt-4">
              <Link
                to="/signin"
                className="inline-flex min-h-[44px] items-center justify-center gap-2 rounded-md bg-accent px-5 font-semibold text-white transition-colors duration-150 hover:bg-accent-strong"
              >
                Go to sign in
              </Link>
            </p>
          </Card>
        )}
        {notice !== "" && <Alert tone="success" title={notice} />}
        {loadError !== "" && (
          <Alert tone="error" title="Something went wrong.">
            {loadError}
            {loadErrorCode === "UNAUTHORIZED" && (
              <p className="mt-1">
                Your session may have expired.{" "}
                <Link to="/signin" className="underline underline-offset-4">
                  Sign in again.
                </Link>
              </p>
            )}
          </Alert>
        )}
        {ready && user !== null && reports !== null && reports.length === 0 && !loadError && (
          <Card>
            <p className="font-semibold">No saved reports yet.</p>
            <p className="mt-1 text-muted">
              Run an analysis while signed in and it will show up here.{" "}
              <Link to="/" className="underline underline-offset-4">
                Analyze a website
              </Link>
            </p>
          </Card>
        )}
        {reports !== null &&
          reports.map((entry) => (
            <Card key={entry.id}>
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div className="min-w-0">
                  <p className="break-words font-semibold">{entry.url}</p>
                  <p className="mt-1 text-sm text-muted">
                    {formatDate(entry.created_at)} | {entry.issue_count}{" "}
                    {entry.issue_count === 1 ? "issue" : "issues"}
                    {entry.score_value !== null && entry.score_value !== undefined
                      ? ` | Score ${entry.score_value}`
                      : ""}
                    {" | Data: "}
                    {entry.data_quality}
                  </p>
                </div>
                {confirming === entry.id ? (
                  <div className="flex flex-wrap gap-2">
                    <Button
                      variant="secondary"
                      loading={deleting}
                      onClick={() => void onDelete(entry.id)}
                    >
                      Yes, delete
                    </Button>
                    <Button variant="secondary" onClick={() => setConfirming(null)}>
                      Cancel
                    </Button>
                  </div>
                ) : (
                  <Button variant="secondary" onClick={() => setConfirming(entry.id)}>
                    Delete
                  </Button>
                )}
              </div>
              <p className="mt-3 text-sm text-muted">{entry.summary}</p>
            </Card>
          ))}
        {ready && user !== null && (
          <Card>
            <p className="font-semibold">Delete your account</p>
            <p className="mt-1 text-muted">
              Removes your account, every saved report, and your contact messages.
              This cannot be undone.
            </p>
            {confirmingAccount ? (
              <div className="mt-4 flex flex-wrap gap-2">
                <Button
                  variant="secondary"
                  loading={deletingAccount}
                  onClick={() => void onDeleteAccount()}
                >
                  Yes, delete everything
                </Button>
                <Button variant="secondary" onClick={() => setConfirmingAccount(false)}>
                  Cancel
                </Button>
              </div>
            ) : (
              <div className="mt-4">
                <Button variant="secondary" onClick={() => setConfirmingAccount(true)}>
                  Delete my account
                </Button>
              </div>
            )}
          </Card>
        )}
      </div>
    </Container>
  );
}
