import { Suspense, lazy, useEffect } from "react";
import { Route, Routes, useLocation } from "react-router-dom";
import Container from "./components/Container";
import Footer from "./components/Footer";
import Header from "./components/Header";
import SkipLink from "./components/SkipLink";
import Home from "./pages/Home";

const Privacy = lazy(() => import("./pages/Privacy"));
const Terms = lazy(() => import("./pages/Terms"));
const Contact = lazy(() => import("./pages/Contact"));
const SignIn = lazy(() => import("./pages/SignIn"));
const Saved = lazy(() => import("./pages/Saved"));
const NotFound = lazy(() => import("./pages/NotFound"));

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
        <Suspense
          fallback={
            <Container className="py-10">
              <p role="status">Loading page…</p>
            </Container>
          }
        >
          <Routes>
            <Route path="/" element={<Home />} />
            <Route path="/privacy" element={<Privacy />} />
            <Route path="/privacy.html" element={<Privacy />} />
            <Route path="/terms" element={<Terms />} />
            <Route path="/terms.html" element={<Terms />} />
            <Route path="/contact" element={<Contact />} />
            <Route path="/contact.html" element={<Contact />} />
            <Route path="/signin" element={<SignIn />} />
            <Route path="/signin.html" element={<SignIn />} />
            <Route path="/saved" element={<Saved />} />
            <Route path="/saved.html" element={<Saved />} />
            <Route path="*" element={<NotFound />} />
          </Routes>
        </Suspense>
      </main>
      <Footer />
    </>
  );
}
