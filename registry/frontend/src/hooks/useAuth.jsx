import { createContext, useContext, useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { auth } from '../api/client';

const AuthContext = createContext(null);

// Role hierarchy: administrator > approver > user
const ROLE_RANK = {
  administrator: 3,
  approver: 2,
  user: 1,
};

export function hasMinRole(userRole, requiredRole) {
  return (ROLE_RANK[userRole] || 0) >= (ROLE_RANK[requiredRole] || 0);
}

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);
  const navigate = useNavigate();

  useEffect(() => {
    checkAuth();
  }, []);

  async function checkAuth() {
    if (!auth.isAuthenticated()) {
      setLoading(false);
      return;
    }

    try {
      const userData = await auth.me();
      setUser(userData);
    } catch (error) {
      setUser(null);
    } finally {
      setLoading(false);
    }
  }

  async function login(username, password) {
    await auth.login(username, password);
    const userData = await auth.me();
    setUser(userData);
    navigate('/');
  }

  async function logout() {
    await auth.logout();
    setUser(null);
    navigate('/login');
  }

  const value = {
    user,
    loading,
    login,
    logout,
    isAuthenticated: !!user,
  };

  return (
    <AuthContext.Provider value={value}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error('useAuth must be used within an AuthProvider');
  }
  return context;
}

export function RequireAuth({ children }) {
  const { isAuthenticated, loading } = useAuth();
  const navigate = useNavigate();

  useEffect(() => {
    if (!loading && !isAuthenticated) {
      navigate('/login');
    }
  }, [isAuthenticated, loading, navigate]);

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="spinner" />
      </div>
    );
  }

  return isAuthenticated ? children : null;
}

export function RequireRole({ minRole, children }) {
  const { user } = useAuth();

  if (!user || !hasMinRole(user.effective_role, minRole)) {
    return (
      <div className="p-8 text-center text-gray-500">
        You do not have permission to view this page.
      </div>
    );
  }

  return children;
}
