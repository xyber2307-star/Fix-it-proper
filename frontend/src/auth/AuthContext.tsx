import { createContext, useCallback, useContext, useEffect, useState } from "react";
import type { ReactNode } from "react";
import { fetchProfile } from "../lib/api";
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
import type { BusinessProfile } from "../types/api";

interface AuthContextValue {
  user: AuthUser | null;
  ready: boolean;
  configured: boolean;
  profile: BusinessProfile | null;
  profileComplete: boolean;
  profileLoaded: boolean;
  signUp: (email: string, password: string, name: string) => Promise<AuthUser>;
  signIn: (email: string, password: string) => Promise<AuthUser>;
  signInGoogle: () => Promise<AuthUser>;
  sendReset: (email: string) => Promise<void>;
  signOut: () => Promise<void>;
  getToken: () => Promise<string | null>;
  refreshProfile: () => Promise<void>;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<AuthUser | null>(null);
  const [ready, setReady] = useState(false);
  const [profile, setProfile] = useState<BusinessProfile | null>(null);
  const [profileComplete, setProfileComplete] = useState(false);
  const [profileLoaded, setProfileLoaded] = useState(false);
  const configured = isFirebaseConfigured();

  const refreshProfile = useCallback(async () => {
    try {
      const token = await currentUserToken();
      if (token === null) {
        setProfile(null);
        setProfileComplete(false);
        setProfileLoaded(true);
        return;
      }
      const response = await fetchProfile(token);
      setProfile(response.profile);
      setProfileComplete(response.profile_complete && response.profile !== null);
      setProfileLoaded(true);
    } catch {
      setProfile(null);
      setProfileComplete(false);
      setProfileLoaded(true);
    }
  }, []);

  useEffect(() => {
    if (!ready) return;
    if (user === null) {
      setProfile(null);
      setProfileComplete(false);
      setProfileLoaded(true);
      return;
    }
    setProfileLoaded(false);
    void refreshProfile();
  }, [ready, user, refreshProfile]);

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
    profile,
    profileComplete,
    profileLoaded,
    signUp: wrappedSignUp,
    signIn: wrappedSignIn,
    signInGoogle: wrappedSignInGoogle,
    sendReset: sendPasswordReset,
    signOut: wrappedSignOut,
    getToken: currentUserToken,
    refreshProfile,
  };
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const value = useContext(AuthContext);
  if (value === null) throw new Error("useAuth must be used inside AuthProvider");
  return value;
}

export { friendlyAuthError };
