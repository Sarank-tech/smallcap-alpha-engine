#!/usr/bin/env python3
"""
NSE Multibagger Discovery System — Dashboard HTML Generator
============================================================
Program Name: generate_dashboard.py

Objective:
Reads output CSV files from Stages 1–5 and compiles a single, self-contained,
production-grade interactive HTML Dashboard (`index.html`).

Outputs:
  - index.html (Viewable directly in any browser)
"""

import sys
import json
import logging
from pathlib import Path
from datetime import datetime

import pandas as pd

ROOT_DIR    = Path(__file__).resolve().parent.parent  # smallcap-alpha-engine/
OUTPUTS_DIR = ROOT_DIR / "outputs"
OUTPUT_HTML = ROOT_DIR / "index.html"

# CSV Input Files (read from outputs/)
FILE_STAGE1 = OUTPUTS_DIR / "turnaround_shortlist.csv"
FILE_STAGE2 = OUTPUTS_DIR / "business_momentum_ranked.csv"
FILE_STAGE3 = OUTPUTS_DIR / "stage3_ai_scores.csv"
FILE_STAGE4 = OUTPUTS_DIR / "final_multibagger_ranking.csv"
FILE_STAGE5 = OUTPUTS_DIR / "portfolio_plan.csv"


def load_csv_as_json(path: Path) -> list:
    if not path.exists():
        return []
    try:
        df = pd.read_csv(path)
        df = df.fillna("N/A")
        return df.to_dict(orient="records")
    except Exception:
        return []


