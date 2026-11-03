import { Link } from "react-router-dom";
import LegalPage from "../components/LegalPage";
import { NOT_FOUND_META } from "../lib/pages";

export default function NotFound() {
  return (
    <LegalPage
      title={NOT_FOUND_META.shortTitle}
      metaDescription={NOT_FOUND_META.description}
      path={NOT_FOUND_META.path}
      updated="November 2, 2026"
    >
      <p className="text-muted">
        Nothing lives at this address.{" "}
        <Link to="/" className="font-semibold underline underline-offset-4">
          Go back to the homepage
        </Link>{" "}
        to analyze a website.
      </p>
    </LegalPage>
  );
}
