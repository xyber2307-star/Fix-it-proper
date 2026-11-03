import { Link } from "react-router-dom";
import { BRAND } from "../config/brand";
import Container from "./Container";

export default function Footer() {
  return (
    <footer className="mt-16 border-t border-line bg-surface">
      <Container className="py-8 text-sm text-muted">
        <nav aria-label="Footer">
          <ul className="flex flex-wrap gap-x-6 gap-y-2">
            <li>
              <Link
                to="/privacy"
                className="inline-flex min-h-[44px] items-center underline underline-offset-4"
              >
                Privacy Policy
              </Link>
            </li>
            <li>
              <Link
                to="/terms"
                className="inline-flex min-h-[44px] items-center underline underline-offset-4"
              >
                Terms and Conditions
              </Link>
            </li>
            <li>
              <Link
                to="/contact"
                className="inline-flex min-h-[44px] items-center underline underline-offset-4"
              >
                Contact
              </Link>
            </li>
          </ul>
        </nav>
        <p className="mt-4">
          © {new Date().getFullYear()} {BRAND.name}.
        </p>
        <p className="mt-1">
          {BRAND.name} checks public pages with deterministic rules. Suggestions labeled AI
          generated need human review before use.
        </p>
      </Container>
    </footer>
  );
}
