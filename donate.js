/* 打赏组件逻辑 —— 全站共享
 * 用法：在 <head> 引入 donate.css，在 </body> 前引入本文件，
 * 并通过 data-donate-img 属性指定二维码图片路径（默认 donate.png，相对当前页面）。
 */
(function () {
  var img = document.currentScript ? document.currentScript.getAttribute('data-donate-img') : null;
  if (!img) img = 'donate.png';

  var tipText = '☕ 请老许喝碗胡辣汤';

  var pc = document.createElement('div');
  pc.id = 'donate-pc';
  pc.innerHTML =
    '<div class="d-title">请老许喝碗胡辣汤</div>' +
    '<div class="d-sub">SUPPORT · 胡辣汤基金</div>' +
    '<img src="' + img + '" alt="打赏码">' +
    '<div class="d-tip">如果今天的日报帮到你<br>请老许喝碗胡辣汤 <strong>☕</strong></div>';

  var fab = document.createElement('button');
  fab.id = 'donate-fab';
  fab.type = 'button';
  fab.textContent = '☕ 打赏';

  var modal = document.createElement('div');
  modal.id = 'donate-modal';
  modal.innerHTML =
    '<div class="dm-card">' +
    '<button class="dm-close" type="button" aria-label="关闭">✕</button>' +
    '<div class="dm-title">请老许喝碗胡辣汤</div>' +
    '<div class="dm-sub">SUPPORT · 胡辣汤基金</div>' +
    '<img src="' + img + '" alt="打赏码">' +
    '<div class="dm-tip">微信 / 支付宝扫码均可<br>谢谢你的支持 <strong>☕</strong></div>' +
    '</div>';

  document.body.appendChild(pc);
  document.body.appendChild(fab);
  document.body.appendChild(modal);

  function openModal() { modal.classList.add('show'); }
  function closeModal() { modal.classList.remove('show'); }
  fab.addEventListener('click', openModal);
  modal.querySelector('.dm-close').addEventListener('click', closeModal);
  modal.addEventListener('click', function (e) { if (e.target === modal) closeModal(); });
})();
