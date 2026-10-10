import { createContext, useContext, useEffect, useMemo, useState } from 'react';
import { getCurrentUser, loginAccount, logoutAccount, registerAccount } from '../services/api';

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let active = true;
    getCurrentUser()
      .then((currentUser) => { if (active) setUser(currentUser); })
      .catch(() => { if (active) setUser(null); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, []);

  const value = useMemo(() => ({
    user,
    loading,
    async login(credentials) {
      const currentUser = await loginAccount(credentials);
      setUser(currentUser);
      return currentUser;
    },
    async register(details) {
      const currentUser = await registerAccount(details);
      setUser(currentUser);
      return currentUser;
    },
    async logout() {
      await logoutAccount();
      setUser(null);
    },
  }), [user, loading]);

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const context = useContext(AuthContext);
  return context ?? {
    user: null,
    loading: false,
    login: async () => {},
    register: async () => {},
    logout: async () => {},
  };
}
