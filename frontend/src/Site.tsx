import { useEffect } from "react";
import type { ReactNode } from "react";
import { Navigate, Route, Routes, useLocation } from "react-router-dom";
import { useAuth } from "./auth/AuthContext";
import Footer from "./components/Footer";
import Header from "./components/Header";
import SkipLink from "./components/SkipLink";
import Contact from "./pages/Contact";
import Creative from "./pages/Creative";
import Home from "./pages/Home";
import LearnSeo from "./pages/LearnSeo";
import NotFound from "./pages/NotFound";
import Onboarding from "./pages/Onboarding";
import Privacy from "./pages/Privacy";
import Saved from "./pages/Saved";
import Settings from "./pages/Settings";
import SignIn from "./pages/SignIn";
import Terms from "./pages/Terms";

function RequireAuth({ children }: { children: ReactNode }) {
  const { user, ready, configured } = useAuth();
  if (!ready) return null;
  if (user === null || !configured) return <Navigate to="/login" replace />;
  return <>{children}</>;
}

function RequireProfile({ children }: { children: ReactNode }) {
  const { profileComplete, profileLoaded } = useAuth();
  if (!profileLoaded) return null;
  if (!profileComplete) return <Navigate to="/onboarding" replace />;
  return <>{children}</>;
}

function ScrollToTop() {
  const { pathname } = useLocation();
  useEffect(() => {
    window.scrollTo(0, 0);
  }, [pathname]);
  return null;
}

export default function Site() {
  return (
    <>
      <ScrollToTop />
      <SkipLink />
      <Header />
      <main id="main-content">
        <Routes>
            <Route path="/" element={<Home />} />
            <Route path="/privacy" element={<Privacy />} />
            <Route path="/privacy.html" element={<Privacy />} />
            <Route path="/terms" element={<Terms />} />
            <Route path="/terms.html" element={<Terms />} />
            <Route path="/contact" element={<Contact />} />
            <Route path="/contact.html" element={<Contact />} />
            <Route path="/login" element={<SignIn />} />
            <Route path="/login.html" element={<SignIn />} />
            <Route path="/signin" element={<Navigate to="/login" replace />} />
            <Route path="/signin.html" element={<Navigate to="/login" replace />} />
            <Route path="/signup" element={<SignIn />} />
            <Route path="/signup.html" element={<SignIn />} />
            <Route
              path="/onboarding"
              element={
                <RequireAuth>
                  <Onboarding />
                </RequireAuth>
              }
            />
            <Route
              path="/onboarding.html"
              element={
                <RequireAuth>
                  <Onboarding />
                </RequireAuth>
              }
            />
            <Route
              path="/saved"
              element={
                <RequireAuth>
                  <RequireProfile>
                    <Saved />
                  </RequireProfile>
                </RequireAuth>
              }
            />
            <Route
              path="/saved.html"
              element={
                <RequireAuth>
                  <RequireProfile>
                    <Saved />
                  </RequireProfile>
                </RequireAuth>
              }
            />
            <Route
              path="/creative"
              element={
                <RequireAuth>
                  <RequireProfile>
                    <Creative />
                  </RequireProfile>
                </RequireAuth>
              }
            />
            <Route
              path="/creative.html"
              element={
                <RequireAuth>
                  <RequireProfile>
                    <Creative />
                  </RequireProfile>
                </RequireAuth>
              }
            />
            <Route path="/learn/seo" element={<LearnSeo />} />
            <Route path="/learn/seo.html" element={<LearnSeo />} />
            <Route
              path="/settings"
              element={
                <RequireAuth>
                  <Settings />
                </RequireAuth>
              }
            />
            <Route
              path="/settings.html"
              element={
                <RequireAuth>
                  <Settings />
                </RequireAuth>
              }
            />
            <Route path="*" element={<NotFound />} />
        </Routes>
      </main>
      <Footer />
    </>
  );
}