def generate_html_dashboard():
    now_str = datetime.now().strftime("%d %B %Y, %H:%M:%S")

    data_s1 = load_csv_as_json(FILE_STAGE1)
    data_s2 = load_csv_as_json(FILE_STAGE2)
    data_s3 = load_csv_as_json(FILE_STAGE3)
    data_s4 = load_csv_as_json(FILE_STAGE4)
    data_s5 = load_csv_as_json(FILE_STAGE5)

    # Compute dynamic portfolio capital from Stage 5 data
    total_capital = 0.0
    for r in data_s5:
        val = r.get("Position Size (INR)")
        if val != "N/A" and val is not None:
            try:
                total_capital += float(val)
            except ValueError:
                pass

    if total_capital > 0:
        total_cap_str = f"₹{int(round(total_capital)):,}"
    else:
        total_cap_str = "₹10,00,000"

    payload = {
        "generated_at": now_str,
        "stage1": data_s1,
        "stage2": data_s2,
        "stage3": data_s3,
        "stage4": data_s4,
        "stage5": data_s5,
    }

    payload_json = json.dumps(payload, indent=2)

    html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>NSE Multibagger Stock Discovery & Portfolio Dashboard</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&family=Outfit:wght@500;600;700;800&display=swap" rel="stylesheet">
  <style>
    :root {{
      --bg-dark: #0B0F19;
      --bg-card: #131B2E;
      --bg-card-hover: #1A243B;
      --border-color: #232F4A;
      --border-glow: #3B82F6;
      --text-main: #F1F5F9;
      --text-muted: #94A3B8;
      --accent-blue: #3B82F6;
      --accent-emerald: #10B981;
      --accent-purple: #8B5CF6;
      --accent-amber: #F59E0B;
      --accent-rose: #F43F5E;
      --font-heading: 'Outfit', sans-serif;
      --font-body: 'Inter', sans-serif;
    }}

    * {{
      box-sizing: border-box;
      margin: 0;
      padding: 0;
    }}

    body {{
      background-color: var(--bg-dark);
      color: var(--text-main);
      font-family: var(--font-body);
      line-height: 1.6;
      padding-bottom: 60px;
    }}

    /* Header */
    header {{
      background: linear-gradient(135deg, #0F172A 0%, #1E1B4B 50%, #0F172A 100%);
      border-bottom: 1px solid var(--border-color);
      padding: 30px 40px;
      display: flex;
      justify-content: space-between;
      align-items: center;
      flex-wrap: wrap;
      gap: 20px;
    }}

    .header-title h1 {{
      font-family: var(--font-heading);
      font-size: 26px;
      font-weight: 800;
      background: linear-gradient(90deg, #60A5FA, #A78BFA, #34D399);
      -webkit-background-clip: text;
      -webkit-text-fill-color: transparent;
      margin-bottom: 4px;
    }}

    .header-title p {{
      color: var(--text-muted);
      font-size: 13px;
    }}

    .header-badge {{
      background: rgba(59, 130, 246, 0.15);
      border: 1px solid rgba(59, 130, 246, 0.4);
      color: #93C5FD;
      padding: 6px 14px;
      border-radius: 20px;
      font-size: 12px;
      font-weight: 600;
    }}

    /* Container */
    .container {{
      max-width: 1400px;
      margin: 0 auto;
      padding: 30px 20px;
    }}

    /* KPI Summary Grid */
    .kpi-grid {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
      gap: 20px;
      margin-bottom: 35px;
    }}

    .kpi-card {{
      background: var(--bg-card);
      border: 1px solid var(--border-color);
      border-radius: 14px;
      padding: 22px;
      position: relative;
      overflow: hidden;
      transition: transform 0.2s ease, border-color 0.2s ease;
    }}

    .kpi-card:hover {{
      transform: translateY(-3px);
      border-color: var(--accent-blue);
    }}

    .kpi-card::before {{
      content: '';
      position: absolute;
      top: 0;
      left: 0;
      width: 4px;
      height: 100%;
    }}

    .kpi-card.blue::before {{ background: var(--accent-blue); }}
    .kpi-card.emerald::before {{ background: var(--accent-emerald); }}
    .kpi-card.purple::before {{ background: var(--accent-purple); }}
    .kpi-card.amber::before {{ background: var(--accent-amber); }}

    .kpi-label {{
      font-size: 12px;
      text-transform: uppercase;
      letter-spacing: 0.5px;
      color: var(--text-muted);
      margin-bottom: 6px;
      font-weight: 600;
    }}

    .kpi-value {{
      font-family: var(--font-heading);
      font-size: 28px;
      font-weight: 700;
      color: var(--text-main);
    }}

    .kpi-subtext {{
      font-size: 12px;
      color: var(--accent-emerald);
      margin-top: 4px;
      font-weight: 500;
    }}

    /* Navigation Tabs */
    .tabs-nav {{
      display: flex;
      gap: 10px;
      border-bottom: 2px solid var(--border-color);
      margin-bottom: 30px;
      overflow-x: auto;
      padding-bottom: 2px;
    }}

    .tab-btn {{
      background: transparent;
      border: none;
      color: var(--text-muted);
      font-family: var(--font-heading);
      font-size: 14px;
      font-weight: 600;
      padding: 12px 20px;
      cursor: pointer;
      border-bottom: 3px solid transparent;
      transition: all 0.2s ease;
      white-space: nowrap;
      border-radius: 8px 8px 0 0;
    }}

    .tab-btn:hover {{
      color: var(--text-main);
      background: rgba(255, 255, 255, 0.03);
    }}

    .tab-btn.active {{
      color: #60A5FA;
      border-bottom-color: var(--accent-blue);
      background: rgba(59, 130, 246, 0.08);
    }}

    /* Search & Filter Bar */
    .toolbar {{
      display: flex;
      justify-content: space-between;
      align-items: center;
      gap: 15px;
      margin-bottom: 20px;
      flex-wrap: wrap;
    }}

    .search-box {{
      position: relative;
      width: 320px;
    }}

    .search-box input {{
      width: 100%;
      background: var(--bg-card);
      border: 1px solid var(--border-color);
      border-radius: 8px;
      padding: 10px 16px 10px 40px;
      color: var(--text-main);
      font-size: 13px;
      outline: none;
    }}

    .search-box input:focus {{
      border-color: var(--accent-blue);
      box-shadow: 0 0 0 3px rgba(59, 130, 246, 0.2);
    }}

    .search-box::before {{
      content: '🔍';
      position: absolute;
      left: 14px;
      top: 50%;
      transform: translateY(-50%);
      font-size: 14px;
      opacity: 0.6;
    }}

    /* Tab Content Section */
    .tab-pane {{
      display: none;
    }}

    .tab-pane.active {{
      display: block;
      animation: fadeIn 0.3s ease;
    }}

    @keyframes fadeIn {{
      from {{ opacity: 0; transform: translateY(6px); }}
      to {{ opacity: 1; transform: translateY(0); }}
    }}

    /* Tables */
    .table-container {{
      background: var(--bg-card);
      border: 1px solid var(--border-color);
      border-radius: 12px;
      overflow-x: auto;
      box-shadow: 0 10px 30px rgba(0, 0, 0, 0.3);
    }}

    table {{
      width: 100%;
      border-collapse: collapse;
      text-align: left;
      font-size: 13px;
    }}

    th {{
      background: #172036;
      color: #94A3B8;
      font-family: var(--font-heading);
      font-weight: 600;
      padding: 14px 18px;
      border-bottom: 1px solid var(--border-color);
      white-space: nowrap;
      text-transform: uppercase;
      letter-spacing: 0.5px;
      font-size: 11px;
    }}

    td {{
      padding: 14px 18px;
      border-bottom: 1px solid var(--border-color);
      color: #E2E8F0;
    }}

    tr:last-child td {{
      border-bottom: none;
    }}

    tr:hover td {{
      background-color: var(--bg-card-hover);
    }}

    /* Badges & Tags */
    .badge {{
      display: inline-block;
      padding: 4px 10px;
      border-radius: 6px;
      font-size: 11px;
      font-weight: 700;
      text-transform: uppercase;
      letter-spacing: 0.3px;
    }}

    .badge-rank {{
      background: rgba(245, 158, 11, 0.15);
      color: #FBBF24;
      border: 1px solid rgba(245, 158, 11, 0.3);
    }}

    .badge-p1 {{
      background: rgba(16, 185, 129, 0.15);
      color: #34D399;
      border: 1px solid rgba(16, 185, 129, 0.3);
    }}

    .badge-p2 {{
      background: rgba(59, 130, 246, 0.15);
      color: #60A5FA;
      border: 1px solid rgba(59, 130, 246, 0.3);
    }}

    .badge-p3 {{
      background: rgba(245, 158, 11, 0.15);
      color: #FBBF24;
      border: 1px solid rgba(245, 158, 11, 0.3);
    }}

    .badge-exceptional {{
      background: rgba(16, 185, 129, 0.2);
      color: #10B981;
      border: 1px solid #10B981;
    }}

    .badge-strong {{
      background: rgba(59, 130, 246, 0.2);
      color: #3B82F6;
      border: 1px solid #3B82F6;
    }}

    .badge-watchlist {{
      background: rgba(245, 158, 11, 0.2);
      color: #F59E0B;
      border: 1px solid #F59E0B;
    }}

    .ticker-symbol {{
      font-weight: 700;
      color: #60A5FA;
      font-family: var(--font-heading);
    }}

    .score-pill {{
      display: inline-block;
      font-weight: 700;
      padding: 3px 8px;
      border-radius: 4px;
      background: rgba(255, 255, 255, 0.06);
    }}

    .thesis-text {{
      font-size: 12px;
      color: var(--text-muted);
      max-width: 340px;
      line-height: 1.4;
    }}

    /* Card Details Grid */
    .detail-grid {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(340px, 1fr));
      gap: 20px;
      margin-top: 20px;
    }}

    .stock-card {{
      background: var(--bg-card);
      border: 1px solid var(--border-color);
      border-radius: 14px;
      padding: 24px;
    }}

    .stock-card-header {{
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin-bottom: 16px;
      border-bottom: 1px solid var(--border-color);
      padding-bottom: 12px;
    }}

    .stock-title {{
      font-family: var(--font-heading);
      font-size: 18px;
      font-weight: 700;
      color: var(--text-main);
    }}

    .stock-meta {{
      font-size: 12px;
      color: var(--text-muted);
    }}

    .metric-row {{
      display: flex;
      justify-content: space-between;
      font-size: 13px;
      padding: 6px 0;
      border-bottom: 1px dashed rgba(255, 255, 255, 0.05);
    }}

    .metric-row:last-child {{
      border-bottom: none;
    }}

    .metric-name {{
      color: var(--text-muted);
    }}

    .metric-val {{
      font-weight: 600;
      color: var(--text-main);
    }}

    /* Footer */
    footer {{
      margin-top: 50px;
      text-align: center;
      font-size: 12px;
      color: var(--text-muted);
      border-top: 1px solid var(--border-color);
      padding-top: 20px;
    }}
  </style>
