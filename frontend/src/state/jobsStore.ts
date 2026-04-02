import { useEffect, useState } from "react";
import { Dashboard, JobDetail, JobSummary, fetchDashboard, fetchJob, fetchJobs } from "../api";

type JobsDashboardState = {
  jobs: JobSummary[];
  dashboard: Dashboard | null;
  loading: boolean;
  error: string | null;
  lastLoadedAt: number | null;
};

type JobDetailState = {
  data: JobDetail | null;
  loading: boolean;
  error: string | null;
  lastLoadedAt: number | null;
};

type JobsStoreState = {
  dashboard: JobsDashboardState;
  jobsById: Record<string, JobDetailState>;
};

const initialDashboard: JobsDashboardState = {
  jobs: [],
  dashboard: null,
  loading: false,
  error: null,
  lastLoadedAt: null,
};

const store: JobsStoreState = {
  dashboard: initialDashboard,
  jobsById: {},
};

type Listener = () => void;
const listeners = new Set<Listener>();

function notify() {
  for (const l of listeners) {
    l();
  }
}

function setDashboardState(patch: Partial<JobsDashboardState>) {
  store.dashboard = { ...store.dashboard, ...patch };
  notify();
}

function ensureJobDetailState(id: string): JobDetailState {
  if (!store.jobsById[id]) {
    store.jobsById[id] = { data: null, loading: false, error: null, lastLoadedAt: null };
  }
  return store.jobsById[id];
}

function setJobDetailState(id: string, patch: Partial<JobDetailState>) {
  const current = ensureJobDetailState(id);
  store.jobsById[id] = { ...current, ...patch };
  notify();
}

export function subscribe(listener: Listener): () => void {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}

/** Refresh dashboard jobs + summary if stale or forced. */
export async function refreshJobsDashboard(opts: { force?: boolean } = {}): Promise<void> {
  const now = Date.now();
  const { force } = opts;
  const { loading, lastLoadedAt } = store.dashboard;
  const isStale = !lastLoadedAt || now - lastLoadedAt > 5000;
  if (!force && (loading || !isStale)) return;

  setDashboardState({ loading: true });
  try {
    const [jobs, dashboard] = await Promise.all([fetchJobs(), fetchDashboard()]);
    setDashboardState({
      jobs,
      dashboard,
      error: null,
      lastLoadedAt: Date.now(),
      loading: false,
    });
  } catch (e) {
    setDashboardState({
      error: String(e),
      loading: false,
    });
  }
}

/** Hook for dashboard data; always returns cached data immediately. */
export function useJobsDashboard() {
  const [snapshot, setSnapshot] = useState<JobsDashboardState>(store.dashboard);

  useEffect(() => {
    const unsub = subscribe(() => {
      setSnapshot(store.dashboard);
    });
    // On first mount, kick off a refresh if we have nothing yet.
    if (!store.dashboard.jobs.length && !store.dashboard.dashboard && !store.dashboard.loading) {
      void refreshJobsDashboard();
    } else {
      // Optionally refresh in background if stale.
      void refreshJobsDashboard();
    }
    return unsub;
  }, []);

  return {
    jobs: snapshot.jobs,
    dashboard: snapshot.dashboard,
    loading: snapshot.loading,
    error: snapshot.error,
    refresh: refreshJobsDashboard,
  };
}

export async function refreshJobDetail(id: string, opts: { force?: boolean } = {}): Promise<void> {
  if (!id) return;
  const now = Date.now();
  const current = ensureJobDetailState(id);
  const { force } = opts;
  const isStale = !current.lastLoadedAt || now - current.lastLoadedAt > 3000;
  if (!force && (current.loading || !isStale)) return;

  setJobDetailState(id, { loading: true });
  try {
    const data = await fetchJob(id);
    setJobDetailState(id, {
      data,
      error: null,
      lastLoadedAt: Date.now(),
      loading: false,
    });
  } catch (e) {
    setJobDetailState(id, { error: String(e), loading: false });
  }
}

export function useJobDetail(jobId: string | undefined) {
  const [local, setLocal] = useState<JobDetailState>(() => ensureJobDetailState(jobId || ""));

  useEffect(() => {
    if (!jobId) return;
    const unsub = subscribe(() => {
      setLocal(ensureJobDetailState(jobId));
    });
    // initial load / refresh
    void refreshJobDetail(jobId);
    return unsub;
  }, [jobId]);

  // Auto-poll while in non-terminal state.
  useEffect(() => {
    if (!jobId) return;
    const terminalStatuses = new Set(["rendered", "failed"]);
    const status = local.data?.job.status;
    if (!status || terminalStatuses.has(status)) {
      return;
    }
    const id = setInterval(() => {
      void refreshJobDetail(jobId);
    }, 3000);
    return () => clearInterval(id);
  }, [jobId, local.data?.job.status]);

  return {
    data: local.data,
    loading: local.loading,
    error: local.error,
    refresh: (opts?: { force?: boolean }) => (jobId ? refreshJobDetail(jobId, opts) : Promise.resolve()),
  };
}

