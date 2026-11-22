// app.js - builds each tab from the PLAYERS array defined in players.js.
// Each tab has its own small function below. Add a new tab by:
//   1. adding a <button> and a <section> in index.html
//   2. writing a render function here and calling it at the bottom.

// ---------- Helpers ----------

const COUNTRY_NAMES = {
  ARG: "Argentina", AUS: "Australia", AUT: "Austria", BEL: "Belgium", BIH: "Bosnia & Herzegovina",
  BOL: "Bolivia", BRA: "Brazil", BUL: "Bulgaria", CAN: "Canada", CHI: "Chile", CHN: "China",
  COL: "Colombia", CRO: "Croatia", CZE: "Czechia", DEN: "Denmark", DOM: "Dominican Republic",
  ECU: "Ecuador", ESP: "Spain", EST: "Estonia", FIN: "Finland", FRA: "France", GBR: "Great Britain",
  GEO: "Georgia", GER: "Germany", GRE: "Greece", HKG: "Hong Kong", HUN: "Hungary", IND: "India",
  IRL: "Ireland", ISR: "Israel", ITA: "Italy", JPN: "Japan", KAZ: "Kazakhstan", KOR: "South Korea",
  LAT: "Latvia", LTU: "Lithuania", LUX: "Luxembourg", MEX: "Mexico", MON: "Monaco", NED: "Netherlands",
  NOR: "Norway", NZL: "New Zealand", PAR: "Paraguay", PER: "Peru", POL: "Poland", POR: "Portugal",
  ROU: "Romania", RSA: "South Africa", RUS: "Russia", SLO: "Slovenia", SRB: "Serbia", SUI: "Switzerland",
  SVK: "Slovakia", SWE: "Sweden", TPE: "Chinese Taipei", TUN: "Tunisia", TUR: "Turkey", UKR: "Ukraine",
  URU: "Uruguay", USA: "United States", UZB: "Uzbekistan", VEN: "Venezuela",
};

// The ranking source uses 3-letter sports codes; flag images are named by 2-letter ISO codes.
const FLAG_CODES = {
  ARG: "ar", AUS: "au", AUT: "at", BEL: "be", BIH: "ba", BOL: "bo", BRA: "br", BUL: "bg", CAN: "ca",
  CHI: "cl", CHN: "cn", COL: "co", CRO: "hr", CZE: "cz", DEN: "dk", DOM: "do", ECU: "ec", ESP: "es",
  EST: "ee", FIN: "fi", FRA: "fr", GBR: "gb", GEO: "ge", GER: "de", GRE: "gr", HKG: "hk", HUN: "hu",
  IND: "in", IRL: "ie", ISR: "il", ITA: "it", JPN: "jp", KAZ: "kz", KOR: "kr", LAT: "lv", LTU: "lt",
  LUX: "lu", MEX: "mx", MON: "mc", NED: "nl", NOR: "no", NZL: "nz", PAR: "py", PER: "pe", POL: "pl",
  POR: "pt", ROU: "ro", RSA: "za", RUS: "ru", SLO: "si", SRB: "rs", SUI: "ch", SVK: "sk", SWE: "se",
  TPE: "tw", TUN: "tn", TUR: "tr", UKR: "ua", URU: "uy", USA: "us", UZB: "uz", VEN: "ve",
};

function countryName(code) {
  return COUNTRY_NAMES[code] || code;
}

// Flag image (from flagcdn.com) with the country name as a hover tooltip.
// Unknown codes fall back to the plain 3-letter code.
function flag(code) {
  const name = countryName(code);
  const iso = FLAG_CODES[code];
  if (!iso) return `<span title="${name}">${code}</span>`;
  return `<img class="flag" src="https://flagcdn.com/w40/${iso}.png"
    srcset="https://flagcdn.com/w80/${iso}.png 2x" width="24" height="18"
    alt="${name}" title="${name}" loading="lazy">`;
}

// 188 -> "6'2\""
function cmToFeetInches(cm) {
  const totalInches = Math.round(cm / 2.54);
  return `${Math.floor(totalInches / 12)}'${totalInches % 12}"`;
}

// Builds an HTML table from a list of players.
function playersTable(players) {
  const rows = players.map(p => `
    <tr>
      <td class="num">${p.rank}</td>
      <td>${p.name}</td>
      <td>${flag(p.country)}</td>
      <td class="num">${p.height} cm</td>
    </tr>`).join("");
  return `
    <table>
      <thead><tr><th class="num">Rank</th><th>Player</th><th>Country</th><th class="num">Height</th></tr></thead>
      <tbody>${rows}</tbody>
    </table>`;
}

