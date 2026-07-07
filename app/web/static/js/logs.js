// logs.js — tail log พร้อม filter, ปุ่มรันตรวจสอบ/ทดสอบส่งอีเมล

(function () {
  const consoleEl = document.getElementById('log-console');
  const levelSel = document.getElementById('f-level');
  const bankSel = document.getElementById('f-bank');
  const linesSel = document.getElementById('f-lines');
  const autoChk = document.getElementById('auto-refresh');
  let autoTimer = null;

  function esc(s) {
    return String(s ?? '').replace(/[&<>"']/g, c => ({
      '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
    }[c]));
  }

  async function loadLogs() {
    const params = new URLSearchParams({
      level: levelSel.value, bank: bankSel.value, lines: linesSel.value,
    });
    consoleEl.textContent = 'กำลังโหลด...';
    try {
      const res = await fetch('/api/logs?' + params.toString());
      const data = await res.json();
      if (!data.lines.length) {
        consoleEl.textContent = '(ไม่มี log ตรงกับเงื่อนไข)';
        return;
      }
      consoleEl.innerHTML = data.lines.map(l => {
        const lvl = esc(l.level || '');
        return `<div class="log-line"><span class="ts">${esc(l.ts)}</span> <span class="lvl ${lvl}">${lvl}</span> ${esc(l.msg)}</div>`;
      }).join('');
      consoleEl.scrollTop = consoleEl.scrollHeight;
    } catch (e) {
      consoleEl.textContent = 'โหลด log ไม่สำเร็จ';
    }
  }

  document.getElementById('refresh-logs').addEventListener('click', loadLogs);
  [levelSel, bankSel, linesSel].forEach(el => el.addEventListener('change', loadLogs));
  autoChk.addEventListener('change', () => {
    clearInterval(autoTimer);
    if (autoChk.checked) autoTimer = setInterval(loadLogs, 10000);
  });

  document.getElementById('test-email').addEventListener('click', async () => {
    const btn = document.getElementById('test-email');
    btn.disabled = true;
    CheckRateRun.setStatus('running', '⏳ กำลังส่งอีเมลทดสอบ...');
    try {
      const res = await fetch('/api/test-email', { method: 'POST' });
      const data = await res.json();
      CheckRateRun.setStatus(data.ok ? 'ok' : 'err', data.ok ? '✓ ส่งอีเมลทดสอบสำเร็จ' : '✗ ส่งไม่สำเร็จ');
      CheckRateRun.showOutput((data.output || '') + '\n\nผู้รับ: ' + (data.recipients || []).join(', '));
    } catch (e) {
      CheckRateRun.setStatus('err', 'เชื่อมต่อไม่ได้');
    }
    btn.disabled = false;
  });

  window.addEventListener('checkrate:run-finished', loadLogs);

  loadLogs();
})();
