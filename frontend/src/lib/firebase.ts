// Lazy Firebase Auth loader. The firebase SDK is only imported inside
// these functions, so it lands in its own chunk and never grows the
// initial JS bundle. Everything returns null or throws FirebaseNotConfigured
// when the VITE_FIREBASE_* keys are missing.
import type { Auth, User } from "firebase/auth";

export interface AuthUser {
  uid: string;
  email: string | null;
  displayName: string | null;
}

export class FirebaseNotConfigured extends Error {
  constructor() {
    super("Sign in is not configured.");
    this.name = "FirebaseNotConfigured";
  }
}

interface FirebaseConfig {
  apiKey: string;
  authDomain: string;
  projectId: string;
}

function readConfig(): FirebaseConfig | null {
  const apiKey = import.meta.env.VITE_FIREBASE_API_KEY as string | undefined;
  const authDomain = import.meta.env.VITE_FIREBASE_AUTH_DOMAIN as string | undefined;
  const projectId = import.meta.env.VITE_FIREBASE_PROJECT_ID as string | undefined;
  if (!apiKey || !authDomain || !projectId) return null;
  return { apiKey, authDomain, projectId };
}

export function isFirebaseConfigured(): boolean {
  return readConfig() !== null;
}

let authPromise: Promise<Auth> | null = null;

export async function loadAuth(): Promise<Auth> {
  if (authPromise === null) {
    authPromise = (async () => {
      const config = readConfig();
      if (config === null) throw new FirebaseNotConfigured();
      const [{ getApp, getApps, initializeApp }, authModule] = await Promise.all([
        import("firebase/app"),
        import("firebase/auth"),
      ]);
      const app = getApps().length > 0 ? getApp() : initializeApp(config);
      const auth = authModule.getAuth(app);
      if (import.meta.env.VITE_FIREBASE_USE_EMULATORS === "true") {
        authModule.connectAuthEmulator(auth, "http://127.0.0.1:9099", {
          disableWarnings: true,
        });
      }
      return auth;
    })();
  }
  return authPromise;
}

function toAuthUser(user: User): AuthUser {
  return { uid: user.uid, email: user.email, displayName: user.displayName };
}

export async function signUpWithPassword(
  email: string,
  password: string,
): Promise<AuthUser> {
  const auth = await loadAuth();
  const { createUserWithEmailAndPassword } = await import("firebase/auth");
  const credential = await createUserWithEmailAndPassword(auth, email, password);
  return toAuthUser(credential.user);
}

export async function signInWithPassword(
  email: string,
  password: string,
): Promise<AuthUser> {
  const auth = await loadAuth();
  const { signInWithEmailAndPassword } = await import("firebase/auth");
  const credential = await signInWithEmailAndPassword(auth, email, password);
  return toAuthUser(credential.user);
}

export async function signInWithGoogle(): Promise<AuthUser> {
  const auth = await loadAuth();
  const { GoogleAuthProvider, signInWithPopup } = await import("firebase/auth");
  const credential = await signInWithPopup(auth, new GoogleAuthProvider());
  return toAuthUser(credential.user);
}

export async function sendPasswordReset(email: string): Promise<void> {
  const auth = await loadAuth();
  const { sendPasswordResetEmail } = await import("firebase/auth");
  await sendPasswordResetEmail(auth, email);
}

export async function signOutUser(): Promise<void> {
  const auth = await loadAuth();
  const { signOut } = await import("firebase/auth");
  await signOut(auth);
}

export async function watchAuthState(
  callback: (user: AuthUser | null) => void,
): Promise<() => void> {
  const auth = await loadAuth();
  const { onAuthStateChanged } = await import("firebase/auth");
  return onAuthStateChanged(auth, (user) => callback(user ? toAuthUser(user) : null));
}

export async function currentUserToken(): Promise<string | null> {
  const auth = await loadAuth();
  if (auth.currentUser === null) return null;
  return auth.currentUser.getIdToken();
}

export function friendlyAuthError(error: unknown): string {
  if (error instanceof FirebaseNotConfigured) return error.message;
  const code =
    typeof error === "object" && error !== null
      ? (error as Record<string, unknown>).code
      : null;
  switch (code) {
    case "auth/email-already-in-use":
      return "An account with this email already exists. Sign in instead.";
    case "auth/invalid-credential":
    case "auth/wrong-password":
    case "auth/user-not-found":
      return "Email or password is wrong. Try again.";
    case "auth/weak-password":
      return "Password must be at least 6 characters.";
    case "auth/invalid-email":
      return "Enter a valid email address.";
    case "auth/popup-closed-by-user":
      return "The Google sign in window was closed before finishing.";
    case "auth/network-request-failed":
      return "Network error. Check your connection and try again.";
    case "auth/operation-not-allowed":
      return "This sign in method is not enabled. Use the other option.";
    default:
      return "Sign in failed. Try again in a minute.";
  }
}
