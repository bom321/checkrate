// logs.js — tail log พร้อม filter

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

  // ปีในบรรทัด log เป็น ค.ศ. — แปลงเป็น พ.ศ. ให้เข้าชุดกับที่อื่นในเว็บ (thaidate.py)
  function thaiTs(ts) {
    return String(ts ?? '').replace(/^(\d{4})/, (_, y) => String(Number(y) + 543));
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
        return `<div class="log-line"><span class="ts">${esc(thaiTs(l.ts))}</span>` +
               `<span class="lvl ${lvl}">${lvl}</span>` +
               `<span class="msg">${esc(l.msg)}</span></div>`;
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

  window.addEventListener('checkrate:run-finished', loadLogs);

  loadLogs();
})();
