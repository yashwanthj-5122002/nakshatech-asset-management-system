
import { useEffect, useMemo, useState } from "react";
import { X } from "lucide-react";
import "./projectTrackingSales.css";

const API = "/api/management/project-tracking-sales";

type Period = "today" | "month" | "year" | "custom";

type Project = {
  id: string;
  project_name: string;
  client_name: string;
  department: string;
  manager: string;
  finance_status: string;
  operational_status: string;
  sales_approved: number;
  payments_received: number;
  outstanding: number;
};

type Dashboard = {
  summary: Record<string, number>;
  projects: Project[];
  generated_at?: string;
};

type Detail = {
  project: Project;
  sales_invoices: any[];
  finance_invoices: any[];
  payments: any[];
  expenses: any[];
  bad_debts: any[];
};

const formatDate = (date: Date) => {
  const y = date.getFullYear();
  const m = String(date.getMonth() + 1).padStart(2, "0");
  const d = String(date.getDate()).padStart(2, "0");
  return `${y}-${m}-${d}`;
};

const money = (paise?: number) =>
  typeof paise === "number"
    ? new Intl.NumberFormat("en-IN", {
        style: "currency",
        currency: "INR",
      }).format(paise / 100)
    : "—";

function trackingAuthHeaders(): Record<string, string> {
  const token =
    localStorage.getItem('asset_token') ||
    sessionStorage.getItem('asset_token')

  return token ? { Authorization: `Bearer ${token}` } : {}
}
export default function ProjectTrackingSalesPage() {
  const [period, setPeriod] = useState<Period>("month");
  const [customFrom, setCustomFrom] = useState("");
  const [customTo, setCustomTo] = useState("");
  const [search, setSearch] = useState("");
  const [dashboard, setDashboard] = useState<Dashboard | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [details, setDetails] = useState<Detail | null>(null);
  const [error, setError] = useState("");
  const [lastSync, setLastSync] = useState("");
  const [live, setLive] = useState(false);

  const range = useMemo(() => {
    const now = new Date();
    let start = new Date(now);

    if (period === "month") {
      start = new Date(now.getFullYear(), now.getMonth(), 1);
    } else if (period === "year") {
      start = new Date(now.getFullYear(), 0, 1);
    }

    return {
      start: period === "custom" ? customFrom : formatDate(start),
      end: period === "custom" ? customTo : formatDate(now),
    };
  }, [period, customFrom, customTo]);

  // Automatic refresh - no changes required to existing
  // finance or project update handlers.
  useEffect(() => {
    if (!range.start || !range.end) return;

    let stopped = false;
    let timer: ReturnType<typeof setTimeout>;
    let controller: AbortController | null = null;

    async function refresh() {
      if (document.hidden) {
        timer = setTimeout(refresh, 2000);
        return;
      }

      controller = new AbortController();
      let retry = true;

      try {
        const params = new URLSearchParams(range);

        const response = await fetch(
          `${API}/dashboard?${params}`,
          {
            credentials: "include", headers: trackingAuthHeaders(),
            cache: "no-store",
            signal: controller.signal,
          }
        );

        if (response.status === 401 || response.status === 403) {
          retry = false;
          throw new Error("Not authorized to view management reports");
        }

        if (!response.ok) {
          throw new Error("Could not load reporting data");
        }

        const result: Dashboard = await response.json();

        if (!stopped) {
          setDashboard(result);
          setLive(true);
          setError("");
          setLastSync(new Date().toLocaleTimeString());
        }
      } catch (err) {
        if (!stopped) {
          setLive(false);
          setError(
            err instanceof Error ? err.message : "Connection failed"
          );
        }
      } finally {
        if (!stopped && retry) {
          timer = setTimeout(refresh, 2000);
        }
      }
    }

    refresh();

    return () => {
      stopped = true;
      clearTimeout(timer);
      controller?.abort();
    };
  }, [range.start, range.end]);

  useEffect(() => {
    if (!selectedId || !range.end) return;

    let cancelled = false;
    setDetails(null);

    fetch(
      `${API}/projects/${encodeURIComponent(selectedId)}?end=${range.end}`,
      { credentials: "include", headers: trackingAuthHeaders(), cache: "no-store" }
    )
      .then(response => {
        if (!response.ok) throw new Error("Unable to load details");
        return response.json();
      })
      .then((result: Detail) => {
        if (!cancelled) setDetails(result);
      })
      .catch(() => {
        if (!cancelled) setError("Unable to load project details");
      });

    return () => { cancelled = true; };
  }, [selectedId, range.end]);

  async function exportFile(type: "pdf" | "xlsx") {
    if (!range.start || !range.end) return;

    try {
      const params = new URLSearchParams(range);
      const response = await fetch(
        `${API}/export/${type}?${params}`,
        { credentials: "include", headers: trackingAuthHeaders() }
      );

      if (!response.ok) throw new Error("Export failed");

      const blob = await response.blob();
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");

      link.href = url;
      link.download = `project-tracking-${range.start}-${range.end}.${type}`;
      link.click();

      URL.revokeObjectURL(url);
    } catch {
      setError("Could not export the report");
    }
  }

  const projects = (dashboard?.projects || []).filter(project => {
    const text = [
      project.project_name,
      project.client_name,
      project.department,
      project.manager,
    ].join(" ").toLowerCase();

    return text.includes(search.toLowerCase());
  });

  const metrics = [
    ["Approved Sales", "sales_approved"],
    ["Invoices Raised", "invoiced"],
    ["Payments Received", "payments_received"],
    ["Partial Payments", "partial_payments"],
    ["Outstanding Amount", "outstanding"],
    ["Total Expenses", "expenses"],
    ["Approved Bad Debts", "bad_debts"],
  ] as const;

  return (
    <main className="pts-page">
      <header className="pts-header">
        <div>
          <small>FINANCE — MANAGEMENT INTELLIGENCE</small>
          <h1>Project Tracking and Sales</h1>
          <p>Company-wide financial and operational reporting</p>
        </div>
        <div className={live ? "pts-live" : "pts-offline"}>
          {live ? "LIVE" : " Disconnected"}
          <small>Last sync: {lastSync || "Not connected"}</small>
        </div>
      </header>

      <div className="pts-toolbar">
        <div className="pts-periods">
          {(["today", "month", "year", "custom"] as Period[]).map(p => (
            <button
              key={p}
              className={period === p ? "active" : ""}
              onClick={() => setPeriod(p)}
            >
              {p === "today" ? "Today" :
               p === "month" ? "This Month" :
               p === "year" ? "This Year" : "Custom Dates"}
            </button>
          ))}
        </div>

        <div>
          <button onClick={() => exportFile("pdf")}>Export PDF</button>
          <button onClick={() => exportFile("xlsx")}>Export Excel</button>
        </div>
      </div>

      {period === "custom" && (
        <div className="pts-date-range">
          <input
            type="date"
            value={customFrom}
            onChange={e => setCustomFrom(e.target.value)}
          />
          <input
            type="date"
            value={customTo}
            onChange={e => setCustomTo(e.target.value)}
          />
        </div>
      )}

      {error && <p className="pts-error">{error}</p>}

      <section className="pts-metrics">
        {metrics.map(([label, key]) => (
          <article className="pts-metric" key={key}>
            <small>{label}</small>
            <strong>{money(dashboard?.summary?.[key])}</strong>
          </article>
        ))}
      </section>

      <section className="pts-panel">
        <div className="pts-table-title">
          <h2>Project Financial Register</h2>
          <input
            placeholder="Search Project / Client / Department"
            value={search}
            onChange={e => setSearch(e.target.value)}
          />
        </div>

        <div className="pts-table-scroll">
          <table className="pts-table">
            <thead>
              <tr>
                <th>Project / Client</th>
                <th>Department</th>
                <th>Finance Status</th>
                <th>Operational Status</th>
                <th>Sales</th>
                <th>Received</th>
                <th>Outstanding</th>
                <th>Actions</th>
              </tr>
            </thead>

            <tbody>
              {projects.map(project => (
                <tr key={project.id}>
                  <td>
                    <b>{project.project_name}</b>
                    <small>{project.client_name}</small>
                  </td>
                  <td>{project.department}</td>
                  <td>{project.finance_status}</td>
                  <td>{project.operational_status}</td>
                  <td>{money(project.sales_approved)}</td>
                  <td>{money(project.payments_received)}</td>
                  <td>{money(project.outstanding)}</td>
                  <td>
                    <button onClick={() => setSelectedId(project.id)}>
                      Details
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {dashboard && projects.length === 0 && (
            <p>No matching project records.</p>
          )}
        </div>
      </section>

      {selectedId && (
        <div className="pts-overlay" role="presentation">
          <div className="pts-modal" role="dialog" aria-modal="true">
            <div className="pts-modal-title">
              <h2>Project Financial Details</h2>
              <button
                className="pts-modal-close"
                type="button"
                onClick={() => setSelectedId(null)}
                aria-label="Close project financial details"
              >
                <X size={20} />
              </button>
            </div>

            {!details ? (
              <p>Loading details...</p>
            ) : (
              <>
                <h3>{details.project.project_name}</h3>
                <p>{details.project.client_name}</p>

                {([
                  ["BD Sales Invoices", details.sales_invoices],
                  ["Finance Invoices", details.finance_invoices],
                  ["Payment History", details.payments],
                  ["Expenses", details.expenses],
                  ["Approved Bad Debts", details.bad_debts],
                ] as const).map(([title, records]) => (
                  <section key={title} className="pts-detail-section">
                    <h3>{title}</h3>
                    {records.length === 0 ? (
                      <p>No records available.</p>
                    ) : (
                      records.map((record: any, i: number) => (
                        <div className="pts-detail-row" key={record.id || i}>
                          <span>{record.date || record.invoice_number || "Record"}</span>
                          <strong>{money(record.amount_paise)}</strong>
                        </div>
                      ))
                    )}
                  </section>
                ))}
              </>
            )}
          </div>
        </div>
      )}
    </main>
  );
}
