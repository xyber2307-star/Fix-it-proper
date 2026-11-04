import { Link } from "react-router-dom";
import { BRAND } from "../config/brand";
import LegalPage, { LegalSection } from "../components/LegalPage";
import { metaForPath } from "../lib/pages";

const EMAIL = BRAND.contactEmail;
const META = metaForPath("/privacy");

export default function Privacy() {
  return (
    <LegalPage
      title={META.shortTitle}
      metaDescription={META.description}
      path={META.path}
      updated="November 3, 2026"
    >
      <LegalSection id="who-we-are" title="Who we are">
        <p>
          {BRAND.legalName} is an independent project run by its operator ("we", "us").
          There is no company behind the service yet. Questions about this policy go
          to{" "}
          <a href={`mailto:${EMAIL}`} className="underline underline-offset-4">
            {EMAIL}
          </a>
          .
        </p>
      </LegalSection>

      <LegalSection id="what-you-give-us" title="What you give us">
        <p>
          The website or video URL you submit for analysis, any brand voice text you add,
          anything you send through the contact form, and your email address if you create
          an account.
        </p>
      </LegalSection>

      <LegalSection id="accounts" title="Accounts and saved reports">
        <p>
          An account is required to run analyses. Accounts are handled by Firebase
          Authentication with email and password or Google sign in. We store
          your account ID, your name, your email address, and the
          dates you joined and last signed in. After your first sign in we ask for a
          business profile (business name, website, industry, city, country, size,
          and role) plus three optional questions. That profile is stored with your
          account and you can edit or delete it at any time from Settings.
        </p>
        <p>
          Analyses you run while signed in are saved to your history with the URL, the
          full report, and the date. Saved reports are deleted automatically after 30
          days. You can delete any report sooner from the Saved reports page, and you
          can delete your whole account, including every saved report, from the same
          page. All stored data lives in Firestore and only our backend can read or
          write it; direct access from browsers is denied.
        </p>
      </LegalSection>

      <LegalSection id="contact-messages" title="Contact messages">
        <p>
          Messages sent through the contact form are stored with your name, email
          address, message text, the date sent, and whether it was answered. We keep
          them only to handle your request, until you ask us to delete them. The form
          includes spam protection that rejects obvious bots.
        </p>
      </LegalSection>

      <LegalSection id="what-we-fetch" title="What we fetch">
        <p>
          To run an analysis we fetch the public page at your URL: the HTML, response
          headers, and meta tags, plus the public transcript for YouTube video pages when
          captions exist. Rendering uses a real browser, which captures a screenshot that
          stays inside the short lived fetch cache described below and is never included
          in reports. We only fetch public content; pages that block automated readers
          return an error instead of a report.
        </p>
      </LegalSection>

      <LegalSection id="what-we-log" title="What we log">
        <p>
          Every request writes one structured log line with the timestamp, your IP
          address, the request path, the status code, how long it took, and a random
          request ID. Analysis requests also log the domain you asked us to check. We
          never log page contents, API keys, or the text sent to the AI provider.
        </p>
      </LegalSection>

      <LegalSection id="caching" title="Caching and retention">
        <p>
          Fetched pages and finished reports are cached for up to 1 hour so repeat checks
          are fast. PageSpeed results are cached for up to 24 hours. Rate limit counters
          live in server memory only and expire after 1 hour. Everything above expires
          automatically; there is nothing you need to clear.
        </p>
        <p>
          Request logs are kept only as long as needed for debugging and abuse
          prevention. Accounts, contact messages, and anything else tied to you are
          removed when you delete your account or when you ask us to. Email us at the
          address above to ask what we hold about you or to request deletion, and we
          will respond to every request.
        </p>
      </LegalSection>

      <LegalSection id="third-parties" title="Third parties">
        <p>
          Three outside services process parts of your request. Google PageSpeed Insights
          receives the URL you submit and returns performance measurements. Groq, our AI
          provider, receives the ranked issue list, extracted page text, and brand voice
          to write explanations and rewrite variants; it never receives raw page HTML.
          Firebase, from Google, provides sign in (Authentication) and storage
          (Firestore) for accounts, saved reports, and contact messages. Each provider
          handles that data under its own policy.
        </p>
        <p>
          The site itself loads no analytics, no advertising trackers, and no third party
          fonts or icons. Those files ship with the site.
        </p>
      </LegalSection>

      <LegalSection id="what-we-never-do" title="What we never do">
        <p>
          We do not sell or rent your data, use your submissions for anything except
          running the analysis you asked for, or share them with anyone except the three
          processors named above.
        </p>
      </LegalSection>

      <LegalSection id="children" title="Children">
        <p>
          {BRAND.name} is built for business owners and is not directed at children. We
          do not knowingly collect data from anyone under 13.
        </p>
      </LegalSection>

      <LegalSection id="changes" title="Changes">
        <p>
          When this policy changes we update the date at the top of this page. Continued
          use of the service after a change means you accept the updated policy. See also
          our <Link to="/terms" className="underline underline-offset-4">Terms</Link> and{" "}
          <Link to="/contact" className="underline underline-offset-4">
            contact page
          </Link>
          .
        </p>
      </LegalSection>
    </LegalPage>
  );
}
