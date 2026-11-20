import React, { useState, useEffect } from "react";
import { Navbar } from "./components/Navbar";
import { Sidebar } from "./components/Sidebar";
import type { TabType } from "./components/Sidebar";
import { Overview } from "./components/Overview";
import { StudentAnalysis } from "./components/StudentAnalysis";
import { ClassAnalysis } from "./components/ClassAnalysis";
import { ManualPrediction } from "./components/ManualPrediction";
import { Login } from "./components/Login";
import { MarksEntry } from "./components/MarksEntry";
import { AdminConsole } from "./components/AdminConsole";
import { checkBackendHealth, fetchStudentsList, fetchClassesList, getCurrentUser, login, logout, type AuthUser } from "./services/api";
import type { StudentSummary } from "./types";

export const App: React.FC = () => {
  const [activeTab, setActiveTab] = useState<TabType>("overview");
  const [isBackendConnected, setIsBackendConnected] = useState<boolean>(true);
  const [studentsList, setStudentsList] = useState<StudentSummary[]>([]);
  const [classesList, setClassesList] = useState<string[]>(["10A", "10B", "10C"]);
  const [selectedStudentId, setSelectedStudentId] = useState<string>("S001");
  const [selectedClassId, setSelectedClassId] = useState<string>("10A");
  const [user, setUser] = useState<AuthUser | null>(null);
  const [authLoading, setAuthLoading] = useState(true);

  const verifyHealth = async () => {
    const isOk = await checkBackendHealth();
    setIsBackendConnected(isOk);
  };

  const loadMetadata = async () => {
    const students = await fetchStudentsList();
    setStudentsList(students);

    const classes = await fetchClassesList();
    setClassesList(classes);
  };

  useEffect(() => {
    verifyHealth();
    if (localStorage.getItem("spi_token")) {
      getCurrentUser().then((value) => { setUser(value); loadMetadata(); }).catch(() => logout()).finally(() => setAuthLoading(false));
    } else setAuthLoading(false);

    const interval = setInterval(verifyHealth, 15000);
    return () => clearInterval(interval);
  }, []);

  const handleLogin = async (username: string, password: string) => {
    const result = await login(username, password);
    localStorage.setItem("spi_token", result.access_token); setUser(result.user); await loadMetadata();
  };
  const handleLogout = () => { logout(); setUser(null); setStudentsList([]); setClassesList([]); };

  if (authLoading) return <div className="min-h-screen grid place-items-center text-slate-500">Loading secure session…</div>;
  if (!user) return <Login onLogin={handleLogin} />;

  const handleSelectStudent = (studentId: string) => {
    setSelectedStudentId(studentId);
  };

  const handleSelectClass = (classId: string) => {
    setSelectedClassId(classId);
  };

  return (
    <div className="min-h-screen bg-[#F7F8FC] text-slate-900 flex flex-col font-sans">
      {/* Top Navbar */}
      <Navbar
        isBackendConnected={isBackendConnected}
        onRefreshHealth={verifyHealth}
        userName={`${user.full_name} · ${user.role}`}
        onLogout={handleLogout}
      />

      {/* Main Layout Container */}
      <div className="flex flex-1 overflow-hidden">
        {/* Sidebar Navigation */}
        <Sidebar activeTab={activeTab} setActiveTab={setActiveTab} role={user.role} />

        {/* Content View Area */}
        <main className="flex-1 p-6 md:p-8 overflow-y-auto max-w-7xl mx-auto w-full">
          {activeTab === "overview" && (
            <Overview
              setActiveTab={setActiveTab}
              onSelectStudent={handleSelectStudent}
              onSelectClass={handleSelectClass}
              studentsList={studentsList}
              classesList={classesList}
            />
          )}

          {activeTab === "student" && (
            <StudentAnalysis
              initialStudentId={selectedStudentId}
              studentsList={studentsList}
            />
          )}

          {activeTab === "class" && (
            <ClassAnalysis
              initialClassId={selectedClassId}
              classesList={classesList}
            />
          )}

          {activeTab === "manual" && <ManualPrediction />}
          {activeTab === "marks" && user.role === "faculty" && (
            <MarksEntry classes={classesList} students={studentsList} onSaved={loadMetadata} />
          )}
          {activeTab === "admin" && user.role === "admin" && <AdminConsole onChanged={loadMetadata} />}
        </main>
      </div>
    </div>
  );
};

export default App;
