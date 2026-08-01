// config.js — จัดการ banks_config.json (rate_targets/enabled/ลิงก์) ผ่านหน้าเว็บ

(function () {
  let state = { banks: [], settings: {}, logos: {} };
  const openBanks = new Set();     // index ของธนาคารที่กางอยู่ — ต้องอยู่รอดข้าม render()
  const openTargets = new Set();   // `${bIdx}:${tIdx}` ของรายการอัตราที่กางอยู่ — เช่นกัน

  const container = document.getElementById('banks-container');
  const msgEl = document.getElementById('msg');
  const countEl = document.getElementById('banks-count');
  const stripOnEl = document.getElementById('strip-on');
  const stripTotalEl = document.getElementById('strip-total');

  // สีเน้นแถบซ้ายของการ์ดต่อธนาคาร — โทนเดียวกับ .ov-logo ในหน้าภาพรวม (style.css) ธนาคารที่ไม่ได้
  // ระบุไว้ (เพิ่มใหม่) ตกไปใช้สีกลางเริ่มต้นโดยอัตโนมัติ ไม่ต้องแก้ตรงนี้เพิ่ม
  const BANK_ACCENT = { SCB: '#7C5CA8', KBANK: '#1E8E5A', KTB: '#2B6CB0', BAY: '#B7791F', BBL: '#2B6CB0' };
  const BANK_ACCENT_DEFAULT = '#B0B3B9';
  // พื้นอ่อนของกล่องตัวอักษรย่อ (ใช้เฉพาะธนาคารที่ยังไม่มีไฟล์โลโก้) — คู่กับ BANK_ACCENT ตัวข้างบน
  const BANK_TINT = { SCB: '#F1EDF6', KBANK: '#E7F4EC', KTB: '#E7F0F9', BAY: '#FBF1E8', BBL: '#E6EDF5' };

  function esc(s) {
    return String(s ?? '').replace(/[&<>"']/g, c => ({
      '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
    }[c]));
  }

  // text มักมาจาก validateClientSide()/data.error ซึ่งฝัง t.key/b.code ที่ admin พิมพ์เองได้ — escape
  // เสมอ ไม่ไว้ใจว่าข้อความ error สะอาด (self-XSS ของ admin เอง แต่ทำให้สม่ำเสมอกับจุดอื่นในไฟล์นี้)
  function notice(kind, text) {
    msgEl.innerHTML = `<div class="notice ${esc(kind)}">${esc(text)}</div>`;
    setTimeout(() => { msgEl.innerHTML = ''; }, 5000);
  }

  // ธนาคารที่ parser ยังไม่รองรับโหมด max_tier/top_tier/max_all (①②③ "อัตราสูงสุด") — ว่างอยู่ตอนนี้
  // (SCB/KTB/BAY/KBANK/BBL รองรับครบแล้ว — BBL เคยอยู่ในเซ็ตนี้เพราะเป็น OCR เสี่ยงอ่านค่าสูงสุดผิด
  // แก้แล้วด้วยกลไกโหวตข้าม OCR variant ดู bbl.py/CLAUDE.md) เว็บไม่ import โค้ดฝั่ง monitor มาเช็คเอง
  // (สถาปัตยกรรมแยก web/monitor เชื่อมกันผ่านไฟล์เท่านั้น) จึง hardcode รายชื่อ parser ไว้ตรงนี้แทน
  // (ฝั่งเซิร์ฟเวอร์เช็คซ้ำอีกชั้นใน _validate_banks() กันยิง POST /api/config ตรง ๆ ข้ามหน้าเว็บ)
  const MAX_MODE_UNSUPPORTED_PARSERS = new Set([]);

  // ข้อความที่ผู้ใช้เห็นเป็นคำล้วน ไม่มีเลข ①②③ (เลขเป็นชวเลขในเอกสาร/CLI เท่านั้น) — ค่าที่เก็บลง
  // banks_config.json ยังเป็น cell/max_tier/top_tier/max_all เหมือนเดิมทุกตัวอักษร
  const MODE_OPTIONS = [
    ['cell', 'ปกติ (ระบุวงเงิน)'],
    ['max_tier', 'สูงสุดทุกวงเงิน'],
    ['top_tier', 'วงเงินสูงสุด'],
    ['max_all', 'สูงสุดทุกผู้ฝาก'],
  ];
  // placeholder ช่องคีย์ — แค่ตัวอย่างแนะนำ ไม่ได้เติมให้อัตโนมัติ (ผู้ใช้พิมพ์คีย์/ชื่อย่อเองทั้งหมด)
  const MODE_KEY_HINT = { cell: 'เช่น rate_3m_1m', max_tier: 'เช่น maxtier_12m', top_tier: 'เช่น toptier_12m', max_all: 'เช่น maxall_12m' };

  function modeSelectHtml(t, disabled) {
    const mode = t.mode && t.mode !== 'cell' ? t.mode : 'cell';
    const opts = MODE_OPTIONS.map(([v, lab]) =>
      `<option value="${v}" ${v === mode ? 'selected' : ''}>${lab}</option>`).join('');
    return `<select class="t-mode"${disabled ? ' disabled title="parser นี้ยังไม่รองรับโหมดอัตราสูงสุด"' : ''}>${opts}</select>`;
  }

  // คำเตือนสั้น ๆ ใต้แถวเมื่อโหมดปิดบางช่องอัตโนมัติ — โผล่เฉพาะตอนกางรายละเอียด
  function modeHintText(mode) {
    if (mode === 'max_all') return 'ช่อง “วงเงิน” และ “ผู้รับดอกเบี้ย” ถูกปิดอัตโนมัติ — โหมดนี้ไล่หาค่าสูงสุดจากทุกวงเงินและทุกผู้ฝาก';
    if (mode === 'max_tier' || mode === 'top_tier') return 'ช่อง “วงเงิน” ถูกปิดอัตโนมัติ — โหมดนี้ใช้ค่าสูงสุดของทั้งผลิตภัณฑ์แทนวงเงินเจาะจง';
    return '';
  }

  // ป้ายเล็กบนหัวการ์ด — สื่อสิ่งที่สำคัญที่สุดของ target นี้แบบไม่ต้องกาง เป็น "สองมิติที่ไม่เกี่ยวกัน"
  // จึงแยกป้ายกันคนละใบ (ไม่ใช่ป้ายเดียวสลับความหมายเหมือนเดิม ซึ่งทำให้ "ราชการ" หายไปทันทีที่ตั้ง
  // โหมดสูงสุด): ประเภทอัตรา (โทนแบรนด์) มาก่อนเพราะกระทบวิธีอ่านค่าทั้งแถว · ผู้รับดอกเบี้ย (โทนกลาง)
  // ตามหลัง — max_all ไล่ทุกผู้ฝากเองอยู่แล้ว จึงไม่ติดป้ายผู้รับดอกเบี้ย (ค่าที่ค้างอยู่ก็ไม่ถูกบันทึก)
  const MODE_BADGE = { max_tier: 'สูงสุด', top_tier: 'วงเงินสูงสุด', max_all: 'ทุกผู้ฝาก' };
  function badgesHtml(t, mode) {
    const badges = [];
    if (MODE_BADGE[mode]) badges.push(`<span class="cfg-t-badge mode" title="ประเภทอัตรา">${esc(MODE_BADGE[mode])}</span>`);
    if (t.depositor && mode !== 'max_all') badges.push(`<span class="cfg-t-badge dep" title="ผู้รับดอกเบี้ย">${esc(t.depositor)}</span>`);
    return badges.length ? `<span class="cfg-t-badges">${badges.join('')}</span>` : '';
  }

  // สรุปแถวเดียวที่โชว์ตอนพับ — ใช้ค่าจาก state object ตอน render() หรือจากฟอร์มสดตอนเพิ่งพับ (updateTargetSummaryFromDom)
  function targetSummary(t, mode) {
    const parts = [];
    if (mode !== 'cell') parts.push((MODE_OPTIONS.find(([v]) => v === mode) || [])[1] || '');
    if (t.tenor_months) parts.push(`${t.tenor_months} เดือน`);
    else if (t.row_keyword) parts.push(t.row_keyword);
    if (mode === 'cell' && t.amount_m !== null && t.amount_m !== undefined && t.amount_m !== '') parts.push(`${t.amount_m} ล้าน`);
    if (mode !== 'max_all') parts.push(t.depositor || 'บุคคลธรรมดา');
    return parts.join(' · ') || 'ยังไม่ได้ตั้งค่า';
  }

  function targetCardHtml(bIdx, tIdx, t, modeDisabled) {
    const isOpen = openTargets.has(`${bIdx}:${tIdx}`);
    const mode = t.mode && t.mode !== 'cell' ? t.mode : 'cell';
    // โหมด max ไม่ใช้ amount_m (ไม่เจาะวงเงินเดียว) — ปิดช่องกันสับสนว่าตั้งแล้วมีผล
    const amountDisabled = mode !== 'cell';
    // max_all ไล่ทุกคอลัมน์ผู้ฝากเอง ไม่ต้องระบุ
    const depositorDisabled = mode === 'max_all';
    const badges = badgesHtml(t, mode);
    const hint = modeHintText(mode);

    // cls เติมคลาสให้ช่อง เพื่อไล่ระดับความเข้มของป้ายชื่อ (ดู .cfg-t-lab ใน style.css)
    const cell = (lab, input, cls) =>
      `<label class="cfg-t-cell${cls ? ' ' + cls : ''}"><span class="cfg-t-lab">${lab}</span>${input}</label>`;

    // คีย์: ปกติโชว์เป็นข้อความ "(key) ✎" · คลิกแล้วสลับเป็น input — target ใหม่ที่ยังไม่มีคีย์เริ่มที่ input เลย
    // input อยู่ใน DOM ตลอด (แค่ hidden) เพื่อให้ readFormIntoState() อ่าน .t-key ได้เหมือนเดิม
    const keyEditing = !t.key;

    return `
      <div class="cfg-t-card${isOpen ? ' open' : ''}" data-bank="${bIdx}" data-target="${tIdx}">
        <div class="cfg-t-card-head">
          <button type="button" class="cfg-t-chevron" aria-expanded="${isOpen}" title="กาง/ยุบ">▾</button>
          <div class="cfg-t-titlewrap" title="คลิกเพื่อพับ/เปิดรายละเอียด">
            <input type="text" class="t-label cfg-t-name" value="${esc(t.alias || t.label || '')}" placeholder="ชื่อที่แสดง">
            <span class="cfg-t-keyview" title="คลิกเพื่อแก้ key" ${keyEditing ? 'hidden' : ''}>(<span class="cfg-t-keytext">${esc(t.key)}</span>)<span class="cfg-t-keypen">✎</span></span>
            <input type="text" class="t-key cfg-t-key" value="${esc(t.key)}" placeholder="${MODE_KEY_HINT[mode]}" ${keyEditing ? '' : 'hidden'}>
          </div>
          ${badges}
          <button type="button" class="cfg-t-del t-remove" title="ลบแถวนี้">✕</button>
        </div>
        <div class="cfg-t-summary">${esc(targetSummary(t, mode))}</div>
        <div class="cfg-t-body">
          ${cell('ประเภทอัตรา', modeSelectHtml(t, modeDisabled), 'mode')}
          ${cell('ประเภทบัญชี', `<input type="text" class="t-section" value="${esc(t.section_keyword || '')}" placeholder="ค่าเริ่มต้น">`)}
          ${cell('ผลิตภัณฑ์', `<input type="text" class="t-row" value="${esc(t.row_keyword || '')}" placeholder="ตามเดือน">`)}
          ${cell('ผู้รับดอกเบี้ย', `<input type="text" class="t-depositor" value="${esc(t.depositor ?? '')}"
                  placeholder="${depositorDisabled ? 'ทุกประเภท' : 'บุคคลธรรมดา'}" ${depositorDisabled ? 'disabled title="โหมดสูงสุดทุกผู้ฝากไล่ทุกประเภทเอง"' : ''}>`,
                depositorDisabled ? 'dim' : '')}
          ${cell('ระยะ (เดือน)', `<input type="number" step="1" class="t-tenor num" value="${esc(t.tenor_months ?? '')}" placeholder="—">`)}
          ${cell('วงเงิน (ล้าน)', `<input type="number" step="0.1" class="t-amount num" value="${esc(t.amount_m ?? '')}"
                  placeholder="${amountDisabled ? '—' : ''}" ${amountDisabled ? 'disabled title="โหมดอัตราสูงสุดไม่เจาะวงเงินเดียว"' : ''}>`,
                amountDisabled ? 'dim' : '')}
        </div>
        ${hint ? `<div class="cfg-t-hint">⊘ ${esc(hint)}</div>` : ''}
      </div>`;
  }

  // อ่านค่าฟิลด์สดจากการ์ด (ไม่ผ่าน readFormIntoState ทั้งก้อน) — ใช้ตอนพับการ์ดเพื่อรีเฟรชสรุปให้ตรง
  // กับที่เพิ่งแก้ไป โดยไม่ต้อง render() ใหม่ทั้งหน้า
  function updateTargetSummaryFromDom(card) {
    const mode = card.querySelector('.t-mode').value;
    const t = {
      tenor_months: card.querySelector('.t-tenor').value || null,
      row_keyword: card.querySelector('.t-row').value.trim(),
      amount_m: card.querySelector('.t-amount').value,
      depositor: card.querySelector('.t-depositor').value.trim(),
    };
    card.querySelector('.cfg-t-summary').textContent = targetSummary(t, mode);
    // ป้ายผู้รับดอกเบี้ยบนหัวการ์ดต้องตามค่าที่เพิ่งพิมพ์ด้วย ไม่ใช่รอ render() ทั้งหน้า
    // (ป้ายประเภทอัตราไม่ต้องห่วง — เปลี่ยนโหมดแล้ว render() ใหม่อยู่แล้ว)
    const head = card.querySelector('.cfg-t-card-head');
    const old = head.querySelector('.cfg-t-badges');
    if (old) old.remove();
    const html = badgesHtml(t, mode);
    if (html) head.querySelector('.cfg-t-del').insertAdjacentHTML('beforebegin', html);
  }

  function logoHtml(b) {
    const url = state.logos ? state.logos[b.code] : null;
    if (url) return `<img class="cfg-logo" src="${esc(url)}" alt="${esc(b.code)}">`;
    // ไม่มีไฟล์โลโก้ — ใช้ตัวอักษรย่อบนพื้น tint สีธนาคาร ธนาคารที่ยังไม่ได้ระบุสีตกไปใช้พื้นกลางเริ่มต้น
    const tint = BANK_TINT[b.code];
    const style = tint ? ` style="background:${tint};color:${BANK_ACCENT[b.code]}"` : '';
    return `<div class="cfg-logo mono"${style}>${esc((b.code || '?')[0])}</div>`;
  }

  function bankCardHtml(b, bIdx) {
    const isOpen = openBanks.has(bIdx);
    const nTargets = (b.rate_targets || []).length;
    const modeDisabled = MAX_MODE_UNSUPPORTED_PARSERS.has(b.parser);
    const targets = (b.rate_targets || []).map((t, tIdx) => targetCardHtml(bIdx, tIdx, t, modeDisabled)).join('');
    const accent = BANK_ACCENT[b.code] || BANK_ACCENT_DEFAULT;
    return `
    <div class="cfg-bank${b.enabled ? '' : ' off'}${isOpen ? ' open' : ''}" data-bank-idx="${bIdx}">
      <div class="cfg-bank-accent" style="background:${accent}"></div>
      <div class="cfg-bank-content">
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
          <div class="cfg-targets-labels">
            <span class="cfg-targets-title">อัตราที่ติดตาม</span>
            <span class="cfg-targets-hint">${nTargets} รายการ · แต่ละรายการ = 1 เส้นกราฟ + 2 คอลัมน์ CSV</span>
          </div>
          <button type="button" class="cfg-add add-target">+ เพิ่มอัตรา</button>
        </div>

        <div class="targets-list">${targets || '<div class="cfg-t-empty">ยังไม่มีอัตราที่ติดตาม — กด “+ เพิ่มอัตรา”</div>'}</div>

        ${modeDisabled ? '' : `
        <div class="cfg-mode-legend">
          <b>ประเภทอัตรา</b> ของแต่ละรายการกำหนดวิธีอ่านค่าจาก PDF · <b>ปกติ (ระบุวงเงิน)</b> อ่านตามวงเงินที่ระบุ ·
          โหมดค่าสูงสุด — ช่อง “วงเงิน” จะถูกปิดอัตโนมัติ (⊘) และเฉพาะ <b>สูงสุดทุกผู้ฝาก</b> จะปิดช่อง “ผู้รับดอกเบี้ย” ด้วย (ไล่ทุกคอลัมน์)
        </div>`}
      </div>
      </div>
    </div>`;
  }

  function render() {
    container.innerHTML = state.banks.map((b, i) => bankCardHtml(b, i)).join('');
    const on = state.banks.filter(b => b.enabled).length;
    countEl.textContent = `เปิดใช้งาน ${on} · ปิด ${state.banks.length - on}`;
    stripOnEl.innerHTML = `${on}<span class="cfg-strip-of"> / ${state.banks.length}</span>`;
    const totalTargets = state.banks.reduce((s, b) => s + (b.enabled ? (b.rate_targets || []).length : 0), 0);
    stripTotalEl.textContent = String(totalTargets);
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
      card.querySelectorAll('.cfg-t-card[data-target]').forEach(row => {
        const key = row.querySelector('.t-key').value.trim();
        if (!key) return;
        const mode = row.querySelector('.t-mode').value;
        const section = row.querySelector('.t-section').value.trim();
        const rowKw = row.querySelector('.t-row').value.trim();
        const depositor = row.querySelector('.t-depositor').value.trim();
        const tenor = row.querySelector('.t-tenor').value;
        const amount = row.querySelector('.t-amount').value;
        const label = row.querySelector('.t-label').value.trim();
        // ลำดับฟิลด์ต้องตรงกับที่เคยเขียนมาก่อนหน้านี้เป๊ะ (key, tenor_months, amount_m, label, alias, ...)
        // ไม่งั้น target เดิมที่ไม่ได้แก้อะไรเลยจะโดน key reorder ตอนบันทึก ทำให้ git diff banks_config.json
        // ขึ้นทั้งที่ค่าจริงเหมือนเดิมทุกตัวอักษร — amount_m เป็น undefined ให้ JSON.stringify ตัดคีย์ทิ้งเอง
        // เมื่อโหมด max (ไม่เจาะวงเงินเดียว) แม้ช่องจะมีค่าค้างจากก่อนสลับโหมด
        const target = {
          key,
          tenor_months: tenor === '' ? null : Number(tenor),
          amount_m: mode === 'cell' ? (amount === '' ? null : Number(amount)) : undefined,
          label: label || key,
          alias: label || undefined,
        };
        if (mode !== 'cell') target.mode = mode;
        if (section) target.section_keyword = section;
        if (rowKw) target.row_keyword = rowKw;
        // max_all ไล่ทุกคอลัมน์ผู้ฝากเอง — ไม่เขียน depositor แม้ช่องจะมีค่าค้างจากก่อนสลับโหมด
        if (depositor && mode !== 'max_all') target.depositor = depositor;
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
        const newIdx = state.banks[bIdx].rate_targets.push({ key: '', tenor_months: null, amount_m: null, label: '' }) - 1;
        openBanks.add(bIdx);
        openTargets.add(`${bIdx}:${newIdx}`);
        render();
        // การ์ดใหม่ต่อท้ายรายการ — ถ้าธนาคารมีอัตราหลายรายการ การ์ดจะอยู่ต่ำกว่าขอบจอ
        // (ปุ่ม "+ เพิ่มอัตรา" อยู่ด้านบนสุดของรายการ) ผู้ใช้จึงไม่เห็นว่ามีแถวใหม่เพิ่มมา
        const card = container.querySelector(`.cfg-t-card[data-bank="${bIdx}"][data-target="${newIdx}"]`);
        if (card) card.scrollIntoView({ behavior: 'smooth', block: 'center' });
      });
    });
    container.querySelectorAll('.t-remove').forEach(btn => {
      btn.addEventListener('click', () => {
        readFormIntoState();
        const row = btn.closest('.cfg-t-card');
        const bIdx = Number(row.dataset.bank);
        const tIdx = Number(row.dataset.target);
        const t = state.banks[bIdx].rate_targets[tIdx];
        if (t && t.mode && t.mode !== 'cell') {
          if (!confirm(`ลบ "${t.key}" — คอลัมน์นี้จะหายและประวัติข้อมูลจะหายตอน backfill รอบถัดไป ยืนยันหรือไม่?`)) return;
        }
        state.banks[bIdx].rate_targets.splice(tIdx, 1);
        // ลบแล้ว index ของรายการถัดไปในธนาคารนี้เลื่อนหมด — ล้างสถานะกาง/พับของธนาคารนี้ทิ้งกันจำผิดรายการ
        [...openTargets].forEach(k => { if (k.startsWith(`${bIdx}:`)) openTargets.delete(k); });
        render();
      });
    });
    // เปลี่ยนโหมด — render ใหม่เพื่ออัปเดตช่องที่ถูกปิด/placeholder ให้ตรงกับโหมดที่เลือกทันที
    container.querySelectorAll('.t-mode').forEach(sel => {
      sel.addEventListener('change', () => { readFormIntoState(); render(); });
    });
    // กาง/ยุบการ์ดรายการอัตรา — คลิกหัวการ์ดหรือ chevron ได้ ยกเว้นตรงช่องกรอกชื่อ/คีย์/ปุ่มลบ
    container.querySelectorAll('.cfg-t-card').forEach(card => {
      const bIdx = Number(card.dataset.bank);
      const tIdx = Number(card.dataset.target);
      const tKey = `${bIdx}:${tIdx}`;
      const toggle = () => {
        const willOpen = !card.classList.contains('open');
        if (!willOpen) updateTargetSummaryFromDom(card);
        card.classList.toggle('open', willOpen);
        card.querySelector('.cfg-t-chevron').setAttribute('aria-expanded', String(willOpen));
        if (willOpen) openTargets.add(tKey); else openTargets.delete(tKey);
      };
      card.querySelector('.cfg-t-chevron').addEventListener('click', toggle);
      card.querySelector('.cfg-t-titlewrap').addEventListener('click', (e) => {
        if (e.target.closest('input') || e.target.closest('.cfg-t-keyview')) return;
        toggle();
      });

      // คีย์: คลิกข้อความ "(key) ✎" → สลับเป็นช่องกรอก · ออกจากช่อง/กด Enter → สลับกลับพร้อมค่าใหม่
      const keyView = card.querySelector('.cfg-t-keyview');
      const keyInput = card.querySelector('.t-key');
      keyView.addEventListener('click', () => {
        keyView.hidden = true;
        keyInput.hidden = false;
        keyInput.focus();
        keyInput.select();
      });
      const endKeyEdit = () => {
        // คีย์ว่างยังไม่ให้พับกลับ — กันสถานะที่ผู้ใช้มองไม่เห็นว่ายังไม่ได้ตั้งคีย์ (บันทึกจะ error)
        if (!keyInput.value.trim()) return;
        card.querySelector('.cfg-t-keytext').textContent = keyInput.value.trim();
        keyInput.hidden = true;
        keyView.hidden = false;
      };
      keyInput.addEventListener('blur', endKeyEdit);
      keyInput.addEventListener('keydown', (e) => {
        if (e.key === 'Enter') { e.preventDefault(); endKeyEdit(); }
      });
    });
  }

  const VALID_MODES = new Set(['cell', 'max_tier', 'top_tier', 'max_all']);

  function validateClientSide() {
    for (const b of state.banks) {
      const seen = new Set();
      for (const t of b.rate_targets) {
        if (!t.key) return `[${b.code}] มี rate target ที่ยังไม่ได้ตั้ง key`;
        if (t.key === 'tiers_used') return `[${b.code}] key 'tiers_used' เป็นคีย์สงวน ห้ามใช้`;
        if (seen.has(t.key)) return `[${b.code}] key ซ้ำ: ${t.key}`;
        seen.add(t.key);
        // ต้องตรงกับ _validate_banks() ฝั่งเซิร์ฟเวอร์ — ลำพัง "ประเภทบัญชี" ยังหาแถวในตารางไม่เจอ
        if (!t.row_keyword && !t.tenor_months) {
          return `[${b.code}] '${t.key}': ต้องระบุ "ผลิตภัณฑ์" หรือ "ระยะ (เดือน)" อย่างน้อยหนึ่งอย่าง`;
        }
        if (t.mode && !VALID_MODES.has(t.mode)) {
          return `[${b.code}] '${t.key}': mode '${t.mode}' ไม่รู้จัก`;
        }
        if (t.mode && MAX_MODE_UNSUPPORTED_PARSERS.has(b.parser)) {
          return `[${b.code}] '${t.key}': parser นี้ยังไม่รองรับโหมดอัตราสูงสุด`;
        }
      }
    }
    return null;
  }

  async function loadConfig() {
    const res = await fetch('/api/config');
    state = await res.json();
    openBanks.clear();
    openTargets.clear();
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

  document.getElementById('save-config').addEventListener('click', () => {
    if (confirm('ยืนยันบันทึกการตั้งค่าธนาคาร? การเปลี่ยนแปลงจะมีผลกับการรันครั้งถัดไป')) saveConfig();
  });
  document.getElementById('reload-config').addEventListener('click', () => {
    if (confirm('โหลดข้อมูลใหม่และยกเลิกการแก้ไขที่ยังไม่บันทึก?')) loadConfig();
  });

  loadConfig();
})();
