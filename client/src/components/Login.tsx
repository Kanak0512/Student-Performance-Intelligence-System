import React, { useState } from "react";
import { GraduationCap, LockKeyhole } from "lucide-react";

export const Login: React.FC<{ onLogin: (username: string, password: string) => Promise<void> }> = ({ onLogin }) => {
  const [username, setUsername] = useState(""); const [password, setPassword] = useState("");
  const [error, setError] = useState(""); const [loading, setLoading] = useState(false);
  const submit = async (event: React.FormEvent) => { event.preventDefault(); setLoading(true); setError(""); try { await onLogin(username, password); } catch (e) { setError(e instanceof Error ? e.message : "Unable to sign in"); } finally { setLoading(false); } };
  return <main className="min-h-screen grid place-items-center bg-[#F7F8FC] p-5"><form onSubmit={submit} className="saas-card w-full max-w-md p-8 space-y-6">
    <div className="text-center"><div className="inline-flex p-3 rounded-xl bg-indigo-600 text-white"><GraduationCap /></div><h1 className="mt-4 text-2xl font-bold">Student Intelligence</h1><p className="mt-1 text-sm text-slate-500">Secure faculty and administrator access</p></div>
    {error && <p className="rounded-lg bg-rose-50 border border-rose-200 p-3 text-sm text-rose-700">{error}</p>}
    <label className="block text-sm font-medium">Username<input autoComplete="username" value={username} onChange={e=>setUsername(e.target.value)} required className="mt-1.5 w-full px-3 py-2.5 saas-input" /></label>
    <label className="block text-sm font-medium">Password<input type="password" autoComplete="current-password" value={password} onChange={e=>setPassword(e.target.value)} required className="mt-1.5 w-full px-3 py-2.5 saas-input" /></label>
    <button disabled={loading} className="w-full rounded-lg bg-indigo-600 py-2.5 text-sm font-semibold text-white disabled:opacity-60 flex justify-center gap-2"><LockKeyhole className="w-4 h-4" />{loading ? "Signing in..." : "Sign in"}</button>
  </form></main>;
};
