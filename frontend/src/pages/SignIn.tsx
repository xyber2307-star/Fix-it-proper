import { useEffect, useState } from "react";
import type { FormEvent } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { friendlyAuthError, useAuth } from "../auth/AuthContext";
import Alert from "../components/Alert";
import Breadcrumbs from "../components/Breadcrumbs";
import Button from "../components/Button";
import Card from "../components/Card";
import Container from "../components/Container";
import Input from "../components/Input";
import { useDocumentHead } from "../lib/head";
import { metaForPath } from "../lib/pages";

type Mode = "signin" | "signup" | "reset";

function modeFromParam(value: string | null): Mode {
  if (value === "signup" || value === "reset") return value;
  return "signin";
}

export default function SignIn() {
  const meta = metaForPath("/signin");
  useDocumentHead(meta.fullTitle, meta.description, meta.path);
  const { user, ready, configured, signUp, signIn, signInGoogle, sendReset } = useAuth();
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const [mode, setMode] = useState<Mode>(() => modeFromParam(params.get("mode")));
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [formError, setFormError] = useState("");
  const [failed, setFailed] = useState("");
  const [resetSent, setResetSent] = useState(false);
  const [formBusy, setFormBusy] = useState(false);
  const [googleBusy, setGoogleBusy] = useState(false);

  useEffect(() => {
    if (ready && user !== null) navigate("/saved", { replace: true });
  }, [ready, user, navigate]);

  function validEmail(): boolean {
    if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email.trim())) {
      setFormError("Enter a valid email address.");
      return false;
    }
    return true;
  }

  function validate(): boolean {
    if (!validEmail()) return false;
    if (password.length < 6) {
      setFormError("Password must be at least 6 characters.");
      return false;
    }
    setFormError("");
    return true;
  }

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!validate()) return;
    setFormBusy(true);
    setFailed("");
    try {
      if (mode === "signup") {
        await signUp(email.trim(), password);
      } else {
        await signIn(email.trim(), password);
      }
      navigate("/saved");
    } catch (unknown) {
      setFailed(friendlyAuthError(unknown));
    } finally {
      setFormBusy(false);
    }
  }

  async function onReset(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!validEmail()) return;
    setFormBusy(true);
    setFailed("");
    setResetSent(false);
    try {
      await sendReset(email.trim());
      setResetSent(true);
    } catch (unknown) {
      setFailed(friendlyAuthError(unknown));
    } finally {
      setFormBusy(false);
    }
  }

  async function onGoogle() {
    setGoogleBusy(true);
    setFailed("");
    try {
      await signInGoogle();
      navigate("/saved");
    } catch (unknown) {
      setFailed(friendlyAuthError(unknown));
    } finally {
      setGoogleBusy(false);
    }
  }

  function switchMode(next: Mode) {
    setMode(next);
    setFormError("");
    setFailed("");
    setResetSent(false);
  }

  return (
    <Container className="py-10">
      <Breadcrumbs items={[{ label: "Home", href: "/" }, { label: meta.shortTitle }]} />
      <h1 className="mt-2 font-serif text-3xl font-semibold">{meta.shortTitle}</h1>
      <p className="mt-2 max-w-2xl text-muted">
        Sign in to keep a history of your website reports. Saved reports are kept
        for 30 days. See the <Link to="/privacy" className="underline underline-offset-4">Privacy Policy</Link> for
        what is stored.
      </p>
      <div className="mt-8 max-w-2xl space-y-4">
        {!configured && (
          <Alert tone="info" title="Sign in is not configured on this site.">
            The site owner has not added sign in keys yet. Analysis still works without
            an account.
          </Alert>
        )}
        {failed !== "" && (
          <Alert tone="error" title="Something went wrong.">
            {failed}
          </Alert>
        )}
        {resetSent && (
          <Alert tone="success" title="Reset link sent.">
            Check your inbox for a password reset link. It may take a minute to arrive.
          </Alert>
        )}
        {mode === "reset" ? (
          <Card>
            <p className="font-semibold">Reset your password</p>
            <p className="mt-1 text-sm text-muted">
              Enter your account email and we will send you a reset link.
            </p>
            <form onSubmit={onReset} noValidate className="mt-4">
              <div className="space-y-4">
                <Input
                  id="reset-email"
                  label="Email"
                  type="email"
                  autoComplete="email"
                  value={email}
                  onChange={(event) => setEmail(event.target.value)}
                />
                {formError !== "" && (
                  <p role="alert" className="text-sm font-semibold text-sev-high">
                    {formError}
                  </p>
                )}
                <div className="flex flex-wrap gap-2">
                  <Button type="submit" loading={formBusy}>
                    Send reset link
                  </Button>
                  <Button variant="secondary" onClick={() => switchMode("signin")}>
                    Back to sign in
                  </Button>
                </div>
              </div>
            </form>
          </Card>
        ) : (
          <Card>
            <div className="flex gap-2" role="group" aria-label="Sign in or create account">
              <Button
                variant={mode === "signin" ? "primary" : "secondary"}
                onClick={() => switchMode("signin")}
                aria-pressed={mode === "signin"}
              >
                Sign in
              </Button>
              <Button
                variant={mode === "signup" ? "primary" : "secondary"}
                onClick={() => switchMode("signup")}
                aria-pressed={mode === "signup"}
              >
                Create account
              </Button>
            </div>
            <form onSubmit={onSubmit} noValidate className="mt-6">
              <div className="space-y-4">
                <Input
                  id="signin-email"
                  label="Email"
                  type="email"
                  autoComplete="email"
                  value={email}
                  onChange={(event) => setEmail(event.target.value)}
                />
                <Input
                  id="signin-password"
                  label="Password"
                  type="password"
                  autoComplete={mode === "signup" ? "new-password" : "current-password"}
                  value={password}
                  onChange={(event) => setPassword(event.target.value)}
                  hint={mode === "signup" ? "At least 6 characters." : undefined}
                />
                {formError !== "" && (
                  <p role="alert" className="text-sm font-semibold text-sev-high">
                    {formError}
                  </p>
                )}
                <div>
                  <Button type="submit" loading={formBusy}>
                    {mode === "signup" ? "Create account" : "Sign in"}
                  </Button>
                </div>
                {mode === "signin" && (
                  <p className="text-sm">
                    <button
                      type="button"
                      onClick={() => switchMode("reset")}
                      className="underline underline-offset-4"
                    >
                      Forgot password?
                    </button>
                  </p>
                )}
              </div>
            </form>
          </Card>
        )}
        {mode !== "reset" && (
          <Card>
            <Button variant="secondary" loading={googleBusy} onClick={() => void onGoogle()}>
              Continue with Google
            </Button>
          </Card>
        )}
      </div>
    </Container>
  );
}
