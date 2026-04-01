import { Link, Route, Routes } from "react-router-dom";
import Dashboard from "./pages/Dashboard";
import JobDetail from "./pages/JobDetail";

export default function App() {
  return (
    <div className="layout">
      <header style={{ marginBottom: "1rem" }}>
        <strong>
          <Link to="/" style={{ textDecoration: "none", color: "inherit" }}>
            Clip Social Pipeline
          </Link>
        </strong>
        <span style={{ color: "#64748b", marginLeft: 8 }}> — semi-auto ingest → clips → publish</span>
      </header>
      <Routes>
        <Route path="/" element={<Dashboard />} />
        <Route path="/job/:id" element={<JobDetail />} />
      </Routes>
    </div>
  );
}
