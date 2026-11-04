import { useEffect, useRef, useState } from "react";
import { Link, NavLink, useLocation, useNavigate } from "react-router-dom";
import { Menu, ScanSearch, X } from "lucide-react";
import { useAuth } from "../auth/AuthContext";
import { BRAND } from "../config/brand";
import Button from "./Button";
import Container from "./Container";

const DISCOVER_ITEMS = [
  { to: "/creative", label: "Creative review" },
  { to: "/learn/seo", label: "Learn SEO" },
];

const NAV_ITEMS = [
  { to: "/privacy", label: "Privacy Policy" },
  { to: "/terms", label: "Terms and Conditions" },
  { to: "/contact", label: "Contact" },
];

export default function Header() {
  const [open, setOpen] = useState(false);
  const [signOutError, setSignOutError] = useState("");
  const buttonRef = useRef<HTMLButtonElement>(null);
  const panelRef = useRef<HTMLDivElement>(null);
  const { pathname } = useLocation();
  const navigate = useNavigate();
  const { user, configured, signOut } = useAuth();
  const items =
    user !== null
      ? [{ to: "/saved", label: "Saved reports" }, ...DISCOVER_ITEMS, ...NAV_ITEMS]
      : [...DISCOVER_ITEMS, ...NAV_ITEMS];

  async function onSignOut() {
    setSignOutError("");
    try {
      await signOut();
      setOpen(false);
      navigate("/");
    } catch {
      setSignOutError("Sign out failed. Try again.");
    }
  }

  useEffect(() => {
    setOpen(false);
  }, [pathname]);

  useEffect(() => {
    if (!open) return;
    panelRef.current?.querySelector("a")?.focus();
    function onKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") {
        setOpen(false);
        buttonRef.current?.focus();
        return;
      }
      if (event.key !== "Tab" || panelRef.current === null) return;
      const items = panelRef.current.querySelectorAll("a[href]");
      if (items.length === 0) return;
      const first = items[0] as HTMLElement;
      const last = items[items.length - 1] as HTMLElement;
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    }
    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, [open ]);

  return (
    <header className="border-b border-line bg-surface">
      <Container className="flex min-h-[64px] items-center justify-between gap-3 py-3">
        <Link to="/" className="flex items-center gap-3">
          <span className="flex size-9 items-center justify-center rounded-md bg-accent">
            <ScanSearch className="size-5 text-white" aria-hidden="true" />
          </span>
          <span>
            <span className="block font-serif text-lg font-semibold leading-tight">
              {BRAND.name}
            </span>
            <span className="block text-sm leading-tight text-muted">{BRAND.tagline}</span>
          </span>
        </Link>
        <div className="hidden items-center gap-6 sm:flex">
          <nav aria-label="Primary">
            <ul className="flex items-center gap-6">
              {items.map((item) => (
                <li key={item.to}>
                  <NavLink
                    to={item.to}
                    className={({ isActive }) =>
                      `inline-flex min-h-[44px] items-center font-semibold transition-colors duration-150 ${
                        isActive ? "text-accent" : "text-ink hover:text-accent"
                      }`
                    }
                  >
                    {item.label}
                  </NavLink>
                </li>
              ))}
            </ul>
          </nav>
          {configured &&
            (user !== null ? (
              <span className="flex items-center gap-3">
                <span className="max-w-[180px] truncate text-sm text-muted">
                  {user.displayName ?? user.email ?? "Signed in"}
                </span>
                <NavLink
                  to="/settings"
                  className="inline-flex min-h-[44px] items-center font-semibold text-ink transition-colors duration-150 hover:text-accent"
                >
                  Settings
                </NavLink>
                <Button variant="secondary" onClick={() => void onSignOut()}>
                  Sign out
                </Button>
              </span>
            ) : (
              <NavLink
                to="/login"
                className="inline-flex min-h-[44px] items-center font-semibold text-ink transition-colors duration-150 hover:text-accent"
              >
                Sign in
              </NavLink>
            ))}
        </div>
        {signOutError !== "" && (
          <p role="alert" className="hidden text-sm font-semibold text-sev-high sm:block">
            {signOutError}
          </p>
        )}
        <button
          ref={buttonRef}
          type="button"
          onClick={() => setOpen((value) => !value)}
          aria-expanded={open}
          aria-controls="mobile-menu"
          aria-label={open ? "Close menu" : "Open menu"}
          className="inline-flex min-h-[44px] min-w-[44px] items-center justify-center rounded-md sm:hidden"
        >
          {open ? (
            <X className="size-6" aria-hidden="true" />
          ) : (
            <Menu className="size-6" aria-hidden="true" />
          )}
        </button>
      </Container>
      {open && (
        <div id="mobile-menu" ref={panelRef} className="border-t border-line sm:hidden">
          <Container>
            <ul className="py-2">
              {items.map((item) => (
                <li key={item.to}>
                  <NavLink
                    to={item.to}
                    className={({ isActive }) =>
                      `flex min-h-[44px] items-center font-semibold transition-colors duration-150 ${
                        isActive ? "text-accent" : "text-ink hover:text-accent"
                      }`
                    }
                  >
                    {item.label}
                  </NavLink>
                </li>
              ))}
              {configured && user === null && (
                <li>
                  <NavLink
                    to="/login"
                    className="flex min-h-[44px] items-center font-semibold text-ink transition-colors duration-150 hover:text-accent"
                  >
                    Sign in
                  </NavLink>
                </li>
              )}
              {configured && user !== null && (
                <li>
                  <NavLink
                    to="/settings"
                    className="flex min-h-[44px] items-center font-semibold text-ink transition-colors duration-150 hover:text-accent"
                  >
                    Settings
                  </NavLink>
                </li>
              )}
              {configured && user !== null && (
                <li>
                  <button
                    type="button"
                    onClick={() => void onSignOut()}
                    className="flex min-h-[44px] w-full items-center font-semibold text-ink transition-colors duration-150 hover:text-accent"
                  >
                    Sign out{user.email ? ` (${user.email})` : ""}
                  </button>
                </li>
              )}
            </ul>
            {signOutError !== "" && (
              <p role="alert" className="pb-3 text-sm font-semibold text-sev-high">
                {signOutError}
              </p>
            )}
          </Container>
        </div>
      )}
    </header>
  );
}
