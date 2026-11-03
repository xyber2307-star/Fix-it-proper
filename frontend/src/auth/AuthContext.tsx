import { createContext, useContext, useEffect, useState } from "react";
import type { ReactNode } from "react";
import {
  currentUserToken,
  friendlyAuthError,
  isFirebaseConfigured,
  sendPasswordReset,
  signInWithGoogle as signInGoogle,
  signInWithPassword,
  signOutUser,
  signUpWithPassword,
  watchAuthState,
} from "../lib/firebase";
import type { AuthUser } from "../lib/firebase";

interface AuthContextValue {
  user: AuthUser | null;
  ready: boolean;
  configured: boolean;
  signUp: (email: string, password: string, name: string) => Promise<AuthUser>;
  signIn: (email: string, password: string) => Promise<AuthUser>;
  signInGoogle: () => Promise<AuthUser>;
  sendReset: (email: string) => Promise<void>;
  signOut: () => Promise<void>;
  getToken: () => Promise<string | null>;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<AuthUser | null>(null);
  const [ready, setReady] = useState(false);
  const configured = isFirebaseConfigured();

  useEffect(() => {
    if (!configured) {
      setReady(true);
      return;
    }
    let unsubscribe: (() => void) | null = null;
    let cancelled = false;
    watchAuthState((next) => {
      if (cancelled) return;
      setUser((prev) => {
        if (
          prev !== null &&
          next !== null &&
          prev.uid === next.uid &&
          prev.displayName !== null &&
          next.displayName === null
        ) {
          return prev;
        }
        return next;
      });
      setReady(true);
    })
      .then((stop) => {
        unsubscribe = stop;
      })
      .catch(() => {
        if (!cancelled) setReady(true);
      });
    return () => {
      cancelled = true;
      unsubscribe?.();
    };
  }, [configured]);

  async function wrappedSignUp(email: string, password: string, name: string) {
    const account = await signUpWithPassword(email, password, name);
    setUser(account);
    return account;
  }

  async function wrappedSignIn(email: string, password: string) {
    const account = await signInWithPassword(email, password);
    setUser(account);
    return account;
  }

  async function wrappedSignInGoogle() {
    const account = await signInGoogle();
    setUser(account);
    return account;
  }

  async function wrappedSignOut() {
    await signOutUser();
    setUser(null);
  }

  const value: AuthContextValue = {
    user,
    ready,
    configured,
    signUp: wrappedSignUp,
    signIn: wrappedSignIn,
    signInGoogle: wrappedSignInGoogle,
    sendReset: sendPasswordReset,
    signOut: wrappedSignOut,
    getToken: currentUserToken,
  };
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const value = useContext(AuthContext);
  if (value === null) throw new Error("useAuth must be used inside AuthProvider");
  return value;
}

export { friendlyAuthError };