// Players with full details. New players that are not in player-details.json yet
// (height is null) still appear by country, but are left out of the other stats.
const COMPLETE = PLAYERS.filter(p => p.height !== null);

function percent(count) {
  return Math.round((count / COMPLETE.length) * 100);
}

// ---------- Tab 1: left-handers ----------

function renderLefties() {
  const lefties = COMPLETE.filter(p => p.hand === "L");
  document.getElementById("lefties").innerHTML = `
    <div class="card">
      <div class="big-number">${lefties.length} <span class="muted" style="font-size:1.2rem">of ${COMPLETE.length} (${percent(lefties.length)}%)</span></div>
      <p class="muted">players in the top 100 are left-handed.</p>
    </div>
    <div class="card">
      <h2>Left-handed players</h2>
      ${playersTable(lefties)}
    </div>`;
}

// ---------- Tab 2: one-handed backhands ----------

function renderOneHanders() {
  const oneHanders = COMPLETE.filter(p => p.backhand === "1H");
  document.getElementById("onehanders").innerHTML = `
    <div class="card">
      <div class="big-number">${oneHanders.length} <span class="muted" style="font-size:1.2rem">of ${COMPLETE.length} (${percent(oneHanders.length)}%)</span></div>
      <p class="muted">players in the top 100 hit a one-handed backhand.</p>
    </div>
    <div class="card">
      <h2>One-handed backhand players</h2>
      ${playersTable(oneHanders)}
    </div>`;
}

// ---------- Tab 3: players by country ----------

function renderCountries() {
  // Group players by country code: { ITA: [player, player...], ... }
  const groups = {};
  PLAYERS.forEach(p => {
    (groups[p.country] = groups[p.country] || []).push(p);
  });

  // Sort by number of players (most first), then alphabetically.
  const sorted = Object.entries(groups).sort((a, b) =>
    b[1].length - a[1].length || countryName(a[0]).localeCompare(countryName(b[0]))
  );

  const maxCount = sorted[0][1].length;

  const rows = sorted.map(([code, players]) => `
    <div class="country-row">
      <div class="country-head">
        <span class="country-name">${flag(code)} ${countryName(code)}</span>
        <div class="bar-track"><div class="bar" style="width:${(players.length / maxCount) * 100}%"></div></div>
        <span class="country-count">${players.length}</span>
      </div>
      <p class="country-players">${players.map(p => `${p.name} (${p.rank})`).join(", ")}</p>
    </div>`).join("");

  document.getElementById("countries").innerHTML = `
    <div class="card">
      <h2>Players in the top 100 by country</h2>
      <p class="muted">${sorted.length} countries represented. Ranking in brackets.</p>
      ${rows}
    </div>`;
}

// ---------- Tab 4: average height ----------

function renderHeight() {
  const total = COMPLETE.reduce((sum, p) => sum + p.height, 0);
  const average = total / COMPLETE.length;

  const byHeight = [...COMPLETE].sort((a, b) => b.height - a.height || a.rank - b.rank);
  const tallest = byHeight.slice(0, 5);
  const shortest = byHeight.slice(-5).reverse();

  const miniList = list => `
    <table><tbody>
      ${list.map(p => `<tr><td>${p.name}</td><td class="num">${p.height} cm</td></tr>`).join("")}
    </tbody></table>`;

  document.getElementById("height").innerHTML = `
    <div class="card">
      <div class="big-number">${average.toFixed(1)} cm</div>
      <p class="muted">average height of the top 100 (about ${cmToFeetInches(average)}).</p>
    </div>
    <div class="two-cols">
      <div class="card"><h2>Tallest 5</h2>${miniList(tallest)}</div>
      <div class="card"><h2>Shortest 5</h2>${miniList(shortest)}</div>
    </div>
    <div class="card">
      <h2>All players, tallest first</h2>
      ${playersTable(byHeight)}
    </div>`;
}

// ---------- Tab switching ----------

function setupTabs() {
  const buttons = document.querySelectorAll(".tabs button");
  const panels = document.querySelectorAll(".panel");

  buttons.forEach(button => {
    button.addEventListener("click", () => {
      buttons.forEach(b => b.classList.toggle("active", b === button));
      panels.forEach(p => p.classList.toggle("active", p.id === button.dataset.tab));
    });
  });
}

// ---------- Header date ----------

function renderMeta() {
  const el = document.getElementById("updated");
  if (el) el.textContent = `rankings dated ${LAST_UPDATED}`;
}

// ---------- Start ----------
// Each step runs on its own, so one problem can't blank the whole page.

[renderMeta, renderLefties, renderOneHanders, renderCountries, renderHeight, setupTabs]
  .forEach(step => {
    try {
      step();
    } catch (error) {
      console.error(`${step.name} failed:`, error);
    }
  });
