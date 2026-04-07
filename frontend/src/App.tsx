import { useEffect } from "react";
import { Link, Route, Routes, useLocation } from "react-router-dom";
import Dashboard from "./pages/Dashboard";
import JobDetail from "./pages/JobDetail";

export default function App() {
  const { pathname } = useLocation();

  useEffect(() => {
    window.scrollTo({ top: 0, behavior: "smooth" });
  }, [pathname]);

  return (
    <div className="layout">
      <header className="site-header">
        <h1 className="site-title">
          <Link to="/">Clip Social Pipeline</Link>
        </h1>
        <span className="site-tagline">Semi-auto ingest → clips → publish</span>
      </header>
      <main key={pathname} className="page-transition">
        <Routes>
          <Route path="/" element={<Dashboard />} />
          <Route path="/job/:id" element={<JobDetail />} />
        </Routes>
      </main>
    </div>
  );
}
