// นาฬิกา footer
(function () {
  var el = document.getElementById('clock');
  function tick(){ if(el) el.textContent = new Date().toLocaleString('th-TH'); }
  tick(); setInterval(tick, 1000);
})();
