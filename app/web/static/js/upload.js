// อัปโหลดประกาศเอง (admin) — ยิง multipart ไป /api/upload/{code} แล้วให้ run.js ติดตามงาน backfill ที่ server สั่งต่อ
(function () {
  const dlg = document.getElementById('upload-dialog');
  const openBtn = document.getElementById('upload-pdf');
  if (!dlg || !openBtn) return;
  const code = openBtn.dataset.code;
  const fileEl = document.getElementById('upload-file');
  const dateEl = document.getElementById('upload-date');
  const msgEl = document.getElementById('upload-msg');
  const submitBtn = document.getElementById('upload-submit');

  openBtn.addEventListener('click', () => { msgEl.textContent = ''; msgEl.className = 'upload-msg'; dlg.showModal(); });
  document.getElementById('upload-cancel').addEventListener('click', () => dlg.close());

  async function send(overwrite) {
    if (!fileEl.files.length) { msgEl.textContent = 'กรุณาเลือกไฟล์ PDF ก่อน'; msgEl.className = 'upload-msg err'; return; }
    const fd = new FormData();
    fd.append('file', fileEl.files[0]);
    if (dateEl.value) fd.append('date', dateEl.value);
    if (overwrite) fd.append('overwrite', '1');
    submitBtn.disabled = true;
    msgEl.textContent = 'กำลังอัปโหลดและอ่านไฟล์...'; msgEl.className = 'upload-msg';
    let data;
    try {
      const res = await fetch('/api/upload/' + code, { method: 'POST', body: fd });
      data = await res.json();
      if (!res.ok) {
        msgEl.textContent = 'ผิดพลาด: ' + (data.detail || res.status);
        msgEl.className = 'upload-msg err'; submitBtn.disabled = false; return;
      }
    } catch (e) {
      msgEl.textContent = 'อัปโหลดไม่สำเร็จ (เชื่อมต่อไม่ได้)';
      msgEl.className = 'upload-msg err'; submitBtn.disabled = false; return;
    }

    if (data.exists) {
      submitBtn.disabled = false;
      if (confirm(data.message + '\n(จะเขียนทับไฟล์ประกาศวันเดิม)')) return send(true);
      msgEl.textContent = 'ยกเลิกการเขียนทับ'; msgEl.className = 'upload-msg';
      return;
    }

    dlg.close();
    fileEl.value = ''; dateEl.value = ''; submitBtn.disabled = false;
    if (window.CheckRateRun) {
      if (data.backfill_started) {
        window.CheckRateRun.trackExternalJob('⏳ อัปโหลดแล้ว (วันที่ ' + data.date + ') — กำลังเติมข้อมูล...');
      } else {
        window.CheckRateRun.setStatus('idle', 'บันทึกไฟล์วันที่ ' + data.date + ' แล้ว — มีงานอื่นค้างอยู่ กด "เติมข้อมูลย้อนหลัง" อีกครั้งภายหลัง');
      }
    }
  }
  submitBtn.addEventListener('click', () => send(false));
})();
