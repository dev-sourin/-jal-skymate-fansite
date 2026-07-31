const state = { airports: [], results: [] };
const $ = (selector) => document.querySelector(selector);
const yen = new Intl.NumberFormat('ja-JP');

function localISODate(offset = 0) {
  const d = new Date();
  d.setDate(d.getDate() + offset);
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, '0');
  const day = String(d.getDate()).padStart(2, '0');
  return `${y}-${m}-${day}`;
}

function availabilityClass(type) {
  if (type === 'EXACT_SKYMATE') return 'exact';
  if (type === 'GENERAL_CURRENT' || type === 'GENERAL_D1') return 'reference';
  if (type === 'PREDICTED') return 'prediction';
  return 'unknown';
}

function durationLabel(minutes) {
  const h = Math.floor(minutes / 60);
  const m = minutes % 60;
  return h ? `${h}時間${m ? `${m}分` : ''}` : `${m}分`;
}

function formatObserved(value) {
  if (!value) return '取得時刻なし';
  return new Intl.DateTimeFormat('ja-JP', {
    month: 'numeric', day: 'numeric', hour: '2-digit', minute: '2-digit'
  }).format(new Date(value));
}

async function loadAirports() {
  const response = await fetch('/api/v1/airports');
  if (!response.ok) throw new Error('空港データを読み込めませんでした。');
  const data = await response.json();
  state.airports = data.airports;

  const origin = $('#origin');
  const destination = $('#destination');
  origin.innerHTML = '';
  for (const airport of state.airports) {
    const option = new Option(`${airport.city} — ${airport.name_ja} (${airport.iata_code})`, airport.iata_code);
    origin.add(option);
    destination.add(option.cloneNode(true));
  }
  origin.value = new URLSearchParams(location.search).get('origin') || 'HND';
}

function readURLIntoForm() {
  const params = new URLSearchParams(location.search);
  $('#flight-date').min = localISODate(0);
  $('#flight-date').value = params.get('date') || localISODate(0);
  $('#destination').value = params.get('destination') || '';
  $('#departure-period').value = params.get('departure_period') || 'all';
  $('#budget').value = params.get('budget') || '';
  $('#availability-filter').value = params.get('availability_filter') || 'all';
  $('#sort').value = params.get('sort') || 'departure';
}

function formParams() {
  const params = new URLSearchParams();
  params.set('origin', $('#origin').value);
  params.set('date', $('#flight-date').value);
  const optional = [
    ['destination', $('#destination').value],
    ['departure_period', $('#departure-period').value],
    ['budget', $('#budget').value],
    ['availability_filter', $('#availability-filter').value],
    ['sort', $('#sort').value],
  ];
  for (const [key, value] of optional) {
    if (value && value !== 'all' && !(key === 'sort' && value === 'departure')) params.set(key, value);
  }
  return params;
}

async function search({ updateURL = true } = {}) {
  const loading = $('#loading');
  const error = $('#error');
  const empty = $('#empty');
  const results = $('#results');
  loading.hidden = false; error.hidden = true; empty.hidden = true; results.innerHTML = '';

  const params = formParams();
  if (updateURL) history.replaceState(null, '', `?${params.toString()}`);

  try {
    const response = await fetch(`/api/v1/destinations?${params.toString()}`);
    if (!response.ok) throw new Error(`検索APIエラー (${response.status})`);
    const data = await response.json();
    state.results = data.results;
    $('#results-title').textContent = `${data.query.origin}発 — ${data.count}便`;
    $('#dataset-meta').textContent = `データ版 ${data.dataset.schedule_version} ／ ${data.dataset.data_mode}`;
    renderResults(data.results);
    empty.hidden = data.results.length !== 0;
  } catch (err) {
    error.textContent = err.message || '検索に失敗しました。';
    error.hidden = false;
  } finally {
    loading.hidden = true;
  }
}

