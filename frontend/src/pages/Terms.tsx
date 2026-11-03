import { Link } from "react-router-dom";
import { BRAND } from "../config/brand";
import LegalPage, { LegalSection } from "../components/LegalPage";
import { metaForPath } from "../lib/pages";

const EMAIL = "xyber2307@gmail.com";
const META = metaForPath("/terms");

export default function Terms() {
  return (
    <LegalPage
      title={META.shortTitle}
      metaDescription={META.description}
      path={META.path}
      updated="November 2, 2026"
    >
      <LegalSection id="service" title="The service">
        <p>
          {BRAND.name} fetches a public page you nominate and returns a checklist of
          specific problems with evidence, plus rewrite suggestions. Results describe what
          our checks found; they are not predictions of rankings, traffic, or revenue,
          and not professional marketing or legal advice.
        </p>
      </LegalSection>

      <LegalSection id="acceptable-use" title="Acceptable use">
        <p>By using the service you agree to:</p>
        <ul className="list-disc space-y-1 pl-5">
          <li>Analyze only URLs you are allowed to analyze.</li>
          <li>Stay within the published rate limit, currently 10 analyses per hour.</li>
          <li>
            Not attack, overload, or probe the service for weaknesses, and not resell
            automated access to it.
          </li>
        </ul>
        <p>We may refuse or limit service for misuse without notice.</p>
      </LegalSection>

      <LegalSection id="ai-content" title="AI suggestions">
        <p>
          Explanations and rewrites come from an AI provider and are always labeled "AI
          generated, test before using". They can be wrong or unsuitable for your
          business. Test them before publishing; what you publish is your responsibility.
        </p>
      </LegalSection>

      <LegalSection id="availability" title="Availability">
        <p>
          The service runs on a best effort basis. Features depend on third parties
          (Google PageSpeed Insights and Groq), so performance data or AI suggestions can
          be temporarily unavailable; the report says so instead of guessing. We may
          change or discontinue the service at any time.
        </p>
      </LegalSection>

      <LegalSection id="your-content" title="Your content">
        <p>
          You keep all rights to the URLs and brand voice text you submit. You grant us
          permission to fetch, cache, and process them, including sending the parts
          described in the{" "}
          <Link to="/privacy" className="underline underline-offset-4">
            Privacy Policy
          </Link>
          , for the sole purpose of running your analysis.
        </p>
      </LegalSection>

      <LegalSection id="warranty" title="No warranty and liability">
        <p>
          The service is provided as is, without warranties of any kind. To the maximum
          extent permitted by law, we are not liable for any loss arising from your use
          of the service or reliance on its results.
        </p>
      </LegalSection>

      <LegalSection id="changes" title="Changes and contact">
        <p>
          We may update these terms; the date at the top always shows the latest version
          and continued use means you accept it. Questions go to{" "}
          <a href={`mailto:${EMAIL}`} className="underline underline-offset-4">
            {EMAIL}
          </a>{" "}
          or through our{" "}
          <Link to="/contact" className="underline underline-offset-4">
            contact page
          </Link>
          .
        </p>
      </LegalSection>
    </LegalPage>
  );
}
