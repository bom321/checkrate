// นาฬิกา footer
// รูปแบบต้องตรงกับ thai_datetime_full ใน app/web/thaidate.py ("02 ส.ค. 2569 14:35 น.")
// เพราะยืนบรรทัดเดียวกับ "ปรับปรุงล่าสุด" — เดิมใช้ toLocaleString('th-TH') ได้ "2/8/2569 14:35:22"
// เป็นคนละรูปแบบกันบนบรรทัดเดียว · ต่อท้ายด้วยวินาทีเพราะเป็นนาฬิกาที่เดินจริง
(function () {
  var MONTH_ABBR = ['ม.ค.', 'ก.พ.', 'มี.ค.', 'เม.ย.', 'พ.ค.', 'มิ.ย.',
                    'ก.ค.', 'ส.ค.', 'ก.ย.', 'ต.ค.', 'พ.ย.', 'ธ.ค.'];
  var BE_OFFSET = 543;

  function pad(n) { return n < 10 ? '0' + n : String(n); }

  function fmt(d) {
    return pad(d.getDate()) + ' ' + MONTH_ABBR[d.getMonth()] + ' ' + (d.getFullYear() + BE_OFFSET)
      + ' ' + pad(d.getHours()) + ':' + pad(d.getMinutes()) + ':' + pad(d.getSeconds()) + ' น.';
  }

  var el = document.getElementById('clock');
  function tick(){ if(el) el.textContent = fmt(new Date()); }
  tick(); setInterval(tick, 1000);
})();
