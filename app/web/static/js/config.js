// config.js — จัดการ banks_config.json + settings.json (ผู้รับอีเมล) ผ่านหน้าเว็บ

(function () {
  let state = { banks: [], settings: {}, logos: {} };
  const openBanks = new Set();   // index ของธนาคารที่กางอยู่ — ต้องอยู่รอดข้าม render()

  const container = document.getElementById('banks-container');
  const msgEl = document.getElementById('msg');
  const countEl = document.getElementById('banks-count');

  function notice(kind, text) {
    msgEl.innerHTML = `<div class="notice ${kind}">${text}</div>`;
    setTimeout(() => { msgEl.innerHTML = ''; }, 5000);
  }

  function esc(s) {
    return String(s ?? '').replace(/[&<>"']/g, c => ({
      '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
    }[c]));
  }

  function targetRowHtml(bIdx, tIdx, t) {
    // label ของแต่ละช่องซ่อนไว้บนจอใหญ่ (มีหัวตารางแล้ว) แต่โผล่มาบนมือถือที่แถวคลี่เป็นการ์ด
    const cell = (lab, input) =>
      `<label class="cfg-t-cell"><span class="cfg-t-lab">${lab}</span>${input}</label>`;
    return `
      <div class="cfg-t-row" data-bank="${bIdx}" data-target="${tIdx}">
        ${cell('คีย์', `<input type="text" class="t-key" value="${esc(t.key)}" placeholder="เช่น rate_3m_1m">`)}
        ${cell('ประเภทบัญชี', `<input type="text" class="t-section" value="${esc(t.section_keyword || '')}" placeholder="ค่าเริ่มต้น">`)}
        ${cell('ผลิตภัณฑ์ / ระยะ', `<input type="text" class="t-row" value="${esc(t.row_keyword || '')}" placeholder="ตามเดือน">`)}
        ${cell('ผู้รับดอกเบี้ย', `<input type="text" class="t-depositor" value="${esc(t.depositor ?? '')}" placeholder="บุคคลธรรมดา">`)}
        ${cell('เดือน', `<input type="number" step="1" class="t-tenor num" value="${t.tenor_months ?? ''}" placeholder="—">`)}
        ${cell('วงเงิน (ล้าน)', `<input type="number" step="0.1" class="t-amount num" value="${t.amount_m ?? ''}" placeholder="—">`)}
        ${cell('ชื่อย่อที่แสดง', `<input type="text" class="t-label" value="${esc(t.alias || t.label || '')}" placeholder="ชื่อ/alias ที่แสดงผล">`)}
        <button type="button" class="cfg-t-del t-remove" title="ลบแถวนี้">✕</button>
      </div>`;
  }

  function logoHtml(b) {
    const url = state.logos ? state.logos[b.code] : null;
    return url
      ? `<img class="cfg-logo" src="${esc(url)}" alt="${esc(b.code)}">`
      : `<div class="cfg-logo mono">${esc((b.code || '?')[0])}</div>`;
  }

  function bankCardHtml(b, bIdx) {
    const isOpen = openBanks.has(bIdx);
    const nTargets = (b.rate_targets || []).length;
    const targets = (b.rate_targets || []).map((t, tIdx) => targetRowHtml(bIdx, tIdx, t)).join('');
    return `
    <div class="cfg-bank${b.enabled ? '' : ' off'}${isOpen ? ' open' : ''}" data-bank-idx="${bIdx}">
      <div class="cfg-bank-head">
        <div class="cfg-bank-ident">
          ${logoHtml(b)}
          <div>
            <div class="cfg-bank-name">
              <span>${esc((b.name || '').replace('ธนาคาร', ''))}</span>
              <span class="cfg-code">${esc(b.code)}</span>
            </div>
            <div class="cfg-bank-sub">${b.enabled ? `${nTargets} อัตราที่ติดตาม` : 'ปิดใช้งานอยู่'}</div>
          </div>
        </div>
        <div class="cfg-bank-ctl">
          <label class="switch" title="เปิด-ปิดการติดตามธนาคารนี้">
            <input type="checkbox" class="b-enabled" ${b.enabled ? 'checked' : ''}>
            <span class="switch-track"><span class="switch-knob"></span></span>
            <span class="switch-text">${b.enabled ? 'เปิดใช้งาน' : 'ปิดใช้งาน'}</span>
          </label>
          <button type="button" class="cfg-chevron" aria-expanded="${isOpen}" title="กาง/ยุบ">▾</button>
        </div>
      </div>

      <div class="cfg-bank-body">
        <div class="cfg-urls">
          <label class="cfg-field wide">
            <span>REFERER</span>
            <input type="text" class="b-referer" value="${esc(b.referer)}">
          </label>
          <label class="cfg-field">
            <span>LATEST PDF URL</span>
            <input type="text" class="b-latest-url" value="${esc(b.latest_pdf_url)}"
                   placeholder="ว่าง = ให้ระบบค้นหาเอกสารล่าสุดเอง">
          </label>
          <label class="cfg-field">
            <span>PREVIOUS PDF URL</span>
            <input type="text" class="b-prev-url" value="${esc(b.prev_pdf_url)}"
                   placeholder="ว่าง = ใช้ฉบับก่อนหน้าที่เก็บไว้">
          </label>
          ${b.latest_pdf_url
            ? `<a class="link cfg-doc-link" href="${esc(b.latest_pdf_url)}" target="_blank" rel="noopener">เปิดลิงก์เอกสารปัจจุบัน ↗</a>`
            : ''}
        </div>

        <div class="cfg-targets-head">
          <span class="cfg-targets-title">อัตราที่ติดตาม</span>
          <button type="button" class="cfg-add add-target">+ เพิ่มอัตรา</button>
        </div>

        <div class="cfg-table">
          <div class="cfg-table-inner">
            <div class="cfg-t-row cfg-t-head">
              <div>คีย์</div><div>ประเภทบัญชี</div><div>ผลิตภัณฑ์ / ระยะ</div><div>ผู้รับดอกเบี้ย</div>
              <div class="num">เดือน</div><div class="num">วงเงิน</div><div>ชื่อย่อที่แสดง</div><div></div>
            </div>
            <div class="targets-list">${targets || '<div class="cfg-t-empty">ยังไม่มีอัตราที่ติดตาม — กด “+ เพิ่มอัตรา”</div>'}</div>
          </div>
        </div>
      </div>
    </div>`;
  }

  function render() {
    container.innerHTML = state.banks.map((b, i) => bankCardHtml(b, i)).join('');
    document.getElementById('email-to').value =
      Array.isArray(state.settings.email_to) ? state.settings.email_to.join(', ') : (state.settings.email_to || '');
    const on = state.banks.filter(b => b.enabled).length;
    countEl.textContent = `เปิดใช้งาน ${on} · ปิด ${state.banks.length - on}`;
    wireEvents();
  }

  function readFormIntoState() {
    container.querySelectorAll('.cfg-bank').forEach(card => {
      const bIdx = Number(card.dataset.bankIdx);
      const b = state.banks[bIdx];
      b.enabled = card.querySelector('.b-enabled').checked;
      b.latest_pdf_url = card.querySelector('.b-latest-url').value.trim();
      b.prev_pdf_url = card.querySelector('.b-prev-url').value.trim();
      b.referer = card.querySelector('.b-referer').value.trim();
      const targets = [];
      card.querySelectorAll('.cfg-t-row[data-target]').forEach(row => {
        const key = row.querySelector('.t-key').value.trim();
        if (!key) return;
        const section = row.querySelector('.t-section').value.trim();
        const rowKw = row.querySelector('.t-row').value.trim();
        const depositor = row.querySelector('.t-depositor').value.trim();
        const tenor = row.querySelector('.t-tenor').value;
        const amount = row.querySelector('.t-amount').value;
        const label = row.querySelector('.t-label').value.trim();
        const target = {
          key,
          tenor_months: tenor === '' ? null : Number(tenor),
          amount_m: amount === '' ? null : Number(amount),
          label: label || key,
          alias: label || undefined,
        };
        if (section) target.section_keyword = section;
        if (rowKw) target.row_keyword = rowKw;
        if (depositor) target.depositor = depositor;
        targets.push(target);
      });
      b.rate_targets = targets;
    });
  }

  function wireEvents() {
    // กาง/ยุบการ์ดธนาคาร — คลิกที่หัวการ์ดได้ทั้งแถบ ยกเว้นตรง toggle เปิด-ปิด
    container.querySelectorAll('.cfg-bank-head').forEach(head => {
      head.addEventListener('click', (e) => {
        if (e.target.closest('.switch')) return;
        const card = head.closest('.cfg-bank');
        const bIdx = Number(card.dataset.bankIdx);
        if (openBanks.has(bIdx)) openBanks.delete(bIdx); else openBanks.add(bIdx);
        card.classList.toggle('open');
        card.querySelector('.cfg-chevron').setAttribute('aria-expanded', String(openBanks.has(bIdx)));
      });
    });
    // เปิด-ปิดธนาคาร — render ใหม่เพื่อให้การ์ดจางลง/สว่างขึ้นตามสถานะทันที
    container.querySelectorAll('.b-enabled').forEach(chk => {
      chk.addEventListener('change', () => { readFormIntoState(); render(); });
    });
    container.querySelectorAll('.add-target').forEach(btn => {
      btn.addEventListener('click', () => {
        readFormIntoState();
        const bIdx = Number(btn.closest('.cfg-bank').dataset.bankIdx);
        state.banks[bIdx].rate_targets.push({ key: '', tenor_months: null, amount_m: null, label: '' });
        openBanks.add(bIdx);
        render();
      });
    });
    container.querySelectorAll('.t-remove').forEach(btn => {
      btn.addEventListener('click', () => {
        readFormIntoState();
        const row = btn.closest('.cfg-t-row');
        const bIdx = Number(row.dataset.bank);
        const tIdx = Number(row.dataset.target);
        state.banks[bIdx].rate_targets.splice(tIdx, 1);
        render();
      });
    });
  }

  function validateClientSide() {
    for (const b of state.banks) {
      const seen = new Set();
      for (const t of b.rate_targets) {
        if (!t.key) return `[${b.code}] มี rate target ที่ยังไม่ได้ตั้ง key`;
        if (seen.has(t.key)) return `[${b.code}] key ซ้ำ: ${t.key}`;
        seen.add(t.key);
        // ต้องตรงกับ _validate_banks() ฝั่งเซิร์ฟเวอร์ — ลำพัง "ประเภทบัญชี" ยังหาแถวในตารางไม่เจอ
        if (!t.row_keyword && !t.tenor_months) {
          return `[${b.code}] '${t.key}': ต้องระบุ "ผลิตภัณฑ์ / ระยะ" หรือ "เดือน" อย่างน้อยหนึ่งอย่าง`;
        }
      }
    }
    return null;
  }

  async function loadConfig() {
    const res = await fetch('/api/config');
    state = await res.json();
    openBanks.clear();
    render();
  }

  async function saveConfig() {
    readFormIntoState();
    const err = validateClientSide();
    if (err) { notice('err', err); return; }
    const res = await fetch('/api/config', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ banks: state.banks }),
    });
    const data = await res.json();
    if (data.ok) notice('ok', '✓ บันทึกการตั้งค่าธนาคารเรียบร้อย');
    else notice('err', 'บันทึกไม่สำเร็จ: ' + (data.error || ''));
  }

  async function saveSettings() {
    const raw = document.getElementById('email-to').value;
    const emails = raw.split(',').map(s => s.trim()).filter(Boolean);
    const res = await fetch('/api/settings', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email_to: emails }),
    });
    const data = await res.json();
    if (data.ok) notice('ok', '✓ บันทึกผู้รับอีเมลเรียบร้อย (' + (data.recipients || []).join(', ') + ')');
    else notice('err', 'บันทึกไม่สำเร็จ: ' + (data.error || ''));
  }

  document.getElementById('save-config').addEventListener('click', () => {
    if (confirm('ยืนยันบันทึกการตั้งค่าธนาคาร? การเปลี่ยนแปลงจะมีผลกับการรันครั้งถัดไป')) saveConfig();
  });
  document.getElementById('reload-config').addEventListener('click', () => {
    if (confirm('โหลดข้อมูลใหม่และยกเลิกการแก้ไขที่ยังไม่บันทึก?')) loadConfig();
  });
  document.getElementById('save-settings').addEventListener('click', saveSettings);

  loadConfig();
})();