</head>
<body>

  <header>
    <div class="header-title">
      <h1>NSE Multibagger Discovery System</h1>
      <p>5-Stage Quantitative & Qualitative Equity Research Dashboard</p>
    </div>
    <div class="header-badge">
      Last Updated: <span id="gen-date">{now_str}</span>
    </div>
  </header>

  <div class="container">

    <!-- KPI Summary Grid -->
    <div class="kpi-grid">
      <div class="kpi-card blue">
        <div class="kpi-label">Universe Screened</div>
        <div class="kpi-value">250</div>
        <div class="kpi-subtext">Nifty Smallcap 250 Index</div>
      </div>
      <div class="kpi-card emerald">
        <div class="kpi-label">Passed Survival Filter</div>
        <div class="kpi-value" id="kpi-passed">7</div>
        <div class="kpi-subtext">Clean Balance Sheet & Turnaround</div>
      </div>
      <div class="kpi-card purple">
        <div class="kpi-label">Top Ranked Candidate</div>
        <div class="kpi-value" id="kpi-top-ticker">CONCORDBIO</div>
        <div class="kpi-subtext" id="kpi-top-score">Score: 91.91 / 100</div>
      </div>
      <div class="kpi-card amber">
        <div class="kpi-label">Portfolio Capital</div>
        <div class="kpi-value" id="kpi-total-capital">{total_cap_str}</div>
        <div class="kpi-subtext">Dynamic Allocation Plan</div>
      </div>
    </div>

    <!-- Toolbar (Search) -->
    <div class="toolbar">
      <div class="tabs-nav">
        <button class="tab-btn active" onclick="switchTab('stage5')">Stage 5: Portfolio Plan</button>
        <button class="tab-btn" onclick="switchTab('stage4')">Stage 4: Final Rankings</button>
        <button class="tab-btn" onclick="switchTab('stage3')">Stage 3: AI Business Scores</button>
        <button class="tab-btn" onclick="switchTab('stage2')">Stage 2: Momentum Scores</button>
        <button class="tab-btn" onclick="switchTab('stage1')">Stage 1: Survival Screener</button>
      </div>

      <div class="search-box">
        <input type="text" id="searchInput" onkeyup="filterTables()" placeholder="Search by Ticker or Category...">
      </div>
    </div>

    <!-- STAGE 5 PANE -->
    <div id="pane-stage5" class="tab-pane active">
      <div class="table-container">
        <table id="table-stage5">
          <thead>
            <tr>
              <th>Rank</th>
              <th>Ticker</th>
              <th>Final Score</th>
              <th>Allocation %</th>
              <th>Position Size (₹)</th>
              <th>Buy Priority</th>
              <th>Holding Period</th>
              <th>Slab-Wise Profit Booking Strategy</th>
              <th>Hard Stop Loss</th>
            </tr>
          </thead>
          <tbody id="tbody-stage5"></tbody>
        </table>
      </div>
    </div>

    <!-- STAGE 4 PANE -->
    <div id="pane-stage4" class="tab-pane">
      <div class="table-container">
        <table id="table-stage4">
          <thead>
            <tr>
              <th>Rank</th>
              <th>Ticker</th>
              <th>Final Score</th>
              <th>Financial (25%)</th>
              <th>Momentum (35%)</th>
              <th>AI Score (40%)</th>
              <th>Category</th>
              <th>Archetype</th>
              <th>Recommendation</th>
              <th>Investment Thesis</th>
            </tr>
          </thead>
          <tbody id="tbody-stage4"></tbody>
        </table>
      </div>
    </div>

    <!-- STAGE 3 PANE -->
    <div id="pane-stage3" class="tab-pane">
      <div class="table-container">
        <table id="table-stage3">
          <thead>
            <tr>
              <th>Ticker</th>
              <th>AI Score</th>
              <th>Business Quality</th>
              <th>Growth Visibility</th>
              <th>Management</th>
              <th>Competitive Moat</th>
              <th>Risk Safety</th>
              <th>Long-Term Potential</th>
              <th>Confidence</th>
            </tr>
          </thead>
          <tbody id="tbody-stage3"></tbody>
        </table>
      </div>
    </div>

    <!-- STAGE 2 PANE -->
    <div id="pane-stage2" class="tab-pane">
      <div class="table-container">
        <table id="table-stage2">
          <thead>
            <tr>
              <th>Rank</th>
              <th>Ticker</th>
              <th>Momentum Score</th>
              <th>Revenue Growth</th>
              <th>Net Income Growth</th>
              <th>EBITDA Trend</th>
              <th>Op Margin Trend</th>
              <th>EPS Trend</th>
              <th>Debt Trend</th>
              <th>Active Metrics</th>
            </tr>
          </thead>
          <tbody id="tbody-stage2"></tbody>
        </table>
      </div>
    </div>

    <!-- STAGE 1 PANE -->
    <div id="pane-stage1" class="tab-pane">
      <div class="table-container">
        <table id="table-stage1">
          <thead>
            <tr>
              <th>Ticker</th>
              <th>Market Cap (Cr)</th>
              <th>3M Avg Volume</th>
              <th>Debt / Equity</th>
              <th>Q1 Net Income (Cr)</th>
              <th>Current Price</th>
              <th>Status</th>
            </tr>
          </thead>
          <tbody id="tbody-stage1"></tbody>
        </table>
      </div>
    </div>

    <footer>
      <p>NSE Multibagger Stock Discovery System v5.0 — Automated Pipeline Dashboard</p>
      <p>For educational & quantitative research purposes only. Not financial advice.</p>
    </footer>

  </div>

  <script>
    const DATA = {payload_json};

    function renderTables() {{
      // Populate Stage 5
      const tbody5 = document.getElementById('tbody-stage5');
      tbody5.innerHTML = (DATA.stage5 || []).map(r => `
        <tr>
          <td><span class="badge badge-rank">#${{r.Rank || '-'}}</span></td>
          <td class="ticker-symbol">${{r.Ticker || ''}}</td>
          <td><span class="score-pill">${{r['Final Score'] || '-'}}</span></td>
          <td style="font-weight:700; color:#34D399;">${{r['Allocation %'] || '-'}}%</td>
          <td style="font-weight:700;">₹${{Number(r['Position Size (INR)'] || 0).toLocaleString('en-IN')}}</td>
          <td><span class="badge badge-p1">${{r['Buy Priority'] || ''}}</span></td>
          <td>${{r['Suggested Holding Period'] || ''}}</td>
          <td style="font-size:11px; color:#94A3B8;">${{r['Slab-wise Profit Booking'] || ''}}</td>
          <td style="color:#F43F5E; font-weight:600;">-12.0%</td>
        </tr>
      `).join('');

      // Populate Stage 4
      const tbody4 = document.getElementById('tbody-stage4');
      tbody4.innerHTML = (DATA.stage4 || []).map(r => `
        <tr>
          <td><span class="badge badge-rank">#${{r.Rank || '-'}}</span></td>
          <td class="ticker-symbol">${{r.Ticker || ''}}</td>
          <td><span class="score-pill" style="color:#60A5FA;">${{r['Final Score'] || '-'}}</span></td>
          <td>${{r['Financial Score'] || '-'}}</td>
          <td>${{r['Momentum Score'] || '-'}}</td>
          <td>${{r['AI Business Score'] || '-'}}</td>
          <td><span class="badge badge-exceptional">${{r['Investment Category'] || ''}}</span></td>
          <td><span class="badge badge-p2">${{r['Classification'] || ''}}</span></td>
          <td style="font-weight:700;">${{r['Recommendation'] || ''}}</td>
          <td class="thesis-text">"${{r['Investment Thesis'] || ''}}"</td>
        </tr>
      `).join('');

      // Populate Stage 3
      const tbody3 = document.getElementById('tbody-stage3');
      tbody3.innerHTML = (DATA.stage3 || []).map(r => `
        <tr>
          <td class="ticker-symbol">${{r.Ticker || ''}}</td>
          <td><span class="score-pill" style="color:#A78BFA;">${{r['Final AI Score'] || r['AI Business Score'] || '-'}}</span></td>
          <td>${{r['Business Quality'] || '-'}}</td>
          <td>${{r['Growth Visibility'] || '-'}}</td>
          <td>${{r['Management'] || '-'}}</td>
          <td>${{r['Competitive Advantage'] || '-'}}</td>
          <td>${{r['Risk'] || '-'}}</td>
          <td>${{r['Long-Term Potential'] || '-'}}</td>
          <td>${{r['Confidence'] || '-'}}%</td>
        </tr>
      `).join('');

      // Populate Stage 2
      const tbody2 = document.getElementById('tbody-stage2');
      tbody2.innerHTML = (DATA.stage2 || []).map(r => `
        <tr>
          <td><span class="badge badge-rank">#${{r.Rank || '-'}}</span></td>
          <td class="ticker-symbol">${{r.Ticker || ''}}</td>
          <td><span class="score-pill" style="color:#34D399;">${{r['Momentum Score'] || '-'}}</span></td>
          <td>${{r['Revenue Growth Score'] || '-'}}</td>
          <td>${{r['Net Income Growth Score'] || '-'}}</td>
          <td>${{r['EBITDA Trend Score'] || '-'}}</td>
          <td>${{r['Op Margin Trend Score'] || '-'}}</td>
          <td>${{r['EPS Trend Score'] || '-'}}</td>
          <td>${{r['Debt Trend Score'] || '-'}}</td>
          <td>${{r['Active Metrics'] || '-'}}</td>
        </tr>
      `).join('');

      // Populate Stage 1
      const tbody1 = document.getElementById('tbody-stage1');
      tbody1.innerHTML = (DATA.stage1 || []).map(r => `
        <tr>
          <td class="ticker-symbol">${{r.Ticker || ''}}</td>
          <td>₹${{r['Market Cap (Cr)'] || '-'}} Cr</td>
          <td>${{Number(r['3M Avg Vol'] || 0).toLocaleString('en-IN')}}</td>
          <td style="color:${{Number(r['Debt/Equity']) <= 0.25 ? '#34D399' : '#FBBF24'}};">${{r['Debt/Equity'] || '-'}}</td>
          <td>₹${{r['Q1 Net Income'] || '-'}} Cr</td>
          <td>${{r['Current Price'] || '-'}}</td>
          <td><span class="badge badge-p1">${{r.Status || 'PASSED'}}</span></td>
        </tr>
      `).join('');

      // KPI Top Candidate Update
      if (DATA.stage4 && DATA.stage4.length > 0) {{
        document.getElementById('kpi-top-ticker').innerText = DATA.stage4[0].Ticker.replace('.NS','');
        document.getElementById('kpi-top-score').innerText = 'Score: ' + DATA.stage4[0]['Final Score'] + ' / 100';
      }}
      if (DATA.stage1) {{
        document.getElementById('kpi-passed').innerText = DATA.stage1.length;
      }}
      if (DATA.stage5 && DATA.stage5.length > 0) {{
        let totalCap = 0;
        DATA.stage5.forEach(function(r) {{ totalCap += Number(r['Position Size (INR)'] || 0); }});
        if (totalCap > 0) {{
          document.getElementById('kpi-total-capital').innerText = '\u20b9' + Math.round(totalCap).toLocaleString('en-IN');
        }}
      }}
    }}

    function switchTab(tabId) {{
      document.querySelectorAll('.tab-btn').forEach(btn => btn.classList.remove('active'));
      document.querySelectorAll('.tab-pane').forEach(pane => pane.classList.remove('active'));

      event.target.classList.add('active');
      document.getElementById('pane-' + tabId).classList.add('active');
    }}

    function filterTables() {{
      const query = document.getElementById('searchInput').value.toLowerCase();
      document.querySelectorAll('tbody tr').forEach(tr => {{
        const text = tr.innerText.toLowerCase();
        tr.style.display = text.includes(query) ? '' : 'none';
      }});
    }}

    document.addEventListener('DOMContentLoaded', renderTables);
  </script>
</body>
</html>
"""

    OUTPUT_HTML.write_text(html_content, encoding="utf-8")
    print(f"Generated dashboard HTML: {OUTPUT_HTML.name} ({len(html_content)} bytes)")
    print(f"✨ Interactive Dashboard HTML generated: {OUTPUT_HTML}")


if __name__ == "__main__":
    generate_html_dashboard()
