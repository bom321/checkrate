// detail.js — วาดกราฟแนวโน้มด้วย Chart.js (ฟอนต์ไทยชัดเจน, self-hosted ไม่พึ่ง CDN)
(function () {
  const dataEl = document.getElementById('chart-data');
  const canvas = document.getElementById('trend');
  if (!dataEl || !canvas || typeof Chart === 'undefined') return;

  const payload = JSON.parse(dataEl.textContent);
  const palette = ['#2563eb', '#16a34a', '#d97706', '#dc2626', '#7c3aed', '#0891b2'];

  Chart.defaults.font.family = "'Noto Sans Thai', 'Segoe UI', system-ui, sans-serif";
  Chart.defaults.color = '#475569';

  const datasets = payload.datasets.map((d, i) => ({
    label: d.label,
    data: d.data,
    borderColor: palette[i % palette.length],
    backgroundColor: palette[i % palette.length],
    spanGaps: true,
    tension: 0.15,
    pointRadius: 3,
  }));

  new Chart(canvas.getContext('2d'), {
    type: 'line',
    data: { labels: payload.labels, datasets },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      interaction: { mode: 'index', intersect: false },
      scales: {
        y: { ticks: { callback: (v) => v + '%' } },
      },
      plugins: {
        legend: { position: 'bottom' },
        tooltip: {
          callbacks: { label: (ctx) => `${ctx.dataset.label}: ${ctx.parsed.y}%` },
        },
      },
    },
  });

  window.addEventListener('checkrate:run-finished', () => {
    setTimeout(() => location.reload(), 800);
  });
})();