function renderResults(items) {
  const container = $('#results');
  container.innerHTML = items.map((item, index) => {
    const av = item.availability;
    const fares = item.fares.map(fare => `
      <div class="fare-row">
        <span>${fare.productLabel}</span>
        <strong>¥${yen.format(fare.totalEstimate)}</strong>
      </div>`).join('') || '<span class="availability-note">対象日の運賃データなし</span>';
    return `
      <article class="flight-card">
        <div>
          <div class="route-line">
            <span class="airport-code">${item.origin.iata}</span>
            <span class="route-arrow">→</span>
            <span class="airport-code">${item.destination.iata}</span>
          </div>
          <p class="destination-name">${item.destination.city}・${item.destination.name}</p>
        </div>
        <div>
          <div class="flight-time"><strong>${item.flight.departure}</strong><span>→</span><strong>${item.flight.arrival}</strong></div>
          <p class="flight-meta">${item.flight.flightNo} ／ ${durationLabel(item.flight.durationMinutes)}</p>
        </div>
        <div class="fare-stack">${fares}</div>
        <div class="availability-box">
          <span class="availability-tag ${availabilityClass(av.type)}">${av.typeLabel}</span>
          <span class="availability-status">${av.statusLabel}${av.score !== null ? `（${av.score}点）` : ''}</span>
          <span class="availability-note">${formatObserved(av.observedAt)} 更新</span>
        </div>
        <button type="button" class="detail-button" data-index="${index}">詳細を見る</button>
      </article>`;
  }).join('');

  container.querySelectorAll('.detail-button').forEach(button => {
    button.addEventListener('click', () => openDetail(items[Number(button.dataset.index)]));
  });
}

function openDetail(item) {
  const av = item.availability;
  const fareRows = item.fares.map(fare => `
    <div class="factor"><span>${fare.productLabel}（施設使用料込み目安）</span><strong>¥${yen.format(fare.totalEstimate)}</strong></div>
  `).join('') || '<p>対象日の運賃データはありません。</p>';
  const factors = av.factors?.length ? `
    <div class="dialog-section">
      <h3>予測の根拠</h3>
      <div class="factor-list">${av.factors.map(f => `
        <div class="factor"><span>${f.name}<small> ${f.detail}</small></span><strong>${f.points === null ? '未観測' : `${f.points}点`}</strong></div>
      `).join('')}</div>
    </div>` : '';

  $('#dialog-content').innerHTML = `
    <div class="dialog-inner">
      <p class="kicker">FLIGHT DETAIL</p>
      <p class="dialog-route">${item.origin.iata} → ${item.destination.iata}</p>
      <p>${item.destination.city} ／ ${item.flight.flightNo} ／ ${item.flight.departure}発 ${item.flight.arrival}着</p>
      <div class="dialog-section">
        <span class="availability-tag ${availabilityClass(av.type)}">${av.typeLabel}</span>
        <h3>${av.statusLabel}${av.score !== null ? `（${av.score}点）` : ''}</h3>
        <p>${av.message}</p>
        <p class="availability-note">取得元：${av.sourceLabel}<br>観測：${formatObserved(av.observedAt)} ／ 信頼度：${av.confidence}</p>
      </div>
      ${factors}
      <div class="dialog-section"><h3>公表運賃（デモ）</h3><div class="factor-list">${fareRows}</div></div>
      <a class="official-button" href="https://www.jal.co.jp/jp/ja/dom/fare/skymate-fare/" target="_blank" rel="noopener noreferrer">JAL公式サイトで確認 ↗</a>
    </div>`;
  $('#detail-dialog').showModal();
}

$('#search-form').addEventListener('submit', (event) => { event.preventDefault(); search(); });
$('#dialog-close').addEventListener('click', () => $('#detail-dialog').close());
$('#detail-dialog').addEventListener('click', (event) => {
  if (event.target === $('#detail-dialog')) $('#detail-dialog').close();
});

document.querySelectorAll('[data-date-offset]').forEach(button => {
  button.addEventListener('click', () => {
    $('#flight-date').value = localISODate(Number(button.dataset.dateOffset));
    search();
  });
});

(async function init() {
  try {
    await loadAirports();
    readURLIntoForm();
    await search({ updateURL: !location.search });
  } catch (err) {
    $('#error').textContent = err.message;
    $('#error').hidden = false;
  }
})();
