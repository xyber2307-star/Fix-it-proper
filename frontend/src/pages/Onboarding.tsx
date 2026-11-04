import { useState } from "react";
import type { FormEvent } from "react";
import { Link, Navigate, useNavigate } from "react-router-dom";
import { friendlyAuthError, useAuth } from "../auth/AuthContext";
import Alert from "../components/Alert";
import Breadcrumbs from "../components/Breadcrumbs";
import Button from "../components/Button";
import Card from "../components/Card";
import Container from "../components/Container";
import Input from "../components/Input";
import Textarea from "../components/Textarea";
import { AnalyzeError, saveProfile } from "../lib/api";
import { useDocumentHead } from "../lib/head";
import { metaForPath } from "../lib/pages";
import type { BusinessProfile, BusinessSize } from "../types/api";

const SIZES: BusinessSize[] = ["Just me", "2 to 10", "11 to 50", "51 to 200", "Over 200"];

const EMPTY_PROFILE: BusinessProfile = {
  business_name: "",
  website: "",
  industry: "",
  city: "",
  country: "",
  size: "Just me",
  role: "",
  usage_plan: "",
  profession: "",
  referral_source: "",
  help_feedback: "",
};

export function validateRequired(profile: BusinessProfile): string {
  if (profile.business_name.trim().length < 2) return "Enter your business name.";
  const site = profile.website.trim();
  if (site.length < 4 || site.includes(" ")) return "Enter your website address.";
  if (profile.industry.trim().length < 2) return "Enter your industry.";
  if (profile.city.trim().length < 2) return "Enter your city.";
  if (profile.country.trim().length < 2) return "Enter your country.";
  if (profile.role.trim().length < 2) return "Enter your role.";
  return "";
}

export default function Onboarding() {
  const meta = metaForPath("/onboarding");
  useDocumentHead(meta.fullTitle, meta.description, meta.path);
  const { user, ready, profileComplete, profileLoaded, getToken, refreshProfile } = useAuth();
  const navigate = useNavigate();
  const [step, setStep] = useState<1 | 2>(1);
  const [form, setForm] = useState<BusinessProfile>(EMPTY_PROFILE);
  const [formError, setFormError] = useState("");
  const [failed, setFailed] = useState("");
  const [busy, setBusy] = useState(false);

  if (ready && user === null) return <Navigate to="/login" replace />;
  if (ready && profileLoaded && profileComplete) return <Navigate to="/" replace />;

  function set<K extends keyof BusinessProfile>(key: K, value: BusinessProfile[K]) {
    setForm((current) => ({ ...current, [key]: value }));
  }

  async function submit(profile: BusinessProfile) {
    setBusy(true);
    setFailed("");
    setFormError("");
    try {
      const token = await getToken();
      if (token === null) throw new Error("missing token");
      await saveProfile(token, profile);
      await refreshProfile();
      navigate("/", { replace: true });
    } catch (unknown) {
      if (unknown instanceof AnalyzeError && unknown.code === "UNAUTHORIZED") {
        setFailed("Your session expired. Sign in again.");
      } else if (unknown instanceof AnalyzeError) {
        setFailed(unknown.message);
      } else {
        setFailed(friendlyAuthError(unknown));
      }
    } finally {
      setBusy(false);
    }
  }

  function onRequired(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const error = validateRequired(form);
    if (error !== "") {
      setFormError(error);
      return;
    }
    setStep(2);
  }

  function onOptional(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    void submit(form);
  }

  function onSkip() {
    void submit({ ...form, usage_plan: "", profession: "", referral_source: "" });
  }

  const selectClass =
    "min-h-[44px] w-full rounded-md border border-line bg-surface px-3 text-ink transition-colors duration-150 hover:border-muted";

  return (
    <Container className="py-10">
      <Breadcrumbs items={[{ label: "Home", href: "/" }, { label: meta.shortTitle }]} />
      <h1 className="mt-2 font-serif text-3xl font-semibold">{meta.shortTitle}</h1>
      <p className="mt-2 max-w-2xl text-muted">
        One step before your first analysis. This helps tailor suggestions to your
        business. See the{" "}
        <Link to="/privacy" className="underline underline-offset-4">
          Privacy Policy
        </Link>{" "}
        for what is stored.
      </p>
      <div className="mt-8 max-w-2xl space-y-4">
        {failed !== "" && (
          <Alert tone="error" title="Something went wrong.">
            {failed}
          </Alert>
        )}
        {step === 1 ? (
          <Card>
            <p className="font-semibold">Step 1 of 2: required</p>
            <form onSubmit={onRequired} noValidate className="mt-4">
              <div className="space-y-4">
                <Input
                  id="ob-business"
                  label="Business name"
                  autoComplete="organization"
                  value={form.business_name}
                  onChange={(event) => set("business_name", event.target.value)}
                />
                <Input
                  id="ob-website"
                  label="Website"
                  type="url"
                  autoComplete="url"
                  placeholder="https://example.com/"
                  value={form.website}
                  onChange={(event) => set("website", event.target.value)}
                />
                <Input
                  id="ob-industry"
                  label="Industry"
                  placeholder="Plumbing, bakery, legal services"
                  value={form.industry}
                  onChange={(event) => set("industry", event.target.value)}
                />
                <div className="grid gap-4 sm:grid-cols-2">
                  <Input
                    id="ob-city"
                    label="City"
                    autoComplete="address-level2"
                    value={form.city}
                    onChange={(event) => set("city", event.target.value)}
                  />
                  <Input
                    id="ob-country"
                    label="Country"
                    autoComplete="country-name"
                    value={form.country}
                    onChange={(event) => set("country", event.target.value)}
                  />
                </div>
                <div>
                  <label htmlFor="ob-size" className="mb-1 block text-sm font-semibold">
                    Business size
                  </label>
                  <select
                    id="ob-size"
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
                  id="ob-role"
                  label="Your role"
                  placeholder="Owner, manager, marketer"
                  value={form.role}
                  onChange={(event) => set("role", event.target.value)}
                />
                {formError !== "" && (
                  <p role="alert" className="text-sm font-semibold text-sev-high">
                    {formError}
                  </p>
                )}
                <div>
                  <Button type="submit">Continue</Button>
                </div>
              </div>
            </form>
          </Card>
        ) : (
          <Card>
            <p className="font-semibold">Step 2 of 2: optional</p>
            <p className="mt-1 text-sm text-muted">
              Three quick questions. Skip them if you prefer.
            </p>
            <form onSubmit={onOptional} noValidate className="mt-4">
              <div className="space-y-4">
                <Textarea
                  id="ob-usage"
                  label="How do you plan to use this site? (optional)"
                  value={form.usage_plan}
                  onChange={(event) => set("usage_plan", event.target.value)}
                />
                <Input
                  id="ob-profession"
                  label="Profession (optional)"
                  value={form.profession}
                  onChange={(event) => set("profession", event.target.value)}
                />
                <Input
                  id="ob-referral"
                  label="How did you find us? (optional)"
                  value={form.referral_source}
                  onChange={(event) => set("referral_source", event.target.value)}
                />
                <div className="flex flex-wrap gap-2">
                  <Button type="submit" loading={busy}>
                    Finish
                  </Button>
                  <Button variant="secondary" onClick={onSkip}>
                    Skip for now
                  </Button>
                </div>
              </div>
            </form>
          </Card>
        )}
      </div>
    </Container>
  );
}
