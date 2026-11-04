import { useEffect, useState } from "react";
import type { FormEvent } from "react";
import { Navigate, useNavigate } from "react-router-dom";
import { useAuth } from "../auth/AuthContext";
import Alert from "../components/Alert";
import Breadcrumbs from "../components/Breadcrumbs";
import Button from "../components/Button";
import Card from "../components/Card";
import Container from "../components/Container";
import Input from "../components/Input";
import Textarea from "../components/Textarea";
import { AnalyzeError, deleteAccount, saveProfile } from "../lib/api";
import { useDocumentHead } from "../lib/head";
import { metaForPath } from "../lib/pages";
import type { BusinessProfile, BusinessSize } from "../types/api";
import { validateRequired } from "./Onboarding";

const SIZES: BusinessSize[] = ["Just me", "2 to 10", "11 to 50", "51 to 200", "Over 200"];

export default function Settings() {
  const meta = metaForPath("/settings");
  useDocumentHead(meta.fullTitle, meta.description, meta.path);
  const { user, ready, profile, profileLoaded, signOut, getToken, refreshProfile } =
    useAuth();
  const navigate = useNavigate();
  const [form, setForm] = useState<BusinessProfile | null>(null);
  const [formError, setFormError] = useState("");
  const [failed, setFailed] = useState("");
  const [saved, setSaved] = useState(false);
  const [busy, setBusy] = useState(false);
  const [signingOut, setSigningOut] = useState(false);
  const [confirmingDelete, setConfirmingDelete] = useState(false);
  const [deleting, setDeleting] = useState(false);

  useEffect(() => {
    if (profile !== null && form === null) setForm(profile);
  }, [profile, form]);

  if (ready && user === null) return <Navigate to="/login" replace />;

  function set<K extends keyof BusinessProfile>(key: K, value: BusinessProfile[K]) {
    setForm((current) => (current === null ? current : { ...current, [key]: value }));
  }

  async function onSave(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (form === null) return;
    const error = validateRequired(form);
    if (error !== "") {
      setFormError(error);
      setSaved(false);
      return;
    }
    setBusy(true);
    setFailed("");
    setSaved(false);
    try {
      const token = await getToken();
      if (token === null) throw new Error("missing token");
      const response = await saveProfile(token, form);
      if (response.profile !== null) setForm(response.profile);
      await refreshProfile();
      setSaved(true);
    } catch (unknown) {
      setFailed(
        unknown instanceof AnalyzeError ? unknown.message : "Could not save. Try again.",
      );
    } finally {
      setBusy(false);
    }
  }

  async function onSignOut() {
    setSigningOut(true);
    setFailed("");
    try {
      await signOut();
      navigate("/");
    } catch {
      setFailed("Sign out failed. Try again.");
    } finally {
      setSigningOut(false);
    }
  }

  async function onDeleteAccount() {
    setDeleting(true);
    setFailed("");
    try {
      const token = await getToken();
      if (token === null) throw new Error("missing token");
      await deleteAccount(token);
      await signOut();
      navigate("/");
    } catch (unknown) {
      setFailed(
        unknown instanceof AnalyzeError
          ? unknown.message
          : "Could not delete your account. Try again.",
      );
    } finally {
      setDeleting(false);
    }
  }

  const selectClass =
    "min-h-[44px] w-full rounded-md border border-line bg-surface px-3 text-ink transition-colors duration-150 hover:border-muted";

  return (
    <Container className="py-10">
      <Breadcrumbs items={[{ label: "Home", href: "/" }, { label: meta.shortTitle }]} />
      <h1 className="mt-2 font-serif text-3xl font-semibold">{meta.shortTitle}</h1>
      <p className="mt-2 max-w-2xl text-muted">
        Signed in as {user?.displayName ?? user?.email ?? "your account"}.
      </p>
      <div className="mt-8 max-w-2xl space-y-4">
        {failed !== "" && (
          <Alert tone="error" title="Something went wrong.">
            {failed}
          </Alert>
        )}
        {saved && <Alert tone="success" title="Profile saved." />}
        <Card>
          <p className="font-semibold">Edit profile</p>
          {!profileLoaded || form === null ? (
            <p className="mt-2 text-sm text-muted">Loading profile…</p>
          ) : (
            <form onSubmit={onSave} noValidate className="mt-4">
              <div className="space-y-4">
                <Input
                  id="settings-business"
                  label="Business name"
                  value={form.business_name}
                  onChange={(event) => set("business_name", event.target.value)}
                />
                <Input
                  id="settings-website"
                  label="Website"
                  type="url"
                  value={form.website}
                  onChange={(event) => set("website", event.target.value)}
                />
                <Input
                  id="settings-industry"
                  label="Industry"
                  value={form.industry}
                  onChange={(event) => set("industry", event.target.value)}
                />
                <div className="grid gap-4 sm:grid-cols-2">
                  <Input
                    id="settings-city"
                    label="City"
                    value={form.city}
                    onChange={(event) => set("city", event.target.value)}
                  />
                  <Input
                    id="settings-country"
                    label="Country"
                    value={form.country}
                    onChange={(event) => set("country", event.target.value)}
                  />
                </div>
                <div>
                  <label htmlFor="settings-size" className="mb-1 block text-sm font-semibold">
                    Business size
                  </label>
                  <select
                    id="settings-size"
                    value={form.size}
                    onChange={(event) => set("size", event.target.value as BusinessSize)}
                    className={selectClass}
                  >
                    {SIZES.map((size) => (
                      <option key={size} value={size}>
                        {size}
                      </option>
                    ))}
                  </select>
                </div>
                <Input
                  id="settings-role"
                  label="Your role"
                  value={form.role}
                  onChange={(event) => set("role", event.target.value)}
                />
                <Textarea
                  id="settings-usage"
                  label="How do you plan to use this site? (optional)"
                  value={form.usage_plan}
                  onChange={(event) => set("usage_plan", event.target.value)}
                />
                <Input
                  id="settings-profession"
                  label="Profession (optional)"
                  value={form.profession}
                  onChange={(event) => set("profession", event.target.value)}
                />
                <Input
                  id="settings-referral"
                  label="How did you find us? (optional)"
                  value={form.referral_source}
                  onChange={(event) => set("referral_source", event.target.value)}
                />
                {form.help_feedback !== "" && (
                  <Textarea
                    id="settings-feedback"
                    label="How did it help you?"
                    value={form.help_feedback}
                    onChange={(event) => set("help_feedback", event.target.value)}
                  />
                )}
                {formError !== "" && (
                  <p role="alert" className="text-sm font-semibold text-sev-high">
                    {formError}
                  </p>
                )}
                <div>
                  <Button type="submit" loading={busy}>
                    Save changes
                  </Button>
                </div>
              </div>
            </form>
          )}
        </Card>
        <Card>
          <p className="font-semibold">Sign out</p>
          <p className="mt-1 text-sm text-muted">Sign out on this device.</p>
          <div className="mt-4">
            <Button variant="secondary" loading={signingOut} onClick={() => void onSignOut()}>
              Sign out
            </Button>
          </div>
        </Card>
        <Card>
          <p className="font-semibold">Delete your account</p>
          <p className="mt-1 text-sm text-muted">
            Removes your account, business profile, every saved report, and your contact
            messages. This cannot be undone.
          </p>
          {confirmingDelete ? (
            <div className="mt-4 flex flex-wrap gap-2">
              <Button
                variant="secondary"
                loading={deleting}
                onClick={() => void onDeleteAccount()}
              >
                Yes, delete everything
              </Button>
              <Button variant="secondary" onClick={() => setConfirmingDelete(false)}>
                Cancel
              </Button>
            </div>
          ) : (
            <div className="mt-4">
              <Button variant="secondary" onClick={() => setConfirmingDelete(true)}>
                Delete my account
              </Button>
            </div>
          )}
        </Card>
      </div>
    </Container>
  );
}
