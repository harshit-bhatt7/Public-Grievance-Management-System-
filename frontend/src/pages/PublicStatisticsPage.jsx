import { useEffect, useState } from "react";
import { ShieldCheck, TrendingUp, Trophy, Sparkles } from "lucide-react";
import {
  getPublicCategories,
  getPublicDepartments,
  getPublicLocations,
  getPublicMostImproved,
  getPublicCategoryRankings,
  getPublicRankings,
  getPublicStatistics,
  getPublicTrends,
} from "../services/api";

const levels = ["state", "district", "taluka", "village"];

export default function PublicStatisticsPage() {
  const [filters, setFilters] = useState({});
  const [data, setData] = useState(null);
  const [loc, setLoc] = useState({});
  const [trends, setTrends] = useState([]);
  const [cats, setCats] = useState([]);
  const [deps, setDeps] = useState([]);
  const [rank, setRank] = useState([]);
  const [improved, setImproved] = useState([]);
  const [categoryRank, setCategoryRank] = useState([]);
  const [selectedCategory, setSelectedCategory] = useState("");
  const [level, setLevel] = useState("district");

  useEffect(() => {
    Promise.all([
      getPublicLocations(filters),
      getPublicStatistics(filters),
      getPublicTrends({ ...filters, period: "monthly" }),
      getPublicCategories(filters),
      getPublicDepartments(filters),
      getPublicMostImproved({ ...filters, level, period: "monthly" }),
    ]).then(([locations, summary, trendData, categoryData, departmentData, improvedData]) => {
      setLoc(locations);
      setData(summary);
      setTrends(trendData.items || []);
      setCats(categoryData.items || []);
      setDeps(departmentData.items || []);
      setImproved(improvedData.items || []);
    });
  }, [filters, level]);

  useEffect(() => {
    getPublicRankings({ level, ...filters }).then((x) => setRank(x.items || []));
  }, [level]);

  useEffect(() => {
    if (!selectedCategory) {
      setCategoryRank([]);
      return;
    }
    getPublicCategoryRankings({ level, category_id: selectedCategory, ...filters }).then((x) => setCategoryRank(x.items || []));
  }, [level, selectedCategory]);

  const choose = (key, value) => {
    const index = levels.indexOf(key);
    const next = { ...filters };
    levels.slice(index).forEach((x) => delete next[x]);
    if (value) next[key] = value;
    setFilters(next);
  };

  const cards = data && !data.insufficient_data
    ? [
        ["Total grievances", data.total_grievances],
        ["Resolved / Closed", (data.resolved_grievances || 0) + (data.closed_grievances || 0)],
        ["Pending", data.pending_grievances],
        ["In progress", data.in_progress_grievances],
        ["Rejected", data.rejected_grievances],
        ["Resolution rate", `${data.resolution_rate}%`],
        ["Pending rate", `${data.pending_rate}%`],
        ["Dispute rate", `${data.dispute_rate}%`],
        ["Avg. resolution", data.average_resolution_days == null ? "—" : `${data.average_resolution_days} days`],
        ["Avg. response", data.average_response_hours == null ? "—" : `${data.average_response_hours} hours`],
      ]
    : [];

  return (
    <main className="stats-page">
      <section className="stats-hero">
        <div>
          <span className="eyebrow">PUBLIC CIVIC INTELLIGENCE</span>
          <h1>How is your area performing?</h1>
          <p>Privacy-preserving grievance outcomes, trends and transparent civic rankings.</p>
        </div>
        <div className="score-chip">
          <ShieldCheck size={16} style={{ verticalAlign: "-3px", marginRight: "0.35rem" }} />
          Aggregated data only<br /><strong>No citizen identities</strong>
        </div>
      </section>

      <section className="geo-bar">
        {levels.map((key) => (
          <label key={key}>
            <span>{key}</span>
            <select value={filters[key] || ""} onChange={(e) => choose(key, e.target.value)}>
              <option value="">All {key}s</option>
              {(loc[`${key}s`] || []).map((value) => <option key={value}>{value}</option>)}
            </select>
          </label>
        ))}
      </section>

      {data === null ? (
        <div className="loading-state"><span className="spinner" /> Loading public statistics...</div>
      ) : data?.insufficient_data ? (
        <div className="privacy-panel">
          <h2>Insufficient data</h2>
          <p>Detailed statistics are hidden until at least {data.minimum_sample_size} eligible grievances are available for this selection.</p>
        </div>
      ) : (
        <>
          <section className="metric-grid">
            {cards.map(([label, value]) => <article key={label}><span>{label}</span><strong>{value}</strong></article>)}
          </section>

          <section className="stats-grid">
            <article className="panel">
              <h2><TrendingUp size={17} style={{ verticalAlign: "-3px", marginRight: "0.4rem" }} />Monthly grievance trend</h2>
              <div className="bars">
                {trends.slice(-8).map((item) => (
                  <div className="bar-row" key={item.period}>
                    <span>{item.period}</span><div><i style={{ width: `${Math.min(100, item.total * 5)}%` }} /></div><b>{item.total}</b>
                  </div>
                ))}
              </div>
              <p className="muted">Only time buckets meeting the minimum aggregation threshold are displayed.</p>
            </article>
            <article className="panel">
              <h2>Categories</h2>
              {cats.slice(0, 8).map((item) => <div className="list-row" key={item.id}><span>{item.name}</span><b>{item.resolution_rate}%</b></div>)}
            </article>
            <article className="panel">
              <h2>Departments</h2>
              {deps.slice(0, 8).map((item) => <div className="list-row" key={item.id}><span>{item.name}</span><b>{item.resolution_rate}%</b></div>)}
            </article>
          </section>
        </>
      )}

      <section className="panel ranking">
        <div className="panel-head">
          <div><span className="eyebrow">CIVIC PERFORMANCE LEAGUE</span><h2><Trophy size={17} style={{ verticalAlign: "-3px", marginRight: "0.4rem" }} />Top Performing Areas</h2></div>
          <select value={level} onChange={(e) => setLevel(e.target.value)}>{levels.map((x) => <option key={x} value={x}>{x}</option>)}</select>
        </div>
        {rank.length ? rank.slice(0, 10).map((item) => (
          <div className="rank-row" key={item.location}>
            <strong>#{item.rank}</strong><span>{item.location}</span>
            <small>{item.grievance_volume} grievances · {item.resolution_rate}% resolved · {item.average_resolution_days ?? "—"} days</small>
            <b>{item.score}</b>
          </div>
        )) : <p className="muted">No locations currently meet the minimum sample threshold.</p>}
        <details>
          <summary>How is this score calculated?</summary>
          <p>Resolution performance, timeliness, citizen satisfaction, and low dispute/reopen rate are combined using the published weights below. Raw grievance volume is not itself a score component.</p>
          <div className="list-row"><span>Resolution performance</span><b>40%</b></div>
          <div className="list-row"><span>Timeliness</span><b>25%</b></div>
          <div className="list-row"><span>Citizen satisfaction</span><b>20%</b></div>
          <div className="list-row"><span>Low dispute/reopen rate</span><b>15%</b></div>
          {rank[0] && <p className="muted">Example component values for {rank[0].location}: resolution {rank[0].resolution_rate}%, timeliness score {rank[0].timeliness_score}, satisfaction score {rank[0].citizen_satisfaction ?? "—"}, low-dispute score {rank[0].low_dispute_score}.</p>}
          <p className="muted">Locations below the minimum sample threshold are excluded. SLA is excluded because the current system has no authoritative SLA target field.</p>
        </details>
      </section>

      <section className="stats-grid">
        <article className="panel">
          <div className="panel-head"><div><span className="eyebrow">MOST IMPROVED</span><h2><Sparkles size={17} style={{ verticalAlign: "-3px", marginRight: "0.4rem" }} />Fastest Improving Areas</h2></div></div>
          {improved.length ? improved.slice(0, 5).map((item) => (
            <div className="rank-row" key={item.location}><strong>#{item.rank}</strong><span>{item.location}</span><small>{item.previous_score} → {item.current_score}</small><b>+{item.improvement_percent ?? item.improvement}%</b></div>
          )) : <p className="muted">No comparable locations have enough data in both periods.</p>}
        </article>

        <article className="panel">
          <div className="panel-head"><div><span className="eyebrow">CATEGORY LEADERBOARD</span><h2>Best Resolution by Category</h2></div>
            <select value={selectedCategory} onChange={(e) => setSelectedCategory(e.target.value)}>
              <option value="">Choose category</option>
              {cats.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}
            </select>
          </div>
          {categoryRank.length ? categoryRank.slice(0, 5).map((item) => (
            <div className="rank-row" key={item.location}><strong>#{item.rank}</strong><span>{item.location}</span><small>{item.grievance_volume} grievances · {item.resolution_rate}% resolved</small><b>{item.score}</b></div>
          )) : <p className="muted">Select a category to view its geographic leaderboard.</p>}
        </article>
      </section>
    </main>
  );
}
