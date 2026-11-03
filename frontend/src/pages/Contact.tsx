import { useRef, useState } from "react";
import type { FormEvent } from "react";
import { Link } from "react-router-dom";
import Alert from "../components/Alert";
import Button from "../components/Button";
import Card from "../components/Card";
import Input from "../components/Input";
import LegalPage from "../components/LegalPage";
import Textarea from "../components/Textarea";
import { BRAND } from "../config/brand";
import { AnalyzeError, sendContactMessage } from "../lib/api";
import { metaForPath } from "../lib/pages";

const EMAIL = BRAND.contactEmail;
const MIN_FILL_SECONDS = 3;

interface FieldErrors {
  name?: string;
  email?: string;
  message?: string;
}

export default function Contact() {
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [message, setMessage] = useState("");
  const [company, setCompany] = useState("");
  const [errors, setErrors] = useState<FieldErrors>({});
  const [sent, setSent] = useState(false);
  const [sending, setSending] = useState(false);
  const [submitError, setSubmitError] = useState("");
  const mountedAt = useRef(Date.now());
  const nameRef = useRef<HTMLInputElement>(null);
  const emailRef = useRef<HTMLInputElement>(null);
  const messageRef = useRef<HTMLTextAreaElement>(null);

  function validate(): FieldErrors {
    const found: FieldErrors = {};
    if (name.trim().length < 2 || name.trim().length > 100) {
      found.name = "Enter your name (2 to 100 characters).";
    }
    if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email.trim())) {
      found.email = "Enter a valid email address.";
    }
    if (message.trim().length < 10 || message.trim().length > 2000) {
      found.message = "Enter a message between 10 and 2000 characters.";
    }
    return found;
  }

  function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const found = validate();
    setErrors(found);
    if (found.name !== undefined) {
      nameRef.current?.focus();
      return;
    }
    if (found.email !== undefined) {
      emailRef.current?.focus();
      return;
    }
    if (found.message !== undefined) {
      messageRef.current?.focus();
      return;
    }
    // Spam protection: a filled honeypot or an instant submit is treated as a
    // bot. We show the same success message without sending anything.
    const tooFast = Date.now() - mountedAt.current < MIN_FILL_SECONDS * 1000;
    if (company.trim() !== "" || tooFast) {
      setSent(true);
      return;
    }
    setSending(true);
    setSubmitError("");
    sendContactMessage({
      name: name.trim(),
      email: email.trim(),
      message: message.trim(),
      company: "",
    })
      .then(() => setSent(true))
      .catch((unknown: unknown) => {
        const message =
          unknown instanceof AnalyzeError
            ? unknown.message
            : "Could not send your message. Try again.";
        setSubmitError(message);
      })
      .finally(() => setSending(false));
  }

  const meta = metaForPath("/contact");
  return (
    <LegalPage
      title={meta.shortTitle}
      metaDescription={meta.description}
      path={meta.path}
      updated="November 2, 2026"
    >
      <p className="text-muted">
        Email us directly at{" "}
        <a href={`mailto:${EMAIL}`} className="font-semibold underline underline-offset-4">
          {EMAIL}
        </a>{" "}
        or use the form below. We only use your details to reply, as explained in our{" "}
        <Link to="/privacy" className="underline underline-offset-4">
          Privacy Policy
        </Link>
        .
      </p>

      {sent ? (
        <Alert tone="success" title="Message received.">
          Thanks for writing. We will reply to {email.trim()}. If anything is urgent,
          email{" "}
          <a href={`mailto:${EMAIL}`} className="underline underline-offset-4">
            {EMAIL}
          </a>{" "}
          directly.
        </Alert>
      ) : (
        <Card>
          <form onSubmit={onSubmit} noValidate>
            <div className="space-y-4">
              <Input
                id="contact-name"
                label="Your name"
                autoComplete="name"
                value={name}
                onChange={(event) => setName(event.target.value)}
                error={errors.name}
                ref={nameRef}
              />
              <Input
                id="contact-email"
                label="Your email"
                type="email"
                autoComplete="email"
                value={email}
                onChange={(event) => setEmail(event.target.value)}
                error={errors.email}
                hint="We only use this to reply to you."
                ref={emailRef}
              />
              <Textarea
                id="contact-message"
                label="Message"
                value={message}
                onChange={(event) => setMessage(event.target.value)}
                error={errors.message}
                hint="10 to 2000 characters."
                ref={messageRef}
              />
              <div className="hidden" aria-hidden="true">
                <label htmlFor="contact-company">
                  Company (leave blank)
                  <input
                    id="contact-company"
                    type="text"
                    tabIndex={-1}
                    autoComplete="off"
                    value={company}
                    onChange={(event) => setCompany(event.target.value)}
                  />
                </label>
              </div>
              {submitError !== "" && (
                <Alert tone="error" title="Could not send your message.">
                  {submitError}
                </Alert>
              )}
              <div>
                <Button type="submit" loading={sending}>
                  Send message
                </Button>
              </div>
            </div>
          </form>
        </Card>
      )}
    </LegalPage>
  );
}
