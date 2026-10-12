// Fonctions partagées par les pages.

async function api(method, url, body) {
  const opts = { method, headers: {} };
  if (body !== undefined) {
    opts.headers["Content-Type"] = "application/json";
    opts.body = JSON.stringify(body);
  }
  const res = await fetch(url, opts);
  let data = null;
  try { data = await res.json(); } catch (e) { /* réponse vide */ }
  if (!res.ok) {
    const msg = data && data.detail ? (typeof data.detail === "string" ? data.detail : "Requête invalide") : `Erreur ${res.status}`;
    throw new Error(msg);
  }
  return data;
}

function esc(s) {
  return String(s ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

let toastTimer;
function toast(msg, isError = false) {
  let el = document.querySelector(".toast");
  if (!el) { el = document.createElement("div"); document.body.appendChild(el); }
  el.className = "toast" + (isError ? " error" : "");
  el.textContent = msg;
  el.hidden = false;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => { el.hidden = true; }, isError ? 4500 : 2200);
}

function fmtDuration(seconds) {
  if (!seconds && seconds !== 0) return "";
  seconds = Math.round(seconds);
  const h = Math.floor(seconds / 3600), m = Math.floor((seconds % 3600) / 60), s = seconds % 60;
  return h ? `${h} h ${String(m).padStart(2, "0")}` : `${m}:${String(s).padStart(2, "0")}`;
}

function fmtDate(ts) {
  return new Date(ts * 1000).toLocaleString("fr-FR", { weekday: "short", day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" });
}

// Tableau de score (HTML). `score` vient de l'API (spash/tennis.py:compute).
function scoreboardHTML(teamA, teamB, score, info) {
  const names = [teamA, teamB];
  const rows = [0, 1].map(i => {
    const sets = score.sets.map(s => {
      const tb = s.tiebreak && s.games[i] < s.games[1 - i] ? `<sup>${s.tiebreak[i]}</sup>` : "";
      return `<span>${s.games[i]}${tb}</span>`;
    });
    if (!score.finished && !score.super_tiebreak) sets.push(`<span class="current">${score.games[i]}</span>`);
    const cls = [
      !score.finished && score.server === i ? "serving" : "",
      score.finished && score.winner === i ? "winner" : "",
    ].join(" ");
    const pts = score.finished ? "" : esc(score.points[i]);
    return `<div class="sb-row ${cls}">
      <div class="sb-serve" title="Au service"></div>
      <div class="sb-name">${esc(names[i])}</div>
      <div class="sb-sets">${sets.join("")}</div>
      <div class="sb-points ${score.finished ? "empty" : ""}">${pts}</div>
    </div>`;
  }).join("");
  let extra = "";
  if (info) extra = `<div class="sb-info">${esc(info)}</div>`;
  return rows + extra;
}

function scoreInfo(score) {
  if (score.finished) return "Match terminé";
  if (score.super_tiebreak) return "Super tie-break (10 points)";
  if (score.tiebreak) return "Tie-break";
  return "";
}
