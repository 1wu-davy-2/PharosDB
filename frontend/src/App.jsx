import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import { AuthProvider } from "./context/AuthContext";
import { ThemeProvider } from "./context/ThemeContext";
import ProtectedRoute from "./components/ProtectedRoute";
import LoginPage from "./pages/LoginPage";
import DashboardPage from "./pages/DashboardPage";
import InstancesPage from "./pages/InstancesPage";
import QANPage from "./pages/QANPage";
import LockPage from "./pages/LockPage";
import AlertsPage from "./pages/AlertsPage";
import SettingsPage from "./pages/SettingsPage";
import AdvisorPage from "./pages/AdvisorPage";
import AdminPage from "./pages/AdminPage";

export default function App() {
  return (
    <ThemeProvider>
    <AuthProvider>
      <BrowserRouter>
        <Routes>
          <Route path="/login" element={<LoginPage />} />
          <Route path="/" element={<ProtectedRoute><DashboardPage /></ProtectedRoute>} />
          <Route path="/instances" element={<ProtectedRoute><InstancesPage /></ProtectedRoute>} />
          <Route path="/qan" element={<ProtectedRoute><QANPage /></ProtectedRoute>} />
          <Route path="/locks" element={<ProtectedRoute><LockPage /></ProtectedRoute>} />
          <Route path="/alerts" element={<ProtectedRoute><AlertsPage /></ProtectedRoute>} />
          <Route path="/settings" element={<ProtectedRoute><SettingsPage /></ProtectedRoute>} />
          <Route path="/advisor" element={<ProtectedRoute><AdvisorPage /></ProtectedRoute>} />
          <Route path="/system" element={<ProtectedRoute><AdminPage /></ProtectedRoute>} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </BrowserRouter>
    </AuthProvider>
    </ThemeProvider>
  );
}
