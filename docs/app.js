// Fishing Companion — dashboard interactions.
// Vanilla JS, no framework, no build step.

(function () {
  "use strict";

  const dataEl = document.getElementById("dashboard-data");
  const dialog = document.getElementById("detail-dialog");
  const titleEl = document.getElementById("detail-title");
  const contentEl = document.getElementById("detail-content");
  if (!dataEl || !dialog || !titleEl || !contentEl) return;

  const data = JSON.parse(dataEl.textContent);

  function escapeHtml(s) {
    return String(s)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#039;");
  }

  function formatTrend(v) {
    return (v > 0 ? "+" : "") + v.toFixed(1);
  }

  function formatPeriods(periods) {
    if (!periods || periods.length === 0) return "<em>—</em>";
    return periods
      .map(function (p) {
        return p[0] + " → " + p[1];
      })
      .join(" · ");
  }

  function moonLabel(phase) {
    if (phase < 0.05 || phase > 0.95) return "Nouvelle lune";
    if (phase < 0.20) return "Premier croissant";
    if (phase < 0.30) return "Premier quartier";
    if (phase < 0.45) return "Gibbeuse croissante";
    if (phase < 0.55) return "Pleine lune";
    if (phase < 0.70) return "Gibbeuse décroissante";
    if (phase < 0.80) return "Dernier quartier";
    return "Dernier croissant";
  }

  function renderDetail(spotId, dateIso, speciesId) {
    const spot = data.spots[spotId];
    if (!spot) return;
    const day = spot.days[dateIso];
    if (!day) return;
    const scores = day.scores[speciesId];
    const species = data.species_meta[speciesId];
    if (!scores || !species) return;

    titleEl.textContent =
      species.emoji + " " + species.name + " — " + spot.name + " — " + dateIso;

    let html = '<p class="big-score">Score : <strong>' +
      scores.total + "</strong> / 100</p>";

    html += "<h4>Sous-scores</h4>";
    html += '<dl class="grid">' +
      "<dt>Thermique (25%)</dt><dd>" + scores.thermal.toFixed(1) + "</dd>" +
      "<dt>Pression (25%)</dt><dd>" + scores.pressure.toFixed(1) + "</dd>" +
      "<dt>Solunaire (20%)</dt><dd>" + scores.solunar.toFixed(1) + "</dd>" +
      "<dt>Lune (10%)</dt><dd>" + scores.moon.toFixed(1) + "</dd>" +
      "<dt>Météo (20%)</dt><dd>" + scores.weather.toFixed(1) + "</dd>" +
      "</dl>";

    const w = day.weather;
    if (w) {
      html += "<h4>Conditions météo</h4>";
      html += '<dl class="grid">' +
        "<dt>Temp. moyenne</dt><dd>" + w.air_temp_avg.toFixed(1) + " °C</dd>" +
        "<dt>Pression</dt><dd>" + w.pressure_now.toFixed(1) + " hPa (" +
          escapeHtml(formatTrend(w.trend_24h)) + " / 24h)</dd>" +
        "<dt>Nuages</dt><dd>" + w.cloud_avg.toFixed(0) + " %</dd>" +
        "<dt>Vent max</dt><dd>" + w.wind_max.toFixed(1) + " km/h</dd>" +
        "<dt>Pluie</dt><dd>" + w.precip_total.toFixed(1) + " mm</dd>" +
        "</dl>";
    }

    const s = day.solunar;
    if (s) {
      html += "<h4>Solunaire</h4>";
      html += '<dl class="grid">' +
        "<dt>Soleil</dt><dd>↑ " + s.sunrise + " · ↓ " + s.sunset + "</dd>" +
        "<dt>Lune</dt><dd>↑ " + (s.moonrise || "—") + " · ↓ " +
          (s.moonset || "—") + "</dd>" +
        "<dt>Phase</dt><dd>" + escapeHtml(moonLabel(s.moon_phase)) +
          " (" + Math.round(s.moon_phase * 100) + " %)</dd>" +
        "<dt>Périodes majeures</dt><dd>" + formatPeriods(s.major_periods) +
          "</dd>" +
        "<dt>Périodes mineures</dt><dd>" + formatPeriods(s.minor_periods) +
          "</dd>" +
        "</dl>";
    }

    contentEl.innerHTML = html;
    if (typeof dialog.showModal === "function") {
      dialog.showModal();
    } else {
      dialog.setAttribute("open", "");
    }
  }

  document.addEventListener("click", function (e) {
    const cell = e.target.closest(".cell[data-spot]");
    if (cell) {
      renderDetail(cell.dataset.spot, cell.dataset.date, cell.dataset.species);
    }
  });

  document.addEventListener("keydown", function (e) {
    if ((e.key === "Enter" || e.key === " ") &&
        e.target.matches(".cell[data-spot]")) {
      e.preventDefault();
      renderDetail(
        e.target.dataset.spot,
        e.target.dataset.date,
        e.target.dataset.species
      );
    }
  });

  dialog.querySelector(".close").addEventListener("click", function () {
    dialog.close();
  });

  // Close on click outside the dialog content (backdrop area).
  dialog.addEventListener("click", function (e) {
    const rect = dialog.getBoundingClientRect();
    const inside =
      e.clientX >= rect.left && e.clientX <= rect.right &&
      e.clientY >= rect.top && e.clientY <= rect.bottom;
    if (!inside) dialog.close();
  });
})();
